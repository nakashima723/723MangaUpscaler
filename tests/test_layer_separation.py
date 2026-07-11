from __future__ import annotations

import numpy as np

from mlu.config import load_config
from mlu.layer_separation import separate_relative_layers
from mlu.mask_extract import extract_line_maps


def _config(**overrides):
    grayscale = {"mode": "line_only", **overrides}
    return load_config(cli_overrides={"grayscale_processing": grayscale})


def test_same_absolute_gray_is_tone_or_line_from_local_context() -> None:
    gray = np.ones((48, 64), dtype=np.float32)
    gray[8:32, 6:26] = np.float32(0.55)
    gray[39:41, 34:58] = np.float32(0.55)

    result = separate_relative_layers(gray, _config())

    assert not result.line_maps.line_mask[18, 16]
    assert result.line_maps.line_mask[40, 45]
    assert result.tone[18, 16] == np.float32(0.55)


def test_multiplicative_line_is_detected_on_bright_and_dark_tone() -> None:
    tone = np.full((48, 72), 0.90, dtype=np.float32)
    tone[:, 36:] = np.float32(0.50)
    gray = tone.copy()
    gray[22:24, 6:66] *= np.float32(0.65)

    result = separate_relative_layers(gray, _config())

    left_recall = result.line_maps.line_mask[22:24, 8:34].mean()
    right_recall = result.line_maps.line_mask[22:24, 38:64].mean()
    assert left_recall >= 0.90
    assert right_recall >= 0.90
    assert abs(float(result.relative_contrast[22, 16]) - 0.35) < 0.02
    assert abs(float(result.relative_contrast[22, 50]) - 0.35) < 0.02
    assert abs(float(result.line_alpha[22, 16]) - 0.35) < 0.02
    assert abs(float(result.line_alpha[22, 50]) - 0.35) < 0.02
    assert abs(float(result.line_maps.line_soft[22, 16]) - 0.35 * 2.425) < 0.02
    assert abs(float(result.line_maps.line_soft[22, 50]) - 0.35 * 2.425) < 0.02


def test_quality_hybrid_preserves_legacy_support_on_white() -> None:
    gray = np.ones((48, 64), dtype=np.float32)
    gray[8:40, 29] = np.float32(0.82)
    gray[8:40, 30] = np.float32(0.55)
    gray[8:40, 31] = np.float32(0.08)
    gray[8:40, 32] = np.float32(0.55)
    gray[8:40, 33] = np.float32(0.82)

    result = separate_relative_layers(gray, _config())

    expected_line_soft = extract_line_maps(gray, _config()).line_soft
    assert np.allclose(
        result.line_maps.line_soft[10:38, 28:35],
        expected_line_soft[10:38, 28:35],
    )
    assert np.array_equal(
        result.line_maps.line_soft[10:38, 28:35] >= np.float32(0.22),
        expected_line_soft[10:38, 28:35] >= np.float32(0.22),
    )
    assert np.all(result.legacy_blend_weight[10:38, 28:35] == np.float32(1.0))


def test_quality_hybrid_lifts_white_border_line_out_of_tone() -> None:
    gray = np.ones((32, 32), dtype=np.float32)
    gray[4:28, 0] = np.float32(0.0)

    result = separate_relative_layers(gray, _config())

    border_line = result.line_maps.line_soft[4:28, 0]
    tone_at_line = result.tone[4:28, 0]
    assert np.all(border_line == np.float32(1.0))
    assert float(np.mean(np.float32(1.0) - tone_at_line)) < 1.0 / 255.0
    assert float(tone_at_line.min()) >= 0.98
    assert np.all(result.tone[:, 1:] == np.float32(1.0))


def test_detection_probability_coverage_remains_available_for_comparison() -> None:
    gray = np.ones((32, 40), dtype=np.float32)
    gray[8:24, 19:21] = np.float32(0.85)

    relative = separate_relative_layers(
        gray,
        _config(line_coverage_mode="relative_contrast"),
    )
    probability = separate_relative_layers(
        gray,
        _config(line_coverage_mode="detection_probability"),
    )

    assert relative.line_coverage_mode == "relative_contrast"
    assert probability.line_coverage_mode == "detection_probability"
    assert float(probability.line_maps.line_soft[16, 20]) > float(
        relative.line_maps.line_soft[16, 20]
    )


def test_smooth_gradient_remains_tone_without_hallucinated_lines() -> None:
    gradient = np.linspace(0.20, 1.0, 96, dtype=np.float32)
    gray = np.broadcast_to(gradient, (64, 96)).copy()

    result = separate_relative_layers(gray, _config())

    assert result.line_maps.mask_area_ratio < 0.01
    assert float(np.mean(np.abs(result.tone - gray))) < 1.0 / 255.0


def test_identical_line_and_tone_cannot_create_a_false_line() -> None:
    gray = np.full((32, 32), 0.42, dtype=np.float32)

    result = separate_relative_layers(gray, _config())

    assert not result.line_maps.line_mask.any()
    assert np.array_equal(result.tone, gray)
