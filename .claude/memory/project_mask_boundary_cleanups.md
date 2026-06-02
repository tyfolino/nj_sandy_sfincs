---
name: project-mask-boundary-cleanups
description: NJ Sandy quadtree — two OPTIONAL mask/boundary improvements to add AFTER current X1+CUDEM testing finishes (deferred 2026-06-02). (1) waterlevel boundary wrongly claims ~1052 back-bay/estuary edge cells; restrict to Atlantic edge + A/B back-bay validation. (2) drop isolated disconnected active-cell patches (offshore GEBCO blob + Sandy Hook slivers).
metadata: 
  node_type: memory
  type: project
  originSessionId: 63424ae5-8815-4197-8275-6cf0f8cea8eb
---

# Mask/boundary cleanups — DEFERRED until after current testing (2026-06-02)

Surfaced while reviewing the rebuilt quadtree mask-layout plot. Both are
PRE-EXISTING (not caused by the X1/CUDEM work), optional, and NOT blockers for
the in-progress run. User wants to add them AFTER finishing the current X1 +
re-clipped-CUDEM test. Implement as opt-in toggles and A/B the back-bay
validation before committing.

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
