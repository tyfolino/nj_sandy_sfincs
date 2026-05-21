"""
Download ERA5 hourly wave parameters for Hurricane Sandy (Oct 28-31, 2012) over
the NJ + offshore box, for spatially-varying parametric wave setup at the SFINCS
boundary (replacing the single NDBC buoy 44025 driver).

Dataset: reanalysis-era5-single-levels (same as the wind/pressure download).
This is the wave input used by Parker et al. (2023) and the Carolinas SnapWave
paper; here we use only Hs and Tp for the Stockdon (2006) setup, but mean wave
direction is kept for a future SnapWave boundary.

Prerequisites: ~/.cdsapirc configured; ERA5 terms accepted; cdsapi installed.

Output variables (renamed to match the NDBC file's convention):
  hs  — significant wave height                 [m]   (swh)
  tp  — peak wave period                        [s]   (pp1d)
  wd  — mean wave direction                      [deg] (mwd)
Coords: time, y, x  (RasterDataset; ERA5 wave grid ~0.5 deg).
"""
from pathlib import Path

import cdsapi
import xarray as xr

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "waves"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# [North, West, South, East] — same wide offshore box as the winds, so we
# capture valid deep-water wave nodes east of the domain (ERA5 masks waves in
# very shallow/coastal cells).
NJ_AREA = [42.0, -76.0, 37.0, -72.0]

client = cdsapi.Client()
request = {
    "product_type": ["reanalysis"],
    "variable": [
        "significant_height_of_combined_wind_waves_and_swell",
        "peak_wave_period",
        "mean_wave_direction",
    ],
    "year": ["2012"],
    "month": ["10"],
    "day": ["28", "29", "30", "31"],
    "time": [f"{h:02d}:00" for h in range(24)],
    "data_format": "netcdf",
    "download_format": "unarchived",
    "area": NJ_AREA,
}

raw = OUTPUT_DIR / "era5_waves_nj_sandy_raw.nc"
print(f"Downloading ERA5 wave params for Sandy to:\n  {raw}")
client.retrieve("reanalysis-era5-single-levels", request, str(raw))

print("Renaming to hs/tp/wd, coords time/y/x ...")
ds = xr.open_dataset(raw)
print(f"  raw variables: {list(ds.data_vars)}")
rename = {}
for src, dst in [
    ("swh", "hs"), ("pp1d", "tp"), ("mwd", "wd"),
    ("longitude", "x"), ("latitude", "y"), ("valid_time", "time"),
]:
    if src in ds.variables or src in ds.coords:
        rename[src] = dst
ds = ds.rename(rename)
for drop in ("number", "expver"):
    if drop in ds.coords or drop in ds.data_vars:
        ds = ds.drop_vars(drop)

out = OUTPUT_DIR / "era5_waves_nj.nc"
ds.to_netcdf(out)
nvalid = int(ds["hs"].isel(time=ds["hs"].argmax(dim=["time", "y", "x"])["time"]).notnull().sum()) \
    if False else int(ds["hs"].notnull().any("time").sum())
print(f"Done — {out.name}")
print(f"  variables: {list(ds.data_vars)}  grid: {dict(ds.sizes)}")
print(f"  hs peak: {float(ds['hs'].max()):.2f} m  tp peak: {float(ds['tp'].max()):.1f} s")
print(f"  ocean nodes with valid hs: {nvalid} of {ds.sizes['y'] * ds.sizes['x']}")
