"""STAC asset resolution for Planetary Computer.

Resolves a categorical land-cover raster to a signed COG URL for a given year
and bounding box. Anonymous access works for public collections; export
PC_SDK_SUBSCRIPTION_KEY for higher rate limits.

USGS LCMAP CONUS (collection: usgs-lcmap-conus-v13) is used as the NLCD-equivalent.
Same source (USGS), same resolution (30m), CONUS coverage, annual time series.
Class legend:
    1 = Developed
    2 = Cropland
    3 = Grass / Shrub
    4 = Tree Cover
    5 = Water
    6 = Wetlands
    7 = Ice / Snow
    8 = Barren
"""

from __future__ import annotations

import os

LCMAP_COLLECTION = "usgs-lcmap-conus-v13"
LCMAP_ASSET_KEY = "lcpri"  # primary land cover band

LCMAP_CLASS_NAMES: dict[int, str] = {
    1: "developed",
    2: "cropland",
    3: "grass_shrub",
    4: "tree_cover",
    5: "water",
    6: "wetlands",
    7: "ice_snow",
    8: "barren",
}


def lcmap_asset_url(
    year: int,
    bbox: tuple[float, float, float, float],
    asset: str = LCMAP_ASSET_KEY,
) -> str:
    """Return a signed COG URL for LCMAP land cover covering bbox in `year`.

    bbox is (minx, miny, maxx, maxy) in EPSG:4326.

    For a single-county AOI like San Diego, LCMAP CONUS is delivered as one
    annual mosaic covering the entire conterminous US; there is one STAC item
    per year. We pick the most recent item that intersects the bbox and the
    target year.
    """
    import planetary_computer
    import pystac_client

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    # LCMAP items use start_datetime/end_datetime rather than a single datetime,
    # so we list all items and filter manually rather than relying on the STAC
    # datetime parameter (which silently returns zero items).
    search = catalog.search(collections=[LCMAP_COLLECTION], bbox=bbox)
    all_items = list(search.items())
    items = [
        i for i in all_items
        if i.properties.get("start_datetime", "").startswith(str(year))
    ]
    if not items:
        years_available = sorted({
            i.properties.get("start_datetime", "")[:4] for i in all_items
        })
        raise RuntimeError(
            f"no LCMAP items for {year} intersecting {bbox}. "
            f"Years available: {years_available[0]}-{years_available[-1]}."
        )
    item = items[0]
    if asset not in item.assets:
        raise RuntimeError(
            f"asset '{asset}' not found on LCMAP item. available: {sorted(item.assets)}"
        )
    return item.assets[asset].href


def pc_subscription_key() -> str | None:
    """Read PC subscription key from env. Returns None if unset (anonymous access)."""
    return os.environ.get("PC_SDK_SUBSCRIPTION_KEY")


def describe_lcmap_classes() -> dict[int, str]:
    """Public copy of the LCMAP class legend, for demo configs to consume."""
    return dict(LCMAP_CLASS_NAMES)


# ---------------------------------------------------------------------------
# Impact Observatory 10m Annual LULC v2 (io-lulc-annual-v02)
# ---------------------------------------------------------------------------
# 10m global land cover, annual time series 2017-present. Higher resolution
# than NLCD/LCMAP and a cleaner class set for urban demos. Tiles in MGRS
# zones, so a single AOI may return one or several items per year.

IO_LULC_COLLECTION = "io-lulc-annual-v02"
IO_LULC_CLASS_NAMES: dict[int, str] = {
    1: "water",
    2: "trees",
    4: "flooded_vegetation",
    5: "crops",
    7: "built_area",
    8: "bare_ground",
    9: "snow_ice",
    10: "clouds",
    11: "rangeland",
}


def io_lulc_asset_urls(
    year: int,
    bbox: tuple[float, float, float, float],
) -> list[str]:
    """Return signed COG URLs for IO LULC items covering bbox in `year`.

    bbox is (minx, miny, maxx, maxy) in EPSG:4326.

    IO LULC tiles by MGRS (Military Grid Reference System) zone, so a county-
    scale AOI may straddle two or more tiles. Returns one URL per intersecting
    tile, in arbitrary order. Callers that need a single raster should mosaic
    them (or pick the dominant tile if a single representative is enough).
    """
    import planetary_computer
    import pystac_client

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    search = catalog.search(collections=[IO_LULC_COLLECTION], bbox=bbox)
    all_items = list(search.items())
    items = [
        i for i in all_items
        if i.properties.get("start_datetime", "").startswith(str(year))
    ]
    if not items:
        years_available = sorted({
            i.properties.get("start_datetime", "")[:4] for i in all_items
        })
        raise RuntimeError(
            f"no IO LULC items for {year} intersecting {bbox}. "
            f"Years available: {years_available[0]}-{years_available[-1]}."
        )
    return [item.assets["data"].href for item in items]


def describe_io_lulc_classes() -> dict[int, str]:
    """Public copy of the IO LULC v2 class legend."""
    return dict(IO_LULC_CLASS_NAMES)
