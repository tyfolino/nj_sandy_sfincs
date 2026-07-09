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

    z_level[c, k] is the water elevation at volume fraction k/(nlev-1); invert to
    get the fraction (hence volume) at zs_t. Clamped at volmax (ignores the small
    above-zmax overspill — fine for an open-vs-wall DIFFERENCE at similar levels).
    Fully vectorised: per-cell piecewise-linear interpolation via searchsorted so
    the full 73-timestep budget runs in seconds, not minutes.
    """
    nlev = zlevel.shape[1]
    frac = np.linspace(0.0, 1.0, nlev)
    # locate zs_t within each cell's own z_level ladder
    z = zs_t.astype(float)
    k = np.array([np.searchsorted(zlevel[c], z[c]) for c in range(z.shape[0])])
    k = np.clip(k, 1, nlev - 1)
    z0 = zlevel[np.arange(z.shape[0]), k - 1]
    z1 = zlevel[np.arange(z.shape[0]), k]
    with np.errstate(divide="ignore", invalid="ignore"):
        w = np.where(z1 > z0, (z - z0) / (z1 - z0), 0.0)
    f = np.clip(frac[k - 1] + w * (frac[k] - frac[k - 1]), 0.0, 1.0)
    vol = f * volmax
    vol[z <= zmin] = 0.0
    return vol


def _cell_geometry(run: Path):
    """Exact per-face east-west width, y-extent, and bed from the map's node mesh.

    Quadtree cells are axis-aligned, so a face's node corners give width/height
    directly (no dx/level assumptions). face_nodes are 1-based. Returns
    (width, ymin, ymax, zb, msk) each length nface.
    """
    m = xr.open_dataset(run / "sfincs_map.nc")
    nx = m["mesh2d_node_x"].values
    ny = m["mesh2d_node_y"].values
    fn = m["mesh2d_face_nodes"].values.astype("int64") - 1
    X, Y = nx[fn], ny[fn]
    return (X.max(1) - X.min(1), Y.min(1), Y.max(1),
            m["zb"].values, m["msk"].values)


def _boundary_flux(run: Path, wall_y: float = WALL_Y):
    """Net northward volume flux (m^3/s) across the y=wall_y latitude line.

    Integrates the SFINCS face-centred northward velocity v (storevel=1, grid is
    unrotated EPSG:32618 so v is true north) over the depth H=zs-zb and the
    east-west width of every active cell straddling the line. Positive = water
    leaving northward (escape/sink); negative = water entering from the harbor
    (source). Returns (time, flux_series, n_cells).
    """
    width, ymin, ymax, zb, msk = _cell_geometry(run)
    idx = np.where((ymin < wall_y) & (ymax >= wall_y) & (msk > 0))[0]
    m = xr.open_dataset(run / "sfincs_map.nc")
    v = m["v"].values[:, idx]              # (time, ncell) northward m/s
    zs = m["zs"].values[:, idx]
    H = np.clip(zs - zb[idx][None, :], 0.0, None)
    flux = np.nansum(v * H * width[idx][None, :], axis=1)
    return m["time"].values, flux, idx.size


def _estuary_volume_series(run: Path, cells: np.ndarray) -> np.ndarray:
    """Total estuary storage volume over time (m^3) from the map + z-table."""
    sg = xr.open_dataset(run / "sfincs_subgrid.nc")
    mp = xr.open_dataset(run / "sfincs_map.nc")
    zmin = sg["z_zmin"].values[cells]
    zmax = sg["z_zmax"].values[cells]
    zlevel = sg["z_level"].values[cells]
    volmax = sg["z_volmax"].values[cells]
    zs = mp["zs"].values[:, cells]  # (time, ncell); full-load+subset (fast vs scattered isel)
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

    # -- 3. direct N/NW boundary flux ----------------------------------------
    # Net northward volume flux across the y=WALL_Y line in the OPEN run answers
    # source-vs-sink directly, without the wall's reflection artifacts.
    print(f"\n=== 3. Net flux across N/NW line (y={WALL_Y:.0f}) ===")
    for name, r in (("open", op), ("wall", wl)):
        t, flux, n = _boundary_flux(r)
        imax = int(np.nanargmax(np.abs(flux)))
        dt = np.diff(t).astype("timedelta64[s]").astype(float)
        netvol = np.nansum(0.5 * (flux[:-1] + flux[1:]) * dt)
        pk = flux[imax]
        print(f"  [{name}] {n} straddle cells | peak |flux| {pk:+.0f} m3/s @ "
              f"{str(t[imax])[:16]} ({'NORTH=out/escape' if pk > 0 else 'SOUTH=in/source'})"
              f" | net vol {netvol:+.3e} m3 "
              f"({'net OUT' if netvol > 0 else 'net IN from harbor'})")
    print("Interpretation: OPEN net-IN (southward) => the N/NW boundary FEEDS the "
          "bay (a source), so walling it removes real inflow and should LOWER "
          "estuary levels — the escape hypothesis is refuted on this build. "
          "OPEN net-OUT (northward) => water was escaping and the wall should raise levels.")


if __name__ == "__main__":
    main()
