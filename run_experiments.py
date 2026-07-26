#!/usr/bin/env python
"""Run the NJ Sandy SnapWave sensitivity experiments.

The static build + base forcing are built ONCE into ``experiments/_template``
(they are identical across every wave experiment); each experiment then copies
the template, layers on its SnapWave knobs, runs SFINCS, and is validated. Skill
metrics are aggregated into ``experiments/metrics.csv`` and a self-contained
``experiments/report.html``.

Examples
--------
    # Build inputs for the baseline, no solver (fast sanity check):
    python run_experiments.py --experiments baseline_no_waves --dry-run

    # Cheap smoke test: one short-window run end-to-end:
    python run_experiments.py --experiments baseline_no_waves --tstop 2012-10-29

    # Full local sweep:
    python run_experiments.py

    # Submit every experiment to SLURM, then aggregate once they finish:
    python run_experiments.py --slurm
    python run_experiments.py --validate-only

Run from the repo root (or set NJ_ROOT).
"""

from __future__ import annotations

import argparse
import gc
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# Import the package first — its __init__ primes PROJ before hydromt_sfincs loads
# (see nj_sfincs/__init__.py). Keep this ahead of the hydromt_sfincs import.
from nj_sfincs import model, premier, report, run, validate
from nj_sfincs.config import EXPERIMENTS, ROOT, BaseConfig, WaveConfig, with_window

from hydromt_sfincs import SfincsModel

EXP_ROOT = ROOT / "experiments"

# THE domain every new experiment is staged from. See nj_sfincs/premier.py: this used to
# be `_template` (the pre-rebuild, leaking-Navesink / dammed-Shark build), which silently
# voided the whole 2026-07-20 phase-lag A/B. Overridable via NJ_TEMPLATE for deliberate
# work on another domain — the lineage assert below still reports what you actually got.
TEMPLATE = Path(os.environ.get("NJ_TEMPLATE", premier.SEALED_TEMPLATE))
FLOODMAPS = EXP_ROOT / "floodmaps"
METRICS_CSV = EXP_ROOT / "metrics.csv"

NO_WAVES = WaveConfig(use_waves=False)


TEMPLATE_STAMP = TEMPLATE / ".window"


def build_template(base: BaseConfig) -> None:
    """Static build + base forcing → the template dir (written once)."""
    # GUARD: this function rmtree's its target. The sealed template is the base of the
    # adopted premier and is hard-linked into every sealed_* run; it was built by
    # scripts/setup_sealed_premier.py against NJ_FROZEN_MESH=data/frozen_mesh_sealed and
    # is NOT reproducible from BaseConfig alone. Rebuilding it here would silently
    # substitute a different domain under the premier's name — the exact class of failure
    # premier.py exists to prevent.
    if premier.is_sealed(TEMPLATE):
        raise SystemExit(
            f"refusing to rebuild {TEMPLATE}: it is the SEALED template "
            f"({premier.SEALED}), the base of premier '{premier.PREMIER_NAME}'.\n"
            "  Rebuild it with scripts/setup_sealed_premier.py (with "
            f"NJ_FROZEN_MESH={premier.SEALED_FROZEN_MESH}), or point NJ_TEMPLATE "
            "somewhere else to build a scratch template."
        )
    print(f"[template] building static model + forcing in {TEMPLATE} ...")
    if TEMPLATE.exists():
        shutil.rmtree(TEMPLATE)
    model.build_static(base, TEMPLATE)

    sf = SfincsModel(str(TEMPLATE), data_libs=base.data_libs, mode="r+")
    model.add_forcing(base, sf)
    model.finalize(NO_WAVES, base, sf, TEMPLATE, None)
    del sf
    gc.collect()
    # Stamp the window so a later run with a different window rebuilds rather
    # than silently reusing a truncated (smoke-test) template.
    TEMPLATE_STAMP.write_text(base.tstop.isoformat())
    print("[template] done")


