"""Validation metrics for a finished SFINCS run — the numeric core of the
notebook's Phase-4 cells, returned as a flat dict for the experiment CSV.

Lifted (behaviour-preserving) from notebooks/sfincs-nj-sandy.ipynb:
* ``load_floodmap`` — cells 61 + 68 (open output, downscale zsmax to the L3 DEM).
* ``gauge_peak_error`` — cell 66 (Sandy Hook NOAA 8531680, peak WSE error).
* ``hwm_metrics`` — cell 74 (USGS HWM residual RMSE/bias/within-0.5 m).
* ``motf_metrics`` — cell 78 (FEMA MOTF CSI / POD / FAR).
* ``sandy_hook_bay_hm0`` — NEW: mean/max SnapWave Hm0 in the bay lee, the
  "did waves reach Sandy Hook Bay?" diagnostic (map output, needs storewavdir=1).

Every metric is wrapped so a partial failure yields NaNs rather than aborting
the whole row — the runner still gets a usable CSV line.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rioxarray  # noqa: F401  (registers .rio)
import xarray as xr
import xugrid as xu
from pyproj import CRS, Transformer
from shapely.geometry import box

from hydromt_sfincs import SfincsModel, utils

from .config import ROOT

DATA = ROOT / "data"

# Sandy Hook Bay lee (lon/lat box) — the sheltered water behind the Hook spit
# where Atlantic swell cannot diffract in; this is the target for wind/IG waves.
SANDY_HOOK_BAY_BOX_LL = (-74.075, 40.420, -73.980, 40.480)

DEPTH_MIN = 0.15  # m; a cell counts as "wet" above this (HWM + MOTF)

# ── HWM hydraulic-basin partition (Workstream A2) ─────────────────────────────
# Split the 31 Sandy HWMs by hydraulic basin so the pooled RMSE stops blending
# the ocean-front marks (surge delivered directly, model gets them right) with
# the behind-the-barrier Shrewsbury/Navesink marks (the conveyance test). All in
# UTM 18N (EPSG:32618); coordinate thresholds, not a fragile hand-drawn polygon.
# The Sea Bright/Monmouth barrier & open coast run NNE, so the ocean<->estuary
# divide is a SLOPED easting, not a fixed one.
HWM_SOUTH_Y = 4_458_000   # below this = south coast (Belmar/Avon ocean front + Shark R.)
HWM_BAY_Y = 4_474_000     # above this = open Sandy Hook / Raritan Bay
HWM_BARRIER_X0 = 586_000  # barrier easting at y = HWM_BARRIER_Y0 ...
HWM_BARRIER_Y0 = 4_456_000
HWM_BARRIER_SLOPE = 0.075  # ... rising 0.075 m east per m north (barrier axis)

# Shark River estuary — split OUT of south_coast (2026-07-14). These marks are fed
# through Shark River Inlet, so their flooding is a CONVEYANCE test, exactly like
# shrewsbury_navesink; the rest of south_coast is open Belmar/Avon ocean front where
# surge is delivered directly. Pooling them hid the dammed inlet: the estuary marks
# were dry (and silently dropped, see hwm_metrics), so the basin reported a
# near-perfect -0.055 m bias while the river behind it never wetted at all.
SHARK_N_Y = 4_450_800   # north edge of the Shark estuary (ocean-front marks lie above)
SHARK_E_X = 584_300     # west of the inlet gorge (the sill sits at x~583,900)

HWM_BASINS = (
    "atlantic_oceanfront",
    "shrewsbury_navesink",
    "sandy_hook_bay",
    "south_coast",
    "shark_river",
)


def classify_hwm_basin(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Label each HWM (UTM 18N easting/northing) by hydraulic basin.

    ``shrewsbury_navesink`` and ``shark_river`` are the behind-barrier estuaries =
    the conveyance test groups; ``atlantic_oceanfront`` and ``south_coast`` are the
    wave/surge-exposed open coast, where surge is delivered directly.
    """
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    barrier = HWM_BARRIER_X0 + HWM_BARRIER_SLOPE * (y - HWM_BARRIER_Y0)
    basin = np.full(len(x), "shrewsbury_navesink", dtype=object)
    basin[y < HWM_SOUTH_Y] = "south_coast"
    basin[(y < HWM_SOUTH_Y) & (y < SHARK_N_Y) & (x < SHARK_E_X)] = "shark_river"
    north = y >= HWM_SOUTH_Y
    basin[north & (y > HWM_BAY_Y)] = "sandy_hook_bay"
    basin[north & (y <= HWM_BAY_Y) & (x > barrier)] = "atlantic_oceanfront"
    return basin


