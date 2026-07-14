"""Workstream K — PLUG THE LEAK. The estuary under-fill is a mass sink, not missing physics.

Job 58159466 (`faber_flux_25m`, the Workstream-J flux partition) returned an output that
could not be squared with conservation, and the reason turned out to be the finding:

  * The active mask CHOPS THE NAVESINK IN HALF, mid-channel, at x~580,670, and hydromt
    assigned the cut face ``mask=3`` -- a free-outflow (Neumann) boundary. West of it the
    cells are ``mask=0`` but the BATHYMETRY IS WATER (zb down to -6.5 m): the real river
    runs on 2.8 km further, to the head of tide at Swimming River Dam. So the domain edge
    is a five-metre-deep open cross-section of a tidal river with a free-outflow BC on it.
    That is a drain, not a boundary. Two more wet cuts do the same at Shark River and the
    NW/Raritan corner.

  * Measured: cut velocity -0.82 m/s mean, -2.02 m/s peak, OUT of the domain in 100% of
    timesteps, never reversing. Estuary balance: 3.72e8 m3 in through the Highlands throat,
    only 2.8e7 m3 stored => 92.5% of the inflow VANISHES. The estuary is a PIPE, not a
    bathtub. And it drains BEFORE the storm: from a flat initial condition the model pulls
    the Navesink to -1.48 m by 04:00 on Oct 28, two days before Sandy peaks. At the peak the
    bay stands at +3.09 m while the Navesink sits at -0.15 m -- a 3.2 m head drop across a
    few km of open tidal water. A constriction can DELAY filling; it cannot hold a basin 3 m
    below the water pressing on it for three days. Only a sink does that.

This matters far beyond one run: every experiment in the campaign was staged by HARD-LINKING
THE SAME ``sfincs.nc``, so Faber, Galibier, and every niter/clamp/wind/narrows arm all
inherit the leak. It is the standing explanation for the whole wall of null results -- you
cannot fill a bucket with a hole in it by widening the tap.

WHAT IS AND IS NOT ESTABLISHED. The leak is MEASURED. That plugging it closes the ~0.5-0.7 m
under-fill is a PREDICTION: once the estuary fills, its head rises and the throat inflow
throttles back, so the system re-equilibrates and the cure may be partial. That is what these
runs decide. They do not presuppose it.

FOUR RUNS -- a 2x2. Two fixes, each with waves ON (the Faber premier) and OFF:

  wall    mask 3 -> 1 on the WET outflow cells of all three cuts, so the domain edge reverts
          to SFINCS's default CLOSED WALL. Under-represents storage: it walls the river 2.8 km
          seaward of its true head of tide, discarding real upstream tidal prism.
  extend  wall, PLUS switch the dead wet cells back ON (flood-filled from the cut, so nothing
          isolated is activated) at the Navesink and Shark River, putting the wall at the real
          head of tide and recovering ~2.5 km2 of genuine prism. The NW corner is walled only
          -- it sits on the true domain edge, so there is nothing there to recover.

The pair BRACKETS the answer: `wall` should undershoot, `extend` should be right.

The no-waves arms are the control that matters. The leak is HYDRODYNAMIC, so it must show up
with SnapWave off too -- and there is already a no-waves baseline to A/B against
(``faber_nowaves_25m``: Shrewsbury HWM -0.606, gauge peak 1.663). They also cost ~10 min each
rather than ~1.6 h, because SnapWave was 90% of the runtime of job 58159466.

NO SUBGRID REBUILD IS NEEDED. ``sfincs_subgrid.nc`` carries all 547,267 quadtree faces --
including the 155,232 INACTIVE ones -- so the dead cells already have their tables. This is a
mask edit and nothing more. Boundary-TYPE/active changes never required a rebuild.

Every run keeps ``crsfile``/``storevel`` from the flux run, so the SAME two control lines are
re-measured on a SEALED model. That closes Workstream J properly: it re-partitions the inflow
(the leak-driven suction through the throat is removed) and it VERIFIES the leak is gone --
the Navesink cut velocity must stop being one-signed.

PREDICTIONS (write them down before looking):
  Shrewsbury gauge peak  2.223 -> toward the observed crest 2.935
  Shrewsbury HWM bias    -0.42 -> toward 0
  interior tidal range   0.91  -> toward the observed 1.54
  Navesink at the cut    stops sitting ~1.5 m below datum on a calm night

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/setup_leak_fix.py
"""

