"""
Download NOAA AORC v1.1 hourly precipitation over the NJ model domain during
Hurricane Sandy and write a hydromt_sfincs RasterDataset NetCDF.

AORC (Analysis of Record for Calibration) is an observation-grounded gridded
QPE/forcing product (it blends Stage IV radar-gauge QPE with gauge analyses),
~1 km (30 arcsec) hourly, 1979-present — so unlike MRMS (≳2014) it covers the
Oct 2012 Sandy window. Public AWS Open Data, Zarr, one store per year:
    s3://noaa-nws-aorc-v1-1-1km/2012.zarr

The precip variable is `APCP_surface` in kg/m^2 = mm ACCUMULATED over each
1-hour interval. We keep it as accumulated mm and let hydromt convert to a rate:
    sf.precipitation.create(precip="aorc_sandy_nj", cumulative_input=True)
(hydromt divides by the 1 h interval -> mm/hr; the numbers are identical but the
semantics are correct).

Output schema matches the renamed `era5_nj.nc` convention:
  dims:   (time, y, x)
  coords: time, y (lat, descending), x (lon)
  var:    precip(time, y, x)  [mm accumulated per hour]
"""
import os
from pathlib import Path

import geopandas as gpd
import s3fs
import xarray as xr

ROOT = Path(os.environ.get("NJ_ROOT", Path(__file__).resolve().parents[1]))
REGION = ROOT / "data/region.geojson"
OUT_DIR = ROOT / "data/precip"
OUT = OUT_DIR / "aorc_sandy_nj.nc"

AORC_STORE = "noaa-nws-aorc-v1-1-1km/2012.zarr"
PRECIP_VAR = "APCP_surface"

# Sandy window (UTC), matching the rest of the model forcing.
TSTART = "2012-10-28"
TSTOP = "2012-10-31"
# Pad the spatial clip by ~1 AORC cell so edge cells aren't dropped on reproject.
BUFFER_DEG = 0.05


def main():
    w, s, e, n = gpd.read_file(REGION).to_crs(4326).total_bounds
    print(f"region bbox: lon[{w:.3f}, {e:.3f}] lat[{s:.3f}, {n:.3f}]")

    fs = s3fs.S3FileSystem(anon=True)
    store = s3fs.S3Map(AORC_STORE, s3=fs)
    ds = xr.open_zarr(store, consolidated=True)

    # AORC latitude is ascending; slice low->high then flip to match era5 (y desc).
    sub = ds[PRECIP_VAR].sel(
        longitude=slice(w - BUFFER_DEG, e + BUFFER_DEG),
        latitude=slice(s - BUFFER_DEG, n + BUFFER_DEG),
        time=slice(TSTART, TSTOP),
    )
    sub = sub.rename({"longitude": "x", "latitude": "y"}).sortby("y", ascending=False)
    sub = sub.load()  # pull from S3 before we touch the store again

    da = sub.rename("precip")
    da.attrs.update(
        units="mm",
        long_name="precipitation accumulated per hour",
        note="AORC APCP_surface (kg/m^2 == mm/hr accumulation); use cumulative_input=True",
    )
    out = da.to_dataset()
    out.attrs.update(
        title="NOAA AORC v1.1 hourly precipitation — Hurricane Sandy",
        source=f"s3://{AORC_STORE} ({PRECIP_VAR})",
        crs="EPSG:4326",
    )
    out["x"].attrs.update(units="degrees_east", standard_name="longitude")
    out["y"].attrs.update(units="degrees_north", standard_name="latitude")

    nt, ny, nx = (out.sizes[d] for d in ("time", "y", "x"))
    print(f"clipped: time={nt} y={ny} x={nx}  "
          f"({str(out.time.values[0])[:13]} -> {str(out.time.values[-1])[:13]})")
    print(f"precip [mm/hr]: max={float(da.max()):.2f}  "
          f"domain-mean={float(da.mean()):.3f}  "
          f"total over window (mean cell)={float(da.sum('time').mean()):.1f} mm")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(OUT.suffix + ".tmp")
    out.to_netcdf(tmp)
    os.replace(tmp, OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
