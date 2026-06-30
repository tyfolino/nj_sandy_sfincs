#!/usr/bin/env python3
"""
Download GMRT (Global Multi-Resolution Topography) bathymetry for the model
region and save a single GeoTIFF for use as the offshore / deep-water bottom
layer of the elevation merge.

Why GMRT instead of GEBCO (as of 2026-06-29):
  - GEBCO's programmatic WCS/WMS service is dead (all endpoints 404 behind their
    CMS); only a manual web download remains.
  - GMRT is a no-key, scriptable bbox GeoTIFF service that blends GEBCO *plus*
    shipboard multibeam. For the NJ shelf it returns ~50 m float bathymetry vs
    GEBCO's 450 m integer-quantized grid (those integer "cliffs" are what the
    project_hm0_spike_rootcause memory blames for the SnapWave hm0 spikes).

Source : GMRT GridServer, https://www.gmrt.org/services/gridserverinfo.php
CRS    : EPSG:4326
Datum  : sea level (~MSL) — same role as the old GEBCO tail (unit m+MSL)

Usage:
    ./micromamba/envs/sfincs/bin/python scripts/download_gmrt.py [--force]

Output:
    data/elevation/gmrt_nj.tif   (use as `gmrt_nj` in data_catalog.yml)

Re-clip if the region changes: widen BBOX to the new footprint (+ a small
buffer) so the bottom layer covers the whole domain.
"""

import sys
import urllib.parse
import urllib.request
from pathlib import Path

# Model region bbox (+ buffer). Region is lon[-74.28,-73.45], lat[40.15,40.52];
# pad outward so the bottom layer fully covers the mesh edges.
BBOX = dict(minlongitude=-74.40, maxlongitude=-73.35,
            minlatitude=40.05, maxlatitude=40.60)

BASE_URL = "https://www.gmrt.org/services/GridServer"
OUT = Path(__file__).resolve().parents[1] / "data" / "elevation" / "gmrt_nj.tif"


def main(force=False):
    if OUT.exists() and not force:
        print(f"{OUT} already exists — use --force to re-download.")
        return
    params = {**BBOX, "format": "geotiff", "resolution": "high", "layer": "topo"}
    url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"GET {url}")
    with urllib.request.urlopen(url, timeout=180) as r:
        data = r.read()
    if not data[:2] in (b"II", b"MM"):  # TIFF magic
        sys.exit(f"Response is not a TIFF ({len(data)} bytes) — service error:\n"
                 f"{data[:300]!r}")
    OUT.write_bytes(data)

    # GMRT ships the GeoTIFF WITHOUT a nodata tag (hydromt warns, and the south-
    # edge NaN strip goes unflagged). Tag nodata = NaN. NB: GMRT renders inland
    # water / bay surfaces as exactly 0 m — we deliberately leave those as 0
    # (they're a valid flat water surface, and CUDEM/nj_10ft_dem override them in
    # the merge anyway); only the true NaN gaps become nodata.
    import rasterio
    with rasterio.open(OUT, "r+") as ds:
        ds.nodata = float("nan")
    print(f"wrote {OUT}  ({len(data) / 1e6:.1f} MB)  [nodata=NaN]")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
