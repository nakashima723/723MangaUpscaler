from __future__ import annotations

import numpy as np
from scipy import ndimage

from mlu.config import load_config
from mlu.mask_extract import (
    cleanup_mask,
    compute_darkness,
    compute_line_probability,
    compute_line_soft,
    extract_line_maps,
    fill_small_holes,
    fixed_threshold_mask,
    hysteresis_threshold,
    remove_small_components,
)


def test_darkness_and_line_probability() -> None:
    gray = np.array([[1.0, 0.75, 0.5, 0.0]], dtype=np.float32)

    darkness = compute_darkness(gray)
    probability = compute_line_probability(darkness, weak=0.25, strong=0.75)

    assert np.allclose(darkness, [[0.0, 0.25, 0.5, 1.0]])
    assert np.allclose(probability, [[0.0, 0.0, 0.5, 1.0]])


def test_compute_line_soft_preserves_source_darkness_on_line_support() -> None:
    darkness = np.array([[0.05, 0.25, 0.60]], dtype=np.float32)
    line_prob = np.array([[0.00, 0.10, 1.00]], dtype=np.float32)
    line_mask = np.array([[False, False, True]], dtype=np.bool_)

    soft = compute_line_soft(darkness, line_prob, line_mask, weak=0.20)

    assert np.allclose(soft, [[0.0, 0.25, 0.60]])


def test_compute_line_soft_can_reproduce_legacy_max_probability_coverage() -> None:
    darkness = np.array([[0.05, 0.25, 0.60]], dtype=np.float32)
    line_prob = np.array([[0.00, 0.10, 1.00]], dtype=np.float32)
    line_mask = np.array([[False, False, True]], dtype=np.bool_)

    soft = compute_line_soft(
        darkness,
        line_prob,
        line_mask,
        weak=0.20,
        coverage_mode="max_probability",
    )

    assert np.allclose(soft, [[0.0, 0.25, 1.00]])


def test_compute_line_soft_can_use_line_probability_for_diagnostics() -> None:
    darkness = np.array([[0.05, 0.25, 0.60]], dtype=np.float32)
    line_prob = np.array([[0.00, 0.10, 1.00]], dtype=np.float32)
    line_mask = np.array([[False, False, True]], dtype=np.bool_)

    soft = compute_line_soft(
        darkness,
        line_prob,
        line_mask,
        weak=0.20,
        coverage_mode="line_probability",
    )

    assert np.allclose(soft, [[0.0, 0.10, 1.00]])


def test_compute_line_soft_applies_coverage_gamma() -> None:
    darkness = np.array([[0.25, 0.50, 1.00]], dtype=np.float32)
    line_prob = np.zeros_like(darkness)
    line_mask = np.array([[True, True, True]], dtype=np.bool_)

    soft = compute_line_soft(
        darkness,
        line_prob,
        line_mask,
        weak=0.20,
        coverage_gamma=2.0,
    )

    assert np.allclose(soft, [[0.0625, 0.25, 1.0]])


def test_fixed_threshold_extracts_dark_diagonal() -> None:
    gray = np.ones((8, 8), dtype=np.float32)
    np.fill_diagonal(gray, 0.0)

    mask = fixed_threshold_mask(gray, threshold=0.72)

    assert mask.diagonal().all()
    assert mask.mean() == 1 / 8


def test_hysteresis_keeps_connected_weak_line_and_drops_isolated_weak_pixel() -> None:
    gray = np.ones((5, 8), dtype=np.float32)
    gray[2, 1] = 0.0
    gray[2, 2:5] = 0.78
    gray[0, 7] = 0.78
    darkness = compute_darkness(gray)

    mask = hysteresis_threshold(darkness, weak=0.20, strong=0.50)

    assert mask[2, 1:5].all()
    assert not mask[0, 7]


def test_cleanup_removes_small_noise_without_erasing_long_thin_line() -> None:
    mask = np.zeros((8, 8), dtype=np.bool_)
    mask[4, 1:7] = True
    mask[0, 0] = True

    cleaned = cleanup_mask(mask, min_component_area=3, close_radius=0, fill_holes_area=0)

    assert cleaned[4, 1:7].all()
    assert not cleaned[0, 0]


def test_fill_small_holes_respects_area_limit() -> None:
    mask = np.ones((8, 8), dtype=np.bool_)
    mask[2, 2] = False
    mask[4:6, 4:6] = False

    filled = fill_small_holes(mask, max_area=1)

    assert filled[2, 2]
    assert not filled[4:6, 4:6].any()


def test_fill_small_holes_matches_binary_fill_holes_reference() -> None:
    rng = np.random.default_rng(723)
    structure = ndimage.generate_binary_structure(2, 2)
    for _ in range(20):
        mask = rng.random((31, 37)) > 0.42
        for max_area in (1, 3, 8, 20):
            filled_all = ndimage.binary_fill_holes(mask, structure=structure)
            holes = filled_all & ~mask
            labels, count = ndimage.label(holes, structure=structure)
            sizes = np.bincount(labels.ravel())
            fill = (sizes <= max_area) & (sizes > 0)
            expected = mask | fill[labels] if count else mask.copy()

            actual = fill_small_holes(mask, max_area=max_area)

            assert np.array_equal(actual, expected)


def test_remove_small_components_handles_empty_mask() -> None:
    mask = np.zeros((3, 3), dtype=np.bool_)

    cleaned = remove_small_components(mask, min_area=2)

    assert cleaned.shape == mask.shape
    assert not cleaned.any()


def test_extract_line_maps_reports_area_and_warnings() -> None:
    config = load_config(
        cli_overrides={
            "mask": {
                "black_threshold": 0.72,
                "cleanup": {"min_component_area": 1, "fill_holes_area": 0},
            }
        }
    )
    gray = np.ones((10, 10), dtype=np.float32)
    gray[3, :] = 0.0

    maps = extract_line_maps(gray, config)

    assert maps.line_prob.dtype == np.float32
    assert maps.line_mask.dtype == np.bool_
    assert maps.line_soft.dtype == np.float32
    assert maps.mask_area_ratio == 0.1
    assert maps.warnings == ()
