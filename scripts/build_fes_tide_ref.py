"""
Predict a FES2014 (or TPXO) tide-only series at the Sandy Hook reference point and
write it as a hydromt_sfincs GeoDataset NetCDF (NOAA schema): gtsm/fes_sandy_tide.nc.

WHY. An INDEPENDENT, well-phased offshore tide to rank against Battery/GTSM with
source_phase_lag — "what is the true offshore tidal phase near the north boundary?"
This is a PHASE REFERENCE only (pure tide, no surge): it is not a runnable SFINCS
forcing on its own, but it (or GTSM tide-only) is the tide ingredient for the
composite forcing (scripts/build_composite_forcing.py).

⚠️ HEAVIEST DATA-ACCESS ITEM (see the plan's Risks). This script is written but NOT
run in-repo because it needs BOTH:
  1. pyTMD  — add to environment.yml (`conda install -c conda-forge pymt-tmd`/`pip
     install pyTMD`); NOT currently in the env.
  2. FES2014 constituent grids — free AVISO+ account (aviso.altimetry.fr): register
     and TICK "FES (Finite Element Solution - Oceanic Tides Heights)" under Auxiliary
     Products; you get FTP/portal login by email. Then either unpack the ocean-tide
     grids to a directory ($FES_DIRECTORY) or fetch them with
     `pyTMD.datasets.fetch_aviso_fes(username=..., password=...)`. (TPXO9 is an
     alternative but needs a separate OSU academic licence request — more restrictive.)
If access blocks, DROP this source and use gtsm_sandy_tide.nc (free from
download_gtsm_sandy.py) as the sole independent tide-phase reference — the matrix
still stands.

The pyTMD API has moved across versions; the call below targets pyTMD>=2.1
(`pyTMD.compute.tide_elevations`). Verify against your installed version.

Run:  FES_DIRECTORY=/path/to/fes2014 NJ_ROOT=$PWD \
      ./micromamba/envs/sfincs/bin/python scripts/build_fes_tide_ref.py
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(os.environ.get("NJ_ROOT", Path(__file__).resolve().parents[1]))
OUT_DIR = ROOT / "data" / "gtsm"
OUT = OUT_DIR / "fes_sandy_tide.nc"

REF_LON, REF_LAT = -74.0091, 40.4669  # NOAA 8531680 Sandy Hook (the north anchor)
MODEL = os.environ.get("TIDE_MODEL", "FES2014")
FES_DIRECTORY = os.environ.get("FES_DIRECTORY")  # AVISO constituent grids
BEGIN, END = "2012-10-28", "2012-10-31"
STEP_MIN = 10


def main() -> None:
    if FES_DIRECTORY is None:
        raise SystemExit(
            "set $FES_DIRECTORY to the FES2014 constituent grids (AVISO). "
            "If unavailable, use gtsm_sandy_tide.nc as the tide-phase reference instead."
        )
    try:
        import pyTMD.compute
    except ImportError as e:
        raise SystemExit(
            "pyTMD not installed — add it to environment.yml. "
            f"({e}) Fallback: gtsm_sandy_tide.nc."
        )

    times = pd.date_range(BEGIN, END, freq=f"{STEP_MIN}min")
    x = np.full(times.size, REF_LON)
    y = np.full(times.size, REF_LAT)

    # tide_elevations returns metres of tidal elevation (model datum ≈ MSL).
    h = pyTMD.compute.tide_elevations(
        x, y, times.to_pydatetime(),
        DIRECTORY=FES_DIRECTORY, MODEL=MODEL,
        EPOCH=(1992, 1, 1, 0, 0, 0), TYPE="drift", TIME="datetime",
    )
    tide = np.ma.filled(np.asarray(h, "float64"), np.nan).ravel()
    if not np.isfinite(tide).any():
        raise SystemExit("FES prediction is all-NaN — check the point is in the ocean mask")

    out = xr.Dataset(
        {"waterlevel": (("time", "stations"), tide[:, None])},
        coords={
            "time": times.values,
            "stations": [8531680],
            "lon": ("stations", [REF_LON]),
            "lat": ("stations", [REF_LAT]),
        },
        attrs={"title": f"{MODEL} tide-only at Sandy Hook (phase reference)",
               "source": f"pyTMD {MODEL}", "datum": "MSL", "units": "m"},
    )
    out["waterlevel"].attrs.update(units="m")
    tmp = OUT.with_suffix(OUT.suffix + ".tmp")
    out.to_netcdf(tmp)
    os.replace(tmp, OUT)
    print(f"Wrote {OUT}  ({MODEL} tide, {times.size} steps, "
          f"range {np.nanmax(tide) - np.nanmin(tide):.2f} m)")


if __name__ == "__main__":
    main()
