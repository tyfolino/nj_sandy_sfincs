---
name: project-mask-boundary-cleanups
description: NJ Sandy quadtree mask/boundary cleanups. (1) waterlevel boundary wrongly claimed estuary edges — IMPLEMENTED 2026-06-23 via two coordinate boxes in notebook cell 0137685c (west-below-bay→outflow, Shrewsbury→active; Atlantic+Sandy Hook Bay stay waterlevel). No subgrid rebuild; validated in-memory; not re-run end-to-end. (2) drop isolated disconnected active-cell patches (offshore GEBCO blob + Sandy Hook slivers) — still pending.
metadata: 
  node_type: memory
  type: project
  originSessionId: 63424ae5-8815-4197-8275-6cf0f8cea8eb
---

# Mask/boundary cleanups — (1) IMPLEMENTED 2026-06-23, (2) still pending (2026-06-02; 2026-06-12; 2026-06-23)

Surfaced while reviewing the rebuilt quadtree mask-layout plot. Both are
PRE-EXISTING (not caused by the X1/CUDEM work), optional, and NOT blockers for
the in-progress run. Implement as opt-in toggles and A/B the back-bay
validation before committing.

**UPDATE 2026-06-23 — item (1) IMPLEMENTED + validated; NO LONGER batched into X2.**
Key realization: restricting the waterlevel boundary is a boundary-TYPE change
(mask 2↔3, plus a few 2→1) among already-active cells → it does NOT touch the
active mask → needs **no subgrid rebuild**, just re-run the mask cell + sf.write().
So it's decoupled from the (expensive, true mask/extent) X2 rebuild and was done now.

**FINAL APPROACH (2026-06-23, after rejecting two polygon attempts): two coarse
coordinate BOXES in notebook cell `0137685c`, no external geojson/script.** The
Atlantic is entirely on the EAST domain edge and Sandy Hook Bay entirely in the
NORTH, so after the standard `create_boundary(waterlevel,zmax=-1)` +
`create_boundary(outflow,zmin=-1,zmax=2)`, reclassify by face_coordinates:
- `west_below_bay = (fx<582500)&(fy<4474000)`: mask 2→3 (Navesink/Red Bank +
  mainland west edges → outflow). ~44 cells.
- `shrewsbury = (fx>586500)&(fx<587400)&(fy>4467000)&(fy<4472000)`: mask 2→**1
  (plain active)** — a SMALL Shrewsbury back-channel pocket WEST of the seaward
  edge (only ~7 cells). 
- Atlantic + Sandy Hook Bay STAY waterlevel.

**CRITICAL CORRECTION (2026-06-23, after re-run): the Sea Bright → Highlands
seaward strip (x~587600-588100, y4467000-4472000) MUST stay waterlevel.** First
nudge had the shrewsbury box east edge at x<588300, which swallowed that strip and
**cut the open-ocean WL boundary from Sea Bright to Highlands** (user caught it in
the dep-map plot). The strip is NOT an interior estuary / "scour hole" feature —
verified east of it (x588150-589500, y4467500-4471500) all 2160 cells are
**inactive, z −11..−16 m = the deep Atlantic shelf** (below the −10 m active
cutoff). So that strip (z≈−9.8) IS the model's open-ocean boundary there; it must
be driven or no surge enters along that flood-prone stretch. Fix: pull the box
east edge 588300→**587400** so it only de-WLs the genuine back-channel pocket and
spares the seaward strip. (My earlier "deep scour hole WEST of the channel" read
was wrong — the inactive deep water is EAST = the Atlantic shelf.)

In-memory validation (no write) after the nudge: WL=2401, outflow=93,
active=233126; the Sea Bright→Highlands strip is continuous WL again (105 cells
restored); active mask intact (no subgrid rebuild). SUPERSEDED the fragile polygon
approaches (river-head exclude_polygon, then ocean include_polygon — both broke at
the thin Sea Bright barrier where ocean/estuary cells are <200 m apart). NOT YET
RE-RUN end-to-end after this nudge.
- **SCOPE CORRECTION (same session): only the RIVER HEADS flip, NOT Sandy Hook
  Bay.** First cut excluded the whole non-Atlantic perimeter (bay→outflow, mask=2
  2452→1070) — user pushed back: Sandy Hook Bay is a tidal embayment that opens
  north to Raritan Bay / NY Harbor (external tidal driver outside the domain;
  Sandy Hook range ~1.4 m ≈ open coast), so it CO-OSCILLATES with the forcing and
  must STAY waterlevel. WL-vs-outflow rule of thumb: waterlevel = co-oscillating
  opening to an external tidal body whose tide ≈ forcing (Atlantic + Sandy Hook
  Bay); outflow = HEAD/terminus fed from WITHIN the domain (Navesink @ Red Bank,
  Shrewsbury @ Sea Bright narrows). The old memory note (and my first polygon)
  wrongly lumped the bay in with the river heads.
- `scripts/build_waterlevel_exclude.py` derives `data/waterlevel_exclude.geojson`
  (EPSG:32618): deep boundary cells (mask∈{2,3} & z≤−1, robust to current type),
  Atlantic = easternmost per northing bin (30 bins / 1500 m), then arm = LANDWARD
  cells inside named RIVER_HEAD_BOXES (navesink 580000–582500 / 4464000–4474000;
  shrewsbury 586500–590000 / 4464000–4468000 — the box+seaward AND is needed
  because the Sea Bright barrier is too thin for a box alone to separate ocean
  from bay). Buffer-union(arm,130 m) MINUS 90 m clear-buffer around keep-WL cells.
  Verify: 0 keep-WL inside, ~62/65 arm covered (30 Navesink + 35 Shrewsbury).
