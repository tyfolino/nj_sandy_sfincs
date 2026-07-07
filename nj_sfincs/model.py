"""Build the NJ Sandy quadtree SFINCS model, in pure functions.

Lifted verbatim (behaviour-preserving) from notebooks/sfincs-nj-sandy.ipynb:

* ``build_static``  — Phase 1, cells 9–33 (grid, elevation, mask, boundary,
  obs points, roughness, subgrid) → written once into a template dir.
* ``add_forcing``   — Phase 2, cells 38–50 (window + surge, wind/pressure, rain,
  discharge, infiltration).
* ``add_waves``     — Phase 2 cell 52 (the SnapWave block), extended with Tim's
  physics params + the optional ocean-side wavemaker.
* ``finalize``      — Phase 2 cell 54 (release handles, write, patch sfincs.inp,
  write the SnapWave ASCII forcing).

The NJ-Sandy-specific coordinate boxes (bay include, boundary corrections) are
kept as module constants with the original comments — re-derive them for a
different NJ region (see notebook Appendix A).
"""

from __future__ import annotations

import gc
import os
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
import xarray as xr
from hydromt import log
from hydromt_sfincs import SfincsModel
from shapely.geometry import Point

from .config import BaseConfig, WaveConfig

# HDF5/netCDF file locking off before any netCDF-backed write on /cache (a failed
# lock surfaces as a misleading "NetCDF: Permission denied"). Mirrors the notebook.
os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")

# ── NJ-Sandy geographic constants (UTM 18N; re-derive for another region) ─────
# Force Raritan / Sandy Hook Bay active at any depth so the dredged channels
# (-11..-27 m) don't punch inactive holes through the bay interior.
BAY_INCLUDE_BOX_LL = (-74.28, 40.40, -73.95, 40.52)
# Support-point / snapwave-boundary northing cut = the Sandy Hook tip.
SANDY_HOOK_TIP_Y = 4_476_000