def _prestorm_window(map_times: np.ndarray, hours: float = 24.0):
    """Clean tidal window = first ``hours`` of the run (before the surge ramp)."""
    t0 = map_times.min()
    return t0, t0 + np.timedelta64(int(hours * 3600), "s")


# A tide RISES about half the time. A drain never does. This is the discriminator:
# anything that spends less than this fraction of its samples going UP is not a tide.
# (A clean semidiurnal signal sampled hourly gives ~0.5; even a badly over-damped
# estuary gives >0.3. A monotonic spin-up drawdown gives ~0.0.)
TIDE_MIN_FRAC_RISING = 0.20
TIDE_NOISE_M = 0.005  # steps smaller than this are numerical wiggle, not motion


def _tidal_signal(series: np.ndarray) -> dict:
    """Decompose a water-level series into spin-up DRIFT and a true TIDAL range.

    WHY THIS EXISTS (2026-07-14). The naive metric -- ``max - min`` over the first
    24 h -- silently reported the model's monotonic SPIN-UP DRAWDOWN as if it were
    a tide. At the Shark River gauge the "tidal range" was 1.27 m, and the series
    behind that number was::

        +0.00 -0.63 -0.86 -0.99 -1.06 ... -1.27 -1.27 -1.27

    i.e. the model equilibrating from its flat initial condition, with ZERO tidal
    oscillation -- because Shark River Inlet was dammed shut in the DEM and the
    basin was hydraulically cut off from the ocean. ``max - min`` cannot tell a
    tide from a drain, so it produced a plausible-looking number for a basin that
    was not tidal at all, and the defect hid for months.

    Note the trap: that drawdown is an EXPONENTIAL decay, so simply de-trending it
    with a straight line leaves a big bowed residual (~1 m) that still looks like a
    range, and counting turning points is defeated by numerical wiggle. Neither is
    a safe test. The robust discriminator is the FRACTION OF TIME THE SERIES RISES:
    a tide floods and ebbs, a drain only ebbs.
    """
    s = np.asarray(series, float)
    s = s[np.isfinite(s)]
    if s.size < 4:
        return dict(range_m=float("nan"), drift_m=float("nan"),
                    frac_rising=float("nan"), is_tidal=False)
    d = np.diff(s)
    moving = np.abs(d) > TIDE_NOISE_M          # ignore numerical chatter
    frac_rising = float((d[moving] > 0).mean()) if moving.any() else 0.0
    is_tidal = bool(frac_rising >= TIDE_MIN_FRAC_RISING)

    # the tide itself: remove the spin-up drift, then measure what is left. Only
    # meaningful once is_tidal has established there IS a tide to measure.
    t = np.arange(s.size, dtype=float)
    detr = s - np.polyval(np.polyfit(t, s, 1), t)
    return dict(
        range_m=float(detr.max() - detr.min()),
        drift_m=float(s[-1] - s[0]),           # the spin-up (net drainage)
        frac_rising=frac_rising,
        is_tidal=is_tidal,
    )


def _wet_channel_cells(model_dir: Path, lon: float, lat: float,
                       radius: float = 150.0, bed_max: float = -1.0):
    """Model face indices of wet channel cells within ``radius`` m of a gauge.

    B (2026-07-08) showed the SFINCS observation points snap to DRY high-ground
    cells (point_zb up to +2 m), so his-based interior gauge series are dry-cell
    artifacts. Sample the map at genuine channel cells (bed < ``bed_max``) near
    the gauge's TRUE coordinate instead. Returns ``(idx, dist, bed)`` or None.
    """
    grid = xr.open_dataset(Path(model_dir) / "sfincs.nc")
    fx = grid["mesh2d_face_x"].values
    fy = grid["mesh2d_face_y"].values
    z = grid["z"].values
    mask = grid["mask"].values
    gx, gy = Transformer.from_crs(4326, 32618, always_xy=True).transform(lon, lat)
    r = np.hypot(fx - gx, fy - gy)
    sel = (r < radius) & (mask > 0) & (z < bed_max)
    idx = np.where(sel)[0]
    if idx.size == 0:
        return None
    return idx, r[idx], z[idx]


