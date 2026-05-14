#!/usr/bin/env python3
"""
Download NOAA NCEI 1/9 arc-second Coastal Relief Model (CUDEM) tiles covering
New Jersey and adjacent coastal waters, then build a virtual mosaic (VRT).

Source: NOAA NCEI Topobathy DEM, northeast_sandy collection
        https://chs.coast.noaa.gov/htdata/raster2/elevation/NCEI_ninth_Topobathy_2014_8483/
Resolution: ~3 m (1/9 arc-second)
CRS: EPSG:4269 (NAD83 geographic, essentially identical to WGS-84/EPSG:4326)
Datum: NAVD88 — note: project uses MSL (difference ~0.1-0.3 m on NJ coast;
       apply a +0.18 m offset when setting up the model DEM if needed)

Usage:
    conda run -n sfincs python scripts/download_cudem.py

Output:
    data/elevation/cudem/raw/ncei19_*.tif   (individual tiles, ~60 MB each)
    data/elevation/cudem_nj.vrt             (virtual mosaic — use in data_catalog.yml)

The VRT is a lightweight metadata file that rasterio/hydromt reads lazily;
it avoids loading all 57 tiles into memory at once.  If you later need a
single clipped GeoTIFF run:
    gdal_translate -projwin <ulx> <uly> <lrx> <lry> data/elevation/cudem_nj.vrt out.tif
"""

import subprocess
import sys
import urllib.request
from pathlib import Path

BASE_URL = (
    "https://chs.coast.noaa.gov/htdata/raster2/elevation/"
    "NCEI_ninth_Topobathy_2014_8483/northeast_sandy/"
)

# All confirmed tiles from NOAA northeast_sandy collection that cover NJ +
# adjacent NY Bight and Delaware Bay offshore areas.
TILES = [
    # Southern NJ / Delaware Bay  (lat ~38.85-40°N)
    "ncei19_n39x00_w075x00_2018v2.tif",
    "ncei19_n39x00_w075x25_2014v1.tif",
    "ncei19_n39x00_w075x50_2014v1.tif",
    "ncei19_n39x25_w074x75_2018v2.tif",
    "ncei19_n39x25_w075x00_2018v2.tif",
    "ncei19_n39x25_w075x25_2018v2.tif",
    "ncei19_n39x25_w075x50_2014v1.tif",
    "ncei19_n39x50_w074x50_2018v2.tif",
    "ncei19_n39x50_w074x75_2018v2.tif",
    "ncei19_n39x50_w075x25_2018v2.tif",
    "ncei19_n39x50_w075x50_2018v2.tif",
    "ncei19_n39x50_w075x75_2014v1.tif",
    "ncei19_n39x75_w074x25_2018v2.tif",
    "ncei19_n39x75_w074x50_2018v2.tif",
    "ncei19_n39x75_w075x50_2014v1.tif",
    "ncei19_n39x75_w075x75_2014v1.tif",
    # Central NJ / Asbury Park area  (lat ~40-40.75°N)
    "ncei19_n40x00_w074x25_2018v2.tif",
    "ncei19_n40x00_w075x25_2014v1.tif",
    "ncei19_n40x00_w075x50_2014v1.tif",
    "ncei19_n40x25_w074x00_2018v2.tif",
    "ncei19_n40x25_w074x25_2018v2.tif",
    "ncei19_n40x25_w074x75_2014v1.tif",
    "ncei19_n40x25_w075x00_2014v1.tif",
    "ncei19_n40x25_w075x25_2014v1.tif",
    "ncei19_n40x50_w074x00_2018v2.tif",
    "ncei19_n40x50_w074x25_2018v2.tif",
    "ncei19_n40x75_w073x00_2015v1.tif",
    "ncei19_n40x75_w073x25_2015v1.tif",
    "ncei19_n40x75_w073x50_2015v1.tif",
    "ncei19_n40x75_w073x75_2015v1.tif",
    "ncei19_n40x75_w074x00_2015v1.tif",
    "ncei19_n40x75_w074x25_2015v1.tif",
    # Northern NJ / NY Bight  (lat ~41-41.5°N)
    "ncei19_n41x00_w072x25_2015v1.tif",
    "ncei19_n41x00_w072x50_2015v1.tif",
    "ncei19_n41x00_w072x75_2015v1.tif",
    "ncei19_n41x00_w073x00_2015v1.tif",
    "ncei19_n41x00_w073x25_2015v1.tif",
    "ncei19_n41x00_w073x50_2015v1.tif",
    "ncei19_n41x00_w073x75_2015v1.tif",
    "ncei19_n41x00_w074x00_2015v1.tif",
    "ncei19_n41x00_w074x25_2015v1.tif",
    "ncei19_n41x25_w072x00_2015v1.tif",
    "ncei19_n41x25_w072x25_2015v1.tif",
    "ncei19_n41x25_w072x50_2015v1.tif",
    "ncei19_n41x25_w072x75_2015v1.tif",
    "ncei19_n41x25_w073x00_2016v1.tif",
    "ncei19_n41x25_w073x25_2016v1.tif",
    "ncei19_n41x25_w073x50_2015v1.tif",
    "ncei19_n41x25_w073x75_2015v1.tif",
    "ncei19_n41x25_w074x00_2015v1.tif",
    "ncei19_n41x50_w072x00_2016v1.tif",
    "ncei19_n41x50_w072x25_2016v1.tif",
    "ncei19_n41x50_w072x50_2016v1.tif",
    "ncei19_n41x50_w072x75_2016v1.tif",
    "ncei19_n41x50_w073x00_2016v1.tif",
    "ncei19_n41x50_w074x00_2015v1.tif",
    "ncei19_n41x50_w074x25_2015v1.tif",
]

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "elevation" / "cudem" / "raw"
VRT_OUT = ROOT / "data" / "elevation" / "cudem_nj.vrt"


