"""
Burn major NJ inlet channels into a small GeoTIFF for the inlet-connectivity
experiment. The merged DEM otherwise resolves these inlets too coarsely at 50 m,
throttling surge flow into the back-bays — which the MOTF spatial validation
flags as missed inland flooding (the inland blue cluster in Shrewsbury / Shark
River / Deal Lake / Wreck Pond marshes).

This raster is added as the TOP-priority elevation source in the experiment
notebook (`notebooks/experiment_inlet_connectivity.ipynb`), which builds a
SEPARATE `model_inlet_test/` directory. The working `model/` is untouched.

Channels are hand-defined polylines (WGS84) drawn with width ~CHANNEL_WIDTH_M
and burned at CHANNEL_ELEV_M NAVD88. Edit the INLETS dict to refine.

RUNTIME REQUIREMENT (this env): export PROJ data dirs before invoking, e.g.:
    PROJ_LIB=$CONDA_PREFIX/share/proj PROJ_DATA=$CONDA_PREFIX/share/proj \\
    GDAL_DATA=$CONDA_PREFIX/share/gdal python scripts/build_inlet_channels.py
Imports must be requests-first → rasterio-last AND we draw with PIL (not
rasterio.features.rasterize, which aborts in this env — same family as the
geometry_mask crash documented in scripts/download_sandy_motf_extent.py).

Output: data/elevation/inlet_channels_burn.tif (EPSG:32618; -2 m at channel
pixels, NoData elsewhere — set as a fill layer in the elevation merge).
"""
from pathlib import Path

import numpy as np
from pyproj import Transformer
import geopandas as gpd
from PIL import Image, ImageDraw
import rasterio
from rasterio.transform import from_origin

OUT = Path("/home/zagreus/nj_sandy_sfincs/data/elevation/inlet_channels_burn.tif")
REGION = Path("/home/zagreus/nj_sandy_sfincs/data/region.geojson")

EPSG = 32618
RES = 5.0                  # m; fine enough that the channel survives subgrid averaging
CHANNEL_ELEV_M = -2.0      # NAVD88
CHANNEL_WIDTH_M = 60.0     # full channel width in meters

INLETS = {
    "shrewsbury":  [(-74.013, 40.466), (-74.025, 40.466), (-74.038, 40.460)],
    "shark_river": [(-74.027, 40.186), (-74.034, 40.185), (-74.041, 40.184)],
    "deal_lake":   [(-74.000, 40.222), (-74.003, 40.221), (-74.008, 40.221)],
}


def main():
    dom = gpd.read_file(REGION).to_crs(EPSG)
    w, s, e, n = dom.total_bounds
    W, H = int(round((e - w) / RES)), int(round((n - s) / RES))
    transform = from_origin(w, n, RES, RES)
    print(f"raster grid: {W}x{H} @ {RES} m, EPSG:{EPSG}")

    # Draw each centerline as a thick PIL line; convert WGS84 -> UTM -> pixel.
    to_utm = Transformer.from_crs(4326, EPSG, always_xy=True)
    img = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(img)
    width_px = max(1, int(round(CHANNEL_WIDTH_M / RES)))
    for name, pts in INLETS.items():
        xs, ys = to_utm.transform([p[0] for p in pts], [p[1] for p in pts])
        cols = [(x - transform.c) / transform.a for x in xs]
        rows = [(y - transform.f) / transform.e for y in ys]
        coords = list(zip(cols, rows))
        draw.line(coords, fill=1, width=width_px, joint="curve")
        print(f"  {name:11s} {len(pts)} pts, drawn at width {width_px} px (~{width_px * RES:.0f} m)")

    mask = np.array(img)
    arr = np.full((H, W), np.nan, dtype="float32")
    arr[mask > 0] = CHANNEL_ELEV_M
    print(f"channel pixels: {int((mask > 0).sum())} ({(mask > 0).mean() * 100:.2f}% of raster)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(OUT, "w", driver="GTiff", height=H, width=W, count=1, dtype="float32",
                       crs=f"EPSG:{EPSG}", transform=transform,
                       nodata=float("nan"), compress="deflate") as dst:
        dst.write(arr, 1)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