def read_output(mod) -> None:
    """Load sfincs_map.nc + sfincs_his.nc, tolerating BOTH SFINCS output conventions.

    ``hydromt_sfincs``' own ``output.read()`` does ``crs = ds["crs"].values`` on the map,
    which breaks on SFINCS v2.4.0 (Galibier) with ``KeyError: 'crs'``.

    The irony is that Galibier's file is the *more* correct one. It declares a CF-compliant
    ``grid_mapping = "crs"`` on its coordinate variables, so xugrid does the right thing:
    it folds ``crs`` into the grid object (``ds.grid.crs`` is already EPSG:32618) and drops
    it from ``data_vars``. v2.3.3 (Faber) omits ``grid_mapping``, leaving ``crs`` lying
    around as a loose variable — which is the only reason the upstream code works there.

    So take the CRS from wherever the engine actually put it: the grid object first
    (Galibier), then a loose variable (Faber), then ``epsg`` in sfincs.inp as a backstop.
    Without this, every spatial metric (HWM, MOTF, floodmaps) silently excludes the
    Galibier runs.
    """
    root = Path(mod.root.path)
    mod.config.read()
    # ``output.set()`` lazily calls ``_initialize()``, which in read mode calls the very
    # ``read()`` we are replacing — so prime the store first or we trip the same KeyError.
    mod.output._initialize(skip_read=True)

    fn_map = root / "sfincs_map.nc"
    if fn_map.is_file():
        ds = xu.load_dataset(fn_map)
        ds = ds.set_coords(["mesh2d_node_x", "mesh2d_node_y"])
        crs = ds.grid.crs                                  # Galibier: xugrid parsed it
        if crs is None:
            if "crs" in ds.variables:                      # Faber: loose variable
                crs = CRS.from_user_input(int(ds["crs"].values))
            else:                                          # backstop: the run's own inp
                epsg = int(_inp_value(root / "sfincs.inp", "epsg"))
                crs = CRS.from_user_input(epsg)
            ds.grid.set_crs(crs)
        ds = ds.drop_vars("crs", errors="ignore")
        mod.output.set(ds, split_dataset=True)

    fn_his = root / "sfincs_his.nc"
    if fn_his.is_file():
        mod.output.set(mod.output.read_his_file(fn_his=str(fn_his)), split_dataset=True)


def _inp_value(inp: Path, key: str) -> str:
    for line in inp.read_text().splitlines():
        if "=" in line and line.split("=")[0].strip() == key:
            return line.split("=", 1)[1].strip()
    raise KeyError(f"{key!r} not found in {inp}")


def load_floodmap(model_dir: Path):
    """Open the run read-only and downscale zsmax onto the L3 subgrid DEM.

    Returns ``(mod, da_hmax, da_dep)`` — the model handle plus the north-up
    depth-max and subgrid-DEM rasters the spatial metrics sample.
    """
    model_dir = Path(model_dir).resolve()
    mod = SfincsModel(str(model_dir), data_libs=[str(DATA / "data_catalog.yml")], mode="r")
    read_output(mod)

    da_zsmax = mod.output.data["zsmax"].max(dim="timemax")
    depfile = str(model_dir / "subgrid" / "dep_subgrid_lev3.tif")
    floodmap_fn = str(model_dir / "floodmap_hmax_lev3.tif")
    utils.downscale_floodmap(
        zsmax=da_zsmax, dep=depfile, hmin=0.05, floodmap_fn=floodmap_fn, nrmax=1000
    )
    da_hmax = rioxarray.open_rasterio(floodmap_fn, masked=True).squeeze(drop=True)
    da_dep = rioxarray.open_rasterio(depfile, masked=True).squeeze(drop=True)
    da_hmax = da_hmax.rio.reproject(da_hmax.rio.crs)   # de-rotate to north-up
    da_dep = da_dep.rio.reproject_match(da_hmax)
    da_hmax = da_hmax.where(da_dep.values > -0.5)      # drop deep ocean
    da_hmax.name = "hmax"
    return mod, da_hmax, da_dep


