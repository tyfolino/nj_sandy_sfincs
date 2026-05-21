# NJ Sandy SFINCS — compound flood hindcast

A [SFINCS](https://github.com/Deltares/SFINCS) hindcast of **Hurricane Sandy
(28–31 Oct 2012)** flooding on the New Jersey coast from **Sandy Hook to Asbury
Park**, built with [HydroMT-SFINCS](https://github.com/Deltares/hydromt_sfincs).
Unlike a surge-only model, it represents **compound** coastal flooding — storm
surge, wave setup, rainfall, and river discharge together — and is validated
against the Sandy Hook tide gauge and USGS high water marks.

> 📊 Interactive maps don't render on github.com (it strips JavaScript). For the
> interactive flood map see `notebooks/floodmap.html` via
> [raw.githack.com](https://raw.githack.com/tyfolino/nj_sandy_sfincs/master/notebooks/floodmap.html),
> or open the notebook on [nbviewer](https://nbviewer.org/github/tyfolino/nj_sandy_sfincs/blob/master/notebooks/sfincs-asbury-sandy.ipynb).

## Study area

NJ coast, Sandy Hook → Asbury Park (~40.15–40.50 °N). The northern half (Sandy
Hook spit + bay) is included so the offshore boundary carries Sandy's alongshore
gradient and the NOAA Sandy Hook gauge falls inside the domain for validation.
Grid: 50 m, rotated, UTM 18N, with 8 subgrid pixels (~3 m effective) to resolve
the barrier dune line.

## What it models

| Process | How | Source |
|---------|-----|--------|
| Storm surge (boundary) | Water-level boundary forced by observed gauges (`buffer=100 km`, interpolated alongshore) | NOAA CO-OPS (Battery, Atlantic City, Cape May) |
| Wave setup | Stockdon (2006) parametric setup added to the boundary (β_f = 0.05) | NDBC buoy 44025 *(→ ERA5 wave field, in progress)* |
| Wind + pressure | ERA5 hourly 10 m winds + MSLP | Copernicus CDS |
| Rainfall | Distributed precipitation (SCS partitions it) | NOAA AORC v1.1 |
| River discharge | Point sources at estuary inflows | USGS NWIS (Shark R., Navesink) |
| Infiltration | NRCS Curve Number (rainfall loss only) | NLCD 2012 × SSURGO HSG |
| Numerics | Coriolis + advection on; subgrid; SFINCS v2.3.2 | — |

Elevation is a four-tier merge with the **pre-Sandy 2010 USACE NCMP** topobathy
on top (captures the 2012 dune state, before post-storm replenishment), filled
by CUDEM, NJ LiDAR, and GEBCO offshore.

## Repository layout

```
notebooks/
  sfincs-asbury-sandy.ipynb   # the model — Phase 1 build · Phase 2 forcing+run · Phase 3 viz+validation
  floodmap.html               # standalone interactive max-flood-depth map
scripts/                      # data download / preparation (see below)
data/                         # inputs (gitignored) + data_catalog.yml
model/                        # SFINCS model files + outputs
environment.yml               # conda environment
```

## Data preparation scripts

Run these to populate `data/` before building the model (each writes a NetCDF/
GeoJSON and a matching `data/data_catalog.yml` entry):

| Script | Produces |
|--------|----------|
| `download_pre_sandy_topobathy.py` | 2010 USACE NCMP pre-Sandy topobathy |
| `download_cudem.py`, `download_3dep.py` | CUDEM + LiDAR elevation fill |
| `download_noaa_sandy_wl.py` | NOAA CO-OPS water levels (boundary + validation) |
| `download_era5_cds.py` | ERA5 winds + MSLP |
| `download_ndbc_sandy_waves.py` | NDBC buoy 44025 waves (Stockdon setup) |
| `download_era5_waves_cds.py` | ERA5 wave field (for spatially-varying setup — staged) |
| `download_aorc_sandy_precip.py` | NOAA AORC rainfall |
| `download_usgs_sandy_discharge.py` | USGS river discharge |
| `build_cn_nj.py` | Curve Number grid (NLCD × SSURGO) for infiltration |
| `download_sandy_hwms.py` | USGS Sandy high water marks (validation) |

## Setup

```bash
conda env create -f environment.yml      # creates the `sfincs` conda env
conda activate sfincs
```

- **ERA5 / CDS:** configure `~/.cdsapirc` with a Copernicus token and accept the
  ERA5 single-levels terms (needed by the ERA5 download scripts).
- **SFINCS engine:** runs in Docker — `docker pull deltares/sfincs-cpu:latest`.

## Running the model

The notebook is organized in three phases:

1. **Phase 1 — Static build** (slow, one-time): grid, elevation, mask + boundary
   cells, observation points, subgrid tables → written to `model/`.
2. **Phase 2 — Forcing & run** (fast, iterate here): water level, wave setup,
   wind/pressure, rainfall, discharge, infiltration → run SFINCS via Docker.
3. **Phase 3 — Visualization & validation**: flood maps, zone stats, and
   validation against the Sandy Hook gauge + USGS high water marks.

SFINCS itself runs via:

```bash
docker run --rm -v $(pwd)/model:/data deltares/sfincs-cpu:latest
```

## Validation

- **Sandy Hook gauge (8531680)** — temporal check (the gauge failed mid-storm at
  10-29 23:00, before Sandy's true peak, so it bounds rather than fixes the peak).
- **31 USGS high water marks** — spatial check. Modeled peak water levels are
  essentially unbiased against the marks (mean bias ≈ 0, RMSE ≈ 1 m): the model
  neither systematically over- nor under-floods Sandy. The structured exception
  is the **highest open-coast marks (≥ 4 m)**, under-predicted because parametric
  setup captures setup but not wave **runup** (a SnapWave/IG signal).

## Roadmap / known limitations

- **ERA5 wave field** (in progress) — replace the single-buoy uniform Stockdon
  setup with a spatially-varying field, fixing the alongshore setup imbalance.
- **Quadtree + SnapWave + IG wavemakers** (planned) — true wave setup *and*
  runup; needs a quadtree grid (regular grids aren't supported by SnapWave in
  hydromt_sfincs v2.0.0rc2; the SFINCS v2.3.2 engine already supports it).
- **Manning roughness** still uses the SF-Bay-Delta-tuned NLCD reclass table —
  swap for a NJ/CONUS table.
- Stockdon setup is applied uniformly alongshore and adds setup, not runup.
