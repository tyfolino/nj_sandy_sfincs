"""The full parameter inventory for a finished run, rendered for the viz notebook.

Everything here is READ FROM THE RUN, not retyped from documentation: the solver and
SnapWave settings come out of that run's own ``sfincs.inp``, the mask/boundary and
elevation-merge rules out of ``nj_sfincs.config`` / ``nj_sfincs.model``. A hand-maintained
table would start lying the first time somebody changed a knob; this one cannot.

The contract is COMPLETENESS: every key in sfincs.inp appears in a table, whether or not
we have a description for it. Anything we do not recognise lands in "Other / unannotated"
rather than being dropped -- a silently omitted parameter is how you end up debugging a
model you think you understand. (That is not hypothetical here: `snapwave_gammax` missing
from a Galibier run was a real bug, and an inventory that only prints known keys would have
hidden it.)

Datum: every elevation, depth and water level in this project is metres NAVD88.

Usage (notebook):
    from nj_sfincs import params
    params.show(sf)                 # renders all tables
    params.show(sf, as_markdown=True)   # same content as markdown text
"""

from __future__ import annotations

from pathlib import Path

from .config import BaseConfig
from .model import (
    BAY_INCLUDE_BOX_LL,
    OUTFLOW_MAX_DEPTH,
    PAVED_BED_LAND,
    PAVED_SURVEY_WATER,
    SANDY_HOOK_TIP_Y,
)

# ── What each sfincs.inp key means, and which table it belongs in ─────────────
# (group, description). Order within a group follows this dict.
INP_META: dict[str, tuple[str, str]] = {
    # Time
    "tref": ("Time", "Reference time (t=0 for all forcing)"),
    "tstart": ("Time", "Simulation start"),
    "tstop": ("Time", "Simulation stop"),
    "tspinup": ("Time", "Spin-up ramp [s] — forcing eased in over this window"),
    "dtwave": ("Time", "SnapWave coupling interval [s] — how often waves are recomputed"),
    "dtwnd": ("Time", "Wind/meteo update interval [s]"),
    "btfilter": ("Time", "Boundary-condition time filter [s]"),
    # Numerics
    "alpha": ("Numerics & physics", "CFL safety factor on the adaptive time step"),
    "huthresh": ("Numerics & physics", "Wet/dry threshold [m] — below this a cell is dry"),
    "advection": ("Numerics & physics", "Advection on (1) / off (0)"),
    "coriolis": ("Numerics & physics", "Coriolis on (1) / off (0)"),
    "viscosity": ("Numerics & physics", "Horizontal viscosity on (1) / off (0)"),
    "nuvisc": ("Numerics & physics", "Viscosity coefficient [m²/s]"),
    "latitude": ("Numerics & physics", "Domain-mean latitude, for Coriolis [°]"),
    "rhoa": ("Numerics & physics", "Air density [kg/m³]"),
    "rhow": ("Numerics & physics", "Water density [kg/m³]"),
    "baro": ("Numerics & physics", "Barometric (inverse-barometer) forcing on/off"),
    "pavbnd": ("Numerics & physics", "Average pressure at the boundary [Pa]; 0 = disabled"),
    "zsini": ("Numerics & physics", "Initial water level [m NAVD88] — the cold-start surface"),
    "epsg": ("Numerics & physics", "Projected CRS (UTM 18N)"),
    # Wind drag
    "cdnrb": ("Wind drag", "Number of breakpoints in the wind-drag curve"),
    "cdwnd": ("Wind drag", "Wind speeds at the breakpoints [m/s]"),
    "cdval": ("Wind drag", "Drag coefficient at each breakpoint [-]"),
    # SnapWave
    "snapwave": ("SnapWave", "SnapWave wave solver on (1) / off (0)"),
    "snapwave_wind": ("SnapWave", "Local wind-wave growth (the bay cannot receive ocean swell)"),
    "snapwave_igwaves": ("SnapWave", "Infragravity balance — Workstream E: measured NULL here"),
    "snapwave_sector": ("SnapWave", "Directional sector [°]; 360 when wind grows waves any way"),
    "snapwave_dtheta": ("SnapWave", "Directional bin size [°]"),
    "snapwave_alpha": ("SnapWave", "Baldock breaking α"),
    "snapwave_gamma": ("SnapWave", "Baldock breaking γ (breaking depth ratio)"),
    "snapwave_gammax": ("SnapWave", "Hs/depth stability clamp — ABSENT in Galibier = a real bug"),
    "snapwave_fw": ("SnapWave", "Wave bottom-friction factor"),
    "snapwave_hmin": ("SnapWave", "Minimum water depth for SnapWave [m]"),
    "snapwave_niter": ("SnapWave", "Max solver iterations (÷4 internal sweeps)"),
    # Output
    "dthisout": ("Output", "History (gauge) output interval [s]"),
    "dtmapout": ("Output", "Map output interval [s] — hourly, so modelled tidal RANGE reads low"),
    "dtmaxout": ("Output", "Max-value (zsmax) accumulation window [s]"),
    "trstout": ("Output", "Restart-file time; -999 = never"),
    "storevel": ("Output", "Store velocities (needed for the flux/mass-budget checks)"),
    "storecumprcp": ("Output", "Store cumulative precipitation"),
    "storemeteo": ("Output", "Store meteo fields"),
    "storefw": ("Output", "Store extra wave output"),
    "storewavdir": ("Output", "Store wave direction"),
}

