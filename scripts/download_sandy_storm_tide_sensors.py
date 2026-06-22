"""
Download USGS rapid-deployment STORM-TIDE SENSOR water levels inside the NJ model
domain for Hurricane Sandy, and write a hydromt GeoDataset NetCDF for validation.

WHY these matter: every *permanent* gauge in the domain (NOAA Sandy Hook + the two
USGS estuary gauges) failed mid-storm. The USGS Surge-Sensor (SSS) rapid-deployment
units were built to survive and DID capture the peak. The in-domain open-coast unit
at Monmouth Beach (40.372 N, site 7726) recorded from 10-29 22:00 through the peak.

These are *wave* sensors (high-frequency pressure -> water-surface elevation, NAVD88,
GMT), so the raw signal includes wave oscillations. We therefore write two products
per sensor, resampled to 6-min:
  - stormtide_m : 30-min low-pass (centered mean) -> still-water + setup, the series
                  directly comparable to the model `zs`.
  - wavemax_m   : 6-min running max of the raw signal -> the wave-crest envelope
                  (for context; comparable to the highest open-coast HWMs, not to zs).

Data source: USGS STN / Flood Event Viewer (event 24). The continuous series are NOT
in the bulk Instruments.json (data_files=0) — they live as per-instrument .txt files
at Instruments/{id}/Files.json -> Files/{file_id}/item. Datum NAVD88 (GPS), time GMT.

Output schema (hydromt GeoDataset):
  dims:   (time, stations)
  coords: time, stations(instrument_id), lon, lat
  vars:   stormtide_m(time, stations), wavemax_m(time, stations)   [m NAVD88]

Catalog entry to add: `sandy_storm_tide_nj` (GeoDataset).
"""
import io
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import xarray as xr

ROOT = Path(os.environ.get("NJ_ROOT", Path(__file__).resolve().parents[1]))
OUT_DIR = ROOT / "data/gtsm"
OUT = OUT_DIR / "sandy_storm_tide_nj.nc"
STN = "https://stn.wim.usgs.gov/STNServices"
FT_TO_M = 0.3048

# In-domain SSS wave/water-level instruments (open coast, Monmouth Beach, 40.372 N).
# 2257 is the barometric (BP) unit -> skip (air pressure, not water level).
INSTRUMENTS = [2258, 2259]   # SSS-NJ-MON-002WV / 003WV


def fetch_sensor(iid: int):
    """Return (lon, lat, raw_series[m NAVD88]) for one SSS instrument, or None."""
    files = requests.get(f"{STN}/Instruments/{iid}/Files.json", timeout=60).json()
    txts = [f for f in files if str(f.get("name", "")).lower().endswith(".txt")]
    for f in txts:
        r = requests.get(f"{STN}/Files/{f['file_id']}/item", timeout=120)
        if r.status_code != 200 or "date_time_GMT" not in r.text:
            continue
        lat = lon = low_ft = None
        for ln in r.text.splitlines():
            if ln.startswith("# Sensor location latitude"):
                lat = float(ln.split()[-1])
            elif ln.startswith("# Sensor location longitude"):
                lon = float(ln.split()[-1])
            elif "Lowest recordable water elevation" in ln:
                low_ft = float(ln.split()[-2])
        rows = [l.split("\t") for l in r.text.splitlines()
                if l and not l.startswith("#") and l.count("\t") >= 1
                and l.split("\t")[0][:2].isdigit()]
        recs = []
        for c in rows:
            try:
                recs.append((pd.Timestamp(c[0]), float(c[1]) * FT_TO_M))
            except (ValueError, IndexError):
                pass
        if len(recs) > 100:
            s = pd.Series(dict(recs)).sort_index()
            # These sensors are mounted ~9 ft NAVD88 and DE-WATER in wave troughs,
            # reading their recordable floor. Mask floored samples to NaN so the
            # still-water mean uses only genuinely-submerged data (valid near the
            # peak; troughs go NaN when the sensor is out of the water).
            if low_ft is not None:
                s = s.mask(s <= low_ft * FT_TO_M + 0.05)
            return lon, lat, s
    return None


def main():
    print(f"Fetching {len(INSTRUMENTS)} USGS storm-tide sensors (NAVD88) ...")
    stormtide, wavemax, lons, lats, kept = {}, {}, {}, {}, []
    for iid in INSTRUMENTS:
        res = fetch_sensor(iid)
        if res is None:
            print(f"  inst {iid}: no parseable data file"); continue
        lon, lat, s = res
        dt = (s.index[1] - s.index[0]).total_seconds()
        win = max(int(round(1800 / dt)), 1)              # 30-min window for still-water
        st = s.rolling(win, center=True, min_periods=win // 2).mean().resample("6min").mean()
        wm = s.resample("6min").max()
        stormtide[iid], wavemax[iid] = st, wm
        lons[iid], lats[iid] = lon, lat
        kept.append(iid)
        print(f"  inst {iid}: ({lon:.3f},{lat:.3f}) {s.index[0]}..{s.index[-1]} dt~{dt:.0f}s | "
              f"raw peak {s.max():.2f} m, stormtide peak {st.max():.2f} m at {st.idxmax()}")
    if not kept:
        raise SystemExit("No storm-tide sensor data retrieved — keep HWMs as the spatial validation.")

    st_df = pd.concat([stormtide[i] for i in kept], axis=1); st_df.columns = kept
    wm_df = pd.concat([wavemax[i] for i in kept], axis=1).reindex(st_df.index); wm_df.columns = kept
    ds = xr.Dataset(
        {"stormtide_m": (("time", "stations"), st_df.values.astype("float64")),
         "wavemax_m":   (("time", "stations"), wm_df.values.astype("float64"))},
        coords={"time": st_df.index.values, "stations": kept,
                "lon": ("stations", [lons[i] for i in kept]),
                "lat": ("stations", [lats[i] for i in kept])},
        attrs={"title": "USGS storm-tide (SSS) sensors, NJ open coast — Hurricane Sandy",
               "source": f"{STN}/Instruments/{{id}}/Files (event 24, SSS-NJ-MON wave sensors)",
               "datum": "NAVD88", "units": "m",
               "note": "wave sensors: stormtide_m=30-min mean (still water, vs model zs); "
                       "wavemax_m=6-min max (wave-crest envelope, vs highest HWMs). Provisional."},
    )
    for v in ("stormtide_m", "wavemax_m"):
        ds[v].attrs.update(units="m", datum="NAVD88")
    ds["lon"].attrs.update(units="degrees_east"); ds["lat"].attrs.update(units="degrees_north")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(OUT.suffix + ".tmp")
    ds.to_netcdf(tmp); os.replace(tmp, OUT)
    print(f"Wrote {OUT}  ({len(kept)} sensors)")


if __name__ == "__main__":
    main()
