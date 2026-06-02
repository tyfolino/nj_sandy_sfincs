---
name: project-noaa-boundary
description: NJ Sandy SFINCS — boundary forcing switched from GTSM-ERA5 to observed NOAA CO-OPS gauges (2026-05-13). Region expanded north to include Sandy Hook.
metadata: 
  node_type: memory
  type: project
  originSessionId: 251296cf-08f6-4e9e-b257-099a9e81fd1b
---

Boundary water-level forcing switched from GTSM-ERA5 to observed NOAA CO-OPS gauge data on 2026-05-13.

**Why:** GTSM-ERA5 underpredicted Sandy's peak at NJ latitudes by ~1 m (2.91 m at the closest GTSM station to Sandy Hook vs ~3.86 m observed). Two suspected drivers: (1) ERA5 surface stress is sampled too far offshore to drive near-shore wind setup, and (2) global tide-surge models miss the NY Bight resonance. With the underpredicted boundary, modeled surge couldn't even reach the dune toe at 5 of 6 obs points — adding wave physics on top would have been chasing the wrong problem.

**How to apply:**
- Catalog entry: `noaa_sandy_nj` (GeoDataset, 4 stations: 8518750 Battery, 8531680 Sandy Hook, 8534720 Atlantic City, 8536110 Cape May). GTSM entry was removed from the catalog entirely.
- Download script: [scripts/download_noaa_sandy_wl.py](../../../scripts/download_noaa_sandy_wl.py) — hits NOAA Tides & Currents API, writes `data/gtsm/noaa_sandy_nj.nc` (kept in the `gtsm/` folder for path-stability — rename later if it bothers).
- **Sandy Hook gauge (8531680) failed mid-storm** — record goes NaN after 2012-10-29 23:00 (48 of 96 hourly samples). It must NOT be a boundary forcing source: feeding the NaN tail into `water_level.create` collapses the northern boundary mid-storm (cell loses forcing → domain drains → modeled zs craters to zb). The Battery (8518750, ~5 km north, complete record, 3.42 m peak) anchors that latitude instead.
- Download script writes TWO files: `noaa_sandy_nj.nc` = forcing (3 complete stations: 8518750, 8534720, 8536110; catalog `noaa_sandy_nj` points here) and `noaa_sandy_validation.nc` = all 4 incl. partial Sandy Hook, for validation plots only. Stations carry a `role` key; script raises if a `role="forcing"` station has gaps. Writes are atomic (temp + os.replace) so a Jupyter kernel holding the file open via the data-catalog cache can't block or corrupt the write.
- **`water_level.create` gotcha — must pass `merge=False` in Phase 2.** Phase 2 opens the model `mode="r+"`, which loads existing bnd forcing from disk. `water_level.create` defaults to `merge=True`, which APPENDS the new stations to the stale forcing — and any old station not present in the new file (e.g. the excluded Sandy Hook) survives the dedup and persists. Then `sf.write()` logs "No changes detected; skipping write" and the model runs on the stale bnd file. Symptom: a fix to the forcing file has no effect, drop/NaN artifacts persist. `merge=False` replaces instead. Same trap likely applies to wind/pressure/other forcing `create` calls in `r+` mode.
- `water_level.create` uses `buffer=100000` (m) so Atlantic City (~88 km from the southern boundary) is included alongside The Battery — keeps the alongshore gradient. `buffer=50000` only reached The Battery → uniform boundary, over-predicts the south.
- Region expanded 2026-05-13 from Asbury Park box (40.15–40.32 N, –74.10 to –73.90 W) to Sandy Hook box. Initial expansion to (40.15–40.55, –74.15 to –73.85) **OOMed** the elevation step on the 24 GB WSL2 box. Tightened to **(40.15–40.50, –74.05 to –73.85)** = ~665 km² — keeps spit + Sandy Hook gauge, drops most of Sandy Hook Bay. CUDEM tops out at 40.45 — GEBCO fills the offshore tail above that.
- Sandy Hook gauge location added as obs point `sandy_hook_gauge` for direct validation against the (partial) observed record.
- **Real OOM cause (not the region size): the USACE 1 m raster was clipped to a stale oversized bbox** (–74.5,39.8,–73.9,40.5 → 78×67 km, ~20.7 GB float32 in memory). hydromt's elevation merge loads the *whole source raster*, so region/resolution changes don't help — the file extent does. Fixed 2026-05-13: re-clipped to `usace_nj_2010_topobathy_clip.tif` (~4 GB in memory, 109 MB on disk), catalog `usace_nj_2010` uri updated, `download_pre_sandy_topobathy.py` BBOX_WGS84 updated to region+0.01°. **If region.geojson changes, re-clip the USACE raster too.**
- `create_active(zmin)` lever for the offshore boundary: at `zmin=-20` (≡ anything ≤ –20 here; domain has no water deeper than ~–20 m) 100% of data cells go active, so the active mask is a clean rotated rectangle and `create_boundary` traces a straight offshore edge instead of the ragged –10 m isobath (which stranded ~39% of waterlevel-bnd cells in the interior). User still tuning the exact value — not yet committed to the notebook.

