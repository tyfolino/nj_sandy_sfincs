"""Extract the SFINCS wavemaker LineString at the −5 m NAVD88 contour from CUDEM.

The wavemaker is the alongshore line inside the SFINCS active domain where the
SnapWave radiation-stress forcing is injected as a forced inflow. Mirrors the
Leijnse et al. (Carolinas / Florence) architecture: a discrete line, not a
zonal coupling.

Output: data/wavemakers/wavemaker_line.geojson  (EPSG:32618)
"""
import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from shapely.geometry import LineString, box
import contourpy

ROOT = Path(os.environ.get("NJ_ROOT", Path(__file__).resolve().parents[1]))
DEM_PATH = ROOT / "data/elevation/cudem_asbury.tif"
REGION_PATH = ROOT / "data/region.geojson"
OUT_DIR = ROOT / "data/wavemakers"
OUT_PATH = OUT_DIR / "wavemaker_line.geojson"

CONTOUR_Z = -5.0           # m NAVD88; Leijnse-style ~5 m at high tide
SIMPLIFY_TOL_M = 200.0     # ~one 200 m cell — keep alongshore shape, drop micro-wiggles
TARGET_CRS = "EPSG:32618"  # SFINCS model CRS

# Optional alongshore trim — keep contour only within model y-range (UTM 18N northing)
# Sandy Hook ~4480 km, Manasquan ~4438 km. Trim to model bbox lat range.

OUT_DIR.mkdir(parents=True, exist_ok=True)

# --- load region in target CRS for clipping bbox ---
region = gpd.read_file(REGION_PATH).to_crs(TARGET_CRS)
minx, miny, maxx, maxy = region.total_bounds
print(f"region bounds (UTM 18N, m): x∈[{minx:.0f}, {maxx:.0f}]  y∈[{miny:.0f}, {maxy:.0f}]")

# --- reproject CUDEM to UTM 18N at 30 m for stable contouring ---
TARGET_RES_M = 30.0
with rasterio.open(DEM_PATH) as src:
    transform, width, height = calculate_default_transform(
        src.crs, TARGET_CRS, src.width, src.height, *src.bounds, resolution=TARGET_RES_M
    )
    dst = np.full((height, width), np.nan, dtype="float32")
    reproject(
        source=rasterio.band(src, 1),
        destination=dst,
        src_transform=src.transform,
        src_crs=src.crs,
        dst_transform=transform,
        dst_crs=TARGET_CRS,
        resampling=Resampling.bilinear,
        dst_nodata=np.nan,
    )

print(f"reprojected DEM: shape={dst.shape}  res={TARGET_RES_M} m  CRS={TARGET_CRS}")
print(f"  z range (valid): [{np.nanmin(dst):.2f}, {np.nanmax(dst):.2f}]")

# --- extract −5 m contour using contourpy ---
arr = np.where(np.isfinite(dst), dst, -9999.0).astype("float64")
ny, nx = arr.shape
xg = np.arange(nx, dtype="float64")
yg = np.arange(ny, dtype="float64")
gen = contourpy.contour_generator(xg, yg, arr, line_type=contourpy.LineType.SeparateCode)
lines, _codes = gen.lines(CONTOUR_Z)
print(f"found {len(lines)} raw contour segments")

# Convert each segment from (col, row) -> (x, y) in the target CRS
def rc_to_xy(rc):
    cols, rows = rc[:, 0], rc[:, 1]
    xs, ys = rasterio.transform.xy(transform, rows, cols)
    return np.column_stack([xs, ys])

contours = lines

INSET = 200.0
bbox_poly = box(minx + INSET, miny + INSET, maxx - INSET, maxy - INSET)

segments = []
for c in contours:
    if len(c) < 3:
        continue
    xy = rc_to_xy(c)
    line = LineString(xy)
    clipped = line.intersection(bbox_poly)
    if clipped.is_empty:
        continue
    geoms = [clipped] if clipped.geom_type == "LineString" else list(clipped.geoms)
    for g in geoms:
        if g.geom_type == "LineString" and g.length > 1000.0:
            segments.append(g)

print(f"kept {len(segments)} segments > 1 km after clipping to model bbox")
segments.sort(key=lambda g: g.length, reverse=True)
for i, g in enumerate(segments[:5]):
    xs, ys = np.array(g.coords).T
    print(f"  seg {i}: length={g.length/1000:.2f} km   y∈[{ys.min():.0f}, {ys.max():.0f}]")

# Pick the single longest segment — the open-coast alongshore contour
if not segments:
    raise SystemExit("No contour segments survived. Check DEM coverage and CONTOUR_Z.")
wavemaker = segments[0]

# Ensure direction is south->north (SFINCS wavemakers: order matters; convention
# 'land on the right when walking the line' so waves come from the left/sea).
# Our coast is roughly N-S with sea to the EAST -> for waves to come from east,
# we need land on the right when walking, i.e. walk from SOUTH to NORTH.
coords = np.array(wavemaker.coords)
if coords[0, 1] > coords[-1, 1]:
    coords = coords[::-1]
    wavemaker = LineString(coords)
    print("reversed line to south->north (so SnapWave forcing enters from the east)")

# PLAN A: open-coast only — trim off the Sandy Hook wrap. The full −5 m contour
# climbs the open coast then curves NW around the Sandy Hook spit (~y=4480–4482k)
# into Sandy Hook Bay, which we don't want feeding wave forcing in this first test.
#
# REPRODUCIBILITY: the old trim used argmax(y) = "keep up to the northernmost
# point." But the contour's SEGMENT CONNECTIVITY around the Hook is version-
# sensitive (contourpy/reproject differ across stacks): on one machine the open
# coast and the Hook wrap are one connected segment, on another they split. With
# argmax that produced different northern endpoints (desktop 33.7 km, stopping at
# the open-coast end y≈4478k; Amarel 37.8 km, wrapping to the Hook tip y≈4482k) —
# and the extra NW wrap put wavemaker points on the L3 refinement boundary and
# destabilised SFINCS (uvmax>1000). A FIXED NORTHING CAP makes the trim identical
# regardless of how contourpy stitches the segments.
Y_OPEN_COAST_MAX = 4_478_500.0   # m UTM18N; just N of the open coast, S of the Hook-tip wrap
coords = np.array(wavemaker.coords)
n_before = len(coords)
north_of_cap = np.where(coords[:, 1] > Y_OPEN_COAST_MAX)[0]   # walking S->N, first crossing
cut = int(north_of_cap[0]) if north_of_cap.size else len(coords)
coords = coords[:cut]
print(f"open-coast trim: kept {len(coords)}/{n_before} vertices "
      f"(cap y<={Y_OPEN_COAST_MAX:.0f}, stops at y={coords[-1, 1]:.0f})")
wavemaker = LineString(coords)

# Simplify to drop micro-wiggles below the 200 m grid resolution
wavemaker = wavemaker.simplify(SIMPLIFY_TOL_M, preserve_topology=False)
print(f"final wavemaker: length={wavemaker.length/1000:.2f} km  vertices={len(wavemaker.coords)}")

# Save as GeoJSON
gdf = gpd.GeoDataFrame(
    {"name": ["nj_coast_-5m"]}, geometry=[wavemaker], crs=TARGET_CRS
)
gdf.to_file(OUT_PATH, driver="GeoJSON")
print(f"wrote {OUT_PATH}")
