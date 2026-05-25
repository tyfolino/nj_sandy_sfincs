"""
Download the FEMA Modeling Task Force (MOTF) Hurricane Sandy storm-surge EXTENT
for the NJ model domain and write a georeferenced binary flood mask (GeoTIFF),
for SPATIAL (extent) validation of the SFINCS flood map.

Source: Rutgers ArcGIS MapServer, layer 0 "Sandy Surge Extent" — FEMA MOTF
"Final Field-Verified High Resolution" footprint, built by interpolating a water
surface from USGS HWMs + storm-tide sensors over the 3 m DEM (best estimate as of
11 Nov 2012). https://njmaps1.rad.rutgers.edu/arcgis/rest/services/CoastalFlooding/StormSurge/MapServer

CAVEATS:
  - The NJ statewide extent is a SINGLE polygon feature too large for the service
    to return as vector (geometry comes back null even with maxAllowableOffset).
    We use the service's `export` (render) op: draw layer 0 over the domain at
    ~RES m and treat non-transparent pixels as flooded. Fine vs a 50 m model.
  - The MOTF surface is HWM/sensor-interpolated over lidar (a static "bathtub"
    surface, not a hydrodynamic run), sharing provenance with our HWMs. Treat
    this as an extent CONSISTENCY check, not independent validation.
  - Output covers the full (rotated) domain bbox; restrict to model land/active
    cells when scoring (the validation cell does this).

RUNTIME REQUIREMENT: this env's GDAL can't find proj.db on its own and aborts on
CRS write. Invoke with the data dirs exported in the shell:
    PROJ_LIB=$CONDA_PREFIX/share/proj PROJ_DATA=$CONDA_PREFIX/share/proj \\
    GDAL_DATA=$CONDA_PREFIX/share/gdal python scripts/download_sandy_motf_extent.py
(In-script os.environ assignment is too late — the GDAL shared lib has already
initialised by the time Python runs the assignment.)

Output: data/validation/sandy_motf_extent.tif  (uint8, 1=flooded, 0=dry; EPSG:32618).
"""
import io
from pathlib import Path

# Import order matters with this env's GDAL: requests/geopandas/PIL must come
# before rasterio, or the GeoTIFF write aborts ("double free or corruption").
import requests
import numpy as np
import geopandas as gpd
from PIL import Image
import rasterio
from rasterio.transform import from_origin

REGION = Path("/home/zagreus/nj_sandy_sfincs/data/region.geojson")
OUT = Path("/home/zagreus/nj_sandy_sfincs/data/validation/sandy_motf_extent.tif")
EXPORT = ("https://njmaps1.rad.rutgers.edu/arcgis/rest/services/"
          "CoastalFlooding/StormSurge/MapServer/export")
EPSG = 32618
RES = 15.0   # m/pixel (export render resolution)

dom = gpd.read_file(REGION).to_crs(EPSG)
w, s, e, n = dom.total_bounds
W, H = int(round((e - w) / RES)), int(round((n - s) / RES))
print(f"domain bbox (EPSG:{EPSG}): {w:.0f},{s:.0f},{e:.0f},{n:.0f}  -> {W}x{H} @ {RES} m")

r = requests.get(EXPORT, params={
    "bbox": f"{w},{s},{e},{n}", "bboxSR": str(EPSG), "imageSR": str(EPSG),
    "size": f"{W},{H}", "layers": "show:0",
    "format": "png32", "transparent": "true", "f": "image",
}, timeout=180)
r.raise_for_status()
rgba = np.array(Image.open(io.BytesIO(r.content)).convert("RGBA"))
flooded = (rgba[..., 3] > 10).astype("uint8")   # any non-transparent fill = surge extent
print(f"rendered flooded pixels: {flooded.sum()} ({flooded.mean() * 100:.1f}%) "
      f"= {flooded.sum() * RES * RES / 1e6:.1f} km2")

OUT.parent.mkdir(parents=True, exist_ok=True)
with rasterio.open(OUT, "w", driver="GTiff", height=H, width=W, count=1,
                   dtype="uint8", crs=f"EPSG:{EPSG}",
                   transform=from_origin(w, n, RES, RES),
                   nodata=255, compress="deflate") as dst:
    dst.write(flooded, 1)
print(f"Wrote {OUT}")
