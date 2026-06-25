---
name: project-quadtree-session
description: NJ Sandy Phase 3 quadtree + SnapWave build — session of 2026-05-25. Quadtree model fully built and running without SnapWave; SnapWave still blows up the SFINCS solver. Multiple upstream hydromt_sfincs bugs discovered + locally patched.
metadata: 
  node_type: memory
  type: project
  originSessionId: f41a60f2-4318-4cff-be80-e8c4cdd68f07
---

# Phase 3 quadtree session — 2026-05-25

Long session. Built the Phase 3 quadtree model end-to-end. SFINCS runs **cleanly without SnapWave**; SnapWave still destabilizes the momentum solver even with all known workarounds. Stopped for the night with the no-SnapWave run as a usable Phase 3a deliverable.

## What got built and works

- **Refinement-polygons recipe** in [scripts/build_quadtree_refinement.py](file:///home/zagreus/nj_sandy_sfincs/scripts/build_quadtree_refinement.py) → `data/quadtree/refinement_polygons.geojson`. Three rows, all in EPSG:32618: `shelf_bay` (level 1, no z-gate, ±1e9 sentinels), `coastal_corridor` (level 2, −20≤z≤+30, east edge shrunk 3 km), `surf_dune` (level 3, **−8≤z≤+3** — was +8 on first attempt, gave 397k cells with L4 at 262k; tightened to +3 to drop the inland coastal plain, yielded 339k total, L4 at 185k).
- **Notebook generator** at [scripts/build_quadtree_notebook.py](file:///home/zagreus/nj_sandy_sfincs/scripts/build_quadtree_notebook.py). Originally rewrote the regular-grid notebook (now `notebooks/archive/sfincs-asbury-sandy.ipynb`) into the quadtree notebook (now `notebooks/sfincs-nj-sandy.ipynb`). **HISTORICAL as of 2026-06-25** — the canonical notebook is hand-maintained now, so re-running the generator would clobber those edits (its docstring + SRC/DST paths were updated to flag this). It baked in: SnapWave-mask flip, ds=30° fill, ERA5 offshore-only filter, quadtree_infiltration call, sfincs.inp post-write strip of orphan infiltration keys.
- **`model_quadtree/` on disk** has a complete Phase 2 run from the no-SnapWave attempt: 339,291 cells (46 @ 200m + 22k @ 100m + 132k @ 50m + 185k @ 25m), 237,488 active SFINCS cells, full subgrid tables, all forcing files written, sfincs.inp valid. The no-SnapWave Docker run completed in 7 minutes with avg dt=1.196 s.

## Local hydromt_sfincs patches (load-bearing, applied directly to source)

All in `/home/zagreus/hydromt_sfincs_examples/hydromt_sfincs/`. These are NOT in pip — they're edits to the working source tree. Document for reproducibility / for when filing upstream PRs.

1. **`components/quadtree/quadtree_mixin.py`** — `compute_quadtree` padding for degenerate chunks. If a chunk has all cells sharing one m- or n-index (common at refinement level 0 once a polygon covers the whole region), `make_regular_grid` produces a 1-wide template and `merge_multi_dataarrays` chokes on `da_like.raster.res`. Patch pads `mmax-mmin>=2` and `nmax-nmin>=2`. Searched by comment "NJ patch: ensure mmax-mmin>=2".

2. **`components/quadtree/subgrid_quadtree_builder.py`** + **`components/quadtree/quadtree_subgrid.py`** — per-level cache evict in subgrid build. Without it, the hydromt data_catalog accumulates all level reads (USACE 1 m + CUDEM + NJ DEM + GEBCO at level-3 sampling = many GB) across the 4 level iterations and we go into swap by L3. Patch: wrapper passes `data_catalog=self.model.data_catalog`; builder accepts kwarg; at start of each `for ilev in range(...)` iteration (except first), null `_data` on every catalog source. Searched by comment "NJ patch: evict the hydromt data_catalog cache". Both files modified.

## Three upstream hydromt_sfincs bugs found (worth filing)

In priority order:

1. **`quadtree_mask.create_boundary(btype="waves", zmax=…)` silently returns 0 cells when called first on a fresh snapwave_mask.** Likely cause: numpy-vs-xugrid array alignment in the `np.logical_and(bounds0_numpy, uda_dep <= zmax)` filter at [quadtree_mask.py:587–594](file:///home/zagreus/hydromt_sfincs_examples/hydromt_sfincs/components/quadtree/quadtree_mask.py#L587-L594). The function reports success but the mask is unchanged. We worked around by manually flipping `(snapwave_mask == 3) & (z <= -8)` cells to mask==2 after the broken call. **Silent correctness bug — prioritize filing.**

2. **`quadtree_infiltration.create_cn` sets `infiltration_file = infiltration.nc` in sfincs.inp but its `write()` method is `pass`.** The file is never written; SFINCS aborts at startup with "Infiltration netcdf file not found". Either the write() needs to write the file OR the create_*() methods should defer the config update to user. Worked around by stripping the orphan inp keys post-write.

3. **`subgrid.create` per-block overhead × `nrmax=200` blow-up.** `nrcb = nrmax // nr_subgrid_pixels`; with `nrmax=200, refi=8` you get blocks of 25×25 cells, and the inner per-block Python loop scanning all level cells (`for ic in range(nr_cells_in_level)`) becomes O(n²) — at L3 alone, 132k cells × 384 blocks = 51M iterations. Combined with one `merge_multi_dataarrays` call per block, this turned a 60-second regular-grid subgrid build into 2+ hours on quadtree. **`nrmax=2000`** (default) gives one block per level for our domain → finishes in 5 min. Performance bug, but worth filing as a docstring fix at minimum so users don't think "smaller nrmax = less memory" the way I did.

## The SnapWave wall (UNRESOLVED — tomorrow's work)

**SnapWave + IG waves on quadtree blows up the SFINCS momentum solver.** Two distinct failure modes observed; the first is fixed, the second isn't.

### Fixed: ERA5 input points over land
First attempt produced 4 "ERROR SnapWave - depth at boundary input point … dropped below 5 m: 0.1" lines at UTM-X ~500000 m (~80 km west of our model's eastern edge). ERA5 0.5° grid (~55 km spacing) had nodes over inland NJ; `create_from_grid`'s 100 km buffer pulled them in; SnapWave then reads depth ~0 m at those points (they're outside the SFINCS mesh) and the IG-bound Hm0ig explodes. **Fix:** prefilter ERA5 to nodes east of the model bbox's east edge — baked into the notebook generator.

### Unfixed: SnapWave-induced velocities still > 1000 m/s
Second attempt (offshore filter applied, zero depth warnings) STILL blew up. SFINCS average dt collapsed from 1.2 s (no-SnapWave) to **0.019 s** (with SnapWave), drove dt below the 0.01 s floor, then "Current velocity exceeded uvmax 1000.0 m/s". No diagnostic depth warnings this time — the radiation-stress gradient itself is the killer. Likely cause: the wave-induced momentum forcing at the 50 m ↔ 25 m refinement boundary in the surf zone is too steep for SFINCS's interface scheme. SnapWave's own time-in-solver is only 2.1% — SnapWave isn't slow, its OUTPUT is destabilizing SFINCS.

### Tomorrow — three knobs to try, in order
1. **`snapwave_igwaves=0`** (keep incident, drop IG). IG is the more aggressive forcing — the 1 cell that adds it produces the largest pressure gradients. Edit sfincs.inp directly between write and Docker run. If incident-only works, we have a degraded but functional SnapWave run + isolated to the IG band.
2. **Move SnapWave wave boundary deeper.** Currently we flipped neumann→wavebnd cells with `z <= -8`. Try `z <= -15` so the boundary cells are in deeper water where wave forcing is less abruptly applied to the SFINCS solver. Risk: may leave us with ~0 wavebnd cells given our shallow shelf — verify count first.
3. **Tune `snapwave_dtheta`.** Default we set was 10°. Wider (15° or 20°) smooths directional discretization; may reduce gradient sharpness.

If all three fail, the fundamental quadtree-SnapWave interaction needs more investigation — possibly an upstream bug or a feature that requires non-2:1 refinement transitions.

## Other loose ends to clean up tomorrow

1. **Git push is broken** because commit `8261af5` accidentally committed `model_quadtree/subgrid/dep_subgrid_lev2.tif` (**107 MB**, over GitHub's 100 MB hard limit) + 5 other large subgrid TIFs. **Root cause:** `.gitignore` had `model/` but not `model_quadtree/`. **Fix:** add `model_quadtree/` to .gitignore, then either `git reset --soft HEAD~1` + restage + new commit (preferred, no amend), or `git rm --cached -r model_quadtree/` + `git commit --amend`. Either way the bad blob lives in the 8261af5 history and must be removed before push will succeed. Hasn't been pushed yet so rewriting is safe.

2. **Validation cells need running on the no-SnapWave quadtree run** to quote a quadtree-vs-regular ΔCSI. The Phase 3 notebook's validation cells (Sandy Hook gauge ts, HWMs, MOTF CSI, etc.) point at `../model_quadtree` already — should "just work" once a kernel is restarted and the validation section is run. Headline numbers to compare against [project_manning_nj](project_manning_nj.md): regular-grid + NJ Manning is CSI 0.49.

3. **`buffer_cells=0` in elevation** was a workaround for a Qhull collinear-points crash in `merge_dataarrays.interpolate_na`. Means hard seams between DEM layers (mostly cosmetic for us since seams are in deep water). The Qhull failure could itself be a hydromt bug worth filing, but lower priority than the three above.

## Configuration snapshot (so next session can reproduce)

- Grid: base 200 m rotated UTM 18N, refined to 100 / 50 / 25 m via the 3-polygon recipe
- Refinement: L1 full region, L2 east-shrunk by 3 km gated −20≤z≤+30, L3 full region gated **−8≤z≤+3**
- Subgrid: `nr_subgrid_pixels=8`, `nrmax=2000` (DO NOT lower for subgrid)
- Roughness: `nrmax=200` (the smaller nrmax is fine for roughness — uses compute_quadtree, not the subgrid builder)
- Elevation: `buffer_cells=0`, `nrmax=200`, 4-tier merge unchanged from regular grid
- SnapWave mask: `create_active(zmin=-50, zmax=10)`; neumann everywhere; **manual flip of `(mask==3) & (z<=-8)` → mask==2** (767 wavebnd cells)
- SnapWave BC: ERA5 wave field with `ds=30°` constant fill, prefiltered to nodes east of bbox east edge, `buffer=100e3` — 29 boundary points (offshore-filtered to ~25 or fewer)
- SFINCS config: `snapwave=1`, `snapwave_igwaves=1`, `snapwave_dtheta=10`, `snapwave_use_nearest=1`, `coriolis=1`, `latitude=40.32` (with re-injection workaround)
- Docker: `deltares/sfincs-cpu:latest` (= v2.3.3 mt. Faber+, includes SnapWave_IG branch from 2025-04-14)

## Sanity-check numbers from today's runs

- No-SnapWave run: 7 min wall, avg dt 1.196 s, 70% time in momentum, all processes "yes" except SnapWave + Infiltration
- SnapWave + IG run: 79 s wall before crash, avg dt 0.019 s, "Time in SnapWave: 2.1%" (SnapWave solver itself is cheap; SFINCS solver is what dies under its forcing)
- Subgrid output: z_zmin ∈ [−29.3, +72.8], z_zmax ∈ [−20, +83.6], uv_havg max 26.5 m, uv_navg ∈ [0.020, 0.180] — all plausible

Related: [project-stockdon-setup](project_stockdon_setup.md), [project-snapwave-plan](project_snapwave_plan.md), [project-compound-roadmap](project_compound_roadmap.md), [project-manning-nj](project_manning_nj.md), [project-coned-upgrade](project_coned_upgrade.md), [project-nj-sandy](project_nj_sandy.md).
