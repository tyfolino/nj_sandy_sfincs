"""Workstream K — did plugging the leak fill the estuary?

Reads the 2x2 staged by ``scripts/setup_leak_fix.py`` (wall|extend x waves|nowaves) against
the leaking premier, and answers two questions IN ORDER. The second only means something if
the first says yes.

1. IS THE LEAK ACTUALLY GONE?  Three independent checks, at the ORIGINAL cut location (in the
   fixed runs those cells are ordinary active water now, so we address them geometrically):

     reversal   the Navesink cut ran -0.82 m/s mean and flowed OUT in 100% of timesteps. A
                real tidal cross-section reverses every ~6 h. If it still never reverses, the
                mask edit did not take and nothing below is worth reading.
     drawdown   from a flat start the leaking model pulled the Navesink to -1.48 m by 04:00 on
                Oct 28 -- two days BEFORE Sandy peaks, on a calm night. Nothing physical does
                that. It must stop.
     closure    the estuary took 3.72e8 m3 in through the Highlands throat and stored 2.8e7 --
                92.5% vanished. The balance must now CLOSE (inflow ~ storage + tidal exchange).

2. DID IT FILL?  gauge crest, HWM bias, tidal range -- vs the predictions written down before
   the runs (see setup_leak_fix.py). An honest possibility is that it only PARTLY fills: once
   the estuary holds water its head rises, the throat inflow throttles back, and the system
   re-equilibrates. `wall` should undershoot `extend` (it discards 2.5 km2 of real prism).

And it re-answers WORKSTREAM J on a sealed model: the leak was sucking water through the
throat, so the barrier-vs-throat partition measured on the leaking run (throat 41x barrier)
was contaminated. Same two control lines, no drain => the honest partition.

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/analyze_leak_fix.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

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
PREMIER = "snapwave_tuned_25m"
# NB the LEAKING reference for the flux/velocity checks is `faber_flux_25m`, not
# `snapwave_tuned_25m`: they are the same physics (the former is staged from the latter and
# only adds crsfile/storevel), but only faber_flux_25m actually carries the diagnostics.
RUNS = {
    "faber_flux_25m":            "PREMIER  (LEAKING)   waves",
    "faber_nowaves_25m":         "baseline (LEAKING)   nowaves",
    "leakfix_wall_waves_25m":    "wall                 waves",
    "leakfix_wall_nowaves_25m":  "wall                 nowaves",
    "leakfix_extend_waves_25m":  "extend               waves",
    "leakfix_extend_nowaves_25m":"extend               nowaves",
}
OBS_CREST = 2.935          # USGS 01407600 Shrewsbury, m NAVD88 (surveyed post-event crest)
OBS_TIDAL_RANGE = 1.54     # interior; model was 0.91 on the leaking premier
CALM = "2012-10-28 04:00"  # two days pre-peak: the leaking model was already at -1.48 m here

# geometry, taken from the PREMIER's mask so every run is probed at the SAME cells
ref = xr.open_dataset(EXP / PREMIER / "sfincs.nc")
FX, FY = ref["mesh2d_face_x"].values, ref["mesh2d_face_y"].values
ZB, M0, LEV = ref["z"].values, ref["mask"].values, ref["level"].values
AREA = (200.0 / 2 ** (LEV - 1)) ** 2

CUT = (M0 == 3) & (ZB < 0) & (FY > 4468000) & (FY < 4471000) & (FX < 582500)  # the drain
# deep Navesink JUST INSIDE the cut — active in every run, so the calm-night drawdown is
# comparable across them (the cut cells themselves are NaN in the leaking runs' map output).
DRAW = (M0 > 0) & (ZB < -1) & (FY > 4468700) & (FY < 4470400) & (FX > 580700) & (FX < 582500)
BAY = (M0 > 0) & (ZB < -1) & (FY > 4472500) & (FY < 4474500) & (FX > 585500) & (FX < 588500)
NEAR = (M0 > 0) & (ZB < -1) & (FY > 4470000) & (FY < 4471800) & (FX > 583500) & (FX < 586800)


def _estuary_cells():
    """West of the Sea Bright barrier polyline, south of the Highlands throat."""
    crs = (EXP / PREMIER / "sfincs.crs")
    if not crs.exists():
        crs = ROOT / "data" / "flux_crosssections.crs"
    L = crs.read_text().split("\n")
    i = L.index("barrier"); n = int(L[i + 1].split()[0])
    bx = np.array([float(L[i + 2 + k].split()[0]) for k in range(n)])
    by = np.array([float(L[i + 2 + k].split()[1]) for k in range(n)])
    xedge = np.interp(FY, by, bx, left=bx[0], right=bx[-1])
    return (M0 > 0) & (FY > 4462400) & (FY < 4472000) & (FX < xedge) & (FX > 578000)


EST = _estuary_cells()


def leak_checks(run: str) -> dict:
    d = EXP / run
    m = xr.open_dataset(d / "sfincs_map.nc")
    t = pd.to_datetime(m.time.values)
    zs = m["zs"].values

    # older runs predate storevel=1, so they carry no velocity — report NaN rather than die.
    if "u" in m:
        uu = np.nan_to_num(m["u"].values[:, CUT])
        cut_u, frac_out = float(uu.mean()), float((uu.mean(axis=1) < 0).mean())
    else:
        cut_u = frac_out = float("nan")
    k = int(np.argmin(np.abs(t - pd.Timestamp(CALM))))
    # in the LEAKING runs the cut cells are boundary cells and their zs is NaN in the map, so
    # read the drawdown just INSIDE the cut, where every run has ordinary active water.
    nav_calm = float(np.nanmean(zs[k, DRAW]))

    h = np.clip(np.nan_to_num(zs[:, EST] - ZB[EST][None, :]), 0, None)
    V = (h * AREA[EST][None, :]).sum(axis=1)

    zb_bay = np.nanmean(zs[:, BAY], axis=1)
    zb_est = np.nanmean(zs[:, NEAR], axis=1)
    kp = int(np.nanargmax(zb_bay))

    r = dict(run=run, desc=RUNS[run],
             cut_mean_u=cut_u, cut_frac_out=frac_out,
             navesink_calm_zs=nav_calm,
             storage_rise=float(V.max() - V[0]),
             head_drop_mean=float(np.nanmean(zb_bay - zb_est)),
             head_drop_peak=float(zb_bay[kp] - zb_est[kp]))

    his = d / "sfincs_his.nc"
    if his.exists():
        H = xr.open_dataset(his)
        if "crosssection_discharge" in H:
            Q = H["crosssection_discharge"].values
            dt = float((pd.to_datetime(H.time.values)[1] - pd.to_datetime(H.time.values)[0]).total_seconds())
            r["barrier_in"] = float(Q[:, 0].sum() * dt)
            r["throat_in"] = float(-Q[:, 1].sum() * dt)      # sign: + = INTO the estuary
            r["missing"] = r["throat_in"] + r["barrier_in"] - r["storage_rise"]
            r["missing_pct"] = 100.0 * r["missing"] / max(r["throat_in"] + r["barrier_in"], 1.0)
    return r


rows = []
for run in RUNS:
    if not (EXP / run / "sfincs_map.nc").exists():
        print(f"[{run}] no map yet — skipping", flush=True)
        continue
    try:
        r = leak_checks(run)
    except Exception as e:   # noqa: BLE001
        # a map still being written has fill-valued `timemax`, which xarray refuses to decode
        print(f"[{run}] map not readable yet (still running?) — skipping: {type(e).__name__}", flush=True)
        continue
    try:
        tr = tidal_range_metric(EXP / run)
        r["tidal_range"] = tr["tide_mod_range_shrewsbury_01407600_m"]
        r["tidal_range_obs"] = tr["tide_obs_range_shrewsbury_01407600_m"]
        r["tidal_range_shark"] = tr["tide_mod_range_shark_r_01407770_m"]
    except Exception as e:                                   # noqa: BLE001
        print(f"[{run}] tidal range failed: {e}", flush=True)
    rows.append(r)
    print(f"[{run}] leak checks done", flush=True)

df = pd.DataFrame(rows)
pd.set_option("display.width", 250, "display.max_columns", 60)

print("\n" + "=" * 100)
print("1. IS THE LEAK GONE?   (premier: -0.82 m/s, out 100% of the time, Navesink -1.48 m on a calm night)")
print("=" * 100)
print(df[["desc", "cut_mean_u", "cut_frac_out", "navesink_calm_zs"]].to_string(index=False))
print("\n  cut_frac_out = fraction of timesteps the cut flowed OUT of the domain.")
print("  1.00 = still a drain.  ~0.5 = a normal tidal cross-section that reverses.")

if "missing_pct" in df:
    print("\n" + "=" * 100)
    print("2. DOES THE MASS BALANCE CLOSE?   (premier: 92.5% of inflow vanished)")
    print("=" * 100)
    print(df[["desc", "throat_in", "barrier_in", "storage_rise", "missing", "missing_pct"]].to_string(index=False))
    print("\n  WORKSTREAM J, re-measured without the drain: throat vs barrier =")
    for _, r in df.iterrows():
        if not np.isnan(r.get("barrier_in", np.nan)) and r["barrier_in"] != 0:
            print("    %-34s throat %+.2e   barrier %+.2e   ratio %5.1fx" % (
                r["desc"], r["throat_in"], r["barrier_in"], r["throat_in"] / r["barrier_in"]))

print("\n" + "=" * 100)
print("3. DID IT FILL?   (head drop bay->estuary was +1.02 m mean / +2.12 m at peak)")
print("=" * 100)
print(df[["desc", "head_drop_mean", "head_drop_peak", "storage_rise", "tidal_range"]].to_string(index=False))
print(f"\n  observed interior tidal range: {OBS_TIDAL_RANGE} m   (leaking premier: 0.91)")

# --- the slow part: downscale each map and score HWMs + the gauge -------------------------
print("\n" + "=" * 100)
print("4. HWM / GAUGE  (downscaling ~660 MB maps, 2-4 min per run — be patient)")
print("=" * 100, flush=True)
hrows = []
done = set(df["run"]) if not df.empty else set()
for run, desc in RUNS.items():
    d = EXP / run
    if run not in done:          # skip anything still being written (see leak_checks guard)
        continue
    try:
        print(f"[{run}] downscaling…", flush=True)
        mod, hmax, dep = load_floodmap(d)
        mt = hwm_metrics(hmax, dep)
        h = {"run": run, "desc": desc,
             "hwm_bias_pooled": mt["hwm_bias_m"], "hwm_rmse_pooled": mt["hwm_rmse_m"]}
        for b in HWM_BASINS:
            h[f"bias_{b}"] = mt[f"hwm_bias_{b}_m"]
            h[f"n_{b}"] = mt[f"hwm_n_{b}"]
        try:
            g = shrewsbury_gauge_peak(mod)
            h["gauge_peak"] = g["shrewsbury_mod_peak_m"]
            h["gauge_err"] = g["shrewsbury_mod_peak_m"] - OBS_CREST
        except Exception as e:                               # noqa: BLE001
            print(f"[{run}] gauge peak failed: {e}", flush=True)
        hrows.append(h)
    except Exception as e:                                   # noqa: BLE001
        print(f"[{run}] FAILED: {type(e).__name__}: {e}", flush=True)

hd = pd.DataFrame(hrows)
if not hd.empty:
    print("\n=== HWM bias by basin (+ = model too HIGH) — obs Shrewsbury crest 2.935 m ===")
    print(hd[[c for c in ["desc", "gauge_peak", "gauge_err", "bias_shrewsbury_navesink",
                          "bias_sandy_hook_bay", "bias_atlantic_oceanfront", "bias_south_coast",
                          "hwm_bias_pooled", "hwm_rmse_pooled"] if c in hd]].to_string(index=False))
    print("\n  THE TEST: shrewsbury bias -0.42 -> 0, gauge 2.223 -> 2.935,")
    print("  WITHOUT moving sandy_hook_bay (+0.04) or the open coast — the leak was estuary-local,")
    print("  so a leak fix MUST NOT shift the basins that never leaked. If they move, think again.")

out = ROOT / "reports" / "leak_fix.csv"
out.parent.mkdir(exist_ok=True)
df.merge(hd, on=["run", "desc"], how="outer").to_csv(out, index=False)
print(f"\nwrote {out}")
