"""Wildfire WUI demo.

Usage:
    python -m demos.wildfire_wui.run --parcels path/to/parcels.parquet --out output/wui_risk.parquet
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import typer
from rich.console import Console
from rich.table import Table

from cogsieve import run_screens
from demos.wildfire_wui.screens import WILDFIRE_WUI_SCREENS

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    parcels: Path = typer.Option(..., exists=True, help="GeoParquet of WUI candidate parcels."),
    out: Path = typer.Option(Path("output/wui_risk.parquet"), help="Output GeoParquet."),
    cache: Path = typer.Option(Path(".cache/wildfire"), help="Stage cache directory."),
) -> None:
    gdf = gpd.read_parquet(parcels)
    console.print(f"loaded [bold]{len(gdf):,}[/bold] WUI parcels")

    results = run_screens(gdf, WILDFIRE_WUI_SCREENS, cache_dir=cache)

    table = Table(title="WUI risk funnel")
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
    console.print(f"wrote [bold]{len(results[-1].gdf):,}[/bold] high-risk WUI parcels -> {out}")


if __name__ == "__main__":
    app()
