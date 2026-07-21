"""Time-varying views of a finished run — animations and interactive browsers.

WHY THIS IS NOT IN ``plots.py``. Everything in ``plots`` draws ONE moment: a max, a
peak, a before/after pair. Those all read a face-indexed field and hand it straight to
matplotlib as a ``PolyCollection`` of 547k quads, which is fine once. Doing it 73 times
for an animation is not — you would rebuild the same half-million polygons every frame.

THE TRICK THAT MAKES THIS FAST. The quadtree is FIXED for a run: only the face VALUES
change with time. So rasterize the face *indices* once (``ugrid.rasterize`` on
``arange(nface)``, ~0.6 s) and every subsequent frame is a fancy-index lookup
``values[idx]`` — about 1 ms. A full 73-frame stack costs under a second, versus the
minutes a per-frame mesh render would. The same index raster serves the animation, the
interactive browser, and any still you want out of the series.

The rasterized indices are exact (xugrid locates each pixel centre in the cell tree and
returns that face's value verbatim — no interpolation), so a pixel is its cell's value,
not a blend of neighbours. Coarse quadtree cells simply cover more pixels.

Read ``resolution`` as the raster pixel size in metres, NOT the mesh resolution. The
mesh is 25 m at its finest; asking for 25 m over the whole 71 x 42 km domain is a
2842 x 1684 image per frame and pointless on a screen. Default to something matched to
the window you are looking at — the helpers below do that for you.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr
import xugrid as xu

from .config import ROOT

# Named map windows (x0, x1, y0, y1) in UTM 18N metres. ``None`` = the whole domain
# (~71 x 42 km). SHREWSBURY mirrors plots.SHREWSBURY_WINDOW — the estuary the leak
# used to drain, and the window every engine argument turns on.
WINDOWS = {
    "domain": None,
    "shrewsbury": (578500, 592000, 4462000, 4482000),
    # The bay + the wave lee. Stops at x=592000 because that is roughly where the
    # SnapWave field itself stops: SnapWave runs on a sub-domain of the hydro mesh
    # (snapwavemsk), so everything east of ~590 km is nodata in hm0 and would just be
    # blank canvas. The bright band at that edge is the wave INFLOW boundary, ~8 m of
    # imposed offshore Hm0 — real forcing, not a spike, but it will sit at the top of
    # any colour scale that includes it.
    "sandy_hook": (574000, 592000, 4468000, 4486000),
    "shark": (573000, 588000, 4442000, 4456000),        # the carved-open inlet
}

# label -> (long name, colour map, unit, default vmax). ``depth`` is derived
# (zs - zb); the rest are read straight off the map file. ``None`` vmax = pick the
# 99th percentile of the window at draw time.
#
# depth's 3.0 m is FIXED, not a percentile, and matches plots.plot_engine_panels so
# the animation and the still panels are on one scale. A percentile here reads the
# 15-28 m of open ocean in frame and stretches the ramp so far that the 0.5-2 m of
# actual flooding — the entire point — renders as near-white.
FIELDS = {
    "depth": ("water depth", "Blues", "m", 3.0),
    "zs": ("water-surface elevation", "viridis", "m+NAVD88", None),
    "hm0": ("SnapWave Hm0", "magma", "m", None),
    "hm0ig": ("infragravity Hm0", "magma", "m", None),
    "tp": ("peak wave period", "cividis", "s", None),
}


def _run_dir(run, root=None) -> Path:
    """Accept an experiment NAME or an explicit path, like the plots helpers do."""
    p = Path(run)
    if p.is_dir() and (p / "sfincs_map.nc").is_file():
        return p
    return (Path(root) if root else ROOT / "experiments") / str(run)


# The index raster is the one genuinely expensive step (~0.6 s), and a notebook
# re-renders the same window over and over while tuning a colour scale. Key on the
# things that change its geometry.
_INDEX_CACHE: dict[tuple, tuple] = {}


def face_index_raster(run, root=None, resolution=100.0, window=None):
    """Map each output pixel to the mesh face that covers it.

    Returns ``(idx, valid, extent)`` — an int array of face indices, the bool array
    saying which pixels actually landed on a face (outside the mesh they did not), and
    an imshow ``extent``. Feed a face-indexed field through it with
    ``np.where(valid, field[idx], np.nan)``.
    """
    rd = _run_dir(run, root)
    win = WINDOWS.get(window, window) if isinstance(window, str) else window
    key = (str(rd), float(resolution), win)
    if key in _INDEX_CACHE:
        return _INDEX_CACHE[key]

    ds = xu.open_dataset(rd / "sfincs_map.nc")
    nface = ds.sizes["nmesh2d_face"]
    # Rasterize the face NUMBERS, not a physical field: this is the lookup table.
    # ugrid.rasterize needs a float field, and 547k is exactly representable.
    tmpl = ds["zb"].copy(data=np.arange(nface, dtype=np.float64))
    r = tmpl.ugrid.rasterize(resolution=float(resolution))
    ds.close()

    if win is not None:
        x0, x1, y0, y1 = win
        r = r.sel(x=slice(x0, x1), y=slice(y1, y0))   # y descends in the raster
    v = r.values
    valid = np.isfinite(v)
    idx = np.where(valid, v, 0).astype(np.int64)

    x, y = r["x"].values, r["y"].values
    hx = abs(float(x[1] - x[0])) / 2 if x.size > 1 else 0.0
    hy = abs(float(y[1] - y[0])) / 2 if y.size > 1 else 0.0
    extent = (x.min() - hx, x.max() + hx, y.min() - hy, y.max() + hy)

    out = (idx, valid, extent)
    _INDEX_CACHE[key] = out
    return out


def field_frames(run, var="depth", root=None, resolution=100.0, window=None,
                 hmin=0.05, every=1, mask_ocean=None):
    """Rasterize a time-varying field into a ``(nt, ny, nx)`` stack.

    ``var`` is a key of ``FIELDS``. ``depth`` is derived as ``zs - zb`` and masked
    below ``hmin`` so dry ground reads as nodata rather than a film of blue; wave
    fields are masked at ``hmin`` too, which drops the flat 0 m of dry land.

    ``mask_ocean`` blanks cells whose bed is below −0.5 m — the same "drop the deep
    ocean" cut ``load_cached_floodmap`` makes. It defaults ON for ``depth``, where
    the permanently-wet shelf is not flooding and only competes for the eye, and OFF
    for the wave fields, which live out there. Set it explicitly to override.

    ``every`` subsamples time (``every=2`` = every other hour) for a shorter loop.

    Returns ``(frames, times, extent, zb_img)`` — the stack, its timestamps, the
    imshow extent, and the bed level on the same grid for use as a land/sea backdrop.
    """
    if var not in FIELDS:
        raise KeyError(f"unknown field {var!r} — choose from {sorted(FIELDS)}")
    rd = _run_dir(run, root)
    idx, valid, extent = face_index_raster(rd, resolution=resolution, window=window)

    ds = xr.open_dataset(rd / "sfincs_map.nc")
    src = "zs" if var == "depth" else var
    if src not in ds:
        ds.close()
        raise KeyError(f"{rd.name} has no {src!r} field (waves off, or an older run)")

    da = ds[src].isel(time=slice(None, None, every))
    times = da["time"].values
    zb = ds["zb"].values
    # One eager read of the whole (nt, nface) field: it is ~160 MB and the netCDF is
    # chunked (1, nface), so this is a clean sequential pass. Slicing it per frame
    # instead would re-open and re-decompress each chunk.
    vals = da.values
    ds.close()

    if var == "depth":
        vals = vals - zb[None, :]
    if mask_ocean is None:
        mask_ocean = var == "depth"
    keep = valid & (zb[idx] > -0.5) if mask_ocean else valid

    frames = np.where(keep[None, :, :], vals[:, idx], np.nan)
    if hmin is not None:
        frames = np.where(frames > hmin, frames, np.nan)
    zb_img = np.where(valid, zb[idx], np.nan)
    return frames, times, extent, zb_img


def animate_field(run, var="depth", root=None, window="shrewsbury", resolution=None,
                  vmax=None, every=1, fps=6, figsize=(9.0, 8.0), title=None):
    """Animate a field over the run, as an inline JS player.

    Returns a matplotlib ``FuncAnimation``. In a notebook show it with
    ``IPython.display.HTML(anim.to_jshtml())`` — a self-contained player with a
    scrubber and no ffmpeg dependency (the env has none). ``anim.save(path)`` also
    writes a GIF via pillow.

    ``resolution`` defaults to roughly 1/500th of the window's width, which keeps a
    frame near 500 px across — enough to read on screen, cheap enough that the whole
    series builds in about a second.
    """
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    win = WINDOWS.get(window, window) if isinstance(window, str) else window
    if resolution is None:
        resolution = round((win[1] - win[0]) / 500.0, -1) if win else 100.0
    frames, times, extent, zb_img = field_frames(
        run, var, root=root, resolution=resolution, window=win, every=every
    )
    long_name, cmap, unit, default_vmax = FIELDS[var]
    if vmax is None:
        vmax = default_vmax
    if vmax is None:
        # Percentile, not the max: a single boundary cell can spike a wave field and
        # would flatten the whole colour scale onto one pixel.
        finite = frames[np.isfinite(frames)]
        vmax = float(np.percentile(finite, 99)) if finite.size else 1.0

    fig, ax = plt.subplots(figsize=figsize, constrained_layout=True)
    ax.imshow(zb_img, extent=extent, origin="upper", cmap="Greys_r",
              vmin=-15, vmax=25, alpha=0.55, interpolation="nearest")
    im = ax.imshow(frames[0], extent=extent, origin="upper", cmap=cmap,
                   vmin=0, vmax=vmax, interpolation="nearest")
    ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    fig.colorbar(im, ax=ax, shrink=0.7).set_label(f"{long_name} [{unit}]")
    head = title or f"{_run_dir(run, root).name} — {long_name}"
    ttl = ax.set_title(f"{head}\n{str(times[0])[:16]} UTC", fontsize=11)

    def _draw(k):
        im.set_data(frames[k])
        ttl.set_text(f"{head}\n{str(times[k])[:16]} UTC")
        return im, ttl

    anim = FuncAnimation(fig, _draw, frames=len(frames),
                         interval=1000 / fps, blit=False)
    plt.close(fig)          # the player is the output; don't also emit a still
    return anim


def explore_field(run, var="depth", root=None, window="sandy_hook", resolution=None,
                  every=1, frame_width=650, tiles="EsriImagery"):
    """Interactive time-slider browser for a field, over satellite tiles (hvplot).

    Pan, zoom, and scrub time with a slider; hovering reads the value out. Same index
    raster underneath, so the whole series is in memory and the slider is instant —
    it is not re-reading the map file per frame.
    """
    import hvplot.xarray  # noqa: F401
    import rioxarray  # noqa: F401

    win = WINDOWS.get(window, window) if isinstance(window, str) else window
    if resolution is None:
        resolution = round((win[1] - win[0]) / 500.0, -1) if win else 100.0
    frames, times, extent, _ = field_frames(
        run, var, root=root, resolution=resolution, window=win, every=every
    )
    long_name, cmap, unit, default_vmax = FIELDS[var]

    nt, ny, nx = frames.shape
    x = np.linspace(extent[0], extent[1], nx, endpoint=False) + (extent[1] - extent[0]) / nx / 2
    y = np.linspace(extent[3], extent[2], ny, endpoint=False) - (extent[3] - extent[2]) / ny / 2
    da = xr.DataArray(frames, dims=("time", "y", "x"),
                      coords={"time": times, "y": y, "x": x}, name=var)
    # Tiles are web-mercator; reproject once here rather than per frame in the browser.
    da = da.rio.write_crs("EPSG:32618").rio.reproject("EPSG:3857", nodata=np.nan)

    finite = frames[np.isfinite(frames)]
    vmax = default_vmax or (float(np.percentile(finite, 99)) if finite.size else 1.0)
    return da.hvplot.image(
        x="x", y="y", groupby="time", cmap=cmap, clim=(0, vmax),
        tiles=tiles, frame_width=frame_width, rasterize=True,
        widget_location="bottom", dynamic=True,
        title=f"{_run_dir(run, root).name} — {long_name}",
        clabel=f"{long_name} [{unit}]",
    )
