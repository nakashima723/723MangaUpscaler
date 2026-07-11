from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

from mlu.centerline_simplification import (
    _corner_anchor_indices,
    _cumulative_lengths,
    _filter_high_frequency_path,
    _filter_path_widths,
    _long_stroke_rejection_reason,
    _rollback_unsafe_components,
    simplify_centerline_alpha,
    thin_zhang_suen,
)
from mlu.config import load_config


def _wobbly_line_alpha(*, scale: int = 4) -> np.ndarray:
    source = Image.new("L", (48, 32), 0)
    draw = ImageDraw.Draw(source)
    points = []
    for x in range(4, 44):
        y = 12 + x // 8
        points.append((x, y))
    draw.line(points, fill=255, width=3)
    high_resolution = source.resize((48 * scale, 32 * scale), Image.Resampling.NEAREST)
    return np.asarray(high_resolution, dtype=np.float32) / np.float32(255.0)


def test_zero_filter_sigma_is_pixel_identical_and_returns_same_alpha() -> None:
    alpha = _wobbly_line_alpha()
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 4},
            "centerline_simplification": {
                "enabled": True,
                "filter_sigma_source_px": 0.0,
            },
        }
    )

    result = simplify_centerline_alpha(alpha, config, renderer="sdf")

    assert result.line_alpha_hr is alpha
    assert result.stats["applied"] is False
    assert result.stats["skip_reason"] == "zero_filter_sigma"


def test_zero_geometry_strength_is_pixel_identical() -> None:
    alpha = _wobbly_line_alpha()
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 4},
            "centerline_simplification": {
                "enabled": True,
                "filter_sigma_source_px": 0.75,
                "geometry_strength": 0.0,
            },
        }
    )

    result = simplify_centerline_alpha(alpha, config, renderer="sdf")

    assert result.line_alpha_hr is alpha
    assert result.stats["skip_reason"] == "zero_geometry_strength"


def test_simplification_stays_inside_local_source_neighborhood() -> None:
    alpha = _wobbly_line_alpha()
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 4},
            "centerline_simplification": {
                "enabled": True,
                "filter_sigma_source_px": 0.75,
                "strength": 1.0,
                "min_path_length_source_px": 8.0,
                "endpoint_protection_source_px": 2.0,
                "long_stroke_gate": {"enabled": False},
                "component_rollback": {"enabled": False},
            },
        }
    )

    result = simplify_centerline_alpha(alpha, config, renderer="sdf")

    assert result.stats["applied"] is True
    assert result.stats["filtered_path_count"] >= 1
    assert result.stats["max_path_displacement_source_px"] <= 0.75
    assert float(np.abs(result.line_alpha_hr - alpha).max()) > 0.0
    source_support = alpha > 0.0
    allowed = np.asarray(
        Image.fromarray(source_support.astype(np.uint8) * 255).filter(
            ImageFilter.MaxFilter(size=9)
        )
    ) > 0
    assert not np.any((result.line_alpha_hr > np.float32(1.0 / 255.0)) & ~allowed)
    assert result.centerline_source is not None
    assert result.filtered_centerline_source is not None
    assert result.filter_displacement_source is not None
    assert result.protected_source is not None
    assert result.delta_hr is not None
    assert set(np.unique(result.line_alpha_hr)).issubset({0.0, 1.0})
    assert result.stats["fractional_pixel_ratio_before_binarization"] > 0.0
    assert result.stats["fractional_pixel_ratio_after_binarization"] == 0.0
    assert (
        sum(result.stats["rejected_path_counts"].values())
        + result.stats["eligible_path_count"]
        == result.stats["path_count"]
    )


