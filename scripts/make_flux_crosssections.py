"""Build the two control lines that partition INFLOW to the Shrewsbury/Navesink.

The campaign asserted "the water comes in OVER the Sea Bright barrier, not through
the narrows" on the strength of crest wetting + storage scaling. Neither demonstrates
the pathway: the estuary ALSO opens to Sandy Hook Bay through a throat at Highlands,
and inflow there would produce the same two signals. This measures the partition.

Two SFINCS cross-sections (`crsfile`; the binary writes `crosssection_discharge` into
sfincs_his.nc at the his interval, so we get 10-min Q(t) through each):

  barrier  — a POLYLINE following the Sea Bright crest. A straight meridian is WRONG:
             the barrier's x wanders with latitude and a line at x=587050 drops into
             the estuary channel at y~4469000 (zb -3.9). So track argmax(zb) per row.
  throat   — the estuary's ONLY connection to Sandy Hook Bay, at Highlands. Clean and
             narrow: ~550 m wide, deepest -8.3 m, at y~4472000.

Writes sfincs.crs (ascii: NAME / "nrows 2" / x y rows) + a geojson for inspection.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import xarray as xr
from shapely.geometry import LineString

from nj_sfincs.config import ROOT

REF = ROOT / "experiments" / "snapwave_tuned_25m"
# Barrier runs y 4462500 (where it roots into the mainland and the estuary closes) to
# the Highlands throat at 4472000. The two lines must MEET at a corner: if they cross,
# flux is double-counted; if they leave a gap, water enters unmeasured.
Y0, Y1, DY = 4462500, 4472000, 100
XSEARCH = (586500, 588000)          # window that contains the crest at every row
THROAT_Y = 4472000
# WEST anchor on the Highlands bluff (x=586420 is +8.8 m). The EAST end is NOT a fixed
# number — it is set to the barrier polyline's final vertex so the two lines join exactly.
#
# Do NOT extend the throat east of the barrier crest. The bathymetry at y=4472000 goes
# bluff | estuary channel (586534-586709) | BARRIER (586734-586984) | ocean (587009+):
# the estuary channel and the ocean are BOTH wet but are different water bodies. A naive
# "wet span" of 586534-587084 merges them, and a line drawn across it would count ocean
# flow as bay inflow. The true throat is only ~175 m wide.
THROAT_X_WEST = 586420


def barrier_polyline(fx, fy, zb, act):
    """Continuous track through the barrier body, ocean on one side, estuary on the other.

    A raw per-row argmax(zb) ZIGZAGS by up to 686 m: at Sea Bright the barrier is a wide
    developed spit, so the seaward dune (x~587200) and the back-barrier built-up strip
    (x~586700) trade places as the highest cell. A zigzagging cross-section would cut
    diagonally through water and corrupt the flux. So: take the raw crest, smooth it with
    a rolling median, then re-snap to the highest cell within +/-60 m of the smoothed
    track. Position along the barrier is not critical for a flux line — CONTINUITY is.
    """
    raw = []
    for y in np.arange(Y0, Y1 + 1, DY):
        s = act & (fy >= y - DY / 2) & (fy < y + DY / 2) & (fx > XSEARCH[0]) & (fx < XSEARCH[1])
        if s.sum():
            k = np.argmax(zb[s])
            raw.append((float(fx[s][k]), float(y)))
    rx = np.array([p[0] for p in raw])
    ry = np.array([p[1] for p in raw])

    w = 7                                          # rolling median window (700 m of shore)
    sx = np.array([np.median(rx[max(0, i - w // 2): i + w // 2 + 1]) for i in range(len(rx))])

    pts = []
    for x0, y in zip(sx, ry):
        s = act & (fy >= y - DY / 2) & (fy < y + DY / 2) & (fx > x0 - 60) & (fx < x0 + 60)
        if not s.sum():
            pts.append((float(x0), float(y), float("nan")))
            continue
        k = np.argmax(zb[s])
        pts.append((float(fx[s][k]), float(y), float(zb[s][k])))
    return pts


def main():
    q = xr.open_dataset(REF / "sfincs.nc")
    fx, fy = q["mesh2d_face_x"].values, q["mesh2d_face_y"].values
    zb, act = q["z"].values, q["mask"].values > 0

    pts = barrier_polyline(fx, fy, zb, act)
    xs = np.array([p[0] for p in pts]); ys = np.array([p[1] for p in pts])
    zs = np.array([p[2] for p in pts])

    print(f"barrier polyline: {len(pts)} vertices, y {ys.min():.0f}-{ys.max():.0f}")
    print(f"  crest zb along it: min {zs.min():.2f}  median {np.median(zs):.2f}  max {zs.max():.2f}")
    print(f"  x wanders {xs.min():.0f}-{xs.max():.0f} ({xs.max()-xs.min():.0f} m)"
          f"  max step between vertices: {np.abs(np.diff(xs)).max():.0f} m")
    low = zs < 1.5
    if low.any():
        print(f"  ⚠ {low.sum()} vertices with crest < 1.5 m (possible gaps/inlets):")
        for x, y, z in np.array(pts)[low][:6]:
            print(f"      y={y:.0f} x={x:.0f} zb={z:.2f}")

    # Validate: estuary to the WEST, ocean to the EAST of the line at each row.
    bad = 0
    for x, y, _ in pts:
        w = act & (fy >= y-50) & (fy < y+50) & (fx > x-400) & (fx < x-100)
        e = act & (fy >= y-50) & (fy < y+50) & (fx > x+100) & (fx < x+400)
        if w.sum() and e.sum() and not (np.median(zb[e]) < np.median(zb[w])):
            bad += 1
    print(f"  sanity: ocean deeper than estuary on {len(pts)-bad}/{len(pts)} rows "
          f"({'OK' if bad < len(pts)*0.15 else '*** LINE MISPLACED ***'})")

    # Join the throat to the barrier's north endpoint so the pair seals the estuary.
    x_join, y_join = xs[-1], ys[-1]
    assert y_join == THROAT_Y, f"barrier must end at the throat, ends at {y_join}"
    print(f"\nthroat: y={THROAT_Y}, x {THROAT_X_WEST} -> {x_join:.0f} "
          f"(joins the barrier line's north end; width {x_join-THROAT_X_WEST:.0f} m)")

    feats = [
        {"name": "barrier", "x": xs.tolist(), "y": ys.tolist()},
        {"name": "throat",  "x": [float(THROAT_X_WEST), float(x_join)],
                            "y": [float(THROAT_Y), float(THROAT_Y)]},
    ]
    out = ROOT / "data" / "flux_crosssections.crs"
    with open(out, "w") as f:
        for ft in feats:
            f.write(f"{ft['name']}\n{len(ft['x'])} 2\n")
            for X, Y in zip(ft["x"], ft["y"]):
                f.write(f"{X:.1f} {Y:.1f}\n")
    print(f"\nwrote {out}")

    gdf = gpd.GeoDataFrame(
        {"name": [ft["name"] for ft in feats]},
        geometry=[LineString(list(zip(ft["x"], ft["y"]))) for ft in feats],
        crs="EPSG:32618",
    )
    gj = ROOT / "data" / "flux_crosssections.geojson"
    gdf.to_file(gj, driver="GeoJSON")
    print(f"wrote {gj}  (open in QGIS to eyeball the lines)")


if __name__ == "__main__":
    main()
