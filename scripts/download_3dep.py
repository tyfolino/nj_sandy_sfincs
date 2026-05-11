#!/usr/bin/env python3
"""
Download the NJ OGIS statewide 10-ft (~3 m) LiDAR DEM from the njogis-elevation
S3 bucket, clip to a bbox of interest, reproject to WGS-84, and write a
compressed GeoTIFF for use in the hydromt data catalog.

Source: s3://njogis-elevation  (public, no credentials required)
Resolution: 10 ft (~3 m), EPSG:6527 (NJ State Plane 2011, US survey feet)
Coverage: full New Jersey statewide mosaic

Usage:
    conda run -n sfincs python scripts/download_3dep.py

Raw download (~16 GB, one-time):
    data/elevation/raw/Rast_statewide_10ft_DEM.img
    data/elevation/raw/Rast_statewide_10ft_DEM.ige

Output:
    data/elevation/nj_10ft_dem.tif   (clipped, WGS-84, deflate-compressed)
"""

import sys
from pathlib import Path

import boto3
import rasterio
import rasterio.warp
from botocore import UNSIGNED
from botocore.config import Config
from pyproj import Transformer

# ── clip bbox (WGS-84) ────────────────────────────────────────────────────────
# Coastal NJ around Asbury Park.  Expand west/south for all-NJ runs.
#   west   south   east   north
BBOX_WGS84 = (-74.5, 39.8, -73.9, 40.5)

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "elevation" / "raw"
OUTPUT = ROOT / "data" / "elevation" / "nj_10ft_dem.tif"

# ── S3 source ─────────────────────────────────────────────────────────────────
BUCKET = "njogis-elevation"
S3_PREFIX = "derived_products/statewide_2021/Statewide_10ft_DEM_2021/Raster/"
FILES = ["Rast_statewide_10ft_DEM.img", "Rast_statewide_10ft_DEM.ige"]

SRC_CRS = "EPSG:6527"   # NJ State Plane 2011, US survey feet
DST_CRS = "EPSG:4326"   # WGS-84


def s3_client():
    return boto3.client("s3", config=Config(signature_version=UNSIGNED), region_name="us-west-2")


def download_raw(s3, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for fname in FILES:
        dest = dest_dir / fname
        if dest.exists():
            print(f"  skip (cached)  {fname}")
            continue
        key = S3_PREFIX + fname
        size_mb = s3.head_object(Bucket=BUCKET, Key=key)["ContentLength"] / 1e6
        print(f"  downloading    {fname}  ({size_mb:.0f} MB)")
        s3.download_file(
            Bucket=BUCKET,
            Key=key,
            Filename=str(dest),
            Callback=_progress(size_mb),
        )
        print()


def _progress(total_mb: float):
    downloaded = [0.0]

    def cb(n_bytes):
        downloaded[0] += n_bytes / 1e6
        pct = min(downloaded[0] / total_mb * 100, 100)
        print(f"\r    {downloaded[0]:.0f} / {total_mb:.0f} MB  ({pct:.0f}%)", end="", flush=True)

    return cb


def clip_and_reproject(src_path: Path, dst_path: Path, bbox_wgs84: tuple) -> None:
    west, south, east, north = bbox_wgs84
    t = Transformer.from_crs(DST_CRS, SRC_CRS, always_xy=True)
    xmin, ymin = t.transform(west, south)
    xmax, ymax = t.transform(east, north)

    print(f"Clipping to bbox and reprojecting {SRC_CRS} → {DST_CRS} ...")
    with rasterio.open(src_path) as src:
        window = src.window(xmin, ymin, xmax, ymax)
        data = src.read(window=window)
        src_transform = src.window_transform(window)
        src_crs = src.crs
        nodata = src.nodata

        dst_transform, dst_width, dst_height = rasterio.warp.calculate_default_transform(
            src_crs, DST_CRS, data.shape[2], data.shape[1],
            left=xmin, bottom=ymin, right=xmax, top=ymax,
        )

        import numpy as np
        dst_arr = np.full((1, dst_height, dst_width), nodata if nodata is not None else -9999.0, dtype=data.dtype)

        rasterio.warp.reproject(
            source=data,
            destination=dst_arr,
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=dst_transform,
            dst_crs=DST_CRS,
            resampling=rasterio.warp.Resampling.bilinear,
        )

    # Source pixel values are in US survey feet (EPSG:6527 linear unit); convert to meters.
    nodata_val = nodata if nodata is not None else -9999.0
    dst_arr = dst_arr.astype("float32")
    valid = dst_arr != nodata_val
    dst_arr[valid] *= 0.3048

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        dst_path, "w",
        driver="GTiff",
        height=dst_height,
        width=dst_width,
        count=1,
        dtype="float32",
        crs=DST_CRS,
        transform=dst_transform,
        nodata=nodata if nodata is not None else -9999.0,
        compress="deflate",
        tiled=True,
        blockxsize=512,
        blockysize=512,
    ) as dst:
        dst.write(dst_arr)

    print(f"Done: {dst_path}")


def main() -> None:
    s3 = s3_client()

    print("Downloading raw NJ 10-ft DEM from S3 (~16 GB total) ...")
    download_raw(s3, RAW_DIR)

    img_path = RAW_DIR / "Rast_statewide_10ft_DEM.img"
    clip_and_reproject(img_path, OUTPUT, BBOX_WGS84)


if __name__ == "__main__":
    main()
