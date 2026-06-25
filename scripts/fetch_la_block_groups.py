"""Fetch Census 2020 block groups for LA County (FIPS 06037) to GeoParquet.

Hits the Census Bureau's TIGERweb ArcGIS REST service. LA County has 6,591
block groups, well under the service's 100k row limit, so this is a single
request with no pagination.

Usage:
    python scripts/fetch_la_block_groups.py
    python scripts/fetch_la_block_groups.py --state 06 --county 037 --out data/foo.parquet
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import requests
import typer
from rich.console import Console
from shapely.geometry import shape

SERVICE = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services"
    "/Census2020/tigerWMS_Census2020/MapServer/8"
)
KEEP_FIELDS = ["GEOID", "STATE", "COUNTY", "TRACT", "BLKGRP", "POP100", "HU100", "AREALAND"]

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    state: str = typer.Option("06", help="2-digit state FIPS (default: 06 = California)."),
    county: str = typer.Option("037", help="3-digit county FIPS (default: 037 = Los Angeles)."),
    out: Path = typer.Option(
        Path("data/la_county_block_groups.parquet"),
        help="Output GeoParquet path.",
    ),
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)

    params = {
        "where": f"STATE='{state}' AND COUNTY='{county}'",
        "outFields": ",".join(KEEP_FIELDS),
        "f": "geojson",
        "outSR": "4326",
    }
    console.print(f"querying Census TIGERweb for state={state} county={county}")
    r = requests.get(f"{SERVICE}/query", params=params, timeout=120)
    r.raise_for_status()
    payload = r.json()
    features = payload.get("features", [])
    console.print(f"received {len(features):,} block groups")

    rows = [f.get("properties", {}) for f in features]
    geoms = [shape(f["geometry"]) for f in features]
    gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")
    gdf.to_parquet(out)
    console.print(f"wrote [bold green]{out}[/bold green] ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    app()
