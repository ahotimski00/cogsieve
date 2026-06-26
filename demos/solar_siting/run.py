"""End-to-end solar siting demo.

Usage:
    python -m demos.solar_siting.run --parcels data/sd_parcels_25k.parquet
"""

from __future__ import annotations

import time
from pathlib import Path

import geopandas as gpd
import typer
from rich.console import Console
from rich.table import Table

from cogsieve import run_screens
from demos.solar_siting.screens import build_solar_screens

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    parcels: Path = typer.Option(..., exists=True, help="GeoParquet of candidate parcels."),
    out: Path = typer.Option(Path("output/solar_sites.parquet"), help="Output GeoParquet."),
    cache: Path = typer.Option(Path(".cache/solar"), help="Stage cache directory."),
    year: int = typer.Option(2021, help="LCMAP year to query (LCMAP covers 1985-2021)."),
    slope_raster: Path = typer.Option(
        None,
        help="Optional pre-built slope-class COG. If set, enables the slope screen.",
    ),
) -> None:
    gdf = gpd.read_parquet(parcels)
    console.print(f"loaded [bold]{len(gdf):,}[/bold] candidate parcels")

    bounds = tuple(gdf.to_crs("EPSG:4326").total_bounds)
    screens = build_solar_screens(year=year, bbox=bounds, slope_raster=slope_raster)
    console.print(f"resolved [bold]{len(screens)}[/bold] screen(s) against LCMAP {year}")

    t0 = time.perf_counter()
    results = run_screens(gdf, screens, cache_dir=cache)
    elapsed = time.perf_counter() - t0

    table = Table(title=f"Solar siting funnel ({elapsed:.1f}s wall clock)")
    table.add_column("stage")
    table.add_column("kept", justify="right")
    table.add_column("dropped", justify="right")
    table.add_column("pass rate", justify="right")
    for r in results:
        m = r.metrics
        table.add_row(r.screen.name, f"{m['kept']:,}", f"{m['dropped']:,}", f"{m['pass_rate']:.1%}")
    console.print(table)

    out.parent.mkdir(parents=True, exist_ok=True)
    results[-1].gdf.to_parquet(out)
    console.print(f"wrote [bold]{len(results[-1].gdf):,}[/bold] suitable parcels -> {out}")
    console.print(
        f"[dim]throughput: {len(gdf) / elapsed:,.0f} parcels/sec over {len(screens)} screen(s)[/dim]"
    )


if __name__ == "__main__":
    app()
