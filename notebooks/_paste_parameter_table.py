# ─────────────────────────────────────────────────────────────────────────────
# PASTE-ME into notebooks/sfincs-nj-sandy-viz.ipynb
#
# Two cells. Put them AFTER the cell that opens `sf` / `mod` (currently cell 3,
# "Open read-only: `sf` ... and `mod` ...") and BEFORE "## Methodology — the build".
# They need `sf` to exist, because the whole point is that the table is read from the
# opened run rather than transcribed.
#
# Delete this file once pasted; it is a delivery vehicle, not part of the notebook.
# (It lives here rather than being inserted directly because the notebook was open in
# VS Code, and editing an open .ipynb wipes its rendered outputs.)
# ─────────────────────────────────────────────────────────────────────────────


# ── CELL 1 of 2 — markdown ───────────────────────────────────────────────────
# Make a MARKDOWN cell and paste the text between the triple quotes:
"""
## Every parameter, in one place

The complete configuration of the run opened above — solver, SnapWave, wind drag, output,
grid/subgrid, mask and boundary depths, the elevation merge **in build order**, and the
forcing sources.

Read **live** from the run's own `sfincs.inp` and `nj_sfincs.config`, so it cannot drift
from what actually ran. Every key in `sfincs.inp` is listed; anything without a
description on file still appears, under *Other / unannotated* — a parameter you cannot
see is a parameter you cannot debug.

All elevations, depths and water levels are **metres NAVD88**.
"""


# ── CELL 2 of 2 — code ───────────────────────────────────────────────────────
# Make a CODE cell and paste the lines below (the import is separate from the notebook's
# other imports on purpose — it keeps this a self-contained paste).
#
# The reload matters: a long-lived kernel caches `nj_sfincs.params` from the first import,
# so a later `from nj_sfincs import params` silently keeps running the OLD file and you
# debug a traceback whose line numbers do not match the source in front of you. Reloading
# costs nothing and means you never have to restart the kernel (and re-open `sf`, which
# re-runs a multi-minute downscale) just to pick up an edit.

import importlib

from nj_sfincs import params

importlib.reload(params)

params.show(sf)


# ── Notes ────────────────────────────────────────────────────────────────────
# * params.show(sf) renders in the notebook. params.show(sf, as_markdown=True) returns the
#   raw markdown string instead — that is what to use if you want to drop the same table
#   into reports/shrewsbury_investigation.md or a paper appendix.
# * It reads whichever run `sf` points at. Open a different experiment and the table
#   follows it, so a bdepth arm or an IG arm documents itself correctly with no edits.
# * If you add a new SnapWave/SFINCS knob, add one line to INP_META in nj_sfincs/params.py
#   to annotate it. You do NOT have to, though: an unannotated key still shows up, it just
#   lands under "Other / unannotated" without a description.
