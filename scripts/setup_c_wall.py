"""Workstream C — set up the N/NW boundary flux/wall experiments.

Derives two runs from the ALREADY-BUILT ``experiments/snapwave_tuned`` inputs
(same mesh, subgrid, forcing, SnapWave) — so nothing is rebuilt and the frozen
mesh is reused. The only differences:

* ``nw_open``  — snapwave_tuned + velocity output (``storevel=1``). Identical
  physics to the premier run; the open-boundary baseline for the flux budget.
* ``nw_wall``  — same, but the N/NW (Raritan Bay / lower-harbor) waterlevel
  boundary cells are CLOSED (mask 2 -> 0). A boundary-TYPE change only, so the
  subgrid/mesh are untouched (no rebuild). Diagnostic A/B vs nw_open.

The Atlantic open-ocean surge boundary (the eastern edge) is left intact — only
the northern edge (northing > WALL_Y) is walled.

Interpretation caveat: walling removes the REAL NY-Harbor surge inflow as well as
any hypothetical "escape", so read the pair together with the flux budget, not the
wall alone.

Run:  micromamba/envs/sfincs/bin/python scripts/setup_c_wall.py
Then submit both (see the printed sbatch commands).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import xarray as xr

from nj_sfincs.config import ROOT

EXP = ROOT / "experiments"
SRC = EXP / "snapwave_tuned"
WALL_Y = 4_480_000.0   # UTM 18N northing; cells north of this = N/NW harbor boundary

# Built inputs to carry over (everything EXCEPT run outputs, which the solver
# regenerates: sfincs_map.nc, sfincs_his.nc, snapwave.upw, logs, floodmap, gis/).
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


def _enable_velocity_output(inp: Path) -> None:
    """Turn on velocity output so we can measure the N/NW boundary flux budget."""
    lines = inp.read_text().splitlines()
    have = {ln.split("=")[0].strip() for ln in lines if "=" in ln}
    out = []
    for ln in lines:
        key = ln.split("=")[0].strip() if "=" in ln else ""
        if key == "storevel":
            out.append("storevel             = 1")
        else:
            out.append(ln)
    if "storevel" not in have:
        out.append("storevel             = 1")
    inp.write_text("\n".join(out) + "\n")


def _wall_nw_boundary(sfincs_nc: Path) -> int:
    """Close the N/NW waterlevel boundary (mask 2 -> 0) north of WALL_Y.

    Boundary-TYPE change only — subgrid tables index cells by position, not mask,
    so no subgrid rebuild is needed. Also drops those cells from the SnapWave mask
    for consistency (the north is not a wave boundary anyway).
    """
    ds = xr.open_dataset(sfincs_nc)
    ds.load()          # pull everything into memory
    ds.close()         # release the file handle before overwriting (avoids Errno 13)

    target = (ds["mask"].values == 2) & (ds["mesh2d_face_y"].values > WALL_Y)
    n = int(target.sum())
    mask = ds["mask"].values.copy()
    mask[target] = 0
    ds["mask"] = ds["mask"].copy(data=mask)
    if "snapwave_mask" in ds:
        sw = ds["snapwave_mask"].values.copy()
        sw[target] = 0
        ds["snapwave_mask"] = ds["snapwave_mask"].copy(data=sw)

    tmp = sfincs_nc.with_suffix(".nc.tmp")
    ds.to_netcdf(tmp)
    tmp.replace(sfincs_nc)
    return n


def main() -> None:
    assert (SRC / "sfincs.nc").exists(), f"built inputs not found in {SRC}"
    for name, wall in [("nw_open", False), ("nw_wall", True)]:
        dst = EXP / name
        print(f"[{name}] staging inputs from {SRC.name} ...")
        _stage(dst)
        _enable_velocity_output(dst / "sfincs.inp")
        if wall:
            n = _wall_nw_boundary(dst / "sfincs.nc")
            print(f"[{name}] walled {n} N/NW waterlevel cells (mask 2->0, northing>{WALL_Y:.0f})")
        # clear any stale outputs
        for stale in ("sfincs_map.nc", "sfincs_his.nc", "snapwave.upw",
                      "sfincs.log", "sfincs_log.txt"):
            (dst / stale).unlink(missing_ok=True)
        print(f"[{name}] ready at {dst}")

    print("\nSubmit both. MUST use sfincs-desktop.sif = v2.3.3 (the build that made")
    print("snapwave_tuned); the SLURM default sfincs-cpu.sif is v2.4.0 Galibier, which")
    print("would conflate the wall test with a version change. Override the 1 h cap too:")
    print("  export SFINCS_SIF=$PWD/sfincs-desktop.sif")
    print("  sbatch --time=03:00:00 hpc/sfincs_run.slurm experiments/nw_open")
    print("  sbatch --time=03:00:00 hpc/sfincs_run.slurm experiments/nw_wall")


if __name__ == "__main__":
    main()
