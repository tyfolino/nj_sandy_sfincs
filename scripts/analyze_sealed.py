"""Workstream O — did the sealed, un-paved domain fix it, and which engine is the premier?

Reads the 2x2 staged by scripts/setup_sealed_premier.py and answers three questions IN ORDER.
Questions 2 and 3 only mean something if question 1 says yes.

  1. IS THE DOMAIN ACTUALLY FIXED?  Two independent checks that need NO storm peak and NO
     high-water marks:
       shark tide   The cleanest test in the project. Shark River Inlet was dammed shut in the
                    DEM (sill +0.57 m, ABOVE mean sea level), so the estuary NEVER FLOODED in
                    any run of this campaign -- peak zs exactly +0.00 m, its initial condition,
                    while the ocean 1.8 km away reached +2.9 m. It never oscillated at all
                    (frac_rising = 0.00). Observed at USGS 01407770: a 1.52 m per-cycle tidal
                    range, rising 47% of the time. **If Shark still has no tide, the carve
                    failed and nothing below is worth reading.**
       no leak      The Navesink cut ran -0.82 m/s OUT of the domain in 100% of timesteps and
                    92.5% of the estuary's inflow vanished. On the sealed domain the mass
                    balance must close.

  2. DOES SHREWSBURY HOLD?  The leak fix (a post-hoc mask edit) took the HWM bias -0.42 ->
     +0.21 and the gauge 2.223 -> 2.691 (obs 2.935). The region fix reaches the same place by
     fixing the CAUSE instead of the symptom, so it should reproduce it. If it does not, the
     two fixes are not doing the same thing and we need to know why.

  3. WHICH ENGINE?  Faber vs Galibier, on a domain that is not broken, with Galibier's missing
     stability clamp (snapwave_gammax) put back so we compare physics and not a bug.

AND THE TEST THE WHOLE THING MUST PASS: **the basins that never broke must not move.**
South-coast bias was -0.0553 and stayed -0.0553 through the leak fix. A domain fix is LOCAL.
If the open coast shifts, we changed something we did not mean to.

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/analyze_sealed.py
Add --with-refs to include the broken-domain reference runs (slower; see BROKEN_REFS).

⚠️ THE NUMBERS MOVE IF YOU RE-RUN AN OLD CSV'S ANALYSIS. tidal_range_metric's window gained a
12 h spin-up skip (validate.SPINUP_SKIP_H) on 2026-07-20, AFTER the 07-15 CSV was written. The
skip is the correct behaviour — without it the window reads spin-up drainage as tide — but it
shifts every tidal number: Shark frac_rising 0.542 -> 0.458 (obs 0.47, so it improved), Shark
range 1.30 -> 1.36, Shrewsbury 0.99 -> 1.03. Do not read that shift as a model change.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import nj_sfincs  # noqa: F401
from nj_sfincs.config import ROOT
from nj_sfincs.validate import (
    HWM_BASINS,
    hwm_metrics,
    load_floodmap,
    shrewsbury_gauge_peak,
    tidal_range_metric,
)

EXP = ROOT / "experiments"
OBS_CREST = 2.935          # Shrewsbury, surveyed post-event crest (no hydrograph exists)
OBS_TIDE_SHARK = 1.52      # USGS 01407770, mean per-M2-cycle range, pre-storm
OBS_TIDE_SHREWS = 1.23     # USGS 01407600, same
OBS_FRAC_RISING = 0.47     # a real tide rises about half the time; a dammed basin, never

RUNS = {
    "sealed_faber_nowaves":    "FABER     sealed   nowaves",
    "sealed_faber_waves":      "FABER     sealed   waves",
    "sealed_galibier_nowaves": "GALIBIER  sealed   nowaves",
    "sealed_galibier_waves":   "GALIBIER  sealed   waves",
}

# References on the OLD (leaking + dammed) domain. OPT-IN via --with-refs: the premier is
# settled, so the routine question is now "how do the four sealed candidates compare", and
# these three carry no cached floodmap (~80 s of downscale each) for an argument that is
# already won and written up in reports/shrewsbury_investigation.md.
BROKEN_REFS = {
    "leakfix_extend_waves_25m":   "[ref] leakfix mask-edit   waves",
    "leakfix_extend_nowaves_25m": "[ref] leakfix mask-edit   nowaves",
    "snapwave_tuned_25m":         "[ref] PREMIER (BROKEN)    waves",
}
if "--with-refs" in sys.argv:
    RUNS = {**RUNS, **BROKEN_REFS}

rows = []
for run, desc in RUNS.items():
    d = EXP / run
    if not (d / "sfincs_map.nc").exists():
        print(f"[{run}] no map yet — skipping", flush=True)
        continue
    r = {"run": run, "desc": desc}
    try:
        t = tidal_range_metric(d)
        r["shark_tide"] = t["tide_mod_range_shark_r_01407770_m"]
        r["shark_frac_rising"] = t["tide_mod_frac_rising_shark_r_01407770"]
        r["shark_is_tidal"] = t["tide_mod_is_tidal_shark_r_01407770"]
        r["shrews_tide"] = t["tide_mod_range_shrewsbury_01407600_m"]
    except Exception as e:  # noqa: BLE001
        print(f"[{run}] tide failed: {e}", flush=True)
    try:
        print(f"[{run}] downscaling…", flush=True)
        mod, hmax, dep = load_floodmap(d)
        m = hwm_metrics(hmax, dep)
        r["gauge"] = shrewsbury_gauge_peak(mod)["shrewsbury_mod_peak_m"]
        r["gauge_err"] = r["gauge"] - OBS_CREST
        r["bias"] = m["hwm_bias_scored_m"]
        r["rmse"] = m["hwm_rmse_scored_m"]
        r["n_dry"] = m["hwm_n_dry_scored"]
        for b in HWM_BASINS:
            r[b] = m[f"hwm_bias_scored_{b}_m"]
    except Exception as e:  # noqa: BLE001
        print(f"[{run}] HWM failed: {type(e).__name__}: {e}", flush=True)
    rows.append(r)

df = pd.DataFrame(rows)
pd.set_option("display.width", 250, "display.max_columns", 60)

print("\n" + "=" * 104)
print("1. IS THE DOMAIN FIXED?  ** DOES SHARK RIVER HAVE A TIDE AT LAST? **")
print("=" * 104)
print(df[[c for c in ["desc", "shark_tide", "shark_frac_rising", "shark_is_tidal", "shrews_tide"]
          if c in df]].to_string(index=False))
print(f"\n  observed: shark {OBS_TIDE_SHARK} m rising {OBS_FRAC_RISING} of the time; "
      f"shrewsbury {OBS_TIDE_SHREWS} m")
print("  the OLD domain gave shark frac_rising = 0.00 — the basin never oscillated AT ALL,")
print("  because its inlet was a +0.57 m dam. is_tidal=False there is the bug, not a metric quirk.")

print("\n" + "=" * 104)
print("2. DOES SHREWSBURY HOLD?   (obs crest 2.935 m; broken premier was 2.223 / -0.42)")
print("=" * 104)
print(df[[c for c in ["desc", "gauge", "gauge_err", "shrewsbury_navesink", "bias", "rmse", "n_dry"]
          if c in df]].to_string(index=False))

print("\n" + "=" * 104)
print("3. THE LOCALITY TEST — the basins that never broke MUST NOT MOVE")
print("=" * 104)
print(df[[c for c in ["desc"] + list(HWM_BASINS) if c in df]].to_string(index=False))
print("\n  south_coast was -0.0553 on the broken domain and -0.0553 after the leak fix.")
print("  If it moves now, the rebuild changed something we did not intend — do not trust the rest.")

out = ROOT / "reports" / "sealed_premier.csv"
out.parent.mkdir(exist_ok=True)
df.to_csv(out, index=False)
print(f"\nwrote {out}")
