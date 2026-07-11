"""Clamp vs. dissipation discriminators — attribute the Galibier estuary lift.

Context (2026-07-11, Workstream I). Reading the SFINCS source pinned the Galibier
blowup to the "2026.01 galibier release" commit 1f1d8286, which changed two coupled
SnapWave defaults:
  * snapwave_gammax          2.0 -> 999.0   (disables the per-sweep hard wave-height
                                             clamp Hrms <= gammax*depth in the solver)
  * snapwave_baldock_exponent  0 -> 2       (steep-coast surf-zone breaking dissipation)

Faber's gammax=2 clamp is applied EVERY sweep, so Faber is unconditionally stable even
when the stationary iteration under-converges. Galibier hands all wave-height control to
the Baldock term, which is a stiff in-iteration feedback that fails to converge on the
steep Sea Bright bay mouth at niter=100 -> 252 m runaway. Removing the clamp is also why
Galibier sets the estuary up ~1 m higher (Faber 2.223 -> Galibier-niter400 3.235,
obs crest 2.935) -- but that lift rides on an unclamped solve, so its magnitude is
untrustworthy until we separate "real steep-coast setup physics" from "removed clamp."

Two one-knob discriminators, both off the Faber premier ``snapwave_tuned_25m`` (frozen
25 m mesh, inputs reused, NO rebuild):

  RUN 1  galibier_gammax2_25m   (GALIBIER sif; theta=1.0, niter=400, snapwave_gammax=2.0)
    = the clean ``galibier_niter400_25m`` baseline with ONE variable changed: gammax
      999 -> 2 (restore Faber's clamp on a CONVERGED Galibier solve). A/B vs
      galibier_niter400_25m (estuary 3.235). Estuary drops toward ~2.2 => the lift was
      the removed clamp; stays ~3.2 with a clean hm0 field => real Baldock physics and a
      stable premier candidate. This is the money run.

  RUN 2  faber_bexp2_25m        (FABER sif; snapwave_baldock_exponent=2, else stock Faber)
    = the premier + ONE knob. Faber's clamp (gammax~2) stays on, so this tests whether
      the improved surf-zone dissipation moves Faber at all (likely small/null; confirms
      the lift is the clamp, not the dissipation). A/B vs snapwave_tuned_25m (2.223).
      CAVEAT: snapwave_baldock_exponent may have been added as an input keyword in
      Galibier; the Faber v2.3.3 binary may silently ignore it. VERIFY empirically after
      the run -- diff its hm0 field vs snapwave_tuned_25m; byte-identical => Faber ignored
      the key and this run == stock Faber (inconclusive, not a null).

Submit (walltimes ~1.5 h each; 3 h cap is safe; main-redhat preemptible -> resubmit):
  RUN 1 (Galibier / DEFAULT sif):
    sbatch --time=03:00:00 hpc/sfincs_run.slurm experiments/galibier_gammax2_25m
  RUN 2 (Faber sif):
    SFINCS_SIF=$PWD/sfincs-desktop.sif sbatch --time=03:00:00 \
        hpc/sfincs_run.slurm experiments/faber_bexp2_25m

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/setup_clamp_experiments.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

from nj_sfincs.config import ROOT

EXP = ROOT / "experiments"
SRC = EXP / "snapwave_tuned_25m"          # the Faber premier (v2.3.3), niter=100

# name -> (inp keys to set, submit-on-Faber-sif?)
RUNS = {
    # RUN 1: clean Galibier (theta=1.0, niter=400) + restored clamp gammax=2
    "galibier_gammax2_25m": (
        {"theta": "1.0", "snapwave_niter": "400", "snapwave_gammax": "2.0"},
        False,   # DEFAULT (Galibier) sif
    ),
    # RUN 2: stock Faber premier + Galibier's steep-coast breaking exponent
    "faber_bexp2_25m": (
        {"snapwave_baldock_exponent": "2"},
        True,    # Faber sif
    ),
    # RUN 3: clamp OFF on the STABLE Faber engine — is the blowup the clamp or the
    # Galibier solver rework? Stock Faber premier + snapwave_gammax=999 (one knob).
    # Faber-no-clamp ALSO explodes  => the clamp is the whole stability story,
    #   engine-independent (Galibier didn't destabilize anything, it just removed the net).
    # Faber-no-clamp stays STABLE   => Galibier's solver rework (Roelvink-2025-consistent
    #   breaking) introduced instability beyond the clamp removal.
    # A/B vs snapwave_tuned_25m (2.223, stable). Completes the 2x2 with RUN 1.
    "faber_gammax999_25m": (
        {"snapwave_gammax": "999.0"},
        True,    # Faber sif
    ),
}

INPUT_FILES = [
    "sfincs.inp",
    "sfincs.nc", "sfincs_subgrid.nc", "roughness.nc", "sfincs.obs",
    "sfincs_netbndbzsbzifile.nc", "sfincs_netsrcdisfile.nc",
    "sfincs_netamuv.nc", "sfincs_netampr.nc", "sfincs_netamp.nc",
    "snapwave.bnd", "snapwave.bhs", "snapwave.btp", "snapwave.bwd", "snapwave.bds",
]
INPUT_DIRS = ["subgrid"]


def _set_inp(inp: Path, kv: dict[str, str]) -> None:
    """Overwrite keys already present; append any that are missing."""
    lines = inp.read_text().splitlines()
    have = {ln.split("=")[0].strip() for ln in lines if "=" in ln}
    out = []
    for ln in lines:
        key = ln.split("=")[0].strip() if "=" in ln else ""
        out.append(f"{key:<20} = {kv[key]}" if key in kv else ln)
    for key, val in kv.items():
        if key not in have:
            out.append(f"{key:<20} = {val}")
    inp.write_text("\n".join(out) + "\n")


def _stage(name: str, kv: dict[str, str]) -> bool:
    dst = EXP / name
    if (dst / "sfincs_map.nc").exists():
        print(f"[{name}] already run -- skipping (delete dir to re-stage).")
        return False
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for f in INPUT_FILES:
        shutil.copy2(SRC / f, dst / f)
    for d in INPUT_DIRS:
        if (SRC / d).exists():
            shutil.copytree(SRC / d, dst / d)
    _set_inp(dst / "sfincs.inp", kv)
    for stale in ("sfincs_his.nc", "snapwave.upw", "sfincs.log", "sfincs_log.txt"):
        (dst / stale).unlink(missing_ok=True)
    print(f"[{name}] staged from {SRC.name}, set {kv}")
    return True


def main() -> None:
    assert (SRC / "sfincs.nc").exists(), f"built inputs not found in {SRC}"
    for name, (kv, faber) in RUNS.items():
        _stage(name, kv)
    print("\nSubmit (48 cores + NUMA interleave via the updated slurm script):")
    for name, (kv, faber) in RUNS.items():
        pre = "SFINCS_SIF=$PWD/sfincs-desktop.sif " if faber else ""
        print(f"  {pre}sbatch --time=03:00:00 hpc/sfincs_run.slurm experiments/{name}")


if __name__ == "__main__":
    main()
