"""
Download observed wave parameters at NDBC buoy 44025 during Hurricane Sandy
and write a hydromt_sfincs SnapWave GeoDataset NetCDF.

Buoy 44025 ("Long Island - 30 NM South of Islip, NY", 40.251 N, 73.164 W) is
the closest open-water NDBC buoy with a complete Sandy record. It sits ~70 km
east of the model domain — far enough that SnapWave's default 25 km buffer
won't reach it, so use a wide buffer in snapwave_boundary.create (see below).

Output schema (hydromt_sfincs SnapWave GeoDataset):
  dims:   (time, stations)
  coord:  time, stations, lon(stations), lat(stations)
  vars:   hs(time,stations)  significant wave height [m]
          tp(time,stations)  peak wave period [s]
          wd(time,stations)  wave direction [deg from N, clockwise, coming-from]
          ds(time,stations)  directional spreading [deg]  -- CONSTANT, see note

Note on `ds`: NDBC's standard meteorological file has no directional-spreading
field, so `ds` is set to a constant DIR_SPREAD (default 30 deg, typical for
storm seas). If SnapWave results look too focused/diffuse, this is the knob.

Note on `wd`: NDBC MWD is the direction waves come FROM, degrees clockwise from
true North. SnapWave's `wd` uses the same convention, so it maps directly. If a
future check shows waves arriving from the wrong quadrant, flip here.

Catalog usage after running:
    sf.snapwave_boundary.create(geodataset="ndbc_sandy_44025", buffer=100000)

Source: https://www.ndbc.noaa.gov/  (historical standard meteorological data)
"""
import gzip
import io
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import xarray as xr

ROOT = Path(os.environ.get("NJ_ROOT", Path(__file__).resolve().parents[1]))
OUT = ROOT / "data/waves/ndbc_sandy_44025.nc"

STATION = {"id": "44025", "name": "Long Island 30NM S of Islip",
           "lon": -73.164, "lat": 40.251}

# Sandy window — same as the NOAA water-level script.
BEGIN = "2012-10-28"
END   = "2012-10-31"

# Directional spreading is not in the NDBC stdmet file — constant fallback.
DIR_SPREAD = 30.0  # degrees

# NDBC historical standard meteorological file (whole year 2012).
URL = ("https://www.ndbc.noaa.gov/view_text_file.php"
       f"?filename={STATION['id']}h2012.txt.gz&dir=data/historical/stdmet/")

# stdmet columns (2012-era format), two header lines both starting with '#'.
COLS = ["YY", "MM", "DD", "hh", "mm", "WDIR", "WSPD", "GST", "WVHT",
        "DPD", "APD", "MWD", "PRES", "ATMP", "WTMP", "DEWP", "VIS", "TIDE"]
# NDBC missing-value sentinels for the fields we use.
MISSING = {"WVHT": 99.0, "DPD": 99.0, "MWD": 999.0}


def fetch() -> pd.DataFrame:
    """Download + parse the 2012 stdmet file, return the Sandy-window slice."""
    r = requests.get(URL, timeout=60)
    r.raise_for_status()
    # view_text_file.php usually serves plain text despite the .gz filename;
    # handle both by sniffing the gzip magic bytes.
    raw = r.content
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    df = pd.read_csv(
        io.BytesIO(raw), sep=r"\s+", comment="#", names=COLS, header=None,
    )
    df["time"] = pd.to_datetime(df[["YY", "MM", "DD", "hh", "mm"]].rename(
        columns={"YY": "year", "MM": "month", "DD": "day",
                 "hh": "hour", "mm": "minute"}))
    df = df.set_index("time").sort_index()
    df = df.loc[BEGIN:END, ["WVHT", "DPD", "MWD"]]
    # Replace NDBC sentinels with NaN.
    for col, sentinel in MISSING.items():
        df[col] = df[col].where(df[col] != sentinel)
    return df


def main():
    print(f"Fetching NDBC {STATION['id']} stdmet for {BEGIN}..{END} ...")
    df = fetch()
    n = len(df)
    print(f"  {n} records  "
          f"WVHT n={df['WVHT'].notna().sum()} peak={df['WVHT'].max():.2f} m  "
          f"DPD n={df['DPD'].notna().sum()} peak={df['DPD'].max():.1f} s  "
          f"MWD n={df['MWD'].notna().sum()}")
    if df["WVHT"].isna().any() or df["DPD"].isna().any() or df["MWD"].isna().any():
        # SnapWave needs gap-free forcing; interpolate small gaps, warn if large.
        gap = int(df[["WVHT", "DPD", "MWD"]].isna().any(axis=1).sum())
        print(f"  WARNING: {gap} record(s) with a NaN in hs/tp/wd — interpolating")
        df = df.interpolate(method="time", limit_direction="both")

    # (time, stations=1) arrays
    t = df.index.values
    hs = df["WVHT"].values[:, None]
    tp = df["DPD"].values[:, None]
    wd = df["MWD"].values[:, None]
    ds_ = np.full_like(hs, DIR_SPREAD)

    out = xr.Dataset(
        {
            "hs": (("time", "stations"), hs),
            "tp": (("time", "stations"), tp),
            "wd": (("time", "stations"), wd),
            "ds": (("time", "stations"), ds_),
        },
        coords={
            "time": t,
            "stations": [int(STATION["id"])],
            "lon": ("stations", [STATION["lon"]]),
            "lat": ("stations", [STATION["lat"]]),
        },
        attrs={
            "title": f"NDBC {STATION['id']} wave parameters — Hurricane Sandy",
            "source": "https://www.ndbc.noaa.gov/ historical stdmet",
            "note": f"ds is constant {DIR_SPREAD} deg (not in NDBC stdmet)",
        },
    )
    out["hs"].attrs.update(units="m", long_name="significant wave height")
    out["tp"].attrs.update(units="s", long_name="peak wave period")
    out["wd"].attrs.update(units="degrees", long_name="wave direction (from, cw from N)")
    out["ds"].attrs.update(units="degrees", long_name="directional spreading")
    out["lon"].attrs.update(units="degrees_east", standard_name="longitude")
    out["lat"].attrs.update(units="degrees_north", standard_name="latitude")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(OUT.suffix + ".tmp")
    out.to_netcdf(tmp)
    os.replace(tmp, OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