def build_static(base: BaseConfig, template_dir: Path) -> None:
    """Phase 1 — build grid/elevation/mask/subgrid and write to ``template_dir``.

    Forcing-independent, so it runs once; ``add_forcing`` reopens from disk.
    """
    template_dir = Path(template_dir)
    template_dir.mkdir(parents=True, exist_ok=True)

    # Reproducibility short-circuit: the quadtree grid+subgrid build is
    # environment-sensitive — two builds of identical code/config can differ by
    # ~18 cells, which shifts CSI ~0.04 (notebook 0.54 vs harness 0.50; see
    # project memory). If a frozen static mesh is provided, copy it verbatim so
    # every run — harness AND notebook — shares ONE identical grid. Freeze once
    # with scripts/freeze_mesh.py; point BaseConfig.frozen_mesh at the result.
    if base.frozen_mesh is not None:
        frozen = Path(base.frozen_mesh)
        if not (frozen / "sfincs.inp").exists():
            raise FileNotFoundError(
                f"BaseConfig.frozen_mesh={frozen} has no sfincs.inp — "
                f"build it first with scripts/freeze_mesh.py"
            )
        print(f"[build_static] reusing frozen mesh from {frozen} (no rebuild)")
        shutil.copytree(frozen, template_dir, dirs_exist_ok=True)
        return

    log.initialize_logging()
    log.set_log_level(log_level=30)  # warnings + errors only (quiet build)
    log.to_file(template_dir / "hydromt_sfincs.log", append=False)

    sf = SfincsModel(
        data_libs=base.data_libs, root=str(template_dir), mode="w+", write_gis=True
    )

    # 2. Quadtree grid --------------------------------------------------------
    refinement_gdf = gpd.read_file(base.refinement)
    sf.quadtree_grid.create_from_region(
        region={"geom": str(base.region)},
        res=base.base_res,
        rotated=base.rotated,
        crs=base.crs,
        refinement_polygons=refinement_gdf,
        elevation_list=base.elevation(),
    )

    # 3. Elevation ------------------------------------------------------------
    sf.quadtree_elevation.create(
        elevation_list=base.elevation(), buffer_cells=0, nrmax=2000
    )

    # 4. Active mask ----------------------------------------------------------
    bay_include = gpd.GeoDataFrame(
        geometry=[shapely.box(*BAY_INCLUDE_BOX_LL)], crs=4326
    )
    sf.quadtree_mask.create_active(zmin=base.mask_zmin, include_polygon=bay_include)

    # Clip the active mask to the region polygon (the rotated grid fills the L's
    # bounding box; drop the dry inland cells in the concave notch). Mask-only.
    _region = gpd.read_file(base.region).to_crs(sf.crs).geometry.iloc[0]
    fx, fy = sf.quadtree_grid.data.grid.face_coordinates.T
    _outside = ~shapely.contains_xy(_region, fx, fy)
    mask = sf.quadtree_grid.data["mask"].values.copy()
    mask[_outside] = 0
    sf.quadtree_grid.data["mask"] = sf.quadtree_grid.data["mask"].copy(data=mask)

    # 5. Boundary cells -------------------------------------------------------
    sf.quadtree_mask.create_boundary(btype="waterlevel", zmax=-1, reset_bounds=True)
    sf.quadtree_mask.create_boundary(
        btype="outflow", zmin=-1, zmax=2, reset_bounds=False
    )

    # region-specific geographic corrections (NJ-Sandy; UTM 18N)
    mask = sf.quadtree_grid.data["mask"].values.copy()
    fx, fy = sf.quadtree_grid.data.grid.face_coordinates.T
    west_below_bay = (fx < 582_500) & (fy < 4_474_000)  # (a)
    shrewsbury = (
        (fx > 586_500) & (fx < 587_400) & (fy > 4_467_000) & (fy < 4_472_000)
    )  # (b)
    arthur_kill_north = fy > 4_484_000  # (c)
    mask[(mask == 2) & west_below_bay] = 3  # waterlevel → outflow
    mask[(mask == 2) & shrewsbury] = 1  # waterlevel → active interior
    mask[(mask == 3) & arthur_kill_north] = 2  # outflow → waterlevel (harbor-driven)
    sf.quadtree_grid.data["mask"] = sf.quadtree_grid.data["mask"].copy(data=mask)

    # 6. Observation points (validation gauges only) --------------------------
    val_gauges = gpd.GeoDataFrame(
        {
            "name": [
                "sandy_hook",
                "usgs_stormtide_sea_bright",
                "usgs_tidal_sea_bright",
                "usgs_tidal_shark_river",
            ]
        },
        geometry=[
            Point(-74.0091, 40.4669),  # NOAA 8531680
            Point(-73.97304, 40.37222),  # USGS storm-tide (co-located)
            Point(-73.97494, 40.36557),  # USGS 1407600 (nudged 21 m into the -4.2 m channel cell; the raw gauge coord lands on a +1.46 m bank cell → dry-at-low-tide, invalid gauge/tidal signal)
            Point(-74.0261, 40.1856),  # USGS 1407770
        ],
        crs="EPSG:4326",
    )
    sf.observation_points.create(locations=val_gauges, merge=False)

    # 7. Roughness + subgrid (memory/CPU peak) --------------------------------
    for src in list(sf.data_catalog.sources):
        s = sf.data_catalog.get_source(src)
        if hasattr(s, "_data"):
            s._data = None
    gc.collect()

    roughness_list = [{"lulc": "nlcd_2012", "reclass_table": str(base.reclass_table)}]
    sf.quadtree_roughness.create(roughness_list=roughness_list, nrmax=200)
    sf.quadtree_subgrid.create(
        elevation_list=base.elevation(),
        roughness_list=roughness_list,
        nr_subgrid_pixels=base.nr_subgrid_pixels,
        nrmax=2000,  # DO NOT lower — smaller explodes the block loop
        write_dep_tif=True,  # per-level subgrid DEMs (flood-map downscale)
        write_man_tif=True,
    )

    # 8. Write ----------------------------------------------------------------
    sf.write()
    del sf
    gc.collect()


def add_forcing(base: BaseConfig, sf: SfincsModel) -> None:
    """Phase 2 — window + physics flags and every compound forcing (no waves)."""
    sf.config.update(
        {
            "tref": base.tref,
            "tstart": base.tstart,
            "tstop": base.tstop,
            "tspinup": 3600.0,
            "coriolis": 1,
            "latitude": base.latitude,
            "advection": 1,
            "dtmapout": 3600.0,  # map output every hour
            "dtmaxout": 86400.0,  # one zsmax over the whole run
            "dthisout": 600.0,  # his output every 10 min
        }
    )

    sf.water_level.create(
        geodataset=base.waterlevel_geodataset,
        buffer=base.waterlevel_buffer,
        merge=False,
    )
    sf.wind.create(wind="era5_nj")
    sf.pressure.create(press="era5_nj")
    sf.precipitation.create(
        precip="aorc_sandy_nj", cumulative_input=True, aggregate=False
    )
    sf.discharge_points.create(geodataset="usgs_sandy_discharge", merge=False)
    sf.quadtree_infiltration.create_cn(cn="cn_nj", antecedent_moisture=None, nrmax=2000)


