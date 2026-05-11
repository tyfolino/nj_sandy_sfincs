# NJ Sandy SFINCS

SFINCS surge model for Hurricane Sandy (Oct 29–31, 2012) at Asbury Park, NJ.

Built with [HydroMT-SFINCS](https://github.com/Deltares/hydromt_sfincs).

## Study area

Asbury Park barrier island and Atlantic shelf, NJ (~38.9–41.4°N, 73.7–75.6°W).

## Data

| Dataset | Source | Purpose |
|---------|--------|---------|
| USGS 3DEP | USGS National Map | Elevation / bathymetry |
| ESA WorldCover 2020 | ESA / S3 | Manning's roughness |
| GTSM-ERA5-E | Copernicus CDS | Offshore water level boundary |
| ERA5 | Copernicus CDS | Wind forcing |

## Notebooks

| Notebook | Description |
|----------|-------------|
| `notebooks/0_download_data.ipynb` | Download and prepare input data |
| `notebooks/1_build_model.ipynb` | Build the SFINCS model with HydroMT |
| `notebooks/2_run_model.ipynb` | Run SFINCS via Docker |
| `notebooks/3_plot_results.ipynb` | Downscale and plot maximum flood depth |
| `notebooks/4_animate_results.ipynb` | Animate flood evolution over time |

## Running SFINCS

```bash
docker pull deltares/sfincs-cpu:latest
docker run --rm -v $(pwd)/model:/data deltares/sfincs-cpu:latest
```

## Known limitations

- GTSM-ERA5-E underestimates nearshore surge peak
