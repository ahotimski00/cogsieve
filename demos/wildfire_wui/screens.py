"""Wildfire wildland-urban-interface (WUI) risk screens.

Goal: flag parcels in the WUI that are exposed to high-hazard fuels and have
recently burned or sit adjacent to recent burn perimeters. Output is a
prioritized list for defensible-space outreach or insurance review.

Pipeline:
  1. High-hazard fuels: LANDFIRE Fire Behavior Fuel Model (FBFM40), keep
     parcels with substantial cover in the high-spread / high-intensity
     fuel classes (timber-understory, shrub, slash-blowdown).
  2. Recent burn footprint: MTBS burn severity raster, keep parcels with
     ANY moderate-or-higher severity coverage in the last N years (this
     uses a single-stage threshold of 5%; tweakable in config).

Both screens look at the same parcel polygons; the second narrows the
high-fuel set to those with documented recent fire activity.
"""

from __future__ import annotations

from cogsieve import CoverageScreen

LANDFIRE_FBFM40_COG = "https://example.com/data/landfire_fbfm40_2022.tif"
MTBS_SEVERITY_COG = "https://example.com/data/mtbs_severity_2010_2023.tif"


# LANDFIRE FBFM40 codes (selected high-hazard models):
#   122 = GS2 moderate grass-shrub
#   142 = SH2 shrub
#   145 = SH5 high-load dry-climate shrub
#   162 = TU2 moderate-load timber-grass-shrub
#   165 = TU5 very high-load dry-climate timber-shrub
#   183 = TL3 moderate-load conifer litter
#   202 = SB2 moderate-load activity fuel
# This is illustrative - tune to local fire history before shipping.

WILDFIRE_WUI_SCREENS = [
    CoverageScreen(
        name="high_hazard_fuels",
        raster=LANDFIRE_FBFM40_COG,
        pass_classes={
            142: "sh2_shrub",
            145: "sh5_high_load_shrub",
            162: "tu2_timber_understory",
            165: "tu5_dry_timber_shrub",
            202: "sb2_activity_fuel",
        },
        track_classes={
            122: "gs2_grass_shrub",
            183: "tl3_conifer_litter",
        },
        min_coverage=0.30,
    ),

    # MTBS severity:
    #   1 = unburned/low, 2 = low, 3 = moderate, 4 = high, 5 = increased greenness, 6 = mask
    # Keep parcels with >=5% moderate or high severity coverage.
    CoverageScreen(
        name="recent_burn",
        raster=MTBS_SEVERITY_COG,
        pass_classes={3: "moderate", 4: "high"},
        track_classes={1: "unburned_low", 2: "low"},
        min_coverage=0.05,
    ),
]