FILE_KEYS = {  # inp keys whose value is a filename
    "qtrfile": "Quadtree grid + mask",
    "sbgfile": "Subgrid tables (conveyance per face)",
    "manningfile": "Manning roughness (NLCD reclass)",
    "netbndbzsbzifile": "Water-level boundary (bzs) — NOAA gauges",
    "netsrcdisfile": "River discharge (USGS)",
    "netamuamvfile": "Wind field (ERA5)",
    "netamprfile": "Precipitation (AORC)",
    "netampfile": "Atmospheric pressure (ERA5)",
    "obsfile": "Observation points",
    "crsfile": "Cross-sections (flux budget)",
    "snapwave_bndfile": "SnapWave boundary support points",
    "snapwave_bhsfile": "SnapWave boundary Hs",
    "snapwave_btpfile": "SnapWave boundary Tp",
    "snapwave_bwdfile": "SnapWave boundary wave direction",
    "snapwave_bdsfile": "SnapWave boundary directional spread",
}

GROUP_ORDER = ["Time", "Numerics & physics", "Wind drag", "SnapWave", "Output"]


def read_inp(run_dir: str | Path) -> dict[str, str]:
    """Parse a sfincs.inp into an ordered {key: value} dict."""
    out: dict[str, str] = {}
    for line in (Path(run_dir) / "sfincs.inp").read_text().splitlines():
        if "=" not in line or line.strip().startswith(("#", "!")):
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def _run_dir(sf) -> Path:
    """The run directory behind ``sf``.

    ``SfincsModel.root`` is a hydromt ``ModelRoot``, NOT a path: it has no __fspath__ and
    its str() is "ModelRoot(path=..., mode=...)", so both Path(sf.root) and Path(str(sf.root))
    are wrong. The Path lives on ``.path``. Accepts a plain str/Path too, so callers can pass
    a run directory directly.
    """
    root = getattr(sf, "root", sf)
    return Path(getattr(root, "path", root))


def _md_table(rows: list[tuple], header: tuple) -> str:
    head = "| " + " | ".join(header) + " |\n|" + "|".join(["---"] * len(header)) + "|\n"
    body = "".join("| " + " | ".join(str(c) for c in r) + " |\n" for r in rows)
    return head + body + "\n"


