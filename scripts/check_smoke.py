#!/usr/bin/env python
"""Premier-relative smoke gate for a short-window SFINCS/SnapWave arm.

    python scripts/check_smoke.py experiments/<arm>_smoke [--control experiments/faber-waves-premier]

Why this is written the way it is
---------------------------------
The first version of this gate used ABSOLUTE thresholds ("zs must be < 15 m", "no NaN")
and reported three failures on a run that was healthy:

  * ``zs`` reached 70.6 m -> so does the premier (71.1 m). ``zs`` tracks the bed in dry
    cells and ``zb`` maxes at 93.6 m, so a bare magnitude cap is meaningless.
  * ``zs``/``hm0`` were 39-52% non-finite -> that is the dry-cell fill value, and the
    premier's own map is the same.
  * nearshore ``hm0`` looked 1.7-2.3x high -> two separate artefacts: (a) premier cells
    that are INACTIVE in its own wave domain read ~0 and dragged its mean down, and
    (b) the enlarged wave domain needs ~6 h to spin up, which dominated a 13-step mean.

So every check here is relative to a control run, over the SAME time window, on the SAME
cell set, and time-varying quantities are reported per timestep rather than aggregated.
The only absolute checks left are the ones that are genuinely absolute: did the solver
close off, and did it emit an error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import xarray as xr

# Cells are compared only where the CONTROL has a valid wave solution: active interior
# (snapwave_mask == 1, excluding its boundary ring) and above its own depth cut. Comparing
# outside this set is what produced false alarm (a).
CONTROL_ZCUT = -9.0
# Wave spin-up on an enlarged SnapWave domain. Ratios before this are transient, not physics.
WAVE_SPINUP_HOURS = 8.0
# A converged nearshore Hs ratio outside this band is a real signal worth stopping for.
HS_RATIO_BAND = (0.5, 1.5)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("arm", type=Path)
    ap.add_argument("--control", type=Path,
                    default=Path("experiments/faber-waves-premier"))
    ap.add_argument("--spinup-hours", type=float, default=WAVE_SPINUP_HOURS)
    a = ap.parse_args()

    ok = True

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= bool(passed)
        print(f"[{'PASS' if passed else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")

    # ── absolute checks: only the ones that really are absolute ──────────────
    log = (a.arm / "sfincs.log").read_text() if (a.arm / "sfincs.log").exists() else ""
    check("solver closed off cleanly", "Closing off SFINCS" in log)
    bad = [w for w in ("NaN", "Infinity", "ERROR", "error stop", "Segmentation") if w in log]
    check("no error keywords in log", not bad, ",".join(bad))

    if not (a.arm / "sfincs_map.nc").exists():
        check("sfincs_map.nc written", False)
        return 1

    arm = xr.open_dataset(a.arm / "sfincs_map.nc")
    ctl = xr.open_dataset(a.control / "sfincs_map.nc")
    grid = xr.open_dataset(a.control / "sfincs.nc")

    # ── same time window ─────────────────────────────────────────────────────
    t0, t1 = arm.time.values[0], arm.time.values[-1]
    ctlw = ctl.sel(time=slice(t0, t1))
    check("control covers the arm's window",
          ctlw.sizes["time"] == arm.sizes["time"],
          f"control {ctlw.sizes['time']} vs arm {arm.sizes['time']} steps")
    if ctlw.sizes["time"] != arm.sizes["time"]:
        return 1

    # ── same cell set: the control's own valid wave interior ─────────────────
    csw = grid["snapwave_mask"].values
    z = grid["z"].values
    interior = (csw == 1) & (z > CONTROL_ZCUT)
    print(f"       comparing on {int(interior.sum()):,} cells "
          f"(control wave interior, z > {CONTROL_ZCUT} m)")

    # ── convergence behaviour vs the control ─────────────────────────────────
    def iters(p: Path) -> list[int]:
        out, n, seen = [], 0, False
        for ln in (p / "sfincs.log").read_text().splitlines():
            if "Computing SnapWave" in ln:
                if seen:
                    out.append(n)
                n, seen = 0, True
            elif "iteration" in ln:
                n += 1
        return out + ([n] if seen else [])

    ia, ic = iters(a.arm), iters(a.control)
    if ia and ic:
        check("no call hit the iteration cap (niter=100)", max(ia) < 100,
              f"max {max(ia)} vs control {max(ic)}")
        check("mean iterations/call comparable to control",
              abs(np.mean(ia) - np.mean(ic)) < 3.0,
              f"{np.mean(ia):.1f} vs control {np.mean(ic):.1f}")

    # ── non-finite fraction: relative, since NaN is the dry-cell fill ────────
    for v in ("zs", "hm0"):
        if v not in arm or v not in ctlw:
            continue
        fa = float(np.mean(~np.isfinite(arm[v].values[:, interior])))
        fc = float(np.mean(~np.isfinite(ctlw[v].values[:, interior])))
        check(f"{v}: non-finite fraction not worse than control",
              fa <= fc + 0.10, f"arm {100*fa:.1f}% vs control {100*fc:.1f}%")

    # ── magnitude: relative to the control's own range, not an invented cap ──
    for v in ("zs", "hm0"):
        if v not in arm or v not in ctlw:
            continue
        ma = float(np.nanmax(arm[v].values[:, interior]))
        mc = float(np.nanmax(ctlw[v].values[:, interior]))
        check(f"{v}: max within 2x the control's max",
              ma < max(2.0 * mc, mc + 1.0), f"arm {ma:.2f} vs control {mc:.2f}")

    # ── Hs ratio PER TIMESTEP, after spin-up ────────────────────────────────
    if "hm0" in arm and "hm0" in ctlw:
        A = ctlw["hm0"].values[:, interior]
        B = arm["hm0"].values[:, interior]
        hrs = (arm.time.values - arm.time.values[0]) / np.timedelta64(1, "h")
        print("\n       hm0 interior mean per timestep (control -> arm, ratio):")
        ratios = []
        for i, h in enumerate(hrs):
            ca, cb = np.nanmean(A[i]), np.nanmean(B[i])
            r = cb / ca if ca > 0 else np.nan
            tag = "spin-up" if h < a.spinup_hours else ""
            if h >= a.spinup_hours and np.isfinite(r):
                ratios.append(r)
            print(f"         +{h:5.1f} h   {ca:6.3f} -> {cb:6.3f}   x{r:5.2f}  {tag}")
        if ratios:
            med = float(np.median(ratios))
            lo, hi = HS_RATIO_BAND
            check(f"converged nearshore Hs ratio in [{lo}, {hi}]", lo <= med <= hi,
                  f"median x{med:.2f} over {len(ratios)} post-spin-up steps")
        else:
            print(f"       (window shorter than {a.spinup_hours} h — "
                  "no converged steps; Hs ratio NOT assessed)")

    print("\n" + ("SMOKE PASSED — safe to launch the full run"
                  if ok else "*** SMOKE FAILED — do NOT launch the full run ***"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
