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

# 2. Run the screen (these thresholds reproduce the benchmark below; code defaults are 20% / 60%)
python -m demos.tree_equity.run \
    --blocks data/la_county_block_groups.parquet \
    --canopy-threshold 0.05 \
    --urban-threshold 0.70 \
    --out output/la_tree_priority.parquet
```

## Benchmark

LA County, 6,591 census block groups, two screens (IO LULC 2023), run with `--canopy-threshold 0.05 --urban-threshold 0.70`:

```
loaded 6,591 candidate blocks
resolved 2 screen(s) against IO LULC 2023
running screen low_canopy_lulc on 6,591 polygons
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

IO LULC v2 is the best free 10m global LULC available, but its categorical "Trees" class undercounts urban tree canopy. A pixel is labeled either Trees or Built Area; a city block with 15% canopy is labeled Built Area, not Trees. That's why the IO LULC screen flags almost all of LA County.

**The finer-grained alternative is NLCD TCC (Tree Canopy Cover)**, a 30m fractional canopy product (0-100% per pixel) from USDA Forest Service / MRLC. The demo's `--canopy-raster` flag accepts a pre-built canopy-bin COG, and [scripts/build_canopy_cog.py](../../scripts/build_canopy_cog.py) reclassifies an MRLC TCC TIFF into 5 canopy bins for any AOI.

Since MRLC's portal has anti-bot protections and the dataset is not on Planetary Computer, the source TIFF requires a one-time manual download. Steps:

```bash
# 1. Manually download the bundle from MRLC
#    https://www.mrlc.gov/data/nlcd-2021-usfs-tree-canopy-cover-conus
#    The ZIP is ~2 GB; unzip and locate nlcd_tcc_conus_2021_v2021-4.tif

# 2. Build the AOI-clipped canopy COG (one-time per AOI)
python scripts/build_canopy_cog.py \
    --src /path/to/nlcd_tcc_conus_2021_v2021-4.tif \
    --bbox -118.95 32.80 -117.65 34.83 \
    --out data/la_county_canopy_classes.tif

# 3. Run the tree-equity demo with the finer canopy raster
python -m demos.tree_equity.run \
    --blocks data/la_county_block_groups.parquet \
    --canopy-raster data/la_county_canopy_classes.tif \
    --out output/la_tree_priority_tcc.parquet
```

With NLCD TCC, the canopy threshold becomes meaningful: setting `--canopy-threshold 0.10` filters to "blocks where less than 10% of pixels are in the moderate-or-higher canopy bins," which actually separates Hollywood Hills from Compton.

## Data sources

- **Block groups**: Census Bureau TIGERweb ArcGIS REST service (`Census2020/tigerWMS_Census2020/MapServer/8`). Filtered server-side by `STATE='06' AND COUNTY='037'`. No auth, no pagination needed below 100k features.
- **IO LULC v2**: Impact Observatory 10m global annual LULC via Planetary Computer (collection `io-lulc-annual-v02`). 2017-2023 coverage. Anonymous access works; subscription key bumps the rate limit.
- **NLCD TCC** (TODO): USGS MRLC, 30m, fractional canopy 0-100. To be built into a CONUS COG and hosted.

## Joining demographics

Block groups are the natural unit for joining ACS (American Community Survey, the Census Bureau's annual demographic survey) tables. Once a priority list is exported, joining income, race, age, or heat-vulnerability tables is one geopandas merge on the `GEOID` column. cogsieve stays focused on the spatial filtering; the equity narrative lives downstream.
