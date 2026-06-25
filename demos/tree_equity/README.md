# Tree equity demo

Find Los Angeles County census block groups that combine low tree canopy with dense urban context, as a planting-prioritization shortlist.

## The funnel

| Stage | Raster | Keep if | Threshold | Status |
|---|---|---|---|---|
| 1. Low canopy | IO LULC v2 (Planetary Computer COG) | block has LESS than threshold fraction of Trees pixels | invert, < 5% | wired |
| 2. Urban context | IO LULC v2 (same COG) | block is mostly Built Area | >= 70% | wired |

Both screens hit the same raster, which is the cheap case for the library: the second screen reuses the same windowed reads the first screen already paid for. Config in [screens.py](screens.py).

## Run

```bash
# 1. Fetch LA County block groups from Census TIGERweb (single REST call)
python scripts/fetch_la_block_groups.py

# 2. Run the screen
python -m demos.tree_equity.run \
    --blocks data/la_county_block_groups.parquet \
    --out output/la_tree_priority.parquet
```

## Benchmark

LA County, 6,591 census block groups, two screens (IO LULC 2023):

```
loaded 6,591 candidate blocks
resolved 2 screen(s) against IO LULC 2023
running screen low_canopy on 6,591 polygons
  kept 6,489 / dropped 102 (98.5% pass rate)
running screen urban_context on 6,489 polygons
  kept 6,213 / dropped 276 (95.7% pass rate)
Tree-equity funnel (52s wall clock)
throughput: 128 blocks/sec over 2 screen(s)
```

## What the result actually means

94% of LA County block groups (6,213 / 6,591) come out as dense-built blocks with under 5% tree canopy in IO LULC's 10m categorical classification. That is in fact the dominant landscape: LA is a tree desert at this measurement granularity, with notable exceptions for the Santa Monica Mountains, Hollywood Hills, and a few wealthier coastal blocks (which fail the urban-context screen because they have too much rangeland or tree class).

The throughput here (128 blocks/sec) is lower than the solar demo's 2,000 parcels/sec because census block groups are 10-100x larger polygons than tax parcels: each one requires reading many more raster windows. The wall clock is comparable (52s vs 12s) on roughly the same order of polygon-pixel-product.

## A note on raster choice

IO LULC v2 is the best free 10m global LULC available, but its categorical "Trees" class undercounts urban tree canopy. A pixel is labeled either Trees or Built Area; a city block with 15% canopy is labeled Built Area, not Trees. That's why the screen flags almost all of LA.

The proper next step is a CONUS-only NLCD TCC (Tree Canopy Cover) build, which gives fractional canopy (0-100%) per 30m pixel and would let the screen tune meaningful thresholds like "blocks with under 10% mean canopy." NLCD TCC is published by USGS MRLC but not on Planetary Computer's STAC catalog; it needs a build-once step similar to [scripts/build_slope_cog.py](../../scripts/build_slope_cog.py). That's tracked as a TODO in [screens.py](screens.py).

## Data sources

- **Block groups**: Census Bureau TIGERweb ArcGIS REST service (`Census2020/tigerWMS_Census2020/MapServer/8`). Filtered server-side by `STATE='06' AND COUNTY='037'`. No auth, no pagination needed below 100k features.
- **IO LULC v2**: Impact Observatory 10m global annual LULC via Planetary Computer (collection `io-lulc-annual-v02`). 2017-2023 coverage. Anonymous access works; subscription key bumps the rate limit.
- **NLCD TCC** (TODO): USGS MRLC, 30m, fractional canopy 0-100. To be built into a CONUS COG and hosted.

## Joining demographics

Block groups are the natural unit for joining ACS (American Community Survey, the Census Bureau's annual demographic survey) tables. Once a priority list is exported, joining income, race, age, or heat-vulnerability tables is one geopandas merge on the `GEOID` column. cogsieve stays focused on the spatial filtering; the equity narrative lives downstream.
