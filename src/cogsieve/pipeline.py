"""Sequential screen pipeline with content-addressed parquet caching."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import geopandas as gpd
from rich.console import Console

from cogsieve.coverage import cache_key, class_coverage, polygon_hash
from cogsieve.screen import CoverageScreen, ScreenResult

_console = Console()


def run_screens(
    polygons: gpd.GeoDataFrame,
    screens: Iterable[CoverageScreen],
    cache_dir: Path | str | None = None,
) -> list[ScreenResult]:
    """Apply each screen in sequence, dropping polygons that fail.

    Each stage caches its output to `cache_dir` as a GeoParquet file keyed by
    (screen name, input polygon hash, classes, threshold). Re-running with the
    same inputs replays from cache.

    Returns one ScreenResult per screen. The final surviving GeoDataFrame is
    `results[-1].gdf`.
    """
    cache_path = Path(cache_dir) if cache_dir else None
    if cache_path:
        cache_path.mkdir(parents=True, exist_ok=True)

    results: list[ScreenResult] = []
    current = polygons

    for screen in screens:
        ph = polygon_hash(current)
        key = cache_key(screen, ph)
        cached = cache_path / f"{key}.parquet" if cache_path else None

        if cached and cached.exists():
            _console.print(f"[dim]cache hit: {screen.name} -> {cached.name}[/dim]")
            scored = gpd.read_parquet(cached)
        else:
            _console.print(f"running screen [bold]{screen.name}[/bold] on {len(current):,} polygons")
            scored = class_coverage(current, screen)
            if cached:
                scored.to_parquet(cached)

        keep = scored[scored[screen.keep_column]]
        drop = scored[~scored[screen.keep_column]]
        metrics = {
            "input": len(scored),
            "kept": len(keep),
            "dropped": len(drop),
            "pass_rate": (len(keep) / len(scored)) if len(scored) else 0.0,
        }
        _console.print(
            f"  kept [green]{metrics['kept']:,}[/green] / "
            f"dropped [red]{metrics['dropped']:,}[/red] "
            f"([dim]{metrics['pass_rate']:.1%} pass rate[/dim])"
        )
        results.append(ScreenResult(gdf=keep, screen=screen, metrics=metrics))
        current = keep

    return results
