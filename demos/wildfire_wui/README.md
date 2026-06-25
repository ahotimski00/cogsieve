# Wildfire WUI demo

Flag parcels in the wildland-urban interface (WUI) that sit on a recent burn footprint, optionally combined with high-hazard surface fuels.

## The funnel

| Stage | Raster | Keep if | Threshold | Status |
|---|---|---|---|---|
| 1. Recent burn | MTBS annual burn-severity (Planetary Computer COG) | parcel has any moderate-or-high severity pixels | >= 1% | wired |
| 2. High-hazard fuels | LANDFIRE FBFM40 (locally-built COG, optional) | parcel has substantial high-intensity fuel cover | >= 30% | wired (build script + optional flag) |

Config in [screens.py](screens.py). The MTBS screen is cloud-native (reads windowed pixels directly from the Planetary Computer COG via HTTP range requests); LANDFIRE requires a one-time manual download because the LANDFIRE.gov portal has anti-bot protections.

## Run

```bash
# Burn-only (works out of the box):
python -m demos.wildfire_wui.run \
    --parcels data/sd_parcels_25k.parquet \
    --burn-year 2007 \
    --out output/sd_wildfire_2007.parquet

# With LANDFIRE fuels (after one-time manual download from landfire.gov):
python scripts/build_landfire_cog.py \
    --src /path/to/LC22_F40_220.tif \
    --bbox -117.281 32.544 -116.935 33.406 \
    --out data/san_diego_fbfm40.tif

python -m demos.wildfire_wui.run \
    --parcels data/sd_parcels_25k.parquet \
    --burn-year 2007 \
    --landfire-raster data/san_diego_fbfm40.tif \
    --out output/sd_wildfire_2007_full.parquet
```

## Benchmark

San Diego County, 25,000 parcels, single screen (MTBS 2007 burn severity):

```
loaded 25,000 candidate parcels
resolved 1 screen(s); burn year 2007
running screen recent_burn on 25,000 polygons
  kept 45 / dropped 24,955 (0.2% pass rate)
Wildfire WUI funnel (12.1s wall clock)
throughput: 2,070 parcels/sec over 1 screen(s)
```

2007 was the Witch Fire year (one of the largest in San Diego County history, burned ~200,000 acres east of Escondido and Ramona). The 45 flagged parcels in the 25k smoke-test subset are mostly inland mountain parcels that intersected the moderate-or-high severity footprint. For the full county-wide run (1.08M parcels) the count would scale roughly proportionally.

## Choosing a burn year

MTBS coverage on Planetary Computer runs 1984-2018. For San Diego County, the most informative years are:

| Year | Fire | Notes |
|---|---|---|
| 2003 | Cedar Fire | ~273,000 acres, largest in CA history at the time |
| 2007 | Witch Fire | ~200,000 acres; tested in benchmark above |
| 2014 | Bernardo / Cocos / Poinsettia | suite of May 2014 wildfires |
| 2017 | Lilac Fire | December 2017 (Thomas was in Ventura) |

Picking a quiet year like 2018 will return zero flagged parcels for San Diego — that's not a bug, that's MTBS reporting that no significant SD fires hit that year.

## Multi-year mosaicking (TODO)

For a portfolio-grade workflow, the right operator is "any moderate-or-high severity in the last 10 years." That requires mosaicking multiple MTBS annual COGs into a single "max severity per pixel" raster. Tracked as a TODO; the cloud-native read pattern already used by the v1 screen extends straightforwardly: pull N annual items from the same STAC search, read windowed across all of them, take per-pixel max.

## Data sources

- **Parcels**: SanGIS Parcels FeatureServer (reused from the solar demo).
- **MTBS**: Monitoring Trends in Burn Severity via Microsoft Planetary Computer (collection `mtbs`). 30m annual CONUS-wide burn-severity COGs, 1984-2018. Cloud-native via STAC, anonymous read works.
- **LANDFIRE FBFM40**: USGS LANDFIRE 2022 Scott and Burgan 40 Fire Behavior Fuel Models, 30m CONUS. Distributed via [landfire.gov](https://landfire.gov/version_download.php), no STAC catalog. Build script: [scripts/build_landfire_cog.py](../../scripts/build_landfire_cog.py) clips a locally-downloaded TIFF to AOI and writes a COG.
