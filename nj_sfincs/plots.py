"""Reusable figures for the visualization notebook.

Each function is a faithful port of a plotting cell from
notebooks/sfincs-nj-sandy.ipynb, parameterized to take an already-opened model
(``sf`` for inputs in read mode, ``mod`` for output) plus the downscaled
``da_hmax`` / ``da_dep`` rasters. Matplotlib functions return ``(fig, ax)``;
the interactive hvplot functions return a HoloViews object.

Keeping these here (rather than inline) is what lets the viz notebook stay thin
and read the same numbers the experiment CSV was built from.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rioxarray  # noqa: F401
import xarray as xr
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

from .config import ROOT

DATA = ROOT / "data"


# ── Static build (grid / elevation / mask) ───────────────────────────────────
def plot_grid(sf, region=DATA / "region.geojson"):
    """Cell 15 — quadtree cell centres coloured by refinement level."""
    import matplotlib.pyplot as plt

    fx, fy = sf.quadtree_grid.data.grid.face_coordinates.T
    lev = sf.quadtree_grid.data["level"].values
    fig, ax = plt.subplots(figsize=(11, 5.2))
    sct = ax.scatter(fx, fy, c=lev, cmap="viridis", s=2, marker="s")
    gpd.read_file(region).to_crs(sf.crs).boundary.plot(ax=ax, color="red", lw=1)
    ax.set_aspect("equal")
    ax.set_xlabel("Easting [m, UTM 18N]")
    ax.set_ylabel("Northing [m]")
    ax.set_title(f"Quadtree mesh — {len(fx):,} cells, {sf.crs.to_epsg()}")
    fig.colorbar(sct, ax=ax, shrink=0.5, label="refinement level (1 = coarsest)")
    fig.tight_layout()
    return fig, ax


def plot_topobathy(sf):
    """Cell 19 — interactive topobathy over Esri imagery (hvplot)."""
    import hvplot.xarray  # noqa: F401

    dem = sf.quadtree_grid.data["z"].ugrid.rasterize(resolution=50)
    dem = dem.rio.write_crs(sf.crs).rio.reproject("EPSG:3857", nodata=float("nan"))
    dem.name = "z"
    return dem.hvplot.image(
        x="x", y="y", rasterize=True, cmap="terrain", clim=(-15, 15),
        tiles="EsriImagery", frame_width=650, frame_height=850,
        title="Topobathy on the quadtree mesh [m NAVD88]",
        clabel="bed level [m NAVD88]",
    )


def plot_mask(sf, region=DATA / "region.geojson"):
    """Cell 25 — mask categories on a Natural-Earth backdrop."""
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt

    mvals = sf.quadtree_grid.data["mask"].values
    fx, fy = sf.quadtree_grid.data.grid.face_coordinates.T
    region = gpd.read_file(region).to_crs(sf.crs)

    proj = ccrs.epsg(32618)
    fig, ax = plt.subplots(figsize=(11, 5.2), subplot_kw={"projection": proj})
    ax.add_feature(cfeature.OCEAN.with_scale("10m"), facecolor="#dbeaf3", zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("10m"), facecolor="#f2efe9", zorder=0)
    ax.coastlines("10m", linewidth=0.6, color="0.4")
    ax.add_feature(cfeature.STATES.with_scale("10m"), linewidth=0.5, edgecolor="0.55")

    for val, (col, lab) in {
        1: ("0.55", "active"),
        2: ("tab:blue", "waterlevel"),
        3: ("tab:orange", "outflow"),
    }.items():
        sel = mvals == val
        ax.scatter(fx[sel], fy[sel], c=col, s=3, marker="s", transform=proj,
                   label=f"{lab} ({int(sel.sum()):,})", zorder=2)

    geom = region.geometry.iloc[0]
    for pg in geom.geoms if geom.geom_type == "MultiPolygon" else [geom]:
        ax.plot(*pg.exterior.xy, color="red", lw=1.5, transform=proj, zorder=3)

    minx, miny, maxx, maxy = region.total_bounds
    pad = 2000
    ax.set_extent([minx - pad, maxx + pad, miny - pad, maxy + pad], crs=proj)
    ax.set_title("SFINCS mask  (red = region L-shape footprint)")
    ax.legend(loc="lower left", markerscale=3, framealpha=0.9)
    fig.tight_layout()
    return fig, ax


# ── Forcing (read back from the written model in read mode) ───────────────────
def plot_surge(sf):
    """Cell 39 — the surge hydrographs driving the open boundary (bzs)."""
    import matplotlib.pyplot as plt

    bzs = sf.water_level.data["bzs"]
    pt = next(d for d in bzs.dims if d != "time")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(bzs["time"], bzs.values, color="tab:blue", lw=0.4, alpha=0.4)
    ax.plot(bzs["time"], bzs.max(pt), color="navy", lw=2, label="max over boundary")
    ax.set_ylabel("water level [m+NAVD88]")
    ax.set_xlabel("time [UTC]")
    ax.set_title(f"Water-level boundary (bzs) — {bzs.sizes[pt]} points")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig, ax


def plot_wind_pressure(sf):
    """Cell 42 — ERA5 storm passage: min MSLP / max wind + the peak field."""
    import matplotlib.pyplot as plt

    w, p = sf.wind.data, sf.pressure.data
    pvar = next((v for v in ("press_2d", "press_msl", "press") if v in p.data_vars),
                list(p.data_vars)[0])
    spd = np.hypot(w["wind10_u"], w["wind10_v"])
    space = [d for d in p[pvar].dims if d != "time"]
    pmin = p[pvar].min(space) / 100.0
    wmax = spd.max(space)
    tpk = pmin.idxmin("time")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    ax1.plot(pmin["time"], pmin, color="tab:red", lw=2)
    ax1.set_ylabel("min MSLP [hPa]", color="tab:red")
    ax1.tick_params(axis="y", colors="tab:red")
    a = ax1.twinx()
    a.plot(wmax["time"], wmax, color="tab:blue", lw=2)
    a.set_ylabel("max wind speed [m/s]", color="tab:blue")
    a.tick_params(axis="y", colors="tab:blue")
    ax1.axvline(tpk.values, color="k", ls=":", alpha=0.6)
    ax1.set_xlabel("time [UTC]")
    ax1.set_title("ERA5 wind + pressure over the domain")
    ax1.grid(alpha=0.3)

    (p[pvar].sel(time=tpk) / 100.0).plot.pcolormesh(
        ax=ax2, cmap="viridis", cbar_kwargs={"label": "MSLP [hPa]", "shrink": 0.7}
    )
    ydim, xdim = p[pvar].sel(time=tpk).dims[-2:]
    s = max(1, p.sizes[xdim] // 15)
    sub = {xdim: slice(None, None, s), ydim: slice(None, None, s)}
    ax2.quiver(w[xdim][::s], w[ydim][::s],
               w["wind10_u"].sel(time=tpk).isel(sub), w["wind10_v"].sel(time=tpk).isel(sub),
               color="white", scale=500, width=0.004)
    ax2.set_title(f"MSLP + wind @ {str(tpk.values)[:16]}")
    fig.tight_layout()
    return fig, (ax1, ax2)


def plot_rain(sf):
    """Cell 45 — AORC storm-total rainfall + domain-mean hyetograph."""
    import matplotlib.pyplot as plt

    pr = sf.precipitation.data
    var = "precip_2d" if "precip_2d" in pr else list(pr.data_vars)[0]
    rain = pr[var]
    space = [d for d in rain.dims if d != "time"]
    dt_h = float((rain["time"][1] - rain["time"][0]) / np.timedelta64(1, "h"))
    accum = rain.sum("time") * dt_h
    hyeto = rain.mean(space)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    accum.plot.pcolormesh(ax=ax1, cmap="Blues",
                          cbar_kwargs={"label": "total rainfall [mm]", "shrink": 0.7})
    ax1.set_title("AORC storm-total rainfall")
    ax2.plot(hyeto["time"], hyeto, color="tab:blue", lw=2)
    ax2.fill_between(hyeto["time"].values, hyeto.values, color="tab:blue", alpha=0.2)
    ax2.set_ylabel("domain-mean rainfall [mm/hr]")
    ax2.set_xlabel("time [UTC]")
    ax2.set_title("Hyetograph")
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    return fig, (ax1, ax2)


def plot_discharge(sf):
    """Cell 48 — USGS discharge hydrographs at the two domain inflows."""
    import matplotlib.pyplot as plt

    dis = sf.discharge_points.data
    da = dis["dis"]
    pt = next(d for d in da.dims if d != "time")
    yc = next((c for c in ("y", "lat", "latitude") if c in dis.coords), None)
    names = {}
    if yc is not None and da.sizes[pt] == 2:
        order = np.argsort(dis[yc].values)
        names[int(order[0])] = "Shark River (1407705)"
        names[int(order[-1])] = "Navesink / Swimming R. (1407500)"
    fig, ax = plt.subplots(figsize=(10, 4))
    for k in range(da.sizes[pt]):
        ax.plot(da["time"], da.isel({pt: k}), lw=2, drawstyle="steps-post",
                label=names.get(k, f"point {k}"))
    ax.set_ylabel("discharge [m$^3$/s]")
    ax.set_xlabel("time [UTC]")
    ax.set_title("USGS river discharge at domain inflows")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig, ax


# ── Output (waves + flooding + validation) ───────────────────────────────────
def plot_wave_field(mod):
    """Cell 62 — SnapWave Hm0 (+ wave direction) at the peak-wave moment."""
    data = mod.output.data
    if "hm0" not in data:
        return None
    hm0 = data["hm0"]
    face = [d for d in hm0.dims if d != "time"]
    tpk = int(hm0.max(face).argmax("time"))
    wet = hm0.isel(time=tpk) > 0.1
    t = str(hm0["time"].isel(time=tpk).values)[:16]
    field = hm0.isel(time=tpk).where(wet)
    vmax = float(np.nanpercentile(field.values, 99)) or None
    fig, ax = mod.plot_basemap(
        variable=field, bmap="sat", cmap="viridis", plot_bounds=False,
        zoomlevel=11, figsize=(11, 5.2), vmin=0, vmax=vmax,
        cbar_kwargs={"shrink": 0.6, "label": "Hm0 [m]"},
    )
    ax.set_title(f"SnapWave Hm0 @ peak waves ({t}) — look for a lee behind Sandy Hook")
    return fig, ax


def plot_floodmap(mod, da_hmax):
    """Cell 70 — maximum water depth over satellite."""
    fig, ax = mod.plot_basemap(
        fn_out=None, figsize=(11, 5.2), variable=da_hmax, plot_bounds=False,
        plot_geoms=False, bmap="sat", zoomlevel=11, vmin=0, vmax=5.0,
        cbar_kwargs={"shrink": 0.6, "anchor": (0, 0)},
    )
    ax.set_title("SFINCS maximum water depth [m]")
    return fig, ax


def _sample_hwm(da_hmax, da_dep, data_dir=DATA):
    """Shared HWM sampling for the scatter + residual map (mirrors cell 74)."""
    DEPTH_MIN, GROUND_CAP = 0.15, 0.5
    hwm = gpd.read_file(str(data_dir / "validation" / "sandy_hwms.geojson")).to_crs(
        da_dep.rio.crs
    )
    depth, dep_arr, wse = da_hmax.values, da_dep.values, (da_dep + da_hmax).values
    if depth.ndim == 3:
        depth, wse, dep_arr = depth[0], wse[0], dep_arr[0]
    T = da_dep.rio.transform()
    ny, nx = wse.shape
    rad = int(round(50 / abs(T.a)))
    obs = hwm["elev_m"].values
    qual = hwm["quality"].values.astype(float)
    mod_wse = np.full(len(obs), np.nan)
    for k, (X, Y) in enumerate(zip(hwm.geometry.x.values, hwm.geometry.y.values)):
        col, row = int((X - T.c) / T.a), int((Y - T.f) / T.e)
        if 0 <= row < ny and 0 <= col < nx:
            sl = (slice(max(0, row - rad), row + rad + 1),
                  slice(max(0, col - rad), col + rad + 1))
            ws, hh, dd = wse[sl], depth[sl], dep_arr[sl]
            flooded = (hh >= DEPTH_MIN) & (dd <= obs[k] + GROUND_CAP)
            if flooded.any():
                mod_wse[k] = np.nanmax(np.where(flooded, ws, np.nan))
    wet = np.isfinite(mod_wse)
    return hwm, obs, mod_wse, mod_wse - obs, wet, qual


def plot_hwm_scatter(da_hmax, da_dep, data_dir=DATA):
    """Cell 74 — modeled still-water WSE vs USGS HWMs (1:1 scatter)."""
    import matplotlib.pyplot as plt

    hwm, obs, mod_wse, resid, wet, qual = _sample_hwm(da_hmax, da_dep, data_dir)
    q2 = qual <= 2
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(obs[wet & ~q2], mod_wse[wet & ~q2], facecolor="none", edgecolor="grey",
               s=55, lw=0.8, label="q3-4")
    sc = ax.scatter(obs[wet & q2], mod_wse[wet & q2], c=qual[wet & q2], cmap="viridis_r",
                    s=60, edgecolor="k", lw=0.4, vmin=1, vmax=5, label="q1-2 (headline)")
    lim = [1.8, 6.0]
    ax.plot(lim, lim, "k--", lw=1, label="1:1")
    ax.fill_between(lim, [x - 0.5 for x in lim], [x + 0.5 for x in lim],
                    color="grey", alpha=0.15)
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_aspect("equal")
    ax.set_xlabel("Observed HWM [m NAVD88]")
    ax.set_ylabel("Modeled still-water WSE [m NAVD88]")
    ax.set_title("Modeled still-water vs USGS HWMs")
    fig.colorbar(sc, ax=ax, shrink=0.8, label="HWM quality (1=best)")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig, ax


def plot_hwm_residual_map(mod, da_hmax, da_dep, data_dir=DATA):
    """Cell 76 — HWM residual spatial map (red over, blue under, ✕ dry)."""
    hwm, obs, mod_wse, resid, wet, qual = _sample_hwm(da_hmax, da_dep, data_dir)
    fig, ax = mod.plot_basemap(
        fn_out=None, figsize=(11, 5.2), variable=da_hmax, plot_bounds=False,
        plot_geoms=False, bmap="sat", zoomlevel=11, vmin=0, vmax=5, cmap="Blues",
        cbar_kwargs={"shrink": 0.5, "label": "Modeled depth [m]"},
    )
    hx, hy = hwm.geometry.x.values, hwm.geometry.y.values
    sc = ax.scatter(hx[wet], hy[wet], c=resid[wet], cmap="RdBu_r", vmin=-1.5, vmax=1.5,
                    s=70, edgecolor="k", lw=0.6, zorder=5)
    ax.scatter(hx[~wet], hy[~wet], marker="x", color="k", s=70, lw=1.6, zorder=6,
               label=f"model dry ({int((~wet).sum())})")
    fig.colorbar(sc, ax=ax, shrink=0.5, label="HWM residual: model − obs [m]")
    ax.legend(loc="upper right")
    ax.set_title("Sandy HWM residuals")
    fig.tight_layout()
    return fig, ax


def plot_motf(da_hmax, da_dep, data_dir=DATA):
    """Cell 78 — modeled flood vs FEMA MOTF (hit / miss / false-alarm map)."""
    import matplotlib.pyplot as plt
    import rasterio

    DEPTH_MIN = 0.15
    with rasterio.open(str(data_dir / "validation" / "sandy_motf_extent.tif")) as r:
        motf, mtf, m_nd = r.read(1), r.transform, r.nodata
    mod_t = da_dep.rio.transform()
    mh, mw = motf.shape
    Xc = mtf.c + (np.arange(mw) + 0.5) * mtf.a
    Yc = mtf.f + (np.arange(mh) + 0.5) * mtf.e
    mc = np.clip(((Xc - mod_t.c) / mod_t.a).astype(int), 0, da_dep.shape[-1] - 1)
    mr = np.clip(((Yc - mod_t.f) / mod_t.e).astype(int), 0, da_dep.shape[-2] - 1)
    rr, cc = np.meshgrid(mr, mc, indexing="ij")
    _2d = lambda a: a[0] if a.ndim == 3 else a
    dep_at, h_at = _2d(da_dep.values)[rr, cc], _2d(da_hmax.values)[rr, cc]
    motf_wet = motf == 1
    mod_wet = (h_at >= DEPTH_MIN) & np.isfinite(h_at)
    land_in = (motf != m_nd) & (dep_at > 0.0)
    hits, miss, fa = (motf_wet & mod_wet & land_in, motf_wet & ~mod_wet & land_in,
                      ~motf_wet & mod_wet & land_in)
    nh, nm, nf = int(hits.sum()), int(miss.sum()), int(fa.sum())
    PIX = mtf.a * abs(mtf.e) / 1e6
    CSI = nh / (nh + nm + nf) if (nh + nm + nf) else float("nan")
    POD = nh / (nh + nm) if (nh + nm) else 0.0
    FAR = nf / (nh + nf) if (nh + nf) else 0.0

    cat = np.zeros_like(motf, dtype="uint8")
    cat[hits], cat[miss], cat[fa] = 1, 2, 3
    cmap = ListedColormap(
        [(1, 1, 1, 0), (0.2, 0.6, 0.3, 1), (0.2, 0.4, 0.85, 1), (0.85, 0.2, 0.2, 1)]
    )
    ext = [mtf.c, mtf.c + mw * mtf.a, mtf.f + mh * mtf.e, mtf.f]
    mod_ext = [mod_t.c, mod_t.c + da_dep.shape[-1] * mod_t.a,
               mod_t.f + da_dep.shape[-2] * mod_t.e, mod_t.f]
    fig, ax = plt.subplots(figsize=(5.5, 9))
    ax.imshow(_2d(da_dep.values), extent=mod_ext, cmap="Greys", vmin=-5, vmax=20,
              alpha=0.45, origin="upper")
    ax.imshow(cat, cmap=cmap, vmin=0, vmax=3, extent=ext, origin="upper",
              interpolation="nearest")
    ax.set_aspect("equal")
    ax.set_xlim(ext[0], ext[1])
    ax.set_ylim(ext[2], ext[3])
    ax.set_xlabel("Easting [m]")
    ax.set_ylabel("Northing [m]")
    ax.legend(handles=[
        Patch(color=cmap(1), label=f"hit ({nh * PIX:.1f} km²)"),
        Patch(color=cmap(2), label=f"miss ({nm * PIX:.1f} km²)"),
        Patch(color=cmap(3), label=f"false alarm ({nf * PIX:.1f} km²)"),
    ], loc="upper right", fontsize=8)
    ax.set_title(f"Modeled flood vs FEMA MOTF — CSI={CSI:.2f}  POD={POD:.2f}  FAR={FAR:.2f}")
    fig.tight_layout()
    return fig, ax


# ── Cross-experiment comparison (share-with-supervisor) ───────────────────────
def plot_experiment_comparison(metrics_df, floodmap_dir):
    """Side-by-side max-depth flood maps for every experiment (small multiples).

    ``metrics_df`` indexed by experiment name; ``floodmap_dir`` holds
    ``<name>_hmax_lev3.tif`` copied out by the runner.
    """
    import matplotlib.pyplot as plt

    floodmap_dir = Path(floodmap_dir)
    names = list(metrics_df.index)
    n = len(names)
    ncol = min(3, n)
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(5.2 * ncol, 4.6 * nrow),
                             squeeze=False)
    for ax in axes.ravel():
        ax.axis("off")
    for k, name in enumerate(names):
        ax = axes.ravel()[k]
        tif = floodmap_dir / f"{name}_hmax_lev3.tif"
        if tif.exists():
            da = rioxarray.open_rasterio(tif, masked=True).squeeze(drop=True)
            da.where(da > 0.05).plot.imshow(ax=ax, vmin=0, vmax=5, cmap="viridis",
                                            add_colorbar=False)
        csi = metrics_df.loc[name].get("motf_csi", float("nan"))
        shb = metrics_df.loc[name].get("shb_hm0_max", float("nan"))
        ax.set_title(f"{name}\nCSI={csi:.2f}  bay Hm0max={shb:.2f} m", fontsize=9)
        ax.set_aspect("equal")
    fig.suptitle("Wave-experiment comparison — max flood depth [m]", y=1.02)
    fig.tight_layout()
    return fig, axes


# ── Engine / clamp comparison (Workstream I) ─────────────────────────────────
# The Shrewsbury-Navesink estuary and the Sea Bright barrier that feeds it.
# Everything the Faber-vs-Galibier argument turns on happens inside this window.
SHREWSBURY_WINDOW = (578500, 592000, 4462000, 4482000)  # UTM 18N (x0, x1, y0, y1)


def load_cached_floodmap(run_dir, window=SHREWSBURY_WINDOW):
    """Read the flood-depth raster ``load_floodmap`` already downscaled to disk.

    ``validate.load_floodmap`` caches ``floodmap_hmax_lev3.tif`` in the run dir but
    writes it in the model's ROTATED frame; the de-rotation and the deep-ocean mask
    happen afterwards, in memory. So repeat that tail here rather than reading the
    tif raw, or the panels will not line up with each other.

    CLIP BEFORE REPROJECTING. The L3 raster is 6596x11300 at 6.25 m, and de-rotating
    the whole thing costs minutes per run; clipping to ``window`` first drops it to
    ~0.3 s. The rotation is <1 degree, so a CRS bbox clip in the rotated frame is a
    cheap window read that comfortably contains the target area.

    Returns ``(da_hmax, da_dep)``, or ``(None, None)`` if the run has not been
    downscaled yet — a missing tif is an expected state, not an error.
    """
    run_dir = Path(run_dir)
    tif = run_dir / "floodmap_hmax_lev3.tif"
    dep_fn = run_dir / "subgrid" / "dep_subgrid_lev3.tif"
    if not tif.exists() or not dep_fn.exists():
        return None, None
    hmax = rioxarray.open_rasterio(tif, masked=True).squeeze(drop=True)
    dep = rioxarray.open_rasterio(dep_fn, masked=True).squeeze(drop=True)
    if window is not None:
        x0, x1, y0, y1 = window
        hmax = hmax.rio.clip_box(x0, y0, x1, y1)
        dep = dep.rio.clip_box(x0, y0, x1, y1)
    hmax = hmax.rio.reproject(hmax.rio.crs)      # de-rotate to north-up
    dep = dep.rio.reproject_match(hmax)
    hmax = hmax.where(dep.values > -0.5)         # drop the deep ocean
    hmax.name = "hmax"
    return hmax, dep


def _extent(da):
    """(left, right, bottom, top) for imshow, from a north-up raster."""
    x, y = da["x"].values, da["y"].values
    dx = abs(float(x[1] - x[0])) / 2 if x.size > 1 else 0.0
    dy = abs(float(y[1] - y[0])) / 2 if y.size > 1 else 0.0
    return (float(x.min()) - dx, float(x.max()) + dx,
            float(y.min()) - dy, float(y.max()) + dy)


def plot_engine_panels(runs, root=None, window=SHREWSBURY_WINDOW, vmax=3.0,
                       hwm=True, ncol=None, panel_h=7.0, data_dir=DATA):
    """Max flood depth for several runs side by side, zoomed on the estuary.

    ``runs`` maps experiment dir name -> panel title. Reads the cached tifs, so it
    is seconds rather than the minutes a re-downscale costs.

    HWMs are drawn as LOCATION markers only, deliberately uncoloured: ``elev_m`` is
    a water-surface elevation (NAVD88) while the raster is a depth, so putting them
    on one colour scale would look meaningful and mean nothing. For the signed
    model-minus-obs residual use ``plot_hwm_residual_map``.
    """
    import matplotlib.pyplot as plt

    root = Path(root) if root is not None else ROOT / "experiments"
    n = len(runs)
    # The domain is tall and narrow (~12 x 20 km), so one row reads best and keeps
    # the panels genuinely side by side. Size each panel to the window's aspect,
    # otherwise most of the figure is whitespace.
    ncol = ncol or min(4, n)
    nrow = int(np.ceil(n / ncol))
    aspect = (window[1] - window[0]) / (window[3] - window[2])
    fig, axes = plt.subplots(nrow, ncol,
                             figsize=(panel_h * aspect * ncol + 1.6, panel_h * nrow),
                             squeeze=False, constrained_layout=True)

    pts = None
    if hwm:
        f = Path(data_dir) / "validation" / "sandy_hwms.geojson"
        if f.exists():
            pts = gpd.read_file(str(f)).to_crs("EPSG:32618")
            pts = pts[pts["quality"].astype(float) <= 2]

    im = None
    for ax, (run, title) in zip(axes.ravel(), runs.items()):
        hmax, dep = load_cached_floodmap(root / run, window=window)
        if hmax is None:
            ax.text(0.5, 0.5, f"{run}\n\nnot downscaled yet", ha="center",
                    va="center", transform=ax.transAxes, fontsize=10, color="0.4")
            ax.set_xticks([]); ax.set_yticks([])
            continue
        ext = _extent(hmax)
        # land/water context so dry ground is legible instead of blank white
        ax.imshow(dep.values, extent=ext, origin="upper", cmap="Greys_r",
                  vmin=-15, vmax=25, alpha=0.55, interpolation="nearest")
        im = ax.imshow(np.where(hmax.values > 0.05, hmax.values, np.nan), extent=ext,
                       origin="upper", cmap="Blues", vmin=0, vmax=vmax,
                       interpolation="nearest")
        if pts is not None:
            ax.scatter(pts.geometry.x, pts.geometry.y, facecolor="none",
                       edgecolor="red", s=30, linewidth=0.8, zorder=5)
        ax.set_title(title, fontsize=10)
        ax.set_xlim(window[0], window[1]); ax.set_ylim(window[2], window[3])
        ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])

    for ax in axes.ravel()[n:]:
        ax.axis("off")
    if im is not None:
        cb = fig.colorbar(im, ax=axes, shrink=0.55, anchor=(0, 0.5))
        cb.set_label("max flood depth [m]")
    fig.suptitle("Where the engines flood — Shrewsbury / Navesink estuary\n"
                 "(red circles = USGS high-water-mark locations, quality ≤ 2)",
                 fontsize=12)
    return fig, axes


def plot_engine_difference(run_a, run_b, root=None, window=SHREWSBURY_WINDOW,
                           vlim=1.5, label_a=None, label_b=None):
    """Depth difference b − a: WHERE one engine puts water the other does not.

    Both runs must sit on the same mesh (they do, on the frozen 25 m grid), so the
    cached rasters share a grid and subtract cleanly. Cells dry in both are masked.
    """
    import matplotlib.pyplot as plt

    root = Path(root) if root is not None else ROOT / "experiments"
    ha, dep = load_cached_floodmap(root / run_a, window=window)
    hb, _ = load_cached_floodmap(root / run_b, window=window)
    if ha is None or hb is None:
        raise FileNotFoundError(
            f"missing cached floodmap for {run_a if ha is None else run_b} — "
            "run validate.load_floodmap() on it first"
        )
    hb = hb.rio.reproject_match(ha)
    # A cell dry in one run and wet in the other is the whole point, so treat dry as
    # depth 0 rather than NaN; masking only where BOTH are dry keeps those cells in.
    a = np.where(np.isfinite(ha.values), ha.values, 0.0)
    b = np.where(np.isfinite(hb.values), hb.values, 0.0)
    diff = np.where((a > 0.05) | (b > 0.05), b - a, np.nan)

    ext = _extent(ha)
    fig, ax = plt.subplots(figsize=(9.5, 8.4), constrained_layout=True)
    ax.imshow(dep.values, extent=ext, origin="upper", cmap="Greys_r",
              vmin=-15, vmax=25, alpha=0.55, interpolation="nearest")
    im = ax.imshow(diff, extent=ext, origin="upper", cmap="RdBu_r",
                   vmin=-vlim, vmax=vlim, interpolation="nearest")
    fig.colorbar(im, ax=ax, shrink=0.7).set_label("Δ max flood depth [m]")
    ax.set_xlim(window[0], window[1]); ax.set_ylim(window[2], window[3])
    ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    lb, la = label_b or run_b, label_a or run_a
    ax.set_title(f"{lb}  −  {la}\nred = deeper in {lb}   ·   blue = deeper in {la}",
                 fontsize=11)
    return fig, ax
