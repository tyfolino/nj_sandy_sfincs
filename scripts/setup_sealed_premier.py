"""Workstream O — re-establish the PREMIER on the sealed, un-paved domain.

Every engine/knob comparison in this campaign — Faber vs Galibier, the niter sweeps, the
clamp study, wind, friction, the narrows-width test — ran on a domain that was **draining
92.5% of the estuary's inflow out of a hole in the Navesink** and had **Shark River Inlet
dammed shut**. Their null results are *explained*, not *informative*. So the premier question
is reopened, and this is the 2x2 that answers it on a domain that is not broken.

  faber     sfincs-desktop.sif (v2.3.0). Ships snapwave_gammax = 2 -> the per-sweep hard
            clamp Hrms <= gammax*depth is ALWAYS on, which makes it unconditionally stable.
  galibier  sfincs-cpu.sif. Commit 1f1d8286 set snapwave_gammax 2 -> 999, i.e. it REMOVED
            that clamp and leans on Baldock dissipation alone, which is stiff and
            non-converging on the steep Sea Bright bay mouth -> a 252 m runaway wave.
            **So the Galibier arms carry snapwave_gammax = 2.0 explicitly.** That finding is
            about the SOURCE CODE, not the domain, so it survives the rebuild intact — and it
            is the only way to compare the two engines' physics rather than one engine's bug.

Each engine runs with waves ON (the premier config: SnapWave + wind + Tim's tuned physics)
and OFF (the still-water control). The no-waves arms cost ~10 min and are the ones that
isolate hydrodynamics from wave setup.

WHAT THIS RUN HAS TO SHOW (write it down before looking):

  1. SHARK RIVER MUST HAVE A TIDE. This is the cleanest, storm-independent test in the whole
     project, and it needs no HWM and no surge. Observed at USGS 01407770: a 1.52 m per-cycle
     tidal range that rises 47% of the time. The old model: **frac_rising = 0.00 — the basin
     never oscillated at all**, because its inlet was dammed. If the carve worked, Shark now
     floods and ebbs. If it does not, nothing else here matters.
  2. SHREWSBURY MUST HOLD. The leak fix took its HWM bias -0.42 -> +0.21 and its gauge
     2.223 -> 2.691 (obs 2.935). The region fix should reproduce that, having reached it by
     fixing the CAUSE (the region polygon) rather than the symptom (a post-hoc mask edit).
  3. THE BASINS THAT NEVER BROKE MUST NOT MOVE. South-coast bias was -0.0553 and stayed
     -0.0553 through the leak fix. A domain fix is LOCAL. If the open coast shifts, we have
     changed something we did not mean to change, and the result is not trustworthy.

Every arm keeps crsfile/storevel, so the flux partition and the leak checks are re-measured
on the sealed domain automatically.

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD NJ_FROZEN_MESH=data/frozen_mesh_sealed \
      micromamba/envs/sfincs/bin/python scripts/setup_sealed_premier.py
"""

from __future__ import annotations

import gc
import os
import shutil
from pathlib import Path

from hydromt_sfincs import SfincsModel

import nj_sfincs  # noqa: F401  (PROJ primer — must precede hydromt_sfincs)
from nj_sfincs import model
from nj_sfincs.config import EXPERIMENTS, ROOT, BaseConfig

EXP = ROOT / "experiments"
TEMPLATE = EXP / "_template_sealed"
CRS_SRC = ROOT / "data" / "flux_crosssections.crs"

# Static/forcing files are identical across all four arms -> hard-link them (each is ~1.8 GB
# copied, and the disk quota is not infinite). Only sfincs.inp is per-arm, so only it is copied.
COPY_FILES = {"sfincs.inp"}

# waves ON = the premier's own settings; OFF = the still-water control.
ARMS = {
    "sealed_faber_waves":      dict(sif="sfincs-desktop.sif", waves=True,  gammax=None),
    "sealed_faber_nowaves":    dict(sif="sfincs-desktop.sif", waves=False, gammax=None),
    "sealed_galibier_waves":   dict(sif="sfincs-cpu.sif",     waves=True,  gammax="2.0"),
    "sealed_galibier_nowaves": dict(sif="sfincs-cpu.sif",     waves=False, gammax="2.0"),
}
DIAG = {"crsfile": "sfincs.crs", "storevel": "1"}


