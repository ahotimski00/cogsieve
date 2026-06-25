"""Wildfire WUI demo: flag parcels with recent burn footprint and/or
high-hazard surface fuels.

Usage:
    python -m demos.wildfire_wui.run --parcels data/sd_parcels_25k.parquet
"""

from __future__ import annotations

import time
from pathlib import Path

import geopandas as gpd
import typer
from rich.console import Console
from rich.table import Table

from cogsieve import run_screens
from demos.wildfire_wui.screens import build_wildfire_screens

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    parcels: Path = typer.Option(..., exists=True, help="GeoParquet of WUI candidate parcels."),
    out: Path = typer.Option(Path("output/wui_risk.parquet"), help="Output GeoParquet."),
    cache: Path = typer.Option(Path(".cache/wildfire"), help="Stage cache directory."),
    burn_year: int = typer.Option(2018, help="MTBS year to query (collection covers 1984-2018)."),
    burn_threshold: float = typer.Option(
        0.01, help="Fraction of moderate-or-high severity pixels required to flag a parcel."
    ),
    landfire_raster: Path = typer.Option(
        None,
        help="Optional AOI-clipped LANDFIRE FBFM40 COG. When set, adds the fuel-hazard screen.",
    ),
    landfire_threshold: float = typer.Option(
        0.30, help="Fraction of high-hazard fuel pixels required to flag a parcel."
    ),
) -> None:
    gdf = gpd.read_parquet(parcels)
    console.print(f"loaded [bold]{len(gdf):,}[/bold] candidate parcels")

    bounds = tuple(gdf.to_crs("EPSG:4326").total_bounds)
    screens = build_wildfire_screens(
        burn_year=burn_year,
        bbox=bounds,
        burn_threshold=burn_threshold,
        landfire_raster=landfire_raster,
        landfire_threshold=landfire_threshold,
    )
    console.print(f"resolved [bold]{len(screens)}[/bold] screen(s); burn year [bold]{burn_year}[/bold]")

    t0 = time.perf_counter()
    results = run_screens(gdf, screens, cache_dir=cache)
    elapsed = time.perf_counter() - t0

    table = Table(title=f"Wildfire WUI funnel ({elapsed:.1f}s wall clock)")
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
    console.print(f"wrote [bold]{len(results[-1].gdf):,}[/bold] flagged parcels -> {out}")
    console.print(
        f"[dim]throughput: {len(gdf) / elapsed:,.0f} parcels/sec over {len(screens)} screen(s)[/dim]"
    )


if __name__ == "__main__":
    app()
