"""Tree-equity demo: find low-canopy urban blocks for planting prioritization.

Usage:
    python -m demos.tree_equity.run --blocks data/la_county_block_groups.parquet
"""

from __future__ import annotations

import time
from pathlib import Path

import geopandas as gpd
import typer
from rich.console import Console
from rich.table import Table

from cogsieve import run_screens
from demos.tree_equity.screens import build_tree_equity_screens

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    blocks: Path = typer.Option(..., exists=True, help="GeoParquet of census block groups."),
    out: Path = typer.Option(
        Path("output/priority_blocks.parquet"), help="Output GeoParquet."
    ),
    cache: Path = typer.Option(Path(".cache/tree_equity"), help="Stage cache directory."),
    year: int = typer.Option(2023, help="IO LULC year (collection covers 2017-2023)."),
    canopy_threshold: float = typer.Option(
        0.20, help="Tree-coverage fraction below which a block is flagged."
    ),
    urban_threshold: float = typer.Option(
        0.60, help="Built-area fraction required to count as 'urban' context."
    ),
) -> None:
    gdf = gpd.read_parquet(blocks)
    console.print(f"loaded [bold]{len(gdf):,}[/bold] candidate blocks")

    bounds = tuple(gdf.to_crs("EPSG:4326").total_bounds)
    screens = build_tree_equity_screens(
        year=year,
        bbox=bounds,
        canopy_threshold=canopy_threshold,
        urban_threshold=urban_threshold,
    )
    console.print(f"resolved [bold]{len(screens)}[/bold] screen(s) against IO LULC {year}")

    t0 = time.perf_counter()
    results = run_screens(gdf, screens, cache_dir=cache)
    elapsed = time.perf_counter() - t0

    table = Table(title=f"Tree-equity funnel ({elapsed:.1f}s wall clock)")
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
    console.print(f"wrote [bold]{len(results[-1].gdf):,}[/bold] priority blocks -> {out}")
    console.print(
        f"[dim]throughput: {len(gdf) / elapsed:,.0f} blocks/sec over {len(screens)} screen(s)[/dim]"
    )


if __name__ == "__main__":
    app()
