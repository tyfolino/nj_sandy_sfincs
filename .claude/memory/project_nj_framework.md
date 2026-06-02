---
name: project-nj-framework
description: NJ Sandy SFINCS notebook is intended to become a REUSABLE FRAMEWORK/template generalizable to all of New Jersey (other domains/events), readable for mixed/newer audience — not just a one-off Sandy hindcast.
metadata:
  type: project
---

User goal (stated 2026-05-21): turn the Sandy notebook into a **reusable framework for all of New Jersey** — re-point it at a different NJ domain/event by changing a few clearly-marked knobs, not by hunting through cells. Audience is "mixed / future learners" (a grad student new to SFINCS should be able to follow), but they want it only **lightly** pedagogical — NOT a heavy teaching rework (no reframing every header as a question, no long concept paragraphs).

Implications / what makes it a framework:
- A single top **Configuration** cell gathering the per-domain/event knobs now scattered across cells: region geojson path, model_root, CRS, grid res, nr_subgrid_pixels, event window (tref/tstart/tstop), boundary buffer, beta_f, latitude, data_catalog path.
- Short **"site-specific — swap this for another domain/event"** notes where hardcoded: NOAA gauges, NDBC buoy, USGS rivers, the *pre-Sandy* DEM choice (for another event pick a contemporaneous DEM), AORC/USGS windows.
- Light concept intros (one clause) + bold **Takeaway** lines on results.
- De-clutter the config cell (39 comment lines) → move rationale to markdown.
- OUT OF SCOPE for the notebook pass but needed for true NJ generalization: the download scripts also hardcode site specifics (gauge IDs, river gauges, bbox) — parameterizing those is a separate step.

Related: [[project-compound-roadmap]], [[project-nj-sandy]], [[reference-notebook-tooling]].