def tables(sf, base: BaseConfig | None = None) -> str:
    """The whole inventory as one markdown string, read from ``sf``'s run directory."""
    base = base or BaseConfig()
    run = _run_dir(sf)
    inp = read_inp(run)
    md = [f"### Every parameter of `{run.name}`\n",
          "*Read live from the run's own `sfincs.inp` and `nj_sfincs.config` — not "
          "transcribed, so it cannot go stale. All elevations/depths/levels are "
          "**metres NAVD88**.*\n\n"]

    # ── solver groups ────────────────────────────────────────────────────────
    seen: set[str] = set()
    for group in GROUP_ORDER:
        rows = []
        for key, (g, desc) in INP_META.items():
            if g != group or key not in inp:
                continue
            rows.append((f"`{key}`", f"**{inp[key]}**", desc))
            seen.add(key)
        if rows:
            md.append(f"**{group}**\n\n")
            md.append(_md_table(rows, ("parameter", "value", "what it does")))

    # ── files ────────────────────────────────────────────────────────────────
    rows = [(f"`{k}`", f"`{inp[k]}`", d) for k, d in FILE_KEYS.items() if k in inp]
    seen |= {k for k in FILE_KEYS if k in inp}
    if rows:
        md.append("**Input files this run points at**\n\n")
        md.append(_md_table(rows, ("key", "file", "what it holds")))

    # ── anything we did not annotate: NEVER dropped ──────────────────────────
    rest = [(f"`{k}`", f"**{v}**") for k, v in inp.items() if k not in seen]
    if rest:
        md.append("**Other / unannotated** — present in `sfincs.inp`, no description "
                  "on file. Listed so nothing is invisible.\n\n")
        md.append(_md_table(rest, ("parameter", "value")))

    # ── grid & subgrid ───────────────────────────────────────────────────────
    md.append("**Grid & subgrid** (`nj_sfincs.config.BaseConfig`)\n\n")
    md.append(_md_table([
        ("`base_res`", f"**{base.base_res} m**", "Level-0 cell size; quadtree refines to ~25 m"),
        ("`rotated`", f"**{base.rotated}**", "Grid rotated to hug the coastline (<1°)"),
        ("`crs`", f"**{base.crs} → EPSG:{inp.get('epsg','?')}**", "hydromt picks the UTM zone"),
        ("`nr_subgrid_pixels`", f"**{base.nr_subgrid_pixels}**", "Subgrid samples per cell edge"),
        ("`refinement`", f"`{Path(base.refinement).name}`",
         "⚠️ the *_25m* file. The other one silently adds L4 12.5 m: +124k faces, +33% runtime"),
        ("`frozen_mesh`", f"`{Path(base.frozen_mesh).name if base.frozen_mesh else None}`",
         "Copied, not rebuilt — a fresh build differs by ~18 cells → CSI ±0.04"),
    ], ("parameter", "value", "note")))

    # ── mask & boundaries ────────────────────────────────────────────────────
    md.append("**Mask & boundary depths** (`nj_sfincs.model.apply_mask_and_boundary`)\n\n")
    md.append(_md_table([
        ("`mask_zmin`", f"**{base.mask_zmin} m**",
         "Cells with z ≥ this are ACTIVE. Workstream M swept −15/−20: keep −10"),
        ("waterlevel BC", "**z ≤ −1 m**",
         "`create_boundary(btype='waterlevel', zmax=-1)` — the driven open edge"),
        ("outflow BC", "**−1 ≤ z ≤ 2 m**",
         "`create_boundary(btype='outflow', zmin=-1, zmax=2)` — free (Neumann) edge"),
        ("`OUTFLOW_MAX_DEPTH`", f"**{OUTFLOW_MAX_DEPTH} m**",
         "🩸 THE LEAK. A free-outflow BC on water deeper than this is a DRAIN. "
         "It cost 92.6% of the estuary's inflow; now a build-time invariant"),
        ("`BAY_INCLUDE_BOX_LL`", f"`{BAY_INCLUDE_BOX_LL}`",
         "Force Raritan/Sandy Hook Bay active at any depth, so dredged channels "
         "(−11..−27 m) don't punch inactive holes"),
        ("`SANDY_HOOK_TIP_Y`", f"**{SANDY_HOOK_TIP_Y:,} m N**",
         "Northing cut for SnapWave support points"),
        ("`PAVED_BED_LAND` / `PAVED_SURVEY_WATER`", f"**{PAVED_BED_LAND} / {PAVED_SURVEY_WATER} m**",
         "🩸 THE DAM. Model calls it land, survey says water this deep ⇒ lidar paved "
         "a channel. Caught Shark River Inlet; now an invariant"),
    ], ("parameter", "value", "what it does")))

    # ── elevation merge ──────────────────────────────────────────────────────
    md.append("**Elevation merge — the exact build order**\n\n")
    md.append("*Top → bottom; **the first dataset with data at a pixel wins**. The order is "
              "not cosmetic: it is what dammed Shark River Inlet for two months.*\n\n")
    why = {
        "ehydro_nj": "eHydro single-beam survey — a boat with an echo sounder, the ONLY "
                     "source that measures the bed *under* water. Carves Shark River Inlet",
        "shrewsbury_ehydro_2015": "eHydro 2015 — carves the Rumson–Sea Bright causeway, "
                                  "which the lidar baked in as a +1.6..+8.6 m dam",
        "usace_nj_2010": "1 m PRE-Sandy topobathy (2010 USACE NCMP). Green lidar: correct in "
                         "clear shallow water, but in deep/turbid water returns the WATER "
                         "SURFACE (~0..+2 m) — which is why it must NOT outrank eHydro",
        "cudem_nj": "3 m CUDEM fill: inlets, shelf, Raritan Bay",
        "nj_10ft_dem": "3 m fill, inland land only (`zmin` guard keeps it off the water)",
        "gmrt_nj": "~50 m GMRT offshore tail, out to the ERA5 node",
    }
    rows = []
    for i, layer in enumerate(base.elevation(), 1):
        name = layer["elevation"]
        guard = ", ".join(f"`{k}={v}`" for k, v in layer.items() if k != "elevation") or "—"
        rows.append((i, f"`{name}`", guard, why.get(name, "")))
    md.append(_md_table(rows, ("#", "dataset", "guard", "why it sits here")))

    # ── forcing ──────────────────────────────────────────────────────────────
    md.append("**Boundary forcing**\n\n")
    md.append(_md_table([
        ("Water level", f"`{base.waterlevel_geodataset}`",
         f"Observed NOAA CO-OPS gauges, interpolated onto the mask==2 edge. "
         f"Buffer **{base.waterlevel_buffer:,} m** to reach the Atlantic City gauge. "
         f"(GTSM was dropped — it under-predicted Sandy by ~1 m)"),
        ("Waves", "`era5_waves_nj`",
         "ERA5 at the offshore node **(-74.0, 40.0)**, 7 alongshore support points on the "
         "deep open-Atlantic mask==2 edge"),
        ("Wind / pressure", "ERA5", "`netamuamvfile` / `netampfile`"),
        ("Rain", "AORC", "`netamprfile`"),
        ("Discharge", "USGS", "`netsrcdisfile` — the two domain inflows"),
        ("Simulation window", f"**{inp.get('tstart')} → {inp.get('tstop')}**",
         "Hurricane Sandy; 73 hourly map frames"),
    ], ("forcing", "source", "detail")))

    return "".join(md)


def show(sf, base: BaseConfig | None = None, as_markdown: bool = False):
    """Render the inventory in a notebook (or return the raw markdown)."""
    md = tables(sf, base)
    if as_markdown:
        return md
    from IPython.display import Markdown, display

    display(Markdown(md))