def gauge_peak_error(mod, data_dir: Path = DATA) -> dict:
    """Sandy Hook (NOAA 8531680) modeled vs observed peak WSE, pre-failure."""
    point_zs = mod.output.data["point_zs"]
    point_zb = mod.output.data["point_zb"]
    names = [
        n.decode() if isinstance(n, bytes) else str(n)
        for n in point_zs["station_name"].values
    ]
    val = xr.open_dataset(str(data_dir / "gtsm" / "noaa_sandy_validation.nc"))
    obs_sh = val["waterlevel"].sel(stations=8531680)

    i_sh = next(k for k, n in enumerate(names) if "sandy_hook" in n)
    mod_sh = point_zs.isel(stations=i_sh)
    # The Sandy Hook gauge died 2012-10-29 23:00 on the RISING limb (last read
    # ~2.81 m), before Sandy's peak. Comparing model peak to obs over the whole
    # run understates the model (obs is truncated). Report BOTH: (a) the honest
    # pre-failure comparison at the gauge's last-good time, and (b) the model's
    # true full-window peak (which the dead gauge never saw). Do NOT read the
    # truncated full-run diff as a model error. See [[project_shrewsbury_reinvestigation]].
    gauge_end = pd.Timestamp("2012-10-29 23:00")

    obs_peak = float(obs_sh.max())                                  # truncated (pre-failure)
    mod_peak_prefail = float(mod_sh.sel(time=slice(None, gauge_end)).max())
    mod_peak_full = float(mod_sh.max())                             # true model peak, post-failure
    return {
        "gauge_obs_peak_m": obs_peak,
        "gauge_mod_peak_prefail_m": mod_peak_prefail,
        "gauge_peak_err_prefail_m": mod_peak_prefail - obs_peak,
        "gauge_mod_peak_full_m": mod_peak_full,
    }


# Observed historic crest at USGS 01407600 (Shrewsbury R @ Sea Bright). The NWS
# flood page lists 11.73 ft; its datum is CONFIRMED MLLW (Workstream A1, 2026-07-08):
# the NWS/NOAA gauge sbin4 for this site is published "(IN MLLW)"
# (water.noaa.gov/gauges/sbin4), distinct from USGS NWIS param 72279 which is NAVD88.
# So the MLLW -> NAVD88 conversion below is correct; 2.935 m NAVD88 and the ~-0.67 m
# deficit stand. Offset from NOAA VDatum (geoid18, MLLW 0.640 m below NAVD88 at
# 40.3656,-73.9747) — the offset value is the only remaining un-cross-checked link.
SHREWSBURY_CREST_FT = 11.73
SHREWSBURY_MLLW_BELOW_NAVD88_M = 0.640
FT_TO_M = 0.3048
SHREWSBURY_CREST_NAVD88 = SHREWSBURY_CREST_FT * FT_TO_M - SHREWSBURY_MLLW_BELOW_NAVD88_M  # 2.935

CREST_DATUM_NOTE = (
    "Shrewsbury crest 11.73 ft is MLLW (CONFIRMED: NWS gauge sbin4 published 'IN MLLW'; "
    "USGS NWIS param 72279 is a separate NAVD88 feed). Re-derivation: "
    "11.73 ft x 0.3048 - 0.640 (VDatum MLLW below NAVD88) = 2.935 m NAVD88."
)


