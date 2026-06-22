"""
Download USGS High Water Marks (HWMs) for Hurricane Sandy within the NJ model
domain and write a GeoJSON for spatial flood validation.

HWMs are surveyed peak water-surface elevations (mud/seed lines, interior-wall
marks) in NAVD88 — directly comparable to modeled peak water level (zsmax).
Source: USGS STN "Short-Term Network" / Flood Event Viewer. Sandy = event_id 24.
    https://stn.wim.usgs.gov/STNServices/Events/24/HWMs.json

We keep only marks inside the model bbox, with a NAVD88 elevation, and convert
ft -> m. `hwm_quality_id` (1=excellent ≤0.05 ft … 5=poor >0.40 ft) is retained
so the validation cell can weight/filter by survey quality.

Output: data/validation/sandy_hwms.geojson
  columns: hwm_id, elev_m (NAVD88), quality, environment, description, geometry(Point, EPSG:4326)
"""
import os
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import Point

ROOT = Path(os.environ.get("NJ_ROOT", Path(__file__).resolve().parents[1]))
OUT_DIR = ROOT / "data/validation"
OUT = OUT_DIR / "sandy_hwms.geojson"
REGION = ROOT / "data/region.geojson"

EVENT_ID = 24  # 2012 Sandy
API = f"https://stn.wim.usgs.gov/STNServices/Events/{EVENT_ID}/HWMs.json"
FT_TO_M = 0.3048
VDATUM_NAVD88 = 2  # STN vdatum_id: 1=NGVD29, 2=NAVD88


def main():
    w, s, e, n = gpd.read_file(REGION).to_crs(4326).total_bounds
    print(f"domain bbox: lon[{w:.3f}, {e:.3f}] lat[{s:.3f}, {n:.3f}]")

    r = requests.get(API, timeout=60)
    r.raise_for_status()
    hwms = r.json()
    print(f"event {EVENT_ID}: {len(hwms)} HWMs total")

    rows = []
    for x in hwms:
        lon, lat = x.get("longitude_dd"), x.get("latitude_dd")
        elev_ft = x.get("elev_ft")
        if lon is None or lat is None or elev_ft is None:
            continue
        if not (w <= lon <= e and s <= lat <= n):
            continue
        if x.get("vdatum_id") != VDATUM_NAVD88:
            continue
        rows.append({
            "hwm_id": x.get("hwm_id"),
            "elev_m": round(elev_ft * FT_TO_M, 3),
            "quality": x.get("hwm_quality_id"),
            "environment": x.get("hwm_environment"),
            "description": x.get("hwm_locationdescription"),
            "geometry": Point(lon, lat),
        })

    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    print(f"in-domain NAVD88 HWMs: {len(gdf)}  "
          f"elev {gdf['elev_m'].min():.2f}–{gdf['elev_m'].max():.2f} m NAVD88")
    print("quality counts:", gdf["quality"].value_counts().sort_index().to_dict())

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(OUT.suffix + ".tmp")
    gdf.to_file(tmp, driver="GeoJSON")
    os.replace(tmp, OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
