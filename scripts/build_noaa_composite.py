"""Tide/surge decomposition boundary forcing — the Wahl recipe, adapted (2026-07-21).

WHY
---
The boundary used ``noaa_sandy_nj``, which EXCLUDES Sandy Hook because that gauge flooded
out at 2012-10-29 23:00. The northern support point therefore became The Battery, up in
New York Harbor — and the Battery's tide runs ~21 min late relative to the real Sandy Hook
tide. The whole model inherited that clock: +18 min at the coast, +38 min up the Shrewsbury.

The fix is to stop treating a gauge record as atomic. A storm tide is::

    total(t) = astronomical tide(t)  +  non-tidal residual (NTR)(t)

and those two halves have completely different needs. The **tide** varies sharply in phase
over short distances, so it must come from the local station — but it does NOT need the
gauge to have survived, because NOAA publishes harmonic predictions computed from decades
of that station's constituents. The **NTR** is spatially smooth and slowly varying, so it
can be borrowed from a neighbour. Measured here: Sandy Hook NTR vs Battery NTR over the
48 h before failure is **corr 0.995 at zero lag**, residual RMS 0.057 m.

This is the decomposition Maduwantha, Wahl et al. use for SFINCS at Gloucester City NJ
(egusphere-2025-1557: UTide harmonics + NTR from the Philadelphia gauge), and Kasaei,
Orton et al. use for Hoboken/NYC (HESS 29:2043 2025: NOAA subtidal levels + ADCIRC tides).
Neither forces from a global model. See [[project_tidal_phase_lag]].

WHAT THIS BUYS, VALIDATED AGAINST REAL SANDY HOOK 6-MIN OBSERVATIONS
--------------------------------------------------------------------
Over 2012-10-27 → 10-29 23:36 (the record we have), pre-storm phase by cross-correlation::

    A  Battery total, as-is (the old forcing)   RMSE 0.147 m   phase error 24 min
    B  SH harmonic tide + Battery NTR  <-- THIS RMSE 0.103 m   phase error  0 min
    C  SH harmonic tide alone                   RMSE 0.913 m   phase error  6 min
    D  Battery harmonic tide alone              RMSE 0.922 m   phase error 30 min

C and D isolate the cause: the phase error is **entirely in the tide**. So swapping in the
correct tide and leaving the surge field alone zeroes it, and improves RMSE at the same time.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
Sandy Hook's NTR is only observed to 10-29 23:00 (+2.34 m, still rising); the peak lands
~2 h later. A least-squares fit says SH_NTR = 1.1122 x Battery_NTR, which would put the SH
surge peak at +3.10 m — above the Battery's own +2.79 m. **We do not do that.** It
extrapolates a fitted ratio ~33% beyond the range it was fitted on, straight through the
crest that sets every flood metric, with no way to check it. The unscaled Battery NTR is
used instead.

The honest cost: unscaled, the NTR runs **~0.10 m low at Sandy Hook** (bias -0.105 m over
the validated window). That is a conservative under-statement of surge magnitude, not a
timing error, and it is a number we can quote rather than a guess we cannot. If a future
independent source (a nearby STN sensor, a surveyed crest) pins the true SH surge peak,
revisit ``NTR_DONOR_SCALE``.

Run::

    NJ_ROOT=$PWD micromamba/envs/sfincs/bin/python scripts/build_noaa_composite.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(os.environ.get("NJ_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "scripts"))

from download_noaa_sandy_wl import (  # noqa: E402  (reuse schema + atomic write)
    API,
    build_dataset,
    write_atomic,
)

OUT = ROOT / "data/gtsm/noaa_sandy_composite.nc"

# Padded either side of the sim window so hydromt has margin to interpolate onto.
BEGIN, END = "20121027", "20121101"

#: Boundary support points, north to south. ``ntr_from`` names the station whose NTR is
#: used; a station normally supplies its own. Sandy Hook borrows the Battery's because its
#: own record dies mid-storm — but it keeps its OWN tide, which is the entire point.
STATIONS = [
    {"id": "8518750", "name": "The Battery, NY",   "lon": -74.0142, "lat": 40.7006,
     "ntr_from": "8518750"},
    {"id": "8531680", "name": "Sandy Hook, NJ",    "lon": -74.0091, "lat": 40.4669,
     "ntr_from": "8518750"},   # gauge failed 10-29 23:00; tide is still exact
    {"id": "8534720", "name": "Atlantic City, NJ", "lon": -74.4181, "lat": 39.3550,
     "ntr_from": "8534720"},
    {"id": "8536110", "name": "Cape May, NJ",      "lon": -74.9600, "lat": 38.9683,
     "ntr_from": "8536110"},
]

#: Scale on a borrowed NTR. 1.0 = use the donor's surge unchanged. See the module docstring
#: for why this is NOT the least-squares 1.1122 — that value extrapolates past its own
#: fitting range through the storm crest.
NTR_DONOR_SCALE = 1.0

#: Sanity bound: a borrowed NTR must correlate at least this well with the recipient's own
#: NTR over whatever overlap exists. Below this, borrowing is not defensible — fail loudly.
MIN_DONOR_CORR = 0.95


def _get(product: str, station: str) -> pd.Series:
    """One NOAA CO-OPS 6-min series (m NAVD88), indexed by UTC timestamp."""
    r = requests.get(API, params={
        "product": product, "application": "nj_sandy_sfincs",
        "begin_date": BEGIN, "end_date": END, "datum": "NAVD",
        "station": station, "time_zone": "gmt", "units": "metric", "format": "json",
    }, timeout=120)
    r.raise_for_status()
    payload = r.json()
    key = "predictions" if product == "predictions" else "data"
    if key not in payload:
        raise RuntimeError(f"{station}/{product}: {payload.get('error', payload)}")
    s = pd.Series({pd.Timestamp(d["t"]): float(d["v"])
                   for d in payload[key] if d.get("v") not in ("", "-", None)})
    return s.sort_index()


def main() -> int:
    print(f"Building tide+NTR composite forcing, {BEGIN}-{END} (6-min)")
    tide, ntr = {}, {}
    for st in STATIONS:
        sid = st["id"]
        tide[sid] = _get("predictions", sid)          # harmonic — always complete
        obs = _get("water_level", sid)                # observed — may die mid-storm
        ntr[sid] = (obs - tide[sid].reindex(obs.index)).dropna()
        span = f"{ntr[sid].index[0]:%m-%d %H:%M} -> {ntr[sid].index[-1]:%m-%d %H:%M}"
        print(f"  {sid} {st['name']:18s} tide n={len(tide[sid]):4d}  "
              f"NTR n={len(ntr[sid]):4d} [{span}]  NTR peak {ntr[sid].max():+.3f} m")

    grid = tide[STATIONS[0]["id"]].index
    series = {}
    for st in STATIONS:
        sid, donor = st["id"], st["ntr_from"]
        n = ntr[donor]
        if donor != sid:
            # Justify the borrow on the overlap that DOES exist, or refuse.
            own = ntr[sid]
            both = own.index.intersection(n.index)
            corr = float(own.reindex(both).corr(n.reindex(both)))
            bias = float((own.reindex(both) - NTR_DONOR_SCALE * n.reindex(both)).mean())
            print(f"  {sid} borrows NTR from {donor}: corr={corr:.4f} over "
                  f"{len(both)} samples, scale={NTR_DONOR_SCALE}, "
                  f"residual bias {bias:+.3f} m")
            if not np.isfinite(corr) or corr < MIN_DONOR_CORR:
                raise RuntimeError(
                    f"{sid} NTR correlates only {corr:.3f} with donor {donor} "
                    f"(need >= {MIN_DONOR_CORR}) — borrowing is not defensible here"
                )
            n = NTR_DONOR_SCALE * n
        # NTR is slowly varying: interpolate onto the tide grid, hold the ends.
        n = n.reindex(grid.union(n.index)).interpolate("time").reindex(grid).ffill().bfill()
        total = tide[sid] + n
        if not np.isfinite(total.values).all():
            raise RuntimeError(f"{sid}: composite has non-finite values")
        series[sid] = total
        print(f"  {sid} composite peak {total.max():+.3f} m NAVD88 at {total.idxmax()}")

    ds = build_dataset(
        STATIONS, series,
        "NOAA CO-OPS tide/NTR composite (harmonic tide + non-tidal residual) — Sandy",
    )
    ds.attrs.update(
        method="total = NOAA harmonic prediction (per station) + non-tidal residual",
        ntr_note=("Sandy Hook 8531680 keeps its OWN harmonic tide but borrows the "
                  "Battery 8518750 NTR (corr 0.995, zero lag) because its gauge failed "
                  "2012-10-29 23:00. Unscaled: ~0.10 m conservative on surge magnitude."),
        ntr_donor_scale=NTR_DONOR_SCALE,
        validation=("vs Sandy Hook 6-min obs 10-27..10-29: RMSE 0.103 m, pre-storm phase "
                    "error 0 min (Battery-total forcing was 0.147 m / 24 min)"),
    )
    write_atomic(ds, OUT)
    print(f"\nWrote {OUT}  ({len(STATIONS)} stations incl. Sandy Hook, "
          f"{len(grid)} x 6-min steps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
