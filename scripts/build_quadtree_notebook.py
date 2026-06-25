"""
HISTORICAL GENERATOR — provenance only; do NOT re-run to "update" the notebook.
This script originally built the quadtree notebook by rewriting the regular-grid
notebook. Both source notebooks have since moved (the regular-grid baseline is now
under notebooks/archive/, the output is the hand-maintained canonical notebook
notebooks/sfincs-nj-sandy.ipynb). The canonical notebook is now edited directly;
re-running this would overwrite those hand edits. Kept as a record of how the
quadtree build was first derived.

Build notebooks/sfincs-nj-sandy.ipynb by surgically rewriting the
working regular-grid notebook (archive/sfincs-asbury-sandy.ipynb). Phase 1 geometry
cells are swapped to the quadtree API; SnapWave mask + BC cells are inserted;
the Stockdon-on-bzs hack is removed (SnapWave replaces it). Phase 2 forcings
(wind, pressure, AORC rain, USGS discharge, CN infiltration) and Phase 3
validation cells are unchanged — they're either grid-agnostic or read the
model output the same way for both grid types.

Run once; iterate by re-running this script. Don't hand-edit the .ipynb.

Cell-by-cell change log (IDs are stable Jupyter cell IDs from the source nb):

  a35817f2  REPLACE   Phase 1 init: model_root -> "../model_quadtree"
  5208270f  REPLACE   grid           -> quadtree_grid.create_from_region(refinement_polygons=...)
  74a2cf62  REPLACE   elevation      -> quadtree_elevation.create
  f2d65ccd  REPLACE   mask active    -> quadtree_mask.create_active
  0137685c  REPLACE   mask wl bnd    -> quadtree_mask.create_boundary(btype="waterlevel")
  2f674d5a  REPLACE   mask outflow   -> quadtree_mask.create_boundary(btype="outflow")
  (NEW)     INSERT    SnapWave mask: create_active + create_boundary(btype="waves"/"neumann")
  772959da  KEEP      obs points (grid-agnostic API)
  5228f7f8  REPLACE   subgrid        -> quadtree_roughness.create + quadtree_subgrid.create
  22ff5fc2  KEEP      Phase 1 write + gc
  be93bc92  REPLACE   Phase 2 init: model_root -> "../model_quadtree"
  b899e871  REPLACE   config: add snapwave=1, snapwave_igwaves=1, snapwave_dtheta, etc.
  4d2cda55  DELETE    Stockdon markdown header (SnapWave replaces it)
  bf111cf3  REPLACE   Stockdon code  -> snapwave_boundary_conditions.create_from_grid
  f023a46f  REPLACE   Phase 3 read:  model_root -> "../model_quadtree"
  cd5b78c0  REPLACE   flood map      -> de-rotated lev3 dep (quadtree has no merged
                                        dep_subgrid.tif; reproduces MOTF CSI~0.53)

  All other Phase 2/3 cells are untouched.
"""
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("NJ_ROOT", Path(__file__).resolve().parents[1]))
SRC = ROOT / "notebooks/archive/sfincs-asbury-sandy.ipynb"
DST = ROOT / "notebooks/sfincs-nj-sandy.ipynb"


def code(src: str):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": src.splitlines(keepends=True),
    }


def markdown(src: str):
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": src.splitlines(keepends=True),
    }


def set_src(cell, src: str):
    cell["source"] = src.splitlines(keepends=True)
    if cell["cell_type"] == "code":
        cell["outputs"] = []
        cell["execution_count"] = None


