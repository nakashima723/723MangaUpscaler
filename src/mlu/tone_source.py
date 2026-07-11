"""Tone-source generation helpers for the grayscale branch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import diplib as dip
import numpy as np
from scipy import ndimage

from mlu.grayscale import FloatImage
from mlu.mask_extract import BoolImage, LineMaps


@dataclass(frozen=True)
class ToneSourceResult:
    """Tone-source image and lightweight diagnostics.

    `image` is source-resolution float32 [0.0, 1.0], where 0.0 is black and
    1.0 is white.
    """

    image: FloatImage
    mode: str
    is_likely_pure_lineart: bool
    line_lift_ratio: float
    midtone_ratio: float


def generate_tone_source(
    gray: FloatImage,
    line_maps: LineMaps,
    config: dict[str, Any],
) -> ToneSourceResult:
    """Generate source-resolution tone input for a later grayscale upscaler."""

    _validate_gray(gray)
    if line_maps.line_mask.shape != gray.shape:
        raise ValueError("line_maps shape must match gray.")

    tone_config = config.get("tone_source", {})
    mode = str(tone_config.get("mode", "white_canvas"))
    is_pure, midtone_ratio = detect_likely_pure_lineart(gray, line_maps.line_mask)

    if mode == "white_canvas":
        image = np.ones_like(gray, dtype=np.float32)
    elif mode == "passthrough":
        image = gray.astype(np.float32, copy=True)
    elif mode == "lift_lines":
        image = lift_line_regions(
            gray,
            line_maps,
            dilate_radius=float(tone_config.get("dilate_radius", 1.2)),
            lift_strength=float(tone_config.get("lift_strength", 0.85)),
            background_blur_radius=float(tone_config.get("background_blur_radius", 9.0)),
            protect_midtones=bool(tone_config.get("protect_midtones", True)),
        )
    else:
        raise ValueError(f"Unsupported tone_source.mode: {mode}")

    line_lift_ratio = _line_lift_ratio(gray, image, line_maps.line_mask)
    return ToneSourceResult(
        image=image,
        mode=mode,
        is_likely_pure_lineart=is_pure,
        line_lift_ratio=line_lift_ratio,
        midtone_ratio=midtone_ratio,
    )


def lift_line_regions(
    gray: FloatImage,
    line_maps: LineMaps,
    *,
    dilate_radius: float,
    lift_strength: float,
    background_blur_radius: float,
    protect_midtones: bool,
) -> FloatImage:
    """Lift line-supported regions toward a blurred local background estimate."""

    _validate_gray(gray)
    if dilate_radius < 0.0:
        raise ValueError("dilate_radius must be non-negative.")
    if not 0.0 <= lift_strength <= 1.0:
        raise ValueError("lift_strength must be between 0.0 and 1.0.")
    if background_blur_radius < 0.0:
        raise ValueError("background_blur_radius must be non-negative.")
    if line_maps.line_mask.shape != gray.shape:
        raise ValueError("line_maps shape must match gray.")

    distance = distance_from_line(line_maps.line_mask)
    if line_maps.line_mask.any():
        lift_weight = np.clip(
            (np.float32(dilate_radius + 1.0) - distance) / np.float32(dilate_radius + 1.0),
            0.0,
            1.0,
        ).astype(np.float32, copy=False)
    else:
        lift_weight = np.zeros_like(gray, dtype=np.float32)

    lift_mask = lift_weight > np.float32(0.0)
    background_seed = np.where(lift_mask, np.float32(1.0), gray).astype(np.float32, copy=False)
    if background_blur_radius > 0.0:
        background = ndimage.gaussian_filter(
            background_seed,
            sigma=float(background_blur_radius),
            mode="nearest",
        ).astype(np.float32, copy=False)
    else:
        background = background_seed
    target = np.maximum(gray, background).astype(np.float32, copy=False)

    if protect_midtones:
        line_strength = np.maximum(
            line_maps.line_soft,
            line_maps.line_mask.astype(np.float32),
        )
        protection = np.clip(line_strength + lift_weight * np.float32(0.20), 0.0, 1.0)
        lift_weight = lift_weight * protection

    lifted = gray + (target - gray) * np.float32(lift_strength) * lift_weight
    return np.clip(lifted, 0.0, 1.0).astype(np.float32, copy=False)


def distance_from_line(line_mask: BoolImage) -> FloatImage:
    """Return distance to the nearest line pixel in source pixels."""

    if line_mask.ndim != 2:
        raise ValueError("line_mask must be a 2D array.")
    if line_mask.dtype != np.bool_:
        raise ValueError("line_mask must be a boolean array.")
    if line_mask.size == 0:
        raise ValueError("line_mask must not be empty.")
    if not line_mask.any():
        return np.full(line_mask.shape, np.inf, dtype=np.float32)
    distance = dip.EuclideanDistanceTransform(~line_mask, "object", "separable")
    return np.asarray(distance, dtype=np.float32)


def dilated_line_mask(line_mask: BoolImage, *, radius: float) -> BoolImage:
    """Dilate line pixels by Euclidean source-pixel radius."""

    if radius < 0.0:
        raise ValueError("radius must be non-negative.")
    distance = distance_from_line(line_mask)
    return (distance <= np.float32(radius)).astype(np.bool_)


def detect_likely_pure_lineart(gray: FloatImage, line_mask: BoolImage) -> tuple[bool, float]:
    """Return a simple pure-line-art guess and background midtone ratio."""

    _validate_gray(gray)
    if line_mask.shape != gray.shape:
        raise ValueError("line_mask shape must match gray.")
    yy, xx = np.mgrid[-2:3, -2:3]
    radius_two_disk = (xx * xx + yy * yy) <= 4
    background = ~ndimage.binary_dilation(line_mask, structure=radius_two_disk)
    if not background.any():
        return True, 0.0
    midtone = (gray > np.float32(0.08)) & (gray < np.float32(0.92)) & background
    midtone_ratio = float(midtone.sum() / background.sum())
    return midtone_ratio < 0.02, midtone_ratio


def _line_lift_ratio(before: FloatImage, after: FloatImage, line_mask: BoolImage) -> float:
    if not line_mask.any():
        return 0.0
    return float(np.mean(after[line_mask] - before[line_mask]))


def _validate_gray(gray: FloatImage) -> None:
    if gray.ndim != 2:
        raise ValueError("gray must be a 2D array.")
    if gray.size == 0:
        raise ValueError("gray must not be empty.")
    if not np.issubdtype(gray.dtype, np.floating):
        raise ValueError("gray must be a floating point array.")
    if not np.isfinite(gray).all():
        raise ValueError("gray must not contain NaN or Inf.")
    if float(gray.min()) < 0.0 or float(gray.max()) > 1.0:
        raise ValueError("gray values must be in [0.0, 1.0].")
