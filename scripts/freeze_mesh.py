#!/usr/bin/env python
"""Build the canonical static mesh ONCE and freeze it.

The quadtree grid + subgrid build is environment-sensitive: two builds of
identical code/config can differ by ~18 cells, enough to shift MOTF CSI ~0.04
(the notebook-0.54 vs harness-0.50 discrepancy, 2026-07-03). Freezing one mesh
and having every run reuse it removes that variance.

Usage
-----
    python scripts/freeze_mesh.py                 # -> data/frozen_mesh/
    python scripts/freeze_mesh.py path/to/dir     # custom location

Then set ``BaseConfig.frozen_mesh`` to that path (in nj_sfincs/config.py, or via
``dataclasses.replace``). Both ``run_experiments.py`` and — with the copy snippet
below — the notebook will then start from this identical grid:

    # notebook: replace the Phase-1 build cells with, once the mesh is frozen:
    import shutil; shutil.copytree("data/frozen_mesh", MODEL_ROOT, dirs_exist_ok=True)
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

from nj_sfincs import model
from nj_sfincs.config import ROOT, BaseConfig


def main(out: str = "data/frozen_mesh") -> int:
    out_path = Path(out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    if (out_path / "sfincs.inp").exists():
        print(f"Refusing to overwrite an existing mesh at {out_path} "
              f"(delete it first to re-freeze).")
        return 1
    # frozen_mesh=None so build_static actually BUILDS (doesn't try to copy).
    base = replace(BaseConfig(), frozen_mesh=None)
    print(f"Building canonical static mesh -> {out_path} (this is the CPU peak) ...")
    model.build_static(base, out_path)
    print(f"Done. Set BaseConfig.frozen_mesh = {out_path!s} to reuse it everywhere.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