def add_waves(wcfg: WaveConfig, base: BaseConfig, sf: SfincsModel) -> dict:
    """Phase 2 cell 52 — the SnapWave block. Returns the ASCII boundary arrays.

    Adds Tim's physics params when ``wcfg.tune_physics`` and the ocean-side
    wavemaker when ``wcfg.wavemaker`` (both no-ops otherwise, so the default
    ``wind_waves`` preset reproduces the notebook byte-for-byte).
    """
    # X1 SnapWave: the wave solver shares the SFINCS mesh. Overwrite the fresh
    # snapwave_mask with the SFINCS mask so waves + hydrodynamics use one mesh.
    sf.quadtree_snapwave_mask.create_active(zmin=base.mask_zmin)
    sf.quadtree_grid.data["snapwave_mask"] = sf.quadtree_grid.data[
        "snapwave_mask"
    ].copy(data=sf.quadtree_grid.data["mask"].values.copy())

    # Incident-wave boundary = the OPEN-ATLANTIC edge only. Demote every snapwave
    # boundary cell north of the Sandy Hook tip back to active interior, so
    # incident waves don't run away into the enclosed NW corner (the ~1e13 blow-up).
    _swm = sf.quadtree_grid.data["snapwave_mask"].values.copy()
    _swfy = sf.quadtree_grid.data.grid.face_coordinates[:, 1]
    _demote = (_swm == 2) & (_swfy >= SANDY_HOOK_TIP_Y)
    _swm[_demote] = 1
    sf.quadtree_grid.data["snapwave_mask"] = sf.quadtree_grid.data[
        "snapwave_mask"
    ].copy(data=_swm)

    # Support points = the DEEP (z<-5), open-Atlantic (y<tip) stretch of the
    # mask==2 boundary, binned by northing, easternmost (seaward) cell per bin.
    N = wcfg.wave_n_support
    _fc = sf.quadtree_grid.data.grid.face_coordinates
    _z = sf.quadtree_grid.data["z"].values
    _atl = (
        (sf.quadtree_grid.data["mask"].values == 2)
        & np.isfinite(_z)
        & (_z < -5.0)
        & (_fc[:, 1] < SANDY_HOOK_TIP_Y)
    )
    _bxy = _fc[_atl]
    _ybins = np.linspace(_bxy[:, 1].min(), _bxy[:, 1].max(), N + 1)
    snapwave_pts = np.array(
        [
            grp[np.argmax(grp[:, 0])]
            for k in range(N)
            for grp in [_bxy[(_bxy[:, 1] >= _ybins[k]) & (_bxy[:, 1] <= _ybins[k + 1])]]
            if len(grp)
        ]
    )

    # Uniform alongshore forcing from the nearest valid ERA5 wave node.
    _ew = sf.data_catalog.get_rasterdataset(wcfg.wave_geodataset)
    _node = _ew.sel(
        x=wcfg.wave_era5_node[0], y=wcfg.wave_era5_node[1], method="nearest"
    )
    snapwave_t = (_node["time"].values - _node["time"].values[0]) / np.timedelta64(
        1, "s"
    )
    snapwave_hs = _node["hs"].values
    snapwave_tp = _node["tp"].values
    snapwave_wd = _node["wd"].values
    snapwave_ds = np.full_like(snapwave_hs, 30.0)  # ERA5 has no dir-spreading; 30 deg

    # Optional ocean-side wavemaker (native hydromt call; writes sfincs.wvm).
    if wcfg.wavemaker:
        sf.wave_makers.create(str(wcfg.wavemaker_line), merge=False)

    cfg = {
        "snapwave": 1,
        "snapwave_igwaves": int(wcfg.wave_igwaves),
        "snapwave_wind": int(wcfg.wave_wind),
        "snapwave_sector": wcfg.sector(),
        "dtwave": wcfg.dtwave,
        "storewavdir": 1,
    }
    if wcfg.tune_physics:
        cfg.update(
            {
                "snapwave_alpha": wcfg.snapwave_alpha,
                "snapwave_gamma": wcfg.snapwave_gamma,
                "snapwave_hmin": wcfg.snapwave_hmin,
                "snapwave_dtheta": wcfg.snapwave_dtheta,
                "snapwave_fw": wcfg.snapwave_fw,
                "snapwave_niter": wcfg.snapwave_niter,
                "storefw": wcfg.storefw,
            }
        )
    sf.config.update(cfg)

    return {
        "pts": snapwave_pts,
        "t": snapwave_t,
        "hs": snapwave_hs,
        "tp": snapwave_tp,
        "wd": snapwave_wd,
        "ds": snapwave_ds,
    }


