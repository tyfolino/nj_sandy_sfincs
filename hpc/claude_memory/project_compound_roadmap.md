---
name: project-compound-roadmap
description: NJ Sandy SFINCS — roadmap for extending toward the Carolinas/Florence compound-flooding paper. Phase 1 = advection + rainfall + discharge; later = SnapWave/IG/quadtree.
metadata: 
  node_type: memory
  type: project
  originSessionId: d42c392d-6e72-4484-805c-d5b00cb0ae62
---

Roadmap set 2026-05-20 for closing the gap between our NJ Sandy model and the Carolinas/Hurricane-Florence SFINCS+SnapWave paper (van Ormondt/Nederhoff lineage; SFINCS v2.1.1 Dollerup). The paper is the reference target; it does explicit **SnapWave** (incident wave setup) + **IG waves via wavemakers** — NOT parametric Stockdon. Our current Stockdon term ([[project-stockdon-setup]], β_f=0.05) is a proxy because SnapWave isn't supported on regular grids in our hydromt_sfincs v2.0.0rc2.

## Conceptual correction (don't re-confuse this)
The paper's "ERA5 wave spectral parameters forced at deep water input points… stationary solver updates every 30 min" describes the **offshore wave BOUNDARY fed INTO SnapWave**, not a parametric formula. Stockdon comes from the cited **Parker et al. (2023)**, which is the source of both (a) the ERA5 wave-param retrieval and (b) the parametric setup. The Carolinas paper reused Parker's ERA5 wave inputs but replaced Parker's Stockdon with SnapWave.

## Phase 1 — DONE 2026-05-20 (regular grid, our version)
All three wired into the notebook and verified with a clean Phase-2 run (SFINCS log: Advection/Precipitation = yes, discharge active; sfincs.inp has advection=1, netamprfile, netsrcdisfile).
1. **Advection** — turned out to be ALREADY ON: hydromt-sfincs defaults `advection=1` and always writes it, so the log showed "Advection: yes" all along. Made explicit in the config cell for the record (no physics change). (Earlier guess "SFINCS default is off" was wrong.)
2. **Rainfall = AORC** — `scripts/download_aorc_sandy_precip.py` pulls NOAA AORC v1.1 from `s3://noaa-nws-aorc-v1-1-1km/2012.zarr` (var `APCP_surface`, kg/m^2 == mm accumulated per 1h → `cumulative_input=True`), clips to domain → `data/precip/aorc_sandy_nj.nc`. Catalog `aorc_sandy_nj` (RasterDataset/raster_xarray). Cell "2b": `sf.precipitation.create(precip="aorc_sandy_nj", cumulative_input=True, aggregate=False)`. ~34 mm total over window, peak 13.3 mm/hr — minor (Sandy surge-dominated here; heavy rain fell inland). Needed `pip install s3fs` into the sfincs env (downgraded botocore 1.43.2→1.43.0, harmless boto3 warning).
3. **Discharge = USGS** — `scripts/download_usgs_sandy_discharge.py` pulls DAILY-mean discharge (IV not archived for these small gauges in 2012) from NWIS for gauges 01407705 (Shark River) + 01407500 (Swimming River/Navesink), cfs→m³/s → `data/discharge/usgs_sandy_discharge.nc`. Catalog `usgs_sandy_discharge` (GeoDataset/geodataset_xarray). Cell "2c": `sf.discharge_points.create(geodataset="usgs_sandy_discharge", merge=False)`. **GOTCHA: the location dim MUST be named `index`, not `stations`** — discharge_points.create reads `da.vector.index_dim` and feeds it to GeoDataset.from_gdf which assumes `index`; `stations` raises "Index dimension stations not found in data_vars". Src points placed at the wet estuary inflow cell (NOT the upstream gauge), verified vs model/gis/{mask,dep}.tif: Shark (40.195,-74.035), Navesink (40.370,-74.045). Peaks 3.5 / 7.9 m³/s — negligible vs surge.

