# cogsieve

Sieve polygons by fractional class coverage of categorical rasters, read directly from Cloud-Optimized GeoTIFFs over HTTP.

```python
from cogsieve import CoverageScreen, run_screens

screens = [
    CoverageScreen(
        name="nlcd_buildable",
        raster="https://example.com/nlcd_2021_conus.tif",
        pass_classes={71: "grassland", 81: "pasture", 82: "cropland"},
        min_coverage=0.70,
    ),
    CoverageScreen(
        name="slope_low",
        raster="https://example.com/usgs_3dep_slope_class_conus.tif",
        pass_classes={1: "0_to_2pct", 2: "2_to_5pct"},
        min_coverage=0.80,
    ),
]

results = run_screens(parcels_gdf, screens, cache_dir=".cache/solar")
suitable = results[-1].gdf
```

## What it does

Given a GeoDataFrame of polygons and a categorical raster, compute the **exact fractional coverage** of each raster class per polygon (sub-pixel accurate, no rasterization artifacts), then filter polygons by a per-class threshold. Chain multiple screens to build a funnel.

## Why

The standard GIS workflow for this question is:

1. Clip the raster to your polygons.
2. Vectorize the clipped raster.
3. Pairwise-intersect the vector with the polygons.
4. Sum geodesic area of each fragment, grouped by class and polygon.
5. Divide and threshold.

That's slow, introduces rasterization artifacts at polygon edges, and requires the full raster in memory. cogsieve calls `exactextract` instead, which:

- computes exact fractional pixel coverage per polygon analytically,
- reads only the windowed pixels intersecting each polygon's bounding box,
- works directly against remote COGs via HTTP range requests.

A state-wide NLCD screen that took hours in the traditional pipeline runs in minutes here, without downloading the scene.

## Design

One dataclass carries the whole configuration for a screen:

```python
@dataclass(frozen=True)
class CoverageScreen:
    name: str
    raster: str | Path
    pass_classes: dict[int, str]
    track_classes: dict[int, str] = {}
    min_coverage: float = 0.5
    invert: bool = False
```

- `pass_classes` contribute to the threshold; `track_classes` are reported but not counted.
- `invert=True` flips the threshold direction (keep polygons BELOW coverage), enabling "find low-canopy blocks" without a separate code path.
- The pipeline caches each stage's output to GeoParquet, content-addressed by polygon hash + screen params, so re-runs are free.

See [src/cogsieve/screen.py](src/cogsieve/screen.py), [src/cogsieve/coverage.py](src/cogsieve/coverage.py), [src/cogsieve/pipeline.py](src/cogsieve/pipeline.py).

## Demos

Three demos, all on public data, all using the same primitive with different class codes and thresholds:

| Demo | Question | Screens |
|---|---|---|
| [Solar siting](demos/solar_siting/) | Where can we site utility-scale solar without paving prime farmland? | NLCD buildable + low slope + NOT prime farmland (inverted SSURGO) |
| [Tree equity](demos/tree_equity/) | Which urban blocks are below the canopy threshold and need planting? | Low canopy (inverted) + urban land-cover context |
| [Wildfire WUI](demos/wildfire_wui/) | Which WUI parcels combine high fuels with a recent burn footprint? | LANDFIRE high-hazard fuels + MTBS recent burn |

Each demo is one `screens.py` listing the `CoverageScreen` instances and a tiny `run.py` typer CLI. Adding a new domain is one config file.

## Development

```bash
pip install -e ".[dev,demos]"
pytest
ruff check .
mypy src
```

Tests are hermetic: a synthetic 4-quadrant raster fixture in `tests/conftest.py` gives ground-truth coverage values to assert against. No network, no large fixture files.

## Benchmark

Real numbers from the [solar siting demo](demos/solar_siting/) against San Diego County, on a 2024 MacBook with a residential broadband connection:

