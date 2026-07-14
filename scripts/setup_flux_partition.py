"""MEASURE how water actually gets into the Shrewsbury/Navesink (Workstream J).

The 07-13 campaign asserted "the water enters OVER the Sea Bright barrier, not through
the narrows" and used it to reframe every earlier null result. That claim was never
measured. It rested on two observations -- the barrier crest gets wet, and estuary
storage scales with the engine -- and NEITHER establishes a pathway: the estuary also
opens to Sandy Hook Bay through a throat at Highlands, and inflow there would produce
exactly the same two signals.

The HWM table actually hints the other way. On Faber, Sandy Hook Bay is essentially
unbiased (+0.038) while the estuary behind it is low (-0.422). If the THROAT were the
dominant route, that is the signature you would expect -- and the deficit would then be
a conveyance problem between bay and estuary, i.e. the narrows/bridge-dam story this
campaign already believes it eliminated.

So the two hypotheses make different, checkable predictions:

  over-the-barrier dominant -> the under-fill is an OVERTOPPING deficit; the sill and the
                               wave setup over it are where to look.
  through-the-throat dominant -> the under-fill is a CONVEYANCE deficit, and the earlier
                               elimination of the narrows work was premature.

This run measures the partition instead of arguing about it. Physics is IDENTICAL to the
premier (``snapwave_tuned_25m``, Faber v2.3.3) -- the only changes are diagnostic output,
so nothing here can disturb the premier verdict:

  crsfile  = sfincs.crs   two control lines (scripts/make_flux_crosssections.py). Both
                          binaries support it and write ``crosssection_discharge`` into
                          sfincs_his.nc at the his interval => 10-min Q(t) through each.
  storevel = 1            velocity fields, for sanity-checking the flux direction.

The two lines were built from the bathymetry and MEET at a corner (586960, 4472000) so
that together they seal the estuary -- if they crossed, flux would be double-counted; if
they left a gap, water would enter unmeasured. Two traps found while placing them:

  * A straight N-S line is WRONG. The barrier's x wanders with latitude; a meridian at
    x=587050 drops into the estuary channel at y~4469000 (zb -3.9).
  * The "wet span" at the throat (586534-587084) MERGES TWO WATER BODIES. The section at
    y=4472000 reads: bluff | estuary channel (586534-586709) | BARRIER (586734-586984) |
    ocean (587009+). A line drawn across the naive wet span would cross the barrier and
    count OCEAN flow as bay inflow. The true throat is only ~175 m wide.

Read the result with:  Q_barrier vs Q_throat, integrated over the storm, against the
estuary's own storage change. Note the attribution boundary: water that overtops the
barrier NORTH of y=4472000 and then runs south into the estuary is counted as "throat"
(it entered by the northern route), which is the intended reading.

Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python \
          scripts/setup_flux_partition.py
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from nj_sfincs.config import ROOT

EXP = ROOT / "experiments"
SRC = EXP / "snapwave_tuned_25m"          # the premier (Faber v2.3.3), physics unchanged
CRS_SRC = ROOT / "data" / "flux_crosssections.crs"

NAME = "faber_flux_25m"
KV = {"crsfile": "sfincs.crs", "storevel": "1"}

INPUT_FILES = [
    "sfincs.inp",
    "sfincs.nc", "sfincs_subgrid.nc", "roughness.nc", "sfincs.obs",
    "sfincs_netbndbzsbzifile.nc", "sfincs_netsrcdisfile.nc",
    "sfincs_netamuv.nc", "sfincs_netampr.nc", "sfincs_netamp.nc",
    "snapwave.bnd", "snapwave.bhs", "snapwave.btp", "snapwave.bwd", "snapwave.bds",
]
INPUT_DIRS = ["subgrid"]
COPY_FILES = {"sfincs.inp"}               # the only file we rewrite; see _place


def _set_inp(inp: Path, kv: dict[str, str]) -> None:
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


def _place(src: Path, dst: Path) -> None:
    """Hard-link read-only inputs (quota); copy only what we rewrite."""
    if Path(src).name in COPY_FILES:
        shutil.copy2(src, dst)
    else:
        os.link(src, dst)


def main() -> None:
    assert (SRC / "sfincs.nc").exists(), f"built inputs not found in {SRC}"
    assert CRS_SRC.exists(), f"missing {CRS_SRC} -- run scripts/make_flux_crosssections.py"

    dst = EXP / NAME
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for f in INPUT_FILES:
        _place(SRC / f, dst / f)
    for d in INPUT_DIRS:
        if (SRC / d).exists():
            shutil.copytree(SRC / d, dst / d, copy_function=_place)
    shutil.copy2(CRS_SRC, dst / "sfincs.crs")
    _set_inp(dst / "sfincs.inp", KV)
    for stale in ("sfincs_his.nc", "sfincs_map.nc", "snapwave.upw", "sfincs.log"):
        (dst / stale).unlink(missing_ok=True)

    print(f"[{NAME}] staged from {SRC.name}; set {KV}")
    print(f"[{NAME}] cross-sections: {(dst / 'sfincs.crs').read_text().count(chr(10))} lines")
    print("\nSubmit (Faber sif -- must match the premier):")
    print(f"  SFINCS_SIF=$PWD/sfincs-desktop.sif sbatch --time=03:00:00 "
          f"hpc/sfincs_run.slurm experiments/{NAME}")


if __name__ == "__main__":
    main()
