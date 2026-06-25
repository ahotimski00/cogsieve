"""Build a categorical slope-class COG from USGS 3DEP for a parcel bbox.

Pipeline:
  1. STAC search Planetary Computer for 3DEP-seamless 10m tiles intersecting the bbox.
  2. Stream-and-mosaic the tiles directly from the signed URLs (rasterio.merge)
     into a single in-memory elevation array clipped to the bbox.
  3. Reproject to UTM Zone 11N (EPSG:32611) so cell sizes are in meters.
  4. Compute slope as percent: tan(atan(sqrt(dx^2 + dy^2))) * 100.
  5. Reclassify into 5 bins suitable for solar siting.
  6. Write a categorical uint8 COG with DEFLATE compression.

Usage:
    python scripts/build_slope_cog.py --bbox -117.281 32.544 -116.935 33.406 \\
        --out data/san_diego_slope_classes.tif
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import planetary_computer as pc
import pystac_client
import rasterio
import typer
from rasterio.crs import CRS
from rasterio.merge import merge
from rasterio.warp import Resampling, calculate_default_transform, reproject
from rich.console import Console

app = typer.Typer(add_completion=False)
console = Console()

UTM_11N = CRS.from_epsg(32611)
SLOPE_BINS_PCT = [2, 5, 10, 20]
SLOPE_CLASS_LABELS = {
    1: "0_to_2pct",
    2: "2_to_5pct",
    3: "5_to_10pct",
    4: "10_to_20pct",
    5: "over_20pct",
}


def _fetch_dem_mosaic(
    bbox_4326: tuple[float, float, float, float],
) -> tuple[np.ndarray, rasterio.Affine, CRS]:
    """Search 3DEP, open remote tiles, return a mosaic clipped to bbox."""
    cat = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=pc.sign_inplace,
    )
    items = [
        i for i in cat.search(collections=["3dep-seamless"], bbox=bbox_4326).items()
        if i.properties.get("gsd") == 10
    ]
    if not items:
        raise RuntimeError(f"no 10m 3DEP items found for bbox {bbox_4326}")
    console.print(f"found {len(items)} 10m 3DEP tile(s) covering bbox")

    srcs = [rasterio.open(i.assets["data"].href) for i in items]
    mosaic, transform = merge(srcs, bounds=bbox_4326)
    for s in srcs:
        s.close()
    return mosaic[0], transform, srcs[0].crs


def _reproject_to_utm(
    arr: np.ndarray,
    src_transform: rasterio.Affine,
    src_crs: CRS,
    bbox_4326: tuple[float, float, float, float],
) -> tuple[np.ndarray, rasterio.Affine]:
    """Reproject the mosaic to UTM 11N so cell sizes are in meters."""
    h, w = arr.shape
    dst_transform, dst_w, dst_h = calculate_default_transform(
        src_crs, UTM_11N, w, h,
        *rasterio.transform.array_bounds(h, w, src_transform),
        resolution=10.0,
    )
    dst = np.empty((dst_h, dst_w), dtype=np.float32)
    reproject(
        source=arr.astype(np.float32),
        destination=dst,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=UTM_11N,
        resampling=Resampling.bilinear,
    )
    return dst, dst_transform


def _slope_percent(dem: np.ndarray, pixel_size_m: float) -> np.ndarray:
    """Compute slope (percent grade) from a metric-CRS DEM."""
    dy, dx = np.gradient(dem, pixel_size_m, pixel_size_m)
    slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
    return (np.tan(slope_rad) * 100).astype(np.float32)


def _reclassify(slope_pct: np.ndarray) -> np.ndarray:
    """Bin slope-percent into 5 classes:
       1 = 0-2%, 2 = 2-5%, 3 = 5-10%, 4 = 10-20%, 5 = >20%
    """
    classes = np.digitize(slope_pct, SLOPE_BINS_PCT, right=False) + 1
    return classes.astype(np.uint8)


def _write_cog(
    arr: np.ndarray,
    transform: rasterio.Affine,
    crs: CRS,
    out_path: Path,
) -> None:
    """Write a single-band categorical COG with DEFLATE compression."""
    profile = {
        "driver": "COG",
        "dtype": "uint8",
        "count": 1,
        "height": arr.shape[0],
        "width": arr.shape[1],
        "crs": crs,
        "transform": transform,
        "compress": "DEFLATE",
        "blocksize": 512,
        "nodata": 0,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(arr, 1)


@app.command()
def main(
    bbox: tuple[float, float, float, float] = typer.Option(
        (-117.281, 32.544, -116.935, 33.406),
        help="minx miny maxx maxy in EPSG:4326 (default: SD parcels extent).",
    ),
    out: Path = typer.Option(
        Path("data/san_diego_slope_classes.tif"),
        help="Output COG path.",
    ),
) -> None:
    console.print(f"step 1/5: fetching 3DEP tiles for bbox {bbox}")
    dem, src_transform, src_crs = _fetch_dem_mosaic(bbox)
    console.print(f"  mosaic shape: {dem.shape}, src CRS: {src_crs}")

    console.print("step 2/5: reprojecting to UTM 11N (meters)")
    dem_m, transform_m = _reproject_to_utm(dem, src_transform, src_crs, bbox)
    console.print(f"  UTM shape: {dem_m.shape}, pixel size: {transform_m.a:.1f} m")

    console.print("step 3/5: computing slope-percent")
    slope = _slope_percent(dem_m, pixel_size_m=transform_m.a)
    console.print(
        f"  slope range: {np.nanmin(slope):.1f}% to {np.nanmax(slope):.1f}%, "
        f"median: {np.nanmedian(slope):.1f}%"
    )

    console.print("step 4/5: reclassifying into 5 slope bins")
    classes = _reclassify(slope)
    for code, label in SLOPE_CLASS_LABELS.items():
        pct = (classes == code).mean() * 100
        console.print(f"  class {code} ({label}): {pct:.1f}% of pixels")

    console.print(f"step 5/5: writing COG -> {out}")
    _write_cog(classes, transform_m, UTM_11N, out)
    size_mb = out.stat().st_size / 1e6
    console.print(f"[bold green]done[/bold green]: {out} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    app()
