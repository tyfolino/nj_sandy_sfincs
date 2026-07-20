"""Workstream E — infragravity evaluation, on the sealed premier.

Still the one open lever from the plan. The premier (``sealed_faber_waves``) runs SnapWave with
incident + wind-wave growth but **IG off**. The back-bay filling mechanism the investigation kept
landing on is WAVE-DRIVEN OVERTOPPING of the Sea Bright barrier (still-water surge sits right at
the +2–3.7 m crest; the runup on top does the work) and long-period runup up the tidal rivers —
exactly the infragravity band. So the cleanest evaluation is the premier with **one flag flipped**:
``snapwave_igwaves = 1``. Everything else — mesh, subgrid, forcing, support points, tuned physics —
is byte-identical to the premier, so any difference is IG and only IG.

This is a pure sfincs.inp change: ``snapwave_igwaves`` toggles the SnapWave IG balance and needs no
new boundary files (the same snapwave.bhs/btp/bwd/bds drive it). So we hard-link the ~1.8 GB of
shared inputs from ``experiments/_template_sealed`` (built off the sealed mesh by
setup_sealed_premier) and copy + rewrite only sfincs.inp — the same staging discipline as the 2x2.

Faber container (sfincs-desktop.sif; snapwave_gammax=2 baked in), waves ON.

Run:
  NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python scripts/setup_ig.py
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from nj_sfincs.config import ROOT

EXP = ROOT / "experiments"
TEMPLATE = EXP / "_template_sealed"
CRS_SRC = ROOT / "data" / "flux_crosssections.crs"

COPY_FILES = {"sfincs.inp"}

# premier + IG on. Diagnostics match the premier 2x2 so the flux/leak checks re-measure.
ARM = "sealed_igwaves_wind"
KV = {
    "snapwave": "1",
    "snapwave_igwaves": "1",   # <-- the only physics change vs the premier
    "snapwave_wind": "1",
    "storefw": "1",
    "storewavdir": "1",
    "storevel": "1",
    "crsfile": "sfincs.crs",
}


def _set_inp(inp: Path, kv: dict) -> None:
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


def main() -> None:
    if not (TEMPLATE / "sfincs_subgrid.nc").exists():
        raise SystemExit(
            f"no {TEMPLATE} — run scripts/setup_sealed_premier.py first (it builds the template)."
        )

    dst = EXP / ARM
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)

    for src in sorted(TEMPLATE.iterdir()):
        if src.is_dir():
            shutil.copytree(src, dst / src.name, copy_function=lambda s, d: os.link(s, d))
        elif src.name in COPY_FILES:
            shutil.copy2(src, dst / src.name)
        else:
            os.link(src, dst / src.name)

    if CRS_SRC.exists():
        shutil.copy2(CRS_SRC, dst / "sfincs.crs")
    _set_inp(dst / "sfincs.inp", KV)

    for stale in ("sfincs_his.nc", "sfincs_map.nc", "snapwave.upw", "sfincs.log"):
        (dst / stale).unlink(missing_ok=True)

    print(f"staged experiments/{ARM}  (premier + snapwave_igwaves=1; Faber, waves ON)")
    print("\nsubmit (--requeue survives heat-wave preemption):")
    print(
        f"  SFINCS_SIF=$PWD/sfincs-desktop.sif sbatch --time=04:00:00 "
        f"hpc/sfincs_run.slurm experiments/{ARM}"
    )


if __name__ == "__main__":
    main()
