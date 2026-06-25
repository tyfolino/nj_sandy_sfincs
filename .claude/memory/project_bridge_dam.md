---
name: project-bridge-dam
description: "NJ Sandy quadtree — ROOT CAUSE of the back-bay conveyance bottleneck FOUND 2026-06-12 (user's hypothesis): the Rumson–Sea Bright bridge causeway is baked into the NJ 10ft lidar DEM as a solid earthen dam across the Shrewsbury River at the narrows. Blocks tide + surge -> flat Shrewsbury gauge + Oceanport under-flooding. Fix: burn the channel through the causeway. Supersedes the generic 'narrows conveyance' framing."
metadata: 
  node_type: memory
  type: project
  originSessionId: 08346867-a115-4cc6-ba9e-64fedfeb2b3a
---

# Bridge-as-dam — root cause of the back-bay conveyance bottleneck (2026-06-12)

**UPDATE 2026-06-23 — fix CONFIRMED to work (user, on Amarel).** Running the
no-bridge-dam bathymetry (eHydro 2015 carve + usace_nj_2010 in elevation_list)
**the Shrewsbury river floods beautifully** — the back-bay deficit chased through
the inlet-channel / wavemaker work is resolved by carving the dam, as predicted.
Knock-on: this defuses the compensation worry that blocked the waterlevel-boundary
restriction (surge now reaches the back-bay through the inlet, not via an edge
clamp) → see [[project-mask-boundary-cleanups]], implemented 2026-06-23. Still
TODO: pull the quantitative back-bay verdict (CSI/HWMs) from the Amarel run.

**User's hypothesis, confirmed:** bridges are captured in the NJ 10 ft lidar DEM as continuous high ground that **dams the river channel**. The back-bay under-flooding + the flat Shrewsbury tide gauge are this one DEM artifact, not under-resolved bathymetry in general.

## The smoking gun
Thalweg test on the model bed (`dep_subgrid_lev3.tif`) = the DEEPEST point across the channel at each step (should stay below sea level up a tidal river):
- **Rumson–Sea Bright bridge, Shrewsbury narrows (y≈4,468,860 UTM18N, ≈40.367°N):** channel floor is −4 to −7 m everywhere EXCEPT a **~24 m-wide band where the deepest point is +1.6 m**. True-height cross-section (nearest resampling) is **100 % above sea level, embankment up to +8.6 m**. A complete dam — the entire section is dry land.
- **Rte 36 / Highlands bridge (→ Sandy Hook)** and the **Oceanic bridge (Navesink)**: channel stays −6.8 / −4.5 m under them → **NOT dams** (lidar caught open water). Only Rumson–Sea Bright fully blocks.

## Why this explains everything we'd been chasing
- **Flat Shrewsbury @ Sea Bright tidal validation:** the gauge's model cell is dry land at +1.88 m and the channel to it is dammed at +1.6 m, so the tide (obs range −0.4..+1.4 m) literally cannot reach it → flat line at the bed, one storm bump. See [[project-validation-roadmap]] (Shrewsbury tide panel).
- **Oceanport / upper-estuary surge under-prediction:** the surge arrives at the bay mouth at the correct level but the +1.6..+8.6 m dam blocks conveyance up the Shrewsbury → the wavemaker's east overtopping can't reach the western estuary. This is the "narrows conveyance bottleneck" from [[project-wavemaker-run]] / [[project-validation-roadmap]] — now PINNED to a specific bridge, not generic resolution.

## Fix
**Burn the Shrewsbury channel through the Rumson–Sea Bright causeway** — cut the +1.6..+8.6 m wall down to the adjacent channel depth (~−4 m) over the channel width, so tide + surge convey. Same technique as the earlier inlet-burn experiment (`experiment_inlet_connectivity.ipynb`, burned inlets at −2 m on the regular grid — never promoted; its value on the quadtree was untested, but THIS is the spot that actually needs it). It's a bed change → Phase-1 subgrid rebuild → **batch with X2** + the [[project-mask-boundary-cleanups]]. Also worth a sweep for other dammed crossings (railroad embankments, smaller road bridges) with the same thalweg test before rebuilding.

