#!/usr/bin/env bash
# Auto-generated inverse of rename_experiment_dirs.sh. Run to undo.
set -euo pipefail
cd "$(dirname "$0")/.."
mv "experiments/faber-waves-premier" "experiments/sealed_faber_waves"
mv "experiments/faber-nowaves" "experiments/sealed_faber_nowaves"
mv "experiments/galibier-waves" "experiments/sealed_galibier_waves"
mv "experiments/galibier-nowaves" "experiments/sealed_galibier_nowaves"
mv "experiments/wave-ig" "experiments/sealed_igwaves_wind"
mv "experiments/mask-zmin15" "experiments/sealed_bdepth_m15"
mv "experiments/mask-zmin20" "experiments/sealed_bdepth_m20"
mv "experiments/wave-deep30" "experiments/snapwave_deep"
mv "experiments/tide-shift" "experiments/phaselag_shift"
mv "experiments/wave-deep30+tide-shift" "experiments/snapwave_deep_phaseshift"
mv "experiments/floodmaps/faber-waves-premier_hmax_lev3.tif" "experiments/floodmaps/sealed_faber_waves_hmax_lev3.tif"
mv "experiments/floodmaps/wave-deep30_hmax_lev3.tif" "experiments/floodmaps/snapwave_deep_hmax_lev3.tif"
mv "experiments/floodmaps/tide-shift_hmax_lev3.tif" "experiments/floodmaps/phaselag_shift_hmax_lev3.tif"
mv "experiments/floodmaps/wave-deep30+tide-shift_hmax_lev3.tif" "experiments/floodmaps/snapwave_deep_phaseshift_hmax_lev3.tif"
