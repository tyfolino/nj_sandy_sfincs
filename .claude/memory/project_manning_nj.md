---
name: project-manning-nj
description: "NJ Sandy SFINCS — NLCD→Manning's n reclass table (Bunya/Atkinson Atlantic-coast values, with class-23/24 NJ tuning); replaces hydromt-sfincs's shipped SFBD-tuned default"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8ffca0c4-0440-46e9-8c2f-ad024ab66809
---

NJ-tuned NLCD → Manning's n reclass for Atlantic-coast storm surge.
Lives at `data/roughness/NLCD_CONUS_mapping.csv` with a full sidecar README at
`data/roughness/NLCD_CONUS_mapping.README.md` (per-class table + reasoning).

**Why:** the hydromt-sfincs default `NLCD_SFBD_mapping.csv` is SF-Bay-Delta-tuned
(marsh-heavy, with implausibly high developed-class friction for an East-Coast
urban coastline). For NJ coastal storm surge we use values from
**Bunya et al. (2010, *Mon. Wea. Rev.* 138:345-377)** and **Atkinson et al.
(2011)** — the de-facto Atlantic-coast ADCIRC / FEMA NACCS post-Sandy table.

**Two NJ-specific refinements (don't re-debate):**
- **Class 23 (Developed-Medium): 0.100**, not Atkinson's 0.080. Per-cell NLCD
  diagnostic (2026-05-25) showed class 23 was 55 % of new false alarms after a
  pure-Atkinson swap (FA/HIT = 2.5×) — Asbury Park / Shark River residential
  was over-flooding. Bunya (2010)'s original 0.10 is what we adopt.
- **Class 24 (Developed-High): 0.130**, split between Bunya 0.150 and Atkinson 0.120.

**How to apply:** in the NLCD reclass cell, set `reclass_table =
"/home/zagreus/nj_sandy_sfincs/data/roughness/NLCD_CONUS_mapping.csv"` instead of
`os.path.join(DATADIR, "lulc", "NLCD_SFBD_mapping.csv")`. The CSV is bare (no
comment lines) because hydromt's PandasDriver calls `pd.read_csv` without
`comment="#"` — any leading `#` lines crash the parse.

## Results

| run | CSI | POD | FAR | new hit (km²) | new FA (km²) | comment |
|---|---|---|---|---|---|---|
| baseline (SFBD) | 0.46 | 0.57 | 0.29 | — | — | starting point |
| pure Atkinson (class 23/24 = 0.080/0.120) | 0.48 | 0.63 | **0.33** | 2.37 | 2.86 | won Shrewsbury, lost Asbury (urban FAs) |
| **NJ-tuned (class 23/24 = 0.100/0.130)** | **0.49** | **0.60** | **0.28** | **1.24** | **0.33** | **adopted — strict win on FAR, 3.8:1 hit:FA ratio** |

Won via reduced developed-class friction letting surge spill into Shrewsbury
back-bay (something the inlet-DEM-burn experiment couldn't do). Class-23/24
tweak eliminated the Asbury/Shark River urban over-flood without losing the
Shrewsbury benefit.

## Promoted into the main notebook 2026-05-25

Cell `5228f7f8` now points at `data/roughness/NLCD_CONUS_mapping.csv` directly.
TODO markers in cells `9cc88bb9` (overview) and `data-sources-table` removed.
**The working `model/` directory is still on the OLD SFBD reclass** — Manning
lives in the subgrid tables, so the change only takes effect on the next
Phase-1 rebuild. Backup of the main notebook before the swap is at
`/tmp/nb_before_manning_swap.ipynb.bak`.

Related: [[project-compound-roadmap]] (Phase 2 status), [[project-nj-framework]]
(notebook is a reusable NJ template — Manning swap is a NJ-tuning decision).
