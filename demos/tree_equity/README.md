# Tree equity demo

Find urban census blocks with low canopy cover, suitable for planting prioritization.

## The funnel

| Stage | Raster | Keep if | Threshold |
|---|---|---|---|
| 1. Low canopy | NLCD Tree Canopy Cover (binned) | block is mostly LOW canopy bins | invert, < 20% |
| 2. Urban context | NLCD 2021 land cover | block is predominantly developed | >= 60% |

The first screen is **inverted** -- this is the same primitive used elsewhere in the codebase but with `invert=True`, which flips the threshold direction. Configuration is in [screens.py](screens.py).

## Why two screens

A naive "low canopy" screen alone over-includes rural vacant land that has no canopy because it has no trees and no people. Stacking with an "urban context" screen restricts to blocks where low canopy is a planting opportunity, not a feature of the landscape. This is the kind of compositional logic that's awkward in monolithic ArcPy scripts and natural with declarative screens.

## Run

```bash
python -m demos.tree_equity.run \
    --blocks data/census_blocks_us.parquet \
    --out output/priority_blocks.parquet
```

## Data sources

- **Census blocks**: TIGER/Line via the Census FTP, converted to GeoParquet.
- **NLCD Tree Canopy Cover**: USGS, 30m, available as a COG. Binned to 5 classes for class-coverage analysis.
- **NLCD 2021 land cover**: same as solar demo.

## Joining demographics

Once priority blocks are exported, joining ACS income / race / heat-vulnerability tables is one line of geopandas. The cogsieve part stays focused on the spatial threshold; the equity narrative lives downstream where it belongs.