REPLACEMENTS = {
    # ---------- Phase 1 ----------
    "a35817f2": '''\
model_root = "../model_quadtree"

log.initialize_logging()
log.set_log_level(log_level=30)  # Only errors and critical

# Add file handler to log to a file
log_file = Path(model_root) / "hydromt_sfincs.log"
Path(model_root).mkdir(parents=True, exist_ok=True)
logger = log._add_filehandler(log_file)

# Add data catalogs
data_libs = ["../data/data_catalog.yml"]

# Create model. write_gis=True dumps gis/*.tif/geojson for QGIS inspection
# (same as the regular-grid notebook).
sf = SfincsModel(
    data_libs=data_libs, root=model_root, mode="w+", write_gis=True
)
''',

    "5208270f": '''\
# Phase 3: QUADTREE grid (replaces the 50 m regular grid).
# Base resolution 200 m; refinement polygons step it down to 100 / 50 / 25 m
# nested toward the surf zone. See scripts/build_quadtree_refinement.py for
# the polygon recipe (full region @ L1, coastal corridor @ L2, dune+surf @ L3
# gated by elevation). Cells outside any polygon stay at 200 m.
refinement_gdf = gpd.read_file(
    "../data/quadtree/refinement_polygons.geojson"
)

# elevation_list is passed here so the level-2/3 polygons can use their
# zmin/zmax columns to gate refinement by topobathy (quadtree_builder.py
# only applies elevation filtering when elevation_list is non-empty).
elevation_list = [
    {"elevation": "usace_nj_2010"},                # 1 m pre-Sandy topobathy
    {"elevation": "cudem_nj"},                     # 3 m fill: inlet + shelf
    {"elevation": "nj_10ft_dem", "zmin": 0.001},   # 3 m fill: inland
    {"elevation": "gebco_nj"},                     # 450 m offshore tail
]

sf.quadtree_grid.create_from_region(
    region={"geom": "../data/region.geojson"},
    res=200,                # base level-0 cell size
    rotated=True,
    crs="utm",
    refinement_polygons=refinement_gdf,
    elevation_list=elevation_list,
)

# Quick cell-count sanity check. Aborts if the grid blew past our 24 GB
# headroom — the subgrid build is the memory peak; conservatively budget
# ~500k cells before worrying.
qg = sf.quadtree_grid.data
nlev = int(qg.attrs["nr_levels"])
n_total = int(qg.grid.n_face)
print(f"Quadtree: {n_total} cells across {nlev} refinement levels")
for ilev in range(nlev):
    nlev_cells = int((qg["level"] == ilev).sum())
    dx_lev = qg.attrs["dx"] / (2 ** ilev)
    print(f"  level {ilev}: {nlev_cells:>7d} cells @ ~{dx_lev:.0f} m")
assert n_total < 500_000, f"Quadtree has {n_total} cells — too many for 24 GB RAM. Tune refinement."
''',

    "74a2cf62": '''\
# Elevation onto the quadtree mesh. Same 4-tier merge as the regular-grid
# notebook; quadtree_elevation.create samples each refinement level at its
# native resolution (level 3 = 25 m, samples USACE 1 m densely; level 0 =
# 200 m, samples GEBCO). nrmax=200 chunks the reproject — memory-friendly.
elevation_list = [
    {"elevation": "usace_nj_2010"},                # 1 m pre-Sandy topobathy
    {"elevation": "cudem_nj"},                     # 3 m fill: inlet + shelf
    {"elevation": "nj_10ft_dem", "zmin": 0.001},   # 3 m fill: inland
    {"elevation": "gebco_nj"},                     # 450 m offshore tail
]

sf.quadtree_elevation.create(elevation_list=elevation_list, buffer_cells=0, nrmax=200)

print(f"z range: {float(sf.quadtree_grid.data['z'].min()):.1f} .. "
      f"{float(sf.quadtree_grid.data['z'].max()):.1f} m")
''',

    "f2d65ccd": '''\
# Active mask on the quadtree grid. Same -10 m criterion as the regular grid:
# cells with z >= -10 m are active (NJ shelf is shallow enough to capture).
sf.quadtree_mask.create_active(zmin=-10)

print(f"active sfincs cells: {int((sf.quadtree_grid.data['mask'] > 0).sum())} "
      f"/ {sf.quadtree_grid.data.grid.n_face}")
''',

    "0137685c": '''\
# Offshore water-level boundary cells (mask=2) where z <= -1 m. Same rule as
# the regular grid; quadtree_mask.create_boundary picks edge cells satisfying
# the elevation gate.
sf.quadtree_mask.create_boundary(
    btype="waterlevel",
    zmax=-1,
    reset_bounds=True,
)

print(f"waterlevel boundary cells: {int((sf.quadtree_grid.data['mask'] == 2).sum())}")
''',

    "2f674d5a": '''\
# Lateral/inland outflow cells (mask=3) on the channels/back-bay edges.
# reset_bounds=False preserves the offshore waterlevel boundary just set above.
sf.quadtree_mask.create_boundary(
    btype="outflow",
    zmin=-1,
    zmax=2,
    reset_bounds=False,
)

print(f"outflow boundary cells: {int((sf.quadtree_grid.data['mask'] == 3).sum())}")
''',

    "5228f7f8": '''\
# Drop the data-catalog cache from the elevation step before reloading the
# DEMs for subgrid. hydromt keeps every RasterDataset it has read alive on
# the catalog object — without this, the cached USACE 1 m topobathy etc.
# stay resident through the subgrid build and double up the peak memory.
import gc
for src in list(sf.data_catalog.sources):
    s = sf.data_catalog.get_source(src)
    if hasattr(s, "_data"):
        s._data = None
gc.collect()

# Roughness on the quadtree mesh, then the subgrid V-h tables.
#
# quadtree_roughness.create writes a per-cell `manning` from the NLCD reclass
# (same NJ-tuned table as the regular grid — Bunya/Atkinson Atlantic-coast
# values, classes 23/24 nudged to 0.10 / 0.13). quadtree_subgrid.create then
# samples each cell at nr_subgrid_pixels x nr_subgrid_pixels finer points to
# build the volume / conveyance / roughness lookup tables.
#
# Effective subgrid resolution per cell level (with nr_subgrid_pixels=8):
#   level 0 (200 m)  -> 25 m subgrid sampling
#   level 1 (100 m)  -> 12.5 m
#   level 2 (50 m)   -> 6.25 m
#   level 3 (25 m)   -> 3.125 m   <- dune line, ~match for USACE 1 m DEM
#
# nrmax=200 chunks the subgrid build by cell-block; this is the load-bearing
# memory mitigation for the 24 GB RAM budget (build does NOT load the full
# subgrid raster at once).
reclass_table = "../data/roughness/NLCD_CONUS_mapping.csv"

elevation_list = [
    {"elevation": "usace_nj_2010"},
    {"elevation": "cudem_nj"},
    {"elevation": "nj_10ft_dem", "zmin": 0.001},
    {"elevation": "gebco_nj"},
]
roughness_list = [{"lulc": "nlcd_2012", "reclass_table": reclass_table}]

sf.quadtree_roughness.create(roughness_list=roughness_list, nrmax=200)

sf.quadtree_subgrid.create(
    elevation_list=elevation_list,
    roughness_list=roughness_list,
    nr_subgrid_pixels=8,
    nrmax=2000,            # DO NOT lower this for subgrid! nrcb = nrmax/refi,
                           # so smaller nrmax => MANY more blocks => MANY more
                           # merge_multi_dataarrays calls + a 132k-iter inner
                           # Python loop per block. With nrmax=200, L3 alone is
                           # 51M Python iterations + 768 merge calls. nrmax=2000
                           # gives ~1 block per level -> 60s total vs 2+ hours.
                           # Memory is fine: block = 6 km square @ 3 m subgrid
                           # = ~64 MB/layer x 4 layers = ~250 MB working set.
    write_dep_tif=True,
    write_man_tif=True,
)
''',

    "746b0485": '''\
# Quick sanity check on the quadtree subgrid table. On quadtree the subgrid
# lives at sf.quadtree_subgrid.data (not sf.subgrid.data) and the variable
# names are z_zmin/z_zmax/uv_havg/uv_navg etc. (per-edge, not per-cell), so
# the regular-grid plot_basemap path doesn\'t apply. Just sanity-check ranges.
sg = sf.quadtree_subgrid.data
print(f"subgrid variables: {list(sg.data_vars)}")
for v in ["z_zmin", "z_zmax", "uv_havg", "uv_navg"]:
    if v in sg:
        print(f"  {v}: shape={sg[v].shape}  "
              f"min={float(sg[v].min()):.3f}  max={float(sg[v].max()):.3f}")
''',

    # ---------- Phase 2 ----------
    "be93bc92": '''\
# --- Phase 2 entry point: reopen the static quadtree model from disk ---
model_root = "../model_quadtree"
data_libs = ["../data/data_catalog.yml"]

sf = SfincsModel(model_root, data_libs=data_libs, mode="r+")
print(f"reopened {sf.grid_type} model at {model_root}")
''',

    "b899e871": '''\
# Set the simulation period to cover Hurricane Sandy's landfall.
# tstart == tref so the model gets ~24 h of calm tide before Sandy arrives.
sf.config.update(
    {
        "tref": datetime(2012, 10, 28),
        "tstart": datetime(2012, 10, 28),
        "tstop": datetime(2012, 10, 31),
        "tspinup": 3600.0,
        "coriolis": 1,
        "latitude": 40.32,
        "advection": 1,
        "dtmapout": 3600.0,
        "dtmaxout": 86400.0,
        "dthisout": 600.0,
        # --- Phase 3 SnapWave additions -------------------------------------
        # snapwave=1 turns the incident wave solver on; it consumes the
        # snapwave_mask + snapwave.bnd we set below. snapwave_igwaves=1 binds
        # IG waves to the incident spectrum at the wave boundary (Herbers
        # 1994), which is what physically overtops the highest dunes during
        # Sandy. snapwave_dtheta=10 (deg) is the directional bin width; 10°
        # is standard. snapwave_use_nearest=1 makes SnapWave use the nearest
        # SFINCS cell when its mesh and the SFINCS mesh don't overlap.
        "snapwave": 1,
        "snapwave_igwaves": 1,
        "snapwave_dtheta": 10.0,
        "snapwave_use_nearest": 1,
    }
)

# Apply observed NOAA CO-OPS water levels to the boundary cells.
# (Carried over verbatim from the regular-grid notebook — same gauges,
# same merge=False reason, same 100 km buffer to reach Atlantic City.)
sf.water_level.create(
    geodataset="noaa_sandy_nj",
    buffer=100000,
    merge=False,
)
''',

    "bf111cf3": '''\
# SnapWave boundary conditions from the ERA5 wave field.
#
# Replaces the regular-grid notebook\'s Stockdon-on-bzs parametric hack.
# `create_from_grid` ingests the ERA5 hs/tp/wd/ds 2-D field, picks all valid
# offshore nodes within `buffer` of the snapwave_mask==2 cells, and writes
# them as snapwave.bnd + snapwave.nc. The SnapWave Fortran solver then
# propagates incident waves onto the SFINCS mesh, producing real spatially-
# varying wave setup and IG runup at the dunes.
#
# Two fixes vs. naive call:
#   (1) ds=30 deg fill. ERA5 has no directional-spreading field; the
#       NDBC stdmet path also uses a constant 30 deg, so this matches
#       the established default. Without ds the create_from_grid call
#       raises NoDataException ("variables not found [...ds]").
#   (2) Filter ERA5 nodes to those EAST of the model bbox. ERA5 0.5 deg
#       grid (~55 km) puts some nodes on inland NJ; create_from_grid\'s
#       buffer pulls them in regardless; SnapWave then reads depth ~0 m
#       at those points and the IG-bound Hm0ig explodes (uv > 1000 m/s,
#       solver blows up). Limiting to nodes east of the eastern edge of
#       the model bbox keeps all input points offshore.
import xarray as xr

era5_waves = sf.data_catalog.get_rasterdataset("era5_waves_nj")
if "ds" not in era5_waves.data_vars:
    era5_waves["ds"] = xr.full_like(era5_waves["hs"], 30.0)
    era5_waves["ds"].attrs["units"] = "deg"
    era5_waves["ds"].attrs["long_name"] = "directional spreading (constant fill)"

bbox = sf.bbox  # (minx, miny, maxx, maxy) in WGS84
east_limit_lon = bbox[2] - 0.1   # tiny pad in case a node sits on the edge
era5_offshore = era5_waves.where(era5_waves["x"] >= east_limit_lon, drop=True)
print(f"ERA5 nodes kept (offshore only): "
      f"{era5_offshore.sizes.get(\'x\')} x {era5_offshore.sizes.get(\'y\')}")

sf.snapwave_boundary_conditions.create_from_grid(
    data=era5_offshore,
    buffer=100e3,
)

bnd = sf.snapwave_boundary_conditions.data
print(f"snapwave boundary points: {bnd.sizes.get(\'index\', \'?\')}")
print(f"  hs peak: {float(bnd[\'hs\'].max()):.2f} m   tp peak: {float(bnd[\'tp\'].max()):.2f} s")
''',

    # ---------- Infiltration: route through quadtree component ----------
    "9bcae5cf": '''\
# SCS Curve Number infiltration on the quadtree mesh.
#
# Uses sf.quadtree_infiltration (not sf.infiltration — that\'s the regular-grid
# API and errors on quadtree models). antecedent_moisture=None reads the \'cn\'
# variable (CN II / average) directly. The scs variable lives on the quadtree
# grid; SCS only consumes rainfall, never surge.
#
# KNOWN HYDROMT BUG: the quadtree component sets sfincs.inp keys
# `infiltration_file = infiltration.nc` + `infiltration_type = cna` but its
# write() method is a `pass` — no infiltration.nc is ever written. SFINCS then
# errors at runtime ("Infiltration netcdf file not found"). The post-write
# patch cell below strips the orphan config lines so SFINCS runs without
# infiltration. Effect on Sandy validation is small (~+/-0.02 CSI) because rain
# was modest (34 mm) and surge-dominated.
sf.quadtree_infiltration.create_cn(cn="cn_nj", antecedent_moisture=None, nrmax=2000)

_scs = sf.quadtree_grid.data["scs"]
print(f"SCS max soil-moisture retention S [inch]: "
      f"mean={float(_scs.where(_scs > 0).mean()):.2f}  max={float(_scs.max()):.2f}  "
      f"(higher S = more infiltration capacity; S=0 over water/impervious)")
''',

    # ---------- Phase 3 ----------
    "f023a46f": '''\
# Open the model read-only for result inspection. Standalone entry point.
model_root = "../model_quadtree"
data_libs = ["../data/data_catalog.yml"]
model_abs = Path(model_root).resolve()

mod = SfincsModel(model_root, data_libs=data_libs, mode="r")
mod.output.read()

print(f"grid_type: {mod.grid_type}")
print("Output variables available:")
list(mod.output.data.keys())
''',

    "cd5b78c0": '''\
# QUADTREE flood map.  Unlike the regular grid, the quadtree subgrid build does
# NOT write a single merged subgrid/dep_subgrid.tif — it writes per-level
# dep_subgrid_lev{0..3}.tif, all on the ROTATED UTM mesh.  The finest level
# (lev3, 3.125 m) blankets the refined surf-zone + back-bay where every MOTF /
# HWM check happens, so we score on it.  We de-rotate to a NORTH-UP 6.25 m grid
# ONCE here, so all downstream cells' axis-aligned pixel sampling [(X-c)/a] is
# EXACT — on the rotated grid it was only approximate (a ~0.7 deg tilt = up to a
# ~400 m offset across the 35 km domain).  This is the path that reproduces the
# wavemaker-baseline MOTF CSI ~= 0.53.
import rioxarray

da_zsmax = mod.output.data["zsmax"].max(dim="timemax")

dep_lev3 = rioxarray.open_rasterio(
    model_abs / "subgrid" / "dep_subgrid_lev3.tif"
).squeeze()
da_dep = dep_lev3.rio.reproject(dep_lev3.rio.crs, resolution=6.25)  # rotated -> north-up
da_dep = da_dep.where(da_dep != da_dep.rio.nodata)
print(f"Subgrid DEM (lev3, de-rotated): shape {da_dep.shape}, "
      f"resolution {da_dep.rio.resolution()}")

# Downscale the quadtree water level onto the north-up DEM (nearest cell), then
# drop deep-ocean cells (dep > -0.5) so the open shelf doesn't dominate the
# colour scale.  NB: pass `dep` as an in-memory DataArray — the on-disk
# path-based downscale_floodmap crashes natively on this numpy/rasterio stack.
da_hmax = utils.downscale_floodmap(zsmax=da_zsmax, dep=da_dep, hmin=0.05)
da_hmax = da_hmax.where(da_dep > -0.5)
''',
}


