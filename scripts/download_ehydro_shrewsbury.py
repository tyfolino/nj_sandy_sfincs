#!/usr/bin/env python3
"""
Download + process the USACE eHydro 2015 Shrewsbury River condition survey
into a NAVD88-metre channel-bathymetry tier for the SFINCS elevation merge.

WHY (see the project_bridge_dam memory):
    The Rumson-Sea Bright bridge causeway is baked into the NJ 10 ft lidar +
    CUDEM as a solid +1.6..+8.6 m earthen dam across the Shrewsbury narrows.
    It blocks tide + surge -> flat Shrewsbury gauge + Oceanport under-flooding.
    88 % of the dam footprint is solid fill in every fine source, so there is
    no buried channel to re-prioritise; we need a REAL bathymetric survey of
    the dredged channel to restore conveyance. BlueTopo's Shrewsbury pixels are
    from a Dec-2025 (POST bridge-rebuild) survey -> rejected. USACE eHydro is a
    PRE-rebuild federal condition survey of the navigation channel.

PICK: NJ_14_SNR_20150902_CS_4368_15 (2015-09-02, type CS). Footprint covers the
    whole Navesink + Shrewsbury system (Sandy Hook Bay -> through the
    Rumson-Sea Bright narrows -> Oceanport, + Navesink to Red Bank). The channel
    is stable and we only need the opening depth, so 2015 is a fine 2012 proxy.

SURVEY DATA (USACE eHydro .zip, see ReadMe_Survey_Data_Format.txt):
    .XYZ            thinned soundings  -> X Y Z, ~19k pts, EPSG:3424, Z = MLLW ft
    .gdb            Bathymetry_Vector  -> per-tile coverage polygons (the real
                                          surveyed footprint, used as the mask)
    horizontal      EPSG:3424  NAD83 / NJ State Plane (US survey foot)
    vertical        MLLW, US survey foot, NEGATIVE = below MLLW (it's a depth
                    survey; XYZ Z already carries the sign, DAT is +depth)

PROCESSING:
    1. horizontal  EPSG:3424 ft  -> EPSG:32618 (UTM18N, m), via pyproj
    2. vertical    MLLW ft       -> NAVD88 m, via the NOAA VDatum REST API.
                   The MLLW->NAVD88 separation is NOT constant here: it ranges
                   -0.45 m (south) to -0.84 m (north, up-estuary) over the
                   footprint (a 0.39 m gradient that matters at channel-depth
                   precision). So we query VDatum at ~400 thinned in-water
                   sounding locations, cache them, and interpolate the offset
                   field onto every point -- not a single mean offset.
                   z_NAVD88_m = z_MLLW_ft * 0.3048006096 + offset(x, y)
    3. rasterise   linear (Delaunay) interpolation of z onto a 5 m UTM18N grid
                   (matches the ~5 m sounding spacing), then MASK to the
                   Bathymetry_Vector coverage polygons so the tier carries data
                   ONLY in the surveyed channel ribbon and is NoData on the
                   marsh flats / land -> in setup_dep it overrides CUDEM/lidar
                   ONLY in the channel and is a pure fill everywhere else.

OUTPUT:
    data/elevation/ehydro/shrewsbury_ehydro_2015_points.gpkg  (UTM18N, z m NAVD88)
    data/elevation/shrewsbury_ehydro_2015.tif                 (5 m, UTM18N, NAVD88 m,
                                                                NoData off-channel)
    data/elevation/ehydro/vdatum_offsets_2015.csv             (cached VDatum nodes)

Usage:
    ~/miniforge3/envs/sfincs/bin/python scripts/download_ehydro_shrewsbury.py
"""

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

SURVEY = "NJ_14_SNR_20150902_CS_4368_15"
ZIP_URL = (
    "https://ehydroprod.blob.core.usgovcloudapi.net/"
    f"ehydro-surveys/CENAN/{SURVEY}.ZIP"
)

