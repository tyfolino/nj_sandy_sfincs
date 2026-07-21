"""
Build a Sandy Hook tidal-window BLEND boundary source: noaa_sandy_nj_shblend.nc.

WHY. On the premier the modeled pre-storm tide peaks late (Sandy Hook +18 min)
because the northern boundary is interpolated from The Battery (8518750), which
carries NY-Harbor phase. The Sandy Hook gauge (8531680) has the correct open-coast
tidal phase but FAILED mid-storm (NaN after 2012-10-29 23:00), so it cannot be a
raw boundary source — feeding its NaN tail collapses the northern boundary at the
surge crest (see scripts/download_noaa_sandy_wl.py).

WHAT. Synthesise a COMPLETE station 8531680 that is the real Sandy Hook tide for
the pre-storm window and hands over to the (complete) Battery for the surge crest:

    t <= splice : real Sandy Hook              (correct coastal tidal PHASE)
    t >  splice : Battery + offset, offset      (correct surge AMPLITUDE at crest)
                  tapered 1->0 over TAPER_H h

  * splice = 2012-10-29 23:00  (Sandy Hook's last good sample — the same constant
    hardcoded as `gauge_end` in nj_sfincs/validate.py)
  * offset = SH(splice) - Battery(splice)  removes the level discontinuity at the
    hand-off; tapering it to 0 lets the crest keep Battery's TRUE amplitude. Both
    series are NAVD88 so the offset is small; the taper mainly smooths the minor
    tidal-phase kink in the surge-dominated tail.

The output carries all four stations (Battery unchanged, synthetic Sandy Hook,
Atlantic City, Cape May); near the domain's north edge the synthetic Sandy Hook is
the nearest gauge, so water_level.create weights it there → SH phase pre-storm,
Battery amplitude at the crest. Every value is finite (asserted).

Run:  NJ_ROOT=$PWD ./micromamba/envs/sfincs/bin/python scripts/build_sandy_hook_blend.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))
from download_noaa_sandy_wl import (  # noqa: E402  (reuse the exact writers/schema)
    OUT_DIR,
    OUT_VALIDATION,
    STATIONS,
    build_dataset,
    write_atomic,
)

OUT_BLEND = OUT_DIR / "noaa_sandy_nj_shblend.nc"

SH_ID = "8531680"      # Sandy Hook (the station we synthesise)
BATTERY_ID = "8518750"  # the complete northern anchor we hand over to
SPLICE = pd.Timestamp("2012-10-29 23:00")  # Sandy Hook's last good sample
# Decay the hand-off offset to 0 over exactly the rising limb from the splice to
# the Battery crest (Oct 30 01:00, 2 h later): the transition is smoothed across
# the limb yet the crest gets Battery's TRUE amplitude (a 3 h taper still carried
# ~0.33 weight at the crest and inflated it +0.06 m).
TAPER_H = 2.0


def main() -> None:
    if not OUT_VALIDATION.exists():
        raise SystemExit(
            f"{OUT_VALIDATION} not found — run scripts/download_noaa_sandy_wl.py first"
        )
    val = xr.open_dataset(str(OUT_VALIDATION))
    wl = val["waterlevel"]

    def series(sid: str) -> pd.Series:
        return wl.sel(stations=int(sid)).to_series()

    sh = series(SH_ID)
    bat = series(BATTERY_ID)
    if sh.index.tz is not None:  # normalise to tz-naive to match SPLICE
        sh.index = sh.index.tz_localize(None)
        bat.index = bat.index.tz_localize(None)

    # Sanity: Sandy Hook must actually be gappy after the splice, Battery complete.
    if not np.isfinite(sh.loc[:SPLICE].to_numpy()).all():
        raise SystemExit("Sandy Hook has NaNs BEFORE the splice — inspect the record")
    if not np.isfinite(bat.to_numpy()).all():
        raise SystemExit("Battery record has gaps — cannot anchor the crest")
    if SPLICE not in sh.index:
        raise SystemExit(f"splice time {SPLICE} not on the record's time grid")

    offset = float(sh.loc[SPLICE] - bat.loc[SPLICE])

    t = sh.index
    hours_after = (t - SPLICE) / pd.Timedelta("1h")
    taper = np.clip(1.0 - hours_after / TAPER_H, 0.0, 1.0)  # 1 at splice → 0 after TAPER_H
    tail = bat.to_numpy() + offset * taper

    blended = np.where(t <= SPLICE, sh.to_numpy(), tail).astype("float64")
    if not np.isfinite(blended).all():
        raise SystemExit("blended Sandy Hook series still has NaNs — aborting")

    # Assemble all four stations; only 8531680 is synthetic, the rest are the raw
    # validation records. Reuse the download script's station metadata + schema.
    ser = {s["id"]: series(s["id"]) for s in STATIONS if s["id"] != SH_ID}
    for k in ser:
        if ser[k].index.tz is not None:
            ser[k].index = ser[k].index.tz_localize(None)
    ser[SH_ID] = pd.Series(blended, index=t, name=SH_ID)

    ds = build_dataset(
        STATIONS, ser,
        "NOAA CO-OPS hourly water levels — Sandy Hook tidal-window BLEND "
        "(8531680 = real SH tide → Battery surge crest) — Hurricane Sandy",
    )
    ds.attrs["blend"] = (
        f"station {SH_ID}: real Sandy Hook for t<={SPLICE}, then Battery+offset "
        f"(offset={offset:+.3f} m) tapered to 0 over {TAPER_H} h"
    )
    write_atomic(ds, OUT_BLEND)

    n_pre = int((t <= SPLICE).sum())
    print(f"Wrote {OUT_BLEND}  ({len(STATIONS)} stations)")
    print(f"  splice = {SPLICE}  ({n_pre} pre-storm SH samples kept, "
          f"{len(t) - n_pre} tail samples from Battery)")
    print(f"  hand-off offset SH-Battery = {offset:+.3f} m (tapered over {TAPER_H} h)")
    print(f"  blended peak = {blended.max():.2f} m  (Battery peak = {bat.max():.2f} m, "
          f"SH last-good = {sh.loc[SPLICE]:.2f} m)")
    print(f"  finite: {np.isfinite(blended).all()}")


if __name__ == "__main__":
    main()
