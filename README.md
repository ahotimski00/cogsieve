# cogsieve

Sieve polygons by fractional class coverage of categorical rasters, read directly from Cloud-Optimized GeoTIFFs over HTTP.

[![ci](https://github.com/ahotimski00/cogsieve/actions/workflows/ci.yml/badge.svg)](https://github.com/ahotimski00/cogsieve/actions/workflows/ci.yml)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://cogsieve-vir5swvkd2a5fypnpyqlnn.streamlit.app/)

**Live demo:** [cogsieve.streamlit.app](https://cogsieve-vir5swvkd2a5fypnpyqlnn.streamlit.app/) - one interactive tab per demo, with threshold sliders that re-filter cached coverage fractions in milliseconds. Details under [Interactive demo](#interactive-demo).

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

That's slow, introduces rasterization artifacts at polygon edges, and requires the full raster in memory. cogsieve replaces all of it with a single `exactextract` call that computes exact fractional coverage from windowed COG reads, so a state-wide screen runs without downloading the scene. [Performance notes](#performance-notes) explains why each of those choices matters; [Benchmark](#benchmark) measures it against `rasterstats`.

## Design

One dataclass carries the whole configuration for a screen:

```python
@dataclass(frozen=True)
class CoverageScreen:
    name: str
    raster: str | Path
    pass_classes: dict[int, str]
    track_classes: dict[int, str] = field(default_factory=dict)
    min_coverage: float = 0.5
    invert: bool = False
    nodata_as_zero: bool = True
```

- `pass_classes` contribute to the threshold; `track_classes` are reported but not counted.
- `invert=True` flips the threshold direction (keep polygons BELOW coverage), enabling "find low-canopy blocks" without a separate code path.
- The pipeline caches each stage's output to GeoParquet, content-addressed by polygon hash + screen params, so re-runs replay from cache.

See [src/cogsieve/screen.py](src/cogsieve/screen.py), [src/cogsieve/coverage.py](src/cogsieve/coverage.py), [src/cogsieve/pipeline.py](src/cogsieve/pipeline.py).

## Demos

Three demos, all wired end to end on real public data, all using the same primitive with different class codes and thresholds:

| Demo | AOI | Question | Screens | Scale & time |
|---|---|---|---|---|
| [Solar siting](demos/solar_siting/) | San Diego County | Where can we site utility-scale solar without paving prime farmland? | LCMAP buildable + 3DEP-derived low slope (inverted-SSURGO farmland screen is planned) | 25,000 parcels in 12 s (2 screens) |
| [Tree equity](demos/tree_equity/) | LA County | Which urban blocks are below the canopy threshold and need planting? | IO LULC v2 low canopy (inverted) + urban land-cover context | 6,591 block groups in 52 s (2 screens) |
| [Wildfire WUI](demos/wildfire_wui/) | San Diego County (2007 Witch Fire) | Which WUI parcels sit on a recent burn footprint? | MTBS burn severity (LANDFIRE fuels optional, manual download) | 25,000 parcels in 12 s (MTBS only) |

Tree equity can optionally upgrade to NLCD TCC v2 canopy; wildfire WUI can optionally overlay LANDFIRE FBFM40 fuels.

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

Real numbers from the [solar siting demo](demos/solar_siting/) against San Diego County:

| Stage | Input | Time |
|---|---|---|
| Fetch parcels (SanGIS REST API, 8 parallel workers) | 25,000 polygons | 8.3 s |
| Build slope-class COG from 3DEP (one-time, per AOI) | 4 x 1-degree DEM tiles | 65 s |
| Solar funnel: LCMAP buildable + slope-low (two sequential screens) | 25,000 -> 113 | 12.0 s |

Conditions: Apple Silicon MacBook, exactextract 0.3.0, rasterstats 0.21.0, rasterio 1.5.0, run 2026-06. Single pass, no warm-up. TODO: re-run on a known machine and pin exact hardware (chip, RAM) and downlink bandwidth. Network-bound COG reads dominate the wall clock, so absolute times vary with bandwidth and Planetary Computer server state.

Inside the funnel:

```
running screen lcmap_buildable on 25,000 polygons
  kept 768 / dropped 24,232 (3.1% pass rate)
running screen slope_low on 768 polygons
  kept 113 / dropped 655 (14.7% pass rate)
```

The LCMAP screen reads the remote COG; the slope screen reads a local 7.3 MB COG derived once from 3DEP. End to end this two-screen funnel is 2,082 parcels/sec (25,000 parcels / 12.0 s). The single-screen LCMAP number is higher (2,330 parcels/sec) because it skips the second stage; see the [head-to-head](#head-to-head-against-rasterstats).

## Performance notes

cogsieve gets its speed from three design choices, each of which removes a category of work that traditional GIS workflows pay for:

**1. Exact fractional coverage instead of rasterize-then-intersect.**
The textbook zonal-stats workflow rasterizes the raster into vector polygons, then intersects those vectors with the input polygons, then sums geodesic area per fragment. That introduces edge artifacts (pixels half-inside a polygon get either fully counted or fully discarded depending on the snapping rule) and produces O(input_polygons x intersecting_pixels) intermediate vector features. `exactextract` computes each pixel's fractional intersection with each polygon analytically in C++, with no vectorization step. `exactextract` is the C++ implementation of this algorithm (Daniel Baston, https://github.com/isciences/exactextract). For a measured comparison on this project's data, see the [head-to-head against rasterstats](#head-to-head-against-rasterstats) below.

**2. Cloud-Optimized GeoTIFF (COG) windowed reads instead of full-scene downloads.**
A COG is laid out in internal tiles plus an overview pyramid, and HTTP servers that support range requests can serve individual tiles without serving the whole file. `rasterio` (via GDAL's `/vsicurl/` driver) issues range requests for just the tiles that intersect each polygon's bounding box. For the solar demo, that means screening 25,000 parcels against the CONUS-wide LCMAP raster (which is multiple GB) without downloading the scene: only the COG tiles intersecting each parcel's bounding box are fetched, not the full multi-GB raster.

**3. Funnel pipeline with content-addressed caching.**
The pipeline drops failing polygons between stages, so each successive screen only sees the survivors. In the solar demo, the slope screen runs on 768 polygons rather than 25,000 because LCMAP already filtered to 768 buildable parcels. The cache writes each stage's output to a GeoParquet keyed by `(polygon hash, screen name, classes, threshold)`, so re-running the same inputs replays from cache. The funnel is automatic: `run_screens` drops failing polygons between stages, with no configuration.

The numbers above (12 s for 25k parcels through two screens) reflect all three together.

### Head-to-head against `rasterstats`

`rasterstats` is the standard pure-Python zonal-stats library and represents the same workflow class as ArcPy's `ZonalStatisticsAsTable`. This is the single LCMAP screen (not the two-screen funnel), run on the same 25,000 San Diego County parcels against the same Planetary Computer LCMAP COG, back-to-back, single pass each:

| Tool | Wall clock | Throughput | Passing parcels |
|---|---|---|---|
| **cogsieve** | **10.7 s** | 2,330 parcels/sec | 768 |
| `rasterstats` | 320.0 s | 78 parcels/sec | 730 |

Same machine and library versions as the [Benchmark](#benchmark) conditions above; both tools run back-to-back in one process so they see the same network and server state.

**cogsieve is 30x faster** on this run. Both tools issued HTTP range requests against the same signed COG URL; the gap comes from `exactextract` being C++ rather than Python and from aggressive window batching. The 38-parcel pass-count delta reflects different fidelity, not a bug: `rasterstats` uses centroid-pixel containment (each pixel is either fully in or fully out of a polygon depending on where its centroid lands), while cogsieve computes exact fractional pixel coverage, so they answer slightly different questions on edge pixels.

The benchmark script is at [scripts/bench_rasterstats.py](scripts/bench_rasterstats.py); reproduce with:

```bash
pip install -e ".[bench]"   # pulls in rasterstats, which is not a core dependency
python scripts/bench_rasterstats.py --parcels data/sd_parcels_25k.parquet
```

## Interactive demo

Deployed at [cogsieve.streamlit.app](https://cogsieve-vir5swvkd2a5fypnpyqlnn.streamlit.app/) - one tab per demo (see the table above for AOIs and scale). The expensive raster reads were done once and cached; each slider move only recomputes the boolean `pass_frac >= threshold`, so re-filtering is immediate.

Run locally:

```bash
pip install -e ".[streamlit]"
streamlit run streamlit_app.py
```

**Re-deploy on Streamlit Community Cloud** (free, ~3 minutes):

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with the GitHub account that owns this repo.
2. Click **New app**, pick the `cogsieve` repo, leave branch as `main`, set "Main file path" to `streamlit_app.py`.
3. Under "Advanced settings" set Python version to **3.11** or **3.12**. Streamlit Cloud will install from `pyproject.toml` automatically; the `[streamlit]` extra holds the deps it needs.
4. Click **Deploy**. The build takes ~2 minutes (rasterio and exactextract pull GDAL wheels; no system packages needed).

The deployed app reads the small GeoParquet files committed to [streamlit_data/](streamlit_data/), so it loads instantly with no live API calls. Re-running the screens from scratch happens locally; the cloud app only re-thresholds the cached fractions.

PRs welcome.
