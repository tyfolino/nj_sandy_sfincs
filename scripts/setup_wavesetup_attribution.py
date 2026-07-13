"""Attribute the ~1.16 m Faber-vs-Galibier estuary gap to a specific piece of physics.

Context (2026-07-13, Workstream I). The clamp discriminators
(``scripts/setup_clamp_experiments.py``) settled the STABILITY question and reopened the
PREMIER question:

  * RUN 3 ``faber_gammax999_25m``  -> Faber WITHOUT the clamp explodes too (hm0 16,247 m,
    8,067 cell-steps > 15 m).  The gammax=2 clamp is the stability mechanism, and it is
    ENGINE-INDEPENDENT.  Faber was never the more robust solver; it just kept the net up.
  * RUN 1 ``galibier_gammax2_25m`` -> Galibier WITH the clamp restored does NOT collapse
    back to Faber's level.  Shrewsbury stays at 3.380 m with the cleanest wave field of the
    campaign (hm0 max 9.80 m, ZERO cells > 15 m, spike-free gauges, peak at the true surge
    time).  So Galibier's estuary lift SURVIVES a clamped, converged, spike-free solve =>
    it is real wave-setup physics, NOT a blowup artifact.  The 07-11 "Faber = premier"
    verdict is retracted.
  * RUN 2 ``faber_bexp2_25m``      -> INCONCLUSIVE: its hm0 field is bit-identical to stock
    Faber, so the v2.3.3 binary silently ignores ``snapwave_baldock_exponent`` (a keyword
    added in Galibier).  The exponent CANNOT be tested on Faber -- test it on Galibier.

Where that leaves us: Faber 2.223 (-0.71) and Galibier-clamped 3.380 (+0.45) BRACKET the
observed crest 2.935 m.  The wave-setup formulation is now the largest single lever in the
whole campaign (1.16 m -- vs a wind null of +0.002, a 0.81 m narrows over-dredge, and a
0.60 m response to an unphysical 1.8 m bay wall).  These four runs pin down what that
1.16 m actually IS.  All are one-knob arms off already-built inputs (frozen 25 m mesh,
NO subgrid rebuild).

  A  galibier_gammax2_niter100_25m  (GALIBIER; gammax=2, niter=100)
       Is the CLAMPED Galibier converged in niter the way Faber is?  RUN 1 used niter=400.
       Same answer at niter=100 => the clamped config is genuinely stable AND converged (a
       real premier candidate, and 4x cheaper to run).  Different answer => the clamp alone
       does not buy convergence and niter must stay pinned at 400.
       A/B vs galibier_gammax2_25m (3.380).

  B  galibier_gammax2_bexp0_25m     (GALIBIER; gammax=2, niter=400, baldock_exponent=0)
       Isolates the Baldock steep-coast exponent on a STABLE, CLAMPED solve -- the test
       RUN 2 was meant to do but could not, because Faber cannot read the keyword.  This is
       the only arm that can attribute the lift to a named parameter.
       Drops toward ~2.2 => the lift IS the Baldock exponent (a documented, citable physics
       change).  Stays ~3.4 => the lift is the REST of the v2.4.0 SnapWave solver rework
       (Roelvink et al. 2025, GMD) and no single input keyword explains it.
       A/B vs galibier_gammax2_25m (3.380).

  C  faber_nowaves_25m              (FABER;    snapwave=0)
  D  galibier_nowaves_25m           (GALIBIER; snapwave=0, theta=1.0)
       Workstream I-3.  Turn the wave solver OFF on both engines.  Wind drag on the water
       surface (cdval/cdwnd) STAYS ON, so this removes wave setup specifically, not wind.
       If C and D agree (expected -- the barotropic core barely changed between versions),
       then the ENTIRE 1.16 m engine gap is wave setup, proven rather than inferred, and
       both engines share a common no-wave baseline to measure setup against.
       If C and D DISAGREE, something outside SnapWave changed between versions and every
       version A/B in this campaign is confounded.
       These are the cheap ones: SnapWave was ~85% of runtime, so expect ~15-25 min.

Submit (64 cores; main-redhat is preemptible -> resubmit if a job dies):
  A  sbatch --time=03:00:00 hpc/sfincs_run.slurm experiments/galibier_gammax2_niter100_25m
  B  sbatch --time=03:00:00 hpc/sfincs_run.slurm experiments/galibier_gammax2_bexp0_25m
  D  sbatch --time=03:00:00 hpc/sfincs_run.slurm experiments/galibier_nowaves_25m
  C  SFINCS_SIF=$PWD/sfincs-desktop.sif sbatch --time=03:00:00 \
         hpc/sfincs_run.slurm experiments/faber_nowaves_25m

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python \
          scripts/setup_wavesetup_attribution.py
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from nj_sfincs.config import ROOT

EXP = ROOT / "experiments"
SRC = EXP / "snapwave_tuned_25m"          # the Faber premier (v2.3.3), niter=100

# name -> (inp keys to set, run-on-Faber-sif?)
RUNS = {
    # A: is the clamped Galibier converged w.r.t. niter?
    "galibier_gammax2_niter100_25m": (
        {"theta": "1.0", "snapwave_niter": "100", "snapwave_gammax": "2.0"},
        False,   # DEFAULT (Galibier) sif
    ),
    # B: isolate the Baldock exponent on a stable, clamped Galibier solve.
    "galibier_gammax2_bexp0_25m": (
        {"theta": "1.0", "snapwave_niter": "400", "snapwave_gammax": "2.0",
         "snapwave_baldock_exponent": "0"},
        False,   # DEFAULT (Galibier) sif
    ),
    # C/D (Workstream I-3): wave solver OFF on each engine. Wind drag stays on.
    #
    # storefw/storewavdir MUST be turned off alongside snapwave=0. Leaving them at 1 makes
    # SFINCS try to write the wave-friction / wave-direction fields at finalisation, but
    # with the wave solver off those arrays were never allocated -> SIGSEGV *after* the
    # solve completes ("Closing off SFINCS" is printed, then it dies). The crash happens
    # during netCDF close, so sfincs_map.nc is left TRUNCATED (26 of 73 steps) while
    # sfincs_his.nc, already flushed, survives intact. Bit both engines identically
    # (v2.3.3 and v2.4.0) -> upstream bug, worth including in the Deltares report.
    "faber_nowaves_25m": (
        {"snapwave": "0", "storefw": "0", "storewavdir": "0"},
        True,    # Faber sif
    ),
    "galibier_nowaves_25m": (
        {"theta": "1.0", "snapwave": "0", "storefw": "0", "storewavdir": "0"},
        False,   # DEFAULT (Galibier) sif
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


# SFINCS only ever READS its inputs, so hard-link them instead of copying. Private copies
# (~1.8 GB per run: mesh + subgrid tables + the subgrid/ GeoTIFFs) duplicated across ~26
# experiments blew through the disk quota on 2026-07-13 and killed two jobs mid-write.
# A hard link is transparent to SFINCS and to the Singularity bind mount.
# sfincs.inp is the sole exception: it is the one file we rewrite per run, so it must be
# a real private copy or every experiment would share (and clobber) one config.
COPY_FILES = {"sfincs.inp"}


def _place(src: Path, dst: Path) -> None:
    """Hard-link every read-only input; copy only the files we rewrite."""
    if Path(src).name in COPY_FILES:
        shutil.copy2(src, dst)
    else:
        os.link(src, dst)


def _stage(name: str, kv: dict[str, str]) -> bool:
    dst = EXP / name
    if (dst / "sfincs_map.nc").exists():
        print(f"[{name}] already run -- skipping (delete dir to re-stage).")
        return False
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for f in INPUT_FILES:
        _place(SRC / f, dst / f)
    for d in INPUT_DIRS:
        if (SRC / d).exists():
            shutil.copytree(SRC / d, dst / d, copy_function=_place)
    _set_inp(dst / "sfincs.inp", kv)
    for stale in ("sfincs_his.nc", "snapwave.upw", "sfincs.log", "sfincs_log.txt"):
        (dst / stale).unlink(missing_ok=True)
    print(f"[{name}] staged from {SRC.name}, set {kv}")
    return True


def main() -> None:
    assert (SRC / "sfincs.nc").exists(), f"built inputs not found in {SRC}"
    for name, (kv, _faber) in RUNS.items():
        _stage(name, kv)
    print("\nSubmit (64 cores + NUMA interleave via hpc/sfincs_run.slurm):")
    for name, (_kv, faber) in RUNS.items():
        pre = "SFINCS_SIF=$PWD/sfincs-desktop.sif " if faber else ""
        print(f"  {pre}sbatch --time=03:00:00 hpc/sfincs_run.slurm experiments/{name}")


if __name__ == "__main__":
    main()
