# Streamlit demo data

Pre-computed coverage fractions used by the [Streamlit demo app](../streamlit_app.py). Each parquet is the cached output of one cogsieve screen, written by `cogsieve.run_screens()` to its `cache_dir`. The app reads these files and re-applies threshold filters live as the user moves the sliders; only the boolean `pass_frac >= threshold` comparison recomputes.

| File | Content |
|---|---|
| `solar_lcmap_fractions.parquet` | 25,000 San Diego County parcels with per-class LCMAP coverage fractions. Output of the `lcmap_buildable` screen. |
| `solar_slope_fractions.parquet` | The LCMAP survivors (768 parcels) with per-class slope-bin coverage fractions. Output of the `slope_low` screen run on the survivors. |
| `tree_low_canopy_fractions.parquet` | 6,591 LA County census block groups with IO LULC Trees-class fractions. Output of the `low_canopy` screen (inverted). |
| `tree_urban_context_fractions.parquet` | The low-canopy survivors with IO LULC Built-Area fractions. Output of the `urban_context` screen. |
| `wildfire_recent_burn_fractions.parquet` | 25,000 San Diego County parcels with MTBS 2007 burn-severity class fractions. Output of the `recent_burn` screen. |

To rebuild from scratch:

```bash
# Solar siting (San Diego)
python scripts/fetch_san_diego_parcels.py --limit 25000
python scripts/build_slope_cog.py
python -m demos.solar_siting.run \
    --parcels data/sd_parcels_25k.parquet \
    --slope-raster data/san_diego_slope_classes.tif \
    --cache .cache/solar25k
cp .cache/solar25k/lcmap_buildable*.parquet streamlit_data/solar_lcmap_fractions.parquet
cp .cache/solar25k/slope_low*.parquet     streamlit_data/solar_slope_fractions.parquet

# Tree equity (LA County)
python scripts/fetch_la_block_groups.py
python -m demos.tree_equity.run \
    --blocks data/la_county_block_groups.parquet \
    --canopy-threshold 0.05 --urban-threshold 0.70 \
    --cache .cache/tree
cp .cache/tree/low_canopy*.parquet     streamlit_data/tree_low_canopy_fractions.parquet
cp .cache/tree/urban_context*.parquet  streamlit_data/tree_urban_context_fractions.parquet

# Wildfire WUI (San Diego, 2007 Witch Fire)
python -m demos.wildfire_wui.run \
    --parcels data/sd_parcels_25k.parquet \
    --burn-year 2007 --burn-threshold 0.01 \
    --cache .cache/wildfire
cp .cache/wildfire/recent_burn*.parquet streamlit_data/wildfire_recent_burn_fractions.parquet
```