def build_template(base: BaseConfig) -> None:
    """Static build (from the SEALED frozen mesh) + forcing + waves -> _template_sealed."""
    if TEMPLATE.exists():
        shutil.rmtree(TEMPLATE)
    print(f"[template] static build from frozen_mesh={base.frozen_mesh}")
    model.build_static(base, TEMPLATE)

    sf = SfincsModel(str(TEMPLATE), data_libs=base.data_libs, mode="r+")
    model.add_forcing(base, sf)
    # Stage WITH waves so snapwave.* exist; the no-waves arms simply set snapwave=0 and ignore
    # them. This is exactly how scripts/setup_leak_fix.py staged its 2x2, and it means all four
    # arms share one identical set of inputs — the only difference is sfincs.inp.
    wave_cfg = EXPERIMENTS["snapwave_tuned"].waves
    sw = model.add_waves(wave_cfg, base, sf)
    model.finalize(wave_cfg, base, sf, TEMPLATE, sw)
    del sf
    gc.collect()
    print("[template] done")


def _set_inp(inp: Path, kv: dict) -> None:
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


def stage(name: str, spec: dict) -> Path:
    dst = EXP / name
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)

    for src in sorted(TEMPLATE.iterdir()):
        if src.is_dir():
            shutil.copytree(
                src, dst / src.name,
                copy_function=lambda s, d: os.link(s, d),
            )
        elif src.name in COPY_FILES:
            shutil.copy2(src, dst / src.name)
        else:
            os.link(src, dst / src.name)

    if CRS_SRC.exists():
        shutil.copy2(CRS_SRC, dst / "sfincs.crs")

    kv = dict(DIAG)
    if spec["waves"]:
        kv |= {"snapwave": "1", "storefw": "1", "storewavdir": "1"}
    else:
        kv |= {"snapwave": "0", "storefw": "0", "storewavdir": "0"}
    if spec["gammax"] is not None:
        # Galibier removed the clamp (2 -> 999). Put it back, or we are comparing Faber's
        # physics against Galibier's instability rather than against Galibier's physics.
        kv["snapwave_gammax"] = spec["gammax"]
    _set_inp(dst / "sfincs.inp", kv)

    for stale in ("sfincs_his.nc", "sfincs_map.nc", "snapwave.upw", "sfincs.log"):
        (dst / stale).unlink(missing_ok=True)
    return dst


def main() -> None:
    frozen = os.environ.get("NJ_FROZEN_MESH", "")
    if "sealed" not in frozen:
        raise SystemExit(
            "Refusing to stage: NJ_FROZEN_MESH is %r.\n"
            "This 2x2 is meaningless on the OLD (leaking, dammed) mesh — that is the whole\n"
            "point of it. Set NJ_FROZEN_MESH=data/frozen_mesh_sealed." % (frozen or "unset")
        )
    base = BaseConfig()
    if not (Path(base.frozen_mesh) / "sfincs_subgrid.nc").exists():
        raise SystemExit(f"no subgrid in {base.frozen_mesh} — has the rebuild finished?")

    build_template(base)

    print("\nstaged:")
    for name, spec in ARMS.items():
        stage(name, spec)
        print(f"  experiments/{name:<26s} {spec['sif']:<20s} "
              f"waves={'ON ' if spec['waves'] else 'OFF'}"
              f"{'  snapwave_gammax=' + spec['gammax'] if spec['gammax'] else ''}")

    print("\nsubmit:")
    for name, spec in ARMS.items():
        t = "00:40:00" if not spec["waves"] else "04:00:00"
        print(f"  SFINCS_SIF=$PWD/{spec['sif']} sbatch --time={t} "
              f"hpc/sfincs_run.slurm experiments/{name}")


if __name__ == "__main__":
    main()
