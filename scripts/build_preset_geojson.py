"""Pre-render preset funnel results to disk for instant Streamlit lookup.

When the user clicks a preset button in the Streamlit demo, the app
previously had to: filter the cached fractions parquet, reproject the
survivors to EPSG:4326, build the GeoJSON dict, and send it to the
browser. For tree-equity that took 2-3 seconds even with simplified
geometries, because building 6,000 GeoJSON features is not free.

This script does all of that once, at commit time, and writes a small
JSON file per (demo, preset). The Streamlit app then checks if the
current slider values match a preset and, if so, loads the precomputed
JSON from disk in ~50 ms instead of recomputing.

Output layout:
  streamlit_data/presets/solar_default.json
  streamlit_data/presets/solar_best_candidates_only.json
  ...

Each file is:
  {
    "preset": "Default",
    "thresholds": {"lcmap_thr": 0.60, "slope_thr": 0.80},
    "input": 25000, "stage1": 768, "stage2": 113,
    "bounds": [minx, miny, maxx, maxy],
    "geojson": {"type": "FeatureCollection", "features": [...]}
  }

Re-run after any change to the source parquets or preset definitions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import geopandas as gpd
import typer
from rich.console import Console
from rich.table import Table

DATA_DIR = Path("streamlit_data")
PRESETS_DIR = DATA_DIR / "presets"


SOLAR_PRESETS: dict[str, dict[str, float]] = {
    "Best candidates only": {"lcmap_thr": 0.80, "slope_thr": 0.90},
    "Default":              {"lcmap_thr": 0.60, "slope_thr": 0.80},
    "Broad screen":         {"lcmap_thr": 0.40, "slope_thr": 0.60},
}

TREE_PRESETS: dict[str, dict[str, float]] = {
    "Severe canopy gaps": {"canopy_thr": 0.02, "urban_thr": 0.80},
    "Default":            {"canopy_thr": 0.05, "urban_thr": 0.70},
    "Broad coverage":     {"canopy_thr": 0.10, "urban_thr": 0.50},
}

WILDFIRE_PRESETS: dict[str, dict[str, float]] = {
    "Heavily burned": {"burn_thr": 0.10},
    "Default":        {"burn_thr": 0.01},
    "Any touch":      {"burn_thr": 0.001},
}

app = typer.Typer(add_completion=False)
console = Console()


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def _to_4326(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return gdf.to_crs("EPSG:4326") if gdf.crs and gdf.crs.to_epsg() != 4326 else gdf


def _solar_funnel(lcmap_thr: float, slope_thr: float) -> dict:
    lcmap = gpd.read_parquet(DATA_DIR / "solar_lcmap_fractions.parquet")
    slope = gpd.read_parquet(DATA_DIR / "solar_slope_fractions.parquet")
    stage1 = lcmap[lcmap["lcmap_buildable_pass_frac"] >= lcmap_thr]
    slope_subset = slope[slope.index.isin(stage1.index)]
    stage2 = slope_subset[slope_subset["slope_low_pass_frac"] >= slope_thr]
    final = _to_4326(stage2) if len(stage2) else stage2
    return {
        "input": int(len(lcmap)),
        "stage1": int(len(stage1)),
        "stage2": int(len(stage2)),
        "bounds": list(final.total_bounds) if len(final) else None,
        "geojson": final.__geo_interface__ if len(final) else None,
    }


def _tree_funnel(canopy_thr: float, urban_thr: float) -> dict:
    low_canopy = gpd.read_parquet(DATA_DIR / "tree_low_canopy_fractions.parquet")
    urban_ctx = gpd.read_parquet(DATA_DIR / "tree_urban_context_fractions.parquet")
    stage1 = low_canopy[low_canopy["low_canopy_pass_frac"] < canopy_thr]
    urban_subset = urban_ctx[urban_ctx.index.isin(stage1.index)]
    stage2 = urban_subset[urban_subset["urban_context_pass_frac"] >= urban_thr]
    final = _to_4326(stage2) if len(stage2) else stage2
    return {
        "input": int(len(low_canopy)),
        "stage1": int(len(stage1)),
        "stage2": int(len(stage2)),
        "bounds": list(final.total_bounds) if len(final) else None,
        "geojson": final.__geo_interface__ if len(final) else None,
    }


def _wildfire_funnel(burn_thr: float) -> dict:
    burn = gpd.read_parquet(DATA_DIR / "wildfire_recent_burn_fractions.parquet")
    survivors = burn[burn["recent_burn_pass_frac"] >= burn_thr]
    final = _to_4326(survivors) if len(survivors) else survivors
    return {
        "input": int(len(burn)),
        "stage1": int(len(survivors)),
        "bounds": list(final.total_bounds) if len(final) else None,
        "geojson": final.__geo_interface__ if len(final) else None,
    }


def _write_preset(demo: str, preset: str, thresholds: dict, result: dict) -> Path:
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    out = PRESETS_DIR / f"{demo}_{_slug(preset)}.json"
    payload = {"preset": preset, "thresholds": thresholds, **result}
    out.write_text(json.dumps(payload))
    return out


@app.command()
def main() -> None:
    table = Table(title="Pre-rendered preset GeoJSON")
    table.add_column("file")
    table.add_column("survivors", justify="right")
    table.add_column("size (KB)", justify="right")

    for preset_name, thresholds in SOLAR_PRESETS.items():
        result = _solar_funnel(**thresholds)
        path = _write_preset("solar", preset_name, thresholds, result)
        survivors = result.get("stage2", result.get("stage1", 0))
        table.add_row(path.name, f"{survivors:,}", f"{path.stat().st_size / 1024:.1f}")

    for preset_name, thresholds in TREE_PRESETS.items():
        result = _tree_funnel(**thresholds)
        path = _write_preset("tree", preset_name, thresholds, result)
        survivors = result.get("stage2", result.get("stage1", 0))
        table.add_row(path.name, f"{survivors:,}", f"{path.stat().st_size / 1024:.1f}")

    for preset_name, thresholds in WILDFIRE_PRESETS.items():
        result = _wildfire_funnel(**thresholds)
        path = _write_preset("wildfire", preset_name, thresholds, result)
        survivors = result.get("stage1", 0)
        table.add_row(path.name, f"{survivors:,}", f"{path.stat().st_size / 1024:.1f}")

    console.print(table)


if __name__ == "__main__":
    app()