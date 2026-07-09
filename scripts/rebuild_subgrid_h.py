"""Workstream H — rebuild ONLY the subgrid on the frozen 25 m mesh with the
widened-narrows dredge prepended, into experiments/narrows_wide_h.

The mesh is NOT rebuilt (that is environment-sensitive, ~18-cell drift → breaks the
A/B). We reuse the frozen grid from snapwave_tuned_25m verbatim and regenerate only
the subgrid tables with elevation_list = [narrows_wide_h] + DEFAULT (dredge on top).
Roughness is unchanged (NLCD, independent of the dredge) — the frozen roughness.nc is
kept and the subgrid manning is resampled from the same roughness_list as the premier.

Config is set to galibier_base_25m's (theta=1.0, igwaves=0) so H vs galibier_base_25m
isolates the WIDTH effect on the same engine.

Assumes scripts staging already copied snapwave_tuned_25m inputs into the dir.
Run:  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/rebuild_subgrid_h.py
"""

from __future__ import annotations

import time
from pathlib import Path

from hydromt_sfincs import SfincsModel

from nj_sfincs.config import ROOT, DATA, BaseConfig, DEFAULT_ELEVATION_LIST

DST = ROOT / "experiments" / "narrows_wide_h"
base = BaseConfig()


def _set_theta(inp: Path) -> None:
    lines = inp.read_text().splitlines()
    have = any(ln.split("=")[0].strip() == "theta" for ln in lines if "=" in ln)
    if not have:
        lines.append(f"{'theta':<20} = 1.0")
    inp.write_text("\n".join(lines) + "\n")


def main() -> None:
    assert (DST / "sfincs.nc").exists(), f"stage {DST} first (copy snapwave_tuned_25m inputs)"
    elevation_list = [{"elevation": "narrows_wide_h"}] + [dict(d) for d in DEFAULT_ELEVATION_LIST]
    roughness_list = [{"lulc": "nlcd_2012", "reclass_table": str(base.reclass_table)}]
    print("elevation_list (dredge prepended):")
    for e in elevation_list:
        print("   ", e)

    t = time.time()
    sf = SfincsModel(root=str(DST), data_libs=[str(DATA / "data_catalog.yml")], mode="r+")
    sf.quadtree_grid.read()
    print(f"grid read {time.time()-t:.0f}s  nfaces={sf.quadtree_grid.data.sizes.get('mesh2d_nFaces')}")

    t = time.time()
    sf.quadtree_subgrid.create(
        elevation_list=elevation_list,
        roughness_list=roughness_list,
        nr_subgrid_pixels=base.nr_subgrid_pixels,
        nrmax=2000,
        write_dep_tif=True,
        write_man_tif=True,
    )
    print(f"subgrid built {time.time()-t:.0f}s")

    sf.quadtree_subgrid.write()
    _set_theta(DST / "sfincs.inp")
    for stale in ("sfincs_map.nc", "sfincs_his.nc", "snapwave.upw", "sfincs.log", "sfincs_log.txt"):
        (DST / stale).unlink(missing_ok=True)
    print(f"DONE — {DST} ready. theta=1.0 set, subgrid rebuilt with narrows_wide_h.")


if __name__ == "__main__":
    main()
