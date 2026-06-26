"""Fetch San Diego County parcels from the SanGIS FeatureServer to GeoParquet.

Paginates the ArcGIS REST FeatureServer (which limits each response to 2000
features) in parallel and writes one GeoParquet at the end. Supports a bbox
filter for fast demo subsets.

Usage:
    python scripts/fetch_san_diego_parcels.py
    python scripts/fetch_san_diego_parcels.py --bbox -117.20 32.70 -117.10 32.80
    python scripts/fetch_san_diego_parcels.py --limit 10000

The default fetch is the entire county (~1.08M parcels, ~3-5 minutes).
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import geopandas as gpd
import requests
import typer
from rich.console import Console
from rich.progress import Progress
from shapely.geometry import shape

SERVICE = (
    "https://services7.arcgis.com/3kQCXzNCo2WKILzp/arcgis/rest/services"
    "/SanGIS_Parcels/FeatureServer/0"
)
PAGE_SIZE = 2000
KEEP_FIELDS = ["APN", "PARCELID", "SITUS_JURI", "SITUS_STRE"]

app = typer.Typer(add_completion=False)
console = Console()


def _query_count(where: str, bbox: tuple[float, float, float, float] | None) -> int:
    params = {"where": where, "returnCountOnly": "true", "f": "json"}
    if bbox:
        params["geometry"] = json.dumps({
            "xmin": bbox[0], "ymin": bbox[1], "xmax": bbox[2], "ymax": bbox[3],
            "spatialReference": {"wkid": 4326},
        })
        params["geometryType"] = "esriGeometryEnvelope"
        params["inSR"] = "4326"
        params["spatialRel"] = "esriSpatialRelIntersects"
    r = requests.get(f"{SERVICE}/query", params=params, timeout=60)
    r.raise_for_status()
    return int(r.json()["count"])


def _fetch_page(
    offset: int,
    where: str,
    bbox: tuple[float, float, float, float] | None,
    fields: list[str],
) -> list[dict]:
    params = {
        "where": where,
        "outFields": ",".join(fields),
        "f": "geojson",
        "outSR": "4326",
        "resultOffset": str(offset),
        "resultRecordCount": str(PAGE_SIZE),
        "orderByFields": "FID",
    }
    if bbox:
        params["geometry"] = json.dumps({
            "xmin": bbox[0], "ymin": bbox[1], "xmax": bbox[2], "ymax": bbox[3],
            "spatialReference": {"wkid": 4326},
        })
        params["geometryType"] = "esriGeometryEnvelope"
        params["inSR"] = "4326"
        params["spatialRel"] = "esriSpatialRelIntersects"
    r = requests.get(f"{SERVICE}/query", params=params, timeout=120)
    r.raise_for_status()
    return r.json().get("features", [])


@app.command()
def main(
    out: Path = typer.Option(
        Path("data/sd_parcels_25k.parquet"),
        help="Output GeoParquet path.",
    ),
    bbox: tuple[float, float, float, float] = typer.Option(
        None,
        help="minx miny maxx maxy in EPSG:4326. Restricts the fetch to this envelope.",
    ),
    limit: int = typer.Option(
        0, help="Stop after this many parcels (0 = no limit). Useful for fast smoke tests."
    ),
    where: str = typer.Option("1=1", help="ArcGIS REST WHERE clause."),
    workers: int = typer.Option(8, help="Parallel page requests."),
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)

    total = _query_count(where, bbox)
    fetch_total = min(total, limit) if limit else total
    console.print(
        f"SanGIS reports [bold]{total:,}[/bold] matching parcels; "
        f"fetching [bold]{fetch_total:,}[/bold] in pages of {PAGE_SIZE} across {workers} workers."
    )

    offsets = list(range(0, fetch_total, PAGE_SIZE))
    features: list[dict] = []
    t0 = time.perf_counter()

    with Progress(console=console) as progress:
        task = progress.add_task("fetching", total=len(offsets))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(_fetch_page, off, where, bbox, KEEP_FIELDS): off
                for off in offsets
            }
            for fut in as_completed(futures):
                features.extend(fut.result())
                progress.update(task, advance=1)

    if limit:
        features = features[:limit]
    elapsed = time.perf_counter() - t0
    console.print(f"fetched {len(features):,} features in {elapsed:.1f}s")

    rows = []
    geoms = []
    for f in features:
        geoms.append(shape(f["geometry"]))
        rows.append(f.get("properties", {}))
    gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")
    gdf.to_parquet(out)
    console.print(f"wrote [bold green]{out}[/bold green] ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    app()
