"""Workstream D — analyse the wind-sensitivity (drag) A/B.

Run AFTER the two 25 m wind runs finish (experiments/wind_cd120_25m, wind_cd130_25m).
The apples-to-apples baseline is the completed ``snapwave_tuned_25m`` — SAME 25 m
mesh (both arms must share the mesh; the 12.5 m premier is a different grid).

The plan's "thread-the-needle" test: does more wind
  (1) lift the BAY gauge toward the observed ~3.4 m,
  (2) help the inner Shrewsbury/Navesink (river gauge + estuary HWM basin),
  WITHOUT
  (3) overshooting the already-validated seaward levels (atlantic_oceanfront HWMs)?
We read these on basin-partitioned HWMs + river gauges + tidal range, NOT pooled
HWM bias (which the ocean-front marks dilute — Workstream A2).

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/analyze_d.py
"""

from __future__ import annotations

import numpy as np

from nj_sfincs import validate as V
from nj_sfincs.config import ROOT

EXP = ROOT / "experiments"
BASE = "snapwave_tuned_25m"
RUNS = ["wind_cd120_25m", "wind_cd130_25m"]

# The D-relevant yardsticks pulled from evaluate()'s row, with a friendly label
# and which direction is "toward observations". Bay gauge target ~3.4 m (obs peak
# the dead gauge never saw); estuary should rise toward its crest; ocean-front is
# the overshoot guardrail (already validated — should NOT climb further).
FIELDS = [
    ("gauge_mod_peak_full_m",          "bay gauge peak (model, full)  [obs~3.4]"),
    ("shrewsbury_mod_peak_m",          "Shrewsbury river peak         [crest 2.935]"),
    ("shrewsbury_peak_err_m",          "Shrewsbury deficit vs crest"),
    ("hwm_bias_shrewsbury_navesink_m", "estuary HWM bias  (behind-barrier)"),
    ("hwm_bias_atlantic_oceanfront_m", "ocean-front HWM bias  (overshoot guard)"),
    ("hwm_bias_sandy_hook_bay_m",      "Sandy Hook bay HWM bias"),
    ("tide_mod_range_shrewsbury_01407600_m", "Shrewsbury tidal range  [obs 1.37]"),
    ("tide_mod_range_shark_r_01407770_m",    "Shark R tidal range      [obs 1.82]"),
]


def _row(name: str) -> dict | None:
    d = EXP / name
    if not (d / "sfincs_map.nc").exists():
        print(f"!! {name} not finished (no sfincs_map.nc) — skipping.")
        return None
    print(f"   evaluating {name} ...")
    return V.evaluate(d)


def main() -> None:
    rows = {BASE: _row(BASE)}
    for r in RUNS:
        rows[r] = _row(r)
    if rows[BASE] is None:
        print("baseline snapwave_tuned_25m not available — cannot form the A/B.")
        return

    have = [BASE] + [r for r in RUNS if rows.get(r) is not None]
    print("\n=== Workstream D — wind-drag sensitivity (25 m mesh) ===")
    hdr = f"{'yardstick':<42}" + "".join(f"{h.replace('_25m',''):>16}" for h in have)
    print(hdr)
    base = rows[BASE]
    for key, label in FIELDS:
        cells = [f"{label:<42}"]
        for h in have:
            v = rows[h].get(key, np.nan)
            if h == BASE:
                cells.append(f"{v:>16.3f}" if v == v else f"{'nan':>16}")
            else:
                dv = v - base.get(key, np.nan)
                cells.append(f"{v:>10.3f}{dv:+5.2f}" if v == v else f"{'nan':>16}")
        print("".join(cells))
    print("\n(second number = delta vs snapwave_tuned_25m baseline)")
    print("PASS if: bay peak & estuary HWM rise toward obs AND Shrewsbury deficit "
          "shrinks, WHILE ocean-front bias does NOT overshoot further positive.")


if __name__ == "__main__":
    main()
