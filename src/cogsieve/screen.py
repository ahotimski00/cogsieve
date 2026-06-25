"""Declarative configuration for a single class-coverage screen."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd


@dataclass(frozen=True)
class CoverageScreen:
    """One screen: keep polygons whose fractional coverage of `pass_classes` >= min_coverage.

    Attributes:
        name: short identifier used in column names and cache keys.
        raster: path or URL to a categorical raster (COG, local file, /vsicurl/...).
        pass_classes: {class_value: short_name} required toward the threshold.
        track_classes: {class_value: short_name} reported but not counted toward threshold.
        min_coverage: fraction in [0, 1] of polygon area that must be in pass_classes.
        invert: if True, keep polygons whose pass_classes coverage is BELOW min_coverage
            (used for "find parcels with LOW canopy" style queries).
        nodata_as_zero: treat raster nodata as a 0-coverage class rather than dropping the polygon.
    """

    name: str
    raster: str | Path
    pass_classes: dict[int, str]
    track_classes: dict[int, str] = field(default_factory=dict)
    min_coverage: float = 0.5
    invert: bool = False
    nodata_as_zero: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_coverage <= 1.0:
            raise ValueError(f"min_coverage must be in [0, 1], got {self.min_coverage}")
        overlap = self.pass_classes.keys() & self.track_classes.keys()
        if overlap:
            raise ValueError(f"classes appear in both pass and track: {sorted(overlap)}")

    @property
    def all_classes(self) -> dict[int, str]:
        return {**self.pass_classes, **self.track_classes}

    def column_for(self, class_value: int) -> str:
        short = self.all_classes.get(class_value, str(class_value))
        return f"{self.name}_{short}_frac".lower()

    @property
    def pass_column(self) -> str:
        return f"{self.name}_pass_frac".lower()

    @property
    def keep_column(self) -> str:
        return f"{self.name}_keep".lower()


@dataclass
class ScreenResult:
    """Result of one screen applied to a GeoDataFrame.

    `gdf` is the SURVIVING polygons (those where keep_column is True), with per-class
    coverage columns and the keep_column appended. `metrics` summarizes pass/drop counts.
    """

    gdf: gpd.GeoDataFrame
    screen: CoverageScreen
    metrics: dict[str, int | float]
