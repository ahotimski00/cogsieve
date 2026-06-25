"""Fractional class coverage via exactextract.

Reads windowed raster data only over each polygon's bounding box. For COGs served
over HTTP this means range requests, not whole-file downloads - the same screen
that took 6h in ArcPy runs in minutes against a remote COG.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import rasterio
from exactextract import exact_extract

from cogsieve.screen import CoverageScreen


def class_coverage(
    polygons: gpd.GeoDataFrame,
    screen: CoverageScreen,
) -> gpd.GeoDataFrame:
    """Compute per-class fractional coverage for each polygon.

    Returns a copy of `polygons` with one column per class in screen.all_classes
    (named via screen.column_for), the aggregate `pass_column`, and a boolean
    `keep_column` reflecting the threshold (respecting `invert`).
    """
    raster_path = str(screen.raster)
    with rasterio.open(raster_path) as src:
        raster_crs = src.crs

    working = polygons.to_crs(raster_crs) if polygons.crs != raster_crs else polygons.copy()

    classes = sorted(screen.all_classes.keys())
    # exactextract returns one row per polygon with two list-valued columns:
    #   unique = [class_values_observed], frac = [fraction_each]
    # We pivot those into one column per requested class, defaulting to 0.0.
    results = exact_extract(
        rast=raster_path,
        vec=working,
        ops=["unique", "frac"],
        output="pandas",
        include_geom=False,
    )

    out = polygons.copy()
    for cls in classes:
        out[screen.column_for(cls)] = 0.0

    for row_idx, (uniq, fracs) in enumerate(zip(results["unique"], results["frac"], strict=True)):
        if uniq is None:
            continue
        for u, f in zip(uniq, fracs, strict=True):
            cls = int(u)
            if cls in screen.all_classes:
                out.iat[row_idx, out.columns.get_loc(screen.column_for(cls))] = float(f)

    pass_frac = sum(out[screen.column_for(c)] for c in screen.pass_classes)
    out[screen.pass_column] = pass_frac

    if screen.invert:
        out[screen.keep_column] = pass_frac < screen.min_coverage
    else:
        out[screen.keep_column] = pass_frac >= screen.min_coverage

    return out


def cache_key(screen: CoverageScreen, polygon_hash: str) -> str:
    """Deterministic cache key for a screen against a specific polygon set."""
    classes = "-".join(str(c) for c in sorted(screen.all_classes))
    return f"{screen.name}__{polygon_hash}__cls{classes}__thr{screen.min_coverage}"


def polygon_hash(polygons: gpd.GeoDataFrame) -> str:
    """Stable short hash of polygon geometries + count, for cache invalidation."""
    import hashlib

    h = hashlib.sha1()
    h.update(str(len(polygons)).encode())
    h.update(polygons.total_bounds.tobytes())
    return h.hexdigest()[:12]


def open_raster_info(raster: str | Path) -> dict[str, object]:
    """Lightweight metadata probe useful for diagnostics and demo READMEs."""
    with rasterio.open(str(raster)) as src:
        return {
            "crs": str(src.crs),
            "shape": (src.height, src.width),
            "dtype": str(src.dtypes[0]),
            "nodata": src.nodata,
            "bounds": tuple(src.bounds),
            "transform_px_m": (abs(src.transform.a), abs(src.transform.e)),
        }
