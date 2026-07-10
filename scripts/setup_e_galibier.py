"""Workstream F+E — set up the Galibier regression + first IG-on run.

IG deserves a fair re-test on the v2.4.0 "Galibier" container (``sfincs-cpu.sif``, the
SLURM default SIF). Subgrid format (wet-fraction, Van Ormondt 2024) is unchanged since
v2.1.1, so the frozen 25 m tables load without a rebuild.

NOTE (corrected 2026-07-10): an earlier version of this docstring credited Galibier with
"Fixed bug in SnapWave IG source term implementation". That release note belongs to
**v2.3.0 mt. Faber (2025.02)**, so the fix was already present in our v2.3.3 build — the
one where IG blew up to bay Hm0 6.9e9. Galibier does empirically make IG stable (hm0ig
max 2.7 m), but the cause is some *other* v2.4.0 change, most plausibly "Improvements of
the integrated SnapWave solver for wave breaking ... on steeper coasts".

Two runs, both derived from the completed ``snapwave_tuned_25m`` inputs (frozen
25 m mesh reused — resolution is non-binding, +0.04 m at 12.5 m):

* ``galibier_base_25m``   — regression: same inputs on Galibier, ``theta=1.0``
  explicit (a no-op vs the v2.3.3 default 1.0, just pinned). Diffing its metrics
  against ``snapwave_tuned_25m`` (built on v2.3.3) is a PURE version check — confirms
  Galibier reproduces the premier and that the subgrid tables load. (Plan F3/F4.)
* ``igwaves_galibier_25m`` — the experiment: base + ``snapwave_igwaves=1``. IG is
  generated internally from the existing incident-wave boundary (bhs/btp/bwd/bds);
  no extra input file. IG-run vs base = a PURE IG-effect diff. Tests whether the
  fixed source term is stable (v2.3.3 IG blew up to bay Hm0 6.9e9) and whether it
  helps the open-coast wave setup / back-bay runup.

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/setup_e_galibier.py
Then submit both on the DEFAULT (Galibier) SIF — no SFINCS_SIF override:
  sbatch --time=03:00:00 hpc/sfincs_run.slurm experiments/galibier_base_25m
  sbatch --time=03:00:00 hpc/sfincs_run.slurm experiments/igwaves_galibier_25m
"""

from __future__ import annotations

import shutil
from pathlib import Path

from nj_sfincs.config import ROOT

EXP = ROOT / "experiments"
SRC = EXP / "snapwave_tuned_25m"

# key -> value to set (add-or-replace) in each run's sfincs.inp
RUNS = {
    "galibier_base_25m":   {"theta": "1.0"},
    "igwaves_galibier_25m": {"theta": "1.0", "snapwave_igwaves": "1"},
}

INPUT_FILES = [
    "sfincs.inp",
    "sfincs.nc", "sfincs_subgrid.nc", "roughness.nc", "sfincs.obs",
    "sfincs_netbndbzsbzifile.nc", "sfincs_netsrcdisfile.nc",
    "sfincs_netamuv.nc", "sfincs_netampr.nc", "sfincs_netamp.nc",
    "snapwave.bnd", "snapwave.bhs", "snapwave.btp", "snapwave.bwd", "snapwave.bds",
]
INPUT_DIRS = ["subgrid"]


def _stage(dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for f in INPUT_FILES:
        shutil.copy2(SRC / f, dst / f)
    for d in INPUT_DIRS:
        shutil.copytree(SRC / d, dst / d)


def _set_inp(inp: Path, kv: dict[str, str]) -> None:
    """Add-or-replace ``key = value`` lines in a SFINCS .inp (aligned like SFINCS)."""
    lines = inp.read_text().splitlines()
    have = {ln.split("=")[0].strip() for ln in lines if "=" in ln}
    out = []
    for ln in lines:
        key = ln.split("=")[0].strip() if "=" in ln else ""
        if key in kv:
            out.append(f"{key:<20} = {kv[key]}")
        else:
            out.append(ln)
    for key, val in kv.items():
        if key not in have:
            out.append(f"{key:<20} = {val}")
    inp.write_text("\n".join(out) + "\n")


def main() -> None:
    assert (SRC / "sfincs.nc").exists(), f"built inputs not found in {SRC}"
    for name, kv in RUNS.items():
        dst = EXP / name
        print(f"[{name}] staging from {SRC.name}, setting {kv} ...")
        _stage(dst)
        _set_inp(dst / "sfincs.inp", kv)
        for stale in ("sfincs_map.nc", "sfincs_his.nc", "snapwave.upw",
                      "sfincs.log", "sfincs_log.txt"):
            (dst / stale).unlink(missing_ok=True)
        print(f"[{name}] ready at {dst}")

    print("\nSubmit both on the DEFAULT Galibier SIF (sfincs-cpu.sif) — NO override:")
    for name in RUNS:
        print(f"  sbatch --time=03:00:00 hpc/sfincs_run.slurm experiments/{name}")


if __name__ == "__main__":
    main()
