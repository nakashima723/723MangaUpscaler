"""Grayscale normalization helpers.

Internal grayscale arrays use float32 values in the range [0.0, 1.0], where
0.0 is black and 1.0 is white.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatImage = NDArray[np.float32]


def ensure_float_gray(array: NDArray[np.generic], *, invert: bool = False) -> FloatImage:
    """Normalize a grayscale array to float32 [0.0, 1.0], 0.0 black and 1.0 white."""

    if array.ndim != 2:
        raise ValueError("Expected a 2D grayscale array.")

    if np.issubdtype(array.dtype, np.floating):
        gray = array.astype(np.float32, copy=False)
    elif array.dtype == np.uint16:
        gray = array.astype(np.float32) / np.float32(65535.0)
    else:
        gray = array.astype(np.float32) / np.float32(255.0)

    gray = np.clip(gray, 0.0, 1.0).astype(np.float32, copy=False)
    if invert:
        gray = np.float32(1.0) - gray
    return gray


def rgb_to_grayscale(rgb: NDArray[np.generic], *, invert: bool = False) -> FloatImage:
    """Convert RGB-like data to float32 grayscale [0.0, 1.0], 0.0 black and 1.0 white."""

    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Expected an array with shape (H, W, 3).")

    rgb_float = rgb.astype(np.float32)
    if rgb.dtype == np.uint16:
        rgb_float /= np.float32(65535.0)
    else:
        rgb_float /= np.float32(255.0)

    gray = (
        np.float32(0.2126) * rgb_float[..., 0]
        + np.float32(0.7152) * rgb_float[..., 1]
        + np.float32(0.0722) * rgb_float[..., 2]
    )
    gray = np.clip(gray, 0.0, 1.0).astype(np.float32, copy=False)
    if invert:
        gray = np.float32(1.0) - gray
    return gray


def rgba_to_grayscale_on_white(rgba: NDArray[np.generic], *, invert: bool = False) -> FloatImage:
    """Composite RGBA on white, then convert to float32 grayscale [0.0, 1.0]."""

    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("Expected an array with shape (H, W, 4).")

    rgba_float = rgba.astype(np.float32)
    if rgba.dtype == np.uint16:
        rgba_float /= np.float32(65535.0)
    else:
        rgba_float /= np.float32(255.0)

    rgb = rgba_float[..., :3]
    alpha = rgba_float[..., 3:4]
    composited = rgb * alpha + (np.float32(1.0) - alpha)
    gray = (
        np.float32(0.2126) * composited[..., 0]
        + np.float32(0.7152) * composited[..., 1]
        + np.float32(0.0722) * composited[..., 2]
    )
    gray = np.clip(gray, 0.0, 1.0).astype(np.float32, copy=False)
    if invert:
        gray = np.float32(1.0) - gray
    return gray
