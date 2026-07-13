"""Per-basin HWM residuals across the engine / clamp runs (Workstream A2).

The premier question in one table: Faber under-fills the behind-barrier estuary; does
Galibier-with-the-clamp fix it, and what does it cost elsewhere on the coast?

Uses the OFFICIAL raster path (load_floodmap -> hwm_metrics), which needs
``validate.read_output`` to open the Galibier v2.4.0 maps at all (they omit the loose
``crs`` variable hydromt expects — see that docstring). Slow: each run downscales a
~660 MB map onto the L3 subgrid DEM and writes a GeoTIFF, ~2-4 min per run. Run it in
the background and read the CSV.

Writes reports/hwm_basins.csv.

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python \
          scripts/analyze_hwm_basins.py
"""

from __future__ import annotations

import pandas as pd

import nj_sfincs  # noqa: F401  (pyproj primer — must precede hydromt_sfincs)
from nj_sfincs.config import ROOT
from nj_sfincs.validate import (
    HWM_BASINS,
    hwm_metrics,
    load_floodmap,
    shrewsbury_gauge_peak,
)

RUNS = {
    "snapwave_tuned_25m":    "Faber premier      (clamp on,  bexp0)",
    "faber_gammax999_25m":   "Faber, clamp OFF   (blown-up waves)",
    "galibier_niter400_25m": "Galibier niter400  (clamp OFF, bexp2)",
    "galibier_gammax2_25m":  "Galibier + CLAMP   (clamp on,  bexp2)  <- candidate",
    # added as they land:
    "galibier_gammax2_niter100_25m": "Galibier + CLAMP, niter100 (convergence arm)",
    "galibier_gammax2_bexp0_25m":    "Galibier + CLAMP, bexp0    (Baldock arm)",
    "faber_nowaves_25m":     "Faber,    waves OFF (baseline)",
    "galibier_nowaves_25m":  "Galibier, waves OFF (baseline)",
}
OBS_CREST = 2.935  # USGS 01407600 Shrewsbury, m NAVD88

rows = []
for run, desc in RUNS.items():
    d = ROOT / "experiments" / run
    if not (d / "sfincs_map.nc").exists():
        print(f"[{run}] no map yet — skipping", flush=True)
        continue
    try:
        print(f"[{run}] downscaling…", flush=True)
        mod, hmax, dep = load_floodmap(d)
        m = hwm_metrics(hmax, dep)
        r = {"run": run, "desc": desc,
             "hwm_bias_pooled": m["hwm_bias_m"], "hwm_rmse_pooled": m["hwm_rmse_m"]}
        for b in HWM_BASINS:
            r[f"bias_{b}"] = m[f"hwm_bias_{b}_m"]
            r[f"rmse_{b}"] = m[f"hwm_rmse_{b}_m"]
            r[f"n_{b}"] = m[f"hwm_n_{b}"]
        try:
            g = shrewsbury_gauge_peak(mod)
            r["shrewsbury_gauge_peak"] = g["shrewsbury_mod_peak_m"]
            r["shrewsbury_gauge_err"] = g["shrewsbury_mod_peak_m"] - OBS_CREST
        except Exception as e:      # noqa: BLE001
            print(f"[{run}] gauge peak failed: {e}", flush=True)
        rows.append(r)
        print(f"[{run}] done", flush=True)
    except Exception as e:          # noqa: BLE001
        print(f"[{run}] FAILED: {type(e).__name__}: {e}", flush=True)

df = pd.DataFrame(rows)
out = ROOT / "reports" / "hwm_basins.csv"
out.parent.mkdir(exist_ok=True)
df.to_csv(out, index=False)

pd.set_option("display.width", 200, "display.max_columns", 50)
print("\n=== HWM bias by basin (+ = model too HIGH) — obs crest 2.935 m ===")
cols = ["run", "hwm_bias_pooled", "bias_shrewsbury_navesink", "rmse_shrewsbury_navesink",
        "bias_atlantic_oceanfront", "bias_south_coast", "shrewsbury_gauge_peak"]
print(df[[c for c in cols if c in df]].to_string(index=False))
print(f"\nwrote {out}")