**Result of the compound run:** interior now wets from rainfall where surge alone left it bone-dry (inland-low went 207→all cells wet, but median DEPTH only ~4 cm = a physical rain film; the alarming zsmax ~16 m was just thin film on high-zb cells). Sandy Hook validation peak unchanged (3.93 m full-run) — correct, since rain/discharge don't touch the boundary-driven gauge. Compound signal is real but modest on this surge-dominated coast.

**data/ and data_catalog.yml are gitignored** in this repo — only the download scripts are tracked (they regenerate the data + catalog edits must be re-applied or are also untracked). Note: catalog edits won't show in `git status`.

Carolinas paper reference data sources we did NOT match: ERA5 (not Stockdon) waves; GTSM+Parker WLs; NLDAS rain; NWM discharge.

## Infiltration — ADDED 2026-05-20 (beyond the paper; they omitted it)
The paper explicitly excludes infiltration (Florence = 910 mm extreme → soils saturate fast, losses negligible; and it's outside their wave-focused scope; NWM rivers already embed catchment infiltration). Our case differs: modest rain (34 mm) on a surge-dominated domain made the no-infiltration rain-film artifact proportionally visible (interior ponding ~2.9M m³ on ground above surge reach), so adding it was worthwhile.
- **NRCS Curve Number** method. `scripts/build_cn_nj.py` builds CN = f(NLCD 2012, SSURGO HSG) using the shipped `DATADIR/lulc/NLCD_HSG.csv` lookup → `data/infiltration/cn_nj.nc` (EPSG:4326, var `cn`). Catalog `cn_nj`. Notebook cell "2d": `sf.infiltration.create_cn(cn="cn_nj", antecedent_moisture=None)` (None → reads `cn` = CN II; default 'avg' would look for nonexistent `cn_avg`). Writes sfincs.scs + scsfile; SCS consumes RAINFALL only, never surge.
- **HSG source = USDA SSURGO via Soil Data Access REST** (`https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest`, no auth; spatial SQL with mupolygongeo.STIntersects). HYSOGs250m is Earthdata-gated. 713 polys in-domain, dominant-component hydgrp. Mix: A(sandy) dominant + D + duals.
- **NLCD_HSG.csv decoding (non-obvious!):** columns are HSG integer codes, NOT sequential A,B,C,D. Decoded from CN values (must rise A<B<C<D): **col 1=A, 6=B, 5=C; cols 3/2/7/8 all = D-equivalent (D + all dual groups lumped at undrained D-CN); col 4 = nodata.** Map A→1,B→6,C→5,D & duals→3.
- NLCD tif CRS is a non-standard Albers/WGS84 (no EPSG) — reproject CN to EPSG:4326 before writing or the catalog CRS is ambiguous.
- **Result:** interior ponding ground>6 m went 0.79M → 0.01M m³ (rain film gone; inland-low wet cells 20294→25). HWM tradeoff: infiltration also trims coastal rain, so wet marks 24→20 and quality≤3 RMSE 0.91→1.04 m (mean +0.04) — slightly drier/more conservative at the coast, much cleaner inland. Net win.
- **OPTION FOR LATER:** the "2d" cell prints SCS retention S mean ~444 / max 990 inch — dominated by CN=0 water cells (S→∞). Harmless (SCS consumes rainfall only) but misleading; could mask water out of that diagnostic print to report land-only S. User said don't bother now (2026-05-20).

## Phase 2 — WIRED 2026-05-22, NOT YET RE-RUN
ERA5 wave field replacing single-buoy uniform Stockdon. Data: `scripts/download_era5_waves_cds.py` + `data/waves/era5_waves_nj.nc` (swh→hs, pp1d→tp, mwd→wd; 0.5° grid 11×9; ~43 of 99 nodes NaN/land near the coast).
DONE 2026-05-22: (1) catalog entry `era5_waves_nj` added; (2) Stockdon cell `bf111cf3` rewritten to sample nearest valid ERA5 node per support point (Battery N 40.70, Atlantic City S 39.36) → per-point η → N-S gradient, β_f=0.05; **fixed a (x,y)-vs-(y,x) broadcast bug** in the nearest-node search (flatten valid nodes via np.where(vmask)+meshgrid, argmin on 1-D); (3) markdown `4d2cda55` updated; (4) subtract-setup diagnostic added to Phase 3 (`cf38cd9d`+`a56fc5b0`, after Sandy Hook validation `2a04c49f`). Dry-run gradient: N setup 0.87 m / S 0.78 m.
**STILL TODO:** re-run Phase 2 (`r+`, merge=False, latitude patch) → clear root-owned outputs via Docker → run SFINCS → re-check Sandy Hook AND open-coast ≥4 m HWMs together. Expectation: Sandy Hook eases ~+0.39→+0.26 m (not closed; bay needs SnapWave); open coast is where ERA5 should help. See [[project-stockdon-setup]] for the wiring detail + the 2026-05-22 datum audit (whole chain is NAVD88; `nj_10ft_dem` relabeled m+MSL→m+NAVD88, verified empirically).
SnapWave explicitly deferred per user 2026-05-21.

## Phase 2 detail — LATER (parametric improvement, no version bump)
4. Replace single-buoy (NDBC 44025, applied uniform alongshore) Stockdon driver with a **spatially-varying ERA5 wave field** (swh, pp1d/mwp, mwd, dir-spread from CDS reanalysis-era5-single-levels) → alongshore-varying setup. Directly fixes the "under-states alongshore variation" caveat in cell 1b. See [[project-stockdon-setup]].

## Phase 3 — BIG (version upgrade + grid rebuild)
5. SFINCS v2.1.1 Dollerup + quadtree variable grid (200 m → 25 m at dunes/surfzone).
6. SnapWave coupled wave solver (explicit incident setup) — replaces Stockdon.
7. IG waves: offshore bound IG via Herbers (1994)/Leijnse (2024), injected via absorbing-generating wavemakers (van Dongeren & Svendsen 1997) at ~5 m depth. This is what actually drives dune overtopping/runup — the deepest reason Stockdon is only a proxy.

## Cross-cutting: validation — HWMs DONE 2026-05-20
Spatial validation now exists. `scripts/download_sandy_hwms.py` pulls USGS High Water Marks from the STN Flood Event Viewer (Sandy = **event_id 24**, endpoint `https://stn.wim.usgs.gov/STNServices/Events/24/HWMs.json`; fields `latitude_dd`/`longitude_dd`/`elev_ft`/`vdatum_id`(2=NAVD88)/`hwm_quality_id`(1=best..5=poor)). **31 marks fall in-domain** (all coastal, NAVD88, 2.9–5.79 m) → `data/validation/sandy_hwms.geojson`. Notebook cell after the downscale cell (id cd5b78c0) compares each mark to the **wettest modeled cell within a 50 m radius** (nearest-pixel fails — at 6 m resolution it lands on the building/raised lot the mark sits on, reads dry). Sign: + = model over-predicts.
**Result vs current compound run:** quality≤3 subset (21 pts) mean bias −0.02 m, median +0.17, RMSE 0.92 m, 48% within ±0.5 m; ~6 marks dry in model (local under-pred, partly the deep-ocean mask `da_dep>-0.5` in the downscale cell). **So the model is essentially unbiased — NOT systematically over/under-flooding Sandy.** This validates the boundary + Stockdon water levels spatially, and gives a target for tuning β_f / future SnapWave.
Still missing vs paper: USGS storm-tide sensor TIME SERIES (also in STN) for 4 coastal points.

### HWM regional diagnostic 2026-05-20 (where misfits cluster)
Broke the 31 HWMs down by setting. Key findings:
- **Open beachfront: model matches obs<4 m marks (mean resid −0.18 m) but badly UNDER-predicts obs>=4 m marks (mean −2.56 m), and the dry marks include the highest obs (5.79, 4.18 m).** High open-coast marks = wave runup/swash → still-water+uniform-Stockdon can't reach them. **This is the SnapWave/IG-runup signal.** Corrects the earlier "SnapWave probably isn't the lever" take — for OPEN-COAST extremes / dune overtopping it IS.
- **Back-bay (Sandy Hook Bay/Navesink) is NOT under-reaching** — it's fine/slightly over (+0.52 m). The "dry" bay marks were a VALIDATION ARTIFACT: the HWM cell reuses `da_hmax` which the downscale cell masks with `da_dep>-0.5`, dropping deep bay water cells. So connectivity/roughness is NOT the bay bottleneck.
- Uniform Stockdon is too HIGH in sheltered spots (Sandy Hook ocean +0.67, Shark inlet +0.94) and too LOW at the high-energy beachfront → points to spatially-varying ERA5 wave field (Phase 2) then SnapWave (Phase 3).
- **BUG to fix:** HWM validation cell (d238b602) inherits the `da_dep>-0.5` ocean mask from the downscale cell (cd5b78c0), under-counting bay marks. Recompute an unmasked downscale inside the validation cell (or pass the unmasked hmax). Not yet fixed.

### HWM validation rework 2026-05-22 (post-ERA5 run) — three fixes
After the ERA5 Phase-2 re-run, the HWM scatter still looked scattered. Diagnosed + reworked cell `d238b602` and added a new envelope diagnostic. KEY FINDINGS:
- **Stratify by survey quality — the cloud IS ~1:1 for trustworthy marks.** q≤2 (n=14): mean +0.11 m, RMSE **0.44 m**. The ugly scatter is dominated by q3-q4 (poor-quality surveys) + runup marks. Headline should be q≤2.
- **Ground-cap filter** added to the 50 m WSE search: only accept flooded cells with `da_dep <= obs + 0.5` (water reaching a mark came from ground at/below it). Kills the +2 m outlier (q3 @ lat 40.196: +2.0 → +1.2). This also obsoletes the old `da_dep>-0.5` mask worry — cell now downscales straight from zsmax with the ground cap.
- **Runup envelope diagnostic** (new md `cf38cd9d`-style + code cells inserted after residual-map `c4b10c3b`): bracket each HWM by [still-water .. still-water + **Stockdon R2%**]. R2% = 1.1(η + S/2), S=hypot(0.75·β_f·√(H0L0), 0.06·√(H0L0)) (incident+IG swash), from ERA5 waves + β_f=0.05. **81% of all marks (79% of q≤2) fall inside the envelope.** R2% ≈ 2.9 m above still water at Sandy peak (IG-dominated). Highest open-coast marks (obs 5.3, 5.8) ride the runup TOP → that's the IG/runup tail needing SnapWave+IG (Phase 3), NOT a model bug. CORRECTION to my earlier guess: full R2% is an UPPER ENVELOPE, not a 1:1 point-predictor — it over-shoots moderate marks; only the most-exposed marks reach it.
- Verified figs render (/tmp/hwm_envelope.png). Cells need a Phase-3 re-run to populate in the notebook. da_dep/da_zsmax/wse/depth/T/obs/qual/hwm/mod_wse/wet/resid are shared from `d238b602` into the envelope cell.

### Validation cleanup + new gauges 2026-05-22 ("back to basics", plan spicy-honking-river)
Decluttered Phase 3 and added two new in-domain validation sources. All Phase-3 cells re-verified end-to-end headless (no re-run of the model needed; reads current `model/` outputs).
- **Cut** the interior-obs peak/freeboard table (`1c46203c`+`2589669d`) and zone stats (`27e996fd`). **Relocated** `point_zs`/`point_zb`/`names` (defined in the deleted table cell) into the Sandy Hook validation cell `2a04c49f` so it stays self-contained. Moved the static flood map (`c0345359`) to follow the downscale cell. Kept core + 2 diagnostics (subtract-setup, runup envelope). Backup at /tmp/nb_before_cleanup.ipynb.bak.
- **EVERY permanent gauge in the domain failed mid-storm.** NOAA Sandy Hook (10-29 23:00) AND the two USGS estuary gauges (uv ends ~10-29 04:00 UTC). This is why HWMs are the spatial fallback.
- **B0 — USGS tidal gauges (pre-storm only), `scripts/download_usgs_sandy_tidal.py` → `data/gtsm/usgs_sandy_tidal_nj.nc`, catalog `usgs_sandy_tidal_nj`.** Param 72279 (NAVD88). Two in-domain estuary gauges: 01407770 Shark R @ Belmar (40.19 S), 01407600 Shrewsbury @ Sea Bright (40.37). New validation cell samples model `zs` at nearest grid cell. Findings: Shark River tidal range obs 2.15 vs modeled 2.48 (model ~0.5 m high at peaks — same setup-into-sheltered-water bias as Sandy Hook, so it's NOT only northern); Shrewsbury back-bay modeled range 0.05 m — estuary NOT hydraulically resolved at 50 m (connectivity limit, cf. Deal Lake).
- **B1 — storm-tide sensor (peak-capturing!), `scripts/download_sandy_storm_tide_sensors.py` → `data/gtsm/sandy_storm_tide_nj.nc`, catalog `sandy_storm_tide_nj`.** The continuous series ARE retrievable (despite STN bulk data_files=0) at `Instruments/{id}/Files.json` → `Files/{file_id}/item` (.txt, NAVD88, GMT). In-domain USGS SSS wave sensors at Monmouth Beach (40.37, instruments 2258/2259) recorded 10-29 22:00 → 10-30 10:00, **through the peak**. Wave sensors → mask de-watered (floored) samples; stormtide_m = 30-min mean (still water), wavemax_m = wave-crest envelope. **CAVEAT (corrects an over-claim): the two co-located units BRACKET the model** — stormtide peaks 3.47 & 4.97 m vs modeled 3.80 m — so they do NOT cleanly prove the open-coast under-prediction. But wave crests 5.2-5.9 m match the highest HWMs (5.3/5.8) → confirms that tail is wave runup the still-water model omits. HWMs remain the cleaner spatial validation.
- Notebook Phase-3 validation flow now: Sandy Hook ts → subtract-setup → USGS pre-storm tides → storm-tide sensor (peak) → downscale+static map → HWM scatter (q≤2 headline) → HWM residual map → runup envelope → interactive map.
- **Still deferred** (decide after this): southern boundary anchor (no sensor data there), SnapWave/IG.

### Spatial-extent validation added 2026-05-23 (FEMA MOTF Sandy surge footprint)
Added a SPATIAL extent comparison (the HWMs are points; this is the footprint). New script `scripts/download_sandy_motf_extent.py` → `data/validation/sandy_motf_extent.tif`, catalog `sandy_motf_extent`. New cell (markdown + code) after the runup envelope (id 76befc8c after `075849f3`).
- **Source:** Rutgers MapServer layer 0 "Sandy Surge Extent" (FEMA MOTF Final Field-Verified, HWM/sensor-interpolated over lidar = bathtub surface, NOT a hydrodynamic run → **shares HWM provenance; consistency check, not independent validation**).
- **Two non-obvious traps in this env:**
  1. The NJ extent is ONE giant statewide polygon; `/query` returns the feature with `geometry: null` (transfer limit) even with `maxAllowableOffset`. Use the service's `export` (render) op → PNG with `transparent=true`, treat alpha>0 as flooded.
  2. The conda env's GDAL can't find proj.db on its own (`free()` / `double free or corruption` on CRS write). Required: shell-export `PROJ_LIB=$CONDA_PREFIX/share/proj PROJ_DATA=... GDAL_DATA=...` BEFORE invoking the download script (in-script `os.environ[...]=` is too late once the GDAL shared lib is loaded). Also: import order matters — `requests`/`geopandas`/`PIL` MUST come before `rasterio`, or write aborts. AND avoid `rasterio.features.geometry_mask` in this env (crashes). The script docstring documents this; reads are fine without the env vars (only writes need them).
- **Comparison method (pure numpy, no GDAL warp):** both rasters in EPSG:32618, so sample model `da_hmax`/`da_dep` at MOTF pixel centers via index math. Restrict to land cells (model `dep > 0`) inside the MOTF nodata mask. Threshold model wet at `da_hmax ≥ 0.15` m (matches HWM cell). Compute hits/miss/FA → **CSI / POD / FAR** + categorical map (green/blue/red).
- **Result this run:** MOTF land flood 38.3 km², modeled 30.8 km² → **CSI 0.46, POD 0.57, FAR 0.29**. Misses cluster in back-bays / inland lows (Shrewsbury, Wreck Pond, Shark River — runup + 50 m connectivity limits); false alarms at Sandy Hook spit & a few southern spots (the bay setup leakage). Spatial picture matches the HWM residual map and quantifies the same over/under story.

### Inlet-connectivity experiment + ablation findings 2026-05-24
Built an isolated side experiment (`scripts/build_inlet_channels.py` + `notebooks/experiment_inlet_connectivity.ipynb` + `model_inlet_test/`) to test whether resolving inlets via DEM burn fixes the inland MOTF misses. Main `model/` and notebook untouched.

**Finding 1 — no-waves ablation (accidental, via skipped Stockdon cell on the first run):** Same build, just dropped the ~0.8 m Stockdon setup off the boundary (peak bzs 4.22→3.42 N, 2.59→1.88 S). Result: **ΔCSI = -0.17 (0.46 → 0.29), POD 0.57 → 0.33, 9.26 km² of lost hits, zero new hits.** Strong single-number evidence that the parametric wave setup is worth ~17 CSI points (~37 % relative skill) at the extent level — justifies SnapWave investment. Keep this as a reference panel.

**Finding 2 — DEM-burn connectivity test (inconclusive, not negative):** Hand-drawn inlet polylines at Shrewsbury/Shark River/Deal Lake, burned at −2 m / 60 m wide. After the Stockdon fix, ΔCSI = 0.00; tiny changes (35k m² new hits, 181k new FAs) only near Shark River. Per-inlet wetness diagnostic showed WHY:
  - **Shrewsbury (5167 burn px, 100% wet, peak depth 13.9 m):** burn landed in already-deep harbor cells (~−10 m natural bathy from CUDEM). Redundant, no test of connectivity.
  - **Shark River (2770 burn px, 100% wet, peak WSE 6.26 m):** burn landed in open-coast/surf cells already passing flow. Redundant.
  - **Deal Lake (1572 burn px, 1 wet @ 0.14 m):** polyline missed the actual ocean-to-lake path → burn stayed dry. Test failed.
  - **Subgrid dilution caveat:** even where placed correctly, a 60 m channel in a 50 m grid cell occupies only ~12 % of cell area; subgrid u_havg is still dominated by surrounding land elevation → effective conveyance stays shallow.
  - **Meta-lesson:** hand-drawn lat/lon polylines aren't accurate enough at 50 m to test connectivity reliably; would need to draw against the actual `msk`/`dep` rasters in QGIS, or use `sfincs.drn` drainage structures (explicit hydraulic links that bypass subgrid averaging). Cheap test was too fragile — settles "don't iterate on DEM-burn approach; commit to quadtree when ready."

### Phase 2 status (as of 2026-05-24)
**Done:** advection, AORC rainfall, USGS discharge, SCS infiltration, ERA5 per-support-point Stockdon (re-run done; current `model/` outputs reflect it), USGS pre-storm gauges, storm-tide sensor, HWMs, FEMA MOTF extent.
**Still TODO in Phase 2 (cheap, no version bump):**
- ~~NLCD → Manning reclass swap~~ — **DONE 2026-05-25** (Bunya/Atkinson Atlantic-coast values, classes 23/24 NJ-tuned to 0.10/0.13 after a class-FA diagnostic). See [[project-manning-nj]]. CSI 0.46→0.49, FAR 0.29→0.28. Notebook updated; main `model/` will pick it up on the next Phase-1 rebuild.
- Rename `deal_lake_outlet` obs point (it's actually in Wesley Lake — see [[project-noaa-boundary]]).
- Keep the `latitude` re-injection workaround in the Phase-2 write cell until hydromt-sfincs upstream fix.

Related: [[project-stockdon-setup]], [[project-noaa-boundary]], [[project-coned-upgrade]], [[project-nj-sandy]], [[project-snapwave-plan]].
