"""Utility-scale solar siting screens.

v1: LCMAP land-cover screen (Planetary Computer COG, cloud-native).
v2: slope-class screen (locally-built 3DEP-derived COG; see scripts/build_slope_cog.py).
v3 (TODO): inverted SSURGO farmland screen once gNATSGO is rasterized.

LCMAP classes (see cogsieve.io.LCMAP_CLASS_NAMES):
    1 = Developed       (avoid)
    2 = Cropland        (avoid for solar - social license issue)
    3 = Grass / Shrub   (good)
    4 = Tree Cover      (avoid)
    5 = Water           (avoid)
    6 = Wetlands        (avoid)
    7 = Ice / Snow      (n/a CONUS)
    8 = Barren          (good)

Slope classes (see scripts/build_slope_cog.py):
    1 = 0-2%     (ideal)
    2 = 2-5%     (workable)
    3 = 5-10%    (marginal)
    4 = 10-20%   (no)
    5 = over 20% (no)
"""

from __future__ import annotations

from pathlib import Path

from cogsieve import CoverageScreen, lcmap_asset_url


def build_solar_screens(
    year: int,
    bbox: tuple[float, float, float, float],
    slope_raster: str | Path | None = None,
) -> list[CoverageScreen]:
    """Build the solar-siting screen stack for a given AOI.

    bbox is (minx, miny, maxx, maxy) in EPSG:4326 used to resolve the LCMAP
    STAC asset.

    slope_raster, when provided, enables the slope screen. Path to a
    pre-built slope-class COG (build with scripts/build_slope_cog.py).
    """
    lcmap_url = lcmap_asset_url(year=year, bbox=bbox)
    screens: list[CoverageScreen] = [
        CoverageScreen(
            name="lcmap_buildable",
            raster=lcmap_url,
            pass_classes={
                3: "grass_shrub",
                8: "barren",
            },
            track_classes={
                1: "developed",
                2: "cropland",
                4: "tree_cover",
                5: "water",
                6: "wetlands",
            },
            min_coverage=0.60,
        ),
    ]
    if slope_raster:
        screens.append(
            CoverageScreen(
                name="slope_low",
                raster=str(slope_raster),
                pass_classes={1: "0_to_2pct", 2: "2_to_5pct"},
                track_classes={
                    3: "5_to_10pct",
                    4: "10_to_20pct",
                    5: "over_20pct",
                },
                min_coverage=0.80,
            )
        )
    return screens
