"""
Download observed water levels at NOAA CO-OPS gauges spanning the NJ coast
during Hurricane Sandy and write a hydromt_sfincs GeoDataset NetCDF that
can replace the GTSM boundary forcing.

Output schema matches `gtsm_nj_2012_10_ready.nc`:
  dims:   (time, stations)
  coord:  time, stations, lon(stations), lat(stations)
  var:    waterlevel(time, stations)  [m NAVD88]

Catalog usage after running:
    sf.water_level.create(geodataset="noaa_sandy_nj", buffer=50000)

Gauges chosen to bracket the model boundary and capture the alongshore
gradient that's flattened in GTSM (Sandy Hook ~3.9 m vs Atlantic City ~2.8 m).
"""
from pathlib import Path
import requests
import pandas as pd
import xarray as xr

OUT = Path("/home/zagreus/nj_sandy_sfincs/data/gtsm/noaa_sandy_nj.nc")

# NOAA CO-OPS stations along NJ + NY Bight, north to south.
# Verified water-level gauges with NAVD88 datum + 6-min/hourly data through Sandy.
STATIONS = [
    {"id": "8518750", "name": "The Battery, NY",       "lon": -74.0142, "lat": 40.7006},
    {"id": "8531680", "name": "Sandy Hook, NJ",        "lon": -74.0091, "lat": 40.4669},
    {"id": "8534720", "name": "Atlantic City, NJ",     "lon": -74.4181, "lat": 39.3550},
    {"id": "8536110", "name": "Cape May, NJ",          "lon": -74.9600, "lat": 38.9683},
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


def main():
    print(f"Fetching {len(STATIONS)} NOAA stations for {BEGIN}-{END} ...")
    series = {s["id"]: fetch(s["id"]) for s in STATIONS}
    for sid, s in series.items():
        print(f"  {sid}: n={s.notna().sum()}  peak={s.max():.2f} m NAVD88")

    df = pd.concat(series.values(), axis=1)
    df.columns = [s["id"] for s in STATIONS]

    ds = xr.Dataset(
        {"waterlevel": (("time", "stations"), df.values.astype("float64"))},
        coords={
            "time":     df.index.values,
            "stations": [int(s["id"]) for s in STATIONS],
            "lon": ("stations", [s["lon"] for s in STATIONS]),
            "lat": ("stations", [s["lat"] for s in STATIONS]),
        },
        attrs={
            "title":  "NOAA CO-OPS hourly water levels — Hurricane Sandy",
            "source": "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter",
            "datum":  "NAVD88",
            "units":  "m",
        },
    )
    ds["waterlevel"].attrs.update(units="m", datum="NAVD88")
    ds["lon"].attrs.update(units="degrees_east", standard_name="longitude")
    ds["lat"].attrs.update(units="degrees_north", standard_name="latitude")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
