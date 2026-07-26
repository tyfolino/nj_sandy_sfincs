"""Run SFINCS locally (Singularity/Docker) or submit it to SLURM.

``run_sfincs`` is lifted verbatim from notebooks/sfincs-nj-sandy.ipynb cell 56
(the auto-detecting container runner with numactl + OMP thread handling).
``submit_slurm`` wraps the existing hpc/sfincs_run.slurm batch template.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .config import ROOT


def run_sfincs(model_root, sif: str | None = None):
    """Run SFINCS in the deltares/sfincs-cpu container (Singularity or Docker)."""
    model_abs = Path(model_root).resolve()
    log_path = model_abs / "sfincs_log.txt"
    threads = os.environ.get("OMP_NUM_THREADS") or str(os.cpu_count() or 1)
    if sif is None:
        sif = os.environ.get("SFINCS_SIF", str(ROOT / "sfincs-cpu.sif"))

    # Clear stale outputs first — a held-open sfincs_map.nc/his.nc triggers HDF5
    # file-locking that makes SFINCS silently write ZERO output.
    for stale in ("sfincs_map.nc", "sfincs_his.nc"):
        try:
            (model_abs / stale).unlink()
        except FileNotFoundError:
            pass

    if shutil.which("singularity"):
        sif_abs = Path(os.environ.get("SFINCS_SIF", sif)).resolve()
        # With SnapWave on, the solver scales across BOTH sockets; interleave
        # memory pages so neither socket starves on remote bandwidth.
        numa = ["numactl", "--interleave=all"] if shutil.which("numactl") else []
        bind = os.environ.get("OMP_PROC_BIND", "spread")
        places = os.environ.get("OMP_PLACES", "cores")
        env = {
            **os.environ,
            "OMP_NUM_THREADS": threads,
            "OMP_PROC_BIND": bind,
            "OMP_PLACES": places,
            "SINGULARITYENV_OMP_NUM_THREADS": threads,
            "SINGULARITYENV_OMP_PROC_BIND": bind,
            "SINGULARITYENV_OMP_PLACES": places,
            "APPTAINERENV_OMP_NUM_THREADS": threads,
            "APPTAINERENV_OMP_PROC_BIND": bind,
            "APPTAINERENV_OMP_PLACES": places,
        }
        print(
            f"Running SFINCS via Singularity ({sif_abs.name}) "
            f"[OMP={threads}{', mem-interleaved' if numa else ''}] ..."
        )
        with open(log_path, "w") as lf:
            return subprocess.run(
                numa + [
                    "singularity", "run",
                    "--bind", f"{model_abs}:/data",
                    "--pwd", "/data",
                    str(sif_abs),
                ],
                stdout=lf, stderr=subprocess.STDOUT, env=env,
            )
    if shutil.which("docker"):
        print(f"Running SFINCS via Docker [OMP={threads}] ...")
        subprocess.run(  # clear root-owned stale outputs from a prior Docker run
            ["docker", "run", "--rm", "-v", f"{model_abs}:/data",
             "--entrypoint", "/bin/sh", "deltares/sfincs-cpu:latest",
             "-c", "rm -f /data/sfincs_map.nc /data/sfincs_his.nc"],
            capture_output=True,
        )
        with open(log_path, "w") as lf:
            return subprocess.run(
                ["docker", "run", "--rm", "-v", f"{model_abs}:/data",
                 "deltares/sfincs-cpu:latest"],
                stdout=lf, stderr=subprocess.STDOUT,
            )
    raise RuntimeError("Neither 'singularity' nor 'docker' on PATH.")


def submit_slurm(model_dir, sif: str | None = None,
                 slurm_script: Path | None = None,
                 extra_args: list[str] | None = None) -> str | None:
    """Submit one SFINCS solve via ``sbatch hpc/sfincs_run.slurm <model_dir>``.

    The batch script runs relative to the submit dir (= repo root), so we sbatch
    from ROOT and pass the model dir as a path relative to it. Returns the job id.

    ``sif`` picks the engine and is passed through as SFINCS_SIF. Pass it
    explicitly (``base.container_sif``) — if it is left to the batch script's own
    fallback the SLURM path silently runs a DIFFERENT engine than the local path,
    which is how the 2026-07-20 phaselag runs ended up on Galibier (sfincs-cpu.sif)
    instead of the sealed premier's Faber (sfincs-desktop.sif).
    """
    if slurm_script is None:
        slurm_script = ROOT / "hpc" / "sfincs_run.slurm"
    if not shutil.which("sbatch"):
        raise RuntimeError("'sbatch' not on PATH — not on a SLURM cluster?")

    env = dict(os.environ)
    if sif is not None:
        sif_abs = Path(sif).resolve()
        if not sif_abs.exists():
            raise FileNotFoundError(f"container image not found: {sif_abs}")
        env["SFINCS_SIF"] = str(sif_abs)
    print(f"[slurm] engine = {Path(env.get('SFINCS_SIF', 'batch-script default')).name}")

    model_abs = Path(model_dir).resolve()
    try:
        model_arg = str(model_abs.relative_to(ROOT))
    except ValueError:
        model_arg = str(model_abs)

    # sbatch CLI flags override the #SBATCH directives in the script, so this is the
    # way to give one job a longer wall clock (e.g. ["--time=06:00:00"]) without
    # editing the shared batch script for every future run.
    cmd = ["sbatch", *(extra_args or []), str(slurm_script), model_arg]
    if extra_args:
        print(f"[slurm] sbatch overrides: {' '.join(extra_args)}")
    proc = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True, env=env,
    )
    print(proc.stdout.strip() or proc.stderr.strip())
    if proc.returncode != 0:
        raise RuntimeError(f"sbatch failed: {proc.stderr.strip()}")
    m = re.search(r"Submitted batch job (\d+)", proc.stdout)
    return m.group(1) if m else None
