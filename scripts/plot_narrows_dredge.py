"""Workstream H — high-res map of the widened-narrows dredge for visual inspection.

Shows, over the pre-Sandy ground/bathymetry:
  * the original surveyed eHydro channel (kept at survey depth),
  * the added widening band (-5 m, the aggressive over-dredge),
  * the Sea Bright barrier axis (dredge is clipped west of it),
  * the dune/causeway pixels excluded from dredging.

Out: reports/figures/narrows_widen_h.png
Run:  micromamba/envs/sfincs/bin/python scripts/plot_narrows_dredge.py
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, TwoSlopeNorm
import numpy as np
import rioxarray

from nj_sfincs.config import DATA, ROOT

EHYDRO = DATA / "elevation" / "shrewsbury_ehydro_2015.tif"
DREDGE = DATA / "elevation" / "narrows_wide_h.tif"
TOPO = DATA / "elevation" / "usace_nj_2010_topobathy_clip.tif"
OUT = ROOT / "reports" / "figures" / "narrows_widen_h.png"
BARRIER_X0, BARRIER_Y0, BARRIER_SLOPE = 586_000.0, 4_456_000.0, 0.075
CAUSEWAY_CUTS = (
    dict(xmin=586_400, xmax=586_900, ymin=4_467_850, ymax=4_469_400),
)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ehy = rioxarray.open_rasterio(EHYDRO, masked=True).squeeze()
    drg = rioxarray.open_rasterio(DREDGE, masked=True).squeeze()
    topo = rioxarray.open_rasterio(TOPO, masked=True).squeeze().rio.reproject_match(ehy)
    x = ehy["x"].values
    y = ehy["y"].values
    ext = [x.min(), x.max(), y.min(), y.max()]

    fig, ax = plt.subplots(figsize=(13, 18), dpi=200)

    # background: pre-Sandy ground (land brown / water blue via diverging norm at 0)
    tv = np.asarray(topo.values)
    norm = TwoSlopeNorm(vmin=-8, vcenter=0.0, vmax=8)
    ax.imshow(tv, extent=ext, origin="upper", cmap="gist_earth", norm=norm,
              interpolation="nearest")

    # original eHydro channel (survey depth kept) — solid teal overlay
    chan = np.where(np.isfinite(ehy.values), 1.0, np.nan)
    ax.imshow(chan, extent=ext, origin="upper",
              cmap=ListedColormap(["#0b7a75"]), alpha=0.85, interpolation="nearest")

    # added widening band (-5 m dredge) — solid magenta overlay
    band = np.where(np.isfinite(drg.values), 1.0, np.nan)
    ax.imshow(band, extent=ext, origin="upper",
              cmap=ListedColormap(["#e6007e"]), alpha=0.7, interpolation="nearest")

    # barrier axis (dredge clipped west of this)
    yy = np.array([y.min(), y.max()])
    ax.plot(BARRIER_X0 + BARRIER_SLOPE * (yy - BARRIER_Y0), yy,
            "r--", lw=2, label="Sea Bright barrier axis (dredge clipped west)")

    # causeway-cut box(es) — where we allow cutting through the internal bridge dam
    from matplotlib.patches import Patch, Rectangle
    for c in CAUSEWAY_CUTS:
        ax.add_patch(Rectangle((c["xmin"], c["ymin"]), c["xmax"] - c["xmin"],
                               c["ymax"] - c["ymin"], fill=False, ec="yellow",
                               lw=2.5, ls="-"))
    ax.legend(handles=[
        Patch(color="#0b7a75", label="original eHydro channel (survey depth kept)"),
        Patch(color="#e6007e", label="added widening band (−5 m over-dredge)"),
        plt.Line2D([0], [0], color="r", ls="--", lw=2, label="barrier axis (clip line)"),
        plt.Line2D([0], [0], color="yellow", lw=2.5, label="causeway-cut box (bridge choke widened)"),
    ], loc="upper left", fontsize=11, framealpha=0.9)

    ax.set_title("Workstream H — widened Navesink + Shrewsbury narrows\n"
                 "(aggressive over-dredge diagnostic, 25 m Galibier)", fontsize=14)
    ax.set_xlabel("UTM 18N easting [m]")
    ax.set_ylabel("UTM 18N northing [m]")
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(OUT, bbox_inches="tight")
    print(f"wrote {OUT}  ({OUT.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