def test_simplification_can_keep_fractional_alpha_for_diagnostics() -> None:
    alpha = _wobbly_line_alpha()
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 4},
            "centerline_simplification": {
                "enabled": True,
                "filter_sigma_source_px": 0.75,
                "strength": 1.0,
                "min_path_length_source_px": 8.0,
                "endpoint_protection_source_px": 2.0,
                "binarize_output": False,
                "long_stroke_gate": {"enabled": False},
                "component_rollback": {"enabled": False},
            },
        }
    )

    result = simplify_centerline_alpha(alpha, config, renderer="sdf")

    assert np.any((result.line_alpha_hr > 0.0) & (result.line_alpha_hr < 1.0))
    assert result.stats["fractional_pixel_ratio_after_binarization"] > 0.0


def test_binary_simplification_levels_are_distinct_and_keep_simple_line_connected() -> None:
    alpha = _wobbly_line_alpha()
    outputs = []
    for filter_sigma, geometry_strength, max_displacement in (
        (0.75, 0.5, 0.50),
        (1.00, 0.75, 0.75),
        (1.25, 1.0, 1.00),
    ):
        config = load_config(
            cli_overrides={
                "pipeline": {"scale": 4},
                "centerline_simplification": {
                    "enabled": True,
                    "filter_sigma_source_px": filter_sigma,
                    "max_filter_displacement_source_px": max_displacement,
                    "strength": 1.0,
                    "geometry_strength": geometry_strength,
                    "min_path_length_source_px": 8.0,
                    "endpoint_protection_source_px": 2.0,
                    "long_stroke_gate": {"enabled": False},
                    "component_rollback": {"enabled": False},
                },
            }
        )
        result = simplify_centerline_alpha(alpha, config, renderer="sdf")
        assert set(np.unique(result.line_alpha_hr)).issubset({0.0, 1.0})
        _, component_count = ndimage.label(
            result.line_alpha_hr > 0.5,
            structure=np.ones((3, 3), dtype=np.uint8),
        )
        assert component_count == 1
        outputs.append(result.line_alpha_hr)

    assert not np.array_equal(outputs[0], outputs[1])
    assert not np.array_equal(outputs[1], outputs[2])


