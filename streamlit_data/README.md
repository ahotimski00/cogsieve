# Streamlit demo data

This folder holds pre-computed coverage fractions used by the [Streamlit demo app](../streamlit_app.py).

| File | Content |
|---|---|
| `solar_lcmap_fractions.parquet` | 25,000 San Diego County parcels with per-class LCMAP coverage fractions and the cached `pass_frac`. Output of the `lcmap_buildable` screen run once. |
| `solar_slope_fractions.parquet` | The LCMAP survivors (768 parcels) with per-class slope coverage fractions and the cached `pass_frac`. Output of the `slope_low` screen run once on the survivors. |

The Streamlit app reads these GeoParquet files and applies threshold filters live as the user moves the sliders. The expensive part (windowed COG reads + exactextract zonal stats) was done once when these files were produced; the slider re-thresholding is essentially free because all that changes is the boolean `pass_frac >= threshold` comparison.

To rebuild from scratch:

```bash
python scripts/fetch_san_diego_parcels.py --limit 25000
python scripts/build_slope_cog.py
python -m demos.solar_siting.run \
    --parcels data/sd_parcels_25k.parquet \
    --slope-raster data/san_diego_slope_classes.tif \
    --cache .cache/solar25k

cp .cache/solar25k/lcmap_buildable*.parquet streamlit_data/solar_lcmap_fractions.parquet
cp .cache/solar25k/slope_low*.parquet streamlit_data/solar_slope_fractions.parquet
```
