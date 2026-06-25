---
name: project-james-suggestions
description: "James's modeling tuning suggestions (deeper active boundary, coarser offshore mesh) — forward-looking, not yet tried."
metadata: 
  node_type: memory
  type: project
  originSessionId: 29c0a27e-cfd7-4b35-88fc-259265d7dac0
---

Tuning suggestions from **James** (collaborator/domain advisor), originally jotted as "Note from James" asides in the notebook. Pulled into memory on 2026-06-25 when the notebook was cleaned up for the [[project-housekeeping-2026-06-25]] template — the notes are kept here so the ideas aren't lost. None tried yet.

1. **Make the active/inactive boundary deeper.** Currently active = `bed ≥ −10 m` (inactive on the deep shelf). James suggests trying **−10, −20, −30 m** — a deeper cutoff may better capture **long-period gravity waves**. Directly relevant to the **X2 seaward-extension** work ([[project-snapwave-root-cause]]): as the mesh extends offshore, the active-depth threshold is exactly the knob that decides how much shelf the flow solver sees.

2. **Coarser cells far offshore + double the resolution everywhere.** When pushing the domain farther offshore, the base offshore cell can go to **~1 km**, and shelf + bays can sit around **200 m**. Also "try doubling all resolution." Pairs with X2 — the seaward extension adds coarse offshore levels (current X2 plan: 400 → 800 → 1600 m), and James is comfortable going coarser still out deep.

Related: [[project-validation-roadmap]], [[project-compound-roadmap]].
