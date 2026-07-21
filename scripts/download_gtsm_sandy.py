"""
Download GTSM-ERA5 global tide+surge at the NJ coast for Hurricane Sandy and write
two hydromt_sfincs GeoDataset NetCDFs (same schema as noaa_sandy_nj.nc):

  gtsm_sandy.nc       forcing — TOTAL water level at the GTSM coastal nodes nearest
                      the domain, converted MSL→NAVD88. A full runnable boundary.
  gtsm_sandy_tide.nc  reference — TIDE ONLY (GTSM total − surge) at the same nodes.
                      Phase reference for source_phase_lag; NOT a runnable forcing
                      (no surge). Left on the model's MSL datum (phase-only use).

WHY. The advisor asked us to re-evaluate an alternative forcing source. GTSM-ERA5 is
the global tide+surge reanalysis we used before switching to NOAA gauges (it under-
predicted Sandy's crest ~1 m — a known, quantified gap). Here we A/B its PHASE (and
re-measure that amplitude gap) on the current boundary. The GTSM reanalysis carries
total_water_level and storm_surge_residual (NOT tidal_elevation — projections-only),
so the tide-only reference is derived here as tide = total − surge.

PREREQUISITES (this script is written to the established CDS pattern in
download_era5_cds.py but has NOT been run in-repo — verify on first run):
  1. ~/.cdsapirc configured with your CDS personal access token (same as ERA5).
  2. Terms of use accepted for the GTSM water-level dataset at cds.climate.copernicus.eu.
  3. pip/conda: cdsapi (already in environment.yml).
  4. VERIFY on first run: (a) the CDS dataset id + request keys below against the
     dataset's "Download" tab (CDS occasionally renames keys); (b) the station coord /
     variable names in POST-PROCESS (GTSM versions differ: station_x_coordinate vs
     longitude, total_water_level vs waterlevel); (c) MSL_TO_NAVD88_M against NOAA
     VDatum / the 8531680 station-datums page.

Run:  NJ_ROOT=$PWD ./micromamba/envs/sfincs/bin/python scripts/download_gtsm_sandy.py
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import xarray as xr

ROOT = Path(os.environ.get("NJ_ROOT", Path(__file__).resolve().parents[1]))
OUT_DIR = ROOT / "data" / "gtsm"
RAW = OUT_DIR / "gtsm_reanalysis_2012_10_raw.nc"
OUT_TOTAL = OUT_DIR / "gtsm_sandy.nc"
OUT_TIDE = OUT_DIR / "gtsm_sandy_tide.nc"

# CDS dataset + request. The GTSM ERA5-forced *reanalysis* (Deltares GTSM v3.0)
# lives inside the CMIP6 collection under experiment="reanalysis" (1950-2024).
# VERIFIED 2026-07-20 against the live CDS form.json + constraints.json:
#   * the reanalysis experiment exposes ONLY total_water_level + storm_surge_residual
#     (tidal_elevation is projections-only). So GTSM tide-only is DERIVED here as
#     tide = total_water_level - storm_surge_residual.
#   * `version` is REQUIRED for reanalysis (v2/v3); v3 is latest.
#   * temporal_aggregation "10_min" and year 2012 / month 10 are valid.
#   * datum = MSL (1986-2005 IPCC AR5) → total is shifted to NAVD88 below.
CDS_DATASET = "sis-water-level-change-timeseries-cmip6"
CDS_REQUEST = {
    "experiment": "reanalysis",
    "variable": ["total_water_level", "storm_surge_residual"],
    "temporal_aggregation": "10_min",
    "version": "v3",
    "year": "2012",
    "month": "10",
    "format": "netcdf",
}

# GTSM coastal output nodes are global; keep the nodes nearest these targets so the
# alongshore gradient (Sandy Hook → Atlantic City) is preserved, mirroring the NOAA
# multi-gauge span. (lon, lat, name)
TARGETS = [
    (-74.0091, 40.4669, "sandy_hook"),
    (-74.0142, 40.7006, "battery_approx"),
    (-74.4181, 39.3550, "atlantic_city"),
    (-74.9600, 38.9683, "cape_may"),
]

# MSL → NAVD88 at Sandy Hook. ✅ VERIFIED 2026-07-21 against the NOAA CO-OPS published
# station datums for 8531680 (mdapi .../stations/8531680/datums.json, epoch 1983-2001,
# station-datum feet): MSL = 5.090, NAVD88 = 5.330 ⇒ MSL sits 0.240 ft = 0.0732 m BELOW
# NAVD88, so z_navd88 = z_msl - 0.073.  (The old comment had this backwards — NAVD88 sits
# ABOVE local MSL here — though the sign of the constant happened to be right.)
# Residual uncertainty ~0.01-0.02 m: GTSM's datum is the 1986-2005 AR5 MSL, a later epoch
# than 1983-2001, so its zero is ~1-2 cm higher still. Left out; it is far inside the
# amplitude error below. Phase is datum-independent — this only sets AMPLITUDE.
#
# ⚠️ The datum is NOT this forcing's amplitude problem. Measured 2026-07-21, GTSM
# TIDE-ONLY daily range at this node is 1.23/1.15/1.06/0.95 m (mean 1.09 m) over
# Oct 28-31 2012, against a published great diurnal range GT = 1.594 m — and that week
# was a SPRING tide (full moon Oct 29), so the truth should EXCEED 1.594 m. GTSM is
# therefore >=31% under-amplitude in the TIDE alone, on top of its known ~1 m surge
# deficit. Do not read a low `phaselag_gtsm` interior peak as a phase result.
MSL_TO_NAVD88_M = -0.073


def _coord(ds: xr.Dataset, *names: str) -> np.ndarray:
    for n in names:
        if n in ds.variables:
            return np.asarray(ds[n].values)
    raise KeyError(f"none of {names} in GTSM file (vars: {list(ds.variables)})")


def _var(ds: xr.Dataset, *names: str) -> str:
    for n in names:
        if n in ds.data_vars:
            return n
    raise KeyError(f"none of {names} in GTSM data_vars ({list(ds.data_vars)})")


def _write(ds_src: xr.Dataset, varname: str, node_idx, node_ll, path: Path,
           title: str, to_navd88: float) -> None:
    """Extract selected nodes of one variable → NOAA-schema GeoDataset NetCDF."""
    station_dim = [d for d in ds_src[varname].dims if d != "time"][0]
    da = ds_src[varname].isel({station_dim: node_idx})  # (time, nodes)
    da = da.transpose("time", station_dim)
    vals = np.asarray(da.values, "float64") + to_navd88
    ids = np.arange(1, len(node_idx) + 1)  # synthetic station ids
    out = xr.Dataset(
        {"waterlevel": (("time", "stations"), vals)},
        coords={
            "time": ds_src["time"].values,
            "stations": ids,
            "lon": ("stations", [ll[0] for ll in node_ll]),
            "lat": ("stations", [ll[1] for ll in node_ll]),
        },
        attrs={"title": title, "source": f"GTSM-ERA5 {CDS_DATASET}",
               "datum": "NAVD88" if to_navd88 else "MSL", "units": "m"},
    )
    out["waterlevel"].attrs.update(units="m")
    tmp = path.with_suffix(path.suffix + ".tmp")
    out.to_netcdf(tmp)
    os.replace(tmp, path)
    print(f"Wrote {path}  ({len(node_idx)} nodes)")


def _open_gtsm(raw: Path) -> xr.Dataset:
    """Open the CDS payload, whether a single .nc or a ZIP of per-variable .ncs.

    A multi-variable CDS request often returns a zip (total_water_level and
    storm_surge_residual in separate files); merge them into one dataset.
    """
    with open(raw, "rb") as f:
        magic = f.read(2)
    if magic == b"PK":  # zip archive
        import zipfile
        exdir = raw.with_suffix(".extracted")
        exdir.mkdir(exist_ok=True)
        with zipfile.ZipFile(raw) as z:
            z.extractall(exdir)
        ncs = sorted(exdir.glob("*.nc"))
        if not ncs:
            raise SystemExit(f"no .nc inside {raw}")
        return xr.merge([xr.open_dataset(p) for p in ncs], compat="override")
    return xr.open_dataset(raw)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not RAW.exists():
        import cdsapi
        print(f"Downloading GTSM reanalysis → {RAW}")
        cdsapi.Client().retrieve(CDS_DATASET, CDS_REQUEST, str(RAW))
    else:
        print(f"Reusing cached {RAW}")

    ds = _open_gtsm(RAW)
    glon = _coord(ds, "station_x_coordinate", "longitude", "lon")
    glat = _coord(ds, "station_y_coordinate", "latitude", "lat")
    v_total = _var(ds, "total_water_level", "waterlevel")
    v_surge = _var(ds, "storm_surge_residual", "surge")
    # tide = total − surge (reanalysis has no tidal_elevation variable).
    ds["gtsm_tide"] = ds[v_total] - ds[v_surge]

    idx, node_ll = [], []
    for lon, lat, name in TARGETS:
        j = int(np.argmin(np.hypot(glon - lon, glat - lat)))
        idx.append(j)
        node_ll.append((float(glon[j]), float(glat[j])))
        print(f"  {name:14s} target ({lon:.3f},{lat:.3f}) → GTSM node "
              f"({glon[j]:.3f},{glat[j]:.3f})")

    # clip to the Sandy window to keep files small
    ds = ds.sel(time=slice("2012-10-28", "2012-10-31"))
    _write(ds, v_total, idx, node_ll, OUT_TOTAL,
           "GTSM-ERA5 total water level (forcing), MSL→NAVD88", MSL_TO_NAVD88_M)
    _write(ds, "gtsm_tide", idx, node_ll, OUT_TIDE,
           "GTSM-ERA5 tide = total − surge (tide-only phase reference), MSL", 0.0)


if __name__ == "__main__":
    main()