def finalize(
    wcfg: WaveConfig,
    base: BaseConfig,
    sf: SfincsModel,
    model_dir: Path,
    sw: dict | None,
) -> None:
    """Phase 2 cell 54 — release handles, write, patch sfincs.inp, write ASCII.

    Called for EVERY experiment (waves or not). When ``wcfg.wavemaker`` the
    ``wvmfile`` key + ``sfincs.wvm`` are preserved (the notebook always stripped
    them, which is why the wavemaker was disabled — do NOT strip here).
    """
    model_dir = Path(model_dir)

    # Materialize forcing in memory, drop xarray's open-file cache, so every
    # handle closes before write (avoids Errno 13 on /cache when re-writing a
    # file this kernel still holds open).
    for _c in (
        sf.water_level,
        sf.discharge_points,
        sf.wind,
        sf.pressure,
        sf.precipitation,
    ):
        try:
            if _c.data is not None:
                _c.data.load()
        except Exception:
            pass
    xr.backends.file_manager.FILE_CACHE.clear()
    gc.collect()

    sf.write()

    inp = model_dir / "sfincs.inp"
    text = inp.read_text()

    # (a) latitude — dropped on write, so Coriolis silently disables without it.
    if "\nlatitude" not in text:
        text = text.replace(
            "coriolis             = 1",
            f"coriolis             = 1\nlatitude             = {base.latitude}",
        )

    # (b) strip orphan infiltration keys (component sets key but writes no file).
    text = (
        "\n".join(
            ln
            for ln in text.splitlines()
            if not ln.strip().startswith(
                ("infiltration_file", "infiltration_type", "scsfile")
            )
        )
        + "\n"
    )

    # (c) waves: ensure SnapWave keys + write the ASCII boundary forcing.
    if wcfg.use_waves:
        if not wcfg.wavemaker:
            # Drop any stale wavemaker key (only when this run has no wavemaker).
            text = (
                "\n".join(
                    ln
                    for ln in text.splitlines()
                    if not ln.strip().startswith("wvmfile")
                )
                + "\n"
            )
        sw_keys = {
            "snapwave": "1",
            "snapwave_igwaves": str(int(wcfg.wave_igwaves)),
            "snapwave_wind": str(int(wcfg.wave_wind)),
            "snapwave_sector": str(wcfg.sector()),
            "dtwave": str(wcfg.dtwave),
            "storewavdir": "1",
            "snapwave_bndfile": "snapwave.bnd",
            "snapwave_bhsfile": "snapwave.bhs",
            "snapwave_btpfile": "snapwave.btp",
            "snapwave_bwdfile": "snapwave.bwd",
            "snapwave_bdsfile": "snapwave.bds",
        }
        if wcfg.tune_physics:
            sw_keys.update(
                {
                    "snapwave_alpha": str(wcfg.snapwave_alpha),
                    "snapwave_gamma": str(wcfg.snapwave_gamma),
                    "snapwave_hmin": str(wcfg.snapwave_hmin),
                    "snapwave_dtheta": str(wcfg.snapwave_dtheta),
                    "snapwave_fw": str(wcfg.snapwave_fw),
                    "snapwave_niter": str(wcfg.snapwave_niter),
                    "storefw": str(wcfg.storefw),
                }
            )
        present = {ln.split("=")[0].strip() for ln in text.splitlines() if "=" in ln}
        for k, v in sw_keys.items():
            if k not in present:
                text += f"{k:<20} = {v}\n"

        # Remove stale files keyed to an old config (would crash the solver).
        for stale in ("snapwave.upw", "snapwave.nc"):
            (model_dir / stale).unlink(missing_ok=True)
        if not wcfg.wavemaker:
            (model_dir / "sfincs.wvm").unlink(missing_ok=True)

        pts = sw["pts"]
        np.savetxt(model_dir / "snapwave.bnd", pts, fmt="%.3f")
        for fn, series in [
            ("snapwave.bhs", sw["hs"]),
            ("snapwave.btp", sw["tp"]),
            ("snapwave.bwd", sw["wd"]),
            ("snapwave.bds", sw["ds"]),
        ]:
            block = np.tile(np.asarray(series)[:, None], (1, len(pts)))
            np.savetxt(
                model_dir / fn,
                np.column_stack([sw["t"], block]),
                fmt=["%11.1f"] + ["%11.3f"] * len(pts),
            )

    inp.write_text(text)
