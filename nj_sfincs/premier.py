"""THE PREMIER and the domain it stands on — one place, asserted, not remembered.

WHY THIS FILE EXISTS (2026-07-21)
---------------------------------
The tidal phase-lag A/B (``phaselag_battery`` / ``_shblend`` / ``_gtsm``) ran to completion
on SLURM — clean exit, full-length output, no warning anywhere — and was **scientifically
void**, because ``run_experiments.py`` staged it from ``experiments/_template`` while the
adopted premier lives on ``experiments/_template_sealed``. Those are different domains: the
old one still has the Navesink mass leak and a dammed Shark River Inlet.

Nothing caught it. The staging was silent, the solver was happy, and the metrics came back
as plain numbers with no marking to say which planet they were measured on. What finally
exposed it was ``stat``-ing inodes by hand, hours later.

The trap has a sharp edge worth naming: **the open coast is nearly domain-independent.**
``phaselag_battery`` reproduced the premier's Sandy Hook phase lag to within 0.3 min
(16.9 vs 17.2), which looked like proof the harness had staged correctly. It was not. The
estuary — the entire subject of the experiment — was 30% down in tidal range at Shrewsbury
and flat dead at Shark (0.03 m vs 1.35 m). A coastal control cannot validate an interior
experiment, and a control that passes on the wrong domain is worse than no control at all.

So: the premier's identity is defined HERE, checked by fingerprint, and asserted at every
point where an experiment is staged or scored.

WHAT IDENTIFIES THE DOMAIN
--------------------------
Not file size, and not the inode. Both are real signals — every ``sealed_*`` run hard-links
one 253,750,180-byte ``sfincs.nc`` (inode 579215649) while the old template's is
253,681,934 — but a per-experiment forcing override rewrites ``sfincs.nc`` in place, giving
each arm its own inode and breaking the link. Size survives that; identity does not.

What survives everything is the **mesh and the bed**:

    sealed   547,408 faces   1,635 boundary edges   sha256(z, mask)[:16] = 45f4f74ca9a2347d
    OLD      547,267 faces   1,676 boundary edges   sha256(z, mask)[:16] = ffc48087214bb848

The 41 extra boundary edges in the old domain *are* the leak: the free-outflow face hydromt
cut across the Navesink. Verified stable across ``_template_sealed``, ``sealed_faber_waves``,
``sealed_faber_nowaves`` and ``sealed_galibier_waves`` (waves on and off, both engines), and
distinct from ``_template`` and all three ``phaselag_*`` arms.

``snapwave_mask`` is deliberately EXCLUDED from the hash — ``add_waves`` rewrites it per wave
config, so folding it in would make no-waves and waves arms of the same domain disagree.

Audit any directory::

    NJ_ROOT=$PWD PYTHONPATH=$PWD micromamba/envs/sfincs/bin/python -m nj_sfincs.premier \\
        experiments/sealed_faber_waves experiments/phaselag_battery
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xarray as xr

from nj_sfincs.config import ROOT

# ---------------------------------------------------------------------------
# The premier
# ---------------------------------------------------------------------------

#: The adopted premier (Workstream O, 2026-07-14). Gauge err -0.10 m vs the surveyed
#: crest; MOTF CSI 0.64, FAR 0.14. Faber engine + SnapWave + wind, on the sealed domain.
PREMIER_NAME = "sealed_faber_waves"

#: The ONLY template new experiments may be staged from.
SEALED_TEMPLATE = ROOT / "experiments" / "_template_sealed"

#: The pre-rebuild template: leaking Navesink, dammed Shark. Kept for provenance of the
#: historical runs that sit on it. Nothing new should ever be built here.
LEGACY_TEMPLATE = ROOT / "experiments" / "_template"

#: The frozen mesh the sealed domain was built from (NJ_FROZEN_MESH).
SEALED_FROZEN_MESH = "data/frozen_mesh_sealed"


@dataclass(frozen=True)
class DomainFingerprint:
    """Identity of the physical domain: the mesh and the bed, nothing else."""

    n_faces: int
    n_boundary_edges: int
    sha_z_mask: str

    def __str__(self) -> str:
        return (f"faces={self.n_faces} boundary_edges={self.n_boundary_edges} "
                f"sha(z,mask)={self.sha_z_mask}")


#: The sealed domain — region fixed at the leak's root + Shark eHydro inlet carve.
SEALED = DomainFingerprint(547408, 1635, "45f4f74ca9a2347d")

#: The pre-rebuild domain. Named so the error message can say *which* wrong domain it is.
LEGACY = DomainFingerprint(547267, 1676, "ffc48087214bb848")

KNOWN = {SEALED: "SEALED (leak fixed, Shark inlet carved)",
         LEGACY: "LEGACY pre-rebuild (Navesink LEAKING, Shark inlet DAMMED)"}

#: Shrewsbury tidal gauge, nudged 21 m into the channel so it samples water (zb -4.33 m)
#: rather than the +1.46 m bank it started on. The old template still has the bank point,
#: which silently returns NaN from every phase/tide metric. Checked to 0.1 m.
SHREWSBURY_OBS_XY = (587031.2, 4468837.4)
SHREWSBURY_OBS_NAME = "usgs_tidal_sea_bright"


class WrongDomainError(RuntimeError):
    """Raised when a model directory is not on the sealed domain."""


def domain_fingerprint(model_dir: Path | str) -> DomainFingerprint:
    """Fingerprint the domain in ``model_dir/sfincs.nc``."""
    path = Path(model_dir) / "sfincs.nc"
    if not path.exists():
        raise FileNotFoundError(f"no sfincs.nc in {model_dir}")
    with xr.open_dataset(path) as ds:
        h = hashlib.sha256()
        for var in ("z", "mask"):  # NOT snapwave_mask — rewritten per wave config
            h.update(var.encode())
            h.update(np.ascontiguousarray(ds[var].values).tobytes())
        return DomainFingerprint(int(ds.sizes["mesh2d_nFaces"]),
                                 int(ds.sizes["mesh2d_nBoundary_edges"]),
                                 h.hexdigest()[:16])


def is_sealed(model_dir: Path | str) -> bool:
    """True iff ``model_dir`` sits on the sealed domain. False if it has no sfincs.nc."""
    try:
        return domain_fingerprint(model_dir) == SEALED
    except FileNotFoundError:
        return False


def shrewsbury_obs_ok(model_dir: Path | str) -> bool | None:
    """True iff the Shrewsbury gauge is the in-channel point. None if no sfincs.obs."""
    obs = Path(model_dir) / "sfincs.obs"
    if not obs.exists():
        return None
    for line in obs.read_text().splitlines():
        if SHREWSBURY_OBS_NAME in line:
            parts = line.split()
            x, y = float(parts[0]), float(parts[1])
            return (abs(x - SHREWSBURY_OBS_XY[0]) < 0.1
                    and abs(y - SHREWSBURY_OBS_XY[1]) < 0.1)
    return False


def assert_sealed_domain(model_dir: Path | str, context: str = "") -> None:
    """Raise unless ``model_dir`` is on the sealed domain with the in-channel gauge.

    Call this wherever an experiment is staged or scored. A wrong domain is not a
    degraded result — it is a different planet, and its numbers must never reach a table.
    """
    where = f"{context}: " if context else ""
    got = domain_fingerprint(model_dir)
    if got != SEALED:
        raise WrongDomainError(
            f"{where}{model_dir} is NOT on the sealed domain.\n"
            f"    expected {SEALED}  <- {KNOWN[SEALED]}\n"
            f"    got      {got}"
            + (f"  <- {KNOWN[got]}" if got in KNOWN else "  <- UNRECOGNISED domain")
            + f"\n  Stage from {SEALED_TEMPLATE.name}, not {LEGACY_TEMPLATE.name}.\n"
              "  Results from a non-sealed domain are void: the Navesink leaks 92.5% of\n"
              "  estuary inflow and Shark River Inlet is dammed shut (never floods).\n"
              "  NB the OPEN COAST barely moves between domains — a healthy Sandy Hook\n"
              "  number is NOT evidence the domain is right."
        )
    if shrewsbury_obs_ok(model_dir) is False:
        raise WrongDomainError(
            f"{where}{model_dir} has the sealed domain but a STALE Shrewsbury gauge.\n"
            f"  '{SHREWSBURY_OBS_NAME}' must sit at {SHREWSBURY_OBS_XY} (in-channel,\n"
            "  zb -4.33 m). The old point sits on a +1.46 m bank that only wets during the\n"
            "  storm, so every pre-storm tide/phase metric silently returns NaN."
        )


def describe(model_dir: Path | str) -> str:
    """One-line audit of a model directory."""
    try:
        fp = domain_fingerprint(model_dir)
    except FileNotFoundError as e:
        return f"  {str(model_dir):44s} -- {e}"
    label = KNOWN.get(fp, "UNRECOGNISED")
    obs = shrewsbury_obs_ok(model_dir)
    obs_s = {True: "gauge in-channel", False: "GAUGE STALE", None: "no sfincs.obs"}[obs]
    flag = "OK  " if (fp == SEALED and obs is not False) else "BAD "
    return f"  {flag}{str(model_dir):44s} {label:52s} {obs_s}"


def _main(argv: list[str] | None = None) -> int:
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        args = sorted(str(p) for p in (ROOT / "experiments").glob("*")
                      if (p / "sfincs.nc").exists())
    print(f"PREMIER = {PREMIER_NAME}   template = {SEALED_TEMPLATE.name}")
    print(f"sealed domain: {SEALED}\n")
    bad = 0
    for a in args:
        line = describe(a)
        bad += line.lstrip().startswith("BAD")
        print(line)
    print(f"\n{len(args) - bad}/{len(args)} on the sealed domain")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(_main())