## Source-DEM provenance (2026-06-12) — confirms structure vs solid fill
Sampled the 4-tier merge sources at the crossing cells (priority USACE>CUDEM>NJ_lidar>GEBCO; USACE=`usace_nj_2010_topobathy_clip.tif` EPSG:4326, CUDEM=`cudem_asbury.tif` EPSG:5498, NJ=`nj_10ft_dem.tif` 4326 gated z>0.001, GEBCO 4326):
- **Route 36 piers: 100% from CUDEM** (USACE is NoData across the channel there). CUDEM is a topo*bathy* product built from in-water bathymetric surveys → it captured the bridge SUBSTRUCTURE (pier caps/pile clusters/fenders/riprap) at +0.5..+2.2 m, with the channel OPEN between piers. The high deck (~20 m) is in NO tier → channel stays open → model is accidentally correct. = your "bathymetry of the pilings" hypothesis, confirmed.
- **Rumson–Sea Bright dam: solid fill in ALL fine sources.** Of the 13,121 wall cells (merged +0.5..+8.8 m), USACE median +4.35 (0% sub-sea-level), CUDEM +3.56, NJ-lidar +3.55. Wall provenance 42% USACE + 58% CUDEM. **88% of the dam footprint has NO sub-(-0.5 m) value in any fine tier — genuine solid causeway, no channel to restore.** Only ~12% have a CUDEM sub-sea-level value (down to −4.7 m) that USACE's surface capture overrode — likely the real navigation opening.
- **FIX IMPLICATION:** can't re-prioritize/restore a buried channel (88% is fill); must CARVE a synthetic opening to ~−4 m (adjacent Shrewsbury floor). Use the 12% CUDEM-deep cells to place the burn on the real navigation alignment, not arbitrarily. (Route 36 needs no fix — channel already open.)

## Fix data source RESOLVED 2026-06-12 — eHydro channel survey (better than burning)
Instead of a synthetic burn, use a real bathymetric survey of the channel. NOAA **BlueTopo** covers the Shrewsbury (−4..−5 m near the bridge) BUT its pixels there are from a **Dec-2025 survey = POST bridge-rebuild** (the bridge was destroyed + rebuilt in 2025) → REJECT. Use **USACE eHydro** instead.
- eHydro REST: `https://services7.arcgis.com/n1YM8pTrFmm7L4hs/arcgis/rest/services/eHydro_Survey_Data/FeatureServer/0/query` (query by geometry; fields surveydatestart, sdsfeaturename, surveytype CS/BD/AD, sourcedatalocation=download URL).
- The Shrewsbury is a USACE federal nav project → **annual condition surveys (CS) 2015→2024**, all PRE-rebuild. **No pre-Sandy** (earliest 2015; channel is stable + we only need the opening depth, so 2015 is a fine 2012 proxy).
- **PICK: `NJ_14_SNR_20150902_CS_4368_15`** (2015-09-02, type CS). User confirmed via the eHydro viewer its footprint covers the WHOLE Navesink+Shrewsbury system — Sandy Hook Bay → through the Rumson–Sea Bright narrows → Oceanport, + Navesink to Red Bank. (My single-point API query falsely returned 0 — the surveyed channel is a thin thalweg strip and the test point sat just off it; the visible footprint is authoritative.) Download: `https://ehydroprod.blob.core.usgovcloudapi.net/ehydro-surveys/CENAN/NJ_14_SNR_20150902_CS_4368_15.ZIP`
- **Processing:** horizontal = NJ State Plane ft (NAD83) → reproject UTM18N; vertical = **MLLW ft → NAVD88 m via NOAA VDatum** (must-do). Add as a HIGH-PRIORITY elevation tier IN THE ESTUARY CHANNELS (above CUDEM/lidar) → restores the real channel under Rumson–Sea Bright AND sharpens the Navesink + whole back-bay thalweg. Covers only the dredged channel strip (not marsh flats) — but the channel is what conveys. Burn depth cross-checks: ~−4 m (eHydro + BlueTopo + our own thalweg of the adjacent open channel).
- This is a Phase-1 (bed→subgrid) change → **batch with X2** + [[project-mask-boundary-cleanups]].