EPSG_SRC = 3424      # NAD83 / NJ State Plane (US survey foot)
EPSG_DST = 32618     # WGS84 / UTM 18N (metre)  -- model CRS
FT_TO_M = 0.3048006096012192  # US survey foot

RES = 5.0            # output raster resolution (m), ~ the 5 m sounding spacing
N_VDATUM = 400       # number of thinned points to query VDatum at (cached)

POINTS_OUT = EHYDRO / "shrewsbury_ehydro_2015_points.gpkg"
RASTER_OUT = ELEV / "shrewsbury_ehydro_2015.tif"
VDATUM_CSV = EHYDRO / "vdatum_offsets_2015.csv"


def download_and_extract() -> Path:
    """Fetch + unzip the eHydro survey; return the extracted directory."""
    RAW.mkdir(parents=True, exist_ok=True)
    zip_path = RAW / f"{SURVEY}.ZIP"
    if not zip_path.exists():
        print(f"Downloading {ZIP_URL}")
        urllib.request.urlretrieve(ZIP_URL, zip_path)
    extract_dir = RAW / "extracted"
    if not (extract_dir / f"{SURVEY}.XYZ").exists():
        print(f"Extracting -> {extract_dir}")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir)
    return extract_dir


def vdatum_mllw_to_navd88(lon: float, lat: float) -> float:
    """NAVD88 height (m) of the MLLW=0 surface at (lon, lat); NaN if no coverage."""
    url = (
        "https://vdatum.noaa.gov/vdatumweb/api/convert?"
        f"s_x={lon:.6f}&s_y={lat:.6f}&s_z=0&region=contiguous&s_coor=geo"
        "&s_h_frame=NAD83_2011&s_v_frame=MLLW&s_v_unit=us_ft"
        "&t_h_frame=NAD83_2011&t_v_frame=NAVD88&t_v_unit=m"
    )
    try:
        r = json.load(urllib.request.urlopen(url, timeout=30))
        tz = float(r["t_z"])
    except Exception as exc:  # noqa: BLE001 - network/parse, just skip the node
        print(f"  VDatum err at {lon:.4f},{lat:.4f}: {exc}", file=sys.stderr)
        return float("nan")
    return tz if tz > -1000 else float("nan")