from __future__ import annotations

import os
import shutil
from collections import deque

import netCDF4
import numpy as np
import xarray as xr

from nj_sfincs.config import ROOT

EXP = ROOT / "experiments"
SRC = EXP / "snapwave_tuned_25m"              # Faber premier -- the leaking domain we inherit
CRS_SRC = ROOT / "data" / "flux_crosssections.crs"

# The three wet cuts, and the corridor each one's dead water is allowed to be recovered from.
# `extend=None` => wall only (the NW corner is ON the domain edge; nothing to recover).
CUTS = {
    "navesink": dict(
        cut=dict(ymin=4468000, ymax=4471000, xmax=582500),
        corridor=dict(xmin=574000, xmax=580700, ymin=4463000, ymax=4472000),
    ),
    "shark": dict(
        cut=dict(ymin=4448000, ymax=4449500, xmax=582500),
        corridor=dict(xmin=574000, xmax=580900, ymin=4447800, ymax=4449600),
    ),
    "nw": dict(
        cut=dict(ymin=4482000, ymax=None, xmax=562000),
        corridor=None,
    ),
}

INPUT_FILES = [
    "sfincs.nc",                              # COPIED + mask-edited (see COPY_FILES)
    "sfincs.inp",                             # COPIED + rewritten
    "sfincs_subgrid.nc", "roughness.nc", "sfincs.obs",
    "sfincs_netbndbzsbzifile.nc", "sfincs_netsrcdisfile.nc",
    "sfincs_netamuv.nc", "sfincs_netampr.nc", "sfincs_netamp.nc",
    "snapwave.bnd", "snapwave.bhs", "snapwave.btp", "snapwave.bwd", "snapwave.bds",
]
INPUT_DIRS = ["subgrid"]
COPY_FILES = {"sfincs.inp", "sfincs.nc"}      # the two we rewrite; everything else hard-links

# waves ON = the premier's own settings; waves OFF = exactly how faber_nowaves_25m does it.
WAVES = {
    "waves":   {"snapwave": "1", "storefw": "1", "storewavdir": "1"},
    "nowaves": {"snapwave": "0", "storefw": "0", "storewavdir": "0"},
}
DIAG = {"crsfile": "sfincs.crs", "storevel": "1"}   # re-measure the partition on a sealed model


def _box(fx, fy, b):
    s = np.ones(len(fx), bool)
    if b.get("xmin") is not None: s &= fx > b["xmin"]
    if b.get("xmax") is not None: s &= fx < b["xmax"]
    if b.get("ymin") is not None: s &= fy > b["ymin"]
    if b.get("ymax") is not None: s &= fy < b["ymax"]
    return s


