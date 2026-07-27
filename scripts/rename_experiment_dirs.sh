#!/usr/bin/env bash
# Rename the run directories to the 2026-07-27 convention (see docs/naming.md).
#
# experiments/ is GITIGNORED -- git cannot undo this. The inverse is written to
# scripts/rename_experiment_dirs_REVERT.sh by this script before anything moves.
#
# All moves are within one filesystem => metadata-only, so hard-linked staged inputs
# (see the disk-quota/dedupe note) are preserved and no data is copied.
set -euo pipefail
cd "$(dirname "$0")/.."
E=experiments

MAP=(
  "sealed_faber_waves:faber-waves-premier"
  "sealed_faber_nowaves:faber-nowaves"
  "sealed_galibier_waves:galibier-waves"
  "sealed_galibier_nowaves:galibier-nowaves"
  "sealed_igwaves_wind:wave-ig"
  "sealed_bdepth_m15:mask-zmin15"
  "sealed_bdepth_m20:mask-zmin20"
  "snapwave_deep:wave-deep30"
  "phaselag_shift:tide-shift"
  "snapwave_deep_phaseshift:wave-deep30+tide-shift"
)
# NOT renamed, deliberately: _template, _template_sealed (guarded by premier.py),
# snapwave_deep_composite_v2 (retired, archival), floodmaps/.

REVERT=scripts/rename_experiment_dirs_REVERT.sh
{ echo "#!/usr/bin/env bash"
  echo "# Auto-generated inverse of rename_experiment_dirs.sh. Run to undo."
  echo "set -euo pipefail"
  echo 'cd "$(dirname "$0")/.."'
} > "$REVERT"

for pair in "${MAP[@]}"; do
  old="${pair%%:*}"; new="${pair##*:}"
  if [[ ! -d "$E/$old" ]]; then
    echo "  SKIP   $old (no such dir)"
    continue
  fi
  if [[ -e "$E/$new" ]]; then
    echo "  ABORT  $new already exists" >&2; exit 1
  fi
  mv "$E/$old" "$E/$new"
  echo "mv \"$E/$new\" \"$E/$old\"" >> "$REVERT"
  echo "  MOVED  $old -> $new"
done

# The gallery floodmap tifs are named after the arm too.
for pair in "${MAP[@]}"; do
  old="${pair%%:*}"; new="${pair##*:}"
  src="$E/floodmaps/${old}_hmax_lev3.tif"
  if [[ -f "$src" ]]; then
    mv "$src" "$E/floodmaps/${new}_hmax_lev3.tif"
    echo "mv \"$E/floodmaps/${new}_hmax_lev3.tif\" \"$src\"" >> "$REVERT"
    echo "  MOVED  floodmaps/${old}_hmax_lev3.tif -> ${new}_hmax_lev3.tif"
  fi
done

chmod +x "$REVERT"
echo
echo "done. inverse written to $REVERT"
