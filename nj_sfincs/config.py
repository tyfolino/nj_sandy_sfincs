"""Configuration for the NJ Sandy SFINCS build + wave-sensitivity experiments.

This replaces the single ``CONFIG`` dict in notebooks/sfincs-nj-sandy.ipynb
(cell ``f4dff70f``) with two frozen dataclasses:

* ``BaseConfig`` — everything that is INVARIANT across the wave experiments
  (paths, grid, subgrid/mask, elevation merge, simulation window, surge
  boundary). The values are the exact ones from the notebook.
* ``WaveConfig`` — the ONLY thing that varies between experiments: the SnapWave
  knobs (wind-wave growth, infragravity waves, the ocean-side wavemaker, and
  Tim Leijnse's SnapWave physics parameters).

``EXPERIMENTS`` is the preset library the runner sweeps over.

Paths resolve against the repo root, overridable with ``NJ_ROOT`` — the same
idiom the ``scripts/*.py`` use — so the CLI and the notebook work regardless of
CWD.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

# Repo root (…/nj_sandy_sfincs), overridable via NJ_ROOT. nj_sfincs/ lives one
# level below the root, so parents[1] is the root.
ROOT = Path(os.environ.get("NJ_ROOT", Path(__file__).resolve().parents[1]))
DATA = ROOT / "data"

# Elevation merge, top → bottom; first dataset with data wins. Verbatim from the
# notebook. Kept as a tuple (dataclass forbids mutable list/dict defaults; a
# tuple of dicts is fine). See data/data_catalog.yml for per-layer provenance.
DEFAULT_ELEVATION_LIST: tuple[dict, ...] = (
    {"elevation": "shrewsbury_ehydro_2015"},  # carve Rumson–Sea Bright bridge dam
    {"elevation": "usace_nj_2010"},  # 1 m PRE-Sandy topobathy (top)
    {"elevation": "cudem_nj"},  # 3 m fill: inlets + shelf + Raritan Bay
    {"elevation": "nj_10ft_dem", "zmin": 0.001},  # 3 m fill: inland land
    {"elevation": "gmrt_nj"},  # ~50 m GMRT offshore tail
)


@dataclass(frozen=True)
class BaseConfig:
    """Forcing-independent build parameters (shared by every experiment)."""

    # ── Paths ────────────────────────────────────────────────────────────────
    data_catalog: Path = DATA / "data_catalog.yml"
    region: Path = DATA / "region.geojson"
    refinement: Path = DATA / "quadtree" / "refinement_polygons.geojson"
    reclass_table: Path = DATA / "roughness" / "NLCD_CONUS_mapping.csv"
    container_sif: Path = ROOT / "sfincs-desktop.sif"

    # Reproducibility: if set to a pre-built static-mesh dir, build_static COPIES
    # it instead of rebuilding the quadtree (which is environment-sensitive — two
    # builds can differ by ~18 cells → CSI ±0.04). Frozen 2026-07-03 via
    # scripts/freeze_mesh.py (547,267-cell deterministic grid) so the harness AND
    # notebook share one identical mesh. Set to None to build fresh each time.
    # Override the dir via NJ_FROZEN_MESH (relative to ROOT or absolute) to A/B an
    # alternate mesh, e.g. NJ_FROZEN_MESH=data/frozen_mesh_L4 for the narrows-L4 run.
    frozen_mesh: Path | None = (
        (ROOT / os.environ["NJ_FROZEN_MESH"]) if os.environ.get("NJ_FROZEN_MESH")
        else DATA / "frozen_mesh"
    )

    # ── Grid ─────────────────────────────────────────────────────────────────
    crs: str = "utm"  # let hydromt pick the UTM zone (→ 32618 here)
    base_res: int = 200  # level-0 cell size [m]; refined down to ~25 m
    rotated: bool = True  # rotate the grid to hug the coastline

    # ── Subgrid / mask ───────────────────────────────────────────────────────
    nr_subgrid_pixels: int = 8  # subgrid sampling per cell edge
    mask_zmin: float = -10.0  # cells with z >= this are active (NJ shelf)

    # ── Elevation merge ──────────────────────────────────────────────────────
    elevation_list: tuple[dict, ...] = DEFAULT_ELEVATION_LIST

    # ── Simulation window (Hurricane Sandy) ──────────────────────────────────
    tref: datetime = datetime(2012, 10, 28)
    tstart: datetime = datetime(2012, 10, 28)
    tstop: datetime = datetime(2012, 10, 31)
    latitude: float = 40.32  # for Coriolis (domain-mean lat)

    # ── Surge boundary (observed NOAA CO-OPS gauges) ─────────────────────────
    waterlevel_geodataset: str = "noaa_sandy_nj"
    waterlevel_buffer: int = 100_000  # m; reach down to Atlantic City gauge

    @property
    def data_libs(self) -> list[str]:
        return [str(self.data_catalog)]

    def elevation(self) -> list[dict]:
        """A fresh mutable copy of the elevation list for the hydromt API."""
        return [dict(d) for d in self.elevation_list]


@dataclass(frozen=True)
class WaveConfig:
    """The SnapWave knobs — the only thing that varies between experiments.

    Atlantic swell cannot diffract into the Sandy Hook Bay lee, so bay waves
    have to be *generated* there: via local wind-wave growth (``wave_wind``) or
    injected as infragravity energy (``wave_igwaves`` / ``wavemaker``). Those are
    the levers this project sweeps.
    """

    use_waves: bool = False
    wave_wind: bool = False  # local wind-wave growth (routes model wind; sector→360)
    wave_igwaves: bool = False  # infragravity balance (long-period back-bay runup)
    wavemaker: bool = False  # inject waves along the ocean-side wavemaker line

    # Wave boundary forcing (ERA5-coupled support points)
    wave_geodataset: str = "era5_waves_nj"
    wave_era5_node: tuple[float, float] = (-74.0, 40.0)  # nearest valid offshore node
    wave_n_support: int = 7  # alongshore support points on the boundary
    wavemaker_line: Path = DATA / "wavemakers" / "wavemaker_line.geojson"
    dtwave: float = 1800.0  # SnapWave coupling interval [s]

    # Tim Leijnse's SnapWave physics parameters. Only emitted when
    # ``tune_physics`` is True — the plain wind-wave baseline deliberately SKIPS
    # them (a 2026-06-01 test showed the breaking block worsened surf-zone Hm0),
    # so leaving tune_physics=False reproduces the current notebook exactly.
    tune_physics: bool = False
    snapwave_alpha: float = 1.0  # Baldock breaking alpha
    snapwave_gamma: float = 0.78  # Baldock breaking gamma (breaking depth)
    snapwave_hmin: float = 0.01  # min water depth for SnapWave [m]
    snapwave_dtheta: int = 5  # direction bin size [deg]
    snapwave_fw: float = 0.02  # wave bottom-friction factor
    snapwave_niter: int = 100  # max iterations (÷4 internal sweeps)
    storefw: int = 1  # store extra wave output

    def sector(self) -> int:
        """Directional sector: full circle when wind can grow waves any way."""
        return 360 if self.wave_wind else 180


@dataclass(frozen=True)
class Experiment:
    """A named experiment = a label + the wave knobs to apply."""

    name: str
    waves: WaveConfig
    description: str = ""


# ── The experiment library the runner sweeps over ────────────────────────────
# Reference points first, then the wave knobs turned on one (group) at a time.
EXPERIMENTS: dict[str, Experiment] = {
    "baseline_no_waves": Experiment(
        "baseline_no_waves",
        WaveConfig(use_waves=False),
        "Surge + meteo + fluvial only — the clean still-water spine.",
    ),
    "wind_waves": Experiment(
        "wind_waves",
        WaveConfig(use_waves=True, wave_wind=True, wave_igwaves=False),
        "Current baseline: SnapWave incident + local wind-wave growth, IG off, "
        "default physics (matches the notebook).",
    ),
    "snapwave_tuned": Experiment(
        "snapwave_tuned",
        WaveConfig(
            use_waves=True, wave_wind=True, wave_igwaves=False, tune_physics=True
        ),
        "wind_waves + Tim's SnapWave physics (gamma=0.78, alpha=1.0, fw=0.02, "
        "hmin=0.01, dtheta=5, niter=100).",
    ),
    "snapwave_tuned_wavemaker": Experiment(
        "snapwave_tuned_wavemaker",
        WaveConfig(
            use_waves=True,
            wave_wind=True,
            wave_igwaves=False,
            wavemaker=True,
            tune_physics=True,
        ),
        "snapwave_tuned + an ocean-side wavemaker, IG off — the premier config "
        "with the forcing upper-bound bracket (vs plain snapwave_tuned).",
    ),
    "igwaves": Experiment(
        "igwaves",
        WaveConfig(
            use_waves=True, wave_wind=False, wave_igwaves=True, tune_physics=True
        ),
        "Infragravity waves alone (no wind growth) — long-period energy toward "
        "the back bays.",
    ),
    "igwaves_wind": Experiment(
        "igwaves_wind",
        WaveConfig(
            use_waves=True, wave_wind=True, wave_igwaves=True, tune_physics=True
        ),
        "IG + wind-wave growth — the combined path to fill the Sandy Hook Bay lee.",
    ),
    "wavemaker": Experiment(
        "wavemaker",
        WaveConfig(
            use_waves=True,
            wave_wind=True,
            wave_igwaves=True,
            wavemaker=True,
            tune_physics=True,
        ),
        "IG + wind + an ocean-side wavemaker injecting IG energy along the "
        "open-coast line (kept ocean-side; a wavemaker inside the bay over-forces).",
    ),
}


def with_window(base: BaseConfig, tstop: datetime) -> BaseConfig:
    """Return a copy of ``base`` with a shorter run window (for smoke tests)."""
    return replace(base, tstop=tstop)
