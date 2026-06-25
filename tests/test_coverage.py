"""Ground-truth coverage assertions against a synthetic 4-quadrant raster."""

from __future__ import annotations

import pytest

from cogsieve import CoverageScreen, class_coverage, run_screens


def test_full_class_1_is_100_percent(categorical_raster, polygons):
    screen = CoverageScreen(
        name="quad",
        raster=categorical_raster,
        pass_classes={1: "tl", 2: "tr"},
        track_classes={3: "bl", 4: "br"},
        min_coverage=0.5,
    )
    out = class_coverage(polygons, screen)

    row = out[out["name"] == "full_class_1"].iloc[0]
    assert row["quad_tl_frac"] == pytest.approx(1.0, abs=1e-6)
    assert row["quad_tr_frac"] == pytest.approx(0.0, abs=1e-6)
    assert row["quad_pass_frac"] == pytest.approx(1.0, abs=1e-6)
    assert row["quad_keep"] is True or row["quad_keep"] == 1


def test_half_half_polygon_splits_50_50(categorical_raster, polygons):
    screen = CoverageScreen(
        name="quad",
        raster=categorical_raster,
        pass_classes={1: "tl"},
        track_classes={2: "tr"},
        min_coverage=0.5,
    )
    out = class_coverage(polygons, screen)
    row = out[out["name"] == "half_1_half_2"].iloc[0]
    assert row["quad_tl_frac"] == pytest.approx(0.5, abs=1e-6)
    assert row["quad_tr_frac"] == pytest.approx(0.5, abs=1e-6)


def test_threshold_filters_polygons(categorical_raster, polygons):
    """all_four polygon has only 25% class 1 -- should fail a 50% threshold."""
    screen = CoverageScreen(
        name="quad",
        raster=categorical_raster,
        pass_classes={1: "tl"},
        min_coverage=0.5,
    )
    out = class_coverage(polygons, screen)
    row = out[out["name"] == "all_four"].iloc[0]
    assert row["quad_tl_frac"] == pytest.approx(0.25, abs=1e-6)
    assert not row["quad_keep"]


def test_invert_keeps_low_coverage(categorical_raster, polygons):
    """invert=True is the 'find polygons with LOW coverage' branch (tree-equity demo)."""
    screen = CoverageScreen(
        name="quad",
        raster=categorical_raster,
        pass_classes={1: "tl"},
        min_coverage=0.5,
        invert=True,
    )
    out = class_coverage(polygons, screen)
    full = out[out["name"] == "full_class_1"].iloc[0]
    quarter = out[out["name"] == "all_four"].iloc[0]
    assert not full["quad_keep"]
    assert quarter["quad_keep"]


def test_pipeline_chains_screens_and_caches(categorical_raster, polygons, tmp_path):
    s1 = CoverageScreen(
        name="has_tl",
        raster=categorical_raster,
        pass_classes={1: "tl"},
        min_coverage=0.25,
    )
    s2 = CoverageScreen(
        name="not_br",
        raster=categorical_raster,
        pass_classes={4: "br"},
        min_coverage=0.5,
        invert=True,
    )
    results = run_screens(polygons, [s1, s2], cache_dir=tmp_path)
    # Screen 1: keep polygons with >=25% class 1. All 3 qualify.
    assert results[0].metrics["kept"] == 3
    # Screen 2 inverted: keep polygons with <50% class 4. All 3 qualify
    # (max is 'all_four' at 25%).
    assert results[1].metrics["kept"] == 3
    assert list(tmp_path.glob("*.parquet"))
