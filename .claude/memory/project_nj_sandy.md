---
name: NJ Sandy SFINCS project context
description: Full context for the nj_sandy_sfincs repo — goals, data decisions, lessons from prior tutorial work, planned notebook structure
type: project
originSessionId: 0509403d-b5e9-42ef-aca1-5b296ad6ce8e
---
This repo is a deliberate, clean-slate SFINCS surge model for **Hurricane Sandy (Oct 29–31, 2012)** at **Asbury Park, NJ**, built after working through the hydromt_sfincs tutorial examples in `/home/zagreus/hydromt_sfincs_examples/nj_examples/`.

**Study area:** Asbury Park barrier island + Atlantic shelf (~38.9–41.4°N, 73.7–75.6°W)

**Why starting fresh:** The tutorial version (`nj_examples/`) had known quality issues — GEBCO DEM too coarse to represent narrow barrier island dunes, no wind forcing — that produced only a thin strip of flooding with no meaningful inland inundation. This repo is designed to fix those issues from the start.

---

## Deliberate data decisions

| Dataset | Source | Purpose | Why chosen |
|---------|--------|---------|------------|
| NJ OGIS 10-ft DEM | `s3://njogis-elevation` (public) | Land topography | ~3m statewide LiDAR mosaic (2014-2019); scales to all-NJ. Downloaded via `scripts/download_3dep.py` → `data/elevation/nj_10ft_dem.tif`. ERDAS .img+.ige (~16 GB raw), clipped to bbox and reprojected to WGS-84. |
| ESA WorldCover 2020 | ESA / S3 | Manning's roughness reclass | Already downloaded in nj_examples; 10m, global |
| GTSM-ERA5-E | Copernicus CDS | Offshore water level boundary | Downloaded in nj_examples via `download_gtsm_cds.py`; underestimates peak surge but acceptable starting point. Deliberately kept over NOAA CO-OPS gauges for first run — revisit after seeing results. |
| ERA5 | Copernicus CDS | Wind + pressure forcing | Sandy was wind-driven; this is the highest-impact missing piece from the tutorial version |
| NLCD | MRLC (download pending) or Planetary Computer | Permanent water mask | Better than WorldCover class 80 for NJ's complex wetland coast; user submitted MRLC download request |

**Do NOT use GEBCO as the primary DEM** — at 450m resolution it averages the narrow NJ barrier island into a broad ridge, overestimates dune heights, and prevents realistic surge overtopping.

---

## Lessons from the tutorial version

**Model parameters that worked:**
- Grid: 150 m resolution, rotated, UTM zone 18N (EPSG:32618)
- Active mask: `zmin=-10 m`
- Water level boundary: `zmax=-1 m`
- Subgrid pixels: 6 per cell (25 m effective resolution)
- Output timing: `dtmapout=3600`, `dtmaxout=86400`, `dthisout=600` — **must be set explicitly** or `sfincs_map.nc` won't be created

**Known hydromt bug (locally patched in tutorial env):**
`/home/zagreus/miniforge3/envs/sfincs/lib/python3.14/site-packages/hydromt/readers.py:760`
Change `c.lower()` → `str(c).lower()` — integer column names from headerless `.bnd` files cause AttributeError. Check whether this is still needed in the new env.

**Docker run pattern:**
```bash
docker run --rm -v <abs_model_path>:/data deltares/sfincs-cpu:latest
```
SFINCS writes output files as **root-owned**. Always delete old `sfincs_map.nc` / `sfincs_his.nc` before re-running, or SFINCS gets "NetCDF: Not a valid ID" errors. Use Docker itself to delete:
```bash
docker run --rm -v <abs_model_path>:/data --entrypoint /bin/sh deltares/sfincs-cpu:latest -c "rm -f /data/sfincs_map.nc /data/sfincs_his.nc"
```

**Flood map masking (two-layer approach):**
1. WorldCover class 80 — removes classified water bodies
2. `dep > 0` — removes GEBCO nearshore artifacts (GEBCO assigns ocean-floor bathymetry to the beach face, producing spuriously large depths). With a proper LiDAR DEM, the `dep > 0` condition may be less critical.

**Subgrid downscaling:** Use `utils.downscale_floodmap(zsmax, dep, hmin)` with the high-res DEM (not `zb` from model output, which is the minimum bed level per coarse cell and overestimates flood extent).

---

## Planned notebook structure

| Notebook | Status | Description |
|----------|--------|-------------|
| `notebooks/0_download_data.ipynb` | TODO | Download 3DEP, ERA5 wind, verify GTSM; set up data catalogs |
| `notebooks/1_build_model.ipynb` | TODO | Build SFINCS model via Python API |
| `notebooks/2_run_model.ipynb` | TODO | Run via Docker, inspect log |
| `notebooks/3_plot_results.ipynb` | TODO | Downscale + plot max flood depth |
| `notebooks/4_animate_results.ipynb` | TODO | Animate flood time series |

---

## Deferred improvements

- **Outflow boundary cells** — add passive outflow (mask=3) at Shark River Inlet and Manasquan Inlet so surge can drain from the back-barrier zone. Data: NHD (USGS National Map) for inlet geometry; already supported by hydromt. Active discharge forcing optional via USGS NWIS gauge 01407290 (Shark River at Belmar) or NWM.

---

## Observation points (from tutorial version, carry over)
- Asbury Park Pier
- Deal Lake Outlet
- Shark River Inlet

These are in `nj_examples/data/obs.geojson` — copy to this repo's `data/`.
