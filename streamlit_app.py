"""Streamlit demo: cogsieve solar-siting funnel with live threshold tuning.

The expensive work (windowed COG reads + exactextract zonal stats) has been
done offline and cached as GeoParquet in `streamlit_data/`. This app reads
those cached per-class fractions and re-applies the thresholds at interactive
speed - so moving a slider re-filters 25,000 parcels in milliseconds.

Deploy on Streamlit Community Cloud:
  https://share.streamlit.io
  Repo: ahotimski00/cogsieve
  Main file: streamlit_app.py
  Python version: 3.11+
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pydeck as pdk
import streamlit as st

LCMAP_PARQUET = Path("streamlit_data/solar_lcmap_fractions.parquet")
SLOPE_PARQUET = Path("streamlit_data/solar_slope_fractions.parquet")

st.set_page_config(
    page_title="cogsieve - Solar Siting Demo",
    page_icon=":sunny:",
    layout="wide",
)


@st.cache_data
def load_cached_fractions() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    lcmap = gpd.read_parquet(LCMAP_PARQUET)
    slope = gpd.read_parquet(SLOPE_PARQUET)
    return lcmap, slope


lcmap, slope = load_cached_fractions()

st.title(":sunny: cogsieve solar-siting demo")
st.markdown(
    "Filter San Diego County parcels for utility-scale solar by stacking two "
    "raster-coverage screens. Use the sliders to retune thresholds; the funnel "
    "and map update in real time because the per-class coverage fractions are "
    "cached - only the boolean threshold gets recomputed."
)

# ----- sidebar controls ---------------------------------------------------
with st.sidebar:
    st.header("Thresholds")
    lcmap_thr = st.slider(
        "LCMAP buildable (grass/shrub + barren) - minimum % of parcel",
        min_value=0.0, max_value=1.0, value=0.60, step=0.05,
        help="Parcels with at least this fraction in LCMAP class 3 (grass/shrub) "
             "or class 8 (barren) pass the buildable-land-cover screen.",
    )
    slope_thr = st.slider(
        "Slope - minimum % of parcel under 5% grade",
        min_value=0.0, max_value=1.0, value=0.80, step=0.05,
        help="Parcels with at least this fraction in the 0-2% or 2-5% slope bins "
             "pass the slope screen.",
    )

    st.divider()
    st.caption(
        f"Dataset: {len(lcmap):,} San Diego County parcels, "
        "USGS LCMAP 2021 + 3DEP-derived slope COG. "
        "Re-thresholding is free because fractions are pre-computed."
    )

# ----- apply thresholds ---------------------------------------------------
lcmap_pass = lcmap["lcmap_buildable_pass_frac"] >= lcmap_thr
stage1 = lcmap[lcmap_pass]

# Slope cache only contains the original LCMAP survivors (the funnel ran
# slope only on those). Join slope fractions back onto whichever parcels
# match (intersection by index).
slope_subset = slope[slope.index.isin(stage1.index)]
slope_pass = slope_subset["slope_low_pass_frac"] >= slope_thr
stage2 = slope_subset[slope_pass]

# ----- funnel stats -------------------------------------------------------
col1, col2, col3 = st.columns(3)
col1.metric(
    "Input parcels",
    f"{len(lcmap):,}",
    help="Total candidate parcels in the cached dataset.",
)
col2.metric(
    "Pass LCMAP buildable",
    f"{len(stage1):,}",
    delta=f"{100 * len(stage1) / len(lcmap):.1f}% of input",
    delta_color="off",
)
col3.metric(
    "Pass slope",
    f"{len(stage2):,}",
    delta=f"{100 * len(stage2) / max(len(stage1), 1):.1f}% of LCMAP survivors",
    delta_color="off",
)

# ----- map view -----------------------------------------------------------
st.subheader("Suitable parcels")

if len(stage2) == 0:
    st.warning(
        "No parcels pass both screens at these thresholds. Try lowering the "
        "LCMAP threshold below 60% or the slope threshold below 80%."
    )
else:
    # Reproject to WGS84 for pydeck.
    final = stage2.to_crs("EPSG:4326")
    layer = pdk.Layer(
        "GeoJsonLayer",
        data=final.__geo_interface__,
        filled=True,
        get_fill_color=[34, 197, 94, 160],
        get_line_color=[34, 197, 94, 255],
        line_width_min_pixels=1,
        pickable=True,
    )
    centroid = final.geometry.union_all().centroid
    view = pdk.ViewState(
        latitude=centroid.y,
        longitude=centroid.x,
        zoom=10,
        pitch=0,
    )
    st.pydeck_chart(
        pdk.Deck(
            map_style="light",
            initial_view_state=view,
            layers=[layer],
            tooltip={"text": "APN: {APN}"},
        )
    )

# ----- footer -------------------------------------------------------------
with st.expander("How this works"):
    st.markdown(
        """
The expensive work is **not happening live**. When the project was built,
two screens were run once against:

- **USGS LCMAP CONUS** read windowed directly from a Cloud-Optimized GeoTIFF
  on Microsoft Planetary Computer (no scene download, just HTTP range
  requests)
- A **3DEP-derived slope COG** built once for San Diego County

The output of that one-time run is a GeoParquet (the cached file in
`streamlit_data/`) with per-class coverage fractions for every parcel.
This app reads that file and lets you retune the thresholds.

Re-running the screens with different rasters or AOIs requires running
the actual `cogsieve.run_screens()` pipeline (~12 seconds for 25k parcels).
The slider re-filtering you see here only recomputes the boolean
`pass_frac >= threshold` comparison, which is essentially free.

That two-step pattern - **compute coverage once, threshold many times** -
is the actual workflow advantage of cogsieve over rerun-the-whole-thing
GIS scripts.
        """
    )
