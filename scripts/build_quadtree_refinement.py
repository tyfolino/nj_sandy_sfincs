"""
Build the refinement-polygons GeoJSON consumed by
`sf.quadtree_grid.create_from_region(refinement_polygons=...)` in the quadtree
notebooks.

The hydromt-sfincs quadtree builder
(`components/quadtree/quadtree_builder.py:196-220, 287-309`) accepts a GDF with:

  - `refinement_level` (int, required) — cells inside the polygon are halved
    `refinement_level` times. Base dx=200 m ⇒ levels 1/2/3 = 100/50/25 m
    (level 0 = the 200 m base, outside every polygon).
  - `zmin`, `zmax` (float, optional) — refinement is FURTHER gated by elevation:
    a cell is only refined if its zmin/zmax (over the build-time elevation_list)
    overlaps [polygon.zmin, polygon.zmax]. Lets us keep deep-water cells coarse.

Polygons must be in the GRID CRS (EPSG:32618 UTM 18N) because the algorithm
rotates polygon coords into grid space directly using the grid origin+rotation
(no internal reproject — line 230-242 of quadtree_builder.py).

────────────────────────────────────────────────────────────────────────────
Backwards compatibility (2026-06-29)
────────────────────────────────────────────────────────────────────────────
The original Sandy Hook→Asbury region had no Raritan Bay and little deep
offshore, so the legacy recipe was three full-region nested polygons. The
region was later expanded WEST (Raritan Bay) and EAST (offshore to the ERA5
wave node). Re-deriving the legacy recipe verbatim on the bigger region breaks:
  - level-1 (no gate, full region) would refine the new 30 km deep offshore to
    100 m, and
  - level-3 (z -8..+3, full region) would refine the whole shallow Raritan Bay
    to 25 m → cell explosion.

So this script is now region-adaptive, and the adaptations are NO-OPS for the
original region (i.e. re-running it against the archived setup reproduces the
legacy 3 polygons exactly):

  - The three base nested polygons are clipped to COASTAL_EXTENT — a box that
    CONTAINS the original region, so the clip is a no-op there, but trims the
    base polygons to the open coast on the expanded region (new offshore stays
    200 m; new bay is handled below, not at 25 m).
  - Two depth-gated bay boxes (BAY_BOXES) are added ONLY when the region reaches
    west of RARITAN_TRIGGER_LON, i.e. only when Raritan Bay is actually in the
    domain. The original region never triggers them.

Resulting rows:
  shelf_bay         level 1            → 100 m on the coastal corridor
  coastal_corridor  level 2, z -20..30 → 50 m back-bay/barrier/nearshore
  surf_dune         level 3, z -8..+3  → 25 m surf/dune
  raritan_approach  level 1, z -30..15 → 100 m Raritan/Sandy Hook Bay   (expanded only)
  raritan_bay       level 2, z -20..+3 → 50 m Raritan/Sandy Hook Bay    (expanded only)
  bay_shore         level 3, z  -2..+3 → 25 m Raritan/Sandy Hook SHORE  (expanded only)

Output: data/quadtree/refinement_polygons.geojson (EPSG:32618)
"""
import os
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

ROOT = Path(os.environ.get("NJ_ROOT", Path(__file__).resolve().parents[1]))
REGION = ROOT / "data" / "region.geojson"
OUT = ROOT / "data" / "quadtree" / "refinement_polygons.geojson"

GRID_EPSG = 32618

# Elevation gates (m, NAVD88). zb is positive UP.
LEVEL2_ZMIN, LEVEL2_ZMAX = -20.0, 30.0   # back-bay floor through highest dunes
LEVEL3_ZMIN, LEVEL3_ZMAX = -8.0,  3.0    # surf + foredune + immediate back-beach
                                          # (NJ coastal plain sits at +3-8 m;
                                          #  +3 zmax keeps it OUT of L3 — was
                                          #  pulling the whole inland into 25 m
                                          #  refinement on the first run.)

# Shrink the level-2 polygon eastward by this much, so the deep shelf
# (the easternmost slice) stays at level 1 = 100 m instead of pulling 50 m cells.
LEVEL2_EAST_SHRINK_M = 3000.0

# The legacy Atlantic-coast corridor (lon/lat). Sized to CONTAIN the original
# Sandy Hook→Asbury region, so clipping the base polygons to it is a no-op there
# but trims them to the open coast on an expanded region (keeps the new deep
# offshore at 200 m). Edit only if the open-coast strip itself moves.
COASTAL_EXTENT_LL = (-74.06, 40.14, -73.84, 40.51)

