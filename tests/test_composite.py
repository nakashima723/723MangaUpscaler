from __future__ import annotations

import numpy as np
import pytest

from mlu.composite import (
    apply_edge_alpha_gamma,
    composite_black_lines,
    composite_on_white,
    white_canvas,
)
from mlu.config import load_config


def test_composite_black_lines_maps_alpha_to_black_ink() -> None:
    canvas = white_canvas((1, 3))
    alpha = np.array([[0.0, 0.5, 1.0]], dtype=np.float32)

    final = composite_black_lines(canvas, alpha, line_darkness=1.0, edge_alpha_gamma=1.0)

    assert np.allclose(final, [[1.0, 0.5, 0.0]])


def test_line_darkness_controls_full_ink_density() -> None:
    canvas = white_canvas((1, 1))
    alpha = np.ones((1, 1), dtype=np.float32)

    final = composite_black_lines(canvas, alpha, line_darkness=0.8)

    assert np.allclose(final, [[0.2]])


def test_edge_alpha_gamma_thins_fractional_edges() -> None:
    alpha = np.array([[0.25, 0.5, 1.0]], dtype=np.float32)

    adjusted = apply_edge_alpha_gamma(alpha, gamma=2.0)

    assert adjusted[0, 0] < alpha[0, 0]
    assert adjusted[0, 1] < alpha[0, 1]
    assert adjusted[0, 2] == pytest.approx(1.0)


def test_composite_on_white_uses_config_values() -> None:
    config = load_config(
        cli_overrides={
            "composite": {
                "line_darkness": 0.5,
                "edge_alpha_gamma": 1.0,
            }
        }
    )
    alpha = np.ones((1, 1), dtype=np.float32)

    final = composite_on_white(alpha, config)

    assert np.allclose(final, [[0.5]])


@pytest.mark.parametrize(
    "line_alpha",
    [
        np.array([np.nan], dtype=np.float32).reshape(1, 1),
        np.array([1.1], dtype=np.float32).reshape(1, 1),
        np.ones((1, 1, 1), dtype=np.float32),
        np.ones((0, 1), dtype=np.float32),
    ],
)
def test_composite_rejects_invalid_alpha(line_alpha: np.ndarray) -> None:
    with pytest.raises(ValueError):
        composite_black_lines(white_canvas((1, 1)), line_alpha)


def test_composite_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="same shape"):
        composite_black_lines(
            white_canvas((2, 2)),
            np.ones((2, 3), dtype=np.float32),
        )