def test_filter_strength_moves_points_monotonically_and_keeps_endpoints() -> None:
    points = np.array([(10 + index // 4, index) for index in range(24)], dtype=np.int32)
    cumulative = np.concatenate(
        (
            np.zeros(1, dtype=np.float32),
            np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1)),
        )
    )
    common = {
        "sigma_source_px": 1.0,
        "sample_step_source_px": 0.5,
        "max_displacement_source_px": 0.75,
        "protection": 2.0,
        "corner_angle_degrees": 45.0,
        "corner_window_source_px": 3.0,
    }

    off, _, _ = _filter_high_frequency_path(points, cumulative, strength=0.0, **common)
    half, _, _ = _filter_high_frequency_path(points, cumulative, strength=0.5, **common)
    full, _, stats = _filter_high_frequency_path(
        points,
        cumulative,
        strength=1.0,
        **common,
    )

    assert np.array_equal(off, points.astype(np.float32))
    assert np.array_equal(half[[0, -1]], points[[0, -1]].astype(np.float32))
    assert np.array_equal(full[[0, -1]], points[[0, -1]].astype(np.float32))
    half_move = np.linalg.norm(half - off, axis=1)
    full_move = np.linalg.norm(full - off, axis=1)
    assert np.all(half_move <= full_move + np.float32(1.0e-6))
    assert np.any(half_move > 0.0)
    assert len(full) == len(points)
    assert stats["noise_energy_after"] < stats["noise_energy_before"]


def test_gaussian_filter_removes_short_period_noise_and_preserves_long_wave() -> None:
    x = np.arange(128, dtype=np.float32)
    low_wave = np.float32(0.30) * np.sin(np.float32(2.0 * np.pi) * x / 48.0)
    high_noise = np.float32(0.30) * np.sin(np.float32(2.0 * np.pi) * x / 4.0)
    points = np.column_stack((20.0 + low_wave + high_noise, x)).astype(np.float32)
    cumulative = _cumulative_lengths(points)
    common = {
        "sample_step_source_px": 0.5,
        "strength": 1.0,
        "max_displacement_source_px": 1.0,
        "protection": 0.0,
        "corner_angle_degrees": 179.9,
        "corner_window_source_px": 0.1,
    }

    low, _, _ = _filter_high_frequency_path(
        points,
        cumulative,
        sigma_source_px=0.75,
        **common,
    )
    high, _, _ = _filter_high_frequency_path(
        points,
        cumulative,
        sigma_source_px=1.25,
        **common,
    )

    center = slice(16, 112)
    original_roughness = float(np.mean(np.diff(points[center, 0], n=2) ** 2))
    low_roughness = float(np.mean(np.diff(low[center, 0], n=2) ** 2))
    high_roughness = float(np.mean(np.diff(high[center, 0], n=2) ** 2))
    assert high_roughness < low_roughness < original_roughness

    def amplitude(values: np.ndarray, period: float) -> float:
        samples = values[center] - np.mean(values[center])
        phase = np.exp(
            np.complex64(-2j * np.pi) * np.arange(len(samples), dtype=np.float32) / period
        )
        return float(2.0 * np.abs(np.sum(samples * phase)) / len(samples))

    original_low_amplitude = amplitude(points[:, 0], 48.0)
    high_low_amplitude = amplitude(high[:, 0], 48.0)
    assert high_low_amplitude >= original_low_amplitude * 0.90

    straight = np.column_stack((np.full(64, 12.0, dtype=np.float32), x[:64]))
    straight_filtered, _, _ = _filter_high_frequency_path(
        straight,
        _cumulative_lengths(straight),
        sigma_source_px=1.25,
        **common,
    )
    assert np.allclose(straight_filtered, straight, atol=1.0e-5)


def test_width_filter_reduces_short_period_variation_and_keeps_endpoints() -> None:
    cumulative = np.arange(32, dtype=np.float32)
    widths = np.where(np.arange(32) % 2 == 0, 2.0, 4.0).astype(np.float32)

    filtered = _filter_path_widths(
        widths,
        cumulative,
        sigma_source_px=1.0,
        sample_step_source_px=0.5,
        strength=1.0,
        protection=2.0,
    )

    assert np.array_equal(filtered[:3], widths[:3])
    assert np.array_equal(filtered[-3:], widths[-3:])
    assert float(np.mean(np.diff(filtered[6:-6]) ** 2)) < float(
        np.mean(np.diff(widths[6:-6]) ** 2)
    )


def test_corner_detection_keeps_real_bend_but_not_digital_stair_steps() -> None:
    bend = np.array(
        [(8, x) for x in range(2, 11)] + [(y, 10) for y in range(9, 18)],
        dtype=np.int32,
    )
    bend_cumulative = np.concatenate(
        (
            np.zeros(1, dtype=np.float32),
            np.cumsum(np.linalg.norm(np.diff(bend, axis=0), axis=1)),
        )
    )
    staircase = np.array(
        [(10 + x // 4, x) for x in range(2, 22)],
        dtype=np.int32,
    )
    staircase_cumulative = np.concatenate(
        (
            np.zeros(1, dtype=np.float32),
            np.cumsum(np.linalg.norm(np.diff(staircase, axis=0), axis=1)),
        )
    )

    bend_anchors = _corner_anchor_indices(
        bend,
        bend_cumulative,
        angle_degrees=45.0,
        window_source_px=3.0,
    )
    staircase_anchors = _corner_anchor_indices(
        staircase,
        staircase_cumulative,
        angle_degrees=45.0,
        window_source_px=3.0,
    )

    assert any(abs(index - 8) <= 1 for index in bend_anchors)
    assert staircase_anchors == []


def test_thinning_preserves_crossing_connectivity() -> None:
    mask = np.zeros((21, 21), dtype=bool)
    mask[9:12, 2:19] = True
    mask[2:19, 9:12] = True

    centerline, _ = thin_zhang_suen(mask)

    assert centerline[10, 10]
    assert centerline[:, 10].sum() >= 14
    assert centerline[10, :].sum() >= 14


def test_final_simplification_keeps_t_junction_connected() -> None:
    source = Image.new("L", (40, 40), 0)
    draw = ImageDraw.Draw(source)
    draw.line((5, 12, 35, 12), fill=255, width=3)
    draw.line((20, 12, 20, 35), fill=255, width=3)
    alpha = np.asarray(
        source.resize((160, 160), Image.Resampling.NEAREST),
        dtype=np.float32,
    ) / np.float32(255.0)
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 4},
            "centerline_simplification": {
                "enabled": True,
                "filter_sigma_source_px": 1.25,
                "geometry_strength": 1.0,
                "min_path_length_source_px": 8.0,
                "long_stroke_gate": {"enabled": False},
                "component_rollback": {"enabled": False},
            },
        }
    )

    result = simplify_centerline_alpha(alpha, config, renderer="sdf")
    _, component_count = ndimage.label(
        result.line_alpha_hr > 0.5,
        structure=np.ones((3, 3), dtype=np.uint8),
    )

    assert component_count == 1
    assert np.array_equal(result.line_alpha_hr[40:64, 68:92], alpha[40:64, 68:92])


