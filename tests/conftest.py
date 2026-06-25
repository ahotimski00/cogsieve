"""Synthetic raster + polygon fixtures.

Built in-memory each test run so the suite is hermetic - no fixture files,
no downloads, no flaky network. A 10x10 categorical raster with known class
counts gives us exact ground truth for coverage assertions.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box


@pytest.fixture
def categorical_raster(tmp_path: Path) -> Path:
    """A 10x10 raster with 4 quadrants of class 1/2/3/4, 1m pixels at origin."""
    arr = np.zeros((10, 10), dtype=np.uint8)
    arr[:5, :5] = 1   # top-left
    arr[:5, 5:] = 2   # top-right
    arr[5:, :5] = 3   # bottom-left
    arr[5:, 5:] = 4   # bottom-right

    path = tmp_path / "synthetic.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype=arr.dtype,
        crs="EPSG:3857",
        transform=from_origin(0, 10, 1, 1),
        nodata=0,
    ) as dst:
        dst.write(arr, 1)
    return path


@pytest.fixture
def polygons() -> gpd.GeoDataFrame:
    """Three test polygons against the 10x10 raster:

    - 'full_class_1': 5x5 box covering only class 1 -> 100% class 1
    - 'half_1_half_2': 5x10 box covering classes 1 and 2 -> 50% each
    - 'all_four':     10x10 box covering all four classes -> 25% each
    """
    return gpd.GeoDataFrame(
        {"name": ["full_class_1", "half_1_half_2", "all_four"]},
        geometry=[
            box(0, 5, 5, 10),
            box(0, 5, 10, 10),
            box(0, 0, 10, 10),
        ],
        crs="EPSG:3857",
    )
