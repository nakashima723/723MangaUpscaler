"""Experimental relative separation of line ink and grayscale tone.

The observation model is ``gray ~= tone * (1 - line_alpha)``.  Estimating
``tone`` locally therefore lets the line branch use relative contrast instead
of treating a fixed source luminance as ink everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import ndimage

from mlu.grayscale import FloatImage
from mlu.mask_extract import (
    BoolImage,
    LineMaps,
    cleanup_mask,
    extract_line_maps,
    mask_warnings,
)


@dataclass(frozen=True)
class LayerSeparationResult:
    """Source-resolution line/tone layers and lightweight diagnostics."""

    tone: FloatImage
    relative_contrast: FloatImage
    line_alpha: FloatImage
    line_image: FloatImage
    line_maps: LineMaps
    line_coverage_mode: str
    legacy_blend_weight: FloatImage
    relative_coverage_gain: float
    legacy_blend_start: float
    legacy_blend_end: float
    closing_radius: int
    weak_relative_contrast: float
    strong_relative_contrast: float
    weak_absolute_contrast: float
    strong_absolute_contrast: float
    tone_floor: float

    def to_metadata(self) -> dict[str, float | int | str]:
        """Return JSON-serializable separation diagnostics."""

        return {
            "closing_radius": self.closing_radius,
            "weak_relative_contrast": self.weak_relative_contrast,
            "strong_relative_contrast": self.strong_relative_contrast,
            "weak_absolute_contrast": self.weak_absolute_contrast,
            "strong_absolute_contrast": self.strong_absolute_contrast,
            "tone_floor": self.tone_floor,
            "line_coverage_mode": self.line_coverage_mode,
            "relative_coverage_gain": self.relative_coverage_gain,
            "legacy_blend_start": self.legacy_blend_start,
            "legacy_blend_end": self.legacy_blend_end,
            "legacy_blend_weight_mean": float(self.legacy_blend_weight.mean()),
            "tone_min": float(self.tone.min()),
            "tone_max": float(self.tone.max()),
            "tone_mean": float(self.tone.mean()),
            "line_alpha_mean": float(self.line_alpha.mean()),
            "line_support_ratio": float((self.line_alpha >= np.float32(0.25)).mean()),
            "render_line_coverage_mean": float(self.line_maps.line_soft.mean()),
            "render_line_support_ratio": float(
                (self.line_maps.line_soft >= np.float32(0.25)).mean()
            ),
        }


def separate_relative_layers(
    gray: FloatImage,
    config: dict[str, Any],
) -> LayerSeparationResult:
    """Separate a grayscale image using local background-relative darkness.

    A grayscale closing estimates the tone that would remain if narrow dark
    strokes were removed.  The multiplicative observation model then gives a
    line coverage estimate that remains meaningful on both white and gray
    backgrounds.  Broad or smoothly varying dark regions remain in ``tone``.
    """

    _validate_gray(gray)
    separation_config = config.get("grayscale_processing", {})
    closing_radius = int(separation_config.get("closing_radius", 6))
    weak_relative_contrast = float(
        separation_config.get("weak_relative_contrast", 0.035)
    )
    strong_relative_contrast = float(
        separation_config.get("strong_relative_contrast", 0.12)
    )
    weak_absolute_contrast = float(
        separation_config.get("weak_absolute_contrast", 1.0 / 255.0)
    )
    strong_absolute_contrast = float(
        separation_config.get("strong_absolute_contrast", 3.0 / 255.0)
    )
    tone_floor = float(separation_config.get("tone_floor", 1.0 / 255.0))
    line_coverage_mode = str(
        separation_config.get("line_coverage_mode", "quality_hybrid")
    )
    relative_coverage_gain = float(
        separation_config.get("relative_coverage_gain", 2.425)
    )
    legacy_blend_start = float(separation_config.get("legacy_blend_start", 0.90))
    legacy_blend_end = float(separation_config.get("legacy_blend_end", 0.98))

    footprint = _disk_footprint(closing_radius)
    tone = ndimage.grey_closing(gray, footprint=footprint, mode="nearest")
    tone = np.maximum(tone, gray)
    tone = np.clip(tone, 0.0, 1.0).astype(np.float32, copy=False)
    routing_background = tone.astype(np.float32, copy=True)
    _suppress_unsupported_border_estimate(tone, gray, radius=closing_radius)

    local_background = tone
    delta = (local_background - gray).astype(np.float32, copy=False)
    denominator = np.maximum(local_background, np.float32(tone_floor))
    relative_contrast = np.clip(
        delta / denominator,
        0.0,
        1.0,
    ).astype(np.float32, copy=False)

    weak_mask = (relative_contrast >= np.float32(weak_relative_contrast)) & (
        delta >= np.float32(weak_absolute_contrast)
    )
    strong_mask = (relative_contrast >= np.float32(strong_relative_contrast)) & (
        delta >= np.float32(strong_absolute_contrast)
    )
    if strong_mask.any():
        line_mask = ndimage.binary_propagation(
            strong_mask,
            structure=ndimage.generate_binary_structure(2, 2),
            mask=weak_mask,
        ).astype(np.bool_)
    else:
        line_mask = np.zeros_like(weak_mask, dtype=np.bool_)
    cleanup_config = config.get("mask", {}).get("cleanup", {})
    line_mask = cleanup_mask(
        line_mask,
        min_component_area=int(cleanup_config.get("min_component_area", 4)),
        close_radius=int(cleanup_config.get("close_radius", 0)),
        fill_holes_area=int(cleanup_config.get("fill_holes_area", 12)),
    )

    normalized = np.clip(
        (relative_contrast - np.float32(weak_relative_contrast))
        / np.float32(strong_relative_contrast - weak_relative_contrast),
        0.0,
        1.0,
    )
    line_probability = normalized * normalized * (np.float32(3.0) - np.float32(2.0) * normalized)
    relative_line_alpha = np.where(
        line_mask,
        relative_contrast,
        np.float32(0.0),
    ).astype(np.float32, copy=False)
    legacy_blend_weight = np.zeros_like(gray, dtype=np.float32)
    if line_coverage_mode == "quality_hybrid":
        legacy_blend_weight = _smoothstep_range(
            routing_background,
            start=legacy_blend_start,
            end=legacy_blend_end,
        )
        legacy_line_soft = extract_line_maps(gray, config).line_soft
        relative_render_coverage = np.clip(
            relative_line_alpha * np.float32(relative_coverage_gain),
            0.0,
            1.0,
        )
        line_coverage = (
            legacy_blend_weight * legacy_line_soft
            + (np.float32(1.0) - legacy_blend_weight) * relative_render_coverage
        )
    elif line_coverage_mode == "relative_contrast":
        line_coverage = relative_line_alpha
    elif line_coverage_mode == "detection_probability":
        line_coverage = np.where(line_mask, line_probability, np.float32(0.0))
    else:
        raise ValueError(
            "grayscale_processing.line_coverage_mode must be one of: "
            "quality_hybrid, relative_contrast, detection_probability."
        )
    line_coverage = np.clip(line_coverage, 0.0, 1.0).astype(np.float32, copy=False)
    line_image = (np.float32(1.0) - line_coverage).astype(np.float32, copy=False)

    tone_support = line_mask | (line_coverage >= np.float32(weak_relative_contrast))

    tone_weight = _tone_replacement_weight(
        tone_support,
        dilate_radius=int(separation_config.get("tone_dilate_radius", 1)),
        feather_sigma=float(separation_config.get("tone_feather_sigma", 0.5)),
    )
    tone_target = (
        legacy_blend_weight * routing_background
        + (np.float32(1.0) - legacy_blend_weight) * local_background
    )
    tone = gray + tone_weight * (tone_target - gray)
    tone = np.clip(tone, 0.0, 1.0).astype(np.float32, copy=False)
    line_maps = LineMaps(
        line_prob=line_probability.astype(np.float32, copy=False),
        line_mask=tone_support,
        line_soft=line_coverage,
        darkness=relative_contrast,
        warnings=mask_warnings(line_mask),
    )

    return LayerSeparationResult(
        tone=tone,
        relative_contrast=relative_contrast,
        line_alpha=relative_line_alpha,
        line_image=line_image,
        line_maps=line_maps,
        line_coverage_mode=line_coverage_mode,
        legacy_blend_weight=legacy_blend_weight,
        relative_coverage_gain=relative_coverage_gain,
        legacy_blend_start=legacy_blend_start,
        legacy_blend_end=legacy_blend_end,
        closing_radius=closing_radius,
        weak_relative_contrast=weak_relative_contrast,
        strong_relative_contrast=strong_relative_contrast,
        weak_absolute_contrast=weak_absolute_contrast,
        strong_absolute_contrast=strong_absolute_contrast,
        tone_floor=tone_floor,
    )


def _tone_replacement_weight(
    line_mask: BoolImage,
    *,
    dilate_radius: int,
    feather_sigma: float,
) -> FloatImage:
    if dilate_radius < 0:
        raise ValueError("grayscale_processing.tone_dilate_radius must be non-negative.")
    if feather_sigma < 0.0:
        raise ValueError("grayscale_processing.tone_feather_sigma must be non-negative.")
    support = line_mask
    if dilate_radius > 0:
        support = ndimage.binary_dilation(
            support,
            structure=_disk_footprint(dilate_radius),
        )
    weight = support.astype(np.float32)
    if feather_sigma > 0.0:
        weight = ndimage.gaussian_filter(weight, sigma=feather_sigma, mode="nearest")
    return np.clip(weight, 0.0, 1.0).astype(np.float32, copy=False)


def _disk_footprint(radius: int) -> np.ndarray:
    if radius < 1:
        raise ValueError("grayscale_processing.closing_radius must be at least 1.")
    yy, xx = np.ogrid[-radius : radius + 1, -radius : radius + 1]
    return (xx * xx + yy * yy <= radius * radius).astype(np.bool_)


def _smoothstep_range(
    image: FloatImage,
    *,
    start: float,
    end: float,
) -> FloatImage:
    if end <= start:
        raise ValueError("legacy_blend_end must be greater than legacy_blend_start.")
    normalized = np.clip(
        (image - np.float32(start)) / np.float32(end - start),
        0.0,
        1.0,
    )
    return (
        normalized * normalized * (np.float32(3.0) - np.float32(2.0) * normalized)
    ).astype(np.float32, copy=False)


def _suppress_unsupported_border_estimate(
    estimate: FloatImage,
    source: FloatImage,
    *,
    radius: int,
) -> None:
    """Avoid treating closing padding artifacts as lines at the image edge."""

    border = min(radius, estimate.shape[0], estimate.shape[1])
    if border <= 0:
        return
    estimate[:border, :] = source[:border, :]
    estimate[-border:, :] = source[-border:, :]
    estimate[:, :border] = source[:, :border]
    estimate[:, -border:] = source[:, -border:]


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
