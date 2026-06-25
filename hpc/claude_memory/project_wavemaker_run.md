---
name: project-wavemaker-run
description: "NJ Sandy quadtree — first wavemaker (X-WAVEMAKER) run, 2026-06-12. Wired SnapWave IG wavemaker line into the notebook; ran clean; improved back-bay extent (MOTF box CSI 0.33->0.40) but exposed a spatial DIPOLE — over-forces the eastern Sea Bright barrier (+0.7..+1.2 m at HWMs) while the western upper estuary (Oceanport) stays ~1 m short. Direction CONFIRMED landward (by causality). Remaining problems = forcing MAGNITUDE (east) + NARROWS CONVEYANCE (west), not orientation."
metadata: 
  node_type: memory
  type: project
  originSessionId: 08346867-a115-4cc6-ba9e-64fedfeb2b3a
---

# NJ Sandy quadtree — first wavemaker run (2026-06-12)

Enabled the SnapWave IG wavemaker (the top defensible fix for the back-bay under-flooding from [[project-validation-roadmap]]). On the CURRENT domain — wavemaker is interior (~10.6 km inside the seaward edge), does NOT need the X2 domain extension (that's a separate fix for the offshore *spectrum* boundary).

## Wiring (in `notebooks/sfincs-nj-sandy.ipynb`)
- **Cell 28/29**: replaced the disabled-print placeholder with `sf.wave_makers.create("../data/wavemakers/wavemaker_line.geojson", merge=False)` → writes `sfincs.wvm`. Line = −5 m NAVD88 contour from `scripts/build_wavemaker_line.py`, S→N, 8 verts, ~33.7 km, x583–587k / y4445–4478k.
- **Cell 39 (finalize)**: added `"wvmfile": "sfincs.wvm"` to the defensive key block (rc2 drops config keys on write, same class as the snapwave/latitude keys).
- Coexists with the X1 `snapwave.bnd` boundary (boundary feeds the spectrum into SnapWave; wavemaker injects the resulting IG+incident forcing into the SFINCS flow), exactly as in Tim Leijnse's `withwavemaker` reference notebook.

## Run (user ran it; I did NOT — Phase-1 rebuild RAM)
Clean: 767 s sim, avg dt 1.214 s (= prior clean run, no instability), `Time in wave maker 1.6%` (proves SFINCS picked up sfincs.wvm), SnapWave 27.7%. Output has `hm0`, `hm0ig`, `zsm` map fields + `point_hm0/hm0ig/tp/tpig` his fields.

## Results — genuine but MIXED (the headline)
- **Full-domain MOTF**: CSI 0.48→**0.53**, POD 0.54→**0.61**, FAR 0.17→**0.20** (hits 21.2 / miss 13.8 / FA 5.2 km²). Reproduced the notebook's score exactly from on-disk rasters (`floodmap_hmax_lev3.tif` + `dep_subgrid_lev3.tif` reconciled via reproject_match onto the 6.25 m de-rotated grid, MOTF `sandy_motf_extent.tif`, DEPTH_MIN 0.15, land = dep>0).
- **Estuary box** (x580500–587200, y4458000–4475000, scored land 23.5 km² — apples-to-apples vs the 2026-06-02 baseline): CSI **0.33→0.40**, hits 7.8→**9.4**, miss 13.9→**12.3**, FA 1.7→1.8. So **+1.6 km² miss→hit with ~0 new false alarms, IN the back-bay** = the gain is where the wavemaker was meant to act (not masked open-coast movement; open coast POD already ~0.89). But only ~12% of the 13.9 km² back-bay miss recovered → PARTIAL.
- **HWMs (the real arbiter — MOTF over-paints the estuary)**: all marks now wet (**0 dry**, was 3 dry). In-estuary q≤2 n=13: mean −0.38(incl dry)/+0.12(excl dry) → **+0.07**, but RMSE 0.42→**0.78** and within±0.5 m 80%→**38%**. The mean "improved" by averaging out a NEW DIPOLE — not a real tightening.

## KEY DIAGNOSTIC — the spatial DIPOLE (this is the publishable finding)
Per-mark residuals split cleanly by easting:
- **EAST (Sea Bright barrier, x~586–587k): now OVER-predicted +0.7 to +1.2 m** (587150/4467946 +1.21; 587045/4469712 +0.92; 587055/4466087 +0.86; 586835/4472336 +0.69).
- **WEST (Oceanport/Rumson upper estuary, x~582–585k): still ~1 m SHORT** (the old dry cells 582446/4465287 & 582447/4465258 dry→1.95 vs obs 2.96 = −1.01; 584467/4462845 −1.23; 585009/4463047 −0.71).
- **NORTH bay-mouth marks (x583–586k, y4470–4473k): spot-on +0.1..+0.2.**

Interpretation: the wavemaker injects IG/overtopping on the OCEAN/BARRIER (east) side — over-elevating the barrier marks — but the **narrows constriction still bottlenecks conveyance** to the western upper estuary (water enters east, can't cross to Oceanport). This CONFIRMS the 2026-06-02 trace: the Oceanport deficit is **CONVEYANCE, not forcing**. Dumping more waves at the barrier doesn't push water through the narrows.

## Direction check — CONFIRMED landward (by causality, not field map)
- The `hm0ig` west-vs-east test is **CONFOUNDED and useless on its own**: the −5 m line IS the land/sea boundary, so hm0ig west≈0 (within 1–2 km: WEST 0.01–0.03 vs EAST 1.4–1.6) just because west is dry barrier — NOT because the wavemaker fires seaward. Don't re-run that test as a direction proof.
- **Decisive proof = causality**: the X1 shared-domain coupling already existed pre-wavemaker and left Oceanport DRY; adding ONLY the wavemaker filled those exact cells (dry→1.95). Landward water appeared only when the wavemaker switched on → it fires LANDWARD (west). Consistent with the SFINCS/Leijnse convention (waves emit to the LEFT of the S→N vertex walking direction = west) and the eastern over-prediction (IG piles ~1.6 m at the line → setup over-elevates barrier marks).

## Two remaining fixes (NOT orientation)
1. **East — rein in overtopping MAGNITUDE** (barrier marks ~1 m too hot): check wavemaker `bhs`/IG magnitude is not too hot, and/or the Sea Bright barrier-crest DEM (too low → over-tops). See [[project-validation-roadmap]] barrier-threshold notes.
2. **West — fix the NARROWS CONVEYANCE** (Oceanport ~1 m short): refine the channel thread / check the controlling cross-section bathymetry at the Sea Bright/Rumson narrows so the correct head propagates inland. This is the dominant remaining back-bay miss.

Related: [[project-validation-roadmap]], [[project-hm0-spike-rootcause]], [[project-snapwave-root-cause]], [[project-compound-roadmap]], [[project-mask-boundary-cleanups]].