def shrewsbury_gauge_peak(mod) -> dict:
    """USGS 01407600 Shrewsbury R @ Sea Bright — modeled peak vs observed Sandy crest.

    Observed crest is a fixed value (gauge telemetry, param 72279, failed
    2012-10-29 03:54, before Sandy's peak), not a time series. It anchors the
    in-river conveyance deficit on an instrument (vs the noisier back-bay HWMs).

    Workstream A4 — report the gauge-nudge explicitly: ``usgs_tidal_sea_bright``
    was nudged 21 m toward the -4.2 m channel (model.py:144), but SFINCS still
    snapped the obs point to a +1.38 m BANK cell (``shrewsbury_his_cell_zb_m``).
    This matters for the tidal RANGE (that cell dries at low water -> use
    ``tidal_range_metric`` at channel cells, not this point) but NOT for the surge
    PEAK reported here: at peak the local water surface is continuous, so a bank
    cell and the adjacent channel share the same zs. The his series is 10-min
    (captures the true peak); the hourly map would alias it. So the his peak is
    the right modeled peak here.
    """
    point_zs = mod.output.data["point_zs"]
    point_zb = mod.output.data["point_zb"]
    names = [
        n.decode() if isinstance(n, bytes) else str(n)
        for n in point_zs["station_name"].values
    ]
    i = next(k for k, n in enumerate(names) if "usgs_tidal_sea_bright" in n)
    mod_peak = float(point_zs.isel(stations=i).max())
    return {
        "shrewsbury_obs_crest_m": round(SHREWSBURY_CREST_NAVD88, 3),
        "shrewsbury_crest_datum_note": CREST_DATUM_NOTE,
        "shrewsbury_mod_peak_m": mod_peak,
        "shrewsbury_peak_err_m": mod_peak - SHREWSBURY_CREST_NAVD88,
        "shrewsbury_his_cell_zb_m": float(np.asarray(point_zb.isel(stations=i).values).item()),
    }


def tidal_range_metric(model_dir: Path, data_dir: Path = DATA,
                       window_hours: float = 24.0) -> dict:
    """Modeled vs observed pre-storm tidal RANGE at the in-domain USGS gauges.

    Workstream A3. Turns the one-off "interior range ~0.9 vs obs ~1.5 = over-
    damped" figure into a reproducible metric. Observed range from
    ``usgs_sandy_tidal_nj`` (01407600 Shrewsbury, 01407770 Shark R; NAVD88 m,
    pre-storm only). Modeled range from the map at genuine wet channel cells near
    each gauge (NOT the dry his obs points — see B). Both over the same clean
    tidal window (first ``window_hours`` of the run, before the surge ramp).

    Caveat: map output is hourly, so the modeled range is a mild UNDER-estimate
    (semidiurnal peaks/troughs can fall between samples); the qualitative
    over-damping (~0.7 m short at Shrewsbury) far exceeds that aliasing.

    SPIN-UP GUARD (2026-07-14). The modelled range is now measured on the
    DETRENDED series (see ``_tidal_signal``), because the raw ``max - min`` was
    reporting the model's monotonic spin-up drainage as a tide -- which is how a
    completely non-tidal, dammed-shut Shark River passed for months as a plausible
    "1.27 m range, 0.55 m damping". Each gauge now also reports:

        tide_mod_drift_<g>_m     the spin-up (net drift across the window)
        tide_mod_is_tidal_<g>    False => the series does not oscillate at all,
                                 and the range is NaN rather than a fabricated number
    """
    gauges = {
        "shrewsbury_01407600": (-73.97470, 40.36560, 1407600),
        "shark_r_01407770": (-74.02610, 40.18560, 1407770),
    }
    obs = xr.open_dataset(str(Path(data_dir) / "gtsm" / "usgs_sandy_tidal_nj.nc"))
    mp = xr.open_dataset(Path(model_dir) / "sfincs_map.nc")
    t0, t1 = _prestorm_window(mp["time"].values, window_hours)
    tsel = (mp["time"].values >= t0) & (mp["time"].values <= t1)
    ot = obs["time"].values
    osel = (ot >= t0) & (ot <= t1)

    out: dict = {}
    for name, (lon, lat, sid) in gauges.items():
        # observed range over the same window
        ow = obs["waterlevel"].sel(stations=sid).values[osel]
        ow = ow[np.isfinite(ow)]
        obs_range = float(ow.max() - ow.min()) if ow.size else float("nan")
        out[f"tide_obs_range_{name}_m"] = round(obs_range, 3)

        # modeled range at continuously-wet channel cells, spin-up removed
        mod_range = float("nan")
        drift = float("nan")
        frac_rising = float("nan")
        is_tidal = False
        cells = _wet_channel_cells(model_dir, lon, lat)
        if cells is not None:
            idx, _, _ = cells
            zsw = mp["zs"].isel(time=tsel, nmesh2d_face=idx).values  # (nt, ncell)
            full = np.isfinite(zsw).all(axis=0)
            if full.any():
                series = np.median(zsw[:, full], axis=1)   # one representative channel series
                sig = _tidal_signal(series)
                drift = sig["drift_m"]
                frac_rising = sig["frac_rising"]
                is_tidal = sig["is_tidal"]
                # refuse to report a "range" for a series that never turns around:
                # that is a drain (or a dead basin), not a tide.
                mod_range = sig["range_m"] if is_tidal else float("nan")
        out[f"tide_mod_range_{name}_m"] = round(mod_range, 3)
        out[f"tide_mod_drift_{name}_m"] = round(drift, 3)
        out[f"tide_mod_frac_rising_{name}"] = round(frac_rising, 3)
        out[f"tide_mod_is_tidal_{name}"] = is_tidal
        out[f"tide_range_damping_{name}_m"] = round(obs_range - mod_range, 3)
    return out


