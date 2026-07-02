"""nj_sfincs — a small toolkit for building, running, validating and visualizing
the NJ Sandy SFINCS model as a set of wave-sensitivity experiments.

Submodules are intentionally independent so cheap imports stay cheap:

    from nj_sfincs.config import EXPERIMENTS      # no heavy deps
    from nj_sfincs import plots, validate         # matplotlib / hydromt

The science (grid, elevation, subgrid, forcing, the SnapWave block, the
validation metrics) is lifted verbatim from notebooks/sfincs-nj-sandy.ipynb so
the numbers are behaviour-preserving; only the wave "knobs" vary between
experiments (see config.WaveConfig / config.EXPERIMENTS).
"""

# Prime PROJ/GEOS before hydromt_sfincs loads. In a bare (non-notebook) process,
# importing hydromt_sfincs.utils first and only later touching PROJ triggers a
# native "double free or corruption" inside utils.downscale_floodmap (a GEOS/PROJ
# load-order conflict). Importing pyproj here — before any submodule pulls in
# hydromt_sfincs — initializes PROJ first and makes the package safe from the CLI.
# The notebook never hit this because it imports the viz stack (which pulls
# pyproj) up top. Keep this import ahead of any hydromt_sfincs import.
import pyproj  # noqa: F401,E402  (PROJ primer — do not remove or reorder)

__all__ = ["config", "model", "run", "validate", "plots", "report"]
