#!/usr/bin/env python3
"""Build the eHydro CARVING TIER — federal channel surveys that un-pave the lidar.

WHY THIS TIER EXISTS
--------------------
`usace_nj_2010` (1 m pre-Sandy topobathy lidar) is the TOP entry in
`DEFAULT_ELEVATION_LIST`, because in clear shallow water its green lidar returns the real
bed. But in deep or turbid water it fails to penetrate and returns the **water surface**
instead — ~0 to +2 m, indistinguishable from ordinary land. Ranked first, those bogus
returns shadow CUDEM's correct bed underneath, and where it happens across a channel the
channel is **sealed shut**.

That is what dammed Shark River Inlet. Real bed (eHydro soundings): −4.6 to −10.8 m. Lidar:
+0.4 to +2.2 m. CUDEM: −2.2 to −4.5 m, correct, and never consulted. Result: the entire
Shark River estuary **never floods in any run of this project — peak water level exactly
+0.00 m, its initial condition — while the ocean 1.8 km away reaches +2.9 m.** It is not a
bridge: the dam's western edge is exactly the edge of the lidar tile's coverage.

An eHydro condition survey is a boat with an echo sounder. It is the only source here that
directly measures the bed *under* the water, so it is the only thing that can outrank the
lidar. It goes ON TOP.

WHICH SURVEYS
-------------
Chosen by `scripts/audit_paved_channels.py`, which screens the whole domain for "model says
land, CUDEM says >2 m of water" and then arbitrates each candidate by asking whether a boat
actually sounded WATER at those cells. That audit's verdict was mostly NEGATIVE, and usefully
so — the Sea Bright revetment patches were rejected (soundings there read +2.4 m: the seawall
is real and the 1 m lidar has it right), Sandy Hook Channel was rejected (the patches sit on
the spit, not the channel), and the Shrewsbury is already carved. **Shark River Inlet is
essentially the only genuine paving in the domain.**

THE WATER-ONLY CLIP (the safety rail)
-------------------------------------
This tier is a CARVING tier, not a general DEM. It supplies values only where it says WATER
(z < ``WATER_MAX``); everywhere else it is NoData and the normal tiers show through. That is
what makes it impossible for a survey to accidentally flatten a structure: a beach or
shore-protection survey that happens to cover the revetment reports +2.4 m there, which is
clipped out, so the seawall can never be carved away by this file. Given the revetment is a
knife edge in this model (storm tide lands ON it, 59–75% overtopped), that rail is not
optional.

PROCESSING (unchanged from the proven Shrewsbury chain)
-------------------------------------------------------
  1. horizontal  EPSG:3424 (NAD83 / NJ State Plane, US survey ft) -> EPSG:32618 (UTM18N, m)
  2. vertical    MLLW ft -> NAVD88 m via the NOAA VDatum REST API. The separation is NOT
                 constant (−0.45 m south to −0.84 m north over the Shrewsbury footprint — a
                 0.39 m gradient that matters at channel-depth precision), so we query VDatum
                 at ~N_VDATUM thinned sounding locations, cache them, and interpolate the
                 offset FIELD onto every point.
  3. rasterise   linear (Delaunay) interpolation onto a 5 m UTM18N grid, then MASK to the
                 survey's `Bathymetry_Vector` coverage polygons, then apply the water-only
                 clip -> NoData everywhere except real surveyed channel bed.

OUTPUT: data/elevation/ehydro_nj.tif   (5 m, UTM18N, NAVD88 m, NoData off-channel)

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/download_ehydro_nj.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ELEV = ROOT / "data" / "elevation"
EHYDRO = ELEV / "ehydro"
RAW = EHYDRO / "raw"

# Surveys to carve. Verdicts from scripts/audit_paved_channels.py (2026-07-14).
# Shrewsbury (NJ_14_SNR_20150902_CS_4368_15) is deliberately NOT here: it already ships as
# its own tier, `shrewsbury_ehydro_2015`, from the bridge-as-dam fix.
SURVEYS = [
    # id                                  channel                district
    ("NJ_10_SRI_20150902_CS_4383_15", "Shark River Inlet", "CENAN"),
]

ZIP_URL = ("https://ehydroprod.blob.core.usgovcloudapi.net/"
           "ehydro-surveys/{district}/{sid}.ZIP")

EPSG_SRC = 3424      # NAD83 / NJ State Plane (US survey foot)
EPSG_DST = 32618     # WGS84 / UTM 18N (metre) -- model CRS
FT_TO_M = 0.3048006096012192

RES = 5.0            # output raster resolution (m) ~ the sounding spacing
N_VDATUM = 250       # thinned VDatum query nodes per survey (cached)
WATER_MAX = -1.0     # the carving clip: this tier only ever supplies REAL WATER

RASTER_OUT = ELEV / "ehydro_nj.tif"
NODATA = np.float32(-9999.0)


def fetch(sid: str, district: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    zp = RAW / f"{sid}.ZIP"
    if not zp.exists():
        url = ZIP_URL.format(district=district, sid=sid)
        print(f"  downloading {url}")
        urllib.request.urlretrieve(url, zp)
    out = RAW / sid
    if not out.exists():
        with zipfile.ZipFile(zp) as z:
            z.extractall(out)
    return out


def vdatum_offset(lon: float, lat: float) -> float:
    """NAVD88 height (m) of the MLLW=0 surface at (lon, lat); NaN outside coverage."""
    url = (
        "https://vdatum.noaa.gov/vdatumweb/api/convert?"
        f"s_x={lon:.6f}&s_y={lat:.6f}&s_z=0&region=contiguous&s_coor=geo"
        "&s_h_frame=NAD83_2011&s_v_frame=MLLW&s_v_unit=us_ft"
        "&t_h_frame=NAD83_2011&t_v_frame=NAVD88&t_v_unit=m"
    )
    try:
        r = json.load(urllib.request.urlopen(url, timeout=30))
        tz = float(r["t_z"])
    except Exception as exc:  # noqa: BLE001
        print(f"    VDatum err at {lon:.4f},{lat:.4f}: {exc}", file=sys.stderr)
        return float("nan")
    return tz if tz > -1000 else float("nan")


def offset_field(sid: str, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Spatially-varying MLLW->NAVD88 offset (m). A single mean is NOT good enough."""
    from scipy.interpolate import griddata

    cache_csv = EHYDRO / f"vdatum_{sid}.csv"
    if cache_csv.exists():
        cache = np.loadtxt(cache_csv, delimiter=",", skiprows=1)
        print(f"    {len(cache)} cached VDatum nodes")
    else:
        idx = np.unique(np.linspace(0, len(lon) - 1, N_VDATUM).astype(int))
        print(f"    querying VDatum at {len(idx)} thinned locations …")
        rows = []
        for k, i in enumerate(idx):
            off = vdatum_offset(lon[i], lat[i])
            if np.isfinite(off):
                rows.append((lon[i], lat[i], off))
            if (k + 1) % 50 == 0:
                print(f"      {k + 1}/{len(idx)}")
            time.sleep(0.12)
        cache = np.array(rows)
        np.savetxt(cache_csv, cache, delimiter=",",
                   header="lon,lat,offset_navd88_m", comments="")
        print(f"    cached {len(cache)} nodes -> {cache_csv.name}")

    print("    offset field (m): mean %.3f  min %.3f  max %.3f"
          % (cache[:, 2].mean(), cache[:, 2].min(), cache[:, 2].max()))
    off = griddata(cache[:, :2], cache[:, 2], (lon, lat), method="linear")
    bad = ~np.isfinite(off)
    if bad.any():
        off[bad] = griddata(cache[:, :2], cache[:, 2], (lon[bad], lat[bad]), method="nearest")
    return off


