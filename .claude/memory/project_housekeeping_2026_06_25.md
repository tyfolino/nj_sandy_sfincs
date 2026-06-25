---
name: project-housekeeping-2026-06-25
description: "Repo + notebook housekeeping 2026-06-25: canonical notebook renamed/cleaned, archive/ + reference/ folders, stale dirs deleted, README refreshed."
metadata: 
  node_type: memory
  type: project
  originSessionId: 29c0a27e-cfd7-4b35-88fc-259265d7dac0
---

Major housekeeping pass on 2026-06-25 to make the notebook a clean event-modeling example, clearing the path before the Sandy Hook Bay boundary re-validation.

**Notebook:** `sfincs-asbury-sandy-quadtree.ipynb` → renamed `notebooks/sfincs-nj-sandy.ipynb` and made the standalone canonical example (it's the only live build path — SnapWave needs quadtree). Reframed title (dropped "Phase 3 / rebuild-of-regular-grid" framing). Markdown cleaned: removed the three "Note from James" tuning asides, **reconciled the Sandy Hook Bay boundary prose to one truthful state** = *two-box fix implemented in code (cell `0137685c`) but NOT yet re-validated with a run* (previously it read as "done" in step 5, "planned/future" in the overview caveat, and "future" in the status cell). Tagged the unverifiable status numbers (CSI ≈0.53/0.61, mean +0.07 m, 0.33→0.40) as "last full run, pre-boundary-fix." Fixed the stale wavemaker direction warning (direction was already CONFIRMED landward — see [[project-wavemaker-run]]). Only the 5 markdown cells changed; all 35 code cells + their IDs are byte-identical.

**Notebook is now a clean source-only template:** all cell outputs cleared and all metadata stripped (kernelspec + language_info removed → kernel-agnostic; 506 KB → 85 KB) on 2026-06-25 for a cross-machine/Amarel workflow. So the notebook now carries NO stored outputs — run it to regenerate the validation figures/numbers. (Editing it is via byte-clean JSON script, not NotebookEdit — it exceeds the Read-tool token cap; see [[reference-notebook-tooling]].)

**nbstripout git clean filter (set up 2026-06-25).** `*.ipynb filter=nbstripout` lives in the committed `.gitattributes`; the actual filter config is per-clone (`.git/config`, not committed). Set it up on each machine with **`python scripts/setup_nbstripout.py`** (uses the running interpreter's path, so it works on the laptop miniforge env and the Amarel micromamba env). The filter runs `nbstripout --keep-id --extra-keys "metadata.kernelspec metadata.language_info"`: clears outputs + execution_count + kernelspec/language_info, but **`--keep-id` is essential** — without it nbstripout renumbers cell ids to 0,1,2… and breaks the stable `0137685c`-style ids that memory keys off (verified: nbstripout default DOES clobber ids; also 0.9.1 ignores pyproject/setup.cfg config, so the flags must live in the filter command). Clean-only filter → it strips the committed blob but leaves the working tree's rendered outputs intact. `nbstripout` added to both `environment.yml` files (pip).

**Repo moves (staged, NOT committed — user commits per [[feedback-git-workflow]]):**
- `notebooks/archive/` ← regular-grid `sfincs-asbury-sandy.ipynb` + `experiment_inlet_connectivity.ipynb` + `experiment_manning_nj.ipynb` (superseded; kept for provenance).
- `notebooks/reference/` ← Tim Leijnse's `build_quadtree_from_script_TKI-share_…withwavemaker.ipynb`, now **git-tracked** (was gitignored at .gitignore:19; line removed) with outputs stripped (5.3 MB → 48 KB).
- **Deleted:** `model/` (stale regular-grid run, was gitignored), `model_inlet_test/` + `model_manning_test/` (`git rm`, settled experiments), `notebooks/floodmap.html` (5.1 MB stray tracked artifact). `model_quadtree/` is the sole live model.
- `.gitignore` pruned (dropped `model/`, the two `model_manning_test/*.nc` lines, and Tim's notebook line).
- `scripts/build_quadtree_notebook.py` flagged HISTORICAL (SRC→archive path, DST→new name) — see [[project-quadtree-session]].
- `hpc/run_notebook.slurm` default NB path updated to the new name.
- **README.md** refreshed: grid (50 m → quadtree), waves (Stockdon → SnapWave+wavemaker), run paths (`model/` → `model_quadtree/`), layout, and roadmap (quadtree/SnapWave were listed "planned" but are the live model; remaining = back-bay conveyance + Sandy Hook Bay boundary validation + X2).

**Pending after this:** run `scripts/sync_claude_memory.sh backup` to mirror this memory into the repo, then commit. The actual boundary re-run (and refreshing the validation numbers) is the next session's work — see [[project-mask-boundary-cleanups]].
