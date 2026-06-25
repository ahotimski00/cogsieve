"""Build a categorical canopy-bin COG from a local NLCD TCC raster.

NLCD Tree Canopy Cover (TCC) is a 30m, 0-100 fractional canopy product from
USDA Forest Service / MRLC. It is not on Planetary Computer's STAC catalog and
the MRLC web portal has anti-bot protections, so it cannot be fetched fully
automatically. The recommended workflow:

  1. Manually download the CONUS bundle from MRLC's web portal:
        https://www.mrlc.gov/data/nlcd-2021-usfs-tree-canopy-cover-conus
     The bundle is ~2 GB. Inside the ZIP, the canopy raster is
     nlcd_tcc_conus_2021_v2021-4.tif (or similar).

  2. Run this script pointing at the local TIFF and an AOI bbox. It clips,
     reclassifies into 5 canopy-density bins, and writes a small COG.

cogsieve consumes the result as a categorical raster. Bin codes:
    1 = 0-10% canopy    (low / tree-sparse)
    2 = 10-25% canopy   (low-moderate)
    3 = 25-40% canopy   (moderate)
    4 = 40-60% canopy   (well-canopied)
    5 = 60-100% canopy  (dense canopy)

Usage:
    python scripts/build_canopy_cog.py \\
        --src /path/to/nlcd_tcc_conus_2021_v2021-4.tif \\
        --bbox -118.95 32.80 -117.65 34.83 \\
        --out data/la_county_canopy_classes.tif
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
import typer
from rasterio.crs import CRS
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from rich.console import Console

app = typer.Typer(add_completion=False)
console = Console()

CANOPY_BINS_PCT = [10, 25, 40, 60]
CANOPY_CLASS_LABELS = {
    1: "0_to_10pct",
    2: "10_to_25pct",
    3: "25_to_40pct",
    4: "40_to_60pct",
    5: "60_to_100pct",
}


def _reclassify(canopy_pct: np.ndarray) -> np.ndarray:
    """Bin 0-100 canopy percent into 5 classes:
       1 = 0-10%, 2 = 10-25%, 3 = 25-40%, 4 = 40-60%, 5 = >60%.
    NLCD TCC uses values up to 100; pixels >100 (no-data sentinels like 254/255)
    map to bin 5 in this scheme, which is fine because we will keep nodata as 0.
    """
    # Treat anything above 100 as nodata; will be overwritten to 0 below.
    classes = np.digitize(canopy_pct, CANOPY_BINS_PCT, right=False) + 1
    classes[canopy_pct > 100] = 0
    return classes.astype(np.uint8)


def _write_cog(
    arr: np.ndarray,
    transform: rasterio.Affine,
    crs: CRS,
    out_path: Path,
) -> None:
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
    src: Path = typer.Option(
        ...,
        exists=True,
        help="Local NLCD TCC TIFF (download from MRLC portal one-time).",
    ),
    bbox: tuple[float, float, float, float] = typer.Option(
        ...,
        help="minx miny maxx maxy in EPSG:4326 for AOI clip.",
    ),
    out: Path = typer.Option(
        Path("data/canopy_classes.tif"),
        help="Output classified COG path.",
    ),
) -> None:
    console.print(f"step 1/4: opening source TCC raster -> {src}")
    with rasterio.open(src) as ds:
        console.print(f"  src CRS: {ds.crs}, shape: {ds.shape}, pixel: {abs(ds.transform.a):.1f} m")

        console.print(f"step 2/4: clipping to bbox {bbox}")
        src_bounds = transform_bounds("EPSG:4326", ds.crs, *bbox)
        window = from_bounds(*src_bounds, transform=ds.transform).round_offsets().round_lengths()
        arr = ds.read(1, window=window)
        clipped_transform = ds.window_transform(window)
        console.print(f"  clipped shape: {arr.shape}")

    console.print("step 3/4: reclassifying into 5 canopy bins")
    classes = _reclassify(arr)
    for code, label in CANOPY_CLASS_LABELS.items():
        pct = (classes == code).mean() * 100
        console.print(f"  class {code} ({label}): {pct:.1f}% of pixels")

    console.print(f"step 4/4: writing COG -> {out}")
    with rasterio.open(src) as ds:
        crs_out = ds.crs
    _write_cog(classes, clipped_transform, crs_out, out)
    size_mb = out.stat().st_size / 1e6
    console.print(f"[bold green]done[/bold green]: {out} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    app()