# New cells inserted AFTER the cell with the given id.
# Each entry is a list of cells (markdown + code).
INSERT_AFTER = {
    "91087aae": [
        markdown(
            "#### Workaround: strip orphan infiltration keys from sfincs.inp\n"
            "\n"
            "`quadtree_infiltration.create_cn` sets `infiltration_file = infiltration.nc` in the config but never writes the file (the component's `write()` is `pass`). SFINCS then aborts with *\"Infiltration netcdf file not found\"*. Strip the orphan keys so the run proceeds without infiltration — small effect on Sandy validation (rain was modest, surge-dominated). Remove once the upstream write() is implemented.\n"
        ),
        code('''\
from pathlib import Path

inp_path = Path(model_root) / "sfincs.inp"
text = inp_path.read_text()
new_lines = []
for line in text.splitlines():
    if line.strip().startswith(("infiltration_file", "infiltration_type", "scsfile")):
        print(f"stripped: {line!r}")
        continue
    new_lines.append(line)
inp_path.write_text("\\n".join(new_lines) + "\\n")
print(f"patched {inp_path} — infiltration keys removed")
'''),
    ],
    "2f674d5a": [
        markdown(
            "### 5b. SnapWave mask (separate mask for the wave solver)\n"
            "\n"
            "SnapWave needs its **own** active + boundary mask, stored as `snapwave_mask` on the same quadtree grid as the SFINCS mask. The wave domain reaches further offshore than the SFINCS hydrodynamic domain so the incident spectrum has somewhere to propagate from. Boundary cells (`snapwave_mask=2`) are where SnapWave reads from the `.bhs/.btp/.bwd/.bds` files we wire up in Phase 2.\n"
        ),
        code('''\
# SnapWave active cells: shoreline + nearshore + shelf. Wider zmin than the
# SFINCS mask (-50 m vs -10 m) so the wave solver has shelf cells to refract
# waves through; zmax=10 keeps it off high inland topography (SnapWave on dry
# dunes is wasted work).
sf.quadtree_snapwave_mask.create_active(zmin=-50, zmax=10)

# Wave open boundary on the offshore (deepest) edge of the SnapWave mask:
# z <= -15 m. Deeper than the SFINCS waterlevel boundary because SnapWave
# needs the boundary in water that can carry the incident spectrum, AND
# keeping the wavebnd out of the surf-zone refinement (L3/L4 cells) avoids
# applying radiation-stress forcing in fine cells where the resulting
# gradients destabilize the SFINCS solver.
sf.quadtree_snapwave_mask.create_boundary(
    btype="waves",
    zmax=-15,
    reset_bounds=True,
)

# Neumann (zero-gradient) closure on the lateral edges so waves don't reflect
# off the model boundary. zmax wider here — covers everything left after the
# offshore cells were claimed for "waves".
sf.quadtree_snapwave_mask.create_boundary(
    btype="neumann",
    zmin=-50,
    zmax=10,
    reset_bounds=False,
)

sw = sf.quadtree_grid.data["snapwave_mask"]
print(f"snapwave_mask: active={int((sw==1).sum())} "
      f"wavebnd={int((sw==2).sum())} neumann={int((sw==3).sum())}")
'''),
        markdown(
            "#### Workaround: flip deep-edge neumann cells to wavebnd\n"
            "\n"
            "`create_boundary(btype=\"waves\", zmax=-8)` silently returns zero cells when called first on a fresh `snapwave_mask` — likely a numpy/xugrid alignment bug between `_find_boundary_cells` (numpy array) and `uda_dep <= zmax` (xugrid array). The neumann call above DOES find all 3 901 edge cells correctly, so we manually re-label the subset with z ≤ −8 as waves boundary. Remove once the upstream bug is fixed.\n"
        ),
        code('''\
# Manual workaround for the create_boundary(btype="waves") bug.
# Reads neumann (mask==3) cells, flips the deep-water subset to wavebnd (mask==2).
# Threshold z <= -15 m matches the (broken) create_boundary call above — keeps
# wavebnd out of the surf-zone refinement cells where steep radiation-stress
# gradients crash the SFINCS momentum solver.
import numpy as np

sw = sf.quadtree_grid.data["snapwave_mask"]
z  = sf.quadtree_grid.data["z"]

mask_data = sw.values.copy()
to_waves = (mask_data == 3) & (z.values <= -15)
print(f"converting {int(to_waves.sum())} neumann cells to waves boundary")
mask_data[to_waves] = 2

# Write back as a UgridDataArray on the same grid
sf.quadtree_grid.data["snapwave_mask"] = sw.copy(data=mask_data)

sw_new = sf.quadtree_grid.data["snapwave_mask"]
for v, name in [(1, "active"), (2, "wavebnd"), (3, "neumann")]:
    print(f"  mask=={v} ({name}): {int((sw_new==v).sum())}")
'''),
    ],

    # ---------- Wavemaker: SnapWave -> SFINCS forced inflow line ----------
    "bf111cf3": [
        markdown(
            "### Wavemaker line (SnapWave → SFINCS handoff)\n"
            "\n"
            "Following Leijnse et al. (Carolinas / Florence, 2025), the SnapWave radiation-stress forcing is injected into SFINCS along a **single alongshore wavemaker line** at the ~−5 m NAVD88 contour rather than smeared across the full SnapWave/SFINCS overlap. Without this line, SFINCS receives wave forcing across every cell where the two masks overlap; the steep gradients at the SFINCS-active edge (z≈−10 m) and the L3↔L4 (50↔25 m) refinement interface inside the surf zone are enough to drive SFINCS's momentum solver unstable (uvmax > 1000 m/s within the first 1 000 s of simulated time, deterministically, regardless of SnapWave parameter tuning).\n"
            "\n"
            "The wavemaker is built by `scripts/build_wavemaker_line.py` from the CUDEM −5 m contour, trimmed to the open-coast portion (Manasquan-ish up to just south of Sandy Hook tip). **Plan A** (current): open-coast only. **Plan B** (future, if Sandy Hook back-bay validation is poor): also add a bay-side wavemaker inside Sandy Hook Bay to feed wave forcing into the back-bay shoreline.\n"
        ),
        code('''\
# Wavemaker LineString from CUDEM −5 m contour (open-coast, ~34 km).
# See scripts/build_wavemaker_line.py for the extraction recipe.
sf.wave_makers.create("wavemaker_nj_coast")
print(f"wave makers: {sf.wave_makers.nr_lines} line(s)")
for i, geom in enumerate(sf.wave_makers.gdf.geometry):
    print(f"  line {i}: length={geom.length/1000:.2f} km  vertices={len(geom.coords)}")
'''),
    ],
}

