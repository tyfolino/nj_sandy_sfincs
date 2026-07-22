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
# NOTE ON ORDER (2026-07-14). The eHydro tiers MUST outrank `usace_nj_2010`, and that is the
# whole point of them. The 2010 lidar is green (bathymetric) and returns the real bed in clear
# shallow water — but in deep or turbid water it fails to penetrate and returns the WATER
# SURFACE (~0 to +2 m), which is indistinguishable from land. Ranked first, those bogus returns
# shadow CUDEM's correct bed and SEAL THE CHANNEL SHUT. That is what dammed Shark River Inlet
# (real bed −4.6 to −10.8 m; lidar +0.4 to +2.2 m) and left the whole Shark estuary at exactly
# +0.00 m — never flooding — through Hurricane Sandy. An eHydro survey is a boat with an echo
# sounder: the only source here that measures the bed UNDER the water, so it goes on top.
DEFAULT_ELEVATION_LIST: tuple[dict, ...] = (
    {"elevation": "ehydro_nj"},  # carve Shark River Inlet (lidar paved it — see scripts/audit_paved_channels.py)
    {"elevation": "shrewsbury_ehydro_2015"},  # carve Rumson–Sea Bright bridge dam
    {"elevation": "usace_nj_2010"},  # 1 m PRE-Sandy topobathy (fails in deep/turbid water)
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
    # Quadtree refinement. Override with NJ_REFINEMENT (path relative to ROOT).
    #
    # ⚠️ `refinement_polygons.geojson` carries `shrewsbury_l4` + `navesink_l4` at
    # refinement_level 4 (12.5 m), which were STAGED AFTER data/frozen_mesh was built
    # (2026-07-03, max level 25 m). So a rebuild with it silently upgrades the estuary to
    # 12.5 m: +123,691 faces, +33% active cells, +33% runtime on every run thereafter —
    # a third change riding along with any other rebuild, and one that breaks comparability
    # with every 25 m run in the campaign. L4 was measured as a NULL lever (the 12.5 m
    # rebuild, job 57864095, moved the Shrewsbury gauge by +0.04 m).
    #
    # `refinement_polygons_25m.geojson` is the same file WITHOUT those two polygons, so the
    # 2026-07-14 region+eHydro rebuild changes only what it means to change (+1,007 faces).
    refinement: Path = (
        (ROOT / os.environ["NJ_REFINEMENT"]) if os.environ.get("NJ_REFINEMENT")
        else DATA / "quadtree" / "refinement_polygons_25m.geojson"
    )
    reclass_table: Path = DATA / "roughness" / "NLCD_CONUS_mapping.csv"
    container_sif: Path = ROOT / "sfincs-desktop.sif"

    # Reproducibility: if set to a pre-built static-mesh dir, build_static COPIES
    # it instead of rebuilding the quadtree (which is environment-sensitive — two
    # builds can differ by ~18 cells → CSI ±0.04). Set to None to build fresh each time.
    # Override via NJ_FROZEN_MESH (relative to ROOT or absolute) to A/B an alternate
    # mesh, e.g. NJ_FROZEN_MESH=data/frozen_mesh_L4 for the narrows-L4 run.
    #
    # ⚠️ DEFAULT CHANGED 2026-07-21: `data/frozen_mesh` → `data/frozen_mesh_sealed`.
    # The old default is the PRE-REBUILD mesh (547,267 cells) — the one whose region
    # polygon chops the Navesink mid-channel, so hydromt hangs a free-outflow BC on a
    # 5 m-deep tidal cross-section and the estuary drains 92.5% of its inflow, and whose
    # Shark River Inlet is dammed shut. The sealed mesh (547,408 cells, 1,635 boundary
    # edges vs the leaking 1,676) is what the adopted premier stands on.
    #
    # This default was a loaded gun: `_template_sealed` was only sealed because
    # scripts/setup_sealed_premier.py sets NJ_FROZEN_MESH explicitly, so ANY build that
    # forgot the env var — a notebook run, a plain build_template — silently produced a
    # leaking domain. That is how `model/` (built 2026-07-03) ended up leaking, and it is
    # the same class of failure that voided the 2026-07-20 phase-lag A/B.
    # See nj_sfincs/premier.py, which now asserts the resulting domain either way.
    frozen_mesh: Path | None = (
        (ROOT / os.environ["NJ_FROZEN_MESH"]) if os.environ.get("NJ_FROZEN_MESH")
        else DATA / "frozen_mesh_sealed"
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
    """A named experiment = a label + the wave knobs to apply.

    ``waterlevel_geodataset`` optionally OVERRIDES the base water-level forcing
    source for this experiment only (default ``None`` = inherit ``BaseConfig``'s
    Battery-anchored ``noaa_sandy_nj``). The override is applied on the copied
    template in ``run_experiments.prepare_experiment`` by re-running
    ``sf.water_level.create(..., merge=False)`` — everything else (leak-fixed
    mask, subgrid, waves) is identical, so a set of experiments differing only in
    this field is a clean forcing A/B. Faber vs Galibier is NOT a knob here: it is
    the SFINCS container (``sfincs-desktop.sif`` = Faber, the default
    ``BaseConfig.container_sif``), so every run below is Faber.
    """

    name: str
    waves: WaveConfig
    description: str = ""
    waterlevel_geodataset: str | None = None


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
    # ── Boundary re-phasing A/B (2026-07-20) ─────────────────────────────────
    # The modeled pre-storm tide peaks late (Sandy Hook +18 min) because the
    # north is interpolated from the harbor-phase Battery. These share the sealed
    # premier's wave knobs (== snapwave_tuned: Faber SIF + wind waves + Tim's
    # physics) and differ ONLY in the water-level forcing source, so gauge phase
    # lag is compared on an otherwise-identical model. See plan / project memory.
    "phaselag_battery": Experiment(
        "phaselag_battery",
        WaveConfig(use_waves=True, wave_wind=True, wave_igwaves=False, tune_physics=True),
        "Baseline arm: premier wave knobs, default NOAA Battery-anchored forcing "
        "(noaa_sandy_nj). The +18 min-late reference to beat.",
        waterlevel_geodataset=None,
    ),
    "phaselag_shblend": Experiment(
        "phaselag_shblend",
        WaveConfig(use_waves=True, wave_wind=True, wave_igwaves=False, tune_physics=True),
        "Sandy Hook tidal-window blend: real SH tide → Battery surge crest "
        "(noaa_sandy_nj_shblend). Targets the +18 min coastal baseline.",
        waterlevel_geodataset="noaa_sandy_nj_shblend",
    ),
    # ⛔ RETIRED 2026-07-21. GTSM's TIDE is ~34% under-amplitude everywhere in this region
    # (x0.66 vs NOAA harmonics at 6 stations spanning open coast, harbour and a resonant
    # sound), so its interior peaks are an amplitude artifact and say nothing about phase.
    # Kept only so the historical arm remains reproducible. Superseded by phaselag_composite.
    "phaselag_gtsm": Experiment(
        "phaselag_gtsm",
        WaveConfig(use_waves=True, wave_wind=True, wave_igwaves=False, tune_physics=True),
        "RETIRED — GTSM-ERA5 global tide+surge (gtsm_sandy). Tide is ~34% low across "
        "the whole region; do not read its crest as a result.",
        waterlevel_geodataset="gtsm_sandy",
    ),
    # ⭐ The adopted forcing route: tide/surge decomposition (Wahl/Gloucester City NJ,
    # Orton/Hoboken). Sandy Hook returns as a support point with its OWN harmonic tide —
    # predictions don't need the gauge to have survived — and borrows the Battery's NTR
    # (corr 0.996, zero lag) across the mid-storm gap. Validated vs SH 6-min obs:
    # RMSE 0.103 m and pre-storm phase error 0 min, against 0.147 m / 24 min for the
    # Battery-anchored baseline. No extrapolation anywhere.
    "phaselag_composite": Experiment(
        "phaselag_composite",
        WaveConfig(use_waves=True, wave_wind=True, wave_igwaves=False, tune_physics=True),
        "NOAA harmonic tide + non-tidal residual (noaa_sandy_composite). Fixes the "
        "boundary tide phase without touching the surge field — one variable changed.",
        waterlevel_geodataset="noaa_sandy_composite",
    ),
    # ⭐ v2 (2026-07-22) — the arm that actually isolates PHASE from LEVEL.
    # v1 above won on phase (SH 17.6 -> 7.8 min, Shrewsbury 36.9 -> 25.5) but lost on level
    # (HWM bias +0.32 -> +0.73 m, within-0.5 m 74% -> 21%, SSS 2258 3.65 -> 4.01 m vs an
    # observed 3.465) because it gave Sandy Hook the Battery's NTR UNSCALED — a surge peak
    # amplified by the NY Harbor funnel, inserted into the Battery->AC baseline.
    # v2 keeps the local harmonic TIDE (sharp phase gradients => must be local) but takes the
    # NTR as the Battery->AC interpolant (spatially smooth => interpolate). The node then lies
    # ON the existing surge line: 3.143 m vs the 3.146 m the premier's 2-node line already
    # implied there (-0.004 m), where v1 sat at +0.243 m. Source phase still -3.3 min vs the
    # premier's +21.1. No fitted parameter anywhere.
    "phaselag_composite_v2": Experiment(
        "phaselag_composite_v2",
        WaveConfig(use_waves=True, wave_wind=True, wave_igwaves=False, tune_physics=True),
        "Local harmonic tide + spatially interpolated NTR (noaa_sandy_composite_v2). "
        "Re-phases the boundary tide while leaving the surge field as the premier had it.",
        waterlevel_geodataset="noaa_sandy_composite_v2",
    ),
}


def with_window(base: BaseConfig, tstop: datetime) -> BaseConfig:
    """Return a copy of ``base`` with a shorter run window (for smoke tests)."""
    return replace(base, tstop=tstop)
