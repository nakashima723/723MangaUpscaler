"""Line mask extraction helpers.

Input grayscale arrays use float32 values in [0.0, 1.0], where 0.0 is black
and 1.0 is white.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage

from mlu.grayscale import FloatImage

BoolImage = NDArray[np.bool_]


@dataclass(frozen=True)
class LineMaps:
    """Line extraction maps at source resolution."""

    line_prob: FloatImage
    line_mask: BoolImage
    line_soft: FloatImage
    darkness: FloatImage
    warnings: tuple[str, ...] = ()

    @property
    def mask_area_ratio(self) -> float:
        """Return line mask area ratio in [0.0, 1.0]."""

        return float(self.line_mask.mean())


def extract_line_maps(gray: FloatImage, config: dict[str, Any]) -> LineMaps:
    """Extract line probability, binary mask, and soft line map from grayscale input."""

    _validate_gray(gray)
    mask_config = config.get("mask", {})
    threshold = float(mask_config.get("black_threshold", 0.72))
    hysteresis_config = mask_config.get("hysteresis", {})
    cleanup_config = mask_config.get("cleanup", {})

    darkness = compute_darkness(gray)
    line_prob = compute_line_probability(
        darkness,
        strong=float(hysteresis_config.get("strong", 0.50)),
        weak=float(hysteresis_config.get("weak", 0.25)),
    )
    fixed_mask = fixed_threshold_mask(gray, threshold)

    if hysteresis_config.get("enabled", True):
        hysteresis_mask = hysteresis_threshold(
            darkness,
            strong=float(hysteresis_config.get("strong", 0.50)),
            weak=float(hysteresis_config.get("weak", 0.25)),
        )
        line_mask = fixed_mask | hysteresis_mask
    else:
        line_mask = fixed_mask

    line_mask = cleanup_mask(
        line_mask,
        min_component_area=int(cleanup_config.get("min_component_area", 6)),
        close_radius=int(cleanup_config.get("close_radius", 0)),
        fill_holes_area=int(cleanup_config.get("fill_holes_area", 12)),
    )
    soft_coverage_config = mask_config.get("soft_coverage", {})
    line_soft = compute_line_soft(
        darkness,
        line_prob,
        line_mask,
        weak=float(hysteresis_config.get("weak", 0.25)),
        coverage_mode=str(soft_coverage_config.get("mode", "darkness")),
        coverage_gamma=float(soft_coverage_config.get("gamma", 1.0)),
    )

    warnings = mask_warnings(line_mask)
    return LineMaps(
        line_prob=line_prob,
        line_mask=line_mask,
        line_soft=line_soft,
        darkness=darkness,
        warnings=warnings,
    )


def compute_darkness(gray: FloatImage) -> FloatImage:
    """Return darkness = 1 - gray as float32 [0.0, 1.0]."""

    _validate_gray(gray)
    return (np.float32(1.0) - gray).astype(np.float32, copy=False)


def compute_line_probability(darkness: FloatImage, *, strong: float, weak: float) -> FloatImage:
    """Map darkness to line probability using weak/strong thresholds."""

    if strong <= weak:
        raise ValueError("strong threshold must be greater than weak threshold.")

    probability = (darkness - np.float32(weak)) / np.float32(strong - weak)
    return np.clip(probability, 0.0, 1.0).astype(np.float32, copy=False)


def compute_line_soft(
    darkness: FloatImage,
    line_prob: FloatImage,
    line_mask: BoolImage,
    *,
    weak: float,
    coverage_mode: str = "darkness",
    coverage_gamma: float = 1.0,
) -> FloatImage:
    """Preserve source line coverage on extracted line support."""

    _validate_gray(darkness)
    _validate_gray(line_prob)
    if line_prob.shape != darkness.shape:
        raise ValueError("line_prob shape must match darkness.")
    if line_mask.shape != darkness.shape:
        raise ValueError("line_mask shape must match darkness.")
    if line_mask.dtype != np.bool_:
        raise ValueError("line_mask must be a boolean array.")
    if not 0.0 <= weak <= 1.0:
        raise ValueError("weak must be between 0.0 and 1.0.")
    if coverage_gamma <= 0.0:
        raise ValueError("coverage_gamma must be greater than 0.0.")

    support = line_mask | (line_prob > np.float32(0.0)) | (darkness >= np.float32(weak))
    coverage = _soft_coverage_from_mode(darkness, line_prob, coverage_mode=coverage_mode)
    if coverage_gamma != 1.0:
        coverage = np.power(np.clip(coverage, 0.0, 1.0), np.float32(coverage_gamma))
    return np.where(support, coverage, np.float32(0.0)).astype(np.float32, copy=False)


def _soft_coverage_from_mode(
    darkness: FloatImage,
    line_prob: FloatImage,
    *,
    coverage_mode: str,
) -> FloatImage:
    normalized = coverage_mode.lower().replace("-", "_")
    if normalized == "darkness":
        return darkness.astype(np.float32, copy=False)
    if normalized in {"line_probability", "probability", "line_prob"}:
        return line_prob.astype(np.float32, copy=False)
    if normalized in {"max", "max_probability", "legacy_max"}:
        return np.maximum(darkness, line_prob).astype(np.float32, copy=False)
    raise ValueError(
        "coverage_mode must be one of: darkness, line_probability, max_probability."
    )


def fixed_threshold_mask(gray: FloatImage, threshold: float) -> BoolImage:
    """Return mask for pixels darker than the source grayscale threshold."""

    _validate_gray(gray)
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0.")
    return (gray < np.float32(threshold)).astype(np.bool_)


def hysteresis_threshold(darkness: FloatImage, *, strong: float, weak: float) -> BoolImage:
    """Return weak pixels connected to strong pixels using 8-connectivity."""

    if strong <= weak:
        raise ValueError("strong threshold must be greater than weak threshold.")

    strong_mask = darkness >= np.float32(strong)
    weak_mask = darkness >= np.float32(weak)
    if not strong_mask.any():
        return np.zeros_like(weak_mask, dtype=np.bool_)

    return ndimage.binary_propagation(
        strong_mask,
        structure=_connectivity_structure(),
        mask=weak_mask,
    ).astype(np.bool_)


def cleanup_mask(
    line_mask: BoolImage,
    *,
    min_component_area: int,
    close_radius: int,
    fill_holes_area: int,
) -> BoolImage:
    """Clean line mask by optional closing, small component removal, and small hole fill."""

    cleaned = line_mask.astype(np.bool_, copy=True)
    if close_radius > 0:
        cleaned = ndimage.binary_closing(
            cleaned,
            structure=_square_structure(close_radius),
        ).astype(np.bool_)

    if min_component_area > 1:
        cleaned = remove_small_components(cleaned, min_area=min_component_area)

    if fill_holes_area > 0:
        cleaned = fill_small_holes(cleaned, max_area=fill_holes_area)

    return cleaned.astype(np.bool_, copy=False)


def remove_small_components(mask: BoolImage, *, min_area: int) -> BoolImage:
    """Remove connected true components smaller than min_area."""

    labels, count = ndimage.label(mask, structure=_connectivity_structure())
    if count == 0:
        return mask.astype(np.bool_, copy=True)

    sizes = np.bincount(labels.ravel())
    keep = sizes >= min_area
    keep[0] = False
    return keep[labels].astype(np.bool_)


def fill_small_holes(mask: BoolImage, *, max_area: int) -> BoolImage:
    """Fill false regions fully enclosed by true pixels when their area is small enough."""

    labels, count = ndimage.label(~mask, structure=_connectivity_structure())
    if count == 0:
        return mask.astype(np.bool_, copy=True)

    sizes = np.bincount(labels.ravel())
    fill = (sizes <= max_area) & (sizes > 0)
    border_labels = np.unique(
        np.concatenate((labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]))
    )
    fill[border_labels] = False
    return (mask | fill[labels]).astype(np.bool_)


def mask_warnings(line_mask: BoolImage) -> tuple[str, ...]:
    """Return warnings for suspicious line mask area ratios."""

    ratio = float(line_mask.mean())
    warnings: list[str] = []
    if ratio < 0.001:
        warnings.append("line_mask is almost empty")
    if ratio > 0.60:
        warnings.append("line_mask covers too much of the image")
    return tuple(warnings)


def _validate_gray(gray: FloatImage) -> None:
    if gray.ndim != 2:
        raise ValueError("gray must be a 2D array.")
    if not np.issubdtype(gray.dtype, np.floating):
        raise ValueError("gray must be a floating point array.")
    if not np.isfinite(gray).all():
        raise ValueError("gray must not contain NaN or Inf.")
    if float(gray.min()) < 0.0 or float(gray.max()) > 1.0:
        raise ValueError("gray values must be in [0.0, 1.0].")


def _connectivity_structure() -> BoolImage:
    return ndimage.generate_binary_structure(2, 2).astype(np.bool_)


def _square_structure(radius: int) -> BoolImage:
    width = radius * 2 + 1
    return np.ones((width, width), dtype=np.bool_)