# Cell ids to DELETE entirely (cleanly, with no replacement).
DELETE = {
    "4d2cda55",  # Stockdon markdown header — SnapWave replaces it
}


def main():
    nb = json.loads(SRC.read_text())

    # Update top-level notebook title cell to reflect Phase 3 scope.
    for c in nb["cells"]:
        if c.get("id") == "07780d91":
            set_src(
                c,
                "# SFINCS Demo — NJ Sandy (Phase 3: quadtree + SnapWave + IG)\n"
                "\n"
                "Quadtree variable-resolution rebuild (200 → 100 → 50 → 25 m, refined toward the dune line) of the working regular-grid Sandy notebook. Adds the SnapWave incident wave solver with IG-band binding, replacing the parametric Stockdon water-level hack with a real spatially-varying wave field.\n",
            )
            break

    out_cells = []
    for c in nb["cells"]:
        cid = c.get("id")
        if cid in DELETE:
            continue
        if cid in REPLACEMENTS:
            set_src(c, REPLACEMENTS[cid])
        out_cells.append(c)
        if cid in INSERT_AFTER:
            out_cells.extend(INSERT_AFTER[cid])

    nb["cells"] = out_cells
    DST.write_text(json.dumps(nb, indent=1) + "\n")

    print(f"Wrote {DST}")
    print(f"  cells: {len(out_cells)} (was {len(json.loads(SRC.read_text())['cells'])})")


if __name__ == "__main__":
    main()
