"""
Build the refinement-polygons GeoJSON consumed by
`sf.quadtree_grid.create_from_region(refinement_polygons=...)` in the Phase-3
quadtree+SnapWave notebook.

The hydromt-sfincs quadtree builder
(`components/quadtree/quadtree_builder.py:196-220, 287-309`) accepts a GDF with:

  - `refinement_level` (int, required) — cells inside the polygon are halved
    `refinement_level` times. Base dx=200 m ⇒ levels 0/1/2/3 = 200/100/50/25 m.
  - `zmin`, `zmax` (float, optional) — refinement is FURTHER gated by elevation:
    a cell is only refined if its zmin/zmax (over the build-time elevation_list)
    overlaps [polygon.zmin, polygon.zmax]. Lets us keep deep-water cells coarse.

Polygons must be in the GRID CRS (EPSG:32618 UTM 18N) because the algorithm
rotates polygon coords into grid space directly using the grid origin+rotation
(no internal reproject — line 230-242 of quadtree_builder.py).

Three nested rows, all derived from data/region.geojson:

  Row 1: full region, level=1                          → 200→100 m everywhere
  Row 2: full region (east edge shrunk by 3 km),       → 100→50 m on back-bay,
         level=2, zmin=-20, zmax=+30                       barrier, nearshore;
                                                          deep shelf stays 100 m
  Row 3: full region, level=3, zmin=-8, zmax=+8        → 50→25 m only at the
                                                          surf/dune wave-active
                                                          strip

Cell count target ~130k (vs 265k regular grid). Tune by editing LEVEL2_*/LEVEL3_*.

Output: data/quadtree/refinement_polygons.geojson (EPSG:32618)
"""
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

ROOT = Path("/home/zagreus/nj_sandy_sfincs")
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


def main():
    region = gpd.read_file(REGION).to_crs(GRID_EPSG)
    full = region.geometry.iloc[0]

    minx, miny, maxx, maxy = full.bounds
    level2_geom = full.intersection(
        box(minx, miny, maxx - LEVEL2_EAST_SHRINK_M, maxy)
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
            "geometry": full,
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
            "geometry": full,
        },
    ]

    gdf = gpd.GeoDataFrame(rows, crs=GRID_EPSG)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUT, driver="GeoJSON")

    print(f"Wrote {OUT}")
    print(f"  CRS: {gdf.crs}")
    for _, row in gdf.iterrows():
        area_km2 = gpd.GeoSeries([row.geometry], crs=GRID_EPSG).area.iloc[0] / 1e6
        print(
            f"  {row['name']:<18} level={row['refinement_level']} "
            f"zmin={row['zmin']!s:>6} zmax={row['zmax']!s:>5} "
            f"area={area_km2:6.1f} km^2"
        )


if __name__ == "__main__":
    main()
