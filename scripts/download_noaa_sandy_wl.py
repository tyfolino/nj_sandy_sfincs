"""
Download observed water levels at NOAA CO-OPS gauges spanning the NJ coast
during Hurricane Sandy and write hydromt_sfincs GeoDataset NetCDFs.

Writes TWO files:
  noaa_sandy_nj.nc          forcing — only gauges with a COMPLETE record over
                            the sim window. This is what the boundary uses.
  noaa_sandy_validation.nc  validation — ALL gauges, including ones that failed
                            mid-storm. For comparing modeled zs vs observed at
                            obs points; NOT safe as boundary forcing.

Why the split: the Sandy Hook gauge (8531680) flooded out and stopped
reporting at 2012-10-29 23:00 — half its record is NaN. Feeding that into
the boundary collapses the forcing on the northern stretch mid-storm (the
boundary cell loses its water level and the domain drains there). The Battery
(8518750, ~5 km north, stayed online, peak 3.42 m) anchors that latitude
instead. Sandy Hook is kept for validation only.

Output schema (both files) matches `gtsm_nj_2012_10_ready.nc`:
  dims:   (time, stations)
  coord:  time, stations, lon(stations), lat(stations)
  var:    waterlevel(time, stations)  [m NAVD88]

Catalog usage after running:
    sf.water_level.create(geodataset="noaa_sandy_nj", buffer=50000)
"""
import os
from pathlib import Path
import requests
import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(os.environ.get("NJ_ROOT", Path(__file__).resolve().parents[1]))
OUT_DIR = ROOT / "data/gtsm"
OUT_FORCING = OUT_DIR / "noaa_sandy_nj.nc"
OUT_VALIDATION = OUT_DIR / "noaa_sandy_validation.nc"

# NOAA CO-OPS stations along NJ + NY Bight, north to south.
# role="forcing"    -> complete record, safe as a boundary source
# role="validation" -> incomplete record (gauge failure), validation use only
STATIONS = [
    {"id": "8518750", "name": "The Battery, NY",   "lon": -74.0142, "lat": 40.7006, "role": "forcing"},
    {"id": "8531680", "name": "Sandy Hook, NJ",    "lon": -74.0091, "lat": 40.4669, "role": "validation"},  # failed 10-29 23:00
    {"id": "8534720", "name": "Atlantic City, NJ", "lon": -74.4181, "lat": 39.3550, "role": "forcing"},
    {"id": "8536110", "name": "Cape May, NJ",      "lon": -74.9600, "lat": 38.9683, "role": "forcing"},
]

# Sandy window — pad either side of landfall (2012-10-29 ~23:30 UTC at Atlantic City).
BEGIN = "20121028"
END   = "20121031"

API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"


def fetch(station_id: str) -> pd.Series:
    """Return hourly water level (m NAVD88) for one station."""
    params = {
        "product":    "hourly_height",
        "application": "nj_sandy_sfincs",
        "begin_date": BEGIN,
        "end_date":   END,
        "datum":      "NAVD",
        "station":    station_id,
        "time_zone":  "gmt",
        "units":      "metric",
        "format":     "json",
    }
    r = requests.get(API, params=params, timeout=30)
    r.raise_for_status()
    j = r.json()
    if "data" not in j:
        raise RuntimeError(f"No data for {station_id}: {j}")
    df = pd.DataFrame(j["data"])
    df["t"] = pd.to_datetime(df["t"])
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    return df.set_index("t")["v"].rename(station_id)


def build_dataset(stations: list[dict], series: dict[str, pd.Series], title: str) -> xr.Dataset:
    """Assemble a (time, stations) GeoDataset from a station subset."""
    df = pd.concat([series[s["id"]] for s in stations], axis=1)
    df.columns = [s["id"] for s in stations]
    ds = xr.Dataset(
        {"waterlevel": (("time", "stations"), df.values.astype("float64"))},
        coords={
            "time":     df.index.values,
            "stations": [int(s["id"]) for s in stations],
            "lon": ("stations", [s["lon"] for s in stations]),
            "lat": ("stations", [s["lat"] for s in stations]),
        },
        attrs={
            "title":  title,
            "source": "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter",
            "datum":  "NAVD88",
            "units":  "m",
        },
    )
    ds["waterlevel"].attrs.update(units="m", datum="NAVD88")
    ds["lon"].attrs.update(units="degrees_east", standard_name="longitude")
    ds["lat"].attrs.update(units="degrees_north", standard_name="latitude")
    return ds


def write_atomic(ds: xr.Dataset, path: Path) -> None:
    """Write to a temp file then os.replace into place.

    netCDF/HDF5 takes an exclusive lock to write, so writing directly fails
    with PermissionError if another process (e.g. a Jupyter kernel that cached
    the file via the data catalog) holds it open. Writing to a temp file and
    atomically renaming sidesteps that — the holder keeps its old inode, new
    readers get the new file.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    ds.to_netcdf(tmp)
    os.replace(tmp, path)


def main():
    print(f"Fetching {len(STATIONS)} NOAA stations for {BEGIN}-{END} ...")
    series = {s["id"]: fetch(s["id"]) for s in STATIONS}
    for s in STATIONS:
        v = series[s["id"]]
        n_valid = int(v.notna().sum())
        complete = n_valid == len(v)
        flag = "" if complete else f"  <- INCOMPLETE ({len(v) - n_valid} NaN), {s['role']}-only"
        print(f"  {s['id']} {s['name']:18s}: n={n_valid}/{len(v)}  peak={v.max():.2f} m NAVD88{flag}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Forcing file: only stations with a complete record. Guard against a
    # station silently degrading in a future re-download.
    forcing = [s for s in STATIONS if s["role"] == "forcing"]
    incomplete = [s for s in forcing if int(series[s["id"]].notna().sum()) != len(series[s["id"]])]
    if incomplete:
        raise RuntimeError(
            f"forcing stations have gaps: {[s['id'] for s in incomplete]} — "
            "inspect before writing the boundary file"
        )
    ds_forcing = build_dataset(
        forcing, series,
        "NOAA CO-OPS hourly water levels (forcing subset) — Hurricane Sandy",
    )
    write_atomic(ds_forcing, OUT_FORCING)
    print(f"Wrote {OUT_FORCING}  ({len(forcing)} stations: "
          f"{', '.join(s['id'] for s in forcing)})")

    # Validation file: all stations, gaps and all.
    ds_val = build_dataset(
        STATIONS, series,
        "NOAA CO-OPS hourly water levels (all gauges, validation) — Hurricane Sandy",
    )
    write_atomic(ds_val, OUT_VALIDATION)
    print(f"Wrote {OUT_VALIDATION}  ({len(STATIONS)} stations, includes incomplete records)")


if __name__ == "__main__":
    main()
