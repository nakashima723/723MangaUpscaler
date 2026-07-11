from __future__ import annotations

import numpy as np

from mlu.config import load_config
from mlu.line_stabilizer import detect_straight_segments, stabilize_line_alpha


def _config(**overrides):
    stabilizer = {
        "enabled": True,
        "min_length_source_px": 24.0,
        "max_segments": 8,
    }
    stabilizer.update(overrides)
    return load_config(
        cli_overrides={
            "pipeline": {"scale": 4},
            "io": {"overwrite": True},
            "line_stabilizer": stabilizer,
        }
    )


def test_detect_straight_segments_fits_long_shallow_architectural_line() -> None:
    height, width = 24, 80
    mask = np.zeros((height, width), dtype=np.bool_)
    soft = np.zeros((height, width), dtype=np.float32)
    for x in range(5, 75):
        y = int(round(10 + 0.05 * (x - 5) + (1 if x % 17 == 0 else 0)))
        mask[y, x] = True
        soft[y, x] = 1.0
        soft[min(y + 1, height - 1), x] = 0.4

    segments = detect_straight_segments(mask, soft, _config())

    assert len(segments) >= 1
    assert segments[0].length_source_px >= 24.0
    assert segments[0].rms_error_source_px <= 0.55


def test_stabilizer_blends_geometry_into_high_resolution_alpha() -> None:
    height, width = 24, 80
    mask = np.zeros((height, width), dtype=np.bool_)
    soft = np.zeros((height, width), dtype=np.float32)
    for x in range(5, 75):
        y = int(round(10 + 0.05 * (x - 5)))
        mask[y, x] = True
        soft[y, x] = 1.0

    alpha = np.ones((height * 4, width * 4), dtype=np.float32) * 0.2
    result = stabilize_line_alpha(alpha, mask, soft, _config(strength=0.5))

    assert len(result.segments) >= 1
    assert float(result.line_geometry_hr.max()) > 0.0
    assert np.all(result.line_alpha_hr >= alpha)
    assert float(result.line_alpha_hr.sum()) > float(alpha.sum())


def test_stabilizer_does_not_draw_between_sparse_support_points() -> None:
    height, width = 24, 80
    mask = np.zeros((height, width), dtype=np.bool_)
    soft = np.zeros((height, width), dtype=np.float32)
    for x in range(8, 73, 8):
        mask[10, x] = True
        soft[10, x] = 1.0

    alpha = np.zeros((height * 4, width * 4), dtype=np.float32)
    result = stabilize_line_alpha(
        alpha,
        mask,
        soft,
        _config(
            strength=1.0,
            min_density=0.05,
            max_gap_source_px=12.0,
            support_dilate_hr_px=0,
        ),
    )

    assert len(result.segments) >= 1
    assert result.line_alpha_hr[10 * 4 + 2, 8 * 4 + 2] > 0.0
    assert result.line_alpha_hr[10 * 4 + 2, 12 * 4 + 2] == 0.0


def test_stabilizer_disabled_returns_alpha_unchanged() -> None:
    mask = np.zeros((8, 16), dtype=np.bool_)
    soft = np.zeros((8, 16), dtype=np.float32)
    soft[3, 2:14] = 1.0
    alpha = np.ones((16, 32), dtype=np.float32) * 0.25
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 2},
            "line_stabilizer": {"enabled": False},
        }
    )

    result = stabilize_line_alpha(alpha, mask, soft, config)

    assert result.segments == ()
    assert np.array_equal(result.line_alpha_hr, alpha)
    assert not result.line_geometry_hr.any()


def test_short_lines_are_not_stabilized() -> None:
    mask = np.zeros((16, 16), dtype=np.bool_)
    soft = np.zeros((16, 16), dtype=np.float32)
    mask[8, 3:10] = True
    soft[8, 3:10] = 1.0

    segments = detect_straight_segments(mask, soft, _config(min_length_source_px=24.0))

    assert segments == ()
