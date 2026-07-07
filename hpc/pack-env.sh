#!/usr/bin/env bash
# hpc/pack-env.sh — pack the sfincs conda env into a tarball for fast compute-node deploys.
#
# Run this once (and again after any "micromamba install" into the sfincs env):
#   ./hpc/pack-env.sh
#
# Output: $PROJ/sfincs-env.tar.gz  (~1-1.5 GB)
# That tarball is unpacked to /tmp/$USER/sfincs on the compute node by vscode_node.sh.
set -euo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MM="$PROJ/micromamba/bin/micromamba"
OUT="$PROJ/sfincs-env.tar.gz"

echo "Packing sfincs env → $OUT"
echo "(this takes ~2-3 minutes; only needed again after 'micromamba install' into sfincs)"
echo ""

"$MM" run -n base conda-pack -p "$PROJ/micromamba/envs/sfincs" -o "$OUT" --force \
  --ignore-editable-packages

echo ""
echo "Done: $(du -sh "$OUT" | cut -f1)  →  $OUT"
echo "Next: run ./hpc/vscode_node.sh — it will unpack this onto the compute node automatically."
