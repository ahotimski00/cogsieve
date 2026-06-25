"""Urban tree-equity screens.

Goal: find parcels (or census blocks) where canopy is BELOW a threshold, so they
can be prioritized for planting. This is the canonical inverted-coverage use case
- the same primitive that screens IN farmland for conservation screens OUT
canopy here.

Pipeline:
  1. Low canopy: NLCD Tree Canopy Cover (TCC) is a fractional 0-100 raster,
     reclassified to 5 bins. Keep blocks with < 20% canopy.
  2. Mostly developed: NLCD 2021 -- only keep blocks that are predominantly
     urban land cover, so we're not flagging vacant rural fields.
"""

from __future__ import annotations

from cogsieve import CoverageScreen

NLCD_TCC_BINNED_COG = "https://example.com/data/nlcd_tcc_2021_binned.tif"
NLCD_LANDCOVER_COG = "https://example.com/data/nlcd_2021_conus.tif"


TREE_EQUITY_SCREENS = [
    # Canopy is binned: 1=0-10%, 2=10-20%, 3=20-40%, 4=40-60%, 5=60%+
    # INVERT: keep blocks where the "high canopy" classes (3+4+5) are LOW.
    CoverageScreen(
        name="low_canopy",
        raster=NLCD_TCC_BINNED_COG,
        pass_classes={3: "20_to_40pct", 4: "40_to_60pct", 5: "over_60pct"},
        track_classes={1: "0_to_10pct", 2: "10_to_20pct"},
        min_coverage=0.20,
        invert=True,
    ),

    # Developed land cover - keep blocks that are mostly urban. This rules out
    # rural vacant land that "passes" the canopy screen for the wrong reason.
    CoverageScreen(
        name="urban_context",
        raster=NLCD_LANDCOVER_COG,
        pass_classes={
            21: "developed_open",
            22: "developed_low",
            23: "developed_medium",
            24: "developed_high",
        },
        min_coverage=0.60,
    ),
]