def main() -> None:
    import geopandas as gpd
    import pyproj
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.transform import from_origin
    from scipy.interpolate import griddata

    to_ll = pyproj.Transformer.from_crs(EPSG_SRC, 4326, always_xy=True)
    to_utm = pyproj.Transformer.from_crs(EPSG_SRC, EPSG_DST, always_xy=True)

    parts = []   # (xm, ym, z_navd88, coverage_gdf)
    for sid, chan, district in SURVEYS:
        print(f"\n[{chan}]  {sid}")
        d = fetch(sid, district)
        xyz = next(d.glob("*.XYZ"))
        gdb = next(d.glob("*.gdb"))
        raw = np.loadtxt(xyz)
        x_ft, y_ft, z_mllw_ft = raw[:, 0], raw[:, 1], raw[:, 2]
        print(f"    {len(raw)} soundings; MLLW ft {z_mllw_ft.min():.1f}..{z_mllw_ft.max():.1f}")

        lon, lat = to_ll.transform(x_ft, y_ft)
        xm, ym = to_utm.transform(x_ft, y_ft)
        off = offset_field(sid, np.asarray(lon), np.asarray(lat))
        z = z_mllw_ft * FT_TO_M + off
        print(f"    NAVD88 m: {z.min():.2f} .. {z.max():.2f}")

        cover = gpd.read_file(gdb, layer="Bathymetry_Vector").to_crs(EPSG_DST)
        parts.append((np.asarray(xm), np.asarray(ym), z, cover))

    # --- common grid over every survey ---------------------------------------------------
    xs = np.concatenate([p[0] for p in parts])
    ys = np.concatenate([p[1] for p in parts])
    xmin = np.floor(xs.min() / RES) * RES
    ymin = np.floor(ys.min() / RES) * RES
    xmax = np.ceil(xs.max() / RES) * RES
    ymax = np.ceil(ys.max() / RES) * RES
    ncol = int((xmax - xmin) / RES)
    nrow = int((ymax - ymin) / RES)
    transform = from_origin(xmin, ymax, RES, RES)
    cx = xmin + (np.arange(ncol) + 0.5) * RES
    cy = ymax - (np.arange(nrow) + 0.5) * RES
    gx, gy = np.meshgrid(cx, cy)
    print(f"\ngrid {nrow} x {ncol} @ {RES:g} m")

    grid = np.full((nrow, ncol), np.nan, dtype="float32")
    for xm, ym, z, cover in parts:
        g = griddata((xm, ym), z, (gx, gy), method="linear").astype("float32")
        inside = ~geometry_mask(cover.geometry, out_shape=(nrow, ncol),
                                transform=transform, invert=False)
        g[~inside] = np.nan
        grid = np.where(np.isfinite(g), g, grid)

    n_cover = int(np.isfinite(grid).sum())

    # --- the carving clip: this tier only ever supplies REAL WATER ------------------------
    # Anything the survey reports at or above WATER_MAX is dropped, so a shore-protection or
    # beach survey can never flatten a seawall/jetty through this file. See the module docstring.
    grid[np.isfinite(grid) & (grid >= WATER_MAX)] = np.nan
    n_water = int(np.isfinite(grid).sum())
    print(f"surveyed cells: {n_cover}   -> after water-only clip (< {WATER_MAX} m): {n_water}"
          f"   (dropped {n_cover - n_water} at/above the clip — structures, banks, spoil)")

    grid[~np.isfinite(grid)] = NODATA
    with rasterio.open(
        RASTER_OUT, "w", driver="GTiff", height=nrow, width=ncol, count=1,
        dtype="float32", crs=EPSG_DST, transform=transform, nodata=NODATA,
        compress="DEFLATE", tiled=True, blockxsize=512, blockysize=512,
    ) as dst:
        dst.write(grid, 1)
    print(f"\nwrote {RASTER_OUT.relative_to(ROOT)}  ({n_water} carved cells)")


if __name__ == "__main__":
    main()
