"""Workstream D — set up the wind-sensitivity (drag) experiments.

Derives two runs from the ALREADY-BUILT ``experiments/snapwave_tuned_25m`` inputs
(same mesh, subgrid, forcing, SnapWave) — forcing-only change, nothing rebuilt,
frozen mesh reused. The only difference from that baseline is the wind-drag
coefficient ``cdval`` in ``sfincs.inp``, scaled up to bracket the sensitivity:

* ``wind_cd120_25m`` — cdval x1.20 (wind stress +20%)
* ``wind_cd130_25m`` — cdval x1.30 (wind stress +30%)

We run these on the 25 m mesh (not the 12.5 m premier): refining 25 m -> 12.5 m
moved the Shrewsbury gauge only +0.04 m (resolution is non-binding for this
signal), so the wind *delta* is the same while each run is ~30% cheaper. The
apples-to-apples baseline for the A/B is the completed ``snapwave_tuned_25m``,
NOT the 12.5 m premier — both arms must share the mesh.

Wind stress = rho_air * Cd * W^2, so scaling Cd scales the stress linearly; this
is the one legitimate ERA5 lever (peak magnitude — direction/structure are fine
for a storm as large as Sandy). Evaluate on basin-partitioned inner HWMs + river
gauges + tidal range (NOT pooled HWM bias): does more wind lift the bay toward
~3.4 m AND help the inner rivers without overshooting the validated seaward levels?

Run:  micromamba/envs/sfincs/bin/python scripts/setup_d_wind.py
Then submit both (see the printed sbatch commands).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from nj_sfincs.config import ROOT

EXP = ROOT / "experiments"
SRC = EXP / "snapwave_tuned_25m"   # 25 m baseline (resolution non-binding: +0.04 m at 12.5 m)

# scale factor per experiment name
RUNS = {"wind_cd120_25m": 1.20, "wind_cd130_25m": 1.30}

# Built inputs to carry over (everything EXCEPT run outputs the solver regenerates).
INPUT_FILES = [
    "sfincs.inp",
    "sfincs.nc", "sfincs_subgrid.nc", "roughness.nc", "sfincs.obs",
    "sfincs_netbndbzsbzifile.nc", "sfincs_netsrcdisfile.nc",
    "sfincs_netamuv.nc", "sfincs_netampr.nc", "sfincs_netamp.nc",
    "snapwave.bnd", "snapwave.bhs", "snapwave.btp", "snapwave.bwd", "snapwave.bds",
]
INPUT_DIRS = ["subgrid"]  # per-level dep/manning tifs (floodmap downscale in validation)


def _stage(dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for f in INPUT_FILES:
        shutil.copy2(SRC / f, dst / f)
    for d in INPUT_DIRS:
        shutil.copytree(SRC / d, dst / d)


def _scale_cdval(inp: Path, factor: float) -> str:
    """Scale the wind-drag breakpoints ``cdval`` by ``factor`` (stress lever).

    Leaves ``cdwnd`` (the wind-speed breakpoints) untouched — only the drag
    coefficients at those speeds are raised.
    """
    lines = inp.read_text().splitlines()
    out, changed = [], None
    for ln in lines:
        key = ln.split("=")[0].strip() if "=" in ln else ""
        if key == "cdval":
            vals = [float(v) for v in ln.split("=", 1)[1].split()]
            scaled = [v * factor for v in vals]
            changed = scaled
            out.append("cdval                = " + " ".join(f"{v:.6g}" for v in scaled))
        else:
            out.append(ln)
    assert changed is not None, f"no cdval line found in {inp}"
    inp.write_text("\n".join(out) + "\n")
    return " ".join(f"{v:.6g}" for v in changed)


def main() -> None:
    assert (SRC / "sfincs.nc").exists(), f"built inputs not found in {SRC}"
    for name, factor in RUNS.items():
        dst = EXP / name
        print(f"[{name}] staging inputs from {SRC.name} (cdval x{factor:.2f}) ...")
        _stage(dst)
        new = _scale_cdval(dst / "sfincs.inp", factor)
        for stale in ("sfincs_map.nc", "sfincs_his.nc", "snapwave.upw",
                      "sfincs.log", "sfincs_log.txt"):
            (dst / stale).unlink(missing_ok=True)
        print(f"[{name}] cdval -> {new}   ready at {dst}")

    print("\nSubmit both. MUST use sfincs-desktop.sif = v2.3.3 (the build that made")
    print("snapwave_tuned_25m) so the sensitivity is not conflated with a version change:")
    print("  export SFINCS_SIF=$PWD/sfincs-desktop.sif")
    for name in RUNS:
        print(f"  sbatch --time=03:00:00 hpc/sfincs_run.slurm experiments/{name}")


if __name__ == "__main__":
    main()