def test_long_stroke_gate_accepts_straight_width_stable_path_and_rejects_corner() -> None:
    straight = np.array([(10, x) for x in range(80)], dtype=np.int32)
    straight_cumulative = np.concatenate(
        (
            np.zeros(1, dtype=np.float32),
            np.cumsum(np.linalg.norm(np.diff(straight, axis=0), axis=1)),
        )
    )
    corner = np.array(
        [(12, x) for x in range(40)] + [(y, 39) for y in range(13, 53)],
        dtype=np.int32,
    )
    corner_cumulative = np.concatenate(
        (
            np.zeros(1, dtype=np.float32),
            np.cumsum(np.linalg.norm(np.diff(corner, axis=0), axis=1)),
        )
    )
    settings = {
        "gate_enabled": True,
        "min_chord_arc_ratio": 0.985,
        "max_line_fit_rms_source_px": 0.35,
        "max_line_fit_deviation_source_px": 1.0,
        "max_width_cv": 0.20,
        "max_width_ratio": 1.50,
        "skip_paths_with_corners": True,
        "corner_angle_degrees": 45.0,
        "corner_window_source_px": 3.0,
    }

    straight_reason, _ = _long_stroke_rejection_reason(
        straight,
        straight_cumulative,
        np.ones(len(straight), dtype=np.float32),
        **settings,
    )
    corner_reason, _ = _long_stroke_rejection_reason(
        corner,
        corner_cumulative,
        np.ones(len(corner), dtype=np.float32),
        **settings,
    )
    staircase = np.array([(10 + x % 2, x) for x in range(80)], dtype=np.int32)
    staircase_cumulative = np.concatenate(
        (
            np.zeros(1, dtype=np.float32),
            np.cumsum(np.linalg.norm(np.diff(staircase, axis=0), axis=1)),
        )
    )
    staircase_reason, _ = _long_stroke_rejection_reason(
        staircase,
        staircase_cumulative,
        np.ones(len(staircase), dtype=np.float32),
        **{**settings, "skip_paths_with_corners": False},
    )
    width_reason, _ = _long_stroke_rejection_reason(
        straight,
        straight_cumulative,
        np.concatenate(
            (
                np.ones(40, dtype=np.float32),
                np.full(40, 2.0, dtype=np.float32),
            )
        ),
        **settings,
    )

    assert straight_reason is None
    assert corner_reason == "has_corner"
    assert staircase_reason == "low_chord_arc_ratio"
    assert width_reason == "width_variation"


