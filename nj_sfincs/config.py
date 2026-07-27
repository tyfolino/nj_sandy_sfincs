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

    # ── SnapWave / SFINCS boundary DECOUPLING (2026-07-22) ───────────────────
    # X1 forced the wave solver onto the SFINCS mesh, which pinned the wave
    # boundary to the WATER-LEVEL boundary at BaseConfig.mask_zmin = -10 m. ERA5
    # is a deep-water source, so that pastes the open-ocean sea state onto the
    # 10 m contour with NO shelf transformation: at Sandy's peak ERA5 imposes
    # 7.66 m at 10 m depth while NDBC 44025 measured 8.79 m out in 36 m — i.e.
    # essentially the same number, 26 m of depth too shallow. CORA's SWAN, which
    # resolves the shelf, says 3.5-4.8 m there.
    #
    # Setting decouple_snapwave lets the SnapWave mask run out to
    # ``snapwave_mask_zmin`` while the SFINCS mask (and therefore the tide/surge
    # boundary) stays exactly where it is. This is seal-safe: premier.py
    # deliberately EXCLUDES snapwave_mask from the domain hash, so the sealed
    # fingerprint is unchanged and only one variable moves.
    #
    # Default False => every existing arm reproduces byte-for-byte.
    decouple_snapwave: bool = False
    snapwave_mask_zmin: float = -30.0  # SnapWave-only depth cut [m]
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

    ``legacy_name`` is the pre-2026-07-27 name of a renamed arm, kept so the old
    vocabulary stays greppable and so anything citing it (memory files, plan files,
    older report CSVs) can still be resolved. See ``docs/naming.md`` for the
    convention and the full mapping. Retired arms were NOT renamed — their value is
    archival — so their ``legacy_name`` is None.
    """

    name: str
    waves: WaveConfig
    description: str = ""
    waterlevel_geodataset: str | None = None
    legacy_name: str | None = None


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
    # ⛔ RETIRED 2026-07-26 — superseded by `tide-shift`. Run dir DELETED; the boundary
    # forcing file is preserved at archive/retired_composites/phaselag_composite/ and the
    # scored result at reports/phaselag_composite.csv. Do NOT re-run. See the v2 block below.
    "phaselag_composite": Experiment(
        "phaselag_composite",
        WaveConfig(use_waves=True, wave_wind=True, wave_igwaves=False, tune_physics=True),
        "⛔ RETIRED — NOAA harmonic tide + NTR (noaa_sandy_composite), 3 support points. "
        "Fixed the phase but over-forced the coast. Superseded by tide-shift.",
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
    #
    # ⛔ RETIRED 2026-07-26 — BOTH COMPOSITES ARE DEAD. `tide-shift` beats them on phase
    # AND level simultaneously (SH lag -0.1 vs 6.7 min; HWM bias 0.302 vs 0.500; RMSE 0.466 vs
    # 0.606; within-0.5 74% vs 63%; SSS 2258 3.626 vs 3.837 against an observed 3.465).
    # Two independent reasons not to build a v3:
    #  1. v2's node was NOT on the line after all. Reconstructing SFINCS' own interpolation with
    #     cadence held constant (2-node interpolant built from v2's OWN Battery+AC columns), the
    #     node contributes +0.012 m at its own latitude but +0.049 m at Shark River — it sits on
    #     the line at the surge PEAK, which is all that was ever verified, while its re-phased
    #     TIDE puts it off the line at other times, so the interpolated max between nodes rises.
    #     The off-line error is downstream of the node, not at it. (Cadence is also NOT the
    #     +0.008 m recorded from a single latitude: it is +0.050 m mid-coast and south.)
    #  2. The geographic argument for a Sandy Hook node is independently closed. CORA compared
    #     against a linear interpolation built from CORA at the same two points (so its own bias
    #     cancels): linear interpolation is NOT a meaningful error source on the open coast. The
    #     node has nothing left to do — phase is fixed without it, and the level is not broken.
    # A v3 could only tune the node's LEVEL to chase HWM bias, with no independent constraint on
    # what that level should be (the Sandy Hook gauge died before the crest) — i.e. calibration,
    # the same circularity that got NTR_DONOR_SCALE rejected. Run dir DELETED; boundary file at
    # archive/retired_composites/phaselag_composite_v2/, result at reports/phaselag_composite_v2.csv.
    "phaselag_composite_v2": Experiment(
        "phaselag_composite_v2",
        WaveConfig(use_waves=True, wave_wind=True, wave_igwaves=False, tune_physics=True),
        "⛔ RETIRED — local harmonic tide + interpolated NTR (noaa_sandy_composite_v2), "
        "3 support points. Superseded by tide-shift; do not re-run.",
        waterlevel_geodataset="noaa_sandy_composite_v2",
    ),
    # Phase fix done the way the plan's §5 actually specified — re-phase the EXISTING
    # north anchor rather than inserting a node. 2 support points, same coordinates and
    # same hourly grid as the premier; the Battery's TIDE is advanced +24 min to
    # open-coast phase and every NTR is left alone. Because no node is inserted, nothing
    # can sit off the Battery->AC surge line, which is exactly how v2 leaked +0.051 m
    # into a barrier-overwash threshold and lost the HWM score. One variable vs the
    # premier: tidal TIMING.
    "tide-shift": Experiment(
        "tide-shift",
        WaveConfig(use_waves=True, wave_wind=True, wave_igwaves=False, tune_physics=True),
        "Battery tide advanced +24 min to open-coast phase, 2 support points, NTR "
        "untouched. The phase-only experiment the composites were meant to be.",
        waterlevel_geodataset="noaa_sandy_phaseshift",
        legacy_name="phaselag_shift",
    ),
    # ── SnapWave boundary decoupling (2026-07-22) ────────────────────────────
    # The premier imposes ERA5 DEEP-WATER waves at the ~10 m contour, because X1
    # pinned the wave boundary to the water-level boundary and mask_zmin cuts at
    # -10 m. Evidence it is wrong, from observations rather than argument: at
    # 10-30 00:00 NDBC 44025 measured 8.79 m in 36 m of water while ERA5 imposes
    # 7.82 m in 10 m of water — the same sea state, 26 m too shallow. CORA's SWAN
    # (which resolves the shelf) says 5.07-6.02 m there.
    #
    # This arm gives SnapWave its own domain out to the 30 m contour (+129k of the
    # 141k already-meshed but inactive offshore cells) and leaves the SFINCS mask,
    # the surge boundary and the sealed fingerprint untouched. One variable vs
    # faber-waves-premier. Expected direction: less boundary wave energy -> less
    # setup -> HWM bias down from +0.32 (the premier is too WET, so this pushes
    # the right way, unlike phaselag_composite which overshot to +0.73).
    "wave-deep30": Experiment(
        "wave-deep30",
        WaveConfig(
            use_waves=True,
            wave_wind=True,
            wave_igwaves=False,
            tune_physics=True,
            decouple_snapwave=True,
            snapwave_mask_zmin=-30.0,
        ),
        "Premier wave knobs with the SnapWave domain decoupled from the SFINCS "
        "mask and pushed to the 30 m contour, so ERA5's deep-water Hs is applied "
        "where it is actually valid and SnapWave does the shelf transformation. "
        "Same lever as wave-bnd15/wave-bnd20 at a deeper value, but a DIFFERENT "
        "mechanism: those move support points inside the coupled mask, this one "
        "decouples the mask itself.",
        waterlevel_geodataset=None,
        legacy_name="snapwave_deep",
    ),
    # The 4th cell of the 2x2. The other three are already run: sealed_faber_waves
    # (neither), phaselag_composite_v2 (phase only), snapwave_deep (waves only).
    # The two knobs are orthogonal — `waves` touches only snapwave_mask, and
    # `waterlevel_geodataset` only sfincs_netbndbzsbzifile.nc — so this arm is
    # exactly their combination and the factorial closes.
    #
    # It exists because the phase result is NOT separable from the level. v2 kept
    # the phase win (SH 17.6 -> 6.7 min) but left HWM bias at +0.50 vs the premier's
    # +0.32, and since v2's boundary node sits ON the existing surge line by
    # construction, that residual is the re-phased tide aligning constructively with
    # the surge — not boundary geometry. The open question is whether the premier
    # was getting a defensible level for the WRONG reason: a late tide de-tuning an
    # over-energetic wave forcing. If snapwave_deep lowers the level, the phase fix
    # may come free here. Only this cell can show the interaction; the three
    # existing runs cannot.
    #
    # Carries the same 6-min-vs-hourly forcing cadence lift as the other composite
    # arms (+0.021 m at Battery, +0.038 m at AC), so the clean single-variable
    # comparison for phase is THIS vs snapwave_deep, not vs the premier.
    "snapwave_deep_composite_v2": Experiment(
        "snapwave_deep_composite_v2",
        WaveConfig(
            use_waves=True,
            wave_wind=True,
            wave_igwaves=False,
            tune_physics=True,
            decouple_snapwave=True,
            snapwave_mask_zmin=-30.0,
        ),
        "⛔ SUPERSEDED (v2 retired 2026-07-26) — SnapWave decoupled to 30 m AND the "
        "composite_v2 boundary tide. Retained as the 2x2 interaction evidence; use "
        "snapwave_deep_phaseshift instead.",
        waterlevel_geodataset="noaa_sandy_composite_v2",
    ),
    # ── The production candidate (2026-07-26) ────────────────────────────────
    # snapwave_deep's wave knobs + phaselag_shift's boundary forcing. Both knobs
    # are orthogonal in this config — `waves` touches only snapwave_mask, and
    # `waterlevel_geodataset` only sfincs_netbndbzsbzifile.nc — so this arm is
    # exactly their union.
    #
    # NOTE `phaselag_shift` already carries snapwave_mask_zmin=-30.0, but with
    # decouple_snapwave=False that value is INERT: the flag is what activates it.
    # So the two parents differ in exactly one field each and this is their union.
    #
    # Why it is worth the 3 h. Each parent beats the premier on its own axis for a
    # reason that survives independently of the HWM score:
    #   * phaselag_shift  — Sandy Hook lag 17.6 -> -0.1 min at NO level cost
    #     (bias 0.318 -> 0.302). The +24 min Battery phase is an interpolation
    #     artifact, measured at the source, not a fitted correction.
    #   * snapwave_deep   — the premier imposes Hs 8.624 m at the ~10 m contour,
    #     ABOVE the depth-limited breaking cap (gamma=0.78 => ~7.8 m in 10 m of
    #     water). That BC is physically inadmissible. This arm imposes the SAME
    #     8.624 m at ~30 m (gamma 0.29) where it is valid; faces past breaking
    #     drop 16,532 -> 13,651 (-17%).
    # So this run is mainly a CONFIRMATION that the two do not interfere, not a
    # search for a large gain. Expect HWM bias ~0.27 if they compose; that is
    # success. Neither knob addresses the +0.32 m wet bias and this one will not
    # either.
    #
    # Do NOT read a null result as "the phase fix costs something": the 2x2 already
    # showed deep+composite_v2 kept v2's ~+0.14 penalty, but that was a verdict on
    # v2's INSERTED NODE (off the surge line by +0.049 m at Shark River), and this
    # arm has no node. Interaction is nonetheless not guaranteed to be additive.
    #
    # Runtime: SnapWave is 90-95% of the cost and scales PER-ITERATION with the
    # decoupled domain (6.18 s/iter vs the premier's 3.95). Both deep runs took
    # 3:03-3:05 => submit with extra_args=['--time=06:00:00'], the 3 h batch
    # default would kill it.
    "wave-deep30+tide-shift": Experiment(
        "wave-deep30+tide-shift",
        WaveConfig(
            use_waves=True,
            wave_wind=True,
            wave_igwaves=False,
            tune_physics=True,
            decouple_snapwave=True,
            snapwave_mask_zmin=-30.0,
        ),
        "PRODUCTION CANDIDATE: SnapWave decoupled to the 30 m contour (admissible "
        "wave BC) AND the Battery tide advanced +24 min at 2 support points "
        "(no inserted node). The union of the two best arms. SCORED 2026-07-27: "
        "bias 0.273 / RMSE 0.449, the best level arm; the two knobs are ~additive "
        "(RMSE 100%). But CSI 0.706 -> 0.684 and one wet HWM goes dry -- best on "
        "level, worst on extent. See docs/naming.md.",
        waterlevel_geodataset="noaa_sandy_phaseshift",
        legacy_name="snapwave_deep_phaseshift",
    ),
}


def with_window(base: BaseConfig, tstop: datetime) -> BaseConfig:
    """Return a copy of ``base`` with a shorter run window (for smoke tests)."""
    return replace(base, tstop=tstop)
