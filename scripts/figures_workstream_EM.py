"""HWM-residual and FEMA-MOTF panel figures for the Shrewsbury report.

Four runs, in the order the report tells the story:

  snapwave_tuned_25m   the BROKEN premier  (leaking Navesink + dammed Shark inlet)
  sealed_faber_waves   the SEALED premier  (adopted, Workstream O)
  sealed_bdepth_m20    Workstream M        (mask_zmin -20 m)
  sealed_igwaves_wind  Workstream E        (premier + snapwave_igwaves=1)

Deliberate choices:
  * NO basemap tiles. plots.plot_hwm_residual_map uses bmap="sat", which needs network
    from a compute node. The subgrid DEM is the backdrop instead -- and it is the more
    honest one anyway, since the DEM is what the dam/leak defects live in.
  * IDENTICAL scales on every panel (HWM +/-1.5 m; the same MOTF categories). Small
    multiples with per-panel scales are unreadable as a comparison.
  * The MOTF hit/miss/false-alarm colours match the existing reports/figures/motf_panels.png
    and the report's prose ("the blue miss areas ... have turned to hits"). Do not restyle
    without re-reading the text.

SPEED -- read this before "fixing" the loader. Do NOT use validate.load_floodmap here. It
re-runs downscale_floodmap on every call even when the tif is already cached, and then
de-rotates the whole 6596x11300 L3 raster: minutes per run, ~8 min for four. plots.
load_cached_floodmap reads the cached tif and CLIPS BEFORE REPROJECTING, which is the
whole trick (its docstring: minutes -> ~0.3 s). We clip to the validation area -- the
union of the FEMA MOTF extent and the HWM points -- because that is all either figure
shows; the rest of the domain is de-rotated for nothing. Requires each run to have been
scored once already (floodmap_hmax_lev3.tif present); a missing tif is reported, not
silently skipped.

The "Transform that is non-rectilinear or with rotation found" UserWarnings are expected
and benign: the cached tif lives in the model's rotated frame and the de-rotation is what
emits them. The quadtree rotation is <1 degree.

Run:
  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/figures_workstream_EM.py
"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import matplotlib

matplotlib.use("Agg")

import time

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

import geopandas as gpd

import nj_sfincs  # noqa: F401  (pyproj primer)
from nj_sfincs.config import DATA, ROOT
from nj_sfincs.plots import _sample_hwm, load_cached_floodmap


EXP = ROOT / "experiments"
FIG = ROOT / "reports" / "figures"


def validation_window(margin: float = 1500.0):
    """(x0, x1, y0, y1) covering everything either figure draws, in the model CRS.

    The union of the FEMA MOTF extent and the HWM marks. Clipping to this before the
    de-rotation is what makes the script fast (see the module docstring).
    """
    with rasterio.open(str(DATA / "validation" / "sandy_motf_extent.tif")) as r:
        b, crs = r.bounds, r.crs
    hb = gpd.read_file(str(DATA / "validation" / "sandy_hwms.geojson")).to_crs(crs).total_bounds
    return (min(b.left, hb[0]) - margin, max(b.right, hb[2]) + margin,
            min(b.bottom, hb[1]) - margin, max(b.top, hb[3]) + margin)

RUNS = [
    ("snapwave_tuned_25m", "BROKEN premier\n(leak + dammed Shark)"),
    ("sealed_faber_waves", "SEALED premier\n(adopted)"),
    ("sealed_bdepth_m20", "M — boundary $z_{min}$ = −20 m"),
    ("sealed_igwaves_wind", "E — infragravity ON"),
]

DEPTH_MIN = 0.15
RESID_LIM = 1.5

# hit / miss / false-alarm — the house palette (see module docstring)
MOTF_CMAP = ListedColormap(
    [(1, 1, 1, 0), (0.2, 0.6, 0.3, 1), (0.2, 0.4, 0.85, 1), (0.85, 0.2, 0.2, 1)]
)


def _2d(a):
    return a[0] if a.ndim == 3 else a


def _extent(da):
    t = da.rio.transform()
    return [t.c, t.c + da.shape[-1] * t.a, t.f + da.shape[-2] * t.e, t.f]


def hwm_panel(ax, da_hmax, da_dep, title):
    """One HWM residual panel: DEM backdrop + marks coloured by model − obs.

    NO BIAS NUMBER IN THE TITLE, deliberately. ``hwm_metrics`` does not return the same
    answer on a CLIPPED raster as on the full one, and we do not yet know why: on
    snapwave_tuned_25m the full path gives bias -0.090 / RMSE 0.696 (which is what every
    CSV, table and report in this project quotes) while the identical call on the clipped
    raster this script loads gives +0.024 / 0.468. The sealed runs happen to agree to
    ~0.01 m, so the disagreement is not a constant offset either. It is NOT the sampling
    radius -- clipped and full both come back at 6.2495 m/px, i.e. an 8 px radius.

    Until that is explained, this figure shows the spatial PATTERN and the tables carry
    the NUMBERS. Putting a clip-derived bias in the caption would silently contradict the
    table printed beside it, and the whole point of the panel is to be trustworthy at a
    glance. See "What is still open" in the Shrewsbury report.
    """
    hwm, obs, mod_wse, resid, wet, qual = _sample_hwm(da_hmax, da_dep, DATA)
    q2 = qual <= 2  # headline marks only, as in the metrics
    ax.imshow(_2d(da_dep.values), extent=_extent(da_dep), cmap="Greys",
              vmin=-5, vmax=20, alpha=0.45, origin="upper")
    hx, hy = hwm.geometry.x.values, hwm.geometry.y.values
    sel = wet & q2
    sc = ax.scatter(hx[sel], hy[sel], c=resid[sel], cmap="RdBu_r",
                    vmin=-RESID_LIM, vmax=RESID_LIM, s=46, edgecolor="k",
                    lw=0.5, zorder=5)
    dry = (~wet) & q2
    ax.scatter(hx[dry], hy[dry], marker="x", color="k", s=46, lw=1.5, zorder=6)
    ax.set_title(f"{title}\n✕ model dry: {int(dry.sum())}", fontsize=9)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    return sc, int(dry.sum())


def motf_panel(ax, da_hmax, da_dep, title):
    """One MOTF panel: hits / misses / false alarms against the FEMA extent."""
    with rasterio.open(str(DATA / "validation" / "sandy_motf_extent.tif")) as r:
        motf, mtf, m_nd = r.read(1), r.transform, r.nodata
    mod_t = da_dep.rio.transform()
    mh, mw = motf.shape
    Xc = mtf.c + (np.arange(mw) + 0.5) * mtf.a
    Yc = mtf.f + (np.arange(mh) + 0.5) * mtf.e
    mc = np.clip(((Xc - mod_t.c) / mod_t.a).astype(int), 0, da_dep.shape[-1] - 1)
    mr = np.clip(((Yc - mod_t.f) / mod_t.e).astype(int), 0, da_dep.shape[-2] - 1)
    rr, cc = np.meshgrid(mr, mc, indexing="ij")
    dep_at, h_at = _2d(da_dep.values)[rr, cc], _2d(da_hmax.values)[rr, cc]

    motf_wet = motf == 1
    mod_wet = (h_at >= DEPTH_MIN) & np.isfinite(h_at)
    land_in = (motf != m_nd) & (dep_at > 0.0)
    hits, miss, fa = (motf_wet & mod_wet & land_in,
                      motf_wet & ~mod_wet & land_in,
                      ~motf_wet & mod_wet & land_in)
    nh, nm, nf = int(hits.sum()), int(miss.sum()), int(fa.sum())
    PIX = mtf.a * abs(mtf.e) / 1e6
    csi = nh / (nh + nm + nf) if (nh + nm + nf) else float("nan")
    pod = nh / (nh + nm) if (nh + nm) else float("nan")
    far = nf / (nh + nf) if (nh + nf) else float("nan")

    cat = np.zeros_like(motf, dtype="uint8")
    cat[hits], cat[miss], cat[fa] = 1, 2, 3
    ext = [mtf.c, mtf.c + mw * mtf.a, mtf.f + mh * mtf.e, mtf.f]
    ax.imshow(_2d(da_dep.values), extent=_extent(da_dep), cmap="Greys",
              vmin=-5, vmax=20, alpha=0.45, origin="upper")
    ax.imshow(cat, cmap=MOTF_CMAP, vmin=0, vmax=3, extent=ext, origin="upper",
              interpolation="nearest")
    ax.set_xlim(ext[0], ext[1])
    ax.set_ylim(ext[2], ext[3])
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"{title}\nCSI {csi:.2f}  POD {pod:.2f}  FAR {far:.2f}", fontsize=9)
    return nm * PIX


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    window = validation_window()
    loaded = []
    for run, label in RUNS:
        t0 = time.time()
        hmax, dep = load_cached_floodmap(EXP / run, window=window)
        if hmax is None:
            raise SystemExit(
                f"{run}: floodmap_hmax_lev3.tif missing — score the run once first "
                f"(nj_sfincs.validate.evaluate) so the raster is cached."
            )
        loaded.append((run, label, hmax, dep))
        print(f"loaded {run} in {time.time() - t0:.1f}s", flush=True)

    # ── HWM residuals ────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 4, figsize=(17, 6.4))
    sc = None
    for ax, (run, label, hmax, dep) in zip(axes, loaded):
        sc, _ = hwm_panel(ax, hmax, dep, label)
    cb = fig.colorbar(sc, ax=axes, shrink=0.62, pad=0.015)
    cb.set_label("HWM residual: model − obs [m]   (red = model too high)")
    fig.suptitle("Sandy high-water-mark residuals (q≤2) — ✕ = model left the mark dry",
                 fontsize=11, y=0.97)
    out = FIG / "hwm_panels_EM.png"
    fig.savefig(out, dpi=135, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}", flush=True)

    # ── MOTF extent ──────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 4, figsize=(15, 8.6))
    for ax, (run, label, hmax, dep) in zip(axes, loaded):
        motf_panel(ax, hmax, dep, label)
    fig.legend(handles=[Patch(color=MOTF_CMAP(1), label="hit"),
                        Patch(color=MOTF_CMAP(2), label="miss (model dry, FEMA wet)"),
                        Patch(color=MOTF_CMAP(3), label="false alarm")],
               loc="lower center", ncol=3, frameon=False, fontsize=10,
               bbox_to_anchor=(0.5, 0.02))
    fig.suptitle("Modeled flood extent vs FEMA MOTF observed extent", fontsize=11, y=0.97)
    out = FIG / "motf_panels_EM.png"
    fig.savefig(out, dpi=135, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
