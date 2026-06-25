"""Build an AOI-clipped LANDFIRE FBFM40 COG from a local LANDFIRE raster.

LANDFIRE 40 Scott and Burgan Fire Behavior Fuel Model (FBFM40) is a 30m
categorical raster classifying surface fuels into ~40 named models
(GR1-GR9, GS1-GS4, SH1-SH9, TU1-TU5, TL1-TL9, SB1-SB4, plus non-burnable).
Each model encodes a distinct combination of fuel loading, size class, and
fuel-bed properties used by fire-behavior simulators.

LANDFIRE is not on Planetary Computer's STAC catalog and landfire.gov has
anti-bot protections, so the source TIFF requires a one-time manual
download. Workflow:

  1. Manually download the LANDFIRE 2022 FBFM40 CONUS bundle from:
        https://landfire.gov/version_download.php
     The bundle includes LC22_F40_220.tif (or similar).

  2. Run this script pointing at the local TIFF and an AOI bbox. It clips
     to the bbox and writes a small COG; no reclassification is needed
     because FBFM40 is already categorical.

cogsieve consumes the resulting COG with class codes matching LANDFIRE's
FBFM40 attribute table (101=GR1, 102=GR2, ..., 142=SH2, ..., 162=TU2, etc).

Usage:
    python scripts/build_landfire_cog.py \\
        --src /path/to/LC22_F40_220.tif \\
        --bbox -117.281 32.544 -116.935 33.406 \\
        --out data/san_diego_fbfm40.tif
"""

from __future__ import annotations

from pathlib import Path

import rasterio
import typer
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from rich.console import Console

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    src: Path = typer.Option(
        ...,
        exists=True,
        help="Local LANDFIRE FBFM40 TIFF (download from landfire.gov one-time).",
    ),
    bbox: tuple[float, float, float, float] = typer.Option(
        ...,
        help="minx miny maxx maxy in EPSG:4326 for AOI clip.",
    ),
    out: Path = typer.Option(
        Path("data/fbfm40_aoi.tif"),
        help="Output clipped COG path.",
    ),
) -> None:
    console.print(f"opening source LANDFIRE FBFM40 -> {src}")
    with rasterio.open(src) as ds:
        console.print(f"  src CRS: {ds.crs}, shape: {ds.shape}, pixel: {abs(ds.transform.a):.1f} m")

        console.print(f"clipping to bbox {bbox}")
        src_bounds = transform_bounds("EPSG:4326", ds.crs, *bbox)
        window = from_bounds(*src_bounds, transform=ds.transform).round_offsets().round_lengths()
        arr = ds.read(1, window=window)
        clipped_transform = ds.window_transform(window)
        crs_out = ds.crs
        nodata = ds.nodata
        console.print(f"  clipped shape: {arr.shape}, dtype: {arr.dtype}")

    profile = {
        "driver": "COG",
        "dtype": arr.dtype.name,
        "count": 1,
        "height": arr.shape[0],
        "width": arr.shape[1],
        "crs": crs_out,
        "transform": clipped_transform,
        "compress": "DEFLATE",
        "blocksize": 512,
    }
    if nodata is not None:
        profile["nodata"] = nodata
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(arr, 1)
    size_mb = out.stat().st_size / 1e6
    console.print(f"[bold green]done[/bold green]: {out} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    app()
