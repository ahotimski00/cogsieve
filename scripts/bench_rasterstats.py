"""Head-to-head benchmark: cogsieve vs rasterstats on the LCMAP solar screen.

Same inputs (San Diego County parcels, USGS LCMAP COG via Planetary Computer),
same operation (per-polygon coverage of LCMAP classes 3 and 8), measured
back-to-back on the same machine.

Why rasterstats: it is the standard pure-Python alternative to ArcPy's
ZonalStatisticsAsTable, and represents the "vanilla" approach a working GIS
analyst would reach for. Both tools read the same remote COG; the difference
is exclusively in the per-pixel coverage math and the IO layer.

Key methodological notes for honest interpretation:

  - **Different fidelity.** rasterstats with `categorical=True` does
    centroid-pixel containment (a pixel either is or isn't in the polygon
    depending on its centroid). exactextract computes exact fractional
    pixel coverage analytically. Different answers; rasterstats has edge
    artifacts. We do NOT correct for this.

  - **Different IO.** Both use rasterio under the hood and therefore both
    support COG windowed reads. The difference is in how aggressively each
    library batches windows: cogsieve relies on exactextract's C++ tile
    iterator; rasterstats reads per-polygon via Python.

  - **Single pass each.** No warm-up. Server-side cold/warm state may add
    a few seconds of variance; both tools see the same conditions because
    they run back-to-back against the same signed asset URL.

Usage:
    python scripts/bench_rasterstats.py
    python scripts/bench_rasterstats.py --parcels data/sd_parcels_25k.parquet
    python scripts/bench_rasterstats.py --limit 5000   # smaller smoke test
"""

from __future__ import annotations

import time
from pathlib import Path

import geopandas as gpd
import rasterio
import typer
from rasterstats import zonal_stats
from rich.console import Console
from rich.table import Table

from cogsieve import CoverageScreen, class_coverage, lcmap_asset_url

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    parcels: Path = typer.Option(
        Path("data/sd_parcels_25k.parquet"),
        exists=True,
        help="GeoParquet of candidate polygons.",
    ),
    year: int = typer.Option(2021, help="LCMAP year to query."),
    limit: int = typer.Option(0, help="Cap parcels for a fast smoke test (0 = all)."),
) -> None:
    gdf = gpd.read_parquet(parcels)
    if limit:
        gdf = gdf.iloc[:limit].copy()
    console.print(f"loaded [bold]{len(gdf):,}[/bold] candidate polygons")

    bbox = tuple(gdf.to_crs("EPSG:4326").total_bounds)
    raster_url = lcmap_asset_url(year=year, bbox=bbox)
    console.print(f"LCMAP {year} asset resolved against bbox {tuple(round(x, 3) for x in bbox)}")

    with rasterio.open(raster_url) as src:
        raster_crs = src.crs
    polygons_in_raster_crs = gdf.to_crs(raster_crs)

    # ----- cogsieve --------------------------------------------------------
    screen = CoverageScreen(
        name="lcmap_buildable",
        raster=raster_url,
        pass_classes={3: "grass_shrub", 8: "barren"},
        track_classes={1: "developed", 2: "cropland", 4: "tree_cover", 5: "water", 6: "wetlands"},
        min_coverage=0.60,
    )
    console.print("\n[bold cyan]Running cogsieve (exactextract + COG range reads) ...[/bold cyan]")
    t0 = time.perf_counter()
    cs_result = class_coverage(gdf, screen)
    t_cogsieve = time.perf_counter() - t0
    cogsieve_pass = cs_result[screen.keep_column].sum()
    console.print(f"  cogsieve done in [bold]{t_cogsieve:.1f}s[/bold] ({cogsieve_pass:,} polygons pass)")

    # ----- rasterstats -----------------------------------------------------
    console.print(
        "\n[bold magenta]Running rasterstats "
        "(categorical zonal_stats, centroid-pixel) ...[/bold magenta]"
    )
    t0 = time.perf_counter()
    rs_result = zonal_stats(
        polygons_in_raster_crs,
        raster_url,
        categorical=True,
        all_touched=False,
        nodata=0,
    )
    t_rasterstats = time.perf_counter() - t0

    rs_pass = 0
    for row in rs_result:
        total = sum(row.values()) if row else 0
        if total == 0:
            continue
        buildable = row.get(3, 0) + row.get(8, 0)
        if buildable / total >= 0.60:
            rs_pass += 1
    console.print(f"  rasterstats done in [bold]{t_rasterstats:.1f}s[/bold] ({rs_pass:,} polygons pass)")

    # ----- summary table ---------------------------------------------------
    ratio = t_rasterstats / t_cogsieve if t_cogsieve else float("inf")
    pass_delta = abs(cogsieve_pass - rs_pass)

    table = Table(title=f"cogsieve vs rasterstats - LCMAP buildable screen, {len(gdf):,} parcels")
    table.add_column("tool")
    table.add_column("wall clock", justify="right")
    table.add_column("throughput (parcels/sec)", justify="right")
    table.add_column("# pass", justify="right")
    table.add_row(
        "cogsieve",
        f"{t_cogsieve:.1f} s",
        f"{len(gdf) / t_cogsieve:,.0f}",
        f"{cogsieve_pass:,}",
    )
    table.add_row(
        "rasterstats",
        f"{t_rasterstats:.1f} s",
        f"{len(gdf) / t_rasterstats:,.0f}",
        f"{rs_pass:,}",
    )
    console.print()
    console.print(table)
    console.print()
    console.print(
        f"[bold]Speed ratio:[/bold] cogsieve is [bold green]{ratio:.1f}x[/bold green] faster on this run."
    )
    console.print(
        f"[dim]Pass-count delta: {pass_delta:,} polygons. Differs because rasterstats uses "
        "centroid-pixel containment; cogsieve computes exact fractional coverage.[/dim]"
    )


if __name__ == "__main__":
    app()