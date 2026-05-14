"""
Download ERA5 hourly 10-m winds and mean sea-level pressure for Hurricane
Sandy (Oct 28-31, 2012) over the NJ + offshore storm-context box.

Dataset: reanalysis-era5-single-levels
DOI:     10.24381/cds.adbb2d47
Docs:    https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels

Prerequisites:
  1. ~/.cdsapirc configured with your CDS personal access token
  2. Terms of use accepted for ERA5 single-levels at cds.climate.copernicus.eu
  3. pip install "cdsapi>=0.7.7"

Output variables (per ERA5 conventions):
  u10  — 10 m u-component of wind   [m s-1]
  v10  — 10 m v-component of wind   [m s-1]
  msl  — mean sea level pressure    [Pa]

Bounding box [North, West, South, East]:
  Wide storm-context box covering Sandy's approach + NJ landfall + post-landfall.
  ERA5 native grid is 0.25° (~25 km).
"""

from pathlib import Path

import cdsapi
import xarray as xr

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "era5"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# [North, West, South, East]
NJ_AREA = [42.0, -76.0, 37.0, -72.0]

client = cdsapi.Client()

request = {
    "product_type": ["reanalysis"],
    "variable": [
        "10m_u_component_of_wind",
        "10m_v_component_of_wind",
        "mean_sea_level_pressure",
    ],
    "year": ["2012"],
    "month": ["10"],
    "day": ["28", "29", "30", "31"],
    "time": [f"{h:02d}:00" for h in range(24)],
    "data_format": "netcdf",
    "download_format": "unarchived",
    "area": NJ_AREA,
}

raw_file = OUTPUT_DIR / "era5_nj_sandy_2012_10_28_31_raw.nc"
print(f"Downloading ERA5 winds + MSLP for Sandy to:\n  {raw_file}")
client.retrieve("reanalysis-era5-single-levels", request, str(raw_file))

# Post-process: rename to hydromt_sfincs conventions.
#   wind10_u / wind10_v  (m/s)   ← u10 / v10
#   press_msl            (Pa)    ← msl
#   time, y, x                   ← valid_time, latitude, longitude
print("Renaming variables to hydromt_sfincs conventions...")
ds = xr.open_dataset(raw_file)
print(f"  raw variables: {list(ds.data_vars)}")
print(f"  raw coords:    {list(ds.coords)}")

rename = {}
for src, dst in [
    ("u10", "wind10_u"),
    ("v10", "wind10_v"),
    ("msl", "press_msl"),
    ("longitude", "x"),
    ("latitude", "y"),
    ("valid_time", "time"),
]:
    if src in ds.variables or src in ds.coords:
        rename[src] = dst
ds = ds.rename(rename)

# Drop ERA5 metadata coords that are not needed (number, expver) if present
for drop in ("number", "expver"):
    if drop in ds.coords or drop in ds.data_vars:
        ds = ds.drop_vars(drop)

out_file = OUTPUT_DIR / "era5_nj_sandy_2012_10_28_31.nc"
ds.to_netcdf(out_file)
print(f"Done — {out_file.name}")
print(f"  variables: {list(ds.data_vars)}")
print(f"  coords:    {list(ds.coords)}")
print(f"  time:      {ds.time.values[0]} → {ds.time.values[-1]}  ({ds.sizes['time']} steps)")
