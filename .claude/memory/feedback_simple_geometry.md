---
name: feedback-simple-geometry
description: "For NJ Sandy mask/boundary geometry, the user prefers simple transparent coordinate rules over auto-derived polygons, and economical validation over many heavy model-loads."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6dd93549-bf22-4192-b06c-9ba8d0d0c8c0
---

On the NJ Sandy quadtree boundary work (2026-06-23), I first built an elaborate
solution — a `build_waterlevel_exclude.py` script deriving polygons via
buffer-unions of mask cells, then an ocean include-polygon — and it kept breaking
at the thin Sea Bright barrier. The user redirected to a much simpler scheme: two
coarse coordinate **boxes** (`x</> threshold & y</> threshold`) applied as a
post-hoc mask reclassification in the notebook cell, exploiting that the Atlantic
is entirely on the east edge and Sandy Hook Bay entirely in the north. That was
cleaner, robust, and shipped. The user also interrupted one slow per-y-bin
diagnostic scan.

**Why:** simple geographic rules are transparent (the user can read and reason
about `x<582500 & y<4474000`), don't have buffer-union/simplify fragility, and
don't require external geojson artifacts. Auto-derived polygons looked rigorous
but were brittle exactly where geometry is hard (thin barriers, interleaved
ocean/estuary cells <200 m apart).

**How to apply:** for mask/boundary/region geometry on this project, reach for
coordinate thresholds / named boxes FIRST; only escalate to derived polygons if a
box genuinely can't express it. Validate economically — each
`SfincsModel(...).read()` is ~30 s; prefer reading `model_quadtree/sfincs.nc`
directly with xarray for quick checks, batch the checks, and don't iterate a heavy
diagnostic many times when a plot or a single targeted dump answers it. See
[[project-mask-boundary-cleanups]].
