"""White-canvas and future tone compositing helpers."""

from __future__ import annotations

from typing import Any

import numpy as np

from mlu.grayscale import FloatImage


def white_canvas(shape: tuple[int, int]) -> FloatImage:
    """Return a white float32 canvas [0.0, 1.0], where 1.0 is white."""

    height, width = shape
    if height <= 0 or width <= 0:
        raise ValueError("canvas shape must be positive.")
    return np.ones((height, width), dtype=np.float32)


def apply_edge_alpha_gamma(line_alpha: FloatImage, gamma: float) -> FloatImage:
    """Apply gamma to line alpha in [0.0, 1.0]."""

    _validate_float_image(line_alpha, name="line_alpha")
    if gamma <= 0.0:
        raise ValueError("edge_alpha_gamma must be greater than 0.")
    return np.power(line_alpha, np.float32(gamma)).astype(np.float32, copy=False)


def composite_black_lines(
    canvas_or_tone: FloatImage,
    line_alpha: FloatImage,
    *,
    line_darkness: float = 1.0,
    edge_alpha_gamma: float = 1.0,
    clamp: bool = True,
) -> FloatImage:
    """Composite black line alpha onto a grayscale canvas.

    Both inputs and output use float32 [0.0, 1.0], where 0.0 is black and
    1.0 is white. The MVP uses a white canvas as `canvas_or_tone`.
    """

    _validate_float_image(canvas_or_tone, name="canvas_or_tone")
    _validate_float_image(line_alpha, name="line_alpha")
    if canvas_or_tone.shape != line_alpha.shape:
        raise ValueError("canvas_or_tone and line_alpha must have the same shape.")
    if not 0.0 <= line_darkness <= 1.0:
        raise ValueError("line_darkness must be between 0.0 and 1.0.")

    adjusted_alpha = apply_edge_alpha_gamma(line_alpha, edge_alpha_gamma)
    final = canvas_or_tone * (np.float32(1.0) - adjusted_alpha * np.float32(line_darkness))
    if clamp:
        final = np.clip(final, 0.0, 1.0)
    if not np.isfinite(final).all():
        raise ValueError("final image contains NaN or Inf.")
    return final.astype(np.float32, copy=False)


def composite_on_white(line_alpha: FloatImage, config: dict[str, Any]) -> FloatImage:
    """Composite high-resolution line alpha onto a white canvas."""

    composite_config = config.get("composite", {})
    canvas = white_canvas(line_alpha.shape)
    return composite_black_lines(
        canvas,
        line_alpha,
        line_darkness=float(composite_config.get("line_darkness", 1.0)),
        edge_alpha_gamma=float(composite_config.get("edge_alpha_gamma", 1.0)),
        clamp=bool(composite_config.get("clamp", True)),
    )


def _validate_float_image(image: FloatImage, *, name: str) -> None:
    if image.ndim != 2:
        raise ValueError(f"{name} must be a 2D array.")
    if image.size == 0:
        raise ValueError(f"{name} must not be empty.")
    if not np.issubdtype(image.dtype, np.floating):
        raise ValueError(f"{name} must be a floating point array.")
    if not np.isfinite(image).all():
        raise ValueError(f"{name} must not contain NaN or Inf.")
    if float(image.min()) < 0.0 or float(image.max()) > 1.0:
        raise ValueError(f"{name} values must be in [0.0, 1.0].")
