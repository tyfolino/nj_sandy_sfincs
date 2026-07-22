"""Composite boundary forcing v2 — local TIDE, spatially interpolated SURGE (2026-07-22).

WHY v2 EXISTS
-------------
v1 (``build_noaa_composite.py``) fixed the tidal phase by adding Sandy Hook as a boundary
support point carrying its own harmonic tide plus **the Battery's NTR, unscaled**. It worked
on phase (Sandy Hook lag 17.6 -> 7.8 min, Shrewsbury 36.9 -> 25.5) and failed on level:

    HWM bias    +0.318 -> +0.732 m        HWM within 0.5 m   74% -> 21%
    HWM RMSE     0.480 ->  0.813 m        Shrewsbury gauge   -0.10 -> +0.25 m
    SSS 2258 Sea Bright (obs 3.465)  premier 3.650 (+0.19) -> composite 4.006 (+0.54)

The cause was NOT the extra node. It was the *level* that node carried. Transplanting the
Battery's surge to Sandy Hook keeps a peak (~3.39 m) that was amplified by the New York
Harbor funnel, and inserting it into the 3.44 -> 1.92 m Battery->Atlantic City baseline
lifted the whole interpolated mid-coast by +0.20..+0.23 m at the HWM latitudes.

THE v2 CONSTRUCTION
-------------------
Split the two halves by their actual spatial behaviour, which is the real content of the
Wahl/Maduwantha decomposition::

    TIDE   varies sharply in phase over short distances  -> take it LOCALLY (Sandy Hook's
           own NOAA harmonic prediction; it does not need the gauge to have survived)
    NTR    is spatially smooth and slowly varying        -> INTERPOLATE it between the
           flanking gauges, exactly as the boundary already did

So Sandy Hook's series becomes::

    total_SH(t) = tide_SH(t) + [ (1-w)*NTR_Battery(t) + w*NTR_AtlanticCity(t) ]

with ``w`` the position of Sandy Hook along the Battery->Atlantic City chord.

WHY THIS IS THE RIGHT EXPERIMENT
--------------------------------
It has **no fitted parameter** (v1's alternative was to scale the donor NTR by ~0.91 to hit
a target peak, which is calibration, not a diagnostic). And because the inserted NTR *is*
the interpolant of its neighbours, the node lies ON the existing surge line -- adding a
point on a line does not move the line. The storm surge field is therefore left
essentially as the premier had it, and the ONLY thing that changes is the tide, which stops
being interpolated from a harbour gauge 26 km away and takes its correct local phase and
amplitude.

  CAVEAT, stated honestly: "does not move the line" is exact for linear-in-distance
  interpolation along the chord. SFINCS does its own spatial weighting of the support
  points onto boundary cells, so the surge field is *essentially*, not provably bit-for-bit,
  unchanged. Verify after the run by differencing the surge component, not by assuming it.

Run::

    NJ_ROOT=$PWD /tmp/$USER/sfincs/bin/python scripts/build_noaa_composite_v2.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyproj

ROOT = Path(os.environ.get("NJ_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "scripts"))

from build_noaa_composite import _get  # noqa: E402  (same NOAA CO-OPS fetch)
from download_noaa_sandy_wl import build_dataset, write_atomic  # noqa: E402

OUT = ROOT / "data/gtsm/noaa_sandy_composite_v2.nc"

BEGIN, END = "20121027", "20121101"

#: Boundary support points, north to south — same set and same coordinates as v1.
#: ``ntr`` selects how each station's non-tidal residual is obtained:
#:   "own"                 use this station's own observed NTR (identity: tide+(obs-tide)=obs)
#:   ("id_a", "id_b")      interpolate the NTR between two flanking stations
STATIONS = [
    {"id": "8518750", "name": "The Battery, NY",   "lon": -74.0142, "lat": 40.7006,
     "ntr": "own"},
    {"id": "8531680", "name": "Sandy Hook, NJ",    "lon": -74.0091, "lat": 40.4669,
     "ntr": ("8518750", "8534720")},   # gauge failed 10-29 23:00; tide is still exact
    {"id": "8534720", "name": "Atlantic City, NJ", "lon": -74.4181, "lat": 39.3550,
     "ntr": "own"},
    {"id": "8536110", "name": "Cape May, NJ",      "lon": -74.9600, "lat": 38.9683,
     "ntr": "own"},
]

#: Sanity bound on an interpolated NTR: it must still track the recipient's OWN observed NTR
#: over whatever overlap exists, or the "NTR is spatially smooth" premise does not hold here.
MIN_CORR = 0.95

#: Model CRS — weights are computed in projected metres, the space SFINCS interpolates in.
UTM = 32618


def _chord_weight(target: dict, a: dict, b: dict) -> float:
    """Fractional position of ``target`` along the a->b chord, in projected metres.

    Projects the target onto the chord rather than using raw distance, so a station a
    little off the straight line still gets the correct along-shore weight.
    """
    tr = pyproj.Transformer.from_crs(4326, UTM, always_xy=True)
    (ax, ay), (bx, by), (tx, ty) = (tr.transform(s["lon"], s["lat"]) for s in (a, b, target))
    abx, aby = bx - ax, by - ay
    w = ((tx - ax) * abx + (ty - ay) * aby) / (abx * abx + aby * aby)
    return float(np.clip(w, 0.0, 1.0))


def main() -> int:
    print(f"Building composite v2 (local tide + interpolated NTR), {BEGIN}-{END} (6-min)")
    tide, ntr = {}, {}
    for st in STATIONS:
        sid = st["id"]
        tide[sid] = _get("predictions", sid)      # harmonic — always complete
        obs = _get("water_level", sid)            # observed — may die mid-storm
        ntr[sid] = (obs - tide[sid].reindex(obs.index)).dropna()
        span = f"{ntr[sid].index[0]:%m-%d %H:%M} -> {ntr[sid].index[-1]:%m-%d %H:%M}"
        print(f"  {sid} {st['name']:18s} tide n={len(tide[sid]):4d}  "
              f"NTR n={len(ntr[sid]):4d} [{span}]  NTR peak {ntr[sid].max():+.3f} m")

    grid = tide[STATIONS[0]["id"]].index
    by_id = {s["id"]: s for s in STATIONS}

    def _on_grid(s: pd.Series) -> pd.Series:
        return s.reindex(grid.union(s.index)).interpolate("time").reindex(grid).ffill().bfill()

    series = {}
    for st in STATIONS:
        sid = st["id"]
        if st["ntr"] == "own":
            n = _on_grid(ntr[sid])
        else:
            ida, idb = st["ntr"]
            w = _chord_weight(st, by_id[ida], by_id[idb])
            na, nb = _on_grid(ntr[ida]), _on_grid(ntr[idb])
            n = (1.0 - w) * na + w * nb
            print(f"  {sid} NTR interpolated {ida}->{idb}  w={w:.4f}  "
                  f"(peaks {na.max():+.3f} / {nb.max():+.3f} -> {n.max():+.3f} m)")
            # The premise is that NTR is spatially smooth. Test it on the overlap that
            # DOES exist (Sandy Hook's own NTR up to gauge failure) rather than asserting it.
            own = ntr[sid]
            both = own.index.intersection(n.index)
            corr = float(own.reindex(both).corr(n.reindex(both)))
            bias = float((own.reindex(both) - n.reindex(both)).mean())
            print(f"       vs its OWN observed NTR: corr={corr:.4f} over {len(both)} "
                  f"samples, residual bias {bias:+.3f} m")
            if not np.isfinite(corr) or corr < MIN_CORR:
                raise RuntimeError(
                    f"{sid} interpolated NTR correlates only {corr:.3f} with its own "
                    f"(need >= {MIN_CORR}) — the smooth-NTR premise fails here"
                )
        total = tide[sid] + n
        if not np.isfinite(total.values).all():
            raise RuntimeError(f"{sid}: composite has non-finite values")
        series[sid] = total
        print(f"  {sid} composite peak {total.max():+.3f} m NAVD88 at {total.idxmax()}")

    ds = build_dataset(
        STATIONS, series,
        "NOAA CO-OPS composite v2 — local harmonic tide + spatially interpolated NTR — Sandy",
    )
    ds.attrs.update(
        method=("total = local NOAA harmonic prediction + NTR; NTR taken from the station "
                "itself where observed, or interpolated along the chord between the "
                "flanking stations where the gauge failed"),
        ntr_note=("Sandy Hook 8531680 keeps its OWN harmonic tide and takes its NTR as the "
                  "Battery<->Atlantic City interpolant, so the inserted node lies ON the "
                  "existing surge line and the surge field is left as the premier had it. "
                  "v1 transplanted the Battery NTR unscaled, which over-forced the coast "
                  "(+0.54 m at SSS 2258 vs +0.19 m for the premier)."),
        supersedes="noaa_sandy_composite.nc (v1)",
    )
    write_atomic(ds, OUT)
    print(f"\nWrote {OUT}  ({len(STATIONS)} stations incl. Sandy Hook, "
          f"{len(grid)} x 6-min steps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