**Status (2026-05-14): NOAA boundary working.** Run with `merge=False, buffer=100000`: offshore boundary peak ~3.17 m, modeled Sandy Hook gauge ~3.09 m vs observed ~3.86 m — **~0.77 m short**, and only ~4% of upper-dune cells overtop. Validation cell added to the notebook (modeled vs observed at `sandy_hook_gauge`, using `noaa_sandy_validation.nc`).

**Next: waves (SnapWave) to close the ~0.77 m gap** — chosen over moving the boundary (no deep water in the domain to move into; observed gauges are already the best still-water level; the gap is the signature of missing wave setup, and wave runup is the actual dune-overtopping mechanism). Done: `scripts/download_ndbc_sandy_waves.py` (NDBC buoy 44025, hs peaks ~9.6 m), `data/waves/ndbc_sandy_44025.nc`, catalog entry `ndbc_sandy_44025`. SnapWave `ds` (directional spreading) is a constant 30° — NDBC stdmet has none. NOT yet done: wiring `sf.snapwave_boundary.create` + `snapwave=1` into the notebook. Fallback if NDBC insufficient: WaveWatch III hindcast.

**Coriolis:** enabled via `coriolis=1` + `latitude=40.32` in `config.update`. **Hydromt-sfincs (v2.0.0rc2 on disk) bug** — silently drops `latitude` from `sfincs.inp` even when set; confirmed `sf.config.get("latitude")` returns 40.32 in memory but the inp has no `latitude` line. Without it, SFINCS disables Coriolis (log says "Coriolis: no") even with `coriolis = 1` set. Workaround in the `sf.write()` cell patches the inp directly with a string replace after write — idempotent, removes once upstream fix lands. Expect Coriolis to be only a *minor* (cm-scale) correction at this domain size with observed-gauge BCs.

**Deal Lake won't flood — diagnosed 2026-05-14.** Three compounding causes: (1) the outlet flume isn't resolved at 50 m grid — model sees a continuous ~5 m oceanfront barrier with no ocean→lake hydraulic path; (2) ocean-side `zsmax` ~2.85 m is below that barrier anyway; (3) the `deal_lake_outlet`/`deal_lake_interior` obs points were on 4–6 m upland — **fixed** in `data/obs.geojson` to in-lake cells (−73.9987,40.2210 and −74.0099,40.2313, zb ≈ 0). Future structural fix for the connection: burn the outlet channel into the DEM, or add a SFINCS drainage structure (`sfincs.drn`). Won't flood until both the connection AND a realistic (wave-boosted) water level are in.

- NLCD reclass table still SFBD-tuned ([[project-nj-sandy]]).

Related: [[project-nj-sandy]], [[project-coned-upgrade]].
