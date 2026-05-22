"""
Download observed tidal water level at the two USGS NWIS estuary gauges that
sit INSIDE the NJ model domain during Hurricane Sandy, for validation.

  01407770  Shark River at Belmar NJ        (40.186, -74.026)  -> southern domain
  01407600  Shrewsbury River at Sea Bright  (40.366, -73.975)  -> mid-north back-bay

Parameter 72279 = "Tidal elevation, NOS-averaged, NAVD88, feet" -> already NAVD88
(converted to metres here), so it is directly comparable to the model `point_zs`.

IMPORTANT — these records do NOT reach Sandy's peak.
  The instantaneous (uv) record for BOTH gauges stops at 2012-10-28 23:54, ~24 h
  before the storm peak (~10-29 23:00 .. 10-30 01:00 UTC). Every permanent coastal
  gauge in the domain (incl. NOAA Sandy Hook) failed mid-storm. So this product is
  for a PRE-STORM TIDAL check only — does the model reproduce tidal range/phase at
  the open coast (40.37) and the south (40.19)? — NOT for validating the surge peak.
  The post-storm USGS HWMs remain the peak/spatial validation.

Output schema (hydromt GeoDataset, mirrors noaa_sandy_validation.nc):
  dims:   (time, stations)
  coords: time, stations(int site no.), lon(stations), lat(stations)
  var:    waterlevel(time, stations)  [m NAVD88]

Catalog entry to add (data/data_catalog.yml): `usgs_sandy_tidal_nj` (GeoDataset).
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import xarray as xr

OUT_DIR = Path("/home/zagreus/nj_sandy_sfincs/data/gtsm")
OUT = OUT_DIR / "usgs_sandy_tidal_nj.nc"

FT_TO_M = 0.3048
PARM = "72279"            # Tidal elevation, NOS-averaged, NAVD88, feet
BEGIN = "2012-10-27T00:00Z"
END = "2012-10-31T12:00Z"
API = "https://waterservices.usgs.gov/nwis/iv/"

STATIONS = [
    {"id": "01407770", "name": "Shark River at Belmar NJ",       "lon": -74.0261, "lat": 40.1856},
    {"id": "01407600", "name": "Shrewsbury River at Sea Bright", "lon": -73.9747, "lat": 40.3656},
]


def fetch(site_id: str) -> pd.Series:
    """Return instantaneous tidal elevation (m NAVD88) for one gauge."""
    params = {
        "format": "json", "sites": site_id, "parameterCd": PARM,
        "startDT": BEGIN, "endDT": END,
    }
    j = requests.get(API, params=params, timeout=60).json()
    ts = j["value"]["timeSeries"]
    if not ts:
        return pd.Series(dtype="float64", name=site_id)
    t = ts[0]
    nd = float(t["variable"]["noDataValue"])
    recs = [(pd.Timestamp(p["dateTime"]).tz_convert("UTC").tz_localize(None), float(p["value"]))
            for p in t["values"][0]["value"]
            if p["value"] not in (None, "") and float(p["value"]) != nd]
    s = pd.Series(dict(recs)).sort_index() * FT_TO_M
    return s.rename(site_id)


def main():
    print(f"Fetching {len(STATIONS)} USGS tidal gauges (param {PARM}, NAVD88) {BEGIN}..{END} ...")
    series = {st["id"]: fetch(st["id"]) for st in STATIONS}
    for st in STATIONS:
        s = series[st["id"]]
        if len(s):
            print(f"  {st['id']} {st['name']:34s}: n={len(s)}  span {s.index[0]} .. {s.index[-1]}  "
                  f"max={s.max():.2f} m (PRE-STORM tide; record ends before peak)")
        else:
            print(f"  {st['id']} {st['name']:34s}: NO DATA returned")

    # union time index across gauges (records may differ slightly)
    df = pd.concat([series[st["id"]] for st in STATIONS], axis=1)
    df.columns = [st["id"] for st in STATIONS]

    ds = xr.Dataset(
        {"waterlevel": (("time", "stations"), df.values.astype("float64"))},
        coords={
            "time": df.index.values,
            "stations": [int(st["id"]) for st in STATIONS],
            "lon": ("stations", [st["lon"] for st in STATIONS]),
            "lat": ("stations", [st["lat"] for st in STATIONS]),
        },
        attrs={
            "title": "USGS in-domain tidal gauges (NAVD88) — Hurricane Sandy PRE-STORM only",
            "source": "https://waterservices.usgs.gov/nwis/iv/ (parameter 72279)",
            "datum": "NAVD88", "units": "m",
            "note": "uv record ends 2012-10-28 23:54, ~24 h before the storm peak — tidal check only",
        },
    )
    ds["waterlevel"].attrs.update(units="m", datum="NAVD88", long_name="tidal water surface elevation")
    ds["lon"].attrs.update(units="degrees_east", standard_name="longitude")
    ds["lat"].attrs.update(units="degrees_north", standard_name="latitude")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(OUT.suffix + ".tmp")
    ds.to_netcdf(tmp)
    os.replace(tmp, OUT)
    print(f"Wrote {OUT}  ({len(STATIONS)} stations)")


if __name__ == "__main__":
    main()
