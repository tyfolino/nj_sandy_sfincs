---
name: project-stockdon-setup
description: "NJ Sandy SFINCS — Stockdon 2006 parametric wave setup added to boundary as a stand-in for SnapWave. Run done, gap closed, uncommitted as of 2026-05-20."
metadata: 
  node_type: memory
  type: project
  originSessionId: d42c392d-6e72-4484-805c-d5b00cb0ae62
---

SnapWave turned out NOT to be supported on regular grids in `hydromt_sfincs` v2.0.0rc2 (would need a quadtree rebuild), so the [[project-snapwave-plan]] is superseded. Instead we apply **Stockdon et al. (2006)** parametric wave setup directly to the boundary water levels, à la Parker et al. (2023), as a hypothesis test for the ~0.77 m surge gap.

## UPDATE 2026-05-22 — uniform buoy REPLACED by per-support-point ERA5 (Phase 2)

Cell 1b (`bf111cf3`) rewritten: instead of one uniform NDBC-buoy setup at every boundary point, it now samples the nearest valid offshore node of the **ERA5 wave field** (`era5_waves_nj`) to EACH of the **2 water-level support points** (Battery N 40.70, Atlantic City S 39.36) → per-point Stockdon η → alongshore gradient. β_f stays 0.05. Dry-run nodes: **N → setup 0.87 m, S → 0.78 m** (real gradient; north slightly higher because Sandy's strongest offshore waves were in the apex). Buoy `ndbc_sandy_44025` no longer used by 1b. See [[project-compound-roadmap]] Phase 2.

- **Bug found+fixed during wiring:** the nearest-node distance array broadcast to dims `(x,y)` while the valid mask was `(y,x)`, so `unravel_index` grabbed the wrong node (AC pulled a node up at 40.5 N). Fix: flatten valid nodes via `np.where(vmask)` + meshgrid and `np.argmin` on 1-D arrays. Replicated identically in the new Phase-3 subtract-setup diagnostic cell.
- **Expectation (NOT yet re-run):** ERA5 only trims the *northern* setup ~1.0→0.87, so Sandy Hook over-prediction should ease ~+0.39 → ~+0.26 m — better, not closed. Sheltered-bay over-prediction is cross-shore sheltering → only SnapWave (Phase 3) truly fixes it. Open-coast is where ERA5 should help most.
- New permanent **subtract-setup diagnostic** added to Phase 3 (markdown `cf38cd9d` + code `a56fc5b0`, right after Sandy Hook validation `2a04c49f`): overlays modeled, modeled−setup (≈ no-wave baseline), and observed. Confirmed the +0.39 m gauge bias is the wave setup, NOT boundary/tide (green tracks obs; mean resid +0.39 with setup → −0.14 without).
- **Datum audit 2026-05-22 (user asked):** whole Sandy-Hook chain is consistently NAVD88 (NOAA gauge forcing+validation via API `datum=NAVD`; USACE2010 + CUDEM topobathy; HWMs `vdatum_id=2`; canonical 3.86 m). So the bias is NOT a datum artifact. `nj_10ft_dem` was mislabeled `m+MSL` in `data/data_catalog.yml` — **verified NAVD88** empirically (median nj−CUDEM = −0.02 m over 6530 land pts) and **relabeled to m+NAVD88**. hydromt doesn't auto-shift on the `unit` string, so the mislabel never biased the model. GEBCO `m+MSL` is the deep offshore tail — immaterial.

## Original implementation (superseded by ERA5 above; notebook cell "1b", cells 25-26)

η_setup(t) = 0.35 · β_f · √(H₀(t)·L₀(t)), L₀ = g·Tp²/2π. H₀, Tp from NDBC buoy 44025 (catalog `ndbc_sandy_44025`). Interpolated onto boundary time axis and added **uniformly alongshore** to `sf.water_level.data["bzs"]`.

- **β_f = 0.05** — tuned DOWN from the open-coast foreshore-slope median 0.079 (computed from 2010 USACE 1 m DEM, ~980 transects between −0.5 and +2 m NAVD88, IQR 0.068–0.088). Reason: Sandy Hook gauge sits inside the bay where real setup << open beach; 0.079 overshot (~+0.5 m calm bias, ~+0.6 m peak overshoot). β_f is THE knob to tune.

## Results (saved run, β_f=0.05) — hypothesis confirmed

- Peak Stockdon setup 0.97 m; boundary bzs peak 3.42 → 4.18 m.
- Sandy Hook modeled peak (full run) 3.09 → **3.93 m** (~3.86 m observed-true-peak estimate → basically closed).
- Upper-dune cells wet 533 → **3175** of 11971 (4%→26%); beach/dune 63%→89%; inland-low 0 → 207 wet.
- **Validation-window caveat:** gauge failed 10-29 23:00, so the validation cell compares to the PRE-FAILURE observed peak (2.81 m). In that comparable window modeled is 3.38 m = **+0.57 m over** observed pre-failure. So depending on target (pre-failure 2.81 vs true-peak ~3.86) β_f=0.05 is either slightly hot or spot-on. Open calibration question.
- Watch the nearshore/surf-zone grid maxes (~8.17 m) — possible runup spikes on steep cells, sanity-check before trusting.

## Status / next steps

- **Uncommitted** as of 2026-05-20 (+218/−112 in the notebook). Should commit to capture the working result.
- Caveats (in the markdown cell): Stockdon predicts setup at the beach face, so applying uniformly offshore over-states the boundary level, under-states alongshore variation, and misses runup (the real dune-overtopping driver). Honest "real fix" remains SnapWave (quadtree) or WaveWatch III.

Related: [[project-snapwave-plan]], [[project-noaa-boundary]], [[project-coned-upgrade]], [[project-nj-sandy]], [[reference-notebook-tooling]].
