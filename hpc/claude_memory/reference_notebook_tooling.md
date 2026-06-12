---
name: reference-notebook-tooling
description: "How to inspect/edit the Jupyter notebook in this project — env paths, no bare `jupyter` on PATH."
metadata: 
  node_type: memory
  type: reference
  originSessionId: d42c392d-6e72-4484-805c-d5b00cb0ae62
---

Bare `jupyter`/`nbformat`/`jq` are NOT on the default bash-tool PATH in this environment. Don't try `jupyter nbconvert ...` directly — it fails with "command not found".

- Conda is miniforge3 at `~/miniforge3`; envs: `sfincs` and `nj-sfincs` (both have nbformat 5.10.4 + full Jupyter stack).
- To inspect/parse the notebook from the shell, use the env interpreter directly: `~/miniforge3/envs/sfincs/bin/python -c "import nbformat; ..."` (or plain `python3` with `json` for read-only cell dumps — base python3 lacks nbformat but `json` is fine).
- To EDIT notebook cells, use the native `NotebookEdit` tool, not hand-edited JSON.
- If you DO rewrite the `.ipynb` JSON by hand, match the existing serialization or git explodes into a 1000-line whitespace diff: `json.dumps(nb, indent=1, ensure_ascii=False)` + a trailing newline. The notebook stores Unicode RAW (em-dashes, →, ², −), so the default `ensure_ascii=True` re-escapes every such line. A plain `nbformat.write` round-trip is ALSO noisy here (not byte-clean). Verify with a no-op round-trip → empty `git diff` before trusting a hand edit.
- **NEVER `git checkout`/`git restore` the notebook to "reset formatting."** The quadtree notebook's day-to-day work (e.g. the 2026-06-02 Phase-3 validation fixes: tiled downscale `nrmax=1000`, `nearest_wet_face`/`face_coordinates` quadtree sampling, de-rotate `reproject_match`) frequently lives UNCOMMITTED in the working tree — a checkout silently destroys it. (Happened 2026-06-02; recovered only because the cells were verbatim in the session transcript + VSCode Local History had partial snapshots at `~/.vscode-server/data/User/History`.) **Action for the user: commit the notebook often** so the working tree isn't the only copy.

The main notebook is now [notebooks/sfincs-asbury-sandy-quadtree.ipynb](../../../notebooks/sfincs-asbury-sandy-quadtree.ipynb) (the Phase-3 quadtree build; the old regular-grid `sfincs-asbury-sandy.ipynb` still exists). Related: [[project-nj-sandy]], [[project-validation-roadmap]].
