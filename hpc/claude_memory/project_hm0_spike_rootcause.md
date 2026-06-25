---
name: project-hm0-spike-rootcause
description: "NJ Sandy SnapWave X1 run — root cause of the two open-ocean/surf-zone anomalies, found 2026-06-01. (1) hm0 surf-zone spikes = GEBCO integer-quantized bathymetry filling nearshore NoData gaps where CUDEM clip was too small, creating artificial cliffs that blow up SnapWave shoaling. (2) offshore zs spikes = 2dx boundary-edge oscillation, fixed by X2. Param-tuning made hm0 WORSE. CUDEM re-clipped to fix; Phase-1 rebuild + re-run pending."
metadata: 
  node_type: memory
  type: project
  originSessionId: 63424ae5-8815-4197-8275-6cf0f8cea8eb
---

# hm0 spike + open-ocean zs spike — root cause (2026-06-01)

Session goal: investigate the "really high water level values in the open ocean" from the X1 SnapWave run (see [[project-snapwave-root-cause]] known-issues #1 and #2) and confirm they aren't problematic instabilities. Found TWO distinct, both-localized, both-NON-FATAL artifacts and nailed both root causes.

## Headline for the paper
**Through everything, every observation-point water level is identical to ±0.01 m** between configs. SFINCS's shallow-water force limiter fully decouples the garbage hm0 from the momentum/flood solution. So both anomalies are **wave-field-MAP quality issues, not flood-prediction problems.** The Sandy Hook validation (bias +0.02 m, see [[project-snapwave-root-cause]]) stands.

## Anomaly ① — surf-zone hm0 spikes (ROOT CAUSE FOUND)
- X1 baseline: 85 cells max hm0>10 m, worst 425 km, all level-4 (25 m) surf-zone cells.
- **Discriminator = bathymetric steepness.** Spike cells have median 4.08 m depth-jump to a neighbor (80% >2 m); control surf cells median 0.15 m (6% >2 m). Among all surf cells, mean gradient 4.43 m where hm0>10 vs 0.50 m where not. ~9× separation.
- **NOT a refinement-interface effect** (spike cells hit level interfaces at ~7%, same as the general finest-cell population — yesterday's interface theory is dead, now properly tested with the SFINCS quadtree neighbor arrays `mu1/mu2/md1/md2/nu1/nu2/nd1/nd2` + transition flags `mu/md/nu/nd` in sfincs.nc; the earlier shared-node adjacency was BROKEN because the map mesh uses discontinuous private corner nodes per face).
- **ROOT CAUSE: GEBCO (450 m, 100% integer-quantized) filling nearshore NoData gaps.** At spike cells BOTH USACE NCMP (1 m) and CUDEM 1/9" return NoData, so the 4-tier merge falls through to GEBCO's flat integer plateaus (−5, −6, −7, −8 m: ~34k cells domain-wide). Where a GEBCO −5 cell abuts a real lidar/CUDEM cell (e.g. +1 m beach) at 25 m → 5–6 m artificial cliff → SnapWave stationary shoaling concentrates energy across the cliff faster than depth-limited breaking removes it → runaway.
- **Why the Sandy Hook gap exists:** `data/elevation/cudem_asbury.tif` was clipped to north-edge UTM-N **4,478,396**, but the region was later expanded north to **4,483,890** to add Sandy Hook (see [[project-noaa-boundary]]) and CUDEM was never re-clipped. The catalog comment literally says "Re-clip if region changes." The raw tiles covering Sandy Hook (ncei19_n40x50_w074x00 etc.) were already on disk; `cudem_nj.vrt` covers the whole region.
- **FIX APPLIED 2026-06-01:** re-clipped `cudem_nj.vrt` → `data/elevation/cudem_asbury.tif` (projwin -74.10 40.56 -73.80 40.10; new N-edge 4,490,607). Old clip backed up as `cudem_asbury.tif.bak_preSandyHook`. Verified valid CUDEM now at all spike cells (worst cell 241571: NoData→+1.86 m). **STILL TODO: rebuild Phase 1 (elevation merge → subgrid, ~13 GB RAM, via notebook) + re-run + confirm spikes gone.**
- **Residual:** ~50% of deep-step neighbors were non-integer (real CUDEM) — an Asbury/Long Branch sub-cluster sits on genuinely steep nearshore bathymetry (real channels/scarps), which the re-clip won't touch. Likely needs light DEM smoothing or is physically real; revisit after the rebuild.

## Anomaly ② — open-ocean zs spikes (the "high water levels")
- A ~500 m patch of 50 m cells 35 m inside the open boundary (msk==2), on the flat zb=−10 m shelf off southern Sandy Hook (~581.3k, 4479.7k UTM). 8.6 km from nearest SnapWave .bnd point (NOT direct wave forcing).
- zs does grid-scale 2Δx ringing (e.g. −2.47 → +5.46 → −1.99 between snapshots) for 1–2 of 73 timesteps, post-storm-peak; median there a sane 0.77 m. Max zsmax 12.4 m (transient, not physical).
- **This is the boundary-edge symptom of the X1 shortcut** (waves injected at the SFINCS open-boundary edge with no offshore transformation → force gradient on top of the open boundary). **X2 (seaward extension) is the structural fix.** It already improved on its own (12.4→7.2 m) when SnapWave config changed.
- Separately: zsmax>10 m in ~13.4k cells is just dry-land zs=zb reporting (inland hills) — cosmetic; mask to wet (zs−zb>thresh) for figures.

## Failed experiment (informative): Tim's canonical SnapWave params
Added Tim Leijnse's full physics block (gamma=0.78, alpha=1.0, hmin=0.01, niter=100, fw=0.02, dtheta=5, sector=180, igwaves=1) from his shared notebook `notebooks/build_quadtree_from_script_TKI-share_..._withigwaves_withwavemaker.ipynb`. Result: hm0 spikes **WORSE** — 85→1068 cells >10 m, max 425 km→9×10¹⁶ m. This PROVED the spikes are structural (breaking is just barely damping a runaway; loosen gamma 0.70→0.78 and every borderline-steep cell tips over), not a config gap. Water levels unchanged ±0.01 m; offshore zs ring improved 12.4→7.2 m. Reverted to baseline inp; Tim-params saved as `model_quadtree/sfincs.inp.tim_params_experiment`.
- **Gotcha:** changing dtheta/sector invalidates the cached binary `snapwave.upw` (directional-connectivity file) → "End of file" crash at snapwave_domain.f90:231. Delete snapwave.upw so SnapWave regenerates it.

## Tim's notebook (canonical SnapWave-quadtree reference, in notebooks/)
Single-point ASCII snapwave.bnd; mask boundary via `quadtree_mask.create_boundary(btype="waterlevel", zmax=-4)` and `(model='snapwave', btype="waves", zmax=-4, connectivity=4)`; refinement via `quadtree_grid.create(..., refinement_polygons=gdf)` with `refinement_level` column. Reference for the X2 seaward-extension build.

## X1 ported into the notebook (2026-06-01)
The working X1 SnapWave setup was previously only in `/tmp/x1_relocate_inputs.py` (since cleared) — the notebook still had the OLD broken `create_from_grid` cell + a stale "wavebnd flip" workaround. Ported X1 into `notebooks/sfincs-nj-sandy.ipynb` (now 71 cells, was 73) so it's reproducible:
- **snapwave_mask = SFINCS mask** (was: wider −50 m mask + −15 m wavebnd + flip workaround). Verified the on-disk X1 had snapwave_mask byte-identical to SFINCS mask.
- **Boundary input points**: seaward (Atlantic) edge of the mask==2 boundary — bin by northing, take easternmost cell per bin (avoids bay/western boundary). Matches on-disk X1 points to 84 m.
- **Uniform ERA5 forcing** from node (−74.0, 40.0) (only valid offshore node; 40.5 are NaN), broadcast to 7 points, written as ASCII snapwave.{bnd,bhs,btp,bwd,bds} in the post-write "finalize" cell.
- Config: snapwave=1, snapwave_igwaves=1, dtwave=1800; NO wider physics block, NO wavemaker. Snapwave keys force-added to sfincs.inp in finalize (hydromt-rc2 drops keys, like the latitude bug).
- Finalize cell also unlinks stale snapwave.upw + snapwave.nc each run (so the upw regenerates for the directional config — avoids the dtheta/sector "End of file" crash at snapwave_domain.f90:231).
- Deleted flip-workaround cells; neutralized the wavemaker cell. CUDEM picked up automatically (catalog cudem_nj → cudem_asbury.tif, which we re-clipped).
- **NOT executed by me** (Phase-1 rebuild = ~13 GB RAM); validated by compiling all cells + simulating the point-selection against the on-disk model. User runs it.

## REBUILD RESULTS (2026-06-02) — CUDEM fix confirmed, partial
User ran the ported notebook start-to-finish with the re-clipped CUDEM. Clean run (avg dt 1.215 s, 643 s wall, SnapWave 30.7%, no instability). Active cells 234,908 (was 237,488; mask shifted with new bathy).
- **hm0 spikes: worst 425,431 m → 8,815 m; cells >10 m 85 → 63; >100 m 3 → 1.** The Sandy Hook GEBCO-cliff cluster is GONE; residual ~63 cells are the Asbury/Long-Branch REAL steep-bathy ones (non-integer neighbours) — separate, smaller follow-up (light DEM smoothing or accept+mask for plotting).
- **Sandy Hook validation:** modeled peak 2.45 m (pre-failure window) vs observed 2.81 m; full-run modeled peak 3.47 m. Fit visibly better through the storm, but NOISY.
- **The zs NOISE is NOT the waves.** Verified at the Sandy Hook his point: hi-freq noise std 0.22 m PRE-storm when hm0≈0 at the gauge, and corr(|noise|, hm0)=0.08. It's the numerical boundary-edge 2Δx oscillation (gauge sits ~2.7 km from that −10 m boundary ring) — **X2 (seaward extension) is the structural fix.** Possibly also wind/pressure seiche.

## Notebook validation cells — quadtree adaptation (xc fix DONE; flood-map DEFERRED)
The Phase-3 validation cells were carried over from the regular-grid notebook and assume gridded output (xc/yc, isel(y=,x=)) — they break on the quadtree (zs dims = (time, nmesh2d_face), no xc/yc).
- **DONE (2026-06-02):** cells 52 (pre-storm USGS tides) + 54 (storm-tide sensor) fixed → sample nearest mesh face via `mod.quadtree_grid.data.grid.face_coordinates` + `isel(nmesh2d_face=...)`. Cell 52 uses nearest-WET face (Shrewsbury back-bay gauge's nearest face is dry/NaN otherwise). Cell 50 (wave-setup diagnostic) was already fine (its isel is on the ERA5 grid, not the map). `mod.output.data[var]` entries are UgridDataArrays; `mod.output.data` itself is a dict.
- **DONE (2026-06-02) — flood-map / HWM block:** the downscale cell referenced a single `subgrid/dep_subgrid.tif` that DOESN'T EXIST on quadtree — the build writes PER-LEVEL tifs `dep_subgrid_lev0..3.tif` (+ manning_subgrid_lev0..3), each covering ONLY that level's cells (lev3 = finest 3 m = dune/surf where HWMs are; lev0 = 200 m offshore). **ROOT CAUSE of the >24 GB OOM:** the grid is ROTATED, so `downscale_floodmap`'s rotated path calls `xu.UgridDataArray.from_structured2d` on the whole 69M-px L3 DEM → converts it all to an unstructured mesh at once. **FIX:** pass dep as a PATH + `floodmap_fn` + `nrmax=1000` → it TILES the DEM into ~1M-px blocks (bounded memory ~1-2 GB), writes `floodmap_hmax_lev3.tif` to disk; read it back. The HWM cell now REUSES that disk floodmap instead of re-downscaling the in-memory DataArray (which OOMs identically). `utils.downscale_floodmap` accepts a UgridDataArray zsmax; `mod.output.data[var]` entries are UgridDataArrays.
- **Still imperfect:** lev3 only covers the dune/surf corridor, so back-bay HWMs read as "model dry" and the flood map is coastal-focused; a future improvement is mosaicking L2+L3 into one DEM. MOTF extent cell (65/69) untested on quadtree — may need the same treatment.
- **Lesson:** each hydromt `model.read()` is multi-GB; loading several copies in side-processes caused the host OOM/agent crashes this session. Edit cells as lightweight text (no model load) and let the user run in their kernel.

## Full Phase-3 validation runs (2026-06-02) — notebook works end-to-end on quadtree
After the xc fix + tiled+de-rotated downscale + da_hmax.name fix, the whole notebook runs. MOTF spatial validation: **CSI 0.48, POD 0.54, FAR 0.17** (comparable to regular-grid ~0.49; Shark River + Sandy Hook extent visibly improved).
- **KEY: the flood map used ONLY the L3 DEM (dep_subgrid_lev3.tif), and L3 refinement is elevation-gated to z∈[−8,+3] m** (refinement_polygons.geojson: surf_dune poly). So the Navesink/Shrewsbury estuary channels + open water (z<−8 = L2/50 m cells) are NOT in the flood map → they score as "MOTF wet, model dry" (the big 16.3 km² blue miss). **This is largely a flood-map COVERAGE artifact, not proven under-prediction.** Must mosaic L1+L2+L3 before judging the back-bay.
- **Inland "spurious" false alarms (4 km²):** low inland cells (z≤+3) the model wets but surge-only MOTF doesn't. Partly the COMPOUND signal (AORC rain + USGS discharge ponding in flats/valleys — real flooding MOTF can't contain) and partly numerical thin-film/DEM-pit artifacts. Fix: connectivity filter (keep flooding connected to coast/channels) + depth threshold.

## Other next steps
1. Decide SnapWave params on the FIXED bathymetry (Tim's block may be fine once cliffs are gone — the earlier param result was confounded by the cliffs).
2. Residual Asbury/Long-Branch hm0 spikes (real steep bathy) — light smoothing or accept+mask.
3. X2 seaward extension — fixes BOTH the offshore zs ring AND the Sandy Hook gauge noise, plus paper-quality offshore wave transformation.
4. Deferred mask/boundary cleanups — see [[project-mask-boundary-cleanups]].

Related: [[project-snapwave-root-cause]], [[project-noaa-boundary]], [[project-coned-upgrade]], [[project-compound-roadmap]], [[project-quadtree-session]].