# Raritan Bay refinement — added ONLY when the region reaches west of this lon
# (i.e. Raritan Bay is in the domain). The original region (min lon -74.05)
# never triggers it, so the archived notebooks regenerate the legacy 3 polygons.
RARITAN_TRIGGER_LON = -74.10
BAY_BOXES = [
    # (name, refinement_level, zmin, zmax, (minlon, minlat, maxlon, maxlat))
    ("raritan_approach", 1, -30.0, 15.0, (-74.28, 40.38, -73.95, 40.52)),
    ("raritan_bay",      2, -20.0,  3.0, (-74.27, 40.40, -73.97, 40.52)),
    # 25 m on the Sandy Hook / Raritan Bay SHORELINE, for parity with the
    # Atlantic surf_dune. The tight z gate (-2..+3) is the key: it hugs the
    # intertidal fringe + low back-shore (the Highlands/Atlantic Highlands/
    # Keansburg low ground that actually inundates) while EXCLUDING the ~-5 m
    # bay floor, which stays at 50 m (raritan_bay) so the mesh doesn't explode.
    # Widen the floor toward -8 to match the Atlantic nearshore, but watch the
    # cell count — the bay basin is broad and shallow, so every metre of floor
    # you add sweeps in a lot of 25 m cells.
    ("bay_shore",        3,  -2.0,  3.0, (-74.28, 40.38, -73.95, 40.52)),
]


def _box_utm(bounds_ll):
    """lon/lat (minx,miny,maxx,maxy) box → shapely polygon in the grid CRS."""
    return gpd.GeoSeries([box(*bounds_ll)], crs=4326).to_crs(GRID_EPSG).iloc[0]


def main(region_path=REGION, out_path=OUT):
    region = gpd.read_file(region_path).to_crs(GRID_EPSG)
    full = region.geometry.iloc[0]

    # Base nested polygons, clipped to the open-coast corridor (no-op for the
    # original region; trims the new offshore/bay off the base levels otherwise).
    coastal = full.intersection(_box_utm(COASTAL_EXTENT_LL))
    cminx, cminy, cmaxx, cmaxy = coastal.bounds
    level2_geom = coastal.intersection(
        box(cminx, cminy, cmaxx - LEVEL2_EAST_SHRINK_M, cmaxy)
    )

    rows = [
        {
            # No elevation gate — values must be < -20000 / > +20000 to skip the
            # elevation filter (quadtree_builder.py:287). NaN would silently
            # disable refinement because all comparisons against NaN are False.
            "name": "shelf_bay",
            "refinement_level": 1,
            "zmin": -1e9,
            "zmax": 1e9,
            "geometry": coastal,
        },
        {
            "name": "coastal_corridor",
            "refinement_level": 2,
            "zmin": LEVEL2_ZMIN,
            "zmax": LEVEL2_ZMAX,
            "geometry": level2_geom,
        },
        {
            "name": "surf_dune",
            "refinement_level": 3,
            "zmin": LEVEL3_ZMIN,
            "zmax": LEVEL3_ZMAX,
            "geometry": coastal,
        },
    ]

    # Expanded-region (Raritan Bay) refinement. Skipped entirely for the
    # original region, so the archived notebooks reproduce the legacy 3 rows.
    region_minlon = region.to_crs(4326).total_bounds[0]
    if region_minlon < RARITAN_TRIGGER_LON:
        for name, level, zmin, zmax, bounds_ll in BAY_BOXES:
            geom = _box_utm(bounds_ll).intersection(full)
            if not geom.is_empty:
                rows.append(
                    {
                        "name": name,
                        "refinement_level": level,
                        "zmin": zmin,
                        "zmax": zmax,
                        "geometry": geom,
                    }
                )

    gdf = gpd.GeoDataFrame(rows, crs=GRID_EPSG)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path, driver="GeoJSON")

    print(f"Wrote {out_path}")
    print(f"  CRS: {gdf.crs}  |  region min lon: {region_minlon:.3f}  "
          f"({'EXPANDED — bay rows added' if region_minlon < RARITAN_TRIGGER_LON else 'original — legacy 3 rows'})")
    for _, row in gdf.iterrows():
        area_km2 = gpd.GeoSeries([row.geometry], crs=GRID_EPSG).area.iloc[0] / 1e6
        print(
            f"  {row['name']:<18} level={row['refinement_level']} "
            f"zmin={row['zmin']!s:>6} zmax={row['zmax']!s:>5} "
            f"area={area_km2:6.1f} km^2"
        )


if __name__ == "__main__":
    main()
