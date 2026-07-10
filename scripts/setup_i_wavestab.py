"""Workstream I — bracket the Galibier SnapWave blowup.

Symptom (2026-07-10 audit): three v2.4.0 Galibier runs show isolated single-snapshot
spikes; the four v2.3.3 Faber runs do not. In ``galibier_base_25m`` the wave field
reaches hm0 = 252 m at t=32 h in 155 cells clustered at the Sandy Hook Bay mouth
(y 4473930..4475120), ~5.2 km from the Shrewsbury gauge. Faber's domain-wide max is
11.1 m, so anything above ~15 m is unphysical.

The event is *intermittent*, not deterministic-looking: ``igwaves_galibier_25m`` is the
same version, mesh and forcing (differing only by ``snapwave_igwaves=1``) and its wave
field is spotless (max hm0 9.6 m, zero cells > 15 m). That points at non-convergence of
the stationary SnapWave solver rather than a structural bug. ``snapwave_niter=100`` is
documented as being divided by 4 across the internal sweeps, i.e. ~25 iterations/sweep.

Three arms, all staged from the completed ``snapwave_tuned_25m`` inputs (frozen 25 m
mesh reused, no rebuild) with ``theta=1.0`` so each is directly comparable to
``galibier_base_25m``:

* ``galibier_repeat_25m``  — CONTROL. Byte-identical inputs to ``galibier_base_25m``.
  Does the t=32 h spike reproduce? If YES the blowup is deterministic and the two
  knob arms below are interpretable. If NO, the run is not reproducible (OpenMP
  reduction order / thread count) and a "clean" knob arm proves nothing on its own.
  This arm is what makes the bracket falsifiable — do not skip it.
* ``galibier_niter400_25m`` — ``snapwave_niter`` 100 -> 400 (~100 iters/sweep).
  Tests the non-convergence hypothesis directly.
* ``galibier_dtwave600_25m`` — ``dtwave`` 1800 -> 600 s. Couples SnapWave to SFINCS
  3x more often, so each stationary solve starts from a nearer initial guess and the
  water levels it sees change less between calls.

Deliberately NOT varied: ``snapwave_sector`` (we run 360 because ``snapwave_wind=1``;
dropping to Deltares' 180 would change the physics, not just stability) and ``huvmin``
(it only floors the velocity in uv = q/max(hu,huvmin) for output+advection; it cannot
touch hm0, so it would mask the water-level symptom while leaving the wave field wrong).

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/setup_i_wavestab.py
Then submit on the DEFAULT (Galibier) SIF — no SFINCS_SIF override:
  sbatch --time=03:00:00 hpc/sfincs_run.slurm experiments/<name>
"""

from __future__ import annotations

import shutil
from pathlib import Path

from nj_sfincs.config import ROOT

EXP = ROOT / "experiments"
SRC = EXP / "snapwave_tuned_25m"

# key -> value to set (add-or-replace) in each run's sfincs.inp.
# The first three were the 2026-07-10 bracket (control + two single-knob fixes). The
# niter200/800 arms complete the I-1 convergence sweep 100/200/400/800 (100 = the
# corrupted galibier_base_25m; 400 = galibier_niter400_25m already run) to see whether
# the Shrewsbury peak asymptotes (-> premier) or keeps climbing (-> Galibier over-setup).
RUNS = {
    "galibier_repeat_25m":   {"theta": "1.0"},
    "galibier_niter400_25m": {"theta": "1.0", "snapwave_niter": "400"},
    "galibier_dtwave600_25m": {"theta": "1.0", "dtwave": "600.0"},
    "galibier_niter200_25m": {"theta": "1.0", "snapwave_niter": "200"},
    "galibier_niter800_25m": {"theta": "1.0", "snapwave_niter": "800"},
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
    staged = []
    for name, kv in RUNS.items():
        dst = EXP / name
        # Guard: never clobber a completed run. _stage() rmtree's dst, so re-running
        # this script must skip arms that already have output. Delete the run dir by
        # hand to force a re-stage.
        if (dst / "sfincs_map.nc").exists():
            print(f"[{name}] already run (sfincs_map.nc present) — skipping.")
            continue
        print(f"[{name}] staging from {SRC.name}, setting {kv} ...")
        _stage(dst)
        _set_inp(dst / "sfincs.inp", kv)
        for stale in ("sfincs_his.nc", "snapwave.upw", "sfincs.log", "sfincs_log.txt"):
            (dst / stale).unlink(missing_ok=True)
        print(f"[{name}] ready at {dst}")
        staged.append(name)

    if staged:
        print("\nSubmit on the DEFAULT Galibier SIF (sfincs-cpu.sif) — NO override.")
        print("niter800 may ~2x the wave cost; give it 8 h. Others ~3 h.")
        for name in staged:
            wall = "08:00:00" if "niter800" in name else "03:00:00"
            print(f"  sbatch --time={wall} hpc/sfincs_run.slurm experiments/{name}")
    else:
        print("\nNothing to stage — all arms already run.")


if __name__ == "__main__":
    main()