| Stage | Input | Time |
|---|---|---|
| Fetch parcels (SanGIS REST API, 8 parallel workers) | 25,000 polygons | 8.3 s |
| Build slope-class COG from 3DEP (one-time, per AOI) | 4 x 1-degree DEM tiles | 65 s |
| Solar funnel: LCMAP buildable + slope-low (two sequential screens) | 25,000 -> 113 | 12.0 s |

Inside the funnel:

```
running screen lcmap_buildable on 25,000 polygons
  kept 768 / dropped 24,232 (3.1% pass rate)
running screen slope_low on 768 polygons
  kept 113 / dropped 655 (14.7% pass rate)
```

The LCMAP screen reads windowed pixels directly from the remote COG via HTTP range requests; no scene download. The slope screen reads from a local 7.3 MB COG derived once from 3DEP. The two-screen pipeline runs at ~2,000 parcels/sec because the second screen only sees parcels that passed the first.

## Performance notes

cogsieve gets its speed from three design choices, each of which removes a category of work that traditional GIS workflows pay for:

**1. Exact fractional coverage instead of rasterize-then-intersect.**
The textbook zonal-stats workflow rasterizes the raster into vector polygons, then intersects those vectors with the input polygons, then sums geodesic area per fragment. That introduces edge artifacts (pixels half-inside a polygon get either fully counted or fully discarded depending on the snapping rule) and produces O(input_polygons x intersecting_pixels) intermediate vector features. `exactextract` computes each pixel's fractional intersection with each polygon analytically in C++, with no vectorization step. Daniel Baston's published benchmarks for the underlying algorithm show it processes well over an order of magnitude faster than the vector-intersect approach for equivalent fidelity, on the same hardware.

**2. Cloud-Optimized GeoTIFF (COG) windowed reads instead of full-scene downloads.**
A COG is laid out in internal tiles plus an overview pyramid, and HTTP servers that support range requests can serve individual tiles without serving the whole file. `rasterio` (via GDAL's `/vsicurl/` driver) issues range requests for just the tiles that intersect each polygon's bounding box. For the solar demo, that means screening 25,000 parcels against the CONUS-wide LCMAP raster (which is multiple GB) without downloading the scene: the wire reads were in the tens of megabytes, not gigabytes.

**3. Funnel pipeline with content-addressed caching.**
The pipeline drops failing polygons between stages, so each successive screen only sees the survivors. In the solar demo, the slope screen runs on 768 polygons rather than 25,000 because LCMAP already filtered to 768 buildable parcels. The cache writes each stage's output to a GeoParquet keyed by `(polygon hash, screen name, classes, threshold)`, so re-running with the same inputs is near-instant. None of this requires user-side optimization; the funnel falls out of the `run_screens` API.

The numbers above (12 s for 25k parcels through two screens) reflect all three together. A direct apples-to-apples comparison with ArcPy's `ZonalStatisticsAsTable` would require running both on the same hardware against the same data, which this repo doesn't currently do. If you want to verify the speed claim independently, the simplest control is `rasterstats.zonal_stats` (the standard pure-Python alternative): expect cogsieve to be roughly an order of magnitude faster on the same inputs, primarily from #2 and from `exactextract` being C++ rather than Python.

## Status

Three demos wired end to end on real public data:

- **Solar siting** (San Diego County): USGS LCMAP buildable + 3DEP-derived slope. 25,000 parcels in 12 seconds. See [demos/solar_siting/](demos/solar_siting/).
- **Tree equity** (LA County): IO LULC v2 low-canopy + urban-context, with optional NLCD TCC v2 upgrade. 6,591 block groups in 52 seconds. See [demos/tree_equity/](demos/tree_equity/).
- **Wildfire WUI** (San Diego County): MTBS annual burn-severity (cloud-native), with optional LANDFIRE FBFM40 fuels overlay. 25,000 parcels in 12 seconds. See [demos/wildfire_wui/](demos/wildfire_wui/).

PRs welcome.
