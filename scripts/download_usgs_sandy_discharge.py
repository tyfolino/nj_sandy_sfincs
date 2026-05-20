"""
Download observed river discharge at USGS NWIS gauges feeding the NJ model
domain during Hurricane Sandy and write a hydromt_sfincs GeoDataset NetCDF.

Two coastal rivers enter the active SFINCS domain and have a gauged record:

  Shark River      -> Shark River estuary / inlet (Belmar). Gauge 01407705
                      "Shark River near Neptune City" sits just W of the domain.
  Navesink/        -> Shrewsbury-Navesink estuary into Sandy Hook Bay. Gauge
  Shrewsbury          01407500 "Swimming River near Red Bank" drains the
                      Navesink headwaters.

Only DAILY-mean discharge (parameter 00060, statistic 00003) is archived for
these small gauges in 2012 — instantaneous (IV) values are not available that
far back. Daily resolution is adequate here: SFINCS interpolates the `dis`
series, and these are small flashy coastal-plain streams whose discharge
(Sandy peaks ~3.5 and ~7.9 m3/s) is a minor compound contributor next to the
multi-metre surge. We pad one day either side so the sim window is bracketed.

IMPORTANT — src placement vs gauge location:
  The point coords written here are NOT the gauge coords. They are the cell
  where each river *enters the active model domain* (a wet estuary cell,
  verified against model/gis/{mask,dep}.tif). The gauge is upstream; we neglect
  the small ungauged drainage between gauge and inflow, and (for the Navesink)
  the Swimming River gauge captures only part of the system — both
  under-estimates, acceptable for a first-pass compound run.

Output schema (hydromt_sfincs GeoDataset). NOTE the location dim is `index`,
not `stations`: discharge_points.create() reads `da.vector.index_dim` and feeds
it back to GeoDataset.from_gdf, which assumes the conventional `index` name —
a `stations` dim raises "Index dimension stations not found in data_vars".
  dims:   (time, index)
  coords: time, index, lon(index), lat(index)
  var:    discharge(time, index)  [m3/s]

Catalog usage after running:
    sf.discharge_points.create(geodataset="usgs_sandy_discharge", merge=False)
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import xarray as xr

OUT_DIR = Path("/home/zagreus/nj_sandy_sfincs/data/discharge")
OUT = OUT_DIR / "usgs_sandy_discharge.nc"

CFS_TO_CMS = 0.0283168466

# Pad either side of the 2012-10-28..31 sim window so it is fully bracketed.
BEGIN = "2012-10-27"
END = "2012-11-01"

API = "https://waterservices.usgs.gov/nwis/dv/"

# site = USGS gauge id; (src_lat, src_lon) = inflow cell into the ACTIVE domain
# (wet estuary cell, NOT the gauge location — see module docstring).
STATIONS = [
    {"id": "01407705", "name": "Shark River nr Neptune City",
     "src_lon": -74.035, "src_lat": 40.195},
    {"id": "01407500", "name": "Swimming River nr Red Bank (Navesink)",
     "src_lon": -74.045, "src_lat": 40.370},
]


def fetch(site_id: str) -> pd.Series:
    """Return daily-mean discharge (m3/s) for one gauge over the padded window."""
    params = {
        "format": "rdb",
        "sites": site_id,
        "parameterCd": "00060",   # discharge
        "statCd": "00003",        # daily mean
        "startDT": BEGIN,
        "endDT": END,
    }
    r = requests.get(API, params=params, timeout=30)
    r.raise_for_status()
    rows = [ln.split("\t") for ln in r.text.splitlines()
            if ln and not ln.startswith("#")]
    header = rows[0]
    # discharge column is the 00060_00003 value; date is 'datetime'.
    dt_i = header.index("datetime")
    val_i = next(i for i, h in enumerate(header) if h.endswith("_00060_00003"))
    recs = [(pd.Timestamp(row[dt_i]), float(row[val_i]))
            for row in rows[2:] if len(row) > val_i and row[val_i] not in ("", "Ice")]
    s = pd.Series(dict(recs)).sort_index() * CFS_TO_CMS
    return s.rename(site_id)


def main():
    print(f"Fetching {len(STATIONS)} USGS gauges (daily discharge) {BEGIN}..{END} ...")
    series = {st["id"]: fetch(st["id"]) for st in STATIONS}
    for st in STATIONS:
        s = series[st["id"]]
        print(f"  {st['id']} {st['name']:38s}: n={len(s)}  "
              f"peak={s.max():.2f} m3/s on {s.idxmax().date()}")

    df = pd.concat([series[st["id"]] for st in STATIONS], axis=1)
    df.columns = [st["id"] for st in STATIONS]

    ds = xr.Dataset(
        {"discharge": (("time", "index"), df.values.astype("float64"))},
        coords={
            "time": df.index.values,
            "index": [int(st["id"]) for st in STATIONS],
            "lon": ("index", [st["src_lon"] for st in STATIONS]),
            "lat": ("index", [st["src_lat"] for st in STATIONS]),
        },
        attrs={
            "title": "USGS daily-mean river discharge at domain inflows — Hurricane Sandy",
            "source": "https://waterservices.usgs.gov/nwis/dv/ (00060/00003)",
            "units": "m3/s",
            "note": "point coords are the model-domain inflow cells, not the gauge sites",
        },
    )
    ds["discharge"].attrs.update(units="m3/s", long_name="river discharge")
    ds["lon"].attrs.update(units="degrees_east", standard_name="longitude")
    ds["lat"].attrs.update(units="degrees_north", standard_name="latitude")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(OUT.suffix + ".tmp")
    ds.to_netcdf(tmp)
    os.replace(tmp, OUT)
    print(f"Wrote {OUT}  ({len(STATIONS)} src points)")


if __name__ == "__main__":
    main()