def _progress(total_bytes: int):
    downloaded = [0]

    def cb(block_count, block_size, _total):
        downloaded[0] = block_count * block_size
        if total_bytes > 0:
            pct = min(downloaded[0] / total_bytes * 100, 100)
            print(
                f"\r    {downloaded[0]/1e6:.1f} / {total_bytes/1e6:.1f} MB"
                f"  ({pct:.0f}%)",
                end="",
                flush=True,
            )

    return cb


def download_tiles() -> list[Path]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    for tile in TILES:
        dest = RAW_DIR / tile
        if dest.exists():
            print(f"  skip (cached)  {tile}")
            downloaded.append(dest)
            continue
        url = BASE_URL + tile
        print(f"  downloading    {tile}")
        try:
            # Get Content-Length for progress display
            with urllib.request.urlopen(url) as resp:
                total = int(resp.headers.get("Content-Length", 0))
            urllib.request.urlretrieve(url, dest, reporthook=_progress(total))
            print()
            downloaded.append(dest)
        except urllib.error.HTTPError as e:
            print(f"\n  WARNING: {tile} → HTTP {e.code} — skipping")
    return downloaded


def build_vrt(tile_paths: list[Path]) -> None:
    if not tile_paths:
        print("No tiles to mosaic.")
        return
    VRT_OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["gdalbuildvrt", str(VRT_OUT)] + [str(p) for p in tile_paths]
    print(f"\nBuilding VRT: {VRT_OUT}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"gdalbuildvrt failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(f"Done — {VRT_OUT.name}  ({len(tile_paths)} tiles)")
    print(
        "\nAdd to data_catalog.yml as:\n"
        "  cudem_nj:\n"
        "    data_type: RasterDataset\n"
        f"    uri: elevation/cudem_nj.vrt\n"
        "    driver:\n"
        "      name: rasterio\n"
        "      options: {}\n"
        "    metadata:\n"
        "      category: topography\n"
        "      crs: 4269\n"
        "      unit: m+NAVD88\n"
        "      source: NOAA NCEI 1/9 arc-sec Topobathy DEM (northeast_sandy)"
    )


def main() -> None:
    print(f"Downloading {len(TILES)} CUDEM tiles (~3.3 GB total) to:\n  {RAW_DIR}\n")
    paths = download_tiles()
    build_vrt(paths)


if __name__ == "__main__":
    main()
