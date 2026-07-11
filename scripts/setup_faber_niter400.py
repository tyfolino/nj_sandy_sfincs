"""Branch-(b) discriminator — Faber engine with the wave solver converged.

Context (2026-07-10, Workstream I). The niter convergence sweep so far has been run
only on the Galibier engine, where the Shrewsbury peak climbs Faber-100 2.223 ->
Galibier-400 3.235 -> dtwave600 3.610 (obs crest 2.935). Two open readings:
  (a) the answer is converging and Galibier is right, or
  (b) Galibier's wave-breaking-on-steep-coasts rework over-injects setup into the
      sheltered estuary and no iteration count fixes it.

We have implicitly pinned Faber at 2.223, but that is Faber at the *unconverged* default
niter=100. We never tested whether Faber also rises with more iterations. This run closes
that gap: it is the cheap discriminator.

  * If Faber-niter400 stays near ~2.2 -> the niter sensitivity is Galibier-specific
    (its wave-breaking change), reinforcing branch (b); Faber is a stable premier
    candidate for the surge/estuary validation (Galibier reserved for the IG re-test).
  * If Faber-niter400 also climbs toward ~2.9 -> the under-convergence is general to the
    SnapWave solver, not a Galibier defect, and Faber-converged may match obs best of all.

This is the ONLY change from the Faber premier ``snapwave_tuned_25m``: snapwave_niter
100 -> 400. No theta line (Faber default 1.0), same inputs, same frozen 25 m mesh.

CRITICAL: submit on the FABER container, NOT the default Galibier SIF:
  SFINCS_SIF=$PWD/sfincs-desktop.sif sbatch --time=03:00:00 \
      hpc/sfincs_run.slurm experiments/faber_niter400_25m

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/setup_faber_niter400.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

from nj_sfincs.config import ROOT

EXP = ROOT / "experiments"
SRC = EXP / "snapwave_tuned_25m"          # the Faber premier (v2.3.3), niter=100
DST = EXP / "faber_niter400_25m"
SET = {"snapwave_niter": "400"}           # ONLY change; no theta (Faber default 1.0)

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
    assert (SRC / "sfincs.nc").exists(), f"built inputs not found in {SRC}"
    if (DST / "sfincs_map.nc").exists():
        print(f"[faber_niter400_25m] already run — skipping (delete dir to re-stage).")
        return
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)
    for f in INPUT_FILES:
        shutil.copy2(SRC / f, DST / f)
    for d in INPUT_DIRS:
        if (SRC / d).exists():
            shutil.copytree(SRC / d, DST / d)
    _set_inp(DST / "sfincs.inp", SET)
    for stale in ("sfincs_his.nc", "snapwave.upw", "sfincs.log", "sfincs_log.txt"):
        (DST / stale).unlink(missing_ok=True)
    print(f"[faber_niter400_25m] staged from {SRC.name}, set {SET}")
    print("Submit on the FABER SIF (NOT the default Galibier):")
    print("  SFINCS_SIF=$PWD/sfincs-desktop.sif sbatch --time=03:00:00 "
          "hpc/sfincs_run.slurm experiments/faber_niter400_25m")


if __name__ == "__main__":
    main()