def build_offset_field(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """VDatum MLLW->NAVD88 offset (m) for every point, via a cached thinned query."""
    if VDATUM_CSV.exists():
        cache = np.loadtxt(VDATUM_CSV, delimiter=",", skiprows=1)
        print(f"Loaded {len(cache)} cached VDatum nodes from {VDATUM_CSV.name}")
    else:
        idx = np.linspace(0, len(lon) - 1, N_VDATUM).astype(int)
        print(f"Querying VDatum at {len(idx)} thinned sounding locations ...")
        rows = []
        for k, i in enumerate(idx):
            off = vdatum_mllw_to_navd88(lon[i], lat[i])
            if np.isfinite(off):
                rows.append((lon[i], lat[i], off))
            if (k + 1) % 50 == 0:
                print(f"  {k + 1}/{len(idx)} ...")
            time.sleep(0.15)
        cache = np.array(rows)
        hdr = "lon,lat,offset_navd88_m"
        np.savetxt(VDATUM_CSV, cache, delimiter=",", header=hdr, comments="")
        print(f"Cached {len(cache)} valid VDatum nodes -> {VDATUM_CSV.name}")

    print(
        "  offset field (m): mean %.3f std %.3f min %.3f max %.3f"
        % (cache[:, 2].mean(), cache[:, 2].std(), cache[:, 2].min(), cache[:, 2].max())
    )
    from scipy.interpolate import griddata

    pts = cache[:, :2]
    off = griddata(pts, cache[:, 2], (lon, lat), method="linear")
    # nearest-neighbour fill for points outside the convex hull of the nodes
    nan = ~np.isfinite(off)
    if nan.any():
        off[nan] = griddata(pts, cache[:, 2], (lon[nan], lat[nan]), method="nearest")
    return off


def main() -> None:
    import geopandas as gpd
    import pyproj
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.transform import from_origin
    from scipy.interpolate import griddata

    extract_dir = download_and_extract()
    xyz_path = extract_dir / f"{SURVEY}.XYZ"
    gdb = extract_dir / f"{SURVEY}.gdb"

    # --- 1. soundings: X,Y (EPSG:3424 ft), Z (MLLW ft, signed) ----------------
    d = np.loadtxt(xyz_path)
    x_ft, y_ft, z_mllw_ft = d[:, 0], d[:, 1], d[:, 2]
    print(f"Read {len(d)} soundings; Z(MLLW ft) range {z_mllw_ft.min():.1f}..{z_mllw_ft.max():.1f}")

    # --- 2. horizontal -> lon/lat (for VDatum) and -> UTM18N (output) ---------
    to_ll = pyproj.Transformer.from_crs(EPSG_SRC, 4326, always_xy=True)
    to_utm = pyproj.Transformer.from_crs(EPSG_SRC, EPSG_DST, always_xy=True)
    lon, lat = to_ll.transform(x_ft, y_ft)
    xm, ym = to_utm.transform(x_ft, y_ft)

    # --- 3. vertical MLLW ft -> NAVD88 m (spatially-varying VDatum offset) ----
    offset = build_offset_field(np.asarray(lon), np.asarray(lat))
    z_navd88_m = z_mllw_ft * FT_TO_M + offset
    print(f"Z(NAVD88 m) range {z_navd88_m.min():.2f}..{z_navd88_m.max():.2f}")

    # --- write the processed point cloud --------------------------------------
    EHYDRO.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(
        {"z_navd88_m": z_navd88_m, "z_mllw_ft": z_mllw_ft, "offset_m": offset},
        geometry=gpd.points_from_xy(xm, ym),
        crs=EPSG_DST,
    )
    gdf.to_file(POINTS_OUT, driver="GPKG")
    print(f"Wrote {len(gdf)} points -> {POINTS_OUT.relative_to(ROOT)}")

    # --- 4. rasterise to 5 m UTM18N, masked to the survey coverage polygons ---
    cover = gpd.read_file(gdb, layer="Bathymetry_Vector").to_crs(EPSG_DST)
    xmin = np.floor(xm.min() / RES) * RES
    ymin = np.floor(ym.min() / RES) * RES
    xmax = np.ceil(xm.max() / RES) * RES
    ymax = np.ceil(ym.max() / RES) * RES
    ncol = int((xmax - xmin) / RES)
    nrow = int((ymax - ymin) / RES)
    transform = from_origin(xmin, ymax, RES, RES)

    # cell-centre coordinates
    cx = xmin + (np.arange(ncol) + 0.5) * RES
    cy = ymax - (np.arange(nrow) + 0.5) * RES
    gx, gy = np.meshgrid(cx, cy)
    print(f"Interpolating onto {nrow} x {ncol} grid @ {RES:g} m ...")
    grid = griddata((xm, ym), z_navd88_m, (gx, gy), method="linear").astype("float32")

    # coverage mask: keep only cells inside the surveyed footprint polygons
    inside = ~geometry_mask(
        cover.geometry, out_shape=(nrow, ncol), transform=transform, invert=False
    )
    nodata = np.float32(-9999.0)
    grid[~inside] = nodata
    grid[~np.isfinite(grid)] = nodata
    n_valid = int((grid != nodata).sum())
    print(f"  {n_valid} valid channel cells ({100 * n_valid / grid.size:.1f}% of grid)")

    with rasterio.open(
        RASTER_OUT, "w", driver="GTiff", height=nrow, width=ncol, count=1,
        dtype="float32", crs=EPSG_DST, transform=transform, nodata=nodata,
        compress="DEFLATE", tiled=True, blockxsize=512, blockysize=512,
    ) as dst:
        dst.write(grid, 1)
    print(f"Wrote raster -> {RASTER_OUT.relative_to(ROOT)}")
    print("Done.")


if __name__ == "__main__":
    main()
