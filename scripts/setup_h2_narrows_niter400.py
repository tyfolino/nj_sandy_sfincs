"""Workstream H (re-run) — narrows-widen A/B on the CONVERGED wave solver.

The original H verdict compared ``narrows_wide_h`` against ``galibier_base_25m``, but
Workstream I (2026-07-10) showed galibier_base is corrupted throughout by the t=32 h
SnapWave non-convergence blowup (snapwave_niter=100 truncates the stationary solver at
a steep coast -> unphysical 252 m wave -> poisoned state). ``snapwave_niter=400`` cures
it (blowup 155 -> 3 cell-steps, both gauges clean). ``narrows_wide_h`` itself ran at
niter=100 and had 13 blowup cell-steps, so BOTH arms of the original H test were tainted.

This re-runs the width test cleanly: both arms at niter=400, Galibier, theta=1.0,
differing ONLY by the subgrid (dredged vs frozen). The baseline arm already exists as
``galibier_niter400_25m`` (normal subgrid, done, clean). This script stages the dredge
arm from the ``narrows_wide_h`` inputs (which carry the dredged sfincs_subgrid.nc) and
flips snapwave_niter 100 -> 400.

Verdict: compare ``narrows_wide_niter400_25m`` vs ``galibier_niter400_25m`` at the real
surge peak (~t=49 h) on the Shrewsbury gauge + basin-partitioned estuary HWMs + tidal
range. If the estuary still over-fills relative to obs (crest 2.935 m), width is a real
lever (eHydro under-captures the 2012 channel). If the two arms converge, the earlier
"+0.81 m width" headline was an artifact of comparing against the corrupted baseline.

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/setup_h2_narrows_niter400.py
Then submit on the DEFAULT (Galibier) SIF, generous walltime (niter400 fills more wet
cells -> ~1h50m like galibier_niter400_25m, but the cap almost never binds so cost is
close to base; give it 4 h to be safe):
  sbatch --time=04:00:00 hpc/sfincs_run.slurm experiments/narrows_wide_niter400_25m
"""

from __future__ import annotations

import shutil
from pathlib import Path

from nj_sfincs.config import ROOT

EXP = ROOT / "experiments"
SRC = EXP / "narrows_wide_h"          # carries the DREDGED subgrid
DST = EXP / "narrows_wide_niter400_25m"
SET = {"snapwave_niter": "400"}       # theta=1.0 already set in narrows_wide_h

INPUT_FILES = [
    "sfincs.inp",
    "sfincs.nc", "sfincs_subgrid.nc", "roughness.nc", "sfincs.obs",
    "sfincs_netbndbzsbzifile.nc", "sfincs_netsrcdisfile.nc",
    "sfincs_netamuv.nc", "sfincs_netampr.nc", "sfincs_netamp.nc",
    "snapwave.bnd", "snapwave.bhs", "snapwave.btp", "snapwave.bwd", "snapwave.bds",
]
INPUT_DIRS = ["subgrid"]


def _set_inp(inp: Path, kv: dict[str, str]) -> None:
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


def main() -> None:
    assert (SRC / "sfincs_subgrid.nc").exists(), f"dredged inputs not found in {SRC}"
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)
    for f in INPUT_FILES:
        shutil.copy2(SRC / f, DST / f)
    for d in INPUT_DIRS:
        if (SRC / d).exists():
            shutil.copytree(SRC / d, DST / d)
    _set_inp(DST / "sfincs.inp", SET)
    for stale in ("sfincs_map.nc", "sfincs_his.nc", "snapwave.upw",
                  "sfincs.log", "sfincs_log.txt"):
        (DST / stale).unlink(missing_ok=True)
    print(f"[narrows_wide_niter400_25m] staged from {SRC.name}, set {SET}")
    print("Submit on DEFAULT Galibier SIF:")
    print("  sbatch --time=04:00:00 hpc/sfincs_run.slurm experiments/narrows_wide_niter400_25m")


if __name__ == "__main__":
    main()
