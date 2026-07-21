#!/bin/bash
# Run a SFINCS solve in the Singularity container as a batch job.
#   sbatch hpc/sfincs_run.slurm [model_dir]   (default: model_quadtree)
# Target partition is main-redhat: the RHEL 9.6 ("amarel-new") nodes. The older `main`
# partition is CentOS 7 (glibc 2.17) and must NOT be used — see hpc/amarel_bootstrap.md.
#SBATCH -p main-redhat
#SBATCH -c 64
#SBATCH --mem=64G
# Wave-enabled (SnapWave) solves of the 3-day Sandy window take 1:40-2:05 wall; the old
# 1 h limit silently TIMEOUTed the 2026-07-20 phaselag runs at ~80% of the window. There is
# no restart file (trstout is off), so a timeout loses the whole solve. 3 h = ~1.5x worst case.
#SBATCH -t 03:00:00
#SBATCH -J sfincs
#SBATCH -o logs/sfincs_%j.out
#SBATCH -e logs/sfincs_%j.out
# Heat-wave node losses preempt jobs. --requeue lets SLURM put a preempted/node-failed job
# back in the queue automatically instead of killing it. SFINCS re-runs the whole solve from
# scratch on requeue (it overwrites its own output), so a restart is idempotent — no checkpoint
# state to corrupt. SLURM_RESTART_COUNT tells us how many times this happened.
#SBATCH --requeue

set -euo pipefail

# Run relative to the dir the job was submitted from (= the repo root, $PROJ).
cd "${SLURM_SUBMIT_DIR:-$PWD}"
PROJ="${PROJ:-$PWD}"

MODEL="${1:-model_quadtree}"
# Override the image with: SFINCS_SIF=/path/to/x.sif sbatch hpc/sfincs_run.slurm <model>
SIF="${SFINCS_SIF:-$PROJ/sfincs-cpu.sif}"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"

echo "host=$(hostname)  job=${SLURM_JOB_ID:-none}  threads=$OMP_NUM_THREADS"
echo "model=$MODEL  sif=$SIF"
if [ "${SLURM_RESTART_COUNT:-0}" -gt 0 ]; then
    echo "NOTE: this job was requeued (restart #${SLURM_RESTART_COUNT}) — re-running the solve from scratch."
fi

# Singularity runs as the calling user, so no root-owned-output cleanup is needed
# (unlike the old Docker workflow).
# Dual-socket nodes: interleave memory across both NUMA domains so the SnapWave solver
# (which scales with cores, ~1.6x at 48 vs 16) isn't bottlenecked on one socket's memory.
NUMA=""
command -v numactl >/dev/null 2>&1 && NUMA="numactl --interleave=all"
$NUMA singularity run --bind "$(realpath "$MODEL")":/data --pwd /data "$SIF"
