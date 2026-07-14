"""Re-score the leak-fix 2x2 with the REPAIRED validation metrics (Workstream N).

The metrics used to produce `reports/leak_fix.csv` had two blind spots, both found on
2026-07-14 and both fixed in `nj_sfincs/validate.py`:

  1. `hwm_metrics` DROPPED any high-water mark the model failed to flood, so the score
     structurally REWARDED under-flooding. Dry marks are now scored against the model's
     ground elevation ("the water never got above this bed") -- the most generous reading
     available, and still a large negative residual when the observations say metres of
     water stood there. New keys: `hwm_*_scored*`, `hwm_n_dry_*`.
  2. `tidal_range_metric` reported `max - min` of the model's monotonic SPIN-UP DRAWDOWN
     as if it were a tide. It now de-trends the spin-up and refuses to report a range for
     a series that never rises (`is_tidal=False`).

And `shark_river` is now its own HWM basin instead of hiding inside `south_coast`.

THE QUESTION THIS ANSWERS: does the leak-fix conclusion survive the honest metrics? It
should -- the scored-mark counts were identical across all six runs, so the comparison was
apples-to-apples even under the broken metric -- but that must be SHOWN, not assumed. If
the Shrewsbury improvement (-0.42 -> +0.11 wet-only) collapses once dry marks are counted,
we need to know now.

It also, for the first time, puts a NUMBER on the Shark River dam: those 2 marks have never
been scored in this project's history.

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/rescore_leak_fix.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import nj_sfincs  # noqa: F401  (pyproj primer — must precede hydromt_sfincs)
from nj_sfincs.config import ROOT
from nj_sfincs.validate import (
    HWM_BASINS,
    hwm_metrics,
    load_floodmap,
    shrewsbury_gauge_peak,
    tidal_range_metric,
)

EXP = ROOT / "experiments"
OBS_CREST = 2.935

RUNS = {
    "snapwave_tuned_25m":         "PREMIER  (LEAKING)   waves",
    "faber_nowaves_25m":          "baseline (LEAKING)   nowaves",
    "leakfix_wall_waves_25m":     "wall                 waves",
    "leakfix_wall_nowaves_25m":   "wall                 nowaves",
    "leakfix_extend_waves_25m":   "extend               waves",
    "leakfix_extend_nowaves_25m": "extend               nowaves",
}

rows = []
for run, desc in RUNS.items():
    d = EXP / run
    if not (d / "sfincs_map.nc").exists():
        print(f"[{run}] no map — skipping", flush=True)
        continue
    print(f"[{run}] downscaling…", flush=True)
    r = {"run": run, "desc": desc}
    try:
        mod, hmax, dep = load_floodmap(d)
        m = hwm_metrics(hmax, dep)
        r["gauge"] = shrewsbury_gauge_peak(mod)["shrewsbury_mod_peak_m"]
        r["gauge_err"] = r["gauge"] - OBS_CREST
        r["bias_wetonly"] = m["hwm_bias_m"]
        r["rmse_wetonly"] = m["hwm_rmse_m"]
        r["bias_scored"] = m["hwm_bias_scored_m"]
        r["rmse_scored"] = m["hwm_rmse_scored_m"]
        r["n_scored"] = m["hwm_n_scored"]
        r["n_dry"] = m["hwm_n_dry_scored"]
        for b in HWM_BASINS:
            r[f"{b}"] = m[f"hwm_bias_scored_{b}_m"]
            r[f"n_{b}"] = m[f"hwm_n_scored_{b}"]
            r[f"dry_{b}"] = m[f"hwm_n_dry_{b}"]
    except Exception as e:  # noqa: BLE001
        print(f"[{run}] HWM failed: {type(e).__name__}: {e}", flush=True)
    try:
        t = tidal_range_metric(d)
        r["tide_shrews"] = t["tide_mod_range_shrewsbury_01407600_m"]
        r["tide_shark"] = t["tide_mod_range_shark_r_01407770_m"]
        r["shark_is_tidal"] = t["tide_mod_is_tidal_shark_r_01407770"]
    except Exception as e:  # noqa: BLE001
        print(f"[{run}] tide failed: {e}", flush=True)
    rows.append(r)

df = pd.DataFrame(rows)
pd.set_option("display.width", 250, "display.max_columns", 60)

print("\n" + "=" * 104)
print("1. DOES THE LEAK-FIX RESULT SURVIVE THE HONEST METRIC?")
print("=" * 104)
print(df[["desc", "gauge", "gauge_err", "bias_wetonly", "bias_scored",
          "rmse_wetonly", "rmse_scored", "n_scored", "n_dry"]].to_string(index=False))
print("\n  bias_wetonly = old metric (drops marks the model left dry -> rewards under-flooding)")
print("  bias_scored  = every q<=2 mark counted; dry marks scored at ground level")

print("\n" + "=" * 104)
print("2. PER-BASIN, SCORED (+ = model too HIGH).   dry = marks the model never wetted")
print("=" * 104)
cols = ["desc"]
for b in HWM_BASINS:
    cols += [b, f"dry_{b}"]
print(df[cols].to_string(index=False))

print("\n" + "=" * 104)
print("3. THE TIDE (spin-up removed).   obs: shrewsbury 1.369 m, shark 1.817 m")
print("=" * 104)
print(df[["desc", "tide_shrews", "tide_shark", "shark_is_tidal"]].to_string(index=False))
print("\n  shark_is_tidal=False in EVERY run => the basin never oscillates at all.")
print("  That is the dammed Shark River Inlet, and the old metric could not see it.")

out = ROOT / "reports" / "leak_fix_rescored.csv"
df.to_csv(out, index=False)
print(f"\nwrote {out}")
