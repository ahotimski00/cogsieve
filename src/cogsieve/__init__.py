"""cogsieve: sieve polygons by fractional class coverage of categorical rasters.

Reads windowed pixels directly from Cloud-Optimized GeoTIFFs over HTTP, so a
state-wide screen against a remote LCMAP/NLCD COG runs without downloading the
scene.
"""

from cogsieve.coverage import class_coverage
from cogsieve.io import LCMAP_CLASS_NAMES, lcmap_asset_url
from cogsieve.pipeline import run_screens
from cogsieve.screen import CoverageScreen, ScreenResult

__all__ = [
    "CoverageScreen",
    "LCMAP_CLASS_NAMES",
    "ScreenResult",
    "class_coverage",
    "lcmap_asset_url",
    "run_screens",
]
__version__ = "0.1.0"
