"""Workstream M — the boundary-depth sweep, on the sealed premier.

James/Tim: try a DEEPER open-boundary contour. The premier activates cells with
``z >= mask_zmin = -10 m``; this stages the same premier config at ``-15`` and ``-20 m``
so incident waves + surge enter in deeper water and shoal across more shelf, and the known
2Δx boundary-edge zs ring sits further offshore.

WHY THIS NEEDS NO SUBGRID REBUILD (the whole point). The frozen sealed mesh reaches -69 m and
**every one of its 547,408 faces already carries subgrid tables** — the subgrid is computed per
face from elevation+roughness, independent of the mask. So a deeper ``mask_zmin`` only ACTIVATES
faces that already have tables (verified: -15 adds ~31k seaward faces, -20 adds ~90k). This is a
mask + boundary + forcing re-derivation on a COPY of the frozen mesh, not a rebuild:

  1. copy data/frozen_mesh_sealed -> experiments/<arm>
  2. re-run model.apply_mask_and_boundary at the new zmin (the SAME code the premier build uses,
     only mask_zmin differs — verified to reproduce the frozen mask bit-for-bit at zmin=-10, so
     any change here is purely the intended seaward extension)
  3. re-run add_forcing (the water-level boundary is interpolated onto mask==2 cells, which moved)
     + add_waves (the SnapWave support points are the deep, open-Atlantic mask==2 edge, which moved
     seaward) with the premier wave config
  4. finalize

Runs the PREMIER container (Faber = sfincs-desktop.sif, snapwave_gammax=2 baked in) with waves
ON — the boundary-depth effect is only meaningful against the premier it modifies.

WHAT THIS HAS TO SHOW (before looking):
  - Deeper boundary should not move the sheltered basins much (Shrewsbury/Shark are far inland of
    the contour); if it does, the contour is coupling to the interior and that is a red flag.
  - The open-coast gauge (Sandy Hook) + the offshore zs ring are where a deeper boundary should act.
  - The -4 m arm is DEFERRED — create_active(zmin) is a GLOBAL cut and -4 would deactivate the
    carved Shrewsbury narrows (-4.65 m). See the plan.

Run (stages both arms; ~a few min each, forcing+waves+write):
  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/setup_boundary_depth.py
"""

from __future__ import annotations

import gc
import shutil
from dataclasses import replace
from pathlib import Path

from hydromt_sfincs import SfincsModel

import nj_sfincs  # noqa: F401  (PROJ primer — must precede hydromt_sfincs)
from nj_sfincs import model
from nj_sfincs.config import EXPERIMENTS, ROOT, BaseConfig

EXP = ROOT / "experiments"
FROZEN = ROOT / "data" / "frozen_mesh_sealed"
CRS_SRC = ROOT / "data" / "flux_crosssections.crs"

# The premier's own wave config (SnapWave incident + wind growth + Tim's tuned physics, IG off).
WAVE_CFG = EXPERIMENTS["snapwave_tuned"].waves

# arm name -> open-boundary depth contour [m]
ARMS = {
    "sealed_bdepth_m15": -15.0,
    "sealed_bdepth_m20": -20.0,
}

# Diagnostics kept identical to the premier 2x2 so the flux/leak checks re-measure automatically.
DIAG = {"crsfile": "sfincs.crs", "storevel": "1"}


def _set_inp(inp: Path, kv: dict) -> None:
    """Set/append ``key = value`` lines in an sfincs.inp (mirrors setup_sealed_premier)."""
    lines = inp.read_text().splitlines()
    have = {ln.split("=")[0].strip() for ln in lines if "=" in ln}
    out = []
    for ln in lines:
        key = ln.split("=")[0].strip() if "=" in ln else ""
        out.append(f"{key:<20} = {kv[key]}" if key in kv else ln)
    for key, val in kv.items():
        if key not in have:
            out.append(f"{key:<20} = {val}")
    inp.write_text("\n".join(out) + "\n")


def stage(name: str, zmin: float) -> Path:
    base = replace(BaseConfig(), mask_zmin=zmin)  # sealed region is already the default
    dst = EXP / name
    if dst.exists():
        shutil.rmtree(dst)

    print(f"[{name}] copying frozen sealed mesh (subgrid reused, not rebuilt)")
    shutil.copytree(FROZEN, dst)

    sf = SfincsModel(str(dst), data_libs=base.data_libs, mode="r+")
    n_before = int((sf.quadtree_grid.data["mask"].values > 0).sum())
    print(f"[{name}] re-deriving mask/boundary at zmin={zmin:.0f} m")
    model.apply_mask_and_boundary(base, sf)
    n_after = int((sf.quadtree_grid.data["mask"].values > 0).sum())
    print(f"[{name}] active cells {n_before} -> {n_after} (+{n_after - n_before} seaward)")

    print(f"[{name}] forcing + waves")
    model.add_forcing(base, sf)
    sw = model.add_waves(WAVE_CFG, base, sf)
    model.finalize(WAVE_CFG, base, sf, dst, sw)
    del sf
    gc.collect()

    if CRS_SRC.exists():
        shutil.copy2(CRS_SRC, dst / "sfincs.crs")
    _set_inp(dst / "sfincs.inp", dict(DIAG))

    for stale in ("sfincs_his.nc", "sfincs_map.nc", "snapwave.upw", "sfincs.log"):
        (dst / stale).unlink(missing_ok=True)
    return dst


def main() -> None:
    if not (FROZEN / "sfincs_subgrid.nc").exists():
        raise SystemExit(f"no subgrid in {FROZEN} — has the sealed rebuild finished?")

    print("staged:")
    for name, zmin in ARMS.items():
        stage(name, zmin)
        print(f"  experiments/{name:<22s} zmin={zmin:.0f} m  (Faber, waves ON)")

    print("\nsubmit (Faber container; --requeue survives heat-wave preemption):")
    for name in ARMS:
        print(
            f"  SFINCS_SIF=$PWD/sfincs-desktop.sif sbatch --time=04:00:00 "
            f"hpc/sfincs_run.slurm experiments/{name}"
        )


if __name__ == "__main__":
    main()