def template_matches(base: BaseConfig) -> bool:
    """True iff a built template exists for exactly this run window.

    The .window stamp is written by build_template. The sealed template was NOT built
    here and carries no stamp, so fall back to its own sfincs.inp — otherwise it reads as
    stale and we would try to rebuild (and destroy) it on every invocation.
    """
    if not (TEMPLATE / "sfincs.inp").exists():
        return False
    if TEMPLATE_STAMP.exists():
        return TEMPLATE_STAMP.read_text().strip() == base.tstop.isoformat()
    return _inp_tstop(TEMPLATE) == base.tstop


def _inp_tstop(model_dir: Path) -> datetime | None:
    """Parse ``tstop`` out of a sfincs.inp (``YYYYMMDD HHMMSS``)."""
    for line in (model_dir / "sfincs.inp").read_text().splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "tstop":
            try:
                return datetime.strptime(value.strip(), "%Y%m%d %H%M%S")
            except ValueError:
                return None
    return None


def prepare_experiment(name: str, base: BaseConfig) -> Path:
    """Copy the template and apply the experiment's wave knobs. Returns exp dir."""
    exp = EXPERIMENTS[name]
    exp_dir = EXP_ROOT / name
    print(f"[{name}] preparing ({exp.description})")
    if exp_dir.exists():
        shutil.rmtree(exp_dir)
    shutil.copytree(TEMPLATE, exp_dir)
    # Fail here, before the solver burns an hour on the wrong planet.
    premier.assert_sealed_domain(exp_dir, context=f"staging '{name}' from {TEMPLATE.name}")

    sf = SfincsModel(str(exp_dir), data_libs=base.data_libs, mode="r+")
    sf.read()
    # Optional per-experiment water-level forcing swap (a forcing A/B). Re-runs
    # water_level.create on the boundary cells the template already carved;
    # merge=False REPLACES the template's Battery forcing (merge=True would append
    # and leave the stale bnd in place). finalize() below loads + writes it.
    if exp.waterlevel_geodataset is not None:
        print(f"[{name}] overriding water-level forcing → {exp.waterlevel_geodataset}")
        sf.water_level.create(
            geodataset=exp.waterlevel_geodataset,
            buffer=base.waterlevel_buffer,
            merge=False,
        )
    sw = model.add_waves(exp.waves, base, sf) if exp.waves.use_waves else None
    model.finalize(exp.waves, base, sf, exp_dir, sw)
    # hydromt's writer drops crsfile/storevel; put them back so a staged arm carries the
    # same diagnostics as the sealed premier and the inp-diff stays honest.
    model.restore_diagnostics(exp_dir)
    del sf
    gc.collect()
    return exp_dir


