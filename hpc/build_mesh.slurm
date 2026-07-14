#!/bin/bash
# Build the SEALED, UN-PAVED static mesh (Workstream L, 2026-07-14).
#
#   sbatch hpc/build_mesh.slurm [out_dir]      # default: data/frozen_mesh_sealed
#
# PARTITION (2026-07-14). `nonpre` is the natural home for this — it is the one multi-hour,
# non-restartable step in the project — but it is currently FULLY DRAINED by the NJ heat
# shutdown (all 10 nodes drng/drain, 17 jobs queued), so submitting there just waits on nodes
# that are not accepting work. Default is therefore main-redhat (~327 nodes usable).
# Override at submit time, e.g. when nonpre comes back:
#     sbatch -p nonpre hpc/build_mesh.slurm
#
# Preemption is survivable here: every partition is PreemptMode=REQUEUE, so a preempted job is
# RESTARTED rather than killed — and the requeue-safety block below clears the partial output
# that would otherwise trip freeze_mesh.py's "refusing to overwrite" guard on the second attempt.
#
# WHY THIS IS SAFE TO LAUNCH BLIND: build_static runs the domain invariants at step 5 — BEFORE
# the subgrid at step 7. A bad region/elevation aborts in ~4 minutes with a clear error, not
# after hours of subgrid tabulation. The invariants are:
#   * no free-outflow (Neumann) BC on water deeper than 1 m   <- the Navesink drain
#   * no active cell that is land where eHydro sounded water  <- the Shark River dam
# Both FAIL on the old mesh (45 and 68 cells), so they are load-bearing, not decoration.
#
# RESOURCES. The subgrid is the memory peak (it samples every elevation tier at ~3 m subgrid
# pixels across 547k faces). Earlier builds fit in ~128 GB; 150 G on a 192 GB node leaves
# headroom. The build is largely serial per block, so cores buy little — 16 is plenty.
#
#SBATCH -p main-redhat
#SBATCH -c 16
#SBATCH --mem=150G
#SBATCH -t 08:00:00
#SBATCH -J njbuild
#SBATCH -o logs/build_%j.out
#SBATCH -e logs/build_%j.out

set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-$PWD}"
PROJ="${PROJ:-$PWD}"
OUT="${1:-data/frozen_mesh_sealed}"

PY="$PROJ/micromamba/envs/sfincs/bin/python"
export NJ_ROOT="$PROJ"
export PYTHONPATH="$PROJ"
export HDF5_USE_FILE_LOCKING=FALSE
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"

echo "host=$(hostname)  job=${SLURM_JOB_ID:-none}  cpus=$OMP_NUM_THREADS  mem=${SLURM_MEM_PER_NODE:-?}"
echo "building -> $OUT   (restart_count=${SLURM_RESTART_COUNT:-0})"
echo

# REQUEUE-SAFETY. Every partition here has PreemptMode=REQUEUE, so a preempted job is
# RESTARTED FROM SCRATCH — and scripts/freeze_mesh.py refuses to overwrite an existing mesh
# ("Refusing to overwrite ... delete it first"). Without this, the second attempt would die
# instantly on its own half-written output and we would lose the build to a one-line guard.
# Clear any partial product before building.
if [ -e "$OUT" ]; then
    echo "[requeue] clearing partial output at $OUT"
    rm -rf "$OUT"
fi

# What this mesh carries that data/frozen_mesh does NOT:
#   1. region.geojson west edge at x=577,000 — encloses the Navesink to Swimming River Dam and
#      the Shark River, so the domain edge lands on DRY LAND. The old edge chopped the Navesink
#      mid-channel and hydromt put a free-outflow BC on the 5 m-deep cut face; the model then
#      drained 92.5% of the estuary's entire inflow out of the domain.
#   2. ehydro_nj.tif at the TOP of the elevation list — carves Shark River Inlet, which the
#      2010 topobathy lidar had paved over with water-surface returns (+0.4..+2.2 m), leaving
#      the whole Shark estuary at exactly +0.00 m, never flooding, through Hurricane Sandy.
#   3. refinement_polygons_25m.geojson — L4 (12.5 m) polygons EXCLUDED, so this is a clean
#      two-change rebuild (+141 faces) and not a silent +33%-runtime resolution upgrade.
time "$PY" scripts/freeze_mesh.py "$OUT"

echo
echo "=== re-verifying the built mesh ==="
"$PY" - <<'PYEOF'
import os, numpy as np, xarray as xr, rasterio
from pathlib import Path
root = Path(os.environ["NJ_ROOT"])
out = Path(os.environ.get("OUT", "data/frozen_mesh_sealed"))
if not out.is_absolute():
    out = root / out
q = xr.open_dataset(out / "sfincs.nc")
fx, fy = q["mesh2d_face_x"].values, q["mesh2d_face_y"].values
zb, m = q["z"].values, q["mask"].values
print("faces %d   active %d" % (len(zb), int((m > 0).sum())))

n = int(((m == 3) & (zb < -1.0)).sum())
print("free-outflow cells on water : %d   %s" % (n, "SEALED" if n == 0 else "*** STILL LEAKING ***"))

s = (m > 0) & (fx > 583800) & (fx < 584100) & (fy > 4447800) & (fy < 4450000)
print("Shark inlet sill            : %+.2f m   %s" % (
    zb[s].min(), "OPEN" if zb[s].min() < -1 else "*** STILL DAMMED ***"))

sg = out / "sfincs_subgrid.nc"
print("subgrid written             : %s (%.0f MB)" % (sg.exists(), sg.stat().st_size / 1e6 if sg.exists() else 0))
PYEOF

echo
echo "NEXT: point the config at it and re-stage the experiments —"
echo "  export NJ_FROZEN_MESH=$OUT"
echo "  (or edit BaseConfig.frozen_mesh in nj_sfincs/config.py)"
