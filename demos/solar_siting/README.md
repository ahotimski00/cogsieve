# Solar siting demo

Find parcels suitable for utility-scale solar.

## The funnel

| Stage | Raster | Keep if | Threshold | Status |
|---|---|---|---|---|
| 1. Buildable land cover | USGS LCMAP (Planetary Computer COG) | parcel is mostly grass/shrub/barren | >= 60% | wired |
| 2. Low slope | 3DEP-derived slope-class COG | parcel is mostly 0-5% slope | >= 80% | wired |
| 3. Not prime farmland | SSURGO farmland class | parcel is NOT mostly prime farmland | invert, < 30% | TODO |

Each stage is one `CoverageScreen` instance in [screens.py](screens.py). The pipeline drops failing parcels between stages, so the slope read only happens for land-cover-passing parcels, and the farmland read only happens for the remainder.

## Run

```bash
# 1. Fetch San Diego parcels (use --limit for fast iteration, omit for the full ~1M county)
python scripts/fetch_san_diego_parcels.py --limit 25000

# 2. Build the slope COG for the SD AOI (one-time, ~60s, produces a 7 MB COG)
python scripts/build_slope_cog.py

# 3. Run the screen
python -m demos.solar_siting.run \
    --parcels data/san_diego_parcels.parquet \
    --slope-raster data/san_diego_slope_classes.tif \
    --out output/solar_sites.parquet
```

## Benchmark

San Diego County, 25,000 parcels, two screens (LCMAP buildable + slope-low):

```
loaded 25,000 candidate parcels
resolved 2 screen(s) against LCMAP 2021
running screen lcmap_buildable on 25,000 polygons
  kept 768 / dropped 24,232 (3.1% pass rate)
running screen slope_low on 768 polygons
  kept 113 / dropped 655 (14.7% pass rate)
Solar siting funnel (12.0s wall clock)
throughput: 2,082 parcels/sec over 2 screen(s)
```

Final 0.45% pass rate (113 / 25,000) is realistic for utility-scale solar in a populated coastal/mountain county. The two-screen pipeline runs in essentially the same time as the single LCMAP screen because the slope read only sees the 768 LCMAP survivors.

## Data sources

- **Parcels**: SanGIS Parcels FeatureServer (`services7.arcgis.com/3kQCXzNCo2WKILzp/.../SanGIS_Parcels/FeatureServer/0`). 1.08M parcels for San Diego County, no auth, paginated REST.
- **LCMAP**: USGS LCMAP CONUS v1.3 via Microsoft Planetary Computer (collection `usgs-lcmap-conus-v13`). 30m, annual 1985-2021. Anonymous access works; subscription key bumps the rate limit.
- **Slope**: USGS 3DEP 10m seamless DEM via Planetary Computer (collection `3dep-seamless`), mosaicked and clipped to AOI, reprojected to UTM 11N, slope computed in numpy, reclassified to 5 bins, written as a uint8 COG with DEFLATE compression. Build script: [scripts/build_slope_cog.py](../../scripts/build_slope_cog.py).
- **SSURGO farmland class** (TODO): gNATSGO mosaic, rasterized once.

## Why this design

The original workflow this library is based on runs SSURGO first because conservation cares about prime farmland. For solar siting, we want the *opposite* polarity on the same data, which is exactly what `invert=True` is for. The same `CoverageScreen` configuration that screens IN farmland for conservation screens OUT farmland for solar siting, with no code changes - only a flag.
