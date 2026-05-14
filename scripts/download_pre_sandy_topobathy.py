#!/usr/bin/env python3
"""
Download the 2010 USACE NCMP Topobathy LiDAR DEM for NJ Atlantic Coast,
clipped to the model bbox.  This is the canonical PRE-Hurricane-Sandy
1 m topobathy product: collected in 2010, NAD83, true topobathy
(LiDAR + nearshore bathy fused).

Why this dataset (and not the 2022 USACE or NJ/Delaware CoNED):
    Sandy made landfall 2012-10-29.  Post-storm products bake in
    ~$1B+ of NJ beach replenishment + engineered dunes that did not
    exist during the storm — using them would systematically
    under-predict overtopping in a hindcast.  The 2010 NCMP product
    is ~2 years pre-storm — close enough that the beach state is
    representative without contamination from post-Sandy works.

Source : s3://noaa-nos-coastal-lidar-pds/dem/USACE_NJ_DEM_2010_9456/
NOAA ID: 9456     Whole-mosaic VRT (EPSG:4269) is provided.
Total raw dataset: ~721 MB (41 tiles).  We clip via /vsicurl/ so
only the bytes covering the bbox are fetched.

Usage:
    conda run -n sfincs python scripts/download_pre_sandy_topobathy.py

Output:
    data/elevation/usace_nj_2010_topobathy_clip.tif
"""

import subprocess
import sys
from pathlib import Path

# Model region (data/region.geojson) + ~0.01 deg buffer. Keep this tight:
# the 1 m USACE raster is ~20 GB in memory at the old oversized bbox, which
# OOMs hydromt's elevation merge on a 24 GB box. Clipped to the region it's
# ~4 GB. Update this if region.geojson changes.
BBOX_WGS84 = (-74.06, 40.14, -73.84, 40.51)  # west, south, east, north

VRT_URL = (
    "/vsicurl/https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/"
    "dem/USACE_NJ_DEM_2010_9456/USACE_NJ_DEM_2010_m9456_EPSG-4269.vrt"
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "elevation" / "usace_nj_2010_topobathy_clip.tif"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    west, south, east, north = BBOX_WGS84
    cmd = [
        "gdalwarp",
        "-overwrite",
        "-t_srs", "EPSG:4326",
        "-te", str(west), str(south), str(east), str(north),
        "-te_srs", "EPSG:4326",
        "-r", "bilinear",
        "-of", "GTiff",
        "-co", "COMPRESS=DEFLATE",
        "-co", "TILED=YES",
        "-co", "BLOCKXSIZE=512",
        "-co", "BLOCKYSIZE=512",
        "-co", "BIGTIFF=IF_SAFER",
        "--config", "GDAL_HTTP_UNSAFESSL", "YES",
        "--config", "VSI_CACHE", "TRUE",
        "--config", "GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR",
        VRT_URL,
        str(OUTPUT),
    ]
    print(f"Clipping 2010 USACE NJ topobathy to bbox {BBOX_WGS84} ...")
    print(f"  → {OUTPUT}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("gdalwarp failed", file=sys.stderr)
        sys.exit(result.returncode)
    print("Done.")


if __name__ == "__main__":
    main()
