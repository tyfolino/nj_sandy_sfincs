#!/bin/bash
# Run a SFINCS solve in the Singularity container as a batch job.
#   sbatch hpc/sfincs_run.slurm [model_dir]   (default: model_quadtree)
# Target partition is main-redhat: the RHEL 9.6 ("amarel-new") nodes. The older `main`
# partition is CentOS 7 (glibc 2.17) and must NOT be used — see hpc/amarel_bootstrap.md.
#SBATCH -p main-redhat
#SBATCH -c 24
#SBATCH --mem=24G
#SBATCH -t 01:00:00
#SBATCH -J sfincs
#SBATCH -o logs/sfincs_%j.out
#SBATCH -e logs/sfincs_%j.out

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

# Singularity runs as the calling user, so no root-owned-output cleanup is needed
# (unlike the old Docker workflow).
singularity run --bind "$(realpath "$MODEL")":/data --pwd /data "$SIF"