def build_masks(verbose=True):
    """Return (mask_wall, mask_extend) derived from the premier's mask."""
    q = xr.open_dataset(SRC / "sfincs.nc")
    fx, fy = q["mesh2d_face_x"].values, q["mesh2d_face_y"].values
    zb, mask0 = q["z"].values, q["mask"].values
    adj = q["mesh2d_face_faces"].values                      # 0-based, NaN-filled, <=8 nbrs

    wall = mask0.copy()
    extend = mask0.copy()
    if verbose:
        print("cut                 wet-outflow cells walled   dead wet cells re-activated")
        print("-" * 74)

    for name, spec in CUTS.items():
        # --- the wall: wet outflow cells (the drain) become ordinary active cells, so the
        #     inactive ground beyond them is a closed wall. Dry outflow cells are LEFT ALONE:
        #     they legitimately let overland flood water leave instead of ponding at the edge.
        cut = (mask0 == 3) & (zb < 0) & _box(fx, fy, spec["cut"])
        wall[cut] = 1
        extend[cut] = 1

        n_ext = 0
        if spec["corridor"] is not None:
            # --- the extension: flood-fill WEST from the cut through dead wet cells, so we
            #     only ever activate water that is actually CONNECTED to the estuary. An
            #     isolated pool would be a dead pond (or an SFINCS complaint), not a fix.
            cand = (mask0 == 0) & (zb < 0) & _box(fx, fy, spec["corridor"])
            seen = np.zeros(len(fx), bool)
            dq = deque(np.flatnonzero(cut))
            while dq:
                i = dq.popleft()
                for j in adj[i]:
                    if np.isnan(j):
                        continue
                    j = int(j)
                    if cand[j] and not seen[j]:
                        seen[j] = True
                        dq.append(j)
            extend[seen] = 1
            n_ext = int(seen.sum())
            if verbose and n_ext:
                A = (200.0 / 2 ** (q["level"].values[seen] - 1)) ** 2
                print("%-12s %14d %26d   (%.2f km2, x %.0f-%.0f, zb min %+.2f)" % (
                    name, int(cut.sum()), n_ext, A.sum() / 1e6,
                    fx[seen].min(), fx[seen].max(), zb[seen].min()))
                continue
        if verbose:
            print("%-12s %14d %26s" % (name, int(cut.sum()), n_ext if n_ext else "-- (wall only)"))

    if verbose:
        for nm, mk in (("wall", wall), ("extend", extend)):
            print("\n%-7s : active %d (%+d vs premier)   outflow-cells remaining %d" % (
                nm, (mk > 0).sum(), (mk > 0).sum() - (mask0 > 0).sum(), (mk == 3).sum()))
    return wall, extend


def _set_inp(inp, kv):
    lines = inp.read_text().splitlines()
    have = {ln.split("=")[0].strip() for ln in lines if "=" in ln}
    out = []
    for ln in lines:
        key = ln.split("=")[0].strip() if "=" in ln else ""
        out.append(f"{key:<20} = {kv[key]}" if key in kv else ln)
    for key, val in kv.items():
        if key not in have:
            out.append(f"{key:<20} = {val}")
    inp.write_text("\n".join(out) + "\n")


def _place(src, dst):
    if os.path.basename(src) in COPY_FILES:
        shutil.copy2(src, dst)
    else:
        os.link(src, dst)                     # quota: inputs are 1.8 GB/run if copied


def stage(name, new_mask, waves):
    dst = EXP / name
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for f in INPUT_FILES:
        _place(SRC / f, dst / f)
    for d in INPUT_DIRS:
        if (SRC / d).exists():
            shutil.copytree(SRC / d, dst / d, copy_function=_place)
    shutil.copy2(CRS_SRC, dst / "sfincs.crs")

    # edit the mask IN PLACE -- an xarray round-trip would rewrite every variable's encoding,
    # and SFINCS reads this file structurally. Touch the one array and nothing else.
    with netCDF4.Dataset(dst / "sfincs.nc", "r+") as nc:
        nc["mask"][:] = new_mask.astype(nc["mask"].dtype)

    _set_inp(dst / "sfincs.inp", {**WAVES[waves], **DIAG})
    for stale in ("sfincs_his.nc", "sfincs_map.nc", "snapwave.upw", "sfincs.log"):
        (dst / stale).unlink(missing_ok=True)
    return dst


def main():
    assert (SRC / "sfincs.nc").exists(), f"built inputs not found in {SRC}"
    assert CRS_SRC.exists(), f"missing {CRS_SRC} -- run scripts/make_flux_crosssections.py"

    wall, extend = build_masks()

    print("\nstaged:")
    jobs = []
    for fix, mk in (("wall", wall), ("extend", extend)):
        for waves in ("waves", "nowaves"):
            name = f"leakfix_{fix}_{waves}_25m"
            stage(name, mk, waves)
            jobs.append((name, waves))
            print(f"  experiments/{name}")

    print("\nSubmit (Faber sif -- MUST match the premier, snapwave_tuned_25m):")
    for name, waves in jobs:
        t = "00:40:00" if waves == "nowaves" else "03:00:00"   # SnapWave was 90% of runtime
        print(f"  SFINCS_SIF=$PWD/sfincs-desktop.sif sbatch --time={t} "
              f"hpc/sfincs_run.slurm experiments/{name}")


if __name__ == "__main__":
    main()