- Notebook cell ~15 behind `RESTRICT_WL_TO_ATLANTIC` toggle (code UNCHANGED across
  the scope fix — only the geojson content changed): waterlevel `exclude_polygon`
  + 2 outflow passes (shallow −1..2 m; deep `zmax=-1, include_polygon`). Cell-14
  markdown rewritten to the river-head framing. Path read via data_catalog.
- **In-memory validation from a clean baseline** (no write): only **63 deep cells
  flip WL→outflow** (x 580637–588028, y 4465946–4469500 = the two heads), mask=2
  2452→2389, mask=3 49→112, mask=1 unchanged 233119 (no subgrid rebuild). Sandy
  Hook Bay (~1320 cells) stays waterlevel.
- **Compensation catch DEFUSED:** the worry that the bay clamp propped up back-bay
  levels is largely gone — the Rumson–Sea Bright bridge-dam carve (eHydro 2015,
  [[project-bridge-dam]]) now lets surge reach the back-bay through the inlet
  (user confirmed on Amarel: the Shrewsbury floods beautifully). Still A/B the
  upper-Navesink (Red Bank) levels to be sure. NOT YET RE-RUN.

**DECISION (2026-06-12):** fold the boundary restriction + sliver drop into the
SAME Phase-1 rebuild as the X2 seaward extension (both are mask/geometry changes →
one ~13 GB rebuild, not two). **X2 alone does NOT fix the Sandy Hook boundary wrap** —
X2 redraws the *eastern* (Atlantic) edge; the wrap is the *northern* Sandy Hook Bay
edge, and those bay cells are already deep (median zb −9.9 m) so it isn't a depth
problem either. Keep the two "Sandy Hook" problems distinct: (a) this boundary-GEOMETRY
wrap (NOT fixed by X2) vs (b) the Sandy Hook GAUGE NOISE = the offshore 2Δx ring
leaking ~2.7 km to the gauge (IS fixed by X2). Documented in the notebook: boundary
markdown cell (### 5) has a "Known issue" note; the end-of-notebook status section
open-question #2 covers both boundary fixes. See [[project-wavemaker-run]], [[project-validation-roadmap]].

**Recount on the CURRENT (post-wavemaker) model, 2026-06-12:** 2403 mask==2 cells —
**962 on the Atlantic seaward edge, 1441 west/back of it, of which ~980 in Sandy Hook
Bay** (was 1970/918/1052 on 2026-06-02; rebuild shifted the counts, same story).

## (1) Waterlevel boundary claims the back-bay / estuary edges
`quadtree_mask.create_boundary(btype="waterlevel", zmax=-1)` (notebook cell ~14)
grabs EVERY domain-edge cell with z <= -1 m, with no east/west distinction. On
the on-disk model, of 1970 mask==2 cells only **918 are on the Atlantic edge**;
**1052 are west of the barrier** (Sandy Hook Bay, Navesink/Shrewsbury, back-bays)
— deep channel cells z -10..-1.
- **Issue:** imposing the full open-coast NOAA tide+surge at an upstream estuary
  cut over-drives it (real tide is attenuated/lagged AND the estuary is already
  tidally connected to the ocean through Sandy Hook Bay inside the domain →
  double-driving → likely over-predicts upper-estuary levels).
- **CATCH (why not just flip it):** MOTF validation previously flagged MISSED
  back-bay flooding (reason for the inlet-channel work, [[project-nj-sandy]] /
  model_inlet_test). The bay-edge waterlevel forcing may be partly COMPENSATING
  for under-resolved inlets. Flipping to outflow could WORSEN back-bay levels if
  inlets aren't carrying enough surge. So TEST, don't assume.
- **Fix:** restrict waterlevel boundary to the Atlantic edge (include_polygon /
  exclude_polygon on create_boundary, or reassign east-of-barrier x~586500), let
  bay edges fall to outflow (mask=3). Wire as a toggle; A/B the MOTF / back-bay
  validation.

## (2) Isolated disconnected active-cell patches ("weird features" near Sandy Hook)
Connected-components on the active mask: main domain = 237,319 cells, plus small
disconnected islands whose whole perimeter becomes boundary (the red loops in
the plot):
- **153 cells @ (592411, 4483684), all exactly z=-10.0** — flat GEBCO blob cut
  off offshore-NE; 45 are mask==2 → a disconnected "pond" forced at ocean level
  (the offshore red ellipse).
- 13-cell + 1-cell intertidal slivers (z~0) by the Sandy Hook spit (~583k,4480k).
- 2 isolated z=-9.8 cells @ (587890,4461822), both boundary.
- **Fix:** drop small disconnected active regions at mask creation — hydromt
  create_active `drop_area` / min-region-size option. Sandy Hook bathymetry IS
  genuinely complex (channels/spit/shoals) but these specific blobs are
  mesh-disconnection artifacts, not features to keep.

Related: [[project-hm0-spike-rootcause]], [[project-snapwave-root-cause]], [[project-nj-sandy]], [[project-compound-roadmap]].
