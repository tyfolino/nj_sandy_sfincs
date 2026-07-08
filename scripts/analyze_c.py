"""Workstream C — analyse the N/NW boundary flux/wall A/B.

Run AFTER both jobs finish (experiments/nw_open and experiments/nw_wall).

Answers the advisor's escape hypothesis three ways:
  1. Wall A/B on the estuary/river gauges + tidal range (does closing the N/NW
     boundary change how the estuary fills?).
  2. Estuary VOLUME budget from water level + subgrid storage table (open vs wall):
     if the wall raises estuary volume, water was escaping; if it lowers/does not
     change it, the boundary was a source or neutral, not a leak.
  3. Direct net flux across the N/NW boundary line (if velocity output is present).

Run:  micromamba/envs/sfincs/bin/python scripts/analyze_c.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from nj_sfincs import validate as V
from nj_sfincs.config import ROOT

EXP = ROOT / "experiments"
WALL_Y = 4_480_000.0
# Behind-the-barrier estuary (Shrewsbury + Navesink), UTM 18N — the under-fill region.
ESTUARY = dict(xmin=582_000, xmax=588_000, ymin=4_466_000, ymax=4_474_000)


def _his_peaks(run: Path) -> dict:
    """Peak water level at each observation gauge (10-min his output)."""
    h = xr.open_dataset(run / "sfincs_his.nc")
    zs = h["point_zs"]
    names = [n.decode() if isinstance(n, bytes) else str(n)
             for n in zs["station_name"].values]
    return {nm: float(zs.isel(stations=i).max()) for i, nm in enumerate(names)}


def _cell_volume(zs_t, zmin, zmax, zlevel, volmax):
    """Subgrid storage volume per cell at water level zs_t (vectorised over cells).

    z_level[k] is the water elevation at volume fraction k/9; invert to get the
    fraction (hence volume) at zs_t. Clamped at volmax (ignores the small
    above-zmax overspill — fine for an open-vs-wall DIFFERENCE at similar levels).
    """
    nlev = zlevel.shape[1]
    frac = np.linspace(0.0, 1.0, nlev)
    vol = np.zeros(zs_t.shape[0])
    for c in range(zs_t.shape[0]):
        if zs_t[c] <= zmin[c]:
            continue
        f = np.interp(zs_t[c], zlevel[c], frac)
        vol[c] = f * volmax[c]
    return vol


def _estuary_volume_series(run: Path, cells: np.ndarray) -> np.ndarray:
    """Total estuary storage volume over time (m^3) from the map + z-table."""
    sg = xr.open_dataset(run / "sfincs_subgrid.nc")
    mp = xr.open_dataset(run / "sfincs_map.nc")
    zmin = sg["z_zmin"].values[cells]
    zmax = sg["z_zmax"].values[cells]
    zlevel = sg["z_level"].values[cells]
    volmax = sg["z_volmax"].values[cells]
    zs = mp["zs"].isel(nmesh2d_face=cells).values  # (time, ncell)
    vols = np.array([
        np.nansum(_cell_volume(np.nan_to_num(zs[t], nan=-1e9), zmin, zmax, zlevel, volmax))
        for t in range(zs.shape[0])
    ])
    return mp["time"].values, vols


def main() -> None:
    op, wl = EXP / "nw_open", EXP / "nw_wall"
    for r in (op, wl):
        if not (r / "sfincs_map.nc").exists():
            print(f"!! {r.name} not finished (no sfincs_map.nc) — run once both jobs complete.")
            return

    # -- 1. gauge A/B ---------------------------------------------------------
    po, pw = _his_peaks(op), _his_peaks(wl)
    print("=== 1. Gauge peak water level: open vs wall ===")
    print(f"{'gauge':>28} {'open':>7} {'wall':>7} {'wall-open':>9}")
    for k in po:
        print(f"{k:>28} {po[k]:7.3f} {pw[k]:7.3f} {pw[k]-po[k]:+9.3f}")

    # -- 1b. tidal range A/B --------------------------------------------------
    print("\n=== 1b. Tidal range (wet channel cells) ===")
    to, tw = V.tidal_range_metric(op), V.tidal_range_metric(wl)
    for k in to:
        if k.startswith("tide_mod_range"):
            print(f"{k:>40} open {to[k]:.3f}  wall {tw[k]:.3f}")

    # -- 2. estuary volume budget --------------------------------------------
    g = xr.open_dataset(op / "sfincs.nc")
    fx, fy, mask = (g["mesh2d_face_x"].values, g["mesh2d_face_y"].values,
                    g["mask"].values)
    cells = np.where((fx > ESTUARY["xmin"]) & (fx < ESTUARY["xmax"]) &
                     (fy > ESTUARY["ymin"]) & (fy < ESTUARY["ymax"]) & (mask > 0))[0]
    print(f"\n=== 2. Estuary storage volume ({len(cells)} cells) ===")
    _, vo = _estuary_volume_series(op, cells)
    _, vw = _estuary_volume_series(wl, cells)
    print(f"peak estuary volume:  open {vo.max():.3e} m3   wall {vw.max():.3e} m3   "
          f"wall-open {vw.max()-vo.max():+.3e} m3 ({100*(vw.max()-vo.max())/vo.max():+.1f}%)")
    print("Interpretation: wall RAISES volume => water was escaping the N/NW boundary; "
          "wall LOWERS/≈ => boundary was a source or neutral, not a leak.")

    # -- 3. direct N/NW boundary flux (if velocity output present) -----------
    mp = xr.open_dataset(op / "sfincs_map.nc")
    velvars = [v for v in mp.data_vars if v.lower() in
               ("u", "v", "uu", "vv", "qx", "qy", "hu", "hv", "q")]
    print(f"\n=== 3. Velocity/flux vars in map output: {velvars or 'NONE (storevel may name them differently)'} ===")
    print("map data_vars:", list(mp.data_vars))
    print("(extend this section once the variable names/structure are known)")


if __name__ == "__main__":
    main()
