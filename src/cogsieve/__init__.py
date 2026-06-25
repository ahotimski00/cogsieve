"""cogsieve: sieve polygons by fractional class coverage of categorical rasters.

Reads windowed pixels directly from Cloud-Optimized GeoTIFFs over HTTP, so a
state-wide screen against a remote LCMAP/NLCD COG runs without downloading the
scene.
"""

from cogsieve.coverage import class_coverage
from cogsieve.io import (
    IO_LULC_CLASS_NAMES,
    LCMAP_CLASS_NAMES,
    MTBS_CLASS_NAMES,
    io_lulc_asset_urls,
    lcmap_asset_url,
    mtbs_asset_url,
)
from cogsieve.pipeline import run_screens
from cogsieve.screen import CoverageScreen, ScreenResult

__all__ = [
    "CoverageScreen",
    "IO_LULC_CLASS_NAMES",
    "LCMAP_CLASS_NAMES",
    "MTBS_CLASS_NAMES",
    "ScreenResult",
    "class_coverage",
    "io_lulc_asset_urls",
    "lcmap_asset_url",
    "mtbs_asset_url",
    "run_screens",
]
__version__ = "0.1.0"
