---
name: project-snapwave-plan
description: NJ Sandy SFINCS — concrete plan for wiring SnapWave to close the ~0.77 m surge gap and overtop dunes. Data and catalog entries ready; wiring not done.
metadata: 
  node_type: memory
  type: project
  originSessionId: 251296cf-08f6-4e9e-b257-099a9e81fd1b
---

Action plan for adding SnapWave to the Sandy hindcast. Surge baseline (Coriolis on, NOAA-gauge BCs, no waves) is stuck ~0.77 m short of observed at Sandy Hook and only ~4% of upper-dune cells overtop — almost certainly the missing wave setup/runup. Buoy data + catalog entry are ready; wiring into the notebook is the remaining task.

## Current baseline numbers (the gap waves needs to close)

- **Sandy Hook gauge** — modeled 3.09 m vs observed ~3.86 m NAVD88 (gauge failed 10-29 23:00). The Battery anchors the boundary at 3.42 m; gauge sits *below* its own boundary forcing, so there's both a boundary-deficit component and a missing-physics (wave setup) component.
- **Zone stats** — offshore bnd 3.17 m, surf zone p95 4.29 / max 4.87, beach/dune n_wet=8359 of 13273 (~63%), upper dune (3-6m) n_wet=533 of 11971 (~4%), inland low (6-15m) **bone dry**.
- **Obs points** — only `shark_river_inlet` (zb 3.42, peak 4.25, freeboard −0.83) and `asbury_park_pier` (zb 2.40, peak 2.85, freeboard −0.45) overtop. The higher land obs points (long_branch_beach 3.77, deal_lake_interior 0.23 - but isolated -, bradley_beach 4.56) stay dry.

Expected with SnapWave: 0.5–1 m bump from wave setup, more dune overtopping, some inland flooding.

## Data already in place

- `data/waves/ndbc_sandy_44025.nc` — NDBC buoy 44025 GeoDataset with `hs`, `tp`, `wd`, `ds` (1 station, 96 hourly steps). **hs peak 9.65 m, tp peak 14.8 s, direction sweeps 41°→198° as Sandy passed.**
- **`ds` is a constant 30°** — NDBC stdmet has no directional-spreading field. This is the first knob to tune if SnapWave output looks off.
- Catalog entry: `ndbc_sandy_44025` (GeoDataset, `data/waves/ndbc_sandy_44025.nc`).
- Download: [scripts/download_ndbc_sandy_waves.py](../../../scripts/download_ndbc_sandy_waves.py) (atomic write, handles NDBC gzip quirk).
- Buoy is at (40.251, −73.164) — ~70 km east of the domain → SnapWave's default `buffer=25000` won't reach. **Use `buffer=100000`.**

## Wiring steps

**Phase 1 additions** (geometry — must re-run Phase 1):
- After `subgrid.create` and before the Phase-1 write (`22ff5fc2`): create SnapWave's boundary mask. The component is `sf.snapwave_mask` (sister of `sf.mask`); needs investigation — likely `sf.snapwave_mask.create_boundary(...)` defines where the SnapWave BC is applied. SFINCS SnapWave uses its own boundary mask separate from the hydrodynamic mask. The `snapwave_bndfile` keyword in the inp points at it (see `components/forcing/snapwave_boundary_conditions.py`).
- Phase-1 write is unchanged — `sf.write()` then `del sf; gc.collect()`.

**Phase 2 additions** (forcing — fast iteration):
- In the config cell (`b899e871`): add `"snapwave": 1` to the `config.update` dict (probably alongside the existing `coriolis=1`, `latitude=40.32`). SnapWave config knobs (defaults probably fine to start; live in `components/config/config_variables.py`): `snapwave_dt`, `snapwave_use_nearest`, `snapwave_igwaves`, `snapwave_dtheta` (10°), `snapwave_nrsweeps`, `snapwave_crit`, `snapwave_hmin`.
- After wind/pressure cell (`51279b38`) and before write (`91087aae`): add `sf.snapwave_boundary.create(geodataset="ndbc_sandy_44025", buffer=100000, merge=False)`. **`merge=False` is required for the same reason it was for `water_level.create` in `r+` mode** — the merge default would keep stale forcing.

**Open question / hazard:** the SnapWave boundary mask creation API (`sf.snapwave_mask.create_boundary` or similar). Check the hydromt-sfincs source at `components/grid/snapwave_mask.py` (or similar) for the exact method signature before wiring. If hydromt doesn't have a clean API for this, may need to manually create a `snapwave.msk` file or set the geometry directly.

## Validation after wiring

In order of "did this actually do anything":
1. SFINCS run-log Processes block shows **`SnapWave : yes`** (analogous to how we verified Coriolis).
2. The `validation` cell (`2a04c49f`) — modeled Sandy Hook peak should rise toward 3.86 m; gap should shrink from 0.77 m to ~0–0.3 m.
3. The `zone stats` cell (`27e996fd`) — upper-dune n_wet should jump well above the current 533 of 11971; some inland-low cells should wet for the first time.
4. The peak table (`2589669d`) — the high-zb obs points (long_branch_beach 3.77, bradley_beach 4.56) might finally show non-zero freeboard.
5. Eyeball the hvplot flood map (`b93ee319`) for visibly more inland flooding.

If SnapWave is on but the gap doesn't close, suspect: directional spreading (`ds=30°` constant — try other values), boundary placement (the offshore boundary is at ~−10 m depth, very shallow for a wave BC), or fall back to a WaveWatch III hindcast (more spatially complete than the single buoy).

## Loose ends not in this plan

- `deal_lake_outlet` obs point at (−73.9987, 40.221) is actually Wesley Lake area, not Deal Lake's true outlet. Rename to `wesley_lake_outlet` or move when convenient. See [[project-noaa-boundary]] for the full Deal Lake diagnosis (3 compounding causes; outlet flume connectivity requires DEM burn-in or `sfincs.drn` and won't matter until total water level is also realistic).
- `latitude` hydromt-sfincs bug — `sf.write()` strips the `latitude` line from `sfincs.inp` even when set. **Workaround is in the write cell `91087aae`** — it re-injects `latitude = 40.32` after every write. Don't remove until upstream is fixed; without it, SFINCS silently disables Coriolis even with `coriolis = 1`.
- NLCD reclass table is still SFBD-tuned ([[project-nj-sandy]]).
- The `del sf; gc.collect()` at end of Phase 1 (cell `22ff5fc2`) is load-bearing for memory; restart kernel between phases if anything feels weird.

Related: [[project-noaa-boundary]], [[project-coned-upgrade]], [[project-nj-sandy]].
