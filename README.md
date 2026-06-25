# NJ Sandy SFINCS — compound flood hindcast

A [SFINCS](https://github.com/Deltares/SFINCS) hindcast of **Hurricane Sandy
(28–31 Oct 2012)** flooding on the New Jersey coast from **Sandy Hook to Asbury
Park**, built with [HydroMT-SFINCS](https://github.com/Deltares/hydromt_sfincs).
Unlike a surge-only model, it represents **compound** coastal flooding — storm
surge, wave setup, rainfall, and river discharge together — and is validated
against the Sandy Hook tide gauge and USGS high water marks.

> 📊 Interactive maps don't render on github.com (it strips JavaScript). Open the
> notebook on [nbviewer](https://nbviewer.org/github/tyfolino/nj_sandy_sfincs/blob/master/notebooks/sfincs-nj-sandy.ipynb)
> to view the rendered flood maps.

## Study area

NJ coast, Sandy Hook → Asbury Park (~40.15–40.50 °N). The northern half (Sandy
Hook spit + bay) is included so the offshore boundary carries Sandy's alongshore
gradient and the NOAA Sandy Hook gauge falls inside the domain for validation.
Grid: quadtree (200 → 100 → 50 → 25 m), rotated, UTM 18N, refined toward the dune
line, with 8 subgrid pixels (~3 m effective) to resolve the barrier.

## What it models

| Process | How | Source |
|---------|-----|--------|
| Storm surge (boundary) | Water-level boundary forced by observed gauges (`buffer=100 km`, interpolated alongshore) | NOAA CO-OPS (Battery, Atlantic City, Cape May) |
| Waves | SnapWave incident + infragravity solver, plus a nearshore wavemaker line that injects IG runup/overtopping into the flow | ERA5 wave field |
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
  sfincs-nj-sandy.ipynb       # the model — Phase 1 build · Phase 2 forcing+run · Phase 3 viz+validation
  archive/                    # superseded notebooks (regular-grid baseline + experiments)
  reference/                  # Tim Leijnse's quadtree+SnapWave reference notebook
scripts/                      # data download / preparation (see below)
data/                         # inputs (gitignored) + data_catalog.yml
model_quadtree/               # SFINCS model files + outputs (gitignored)
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
| `download_era5_waves_cds.py` | ERA5 wave field (SnapWave incident-wave boundary) |
| `download_ndbc_sandy_waves.py` | NDBC buoy 44025 waves (validation reference) |
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
- **Notebook git filter (once per clone):** `python scripts/setup_nbstripout.py` activates
  the nbstripout clean filter so notebook outputs/metadata are stripped on commit.

## Running the model

The notebook is organized in three phases:

1. **Phase 1 — Static build** (slow, one-time): quadtree grid, elevation, mask +
   boundary cells, observation points, subgrid tables → written to `model_quadtree/`.
2. **Phase 2 — Forcing & run** (fast, iterate here): water level, SnapWave waves +
   wavemaker, wind/pressure, rainfall, discharge, infiltration → run SFINCS.
3. **Phase 3 — Visualization & validation**: flood maps, zone stats, and
   validation against the Sandy Hook gauge + USGS high water marks.

The notebook's `run_sfincs()` helper auto-detects the runtime (Docker locally,
Singularity on HPC). To run the engine directly via Docker:

```bash
docker run --rm -v $(pwd)/model_quadtree:/data deltares/sfincs-cpu:latest
```

## Validation

- **Sandy Hook gauge (8531680)** — temporal check (the gauge failed mid-storm at
  10-29 23:00, before Sandy's true peak, so it bounds rather than fixes the peak).
- **31 USGS high water marks** — spatial check on whether the model floods the
  same places to the same depth as Sandy did.
- **FEMA MOTF surge extent** — spatial flood-extent consistency (CSI / POD / FAR).

## Roadmap / known limitations

- **Back-bay conveyance** — getting enough water deep into the Shrewsbury/Navesink
  estuary (Oceanport, Rumson). The eHydro channel carve and the wavemaker helped;
  the narrows are still the limiting cross-section.
- **Sandy Hook Bay boundary** — the depth-only water-level/outflow rule mis-tags
  deep estuary cuts; a two-box geographic correction is implemented in the build
  but not yet re-validated.
- **X2 seaward extension** — push the domain offshore so waves develop across the
  shelf before reaching the model edge (removes nearshore numerical artifacts).
