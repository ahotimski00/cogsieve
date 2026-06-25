"""Tree-equity demo: find low-canopy urban blocks for planting prioritization.

Usage:
    python -m demos.tree_equity.run --blocks path/to/census_blocks.parquet --out output/priority.parquet
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import typer
from rich.console import Console
from rich.table import Table

from cogsieve import run_screens
from demos.tree_equity.screens import TREE_EQUITY_SCREENS

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    blocks: Path = typer.Option(..., exists=True, help="GeoParquet of census blocks or parcels."),
    out: Path = typer.Option(Path("output/priority_blocks.parquet"), help="Output GeoParquet."),
    cache: Path = typer.Option(Path(".cache/tree_equity"), help="Stage cache directory."),
) -> None:
    gdf = gpd.read_parquet(blocks)
    console.print(f"loaded [bold]{len(gdf):,}[/bold] candidate blocks")

    results = run_screens(gdf, TREE_EQUITY_SCREENS, cache_dir=cache)

    table = Table(title="Tree-equity funnel")
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


if __name__ == "__main__":
    app()