def hwm_metrics(da_hmax, da_dep, data_dir: Path = DATA) -> dict:
    """USGS High Water Mark residuals: RMSE/bias/within-0.5 m (headline q<=2).

    Two families of keys are returned, and the difference between them matters:

    ``*_scored`` (USE THESE)
        Every q<=2 mark is scored. A mark the model leaves DRY is not dropped --
        it is scored against the model's GROUND elevation there, i.e. "the model
        says the water never got above this bed". That is the most generous
        reading available (an upper bound on the model's skill at that mark), and
        it is still a large negative residual whenever the observations say metres
        of water stood there.

    ``hwm_bias_m`` / ``hwm_rmse_m`` / ``hwm_*_m`` (LEGACY, wet-only)
        The historical definition: ``wet & (qual <= 2)``. Kept so numbers in the
        existing reports/CSVs stay comparable -- NOT to be led with.

    WHY (2026-07-14). The wet-only metric **structurally rewards failing to
    flood**: the worse the model under-floods, the more marks fall out of the
    average, and the better the remaining average looks. It hid a real defect for
    months -- the Shark River Inlet was dammed shut in the DEM, so 2 of the 7
    south-coast marks sat in water the model never wetted, silently vanished, and
    ``south_coast`` reported a near-perfect -0.055 m bias while the river behind
    it was bone dry at +0.00 m through Hurricane Sandy.

    This is the mirror image of the FEMA-MOTF POD flaw (which rewards OVER-
    flooding). Never lead with either alone. Always read ``hwm_n_dry`` alongside
    any bias, and treat a CHANGE in the scored-mark count between two runs as
    invalidating the comparison.
    """
    GROUND_CAP = 0.5
    hwm = gpd.read_file(str(data_dir / "validation" / "sandy_hwms.geojson")).to_crs(
        da_dep.rio.crs
    )
    depth, dep_arr, wse = da_hmax.values, da_dep.values, (da_dep + da_hmax).values
    if depth.ndim == 3:
        depth, wse, dep_arr = depth[0], wse[0], dep_arr[0]
    T = da_dep.rio.transform()
    ny, nx = wse.shape
    rad = int(round(50 / abs(T.a)))

    obs = hwm["elev_m"].values
    qual = hwm["quality"].values.astype(float)
    mod_wse = np.full(len(obs), np.nan)     # wet-only (NaN where the model is dry)
    mod_ground = np.full(len(obs), np.nan)  # lowest ground in the window -> dry-mark score
    for k, (X, Y) in enumerate(zip(hwm.geometry.x.values, hwm.geometry.y.values)):
        col, row = int((X - T.c) / T.a), int((Y - T.f) / T.e)
        if 0 <= row < ny and 0 <= col < nx:
            sl = (
                slice(max(0, row - rad), row + rad + 1),
                slice(max(0, col - rad), col + rad + 1),
            )
            ws, hh, dd = wse[sl], depth[sl], dep_arr[sl]
            if np.isfinite(dd).any():
                mod_ground[k] = np.nanmin(dd)   # most generous: the lowest bed nearby
            flooded = (hh >= DEPTH_MIN) & (dd <= obs[k] + GROUND_CAP)
            if flooded.any():
                mod_wse[k] = np.nanmax(np.where(flooded, ws, np.nan))

    wet = np.isfinite(mod_wse)
    resid = mod_wse - obs
    head = wet & (qual <= 2)
    r = resid[head]

    # --- the honest metric: dry marks scored at ground level, never dropped ----
    mod_scored = np.where(wet, mod_wse, mod_ground)
    resid_s = mod_scored - obs
    head_s = np.isfinite(mod_scored) & (qual <= 2)   # only truly off-grid marks drop out
    rs = resid_s[head_s]

    result = {
        # headline (scored): every q<=2 mark on the grid counts
        "hwm_n_scored": int(head_s.sum()),
        "hwm_n_dry_scored": int((head_s & ~wet).sum()),
        "hwm_rmse_scored_m": float(np.sqrt((rs ** 2).mean())) if head_s.any() else float("nan"),
        "hwm_bias_scored_m": float(rs.mean()) if head_s.any() else float("nan"),
        "hwm_within0.5_scored": float(np.mean(np.abs(rs) < 0.5)) if head_s.any() else float("nan"),
        # legacy (wet-only) -- kept for continuity with existing reports
        "hwm_n_wet": int(wet.sum()),
        "hwm_n_dry": int((~wet).sum()),
        "hwm_rmse_m": float(np.sqrt((r ** 2).mean())) if head.any() else float("nan"),
        "hwm_bias_m": float(r.mean()) if head.any() else float("nan"),
        "hwm_within0.5": float(np.mean(np.abs(r) < 0.5)) if head.any() else float("nan"),
    }

    # A2 — per-basin residuals. Pooled bias ~0 hides that the ocean-front basin
    # validates while the behind-barrier Shrewsbury/Navesink basin under-fills;
    # this partition is the real conveyance verdict.
    basin = classify_hwm_basin(hwm.geometry.x.values, hwm.geometry.y.values)
    for b in HWM_BASINS:
        m = head & (basin == b)
        rb = resid[m]
        result[f"hwm_n_{b}"] = int(m.sum())
        result[f"hwm_bias_{b}_m"] = float(rb.mean()) if m.any() else float("nan")
        result[f"hwm_rmse_{b}_m"] = float(np.sqrt((rb ** 2).mean())) if m.any() else float("nan")

        ms = head_s & (basin == b)
        rbs = resid_s[ms]
        result[f"hwm_n_scored_{b}"] = int(ms.sum())
        result[f"hwm_n_dry_{b}"] = int((ms & ~wet).sum())
        result[f"hwm_bias_scored_{b}_m"] = float(rbs.mean()) if ms.any() else float("nan")
        result[f"hwm_rmse_scored_{b}_m"] = float(np.sqrt((rbs ** 2).mean())) if ms.any() else float("nan")
    return result


