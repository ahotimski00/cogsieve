"""Simplify tree-equity block-group geometries in streamlit_data/.

TIGER block-group polygons have hundreds of vertices following street-level
detail invisible at the demo's county-wide zoom level. Simplifying them
with Douglas-Peucker (via shapely) shrinks the GeoJSON payload 5-10x with
no visible difference on the map. Run once after data refresh; commit the
output parquets.

Solar and wildfire parquets are NOT simplified - their visible survivor
counts (113 and 45 respectively) are small, raw geometries render fine.

Usage:
    python scripts/simplify_streamlit_geometries.py
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import typer
from rich.console import Console
from rich.table import Table

DATA_DIR = Path("streamlit_data")
TREE_FILES = [
    "tree_low_canopy_fractions.parquet",
    "tree_urban_context_fractions.parquet",
]

# 0.0005 degrees ~ 55 m at LA latitude. Invisible at zoom 9-10
# (where a screen pixel is ~50-150 m), preserves block-group shape.
SIMPLIFY_TOLERANCE = 0.0005

app = typer.Typer(add_completion=False)
console = Console()


def _count_vertices(gdf: gpd.GeoDataFrame) -> int:
    def n(g):
        if g.geom_type == "Polygon":
            return len(g.exterior.coords)
        return sum(len(p.exterior.coords) for p in g.geoms)
    return int(gdf.geometry.apply(n).sum())


@app.command()
def main(
    tolerance: float = typer.Option(
        SIMPLIFY_TOLERANCE,
        help="Simplification tolerance in degrees (default ~55m at LA latitude).",
    ),
) -> None:
    table = Table(title=f"Geometry simplification (tolerance={tolerance})")
    table.add_column("file")
    table.add_column("rows", justify="right")
    table.add_column("vertices before", justify="right")
    table.add_column("vertices after", justify="right")
    table.add_column("size before (MB)", justify="right")
    table.add_column("size after (MB)", justify="right")

    for name in TREE_FILES:
        path = DATA_DIR / name
        gdf = gpd.read_parquet(path)
        size_before = path.stat().st_size / 1e6
        verts_before = _count_vertices(gdf)

        gdf.geometry = gdf.geometry.simplify(tolerance, preserve_topology=True)

        gdf.to_parquet(path)
        size_after = path.stat().st_size / 1e6
        verts_after = _count_vertices(gdf)

        table.add_row(
            name,
            f"{len(gdf):,}",
            f"{verts_before:,}",
            f"{verts_after:,}",
            f"{size_before:.2f}",
            f"{size_after:.2f}",
        )

    console.print(table)


if __name__ == "__main__":
    app()