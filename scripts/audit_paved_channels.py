"""Find every channel the top-priority lidar has PAVED OVER (Workstream L).

THE BUG (2026-07-14). `usace_nj_2010` — the 1 m pre-Sandy topobathy lidar, and the TOP
entry in `DEFAULT_ELEVATION_LIST` — is green (bathymetric) lidar. In clear shallow water it
returns the bed, which is why it earns top billing. But in deep or turbid water it **fails
to penetrate and returns the WATER SURFACE instead**. Those surface returns are ~0 to +2 m,
they look like perfectly ordinary land, and because the tier is ranked first they SHADOW
CUDEM's correct bed underneath. Where that happens across a channel, the channel is sealed.

It sealed Shark River Inlet: the real bed is -4.6 to -10.8 m (eHydro soundings), the lidar
says +0.4 to +2.2 m, CUDEM says -2.2 to -4.5 m and is never consulted — so the entire Shark
River estuary **never floods in any run of this project (peak zs exactly +0.00 m)** while the
ocean 1.8 km away reaches +2.9 m.

THE SCREEN: model bed >= -0.5 m AND CUDEM < -2.0 m.

**THE SCREEN IS NOT A VERDICT, AND A LOOSE ARBITER IS WORSE THAN NONE.** Several candidate
patches lie on the **Sea Bright revetment**, where the 1 m lidar is RIGHT (it resolves the
seawall) and 3 m CUDEM is WRONG (it smears the wall into the water beside it). Carving those
would demolish a real structure the model currently gets right — and the revetment is a knife
edge in this model (storm tide lands ON it; 59-75% overtopped), so flattening it would silently
manufacture flooding.

A first pass at this asked "does an eHydro survey's footprint intersect the patch's bounding
box?" — and it happily proposed carving the revetment, because a *beach-nourishment* survey
("Seabright to Manasquan", type OT) covers the shoreline there. Footprint-intersects-bbox is
not evidence of water.

THE ARBITER USED HERE: **are there actual eHydro SOUNDINGS at the patch cells, and do they say
water?** A sounding is a direct measurement — a boat floated at that spot and measured the bed
beneath it. We download the survey's XYZ point cloud and require, for each patch:

    >= MIN_SOUNDINGS soundings within SEARCH_R metres of the patch's cells, AND
    a median sounded bed below SOUNDED_WATER metres

Only then is the patch REAL WATER that the lidar paved. Anything else is left alone.

Output: reports/paved_channels.csv + the survey list for scripts/download_ehydro_nj.py.

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/audit_paved_channels.py
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyproj
import rasterio
import xarray as xr
from rasterio.warp import transform as rtx
from scipy import ndimage

import nj_sfincs  # noqa: F401
from nj_sfincs.config import ROOT

MODEL = ROOT / "experiments" / "snapwave_tuned_25m" / "sfincs.nc"
CUDEM = ROOT / "data" / "elevation" / "cudem_nj_clip.tif"
CACHE = ROOT / "data" / "elevation" / "ehydro" / "raw"
OUT = ROOT / "reports" / "paved_channels.csv"

BED_LAND = -0.5       # model says (near-)land at or above this ...
CUDEM_WATER = -2.0    # ... but CUDEM says real water below this
MIN_CELLS = 4         # ignore single-cell speckle

# --- the arbiter -------------------------------------------------------------------------
# SEARCH_R must be SMALL. A generous radius is how you talk yourself into carving a seawall:
# a cell sitting on the Sea Bright barrier's bay-side bulkhead is only ~40 m from a 6 m-deep
# navigation channel, so at R=60 m it "has soundings at -6 m" and scores as open water. The
# question is not "is there water near this cell" -- it is "was THIS CELL sounded".
# Cells are 25 m, so a sounding must be inside the cell's own footprint.
SEARCH_R = 15.0        # m: a sounding must be essentially ON the cell
MIN_SOUNDINGS = 5      # fewer than this = the boat never really went there
SOUNDED_WATER = -1.0   # m NAVD88: the soundings must actually say WATER
MIN_CELL_FRAC = 0.50   # ...and at least half the patch's cells must be sounded, so that a
                       # patch riding the EDGE of a channel cannot pass on its wet fringe

FT_TO_M = 0.3048006096012192
MLLW_TO_NAVD88 = -0.50  # nominal, for the audit only; the real tier uses a VDatum field

EHYDRO = ("https://services7.arcgis.com/n1YM8pTrFmm7L4hs/arcgis/rest/services/"
          "eHydro_Survey_Data/FeatureServer/0/query")



def surveys_near(xmin, ymin, xmax, ymax, pad=200.0):
    p = dict(
        where="1=1",
        geometry=f"{xmin - pad},{ymin - pad},{xmax + pad},{ymax + pad}",
        geometryType="esriGeometryEnvelope", inSR="32618",
        spatialRel="esriSpatialRelIntersects",
        outFields="surveyjobidpk,sdsfeaturename,surveydatestart,surveytype,sourcedatalocation",
        returnGeometry="false", f="json", resultRecordCount="200",
    )
    try:
        r = json.load(urllib.request.urlopen(EHYDRO + "?" + urllib.parse.urlencode(p), timeout=60))
    except Exception as e:  # noqa: BLE001
        print(f"  eHydro query failed: {e}")
        return []
    return [f["attributes"] for f in r.get("features", [])]


_XYZ: dict = {}


def soundings(att) -> np.ndarray | None:
    """(x, y, z_NAVD88_m) point cloud for a survey, cached. None if unavailable."""
    sid = att["surveyjobidpk"]
    if sid in _XYZ:
        return _XYZ[sid]
    url = att.get("sourcedatalocation")
    if not url:
        _XYZ[sid] = None
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    zp = CACHE / f"{sid}.ZIP"
    try:
        if not zp.exists():
            urllib.request.urlretrieve(url, zp)
        with zipfile.ZipFile(zp) as z:
            names = [n for n in z.namelist() if n.upper().endswith(".XYZ")]
            if not names:
                _XYZ[sid] = None
                return None
            raw = z.read(names[0]).decode("utf-8", "ignore")
        d = np.array([[float(v) for v in ln.split()[:3]]
                      for ln in raw.splitlines() if len(ln.split()) >= 3])
        t = pyproj.Transformer.from_crs(3424, 32618, always_xy=True)
        x, y = t.transform(d[:, 0], d[:, 1])
        z = d[:, 2] * FT_TO_M + MLLW_TO_NAVD88
        _XYZ[sid] = np.column_stack([x, y, z])
    except Exception as e:  # noqa: BLE001
        print(f"  [{sid}] sounding fetch failed: {e}")
        _XYZ[sid] = None
    return _XYZ[sid]


def main():
    q = xr.open_dataset(MODEL)
    fx, fy = q["mesh2d_face_x"].values, q["mesh2d_face_y"].values
    zb, mask = q["z"].values, q["mask"].values
    act = mask > 0

    with rasterio.open(CUDEM) as d:
        lx, ly = fx[act].tolist(), fy[act].tolist()
        if d.crs.to_epsg() != 32618:
            lx, ly = rtx("EPSG:32618", d.crs, lx, ly)
        cu = np.array([r[0] for r in d.sample(zip(lx, ly))], dtype="float64")
        if d.nodata is not None:
            cu[cu == d.nodata] = np.nan
        cu[cu < -1e5] = np.nan
    cudem = np.full(len(fx), np.nan)
    cudem[act] = cu

    sus = act & (zb >= BED_LAND) & (cudem < CUDEM_WATER)
    print(f"candidate cells: {int(sus.sum())} of {int(act.sum())} active\n")

    gx = (fx[sus] // 100).astype(int)
    gy = (fy[sus] // 100).astype(int)
    grid: dict = {}
    for a, b, i in zip(gx, gy, np.flatnonzero(sus)):
        grid.setdefault((a, b), []).append(i)
    xs = [k[0] for k in grid]
    ys = [k[1] for k in grid]
    x0, y0 = min(xs), min(ys)
    arr = np.zeros((max(xs) - x0 + 3, max(ys) - y0 + 3), bool)
    for (a, b) in grid:
        arr[a - x0 + 1, b - y0 + 1] = True
    lab, n = ndimage.label(arr, structure=np.ones((3, 3)))

    print("patch  cells      centre         gap   soundings AT the patch      verdict")
    print("-" * 100)
    rows = []
    for L in range(1, n + 1):
        cells: list = []
        for (a, b), idx in grid.items():
            if lab[a - x0 + 1, b - y0 + 1] == L:
                cells += idx
        c = np.array(cells)
        if c.size < MIN_CELLS:
            continue
        px, py = fx[c], fy[c]
        atts = surveys_near(px.min(), py.min(), px.max(), py.max())

        # THE ARBITER: was THIS CELL sounded, and did the sounding say water?
        best = dict(n=0, med=np.nan, frac=0.0, sid="", chan="")
        for a in atts:
            pts = soundings(a)
            if pts is None or not len(pts):
                continue
            sel = np.zeros(len(pts), bool)
            n_cell_sounded = 0
            for cx, cy in zip(px, py):
                hit = (np.abs(pts[:, 0] - cx) < SEARCH_R) & (np.abs(pts[:, 1] - cy) < SEARCH_R)
                if hit.any():
                    n_cell_sounded += 1
                sel |= hit
            frac = n_cell_sounded / len(px)
            if frac > best["frac"]:
                best = dict(n=int(sel.sum()),
                            med=float(np.median(pts[sel, 2])) if sel.any() else np.nan,
                            frac=frac, sid=a["surveyjobidpk"],
                            chan=a.get("sdsfeaturename") or "")

        water = (best["n"] >= MIN_SOUNDINGS
                 and best["frac"] >= MIN_CELL_FRAC
                 and best["med"] < SOUNDED_WATER)
        verdict = "CARVE" if water else "LEAVE"
        rows.append(dict(
            patch=L, ncell=int(c.size), x=round(float(px.mean())), y=round(float(py.mean())),
            model_zb=round(float(zb[c].mean()), 2),
            cudem_zb=round(float(np.nanmean(cudem[c])), 2),
            gap_m=round(float(zb[c].mean() - np.nanmean(cudem[c])), 2),
            n_soundings=best["n"], cells_sounded_frac=round(best["frac"], 2),
            sounded_bed_m=round(best["med"], 2) if best["n"] else np.nan,
            channel=best["chan"], survey=best["sid"], verdict=verdict,
        ))
        s = (f"{best['frac'] * 100:3.0f}% cells, {best['n']:5d} pts @ {best['med']:+6.2f} m  "
             f"{best['chan'][:20]:<20s}" if best["n"] else f"{'-- no soundings on these cells --':<52s}")
        print(f" {L:3d}  {c.size:5d}  ({px.mean():7.0f},{py.mean():8.0f}) {rows[-1]['gap_m']:5.2f}  {s} {verdict}")

    df = pd.DataFrame(rows).sort_values("ncell", ascending=False)
    OUT.parent.mkdir(exist_ok=True)
    df.to_csv(OUT, index=False)

    carve = df[df.verdict == "CARVE"]
    leave = df[df.verdict == "LEAVE"]
    print("\n" + "=" * 100)
    print(f"CARVE : {len(carve):2d} patches, {int(carve.ncell.sum()):4d} cells — "
          f"a boat sounded WATER at these cells; the lidar paved them over")
    print(f"LEAVE : {len(leave):2d} patches, {int(leave.ncell.sum()):4d} cells — "
          f"no soundings say water here. Treat as REAL STRUCTURE. Do not carve.")
    print("=" * 100)
    if len(carve):
        # The survey that ARBITRATED is whichever had the densest coverage — usually a modern
        # multibeam. That is right for deciding "is this water", but WRONG for the mosaic: we
        # are modelling 2012, so pick the Condition Survey nearest to Sandy for each channel.
        print("\nSURVEYS TO MOSAIC (feed to scripts/download_ehydro_nj.py):")
        print("  (arbitration used the densest survey; the MOSAIC uses the CS nearest 2012)")
        for chan, g in carve.groupby("channel"):
            x0, x1 = g.x.min(), g.x.max()
            y0, y1 = g.y.min(), g.y.max()
            atts = surveys_near(x0, y0, x1, y1, pad=500.0)
            same = [a for a in atts if (a.get("sdsfeaturename") or "") == chan]
            cs = [a for a in same if a.get("surveytype") == "CS"] or same
            def yr(a):
                t = a.get("surveydatestart")
                return int(str(np.datetime64(int(t) // 1000, "s"))[:4]) if t else 9999
            pick = min(cs, key=lambda a: abs(yr(a) - 2012)) if cs else None
            if pick:
                print(f"  {pick['surveyjobidpk']:<40s} {chan:<26s} {yr(pick)}  "
                      f"{int(g.ncell.sum()):4d} cells")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
