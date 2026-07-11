from __future__ import annotations

import numpy as np
from scipy import ndimage

from mlu.directional_smoothing import (
    estimate_tangent_field,
    smooth_directional_alpha,
)


def _config(**overrides: object) -> dict:
    directional_smoothing = {
        "enabled": True,
        "strength": 0.55,
        "radius_hr_px": 2,
        "min_angle_from_axis_degrees": 20.0,
        "full_strength_angle_from_axis_degrees": 34.0,
        "orientation_sigma_hr_px": 1.0,
        "tensor_sigma_hr_px": 2.0,
        "min_orientation_confidence": 0.12,
        "min_gradient_energy": 1.0e-5,
        "min_alpha": 0.04,
        "support_dilate_hr_px": 1,
        "max_delta": 0.35,
    }
    directional_smoothing.update(overrides)
    return {"pipeline": {"scale": 4}, "directional_smoothing": directional_smoothing}


def _jagged_diagonal_alpha() -> np.ndarray:
    alpha = np.zeros((96, 96), dtype=np.float32)
    for x in range(12, 84):
        y = 20 + int(round(0.45 * (x - 12))) + (1 if (x // 4) % 2 else -1)
        alpha[max(0, y - 1) : min(96, y + 2), x] = 1.0
    return ndimage.gaussian_filter(alpha, sigma=0.5).astype(np.float32)


def _horizontal_alpha() -> np.ndarray:
    alpha = np.zeros((64, 64), dtype=np.float32)
    alpha[31:34, 8:56] = 1.0
    return ndimage.gaussian_filter(alpha, sigma=0.5).astype(np.float32)


def _shallow_angle_alpha() -> np.ndarray:
    alpha = np.zeros((80, 120), dtype=np.float32)
    for x in range(8, 112):
        y = 38 + int(round(0.10 * (x - 8))) + (1 if (x // 6) % 2 else -1)
        alpha[max(0, y - 1) : min(80, y + 2), x] = 1.0
    return ndimage.gaussian_filter(alpha, sigma=0.5).astype(np.float32)


def test_directional_smoothing_changes_jagged_diagonal_inside_support() -> None:
    alpha = _jagged_diagonal_alpha()

    result = smooth_directional_alpha(alpha, _config())

    assert result.applied is True
    assert result.line_alpha_hr.shape == alpha.shape
    assert result.source_alpha_hr is not None
    assert result.weight_hr.max() > 0.0
    assert result.delta_hr.max() > 0.0
    assert result.stats["sampling_mode"] == "local_angle"
    assert result.stats["changed_pixel_ratio"] > 0.01
    assert np.max(np.abs(result.line_alpha_hr - alpha)) <= 0.35
    assert result.line_alpha_hr[:, :6].max() == 0.0


def test_directional_smoothing_has_limited_effect_on_axis_aligned_line() -> None:
    diagonal = _jagged_diagonal_alpha()
    horizontal = _horizontal_alpha()

    diagonal_result = smooth_directional_alpha(diagonal, _config())
    horizontal_result = smooth_directional_alpha(horizontal, _config())

    diagonal_delta = float(np.mean(np.abs(diagonal_result.line_alpha_hr - diagonal)))
    horizontal_delta = float(np.mean(np.abs(horizontal_result.line_alpha_hr - horizontal)))
    assert diagonal_delta > horizontal_delta * 5.0


def test_directional_smoothing_suppresses_shallow_angle_lines() -> None:
    diagonal = _jagged_diagonal_alpha()
    shallow = _shallow_angle_alpha()

    diagonal_result = smooth_directional_alpha(diagonal, _config())
    shallow_result = smooth_directional_alpha(shallow, _config())

    diagonal_delta = float(np.mean(np.abs(diagonal_result.line_alpha_hr - diagonal)))
    shallow_delta = float(np.mean(np.abs(shallow_result.line_alpha_hr - shallow)))
    assert diagonal_delta > shallow_delta * 3.0
    assert shallow_result.weight_hr.max() < diagonal_result.weight_hr.max()


def test_directional_smoothing_can_be_disabled() -> None:
    alpha = _jagged_diagonal_alpha()

    result = smooth_directional_alpha(alpha, _config(enabled=False))

    assert result.applied is False
    np.testing.assert_array_equal(result.line_alpha_hr, alpha)
    assert result.source_alpha_hr is None
    assert result.weight_hr.max() == 0.0


def test_estimate_tangent_field_returns_finite_maps() -> None:
    alpha = _jagged_diagonal_alpha()

    tangent, confidence, energy = estimate_tangent_field(
        alpha,
        orientation_sigma=1.0,
        tensor_sigma=2.0,
    )

    assert tangent.shape == alpha.shape
    assert confidence.shape == alpha.shape
    assert energy.shape == alpha.shape
    assert np.isfinite(tangent).all()
    assert np.isfinite(confidence).all()
    assert np.isfinite(energy).all()