## DOWNLOADED + PROCESSED 2026-06-17
Survey fetched + processed by `scripts/download_ehydro_shrewsbury.py` (cached/reproducible). Outputs (all under gitignored `data/`):
- `data/elevation/shrewsbury_ehydro_2015.tif` — 5 m, UTM18N, NAVD88 m, NoData OUTSIDE the dredged channel ribbon (masked to the eHydro `Bathymetry_Vector` coverage polygons). 128,605 valid channel cells; z median −3.0 m, min −12.4 m.
- `data/elevation/ehydro/shrewsbury_ehydro_2015_points.gpkg` — the 18,953 processed soundings.
- `data/elevation/ehydro/vdatum_offsets_2015.csv` — cached VDatum nodes (re-run is cheap).
Provenance details now confirmed from the ZIP: `.XYZ` = 18,953 thinned soundings, EPSG:3424 (NAD83 NJ State Plane US-ft), Z = MLLW **US survey ft, signed (negative below MLLW)**; `.DAT` is the same as +depth. Vertical conversion = **spatially-varying** NOAA VDatum REST API (geoid18): MLLW→NAVD88 offset ranges **−0.44 m (south) to −0.84 m (north/up-estuary)**, a 0.39 m gradient → applied per-point (interpolated from 400 cached in-water query nodes), NOT a single mean. `z_NAVD88_m = z_MLLW_ft*0.3048006096 + offset(x,y)`.
**Narrows validation (the whole point):** at the Rumson–Sea Bright bridge crossing latitude (y≈4,468,860 UTM18N) the eHydro tier gives CONTINUOUS channel coverage spanning x≈580,000–587,000 with z down to **−4.65 m** (median −2.9 m) — i.e. a real channel exactly where the merged DEM had the +1.6..+8.6 m dam. Carving confirmed.
**Catalog:** registered as `shrewsbury_ehydro_2015` and prepended as tier 0 (top) of the `setup_dep` list in `data/data_catalog.yml` (above usace_nj_2010 — safe because the footprint is estuary-channel-only and never touches the open-coast dune line).
**Notebook wiring:** the eHydro tier had to be added to THREE `elevation_list` blocks in `notebooks/sfincs-nj-sandy.ipynb`, not one — cell 9 (`5208270f`, `quadtree_grid.create_from_region`, gates refinement by bed → carved narrows now fall in the L3 −8..+3 gate → finer cells on the restored channel), cell 11 (`74a2cf62`, `quadtree_elevation.create`, bed onto mesh), cell 21 (`5228f7f8`, `quadtree_subgrid.create`, the load-bearing V-h conveyance tables). All three prepend `{"elevation": "shrewsbury_ehydro_2015"}`. (Gotcha: editing the .ipynb on disk while the user has it open in VSCode with a live kernel does NOT update their editor buffer — the kernel runs the buffer, not disk — so reload-from-disk or hand-paste was needed.)

## RAN 2026-06-17 — IT WORKED. The Shrewsbury floods. 🚀
Phase-1 rebuilt on the CURRENT mesh (no X2 yet) with the eHydro tier, then ran. **The Shrewsbury River floods now** — the +1.6 m bridge dam is carved out, tide + surge convey up the river into the back-bay. Root cause → fix confirmed end-to-end: real eHydro channel bathymetry restores conveyance through the Rumson–Sea Bright narrows. This is the isolated channel/conveyance fix (the east Sea Bright barrier overtopping side still wants the wavemaker, offshore ring still wants X2). User committing 2026-06-17 and done for the day. TODO next session: pull the quantitative verdict (Shrewsbury gauge tidal range restored? Oceanport/upper-estuary bone-dry HWMs come up from ~0.9 m toward obs ~2.9 m? back-bay MOTF box CSI past the 0.40 wavemaker baseline? any NEW over-flooding?) and decide whether east-barrier/wavemaker + X2 are still needed on top. See [[project-validation-roadmap]] Phase B.

## Diagnostic wired into the notebook (2026-06-12)
Added a "Diagnostic: bridges baked into the bed as dams" markdown + **interactive hvplot** cell (of `dep_subgrid_lev3.tif`) just before the end-of-notebook status section, for the supervisor meeting.

## Method note (reusable)
`dep_subgrid_lev3.tif` is on the **ROTATED** model grid. De-rotate before clip/plot/transect: `da.rio.reproject(da.rio.crs, resolution=3.0, resampling=Resampling.min)` — `min` keeps the deepest sub-pixel so genuine channel openings survive (don't mask a real opening as a dam). For TRUE wall heights use `resampling=nearest`.

Related: [[project-validation-roadmap]], [[project-wavemaker-run]], [[project-mask-boundary-cleanups]], [[project-nj-sandy]].
