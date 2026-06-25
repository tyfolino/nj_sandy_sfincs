#!/bin/bash
# Execute a notebook headless on a compute node (build + forcing + inline solve
# + validation). The run_sfincs() cell auto-uses Singularity here.
#   sbatch hpc/run_notebook.slurm [notebook.ipynb]
# Default: the quadtree notebook. Target main-redhat (RHEL 9.6) — see amarel_bootstrap.md.
#SBATCH -p main-redhat
#SBATCH -c 24
#SBATCH --mem=40G
#SBATCH -t 03:00:00
#SBATCH -J nb_exec
#SBATCH -o logs/nb_exec_%j.out
#SBATCH -e logs/nb_exec_%j.out

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$PWD}"
PROJ="${PROJ:-$PWD}"
ENV="$PROJ/micromamba/envs/sfincs"
MM="$PROJ/micromamba/bin/micromamba"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
# Some build cells write/read GeoTIFFs; point GDAL/PROJ at the env data dirs.
export PROJ_LIB="$ENV/share/proj" PROJ_DATA="$ENV/share/proj" GDAL_DATA="$ENV/share/gdal"

NB="${1:-notebooks/sfincs-nj-sandy.ipynb}"
NBNAME="$(basename "$NB")"
NBDIR="$(dirname "$NB")"
OUT="${NBNAME%.ipynb}.executed.ipynb"

echo "host=$(hostname)  job=${SLURM_JOB_ID:-none}  threads=$OMP_NUM_THREADS  nb=$NB"

# Run with cwd = the notebook's dir so the notebook's relative paths
# (../data, ../model_quadtree, ../sfincs-cpu.sif) resolve.
cd "$NBDIR"
"$MM" run -n sfincs jupyter nbconvert --to notebook --execute \
  --ExecutePreprocessor.timeout=-1 \
  --ExecutePreprocessor.kernel_name=sfincs \
  --allow-errors \
  --output "$OUT" "$NBNAME"

echo "wrote $NBDIR/$OUT"