def _component_rollback_fixture() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    support = np.zeros((12, 24), dtype=bool)
    support[6, 2:22] = True
    component_labels, _ = ndimage.label(
        support,
        structure=np.ones((3, 3), dtype=np.uint8),
    )
    original = np.zeros((24, 48), dtype=np.float32)
    original[11:13, 4:44] = 1.0
    return original, support, component_labels


def _apply_component_rollback(
    candidate: np.ndarray,
    original: np.ndarray,
    affected_source: np.ndarray,
    component_labels: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    return _rollback_unsafe_components(
        candidate,
        original,
        affected_source,
        component_labels,
        np.ones_like(candidate, dtype=bool),
        scale=2,
        binary_threshold=0.5,
        binary_output=True,
        enabled=True,
        preserve_component_count=True,
        min_ink_ratio=0.75,
        max_ink_ratio=1.25,
    )


def test_component_rollback_restores_a_split_component() -> None:
    original, affected_source, component_labels = _component_rollback_fixture()
    candidate = original.copy()
    candidate[:, 23:25] = 0.0

    result, rolled_back_source, stats = _apply_component_rollback(
        candidate,
        original,
        affected_source,
        component_labels,
    )

    assert np.array_equal(result, original)
    assert rolled_back_source.any()
    assert stats["rolled_back_component_count"] == 1
    assert stats["rollback_reason_counts"]["component_split"] == 1


def test_component_rollback_keeps_a_connected_area_preserving_move() -> None:
    original, affected_source, component_labels = _component_rollback_fixture()
    candidate = original.copy()
    candidate[11:13, 12:36] = 0.0
    candidate[10:12, 12:36] = 1.0

    result, rolled_back_source, stats = _apply_component_rollback(
        candidate,
        original,
        affected_source,
        component_labels,
    )

    assert np.array_equal(result, candidate)
    assert not rolled_back_source.any()
    assert stats["accepted_component_count"] == 1
    assert stats["rolled_back_component_count"] == 0


def test_component_rollback_restores_excessive_ink_growth() -> None:
    original, affected_source, component_labels = _component_rollback_fixture()
    candidate = original.copy()
    candidate[8:16, 4:44] = 1.0

    result, rolled_back_source, stats = _apply_component_rollback(
        candidate,
        original,
        affected_source,
        component_labels,
    )

    assert np.array_equal(result, original)
    assert rolled_back_source.any()
    assert stats["rollback_reason_counts"]["ink_gain"] == 1


def test_component_rollback_restores_disappearance_and_new_component() -> None:
    original, affected_source, component_labels = _component_rollback_fixture()
    disappeared = np.zeros_like(original)

    restored, _, disappeared_stats = _apply_component_rollback(
        disappeared,
        original,
        affected_source,
        component_labels,
    )

    assert np.array_equal(restored, original)
    assert disappeared_stats["rollback_reason_counts"]["component_disappeared"] == 1

    added = original.copy()
    added[2:5, 20:24] = 1.0
    restored, _, added_stats = _apply_component_rollback(
        added,
        original,
        affected_source,
        component_labels,
    )

    assert np.array_equal(restored, original)
    assert added_stats["rollback_reason_counts"]["new_component"] == 1


def test_component_rollback_restores_a_merge_between_two_components() -> None:
    support = np.zeros((16, 24), dtype=bool)
    support[4, 2:22] = True
    support[11, 2:22] = True
    component_labels, _ = ndimage.label(
        support,
        structure=np.ones((3, 3), dtype=np.uint8),
    )
    original = np.zeros((32, 48), dtype=np.float32)
    original[7:9, 4:44] = 1.0
    original[21:23, 4:44] = 1.0
    candidate = original.copy()
    candidate[8:23, 23:25] = 1.0

    result, rolled_back_source, stats = _apply_component_rollback(
        candidate,
        original,
        support,
        component_labels,
    )

    assert np.array_equal(result, original)
    assert rolled_back_source.any()
    assert stats["rollback_reason_counts"]["component_merged"] >= 1
