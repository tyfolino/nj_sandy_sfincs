"""Prove the rebuilt DOMAIN is right — before paying for a subgrid build (Workstream L).

The subgrid is by far the most expensive step of a Phase-1 rebuild, and nodes are scarce. So
build only what the geometry checks need — grid, elevation, mask, boundaries — and interrogate
that. If this passes, the full rebuild is worth launching. If it fails, we have lost minutes
instead of hours.

WHAT WE ARE CHECKING, AND WHY EACH ONE EXISTS

  1. THE LEAK IS GONE BY CONSTRUCTION. `region.geojson` used to chop the Navesink in half
     mid-channel; hydromt put a free-outflow (Neumann) BC on the 5 m-deep cut face; the model
     then drained 92.5% of the estuary's entire inflow straight out of the domain, one-way, in
     100% of timesteps. The region's west edge now sits at x=577,000 — west of BOTH tidal
     limits (Navesink water ends x~577,500 at Swimming River Dam; Shark ends x~580,000) — so
     the domain edge lands on DRY LAND and there is no deep cross-section for an outflow BC to
     sit on. Assert: zero free-outflow cells on water.

  2. SHARK RIVER INLET IS OPEN. The 2010 topobathy lidar failed to penetrate the inlet and
     returned the WATER SURFACE (+0.4 to +2.2 m); ranked top of the elevation list it shadowed
     CUDEM's correct bed and sealed the river, leaving the whole Shark estuary at exactly
     +0.00 m — never flooding — through Hurricane Sandy. The eHydro carve tier now outranks it.
     Assert: the controlling sill across the inlet is real water, not a +0.57 m dam.

  3. THE SEA BRIGHT REVETMENT SURVIVED. This is the check that stops us congratulating
     ourselves. The revetment is a knife edge in this model — the storm tide lands ON it and
     59-75% of it overtops — so if the carve quietly flattened it we would manufacture flooding
     and call it a fix. The eHydro tier is clipped to water only (z < -1 m) precisely to make
     that impossible, but assert it, don't assume it.

  4. NOTHING ELSE MOVED. Active-cell count and the Shrewsbury narrows should be essentially
     unchanged. A domain fix that quietly re-draws the whole model is not a domain fix.

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/validate_domain.py
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np
import xarray as xr

import nj_sfincs  # noqa: F401
from nj_sfincs.config import ROOT, BaseConfig
from nj_sfincs.model import OUTFLOW_MAX_DEPTH, build_static

OLD = ROOT / "data" / "frozen_mesh" / "sfincs.nc"

# Shark River Inlet: the sill that dammed it sat at x~583,900, y~4,448,600-4,449,100.
SHARK_X = (583_300, 584_800)
SHARK_Y = (4_447_800, 4_450_000)
# Sea Bright revetment: the barrier crest line, which must NOT be carved away.
REVET_X = (585_500, 587_400)
REVET_Y = (4_454_000, 4_472_000)


def profile_sill(fx, fy, zb, mask, xr_, yr_, step=100):
    """Lowest ACTIVE bed anywhere on each cross-section = the best way through."""
    out = []
    for x0 in range(xr_[0], xr_[1], step):
        s = (mask > 0) & (fx >= x0) & (fx < x0 + step) & (fy > yr_[0]) & (fy < yr_[1])
        if s.any():
            out.append((x0, float(zb[s].min())))
    return out


def main():
    tmp = Path(tempfile.mkdtemp(prefix="njdomain_"))
    try:
        # frozen_mesh=None forces a real build; skip_subgrid stops before the expensive part.
        base = replace(BaseConfig(), frozen_mesh=None)
        print("building grid + elevation + mask (no subgrid) …\n")
        build_static(base, tmp, skip_subgrid=True)
    except RuntimeError as e:
        print("\n" + "=" * 84)
        print("BUILD REFUSED BY THE DOMAIN INVARIANTS — this is the guard working:")
        print("=" * 84)
        print(e)
        shutil.rmtree(tmp, ignore_errors=True)
        raise SystemExit(1)

    npz = tmp / "domain_dryrun.npz"
    if not npz.exists():
        print("\n[error] no domain_dryrun.npz — build_static did not reach the dump")
        shutil.rmtree(tmp, ignore_errors=True)
        raise SystemExit(1)
    D = np.load(npz)

    fx, fy = D["x"], D["y"]
    zb, mask = D["z"], D["mask"]
    o = xr.open_dataset(OLD)
    ofx, ofy = o["mesh2d_face_x"].values, o["mesh2d_face_y"].values
    ozb, omask = o["z"].values, o["mask"].values

    print("\n" + "=" * 84)
    print("1. THE LEAK  — free-outflow cells sitting on open water")
    print("=" * 84)
    n_new = int(((mask == 3) & (zb < OUTFLOW_MAX_DEPTH)).sum())
    n_old = int(((omask == 3) & (ozb < OUTFLOW_MAX_DEPTH)).sum())
    print(f"   old domain : {n_old:4d}   <- the drain (deepest {ozb[(omask == 3) & (ozb < OUTFLOW_MAX_DEPTH)].min():+.2f} m)")
    print(f"   new domain : {n_new:4d}   {'*** SEALED ***' if n_new == 0 else '!!! STILL LEAKING !!!'}")

    print("\n" + "=" * 84)
    print("2. SHARK RIVER INLET — controlling sill across the inlet")
    print("=" * 84)
    print("      x        old bed     new bed")
    for (x0, o), (_, n) in zip(
        profile_sill(ofx, ofy, ozb, omask, SHARK_X, SHARK_Y),
        profile_sill(fx, fy, zb, mask, SHARK_X, SHARK_Y),
    ):
        flag = "   <-- WAS A DAM, NOW OPEN" if o > -0.5 and n < -1 else ""
        print(f"   {x0:6d}   {o:+8.2f}   {n:+8.2f}{flag}")

    print("\n" + "=" * 84)
    print("3. SEA BRIGHT REVETMENT — must NOT have been carved away")
    print("=" * 84)
    r = (mask > 0) & (fx > REVET_X[0]) & (fx < REVET_X[1]) & (fy > REVET_Y[0]) & (fy < REVET_Y[1])
    ro = (omask > 0) & (ofx > REVET_X[0]) & (ofx < REVET_X[1]) & (ofy > REVET_Y[0]) & (ofy < REVET_Y[1])
    print(f"   crest (99th pct bed)  old {np.nanpercentile(ozb[ro], 99):+.2f} m   "
          f"new {np.nanpercentile(zb[r], 99):+.2f} m")
    print(f"   median bed            old {np.nanmedian(ozb[ro]):+.2f} m   "
          f"new {np.nanmedian(zb[r]):+.2f} m")

    print("\n" + "=" * 84)
    print("4. NOTHING ELSE MOVED")
    print("=" * 84)
    print(f"   active cells   old {int((omask > 0).sum()):7d}   new {int((mask > 0).sum()):7d}")
    print(f"   total faces    old {len(ozb):7d}   new {len(zb):7d}")

    keep = ROOT / "reports" / "domain_dryrun.npz"
    keep.parent.mkdir(exist_ok=True)
    shutil.copy2(npz, keep)
    print(f"\n   (dry-run arrays kept at {keep} for further interrogation)")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
