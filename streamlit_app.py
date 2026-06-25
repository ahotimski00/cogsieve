"""Streamlit demo: three cogsieve funnels with live threshold tuning.

Each tab shows one demo (solar siting, tree equity, wildfire WUI). The
expensive work - windowed COG reads and exactextract zonal stats - was
done once and the per-class coverage fractions are committed as small
GeoParquet files in `streamlit_data/`. Slider moves only recompute the
boolean `pass_frac >= threshold` comparison, which is essentially free.

That two-step pattern - compute coverage once, threshold many times -
is the actual workflow advantage cogsieve offers over rerun-the-whole-
thing GIS scripts.

Deploy on Streamlit Community Cloud:
  Repo: ahotimski00/cogsieve
  Main file: streamlit_app.py
  Python version: 3.11+
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pydeck as pdk
import streamlit as st

DATA_DIR = Path("streamlit_data")

st.set_page_config(
    page_title="cogsieve - interactive demos",
    page_icon=":sunny:",
    layout="wide",
)


# ============================================================================
# Cached loaders. One per file so switching tabs reuses what's already in RAM.
# ============================================================================

@st.cache_data
def _load_parquet(path: Path) -> gpd.GeoDataFrame:
    return gpd.read_parquet(path)


# ============================================================================
# Shared helpers
# ============================================================================

def render_polygon_map(
    gdf: gpd.GeoDataFrame,
    fill_color: list[int],
    line_color: list[int],
    tooltip_field: str | None = None,
    zoom: int = 10,
) -> None:
    """Render a pydeck polygon layer over the given GeoDataFrame in EPSG:4326."""
    if len(gdf) == 0:
        return
    final = gdf.to_crs("EPSG:4326") if gdf.crs and gdf.crs.to_epsg() != 4326 else gdf
    layer = pdk.Layer(
        "GeoJsonLayer",
        data=final.__geo_interface__,
        filled=True,
        get_fill_color=fill_color,
        get_line_color=line_color,
        line_width_min_pixels=1,
        pickable=True,
    )
    centroid = final.geometry.union_all().centroid
    view = pdk.ViewState(
        latitude=centroid.y,
        longitude=centroid.x,
        zoom=zoom,
        pitch=0,
    )
    tooltip = {"text": f"{tooltip_field}: " + "{" + tooltip_field + "}"} if tooltip_field else None
    st.pydeck_chart(
        pdk.Deck(
            map_style="light",
            initial_view_state=view,
            layers=[layer],
            tooltip=tooltip,
        )
    )


def render_funnel_metrics(stages: list[tuple[str, int, str]]) -> None:
    """Render N metric cards in a single row.
    Each stage is (label, count, delta_string).
    """
    cols = st.columns(len(stages))
    for col, (label, count, delta) in zip(cols, stages, strict=True):
        col.metric(label, f"{count:,}", delta=delta or None, delta_color="off")


# ============================================================================
# Demo: Solar siting (San Diego County)
# ============================================================================

def render_solar_demo() -> None:
    lcmap = _load_parquet(DATA_DIR / "solar_lcmap_fractions.parquet")
    slope = _load_parquet(DATA_DIR / "solar_slope_fractions.parquet")

    st.subheader("San Diego County, 25,000 parcels")
    st.markdown(
        "Two screens stacked: **USGS LCMAP buildable land cover** (Planetary Computer COG) "
        "and **3DEP-derived slope class** (locally-built COG). Find parcels suitable for "
        "utility-scale solar."
    )

    col_a, col_b = st.columns(2)
    with col_a:
        lcmap_thr = st.slider(
            "LCMAP buildable threshold",
            0.0, 1.0, 0.60, 0.05,
            key="solar_lcmap_thr",
            help="Keep parcels with at least this fraction in LCMAP class 3 (grass/shrub) "
                 "or class 8 (barren).",
        )
    with col_b:
        slope_thr = st.slider(
            "Slope threshold (% of parcel under 5% grade)",
            0.0, 1.0, 0.80, 0.05,
            key="solar_slope_thr",
            help="Keep parcels with at least this fraction in slope class 1 (0-2%) "
                 "or 2 (2-5%).",
        )

    stage1 = lcmap[lcmap["lcmap_buildable_pass_frac"] >= lcmap_thr]
    slope_subset = slope[slope.index.isin(stage1.index)]
    stage2 = slope_subset[slope_subset["slope_low_pass_frac"] >= slope_thr]

    render_funnel_metrics([
        ("Input parcels", len(lcmap), ""),
        (
            "Pass LCMAP buildable",
            len(stage1),
            f"{100 * len(stage1) / len(lcmap):.1f}% of input",
        ),
        (
            "Pass slope",
            len(stage2),
            f"{100 * len(stage2) / max(len(stage1), 1):.1f}% of LCMAP survivors",
        ),
    ])

    st.markdown("##### Suitable parcels")
    if len(stage2) == 0:
        st.warning("No parcels pass both screens. Try lowering one or both thresholds.")
    else:
        render_polygon_map(
            stage2,
            fill_color=[34, 197, 94, 160],
            line_color=[34, 197, 94, 255],
            tooltip_field="APN",
            zoom=10,
        )


# ============================================================================
# Demo: Tree equity (LA County block groups)
# ============================================================================

def render_tree_equity_demo() -> None:
    low_canopy = _load_parquet(DATA_DIR / "tree_low_canopy_fractions.parquet")
    urban_ctx = _load_parquet(DATA_DIR / "tree_urban_context_fractions.parquet")

    st.subheader("LA County, 6,591 census block groups")
    st.markdown(
        "Two screens stacked: **low canopy** (IO LULC Trees fraction below threshold, inverted) "
        "and **urban context** (Built Area fraction above threshold). Find block groups "
        "where planting prioritization would matter most."
    )

    col_a, col_b = st.columns(2)
    with col_a:
        canopy_thr = st.slider(
            "Canopy threshold (Trees fraction; INVERTED - keep blocks BELOW)",
            0.0, 0.20, 0.05, 0.01,
            key="tree_canopy_thr",
            help="Keep block groups where the IO LULC Trees class covers LESS than this fraction. "
                 "Low values flag more sparsely canopied blocks.",
        )
    with col_b:
        urban_thr = st.slider(
            "Urban-context threshold (Built Area fraction)",
            0.0, 1.0, 0.70, 0.05,
            key="tree_urban_thr",
            help="Keep block groups with at least this fraction in IO LULC class 7 (Built Area). "
                 "Rules out rural blocks that have no canopy because they have no people.",
        )

    stage1 = low_canopy[low_canopy["low_canopy_pass_frac"] < canopy_thr]
    urban_subset = urban_ctx[urban_ctx.index.isin(stage1.index)]
    stage2 = urban_subset[urban_subset["urban_context_pass_frac"] >= urban_thr]

    render_funnel_metrics([
        ("Input block groups", len(low_canopy), ""),
        (
            "Pass low-canopy",
            len(stage1),
            f"{100 * len(stage1) / len(low_canopy):.1f}% of input",
        ),
        (
            "Pass urban context",
            len(stage2),
            f"{100 * len(stage2) / max(len(stage1), 1):.1f}% of low-canopy survivors",
        ),
    ])

    st.markdown("##### Priority planting block groups")
    if len(stage2) == 0:
        st.warning("No block groups pass both screens. Try raising the canopy threshold or "
                   "lowering the urban-context threshold.")
    else:
        render_polygon_map(
            stage2,
            fill_color=[239, 68, 68, 110],
            line_color=[185, 28, 28, 255],
            tooltip_field="GEOID",
            zoom=9,
        )
    st.caption(
        "Note: IO LULC's categorical Trees class is conservative in urban matrices "
        "where street-tree canopy doesn't fill 10m pixels, so the funnel typically flags "
        "the majority of LA County. NLCD TCC at 30m fractional canopy is the proper v2 "
        "upgrade; see the project README."
    )


# ============================================================================
# Demo: Wildfire WUI (San Diego County, 2007 Witch Fire)
# ============================================================================

def render_wildfire_demo() -> None:
    burn = _load_parquet(DATA_DIR / "wildfire_recent_burn_fractions.parquet")

    st.subheader("San Diego County, 25,000 parcels, MTBS 2007 burn-severity")
    st.markdown(
        "Single screen: **recent burn footprint**. Flag parcels with at least the threshold "
        "fraction of moderate-or-high MTBS severity pixels from the 2007 Witch Fire (one of "
        "the largest in San Diego County history)."
    )

    burn_thr = st.slider(
        "Burn-severity threshold (moderate + high pixel fraction)",
        0.0, 0.20, 0.01, 0.005,
        key="wildfire_burn_thr",
        help="Keep parcels where MTBS severity class 3 (moderate) + class 4 (high) "
             "covers at least this fraction of the parcel.",
    )

    survivors = burn[burn["recent_burn_pass_frac"] >= burn_thr]

    render_funnel_metrics([
        ("Input parcels", len(burn), ""),
        (
            "Flagged (in burn footprint)",
            len(survivors),
            f"{100 * len(survivors) / len(burn):.2f}% of input",
        ),
    ])

    st.markdown("##### Parcels with 2007 burn footprint")
    if len(survivors) == 0:
        st.warning(
            "No parcels meet the threshold. Lower it to surface the burn perimeter."
        )
    else:
        render_polygon_map(
            survivors,
            fill_color=[249, 115, 22, 160],
            line_color=[194, 65, 12, 255],
            tooltip_field="APN",
            zoom=9,
        )


# ============================================================================
# Page
# ============================================================================

st.title("cogsieve - interactive demos")
st.markdown(
    "Three real-world parcel-screening funnels, each built from the same primitive: "
    "filter polygons by fractional coverage of categorical raster classes. The expensive "
    "work was done offline and cached as GeoParquet; the sliders below only re-apply "
    "the boolean threshold, which is essentially free."
)

with st.sidebar:
    st.markdown(
        """
