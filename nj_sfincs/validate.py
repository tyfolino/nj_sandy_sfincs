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
from shapely.geometry import box

from hydromt_sfincs import SfincsModel, utils

from .config import ROOT

DATA = ROOT / "data"

# Sandy Hook Bay lee (lon/lat box) — the sheltered water behind the Hook spit
# where Atlantic swell cannot diffract in; this is the target for wind/IG waves.
SANDY_HOOK_BAY_BOX_LL = (-74.075, 40.420, -73.980, 40.480)

DEPTH_MIN = 0.15  # m; a cell counts as "wet" above this (HWM + MOTF)


def load_floodmap(model_dir: Path):
    """Open the run read-only and downscale zsmax onto the L3 subgrid DEM.

    Returns ``(mod, da_hmax, da_dep)`` — the model handle plus the north-up
    depth-max and subgrid-DEM rasters the spatial metrics sample.
    """
    model_dir = Path(model_dir).resolve()
    mod = SfincsModel(str(model_dir), data_libs=[str(DATA / "data_catalog.yml")], mode="r")
    mod.output.read()

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
    gauge_end = pd.Timestamp("2012-10-29 23:00")

    obs_peak = float(obs_sh.max())
    mod_peak = float(mod_sh.sel(time=slice(None, gauge_end)).max())
    return {
        "gauge_obs_peak_m": obs_peak,
        "gauge_mod_peak_m": mod_peak,
        "gauge_peak_err_m": mod_peak - obs_peak,
    }


def hwm_metrics(da_hmax, da_dep, data_dir: Path = DATA) -> dict:
    """USGS High Water Mark residuals: RMSE/bias/within-0.5 m (headline q<=2)."""
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
    mod_wse = np.full(len(obs), np.nan)
    for k, (X, Y) in enumerate(zip(hwm.geometry.x.values, hwm.geometry.y.values)):
        col, row = int((X - T.c) / T.a), int((Y - T.f) / T.e)
        if 0 <= row < ny and 0 <= col < nx:
            sl = (
                slice(max(0, row - rad), row + rad + 1),
                slice(max(0, col - rad), col + rad + 1),
            )
            ws, hh, dd = wse[sl], depth[sl], dep_arr[sl]
            flooded = (hh >= DEPTH_MIN) & (dd <= obs[k] + GROUND_CAP)
            if flooded.any():
                mod_wse[k] = np.nanmax(np.where(flooded, ws, np.nan))

    wet = np.isfinite(mod_wse)
    resid = mod_wse - obs
    head = wet & (qual <= 2)
    r = resid[head]
    return {
        "hwm_n_wet": int(wet.sum()),
        "hwm_n_dry": int((~wet).sum()),
        "hwm_rmse_m": float(np.sqrt((r ** 2).mean())) if head.any() else float("nan"),
        "hwm_bias_m": float(r.mean()) if head.any() else float("nan"),
        "hwm_within0.5": float(np.mean(np.abs(r) < 0.5)) if head.any() else float("nan"),
    }


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
        (hwm_metrics, (da_hmax, da_dep, data_dir)),
        (motf_metrics, (da_hmax, da_dep, data_dir)),
        (sandy_hook_bay_hm0, (mod,)),
    ]:
        try:
            row.update(fn(*args))
        except Exception as e:  # noqa: BLE001 — keep the row, note the failure
            row[f"{fn.__name__}_error"] = str(e)
    return row