def motf_metrics(da_hmax, da_dep, data_dir: Path = DATA) -> dict:
    """FEMA MOTF extent: CSI / POD / FAR from hits/miss/false-alarm pixels."""
    with rasterio.open(str(data_dir / "validation" / "sandy_motf_extent.tif")) as r:
        motf, mtf, m_nd = r.read(1), r.transform, r.nodata
    mod_t = da_dep.rio.transform()
    mh, mw = motf.shape

    Xc = mtf.c + (np.arange(mw) + 0.5) * mtf.a
    Yc = mtf.f + (np.arange(mh) + 0.5) * mtf.e
    mc = np.clip(((Xc - mod_t.c) / mod_t.a).astype(int), 0, da_dep.shape[-1] - 1)
    mr = np.clip(((Yc - mod_t.f) / mod_t.e).astype(int), 0, da_dep.shape[-2] - 1)
    rr, cc = np.meshgrid(mr, mc, indexing="ij")
    _2d = lambda a: a[0] if a.ndim == 3 else a
    dep_at, h_at = _2d(da_dep.values)[rr, cc], _2d(da_hmax.values)[rr, cc]

    motf_wet = motf == 1
    mod_wet = (h_at >= DEPTH_MIN) & np.isfinite(h_at)
    land_in = (motf != m_nd) & (dep_at > 0.0)
    nh = int((motf_wet & mod_wet & land_in).sum())
    nm = int((motf_wet & ~mod_wet & land_in).sum())
    nf = int((~motf_wet & mod_wet & land_in).sum())
    return {
        "motf_csi": nh / (nh + nm + nf) if (nh + nm + nf) else float("nan"),
        "motf_pod": nh / (nh + nm) if (nh + nm) else float("nan"),
        "motf_far": nf / (nh + nf) if (nh + nf) else float("nan"),
    }


