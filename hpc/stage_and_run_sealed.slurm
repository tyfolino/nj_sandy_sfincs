#!/bin/bash
# Chain job: stage + launch the sealed-domain PREMIER 2x2 (Workstream O).
#
#   sbatch --dependency=afterok:<BUILD_JOBID> hpc/stage_and_run_sealed.slurm
#
# Fires ONLY if the mesh build succeeded (afterok). It then:
#   1. builds experiments/_template_sealed off data/frozen_mesh_sealed (static + forcing + waves)
#   2. stages the four arms (faber|galibier x waves|nowaves), hard-linking the ~1.8 GB of shared
#      inputs so four arms cost one copy
#   3. submits each to SFINCS with the CORRECT container:
#        faber    = sfincs-desktop.sif   (ships snapwave_gammax=2 -> the stability clamp is on)
#        galibier = sfincs-cpu.sif       (+ snapwave_gammax=2 forced back on in sfincs.inp;
#                                         Galibier's default of 999 REMOVES the clamp and gives
#                                         a 252 m runaway wave at the Sea Bright bay mouth)
#
# The no-waves arms finish in ~10 min and carry the headline result: does SHARK RIVER now have
# a TIDE? Observed 1.52 m per-cycle, rising 47% of the time; the old model never oscillated at
# all (frac_rising = 0.00) because its inlet was dammed shut. That test needs no storm peak and
# no high-water marks, and it is the cleanest thing in this project.
#
#SBATCH -p main-redhat
#SBATCH -c 8
#SBATCH --mem=100G
#SBATCH -t 02:00:00
#SBATCH -J njstage
#SBATCH -o logs/stage_%j.out
#SBATCH -e logs/stage_%j.out

set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-$PWD}"
PROJ="${PROJ:-$PWD}"
PY="$PROJ/micromamba/envs/sfincs/bin/python"

export NJ_ROOT="$PROJ"
export PYTHONPATH="$PROJ"
export NJ_FROZEN_MESH="${NJ_FROZEN_MESH:-data/frozen_mesh_sealed}"
export HDF5_USE_FILE_LOCKING=FALSE

echo "host=$(hostname)  job=${SLURM_JOB_ID:-none}"
echo "frozen mesh: $NJ_FROZEN_MESH"
echo

# Guard: afterok should mean the mesh exists, but check rather than stage onto nothing.
if [ ! -f "$NJ_FROZEN_MESH/sfincs_subgrid.nc" ]; then
    echo "ERROR: no subgrid at $NJ_FROZEN_MESH — the build did not produce a usable mesh."
    exit 1
fi

"$PY" scripts/setup_sealed_premier.py

echo
echo "=== submitting the 2x2 ==="
# nowaves first: they finish in ~10 min and answer the Shark-tide question before the
# 4-hour wave arms are even warm.
SFINCS_SIF=$PROJ/sfincs-desktop.sif sbatch --time=00:40:00 hpc/sfincs_run.slurm experiments/faber-nowaves
SFINCS_SIF=$PROJ/sfincs-cpu.sif     sbatch --time=00:40:00 hpc/sfincs_run.slurm experiments/galibier-nowaves
SFINCS_SIF=$PROJ/sfincs-desktop.sif sbatch --time=04:00:00 hpc/sfincs_run.slurm experiments/faber-waves-premier
SFINCS_SIF=$PROJ/sfincs-cpu.sif     sbatch --time=04:00:00 hpc/sfincs_run.slurm experiments/galibier-waves

echo
echo "submitted. when they land:"
echo "  NJ_ROOT=\$PWD PYTHONPATH=\$PWD $PY scripts/analyze_sealed.py"
