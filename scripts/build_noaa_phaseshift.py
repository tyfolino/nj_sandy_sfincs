"""Phase-shifted boundary forcing — 2 support points, tidal TIMING only (2026-07-25).

WHY THIS EXISTS (and why v1/v2 are superseded)
----------------------------------------------
The modelled interior tide peaks late (Sandy Hook +17.6 min on the premier). Both earlier
composite arms "fixed" it by INSERTING Sandy Hook as a third boundary support point:

    premier  2 stations: Battery(40.70)                    Atlantic City(39.36)
    v1 / v2  3 stations: Battery(40.70)  SandyHook(40.47)  Atlantic City(39.36)

v2's justification was that its inserted node lies ON the Battery->AC surge line, so adding
it "does not move the line". That is only half true. The node carries
``tide_SH + interpolated_NTR``: the NTR half IS the interpolant and does lie on the line, but
the TIDE half is deliberately LOCAL, so it does not. The node sits off the line by exactly
``tide_SH - interpolated_tide``, measured at +0.051 m at Shark River's latitude. Feeding that
through a barrier-overwash threshold produced up to +0.5 m in the interior (x8.6 amplification)
and wrecked the HWM score (bias +0.318 -> +0.500). See memory ``project_tidal_phase_lag``.

THE ROOT CAUSE IS PURE INTERPOLATION GEOMETRY
---------------------------------------------
NOAA harmonic tidal phase, measured against Sandy Hook (open coast, + = late)::

    Battery        +24 min      <- a HARBOUR gauge, up in New York Harbor
    Sandy Hook       0 min      (reference)
    Atlantic City  -18 min      <- genuine alongshore propagation, physically CORRECT

Interpolating linearly between Battery(+24) and AC(-18) therefore imposes a tide that is late
everywhere in the north. Predicted lag at Sandy Hook from geometry alone: **+16.7 min**.
Observed in the premier: **+17.6 min**. The phase error is entirely this artifact.

THE FIX
-------
AC is NOT shifted: its -18 min is the real tide wave travelling up the coast and we want to
keep it. Only the Battery is contaminated -- it is a harbour gauge standing in for an
open-coast anchor. So advance ONLY the Battery's TIDAL component to open-coast phase::

    total_Battery(t) = tide_Battery(t + 24 min) + NTR_Battery(t)
                       ^^^^^^^^^^^^^^^^^^^^^^^   ^^^^^^^^^^^^^^^
                       timing corrected          UNTOUCHED

Residual interpolated phase error after the shift: -0.7 to -3.1 min over the whole coast.

WHY THIS IS THE CLEAN EXPERIMENT
--------------------------------
* **2 stations, same coordinates as the premier** -> no inserted node, so nothing can sit off
  the surge line. The v2 failure mode is structurally impossible here.
* **NTR untouched at every station** -> the surge field is bit-identical in construction.
* **Hourly cadence preserved** -> does not reintroduce the 6-min-vs-hourly difference that the
  composites carried (small, +0.008 m mid-coast, but it is not this experiment's variable).
* Amplitude preserved: the Battery keeps its OWN tidal range, only its timing moves.

KNOWN COST, stated rather than hidden: the Battery node also anchors the Raritan Bay lobe
(~760 boundary cells at lat 40.52). Shifting it gives that lobe an open-coast phase, but
Raritan Bay's true tide really is late, like the harbour. That is 2 of 19 HWMs and the
``sandy_hook_bay`` basin bias is small (+0.09). Check that basin when scoring.

Run::

    NJ_ROOT=$PWD /tmp/$USER/sfincs/bin/python scripts/build_noaa_phaseshift.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get("NJ_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "scripts"))

from build_noaa_composite import _get  # noqa: E402  (same NOAA CO-OPS fetch)
from download_noaa_sandy_wl import build_dataset, write_atomic  # noqa: E402

OUT = ROOT / "data/gtsm/noaa_sandy_phaseshift.nc"

#: The premier's own forcing file. We rebuild the SAME stations on the SAME time grid so the
#: only difference reaching SFINCS is the Battery's tidal timing.
SRC = ROOT / "data/gtsm/noaa_sandy_nj.nc"

BEGIN, END = "20121027", "20121101"

#: Minutes to ADVANCE each station's tide. Positive = the station's tide is that many minutes
#: LATE relative to open-coast phase, so we sample the harmonic that far into the future.
#: Battery measured at +24 min vs Sandy Hook by cross-correlation of NOAA harmonics (r=0.9996).
SHIFT_MIN = {
    "8518750": 24.0,   # The Battery — harbour phase, standing in for an open-coast anchor
    "8534720": 0.0,    # Atlantic City — genuine alongshore propagation, leave alone
    "8536110": 0.0,    # Cape May — outside the boundary buffer anyway
}

STATIONS = [
    {"id": "8518750", "name": "The Battery, NY",   "lon": -74.0142, "lat": 40.7006},
    {"id": "8534720", "name": "Atlantic City, NJ", "lon": -74.4181, "lat": 39.3550},
    {"id": "8536110", "name": "Cape May, NJ",      "lon": -74.9600, "lat": 38.9683},
]

#: The shifted total must still reproduce the original at stations with zero shift, exactly.
IDENTITY_TOL = 1e-9


def main() -> int:
    import xarray as xr

    src = xr.open_dataset(SRC)
    grid = pd.to_datetime(src["time"].values)
    src_ids = [str(s) for s in src["stations"].values]
    print(f"Rebuilding {SRC.name} stations {src_ids} on its own {len(grid)}-step "
          f"{int((grid[1]-grid[0]).total_seconds()/60)}-min grid")

    series = {}
    for st in STATIONS:
        sid = st["id"]
        if sid not in src_ids:
            print(f"  {sid} {st['name']:18s} not in source — skipping")
            continue
        shift = SHIFT_MIN[sid]

        tide_6min = _get("predictions", sid)          # harmonic, 6-min, always complete
        obs_src = pd.Series(
            src["waterlevel"].values[:, src_ids.index(sid)], index=grid
        )

        def on(s: pd.Series, at: pd.DatetimeIndex) -> pd.Series:
            """Evaluate a 6-min series at arbitrary times by linear interpolation."""
            u = s.reindex(s.index.union(at)).interpolate("time")
            return u.reindex(at)

        # Decompose the PREMIER's own hourly series, so NTR carries whatever the premier had.
        tide_now = on(tide_6min, grid)
        ntr = obs_src - tide_now.values

        # Advance only the tide: sample the harmonic `shift` minutes into the future.
        tide_shifted = on(tide_6min, grid + pd.Timedelta(minutes=shift))
        total = pd.Series(tide_shifted.values + ntr.values, index=grid)

        if shift == 0.0:
            dmax = float(np.nanmax(np.abs(total.values - obs_src.values)))
            if dmax > IDENTITY_TOL:
                raise RuntimeError(f"{sid}: zero-shift station changed by {dmax:.3e} m")
            print(f"  {sid} {st['name']:18s} shift  +0 min  IDENTITY verified "
                  f"(max|diff| {dmax:.1e} m)")
        else:
            dpk = float(total.max() - obs_src.max())
            tpk_old = obs_src.idxmax()
            tpk_new = total.idxmax()
            print(f"  {sid} {st['name']:18s} shift {shift:+5.0f} min  "
                  f"peak {obs_src.max():.3f} -> {total.max():.3f} m ({dpk:+.3f}), "
                  f"t_peak {tpk_old:%m-%d %H:%M} -> {tpk_new:%m-%d %H:%M}")
            print(f"       tidal range preserved: "
                  f"{tide_now.max()-tide_now.min():.3f} -> "
                  f"{tide_shifted.max()-tide_shifted.min():.3f} m")
            # The NTR must be untouched — that is the whole point of the construction.
            print(f"       NTR peak {ntr.max():+.3f} m (unchanged by construction)")

        if not np.isfinite(total.values).all():
            raise RuntimeError(f"{sid}: shifted series has non-finite values")
        series[sid] = total

    ds = build_dataset(
        [s for s in STATIONS if s["id"] in series], series,
        "NOAA CO-OPS phase-shifted boundary — Battery tide advanced to open-coast phase — Sandy",
    )
    ds.attrs.update(
        method=("2 support points, identical coordinates and time grid to noaa_sandy_nj. "
                "total = tide(t + shift) + NTR(t), per station. Only the Battery is shifted "
                "(+24 min, its harbour phase vs Sandy Hook); Atlantic City's -18 min is real "
                "alongshore propagation and is preserved."),
        shift_minutes=str(SHIFT_MIN),
        supersedes=("noaa_sandy_composite / _v2, which inserted a 3rd support point whose "
                    "TIDE half sat off the Battery->AC surge line by +0.051 m"),
    )
    write_atomic(ds, OUT)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
