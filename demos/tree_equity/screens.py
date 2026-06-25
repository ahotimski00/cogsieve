"""Urban tree-equity screens.

Find census block groups (small Census geographies that aggregate to tracts)
where canopy is BELOW a threshold so they can be prioritized for planting.

This is the canonical inverted-coverage use case: same primitive that screens
IN farmland for conservation screens OUT canopy here, via `invert=True`.

Pipeline:
  1. Low canopy: IO LULC 10m global LULC v2 (Planetary Computer). Trees class
     coverage below threshold (invert=True).
  2. Urban context: same IO LULC raster, Built Area class coverage above
     threshold. Rules out rural blocks that have no canopy because they
     have no people.

Both screens hit the same COG, so the second screen costs almost nothing
to add: the read pattern is identical, the windows are the same, only the
class codes and threshold differ.

IO LULC v2 classes (see cogsieve.io.IO_LULC_CLASS_NAMES):
    1  = Water
    2  = Trees           (low fraction is the equity flag)
    4  = Flooded vegetation
    5  = Crops
    7  = Built Area      (urban context filter)
    8  = Bare ground
    9  = Snow / Ice
    10 = Clouds
    11 = Rangeland
"""

from __future__ import annotations

from pathlib import Path

from cogsieve import CoverageScreen, io_lulc_asset_urls


def build_tree_equity_screens(
    year: int,
    bbox: tuple[float, float, float, float],
    canopy_threshold: float = 0.20,
    urban_threshold: float = 0.60,
    canopy_raster: str | Path | None = None,
) -> list[CoverageScreen]:
    """Build the tree-equity screen stack for an AOI.

    bbox is (minx, miny, maxx, maxy) in EPSG:4326.
    canopy_threshold: blocks with tree coverage BELOW this fraction are
      flagged (default 20%).
    urban_threshold: blocks with built-area coverage AT OR ABOVE this fraction
      are kept as "actually urban" (default 60%).
    canopy_raster: optional override path to a reclassified canopy COG
      (built by scripts/build_canopy_cog.py from NLCD TCC). When provided,
      the low-canopy screen uses NLCD TCC bins (1=0-10%, 2=10-25%, 3=25-40%,
      4=40-60%, 5=60-100%) instead of IO LULC's categorical Trees class.
      The urban-context screen still uses IO LULC.
    """
    urls = io_lulc_asset_urls(year=year, bbox=bbox)
    if len(urls) > 1:
        raise NotImplementedError(
            f"AOI spans {len(urls)} IO LULC tiles. "
            "Demo currently assumes a single-tile AOI. Mosaic support is a TODO."
        )
    lulc_raster = urls[0]

    if canopy_raster:
        low_canopy_screen = CoverageScreen(
            name="low_canopy_tcc",
            raster=str(canopy_raster),
            # bins 3+4+5 = >=25% canopy. Invert keeps blocks where these
            # well-canopied bins make up LESS than canopy_threshold of the block.
            pass_classes={
                3: "25_to_40pct",
                4: "40_to_60pct",
                5: "60_to_100pct",
            },
            track_classes={
                1: "0_to_10pct",
                2: "10_to_25pct",
            },
            min_coverage=canopy_threshold,
            invert=True,
        )
    else:
        low_canopy_screen = CoverageScreen(
            name="low_canopy_lulc",
            raster=lulc_raster,
            pass_classes={2: "trees"},
            track_classes={
                1: "water", 5: "crops", 7: "built_area", 11: "rangeland",
                4: "flooded_veg", 8: "bare_ground",
            },
            min_coverage=canopy_threshold,
            invert=True,
        )

    urban_screen = CoverageScreen(
        name="urban_context",
        raster=lulc_raster,
        pass_classes={7: "built_area"},
        track_classes={2: "trees", 11: "rangeland", 1: "water"},
        min_coverage=urban_threshold,
    )

    return [low_canopy_screen, urban_screen]
