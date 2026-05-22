"""
Download the FEMA Modeling Task Force (MOTF) Hurricane Sandy storm-surge EXTENT
for the NJ model domain and write a georeferenced binary flood mask (GeoTIFF),
for SPATIAL (extent) validation of the SFINCS flood map.

Source: Rutgers ArcGIS MapServer, layer 0 "Sandy Surge Extent" — FEMA MOTF
"Final Field-Verified High Resolution" footprint, built by interpolating a water
surface from USGS HWMs + storm-tide sensors over the 3 m DEM (best estimate as of
11 Nov 2012). https://njmaps1.rad.rutgers.edu/arcgis/rest/services/CoastalFlooding/StormSurge/MapServer

CAVEAT: this is the NJ statewide extent as a SINGLE polygon feature — too large for
the service to return as vector (the /query geometry comes back null). So we use the
service's `export` (render) op: draw layer 0 over the domain at a fixed resolution
and treat non-transparent pixels as flooded (~RES m; fine vs a 50 m model). NOTE it
shares provenance with our HWMs (HWM/sensor-interpolated, static "bathtub" surface,
not a hydrodynamic run) -> treat as an extent CONSISTENCY check, not independent
validation. The output covers the full (rotated) domain bbox; restrict to model
land/active cells when scoring.

Output: data/validation/sandy_motf_extent.tif  (uint8, 1=flooded, 0=dry; EPSG:32618).
"""
import io
import os
from pathlib import Path

# This conda env ships a proj.db that GDAL can't locate on its own (it aborts on
# CRS write). Point GDAL/PROJ at the env data dirs BEFORE importing rasterio.
_SHARE = "/home/zagreus/miniforge3/envs/sfincs/share"
os.environ["PROJ_LIB"] = f"{_SHARE}/proj"
os.environ["PROJ_DATA"] = f"{_SHARE}/proj"
os.environ["GDAL_DATA"] = f"{_SHARE}/gdal"

import geopandas as gpd
import numpy as np
import rasterio
import requests
from PIL import Image
from rasterio.transform import from_origin

REGION = Path("/home/zagreus/nj_sandy_sfincs/data/region.geojson")
OUT_DIR = Path("/home/zagreus/nj_sandy_sfincs/data/validation")
OUT = OUT_DIR / "sandy_motf_extent.tif"
EXPORT = ("https://njmaps1.rad.rutgers.edu/arcgis/rest/services/"
          "CoastalFlooding/StormSurge/MapServer/export")
EPSG = 32618
RES = 15.0   # m/pixel (export render resolution)


def main():
    dom = gpd.read_file(REGION).to_crs(EPSG)
    w, s, e, n = dom.total_bounds
    W, H = int(round((e - w) / RES)), int(round((n - s) / RES))
    print(f"domain bbox (EPSG:{EPSG}): {w:.0f},{s:.0f},{e:.0f},{n:.0f}  -> {W}x{H} @ {RES} m")

    params = {
        "bbox": f"{w},{s},{e},{n}", "bboxSR": str(EPSG), "imageSR": str(EPSG),
        "size": f"{W},{H}", "layers": "show:0",
        "format": "png32", "transparent": "true", "f": "image",
    }
    r = requests.get(EXPORT, params=params, timeout=180)
    r.raise_for_status()
    rgba = np.array(Image.open(io.BytesIO(r.content)).convert("RGBA"))
    flooded = (rgba[..., 3] > 10).astype("uint8")     # any non-transparent fill = surge extent
    print(f"rendered flooded pixels: {flooded.sum()} ({flooded.mean()*100:.1f}%) "
          f"= {flooded.sum() * RES * RES / 1e6:.1f} km2")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tif.tmp")
    with rasterio.open(tmp, "w", driver="GTiff", height=H, width=W, count=1,
                       dtype="uint8", crs=f"EPSG:{EPSG}", transform=from_origin(w, n, RES, RES),
                       nodata=255, compress="deflate") as dst:
        dst.write(flooded, 1)
    os.replace(tmp, OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
