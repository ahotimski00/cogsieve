"""Wildfire wildland-urban-interface (WUI) risk screens.

Goal: flag parcels in the WUI that are exposed to high-hazard fuels and/or sit
on a recent burn footprint. Output is a prioritized list for defensible-space
outreach, insurance review, or planning department coordination.

Pipeline:
  1. Recent burn (cloud-native): MTBS annual burn-severity raster from
     Planetary Computer. Keep parcels with ANY moderate-or-high severity
     coverage. Single-year for simplicity (mosaic-by-year is a TODO).
  2. High-hazard fuels (optional, v2): LANDFIRE FBFM40 fuel models from a
     locally-built COG (see scripts/build_landfire_cog.py). Keep parcels
     with substantial cover in the high-intensity fuel classes.

MTBS class codes (see cogsieve.io.MTBS_CLASS_NAMES):
    1 = unburned to low
    2 = low severity
    3 = moderate severity
    4 = high severity
    5 = increased greenness
    6 = mask / cloud / artifact

LANDFIRE FBFM40 class codes (selected high-hazard models used here):
    122 = GS2 moderate grass-shrub
    142 = SH2 shrub
    145 = SH5 high-load dry-climate shrub
    162 = TU2 moderate-load timber-grass-shrub
    165 = TU5 very high-load dry-climate timber-shrub
    183 = TL3 moderate-load conifer litter
    202 = SB2 moderate-load activity fuel
"""

from __future__ import annotations

from pathlib import Path

from cogsieve import CoverageScreen, mtbs_asset_url


def build_wildfire_screens(
    burn_year: int,
    bbox: tuple[float, float, float, float],
    burn_threshold: float = 0.01,
    landfire_raster: str | Path | None = None,
    landfire_threshold: float = 0.30,
) -> list[CoverageScreen]:
    """Build the wildfire-WUI screen stack for an AOI.

    bbox is (minx, miny, maxx, maxy) in EPSG:4326.
    burn_year: MTBS year to query (collection covers 1984-2018).
    burn_threshold: parcels with at least this fraction of moderate-or-high
      severity pixels are flagged (default 1% - any non-trivial burn).
    landfire_raster: optional path to an AOI-clipped LANDFIRE FBFM40 COG
      (build with scripts/build_landfire_cog.py). When set, adds a second
      screen keeping parcels with substantial high-hazard fuel coverage.
    landfire_threshold: parcels with at least this fraction of high-hazard
      fuel pixels are kept (default 30%).
    """
    mtbs_url = mtbs_asset_url(year=burn_year, bbox=bbox)

    screens: list[CoverageScreen] = [
        CoverageScreen(
            name="recent_burn",
            raster=mtbs_url,
            pass_classes={3: "moderate", 4: "high"},
            track_classes={
                1: "unburned_low",
                2: "low",
                5: "increased_greenness",
                6: "mask",
            },
            min_coverage=burn_threshold,
        ),
    ]
    if landfire_raster:
        screens.append(
            CoverageScreen(
                name="high_hazard_fuels",
                raster=str(landfire_raster),
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
                min_coverage=landfire_threshold,
            )
        )
    return screens
