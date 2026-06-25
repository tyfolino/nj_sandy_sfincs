---
name: project-snapwave-root-cause
description: "NJ Sandy SnapWave+quadtree crash diagnosis — root cause identified 2026-05-26 after a full session of trial-and-error. Boundary input points placed at raw ERA5 grid coords were OUTSIDE the model mesh; SnapWave had no bathymetry there, set depth=0, clamped to 5m, generated runaway waves. Explains ALL prior failures."
metadata: 
  node_type: memory
  type: project
  originSessionId: 37cfeedd-f523-4884-8b31-5c4e27f59a4a
---

# SnapWave crash root cause — 2026-05-26

## What we finally found

`hydromt_sfincs.snapwave_boundary_conditions.create_from_grid()` placed our 11 boundary input points at **raw ERA5 grid coordinates**, which sit **25–130 km outside our model mesh**. SnapWave can't compute a depth at points outside the mesh — it defaults to **0**, then clamps to **5 m** for "stability", but then `Hm0ig` at the boundary blows up (small depth → large IG wave heights via Herbers shoaling). That runaway wave energy propagates into SFINCS and destabilizes the momentum solver.

**This explains every single one of the ~10 failed configurations from this session and yesterday's session.** It was never:
- A quadtree+SnapWave fundamental incompatibility
- A subgrid interaction (we tested with/without; both crashed)
- An IG wave issue (igwaves=0 crashed identically)
- A wavebnd-depth-threshold problem (z≤−8, z≤−15 both crashed)
- A wavemaker presence/absence issue (both crashed)
- A `snapwave_waveforces_factor` issue (factor=0 crashed identically)
- Issue [#184](https://github.com/Deltares/SFINCS/issues/184) (depth extrapolation) — that's a different bug; ours fires before any extrapolation happens
- A v2.3.x regression (v2.1.1 Dollerup can't read our sfincs.nc due to schema change, so we can't even test it without a parallel hydromt env)

**The "smoking gun" log line in our final test (Option B', test-fixture-style config):**

```
ERROR SnapWave - depth at boundary input point 625195, 4595350 dropped below 5 m: 0.00000000
Depth set back to 5 meters for stability, simulation will continue.
```

Repeated for all 11 input points (which are all outside model bbox `x∈[580k, 598k], y∈[4445k, 4484k]`).

## How we cornered it

Final diagnostic test (Option B'): stripped our model to match the hydromt_sfincs test fixture (`tests/data/sfincs_test_quadtree/`):
- Removed `snapwave_mask` variable from sfincs.nc
- Converted `snapwave.nc` → ASCII `snapwave.{bnd,bhs,btp,bwd,bds}`
- Removed `snapwave_dtheta`, `snapwave_waveforces_factor`, `netsnapwavefile`, `wvmfile`
- Restored subgrid

Result: SFINCS ran cleanly for the full 72-hour Sandy hindcast (avg dt 1.196 s, 9 min wall) — **but** `Number of active SnapWave nodes: 0` in the log, hm0 NaN everywhere. Vacuous success: SnapWave initialized with 0 cells because all input points were outside the mesh. The boundary-depth ERROR lines made the cause obvious.

## Plan to pick up

Two valid fixes, very different effort/reward.

### X1 (immediate — diagnostic test, ~30 min)
Keep our small mesh; relocate the 11 input points to **inside the SFINCS active boundary** (along the offshore `mask==2` waterlevel-boundary cells at ~5–10 m depth). Interpolate the ERA5 wave time series to each new point (nearest-neighbor on the ERA5 grid). Restore `snapwave_mask = SFINCS mask`. Rewrite `snapwave.{bnd,bhs,btp,bwd,bds}` ASCII files. Run.
- **Confirms the diagnosis** — if hm0 develops and SFINCS stays stable, we're 100% certain.
- Wave physics: waves get "injected" at SFINCS's offshore boundary in intermediate water. No offshore shoaling/refraction. Adequate for a quick demo, not paper-quality.

### X2 (proper architecture — ~1-3 hours rebuild, paper quality)
**Extend the quadtree mesh seaward to encompass the ERA5 input points**, as Leijnse does in the Carolinas/Florence paper. Add 3 more refinement levels eastward: 400 m → 800 m → 1600 m, reaching ~100 km offshore where the ERA5 nodes live. The SnapWave active mask spans the full extended mesh; the SFINCS active mask stays at z≥−10 (= the original coastal subset). Place input points at ERA5 grid coords (now inside the extended mesh). Optionally add a wavemaker line at ~−5 m for IG forcing.

This matches Leijnse exactly: waves enter at deep water on coarse cells, transform/shoal/refract across the SnapWave-only offshore extension, then drive SFINCS at the coastal handoff. Modest compute cost (~20–30k extra coarse offshore cells vs current 339k).

### Plan
1. Do X1 first as the diagnostic confirmation (next session).
2. Commit to X2 once X1 validates the hypothesis.
3. Parallel: user emailed Tim Leijnse (Tim.Leijnse@deltares.nl) asking for Carolinas model files / build scripts; if he replies with anything useful, fold that in.
4. **Also explicitly set `dtwave = 1800` in sfincs.inp** for both X1 and X2 — we currently use the SFINCS default 3600 s (1 hour), but Leijnse uses 1800 s (30 min). Cheap one-liner, matches paper.

## X1 EXECUTED 2026-05-26 — full success

Reproducible by `/tmp/x1_relocate_inputs.py` (placed 7 input points along the offshore SFINCS waterlevel boundary, depths −9.6 to −10.0 m, nearest-ERA5-node interpolation, restored snapwave_mask = SFINCS mask, dtwave=1800, ASCII forcing files).

**Run characteristics (vs prior crashes):**
- Avg dt: **1.195 s** (matches no-SnapWave baseline; was 0.019 s when crashing)
- Wall time: **632 s for full 3-day Sandy** (vs 60–80 s before crash)
- SnapWave compute: **31.6%** (vs ~1% when crashing, 8% in B' vacuous success)
- All 73 dtmapout timesteps written
- Mean hm0 grows realistically with storm: 1.09 → peak 2.51 → decay 1.38 m
- IG: peak hm0ig 3.58 m max anywhere, ~0.85–2.93 m mean during storm

**Sandy Hook NOAA 8531680 validation (X1 vs Stockdon baseline):**
| Metric | Stockdon (project-stockdon-setup) | **X1 SnapWave** |
|---|---|---|
| Bias at gauge | **+0.39 m** | **+0.02 m** |
| Modeled peak | overshoots ~3.2 m | 2.64 m |
| Observed peak | 2.81 m | 2.81 m |
| RMSE | n/a | 0.285 m |
| MAE | n/a | 0.210 m |
| hm0 at gauge peak | n/a | 1.34 m |
| hm0ig at gauge peak | n/a | 0.31 m |

**Headline: 95 % bias reduction at Sandy Hook**, modeled now slightly *under* (–0.17 m) at peak instead of overshooting. Real SnapWave wave setup beats the parametric Stockdon proxy decisively.

## Known issues still in the X1 run

1. **Isolated hm0 spike cells (INITIAL DIAGNOSIS 2026-05-26 — NEEDS DEEPER INVESTIGATION).** 85 of 339,291 cells (0.03%) report max hm0 > 10 m over the run; 1 cell (cell 241571 @ zb=−4 m, southern Sandy Hook) hits 425 km. **All spike cells are level-4 (25 m) surf-zone cells, none at input boundary points, mostly mask=1 interior.** Two geographic clusters: (583–584k, 4479–4481k UTM) at southern Sandy Hook, and (585–586k, 4454–4458k) at Asbury Park / Long Branch. Working hypothesis: SnapWave's stationary wave-energy balance produces numerical artifacts at the 50 m ↔ 25 m refinement interface under steep surf-zone depth gradients. SFINCS's `fwmax = 0.8·hwet^1.5/15` shallow-water limiter caps the actual momentum injection so the solver stays stable; mean hm0 across the surf zone is realistic (1–3 m).

    **Open questions for follow-up investigation:**
    - Is the 50→25m refinement interface actually the trigger? Cross-reference spike cell locations against refinement-level boundaries from the refinement polygons.
    - Are spike cells correlated with specific bathymetric features (steep slopes, isolated depression cells, abrupt zb jumps to neighbours)?
    - Does the wave-height blow-up coincide with wave breaking (Hm0 / depth ratio approaching gammax)?
    - Do `snapwave_alpha` / `snapwave_gamma` / `snapwave_dtheta` knob sweeps change the spike count/magnitude?
    - **Critical for paper:** do the spikes bias derived wave-setup maps or maximum-water-depth maps? Compare mean/median surf-zone wave heights with and without spike cells masked.
    - Possible workarounds in the meantime: filter output cells with hm0 > some-threshold for plotting; OR wait for Galibier-era fixes (PR #302's wave-force limiter rework).
2. **High-frequency noise on modeled water level at Sandy Hook**, even pre-storm when hm0 at the gauge ≈ 0. Inflates RMSE. Could be wind/pressure seiche, dynamic-IG artifact at wavemakers, numerical leakage from the spike cells, or output sub-sampling at 10-min `dthisout`. Worth diagnosing.
3. **All 7 input points map to the same ERA5 node** (-74.00, 40.00). No spatial variability in the wave forcing along the boundary — the ERA5 0.5° grid is too coarse for our 40 km of coastline. Acceptable for X1; X2 should pick distinct ERA5 nodes per alongshore position OR weight-interpolate across multiple nodes.
4. **No proper offshore wave transformation** — waves get "injected" at SFINCS's z≈−10 m edge with no shoaling/refraction across the shelf. X2 (Leijnse-style seaward extension) addresses this for paper quality.

## Cleanup / unwinding for X2 build

When we move to X2, revert these X1-and-earlier hacks. **NOTE (2026-06-25):** edits now go DIRECTLY in the hand-maintained notebook `notebooks/sfincs-nj-sandy.ipynb` — `scripts/build_quadtree_notebook.py` is HISTORICAL (do not re-run it; see [[project-housekeeping-2026-06-25]]). Verify each hack's current state in the notebook before reverting (X1 was already ported in, so some may be gone).
- Restore the original z<=-8 wavebnd workaround removal (the "manual flip" cells are now known to attack the wrong problem)
- Remove the `snapwave_waveforces_factor = 0.0` line if still lingering (harmless but stale)
- The `data/wavemakers/wavemaker_line.geojson` is reusable for X2 to force IG dynamically
- Keep `dtwave = 1800` in sfincs.inp

## Architectural differences vs Leijnse (for the X2 build)

Catalogued from the Coastal Engineering 199 (2025) 104726 paper:

| Dimension | Leijnse Carolinas | Us NJ Sandy |
|---|---|---|
| SFINCS version | v2.1.1 Dollerup (Sept 2024) | v2.3.3 mt_Faber (April 2025 build, **same binary** as v2.2.0 col d'Eze and v2.3.0–2 — Docker just retags) |
| SnapWave seaward extent | 1600 m cells at ERA5 input points (~100 km offshore), refines 7 levels (1600→800→400→200→100→50→25) | Currently stops at SFINCS mesh edge |
| Subgrid tables | None ("not needed — high-res grid resolves bathymetry directly") | Yes (and removing them did not change the crash) |
| Wavemakers | At ~−5 m water depth alongshore (forces IG as long-crested dynamic waves) | Built one but no longer needed for current crash |
| dtwave (SnapWave update interval) | 1800 s (30 min) | Default 3600 s — match Leijnse's 1800 s |
| IG forcing path | SnapWave computes IG; forced into SFINCS at wavemakers as dynamic long-crested waves | Tried continuous coupling, off, etc. |
| Active SFINCS cells | 5,000,000 | 237,000 |
| Active SnapWave cells | 1,400,000 | matches SFINCS active (was wider) |

## Notes / loose ends

- **Docker tags are not unique binaries.** `latest`, `sfincs-v2.3.3`, `sfincs-v2.3.2`, `sfincs-v2.3.1`, `sfincs-v2.3.0-mt-Faber-Release`, `sfincs-v2.2.0-col-dEze-Release` all point at the **same April 2025 build** (`$Date: 2025-04-14`). Only `sfincs-v2.1.1-Dollerup-Release` is a genuinely older binary, and it segfaults on our sfincs.nc because the quadtree netCDF schema changed between v2.1.1 and v2.3.x.
- **The hydromt_sfincs test fixture path** (`/home/zagreus/hydromt_sfincs_examples/tests/data/sfincs_test_quadtree/`) is the only working SnapWave+quadtree example available locally. Its config: no snapwave_mask variable, ASCII boundary files, no IG, no dtheta, no use_nearest, no wavemaker, 2 boundary points at coords inside the SFINCS waterlevel boundary. Useful reference for the X1 setup.
- **PR #302 ("All snapwave changes in one")** — the Galibier-milestone meta-PR with `snapwave_waveforces_factor`, `snapwave_fw_ratio`, etc. — adds nice tuning knobs but does NOT address our root cause, so we don't need to wait for Galibier.
- **Memory `project_quadtree_session` from 2026-05-25 is partially superseded** by today's findings. Specifically, yesterday's diagnosis ("SnapWave forcing at refinement boundaries destabilizes momentum solver") was wrong — the destabilizer was upstream of any wave forcing, in the boundary input point depth lookup.
- **The wavebnd "manual flip" workaround** in `scripts/build_quadtree_notebook.py` was attacking the wrong problem and can be reverted as part of the X1/X2 cleanup.
- **Wavemaker geometry** (`data/wavemakers/wavemaker_line.geojson`, `scripts/build_wavemaker_line.py`) is reusable as-is for X2 — just need to wire it back in.

Related: [[project-quadtree-session]], [[project-snapwave-plan]], [[project-compound-roadmap]], [[project-stockdon-setup]].