**cogsieve** is a Python library that filters polygons by fractional class
coverage of categorical rasters, reading windowed pixels directly from
remote Cloud-Optimized GeoTIFFs.

- :earth_americas: **Repository:** [github.com/ahotimski00/cogsieve](https://github.com/ahotimski00/cogsieve)
- :books: **Docs and demos:** see the repo README
- :scroll: **License:** MIT
        """
    )
    st.divider()
    st.caption(
        "Each demo's per-class coverage fractions are pre-computed and ship "
        "with the app as small GeoParquet files. Switching demos or moving "
        "sliders never re-runs the cogsieve pipeline; only the threshold "
        "comparison is recomputed."
    )

tab_solar, tab_tree, tab_fire = st.tabs([
    ":sunny:  Solar siting",
    ":deciduous_tree:  Tree equity",
    ":fire:  Wildfire WUI",
])

with tab_solar:
    render_solar_demo()
with tab_tree:
    render_tree_equity_demo()
with tab_fire:
    render_wildfire_demo()

with st.expander("How this works"):
    st.markdown(
        """
The library does three things to be fast:

1. **Exact fractional pixel coverage** via `exactextract` (C++), rather than the
   standard rasterize-then-intersect workflow that produces edge artifacts.
2. **Cloud-Optimized GeoTIFF windowed reads** via rasterio's `/vsicurl/` driver:
   screens against multi-GB rasters fetch only the tiles intersecting each
   polygon's bounding box. No scene download.
3. **Funnel pipeline with content-addressed caching:** the second screen only
   sees parcels that passed the first, and per-stage GeoParquet caches make
   re-runs essentially instant.

A two-screen funnel against 25,000 San Diego County parcels runs end-to-end
in about 12 seconds, including the LCMAP read from a remote COG and the
slope read from a locally-built COG.

The sliders in this app are the third point made visible: the per-class
coverage fractions are pre-computed and committed alongside the app, so
moving a slider only recomputes the boolean `pass_frac >= threshold`
comparison. Switching tabs reuses the in-memory cache.
        """
    )
