---
name: coned-elevation-upgrade
description: "Elevation stack upgrade for the Sandy hindcast — pre-Sandy 1 m topobathy added as top layer, grid refined to 50 m. Completed 2026-05-13."
metadata: 
  node_type: memory
  type: project
  originSessionId: 2b650126-260c-4bb0-bed9-620be8c3d636
---

Upgrade to the [[NJ Sandy SFINCS project context]] elevation stack — completed 2026-05-13.

**What changed:**
- New top elevation layer: **2010 USACE NCMP Topobathy LiDAR DEM (NJ Atlantic Coast)**, NOAA ID 9456 — 1 m, NAD83, true topobathy, collected 2010 (~2 years pre-Sandy).
- Clipped to model bbox at `data/elevation/usace_nj_2010_topobathy.tif` (~248 MB).
- Download script: `scripts/download_pre_sandy_topobathy.py` (uses `gdalwarp` + `/vsicurl/` on the whole-mosaic VRT — no AWS creds needed, 60–90 s).
- 4-tier hierarchy in `data_catalog.yml` and both notebook `elevation_list` cells: usace_nj_2010 → cudem_nj → nj_10ft_dem (zmin=0.001) → gebco_nj.
- Grid res: 100 m → **50 m**.
- `nr_subgrid_pixels`: 8 → **16** (≈ 3 m effective).

**Why pre-Sandy and not modern CoNED / 2022 USACE:** the user reasoned this through unprompted on 2026-05-13 — Sandy is a hindcast, and post-storm products bake in ~$1B of NJ beach replenishment + engineered dunes that didn't exist 2012-10-29. Using post-storm data would systematically under-predict overtopping. The 2010 NCMP product is the closest pre-storm 1 m topobathy available for NJ.

**Why apply:** the surge-relevant surface (dune crest, beach face, surf zone) is the 2010 state because that's what the top layer governs. Post-Sandy CUDEM only fills areas seaward of the dune line, so contamination of the overtopping surface is minimal.

**Datasets we considered and rejected (record so we don't re-research):**
- `USACE_NJ_NY_DEM_2022_9851` — 2022, modern, post-replenishment. **Wrong for hindcast.** Worth using for present-day or forward-looking runs.
- `NewJersey_Delaware_Coned_Topobathy_DEM_2015_5040` — full USGS CoNED, integrates 1888–2014 source data, mixed pre/post-Sandy. Likely what Nederhoff et al. 2024b cited; great for general use but ambiguous temporal state for a clean hindcast.
- `Post_Sandy_DEM_2014_4967` — NOAA NGS flights flown Nov 2012 – Mar 2013. Captures storm-eroded surface — useful for post-storm calibration, not for hindcasting Sandy itself.

**Still open / next time:**
- The notebook hasn't been re-run yet — verify `dep_subgrid.tif` actually picks up the dune line and that the model still completes. Subgrid build will be ~4× slower than the 100 m / 8-pixel baseline.
- The `cudem_nj` CRS-mismatch warning during subgrid read is still unaddressed — catalog says `crs: 4269` but hydromt warns it doesn't match. Worth a separate look.
- If the user wants to validate the choice, comparing pre-Sandy NCMP to post-Sandy NOAA NGS over Long Beach Island / Mantoloking would show how much sand actually moved.
