"""Streamlit demo: three cogsieve funnels with live threshold tuning.

Each tab shows one demo (solar siting, tree equity, wildfire WUI). The
expensive work - windowed COG reads and exactextract zonal stats - was
done once and the per-class coverage fractions are committed as small
GeoParquet files in `streamlit_data/`. Slider moves and preset clicks
only recompute the boolean `pass_frac >= threshold` comparison, and
the full funnel-plus-map result is cached on top so repeat preset
clicks are instant.

That two-step pattern - compute coverage once, threshold many times -
is the actual workflow advantage cogsieve offers over rerun-the-whole-
thing GIS scripts.

Deploy on Streamlit Community Cloud:
  Repo: ahotimski00/cogsieve
  Main file: streamlit_app.py
  Python version: 3.11+
"""

from __future__ import annotations

import math
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

# Hide the default Streamlit top-right "Running..." status widget so the
# inline map spinner is the only loading affordance the user sees.
st.markdown(
    """
    <style>
    div[data-testid="stStatusWidget"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================================
# Cached loaders. One per file so switching tabs reuses what's already in RAM.
# ============================================================================

@st.cache_data
def _load_parquet(path: Path) -> gpd.GeoDataFrame:
    return gpd.read_parquet(path)


# ============================================================================
# Shared map helpers
# ============================================================================

def _view_from_bounds(
    bounds: tuple[float, float, float, float] | None,
    fallback_zoom: int = 9,
) -> pdk.ViewState:
    """Fit-bounds view from a (minx, miny, maxx, maxy) bbox in EPSG:4326."""
    if not bounds:
        return pdk.ViewState(latitude=34.0, longitude=-118.0, zoom=fallback_zoom)
    minx, miny, maxx, maxy = bounds
    center_lat = (miny + maxy) / 2
    center_lon = (minx + maxx) / 2
    lon_span = max(maxx - minx, 1e-4)
    lat_span = max(maxy - miny, 1e-4)
    zoom_lon = math.log2(360 / lon_span)
    zoom_lat = math.log2(180 / lat_span)
    zoom = max(0, min(15, min(zoom_lon, zoom_lat) - 0.5))
    return pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=zoom, pitch=0)


def render_geojson_map(
    geojson: dict | None,
    bounds: tuple[float, float, float, float] | None,
    fill_color: list[int],
    line_color: list[int],
    tooltip_field: str | None = None,
    fallback_zoom: int = 9,
) -> None:
    """Render a pydeck polygon layer from a precomputed GeoJSON dict.
    Wrapped in a spinner so the loading affordance is over the map, not
    in the top nav bar."""
    if not geojson or not geojson.get("features"):
        return
    with st.spinner("Updating map..."):
        layer = pdk.Layer(
            "GeoJsonLayer",
            data=geojson,
            filled=True,
            get_fill_color=fill_color,
            get_line_color=line_color,
            line_width_min_pixels=1,
            pickable=True,
        )
        view = _view_from_bounds(bounds, fallback_zoom=fallback_zoom)
        tooltip = (
            {"text": f"{tooltip_field}: " + "{" + tooltip_field + "}"} if tooltip_field else None
        )
        st.pydeck_chart(
            pdk.Deck(
                map_style="light",
                initial_view_state=view,
                layers=[layer],
                tooltip=tooltip,
            )
        )


# ============================================================================
# Shared UI helpers
# ============================================================================

def render_funnel_metrics(stages: list[tuple[str, int, str]]) -> None:
    """Render N metric cards in a single row.
    Each stage is (label, count, delta_string)."""
    cols = st.columns(len(stages))
    for col, (label, count, delta) in zip(cols, stages, strict=True):
        col.metric(label, f"{count:,}", delta=delta or None, delta_color="off")


def render_preset_buttons(
    presets: dict[str, dict[str, float]],
    active_state_key: str,
    container_key: str,
) -> None:
    """Render a row of preset buttons. The currently-active preset is rendered
    with type=primary so the user sees which scenario is selected. Clicking
    a button writes preset values into session_state AND updates the active
    state, so the visual sticks across the rerun."""
    active = st.session_state.get(active_state_key, "")
    cols = st.columns(len(presets))
    for col, (label, values) in zip(cols, presets.items(), strict=True):
        btn_type = "primary" if label == active else "secondary"
        if col.button(
            label,
            key=f"{container_key}_btn_{label}",
            type=btn_type,
            use_container_width=True,
        ):
            for key, val in values.items():
                st.session_state[key] = val
            st.session_state[active_state_key] = label
            st.rerun()


# ============================================================================
# Demo: Solar siting (San Diego County)
# ============================================================================

SOLAR_PRESETS: dict[str, dict[str, float]] = {
    "Best candidates only":  {"solar_lcmap_thr": 0.80, "solar_slope_thr": 0.90},
    "Default":               {"solar_lcmap_thr": 0.60, "solar_slope_thr": 0.80},
    "Broad screen":          {"solar_lcmap_thr": 0.40, "solar_slope_thr": 0.60},
}


@st.cache_data
def solar_funnel(lcmap_thr: float, slope_thr: float) -> dict:
    """Return cached funnel result + final GeoJSON for given thresholds.
    Repeat calls with the same args hit the cache instantly."""
    lcmap = _load_parquet(DATA_DIR / "solar_lcmap_fractions.parquet")
    slope = _load_parquet(DATA_DIR / "solar_slope_fractions.parquet")
    stage1 = lcmap[lcmap["lcmap_buildable_pass_frac"] >= lcmap_thr]
    slope_subset = slope[slope.index.isin(stage1.index)]
    stage2 = slope_subset[slope_subset["slope_low_pass_frac"] >= slope_thr]
    geojson = None
    bounds = None
    if len(stage2) > 0:
        final = (
            stage2.to_crs("EPSG:4326")
            if stage2.crs and stage2.crs.to_epsg() != 4326
            else stage2
        )
        geojson = final.__geo_interface__
        bounds = tuple(final.total_bounds)
    return {
        "input": len(lcmap),
        "stage1": len(stage1),
        "stage2": len(stage2),
        "geojson": geojson,
        "bounds": bounds,
    }


def render_solar_demo() -> None:
    if "solar_active_preset" not in st.session_state:
        st.session_state.solar_active_preset = "Default"
    if "solar_lcmap_thr" not in st.session_state:
        st.session_state.solar_lcmap_thr = 0.60
    if "solar_slope_thr" not in st.session_state:
        st.session_state.solar_slope_thr = 0.80

    st.subheader("San Diego County, 25,000 parcels")
    st.markdown(
        "Two screens stacked: **USGS LCMAP buildable land cover** (Planetary Computer COG) "
        "and **3DEP-derived slope class** (locally-built COG). Find parcels suitable for "
        "utility-scale solar."
    )

    st.markdown("**Preset scenarios** (or fine-tune with the sliders below)")
    render_preset_buttons(SOLAR_PRESETS, "solar_active_preset", container_key="solar")

    col_a, col_b = st.columns(2)
    with col_a:
        st.slider(
            "LCMAP buildable threshold",
            0.0, 1.0, step=0.05,
            key="solar_lcmap_thr",
            help="Keep parcels with at least this fraction in LCMAP class 3 (grass/shrub) "
                 "or class 8 (barren).",
        )
    with col_b:
        st.slider(
            "Slope threshold (% of parcel under 5% grade)",
            0.0, 1.0, step=0.05,
            key="solar_slope_thr",
            help="Keep parcels with at least this fraction in slope class 1 (0-2%) "
                 "or 2 (2-5%).",
        )

    result = solar_funnel(
        st.session_state.solar_lcmap_thr,
        st.session_state.solar_slope_thr,
    )

    render_funnel_metrics([
        ("Input parcels", result["input"], ""),
        (
            "Pass LCMAP buildable",
            result["stage1"],
            f"{100 * result['stage1'] / result['input']:.1f}% of input",
        ),
        (
            "Pass slope",
            result["stage2"],
            f"{100 * result['stage2'] / max(result['stage1'], 1):.1f}% of LCMAP survivors",
        ),
    ])

    st.markdown("##### Suitable parcels (map auto-zooms to the surviving set)")
    if result["stage2"] == 0:
        st.warning("No parcels pass both screens. Try lowering one or both thresholds.")
    else:
        render_geojson_map(
            geojson=result["geojson"],
            bounds=result["bounds"],
            fill_color=[34, 197, 94, 160],
            line_color=[34, 197, 94, 255],
            tooltip_field="APN",
            fallback_zoom=10,
        )


# ============================================================================
# Demo: Tree equity (LA County block groups)
# ============================================================================

TREE_PRESETS: dict[str, dict[str, float]] = {
    "Severe canopy gaps":    {"tree_canopy_thr": 0.02, "tree_urban_thr": 0.80},
    "Default":               {"tree_canopy_thr": 0.05, "tree_urban_thr": 0.70},
    "Broad coverage":        {"tree_canopy_thr": 0.10, "tree_urban_thr": 0.50},
}


@st.cache_data
def tree_funnel(canopy_thr: float, urban_thr: float) -> dict:
    low_canopy = _load_parquet(DATA_DIR / "tree_low_canopy_fractions.parquet")
    urban_ctx = _load_parquet(DATA_DIR / "tree_urban_context_fractions.parquet")
    stage1 = low_canopy[low_canopy["low_canopy_pass_frac"] < canopy_thr]
    urban_subset = urban_ctx[urban_ctx.index.isin(stage1.index)]
    stage2 = urban_subset[urban_subset["urban_context_pass_frac"] >= urban_thr]
    geojson = None
    bounds = None
    if len(stage2) > 0:
        final = (
            stage2.to_crs("EPSG:4326")
            if stage2.crs and stage2.crs.to_epsg() != 4326
            else stage2
        )
        geojson = final.__geo_interface__
        bounds = tuple(final.total_bounds)
    return {
        "input": len(low_canopy),
        "stage1": len(stage1),
        "stage2": len(stage2),
        "geojson": geojson,
        "bounds": bounds,
    }


def render_tree_equity_demo() -> None:
    if "tree_active_preset" not in st.session_state:
        st.session_state.tree_active_preset = "Default"
    if "tree_canopy_thr" not in st.session_state:
        st.session_state.tree_canopy_thr = 0.05
    if "tree_urban_thr" not in st.session_state:
        st.session_state.tree_urban_thr = 0.70

    st.subheader("LA County, 6,591 census block groups")
    st.markdown(
        "Two screens stacked: **low canopy** (IO LULC Trees fraction below threshold, inverted) "
        "and **urban context** (Built Area fraction above threshold). Find block groups "
        "where planting prioritization would matter most."
    )

    st.markdown("**Preset scenarios** (or fine-tune with the sliders below)")
    render_preset_buttons(TREE_PRESETS, "tree_active_preset", container_key="tree")

    col_a, col_b = st.columns(2)
    with col_a:
        st.slider(
            "Canopy threshold (Trees fraction; INVERTED - keep blocks BELOW)",
            0.0, 0.20, step=0.01,
            key="tree_canopy_thr",
            help="Keep block groups where the IO LULC Trees class covers LESS than this fraction. "
                 "Low values flag more sparsely canopied blocks.",
        )
    with col_b:
        st.slider(
            "Urban-context threshold (Built Area fraction)",
            0.0, 1.0, step=0.05,
            key="tree_urban_thr",
            help="Keep block groups with at least this fraction in IO LULC class 7 (Built Area). "
                 "Rules out rural blocks that have no canopy because they have no people.",
        )

    result = tree_funnel(
        st.session_state.tree_canopy_thr,
        st.session_state.tree_urban_thr,
    )

    render_funnel_metrics([
        ("Input block groups", result["input"], ""),
        (
            "Pass low-canopy",
            result["stage1"],
            f"{100 * result['stage1'] / result['input']:.1f}% of input",
        ),
        (
            "Pass urban context",
            result["stage2"],
            f"{100 * result['stage2'] / max(result['stage1'], 1):.1f}% of low-canopy survivors",
        ),
    ])

    st.markdown("##### Priority planting block groups (map auto-zooms to the surviving set)")
    if result["stage2"] == 0:
        st.warning(
            "No block groups pass both screens. Try raising the canopy threshold or "
            "lowering the urban-context threshold."
        )
    else:
        render_geojson_map(
            geojson=result["geojson"],
            bounds=result["bounds"],
            fill_color=[239, 68, 68, 110],
            line_color=[185, 28, 28, 255],
            tooltip_field="GEOID",
            fallback_zoom=9,
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

WILDFIRE_PRESETS: dict[str, dict[str, float]] = {
    "Heavily burned":  {"wildfire_burn_thr": 0.10},
    "Default":         {"wildfire_burn_thr": 0.01},
    "Any touch":       {"wildfire_burn_thr": 0.001},
}


@st.cache_data
def wildfire_funnel(burn_thr: float) -> dict:
    burn = _load_parquet(DATA_DIR / "wildfire_recent_burn_fractions.parquet")
    survivors = burn[burn["recent_burn_pass_frac"] >= burn_thr]
    geojson = None
    bounds = None
    if len(survivors) > 0:
        final = (
            survivors.to_crs("EPSG:4326")
            if survivors.crs and survivors.crs.to_epsg() != 4326
            else survivors
        )
        geojson = final.__geo_interface__
        bounds = tuple(final.total_bounds)
    return {
        "input": len(burn),
        "stage1": len(survivors),
        "geojson": geojson,
        "bounds": bounds,
    }


def render_wildfire_demo() -> None:
    if "wildfire_active_preset" not in st.session_state:
        st.session_state.wildfire_active_preset = "Default"
    if "wildfire_burn_thr" not in st.session_state:
        st.session_state.wildfire_burn_thr = 0.01

    st.subheader("San Diego County, 25,000 parcels, MTBS 2007 burn-severity")
    st.markdown(
        "Single screen: **recent burn footprint**. Flag parcels with at least the threshold "
        "fraction of moderate-or-high MTBS severity pixels from the 2007 Witch Fire (one of "
        "the largest in San Diego County history)."
    )

    st.markdown("**Preset scenarios** (or fine-tune with the slider below)")
    render_preset_buttons(WILDFIRE_PRESETS, "wildfire_active_preset", container_key="wildfire")

    st.slider(
        "Burn-severity threshold (moderate + high pixel fraction)",
        0.0, 0.20, step=0.005,
        key="wildfire_burn_thr",
        help="Keep parcels where MTBS severity class 3 (moderate) + class 4 (high) "
             "covers at least this fraction of the parcel.",
    )

    result = wildfire_funnel(st.session_state.wildfire_burn_thr)

    render_funnel_metrics([
        ("Input parcels", result["input"], ""),
        (
            "Flagged (in burn footprint)",
            result["stage1"],
            f"{100 * result['stage1'] / result['input']:.2f}% of input",
        ),
    ])

    st.markdown("##### Parcels in the 2007 burn footprint (map auto-zooms to the surviving set)")
    if result["stage1"] == 0:
        st.warning(
            "No parcels meet the threshold. Lower it to surface the burn perimeter."
        )
    else:
        render_geojson_map(
            geojson=result["geojson"],
            bounds=result["bounds"],
            fill_color=[249, 115, 22, 160],
            line_color=[194, 65, 12, 255],
            tooltip_field="APN",
            fallback_zoom=9,
        )


# ============================================================================
# Background cache warmup
# ============================================================================

def _warm_caches() -> None:
    """Pre-populate caches for the DEFAULT preset of each demo so the first
    tab the user lands on responds instantly. Other presets warm lazily on
    first click. Adds ~1-2 seconds to the initial page load, in exchange
    for instant default-preset response across all three tabs."""
    if st.session_state.get("_caches_warmed"):
        return
    solar_funnel(0.60, 0.80)
    tree_funnel(0.05, 0.70)
    wildfire_funnel(0.01)
    st.session_state._caches_warmed = True


# ============================================================================
# Page
# ============================================================================

st.title("cogsieve - interactive demos")
st.markdown(
    "Three real-world parcel-screening funnels, each built from the same primitive: "
    "filter polygons by fractional coverage of categorical raster classes. The expensive "
    "work was done offline and cached as GeoParquet; the preset buttons and sliders below "
    "only re-apply the boolean threshold, which is essentially free. The map auto-fits "
    "to the surviving polygons after each change."
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
        "with the app as small GeoParquet files. Switching demos, clicking a "
        "preset, or moving a slider never re-runs the cogsieve pipeline; only "
        "the threshold comparison is recomputed, and the map re-fits to the "
        "new surviving set."
    )

_warm_caches()

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

The presets and sliders in this app are the third point made visible: the
per-class coverage fractions are pre-computed and committed alongside the app,
so changing thresholds only recomputes the boolean `pass_frac >= threshold`
comparison. Switching tabs reuses the in-memory cache. The map auto-fits to
the surviving polygons so you can see where they are without panning.
        """
    )