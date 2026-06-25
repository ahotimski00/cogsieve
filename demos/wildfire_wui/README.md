# Wildfire WUI demo

Prioritize parcels in the wildland-urban interface that combine high-hazard fuels with a recent burn footprint.

## The funnel

| Stage | Raster | Keep if | Threshold |
|---|---|---|---|
| 1. High-hazard fuels | LANDFIRE FBFM40 | parcel has substantial cover in high-spread/high-intensity fuel models | >= 30% |
| 2. Recent burn | MTBS severity (2010-2023 mosaic) | parcel has any moderate-or-high severity pixels | >= 5% |

Config in [screens.py](screens.py). Fuel model codes are LANDFIRE FBFM40; severity codes are MTBS standard.

## Run

```bash
python -m demos.wildfire_wui.run \
    --parcels data/wui_parcels.parquet \
    --out output/wui_risk.parquet
```

## Data sources

- **Parcels**: any state or county parcel feed clipped to the WUI boundary (USFS SILVIS Lab publishes a national WUI polygon).
- **LANDFIRE FBFM40**: Fire Behavior Fuel Model, 30m, CONUS, available as COG from LANDFIRE.
- **MTBS**: Monitoring Trends in Burn Severity, annual severity rasters mosaicked into a single multi-year COG.

## Why this is a good portfolio piece

The two rasters answer different questions (potential vs. realized) and the threshold cutoffs encode policy choices (what counts as "high-hazard"? what counts as "recently burned"?). Putting both into `CoverageScreen` instances and stacking them in a pipeline lets you tweak thresholds independently and see the funnel attrition stage by stage. That's a more honest presentation of fire risk than a single composite score.