def collect_metrics(names: list[str]) -> pd.DataFrame:
    """Validate each existing experiment dir and aggregate to a DataFrame."""
    FLOODMAPS.mkdir(parents=True, exist_ok=True)
    rows = {}
    for name in names:
        exp_dir = EXP_ROOT / name
        if not (exp_dir / "sfincs_map.nc").exists():
            print(f"[{name}] no sfincs_map.nc — skipping validation")
            continue
        print(f"[{name}] validating ...")
        try:
            rows[name] = validate.evaluate(
                exp_dir, gallery_tif=FLOODMAPS / f"{name}_hmax_lev3.tif"
            )
        except Exception as e:  # noqa: BLE001
            print(f"[{name}] validation failed: {e}")
            rows[name] = {"error": str(e)}
        # Stamp the domain onto every row. A metrics table whose numbers do not say which
        # domain they came from is how the phase-lag A/B got compared against a premier it
        # never shared a mesh with. Scoring legacy runs stays legal — silently is not.
        sealed = premier.is_sealed(exp_dir)
        rows[name]["domain"] = "sealed" if sealed else "NOT-SEALED"
        if not sealed:
            print(f"[{name}] *** WARNING: not on the sealed domain "
                  f"({premier.domain_fingerprint(exp_dir)}) — not comparable to "
                  f"'{premier.PREMIER_NAME}'. See nj_sfincs/premier.py.")
    return pd.DataFrame.from_dict(rows, orient="index")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--experiments", default="all",
                   help="comma-separated preset names, or 'all' (default). "
                        f"Choices: {', '.join(EXPERIMENTS)}")
    p.add_argument("--rebuild-template", action="store_true",
                   help="force-rebuild experiments/_template even if it exists")
    p.add_argument("--no-run", action="store_true",
                   help="build inputs but do not run the solver")
    p.add_argument("--dry-run", action="store_true",
                   help="build inputs only, skip solver AND validation")
    p.add_argument("--slurm", action="store_true",
                   help="submit each experiment via hpc/sfincs_run.slurm instead of "
                        "running locally (validate later with --validate-only)")
    p.add_argument("--validate-only", action="store_true",
                   help="skip build/run; just (re)aggregate metrics + report")
    p.add_argument("--tstop", default=None,
                   help="override the run end date (YYYY-MM-DD) for a short smoke "
                        "test; forces a template rebuild")
    args = p.parse_args(argv)

    names = list(EXPERIMENTS) if args.experiments == "all" \
        else [n.strip() for n in args.experiments.split(",")]
    unknown = [n for n in names if n not in EXPERIMENTS]
    if unknown:
        p.error(f"unknown experiment(s): {unknown}. Choices: {list(EXPERIMENTS)}")

    base = BaseConfig()
    if args.tstop:
        base = with_window(base, datetime.strptime(args.tstop, "%Y-%m-%d"))
        print(f"[window] short run: tstop = {base.tstop:%Y-%m-%d}")

    EXP_ROOT.mkdir(parents=True, exist_ok=True)

    # ── validate-only: just re-aggregate ─────────────────────────────────────
    if args.validate_only:
        df = collect_metrics(names)
        _write_outputs(df)
        return 0

    # ── build template (once) ────────────────────────────────────────────────
    if args.rebuild_template or not template_matches(base):
        build_template(base)
    else:
        print(f"[template] reusing existing {TEMPLATE} for window ending "
              f"{base.tstop:%Y-%m-%d} (pass --rebuild-template to force a rebuild)")

    # ── per-experiment prepare + run ─────────────────────────────────────────
    submitted = {}
    for name in names:
        exp_dir = prepare_experiment(name, base)
        if args.dry_run or args.no_run:
            print(f"[{name}] inputs written to {exp_dir} (solver skipped)")
            continue
        if args.slurm:
            job = run.submit_slurm(exp_dir, sif=str(base.container_sif))
            submitted[name] = job
            print(f"[{name}] submitted SLURM job {job}")
        else:
            result = run.run_sfincs(exp_dir, sif=str(base.container_sif))
            print(f"[{name}] solver return code {result.returncode}")

    if args.dry_run or args.no_run:
        print("Done (inputs only).")
        return 0
    if args.slurm:
        print("\nSubmitted:", submitted)
        print("When the jobs finish, run:  python run_experiments.py --validate-only")
        return 0

    # ── local: validate + aggregate ──────────────────────────────────────────
    df = collect_metrics(names)
    _write_outputs(df)
    return 0


def _write_outputs(df: pd.DataFrame) -> None:
    if df.empty:
        print("No metrics to write (no completed runs found).")
        return
    df.to_csv(METRICS_CSV)
    print(f"\nwrote {METRICS_CSV}")
    try:
        rpt = report.generate_html_report(df, EXP_ROOT)
        print(f"wrote {rpt}")
    except Exception as e:  # noqa: BLE001
        print(f"(report generation skipped: {e})")
    with pd.option_context("display.width", 200, "display.max_columns", 50):
        print("\n" + df.to_string())


if __name__ == "__main__":
    sys.exit(main())