def sandy_hook_bay_hm0(mod) -> dict:
    """Mean/max SnapWave Hm0 in the Sandy Hook Bay lee (needs storewavdir=1).

    The headline "did waves get into the bay?" number: with swell blocked, any
    Hm0 here comes from wind growth or injected IG energy.
    """
    out = {"shb_hm0_mean": float("nan"), "shb_hm0_max": float("nan")}
    data = mod.output.data
    if "hm0" not in data:
        return out
    hm0 = data["hm0"]
    face_dim = next((d for d in hm0.dims if d != "time"), None)
    hm0_max = hm0.max("time") if "time" in hm0.dims else hm0

    # Face coordinates from the quadtree grid (UTM 18N). Fall back to NaN if the
    # output face ordering can't be matched to the grid.
    try:
        fc = mod.quadtree_grid.data.grid.face_coordinates
    except Exception:
        return out
    vals = np.asarray(hm0_max.values).ravel()
    if fc.shape[0] != vals.size:
        return out

    bay = gpd.GeoSeries([box(*SANDY_HOOK_BAY_BOX_LL)], crs=4326).to_crs(32618).iloc[0]
    minx, miny, maxx, maxy = bay.bounds
    inbox = (
        (fc[:, 0] >= minx) & (fc[:, 0] <= maxx)
        & (fc[:, 1] >= miny) & (fc[:, 1] <= maxy)
    )
    sel = vals[inbox & np.isfinite(vals)]
    if sel.size:
        out["shb_hm0_mean"] = float(sel.mean())
        out["shb_hm0_max"] = float(sel.max())
    return out


def evaluate(model_dir: Path, data_dir: Path = DATA,
             gallery_tif: Path | None = None) -> dict:
    """Full metric row for one experiment. Robust: missing pieces → NaN.

    If ``gallery_tif`` is given, the *masked* (permanent water dropped, north-up)
    ``da_hmax`` is written there for the report/notebook gallery — so the figure
    shows flooding on land, not the full water column of the bay/ocean. This is
    the same ``dep > -0.5`` display raster the notebook and HWM/CSI figures use;
    the raw ``floodmap_hmax_lev3.tif`` in the run dir stays unmasked.
    """
    row: dict = {}
    mod, da_hmax, da_dep = load_floodmap(model_dir)

    if gallery_tif is not None:
        Path(gallery_tif).parent.mkdir(parents=True, exist_ok=True)
        da_hmax.rio.to_raster(gallery_tif)

    for fn, args in [
        (gauge_peak_error, (mod, data_dir)),
        (shrewsbury_gauge_peak, (mod,)),
        (tidal_range_metric, (model_dir, data_dir)),
        (hwm_metrics, (da_hmax, da_dep, data_dir)),
        (motf_metrics, (da_hmax, da_dep, data_dir)),
        (sandy_hook_bay_hm0, (mod,)),
    ]:
        try:
            row.update(fn(*args))
        except Exception as e:  # noqa: BLE001 — keep the row, note the failure
            row[f"{fn.__name__}_error"] = str(e)
    return row
