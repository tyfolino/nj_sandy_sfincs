"""Workstream H — build the 'widened narrows' dredge raster.

Aggressive over-dredge diagnostic: take the surveyed eHydro channel ribbon
(Navesink + Shrewsbury) and WIDEN it laterally, setting the added banks to a deep
flat -5 m. Leaves the original eHydro thalweg pixels as NoData so the real survey
depth still wins there (dredge layer sits ON TOP / highest priority, but only
where it has data). Net effect: a much wider deep cross-section through both
narrows, isolating channel WIDTH as the lever (Workstream B already showed DEPTH
is faithful; this tests whether the eHydro ribbon is narrower than the real 2012
channel).

Safety: the lateral buffer is clipped BEHIND the Sea Bright barrier axis
(x <= 586000 + 0.075*(y-4456000), same line validate.py uses) so it can never
dredge a hole through the ocean-front dune line and breach the barrier.

Out: data/elevation/narrows_wide_h.tif  (EPSG:32618, -5 m in the widened band,
NoData elsewhere).
Run:  micromamba/envs/sfincs/bin/python scripts/make_narrows_dredge.py
"""

from __future__ import annotations

import numpy as np
import rioxarray
from scipy.ndimage import binary_dilation

from nj_sfincs.config import ROOT, DATA

EHYDRO = DATA / "elevation" / "shrewsbury_ehydro_2015.tif"
TOPO = DATA / "elevation" / "usace_nj_2010_topobathy_clip.tif"  # 1 m pre-Sandy ground
OUT = DATA / "elevation" / "narrows_wide_h.tif"

DREDGE_Z = -5.0          # m NAVD88, the deep flat bank level
BUFFER_M = 150.0         # lateral widening each side (~2-3x a 150-230 m narrows)
GROUND_MAX = 1.0         # exclude only VALID high ground > this (ocean dune/upland);
                         # NoData (open water) is includable. Real marsh sits near 0.
# Sea Bright barrier axis — keep the dredge strictly WEST/inland of this line.
BARRIER_X0, BARRIER_Y0, BARRIER_SLOPE = 586_000.0, 4_456_000.0, 0.075
# CAUSEWAY-CUT zones: INTERNAL bridge causeways (the Rumson–Sea Bright dam) are the
# very chokes we want to widen, but they read as high ground so GROUND_MAX would
# protect them. Inside these boxes we ALLOW cutting through high ground (still bounded
# by the barrier-axis clip, so the OCEAN dune east of it stays intact). UTM 18N.
CAUSEWAY_CUTS = (
    dict(xmin=586_400, xmax=586_900, ymin=4_467_850, ymax=4_469_400),  # Rumson–Sea Bright bridge (+north approach)
)


def main() -> None:
    r = rioxarray.open_rasterio(EHYDRO, masked=True).squeeze()
    res = abs(r.rio.resolution()[0])
    npix = int(round(BUFFER_M / res))
    chan = np.isfinite(r.values)                    # surveyed channel footprint
    wide = binary_dilation(chan, iterations=npix)   # widen laterally
    ring = wide & ~chan                             # the ADDED banks only

    # clip behind the barrier axis (never breach the ocean-front dune line)
    xs = r["x"].values
    ys = r["y"].values
    X, Y = np.meshgrid(xs, ys)
    behind = X <= (BARRIER_X0 + BARRIER_SLOPE * (Y - BARRIER_Y0))
    ring = ring & behind

    # never carve through dune/causeway/upland — exclude ring pixels where the real
    # ground is VALID and high (> GROUND_MAX). NoData in the topobathy = open water,
    # which is includable (safe to deepen). Keeps the barrier + causeway intact.
    topo = rioxarray.open_rasterio(TOPO, masked=True).squeeze().rio.reproject_match(r)
    tv = np.asarray(topo.values, dtype="float32")
    upland = np.isfinite(tv) & (tv > GROUND_MAX)
    # but permit cutting through high ground inside the internal causeway-cut boxes
    cutzone = np.zeros(r.shape, dtype=bool)
    for c in CAUSEWAY_CUTS:
        cutzone |= (X >= c["xmin"]) & (X <= c["xmax"]) & (Y >= c["ymin"]) & (Y <= c["ymax"])
    protect = upland & ~cutzone
    n_upland = int((ring & protect).sum())
    n_cause = int((ring & upland & cutzone).sum())
    ring = ring & ~protect

    out = np.full(r.shape, np.nan, dtype="float32")
    out[ring] = DREDGE_Z
    da = r.copy(data=out)
    da.rio.set_nodata(np.nan, inplace=True)
    da.rio.to_raster(OUT)

    print(f"eHydro channel pixels : {int(chan.sum()):,}")
    print(f"widened band (+{BUFFER_M:.0f} m each side, {npix} px) : {int(ring.sum()):,} pixels @ {DREDGE_Z} m")
    print(f"ocean-dune/upland pixels EXCLUDED (ground > {GROUND_MAX} m) : {n_upland:,}")
    print(f"causeway high-ground CUT THROUGH (bridge choke widened) : {n_cause:,}")
    print(f"added area : {ring.sum() * res * res / 1e6:.2f} km^2")
    yy, xx = np.where(ring)
    print(f"band extent  x[{int(xs[xx].min())},{int(xs[xx].max())}]  y[{int(ys[yy].min())},{int(ys[yy].max())}]")
    print(f"barrier clip removed any ocean-side dredge: max dredge x = {int(xs[xx].max())} "
          f"(barrier at y-min ~ {int(BARRIER_X0 + BARRIER_SLOPE*(ys[yy].min()-BARRIER_Y0))})")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
