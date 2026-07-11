"""Directional smoothing for non-axis-aligned line alpha."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import ndimage

from mlu.grayscale import FloatImage


@dataclass(frozen=True)
class DirectionalSmoothingResult:
    """Result of support-gated directional alpha smoothing."""

    line_alpha_hr: FloatImage
    source_alpha_hr: FloatImage | None
    weight_hr: FloatImage
    delta_hr: FloatImage
    applied: bool
    stats: dict[str, float | int | bool | str]


def smooth_directional_alpha(
    line_alpha_hr: FloatImage,
    config: dict[str, Any],
    *,
    renderer: str = "sdf",
) -> DirectionalSmoothingResult:
    """Smooth jagged non-axis-aligned strokes without fitting new lines."""

    _validate_alpha(line_alpha_hr)
    smoothing_config = config.get("directional_smoothing", {})
    empty = np.zeros_like(line_alpha_hr, dtype=np.float32)
    if renderer != "sdf" or not bool(smoothing_config.get("enabled", False)):
        return DirectionalSmoothingResult(
            line_alpha_hr=line_alpha_hr,
            source_alpha_hr=None,
            weight_hr=empty,
            delta_hr=empty,
            applied=False,
            stats={
                "enabled": bool(smoothing_config.get("enabled", False)),
                "applied": False,
                "reason": "disabled" if renderer == "sdf" else "non_sdf_renderer",
            },
        )

    strength = float(smoothing_config.get("strength", 0.55))
    radius = int(smoothing_config.get("radius_hr_px", 2))
    if strength <= 0.0 or radius <= 0:
        return DirectionalSmoothingResult(
            line_alpha_hr=line_alpha_hr,
            source_alpha_hr=None,
            weight_hr=empty,
            delta_hr=empty,
            applied=False,
            stats={
                "enabled": True,
                "applied": False,
                "reason": "zero_strength_or_radius",
            },
        )

    alpha = np.clip(line_alpha_hr, 0.0, 1.0).astype(np.float32, copy=False)
    tangent_degrees, confidence, energy = estimate_tangent_field(
        alpha,
        orientation_sigma=float(smoothing_config.get("orientation_sigma_hr_px", 1.0)),
        tensor_sigma=float(smoothing_config.get("tensor_sigma_hr_px", 2.0)),
    )
    selected = _local_directional_average(alpha, tangent_degrees, radius=radius)
    gate = _smoothing_gate(alpha, tangent_degrees, confidence, energy, config)
    if float(gate.max(initial=0.0)) <= 0.0:
        return DirectionalSmoothingResult(
            line_alpha_hr=line_alpha_hr,
            source_alpha_hr=None,
            weight_hr=empty,
            delta_hr=empty,
            applied=False,
            stats={
                "enabled": True,
                "applied": False,
                "reason": "empty_gate",
            },
        )

    max_delta = float(smoothing_config.get("max_delta", 0.35))
    delta = np.clip(selected - alpha, -max_delta, max_delta).astype(np.float32, copy=False)
    confidence_weight = _confidence_weight(
        confidence,
        minimum=float(smoothing_config.get("min_orientation_confidence", 0.12)),
    )
    weight = (
        np.float32(np.clip(strength, 0.0, 1.0)) * gate * confidence_weight
    )
    smoothed = np.clip(alpha + delta * weight, 0.0, 1.0).astype(np.float32, copy=False)
    applied_delta = np.abs(smoothed - alpha).astype(np.float32, copy=False)

    return DirectionalSmoothingResult(
        line_alpha_hr=smoothed,
        source_alpha_hr=alpha.copy(),
        weight_hr=weight.astype(np.float32, copy=False),
        delta_hr=np.clip(applied_delta / max(max_delta, 1.0e-6), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        ),
        applied=True,
        stats={
            "enabled": True,
            "applied": True,
            "sampling_mode": "local_angle",
            "radius_hr_px": radius,
            "strength": float(np.clip(strength, 0.0, 1.0)),
            "min_angle_from_axis_degrees": float(
                smoothing_config.get("min_angle_from_axis_degrees", 20.0)
            ),
            "full_strength_angle_from_axis_degrees": float(
                smoothing_config.get("full_strength_angle_from_axis_degrees", 34.0)
            ),
            "active_weight_ratio": float(np.count_nonzero(weight > 1.0e-4))
            / float(weight.size),
            "changed_pixel_ratio": float(np.count_nonzero(applied_delta > 1.0e-4))
            / float(applied_delta.size),
            "mean_abs_delta": float(applied_delta.mean()),
            "max_abs_delta": float(applied_delta.max()),
        },
    )


def estimate_tangent_field(
    alpha: FloatImage,
    *,
    orientation_sigma: float,
    tensor_sigma: float,
) -> tuple[FloatImage, FloatImage, FloatImage]:
    """Estimate local stroke tangent direction from a structure tensor."""

    if orientation_sigma < 0.0:
        raise ValueError("orientation_sigma must be non-negative.")
    if tensor_sigma < 0.0:
        raise ValueError("tensor_sigma must be non-negative.")

    source = alpha.astype(np.float32, copy=False)
    if orientation_sigma > 0.0:
        source = ndimage.gaussian_filter(source, sigma=orientation_sigma).astype(
            np.float32,
            copy=False,
        )
    gradient_y, gradient_x = np.gradient(source)
    jxx = ndimage.gaussian_filter(gradient_x * gradient_x, sigma=tensor_sigma)
    jxy = ndimage.gaussian_filter(gradient_x * gradient_y, sigma=tensor_sigma)
    jyy = ndimage.gaussian_filter(gradient_y * gradient_y, sigma=tensor_sigma)

    normal = 0.5 * np.arctan2(2.0 * jxy, jxx - jyy)
    tangent = np.mod(np.rad2deg(normal + np.pi / 2.0), 180.0).astype(np.float32, copy=False)
    anisotropy = np.sqrt((jxx - jyy) * (jxx - jyy) + 4.0 * jxy * jxy)
    energy = (jxx + jyy).astype(np.float32, copy=False)
    confidence = (anisotropy / (energy + np.float32(1.0e-6))).astype(np.float32, copy=False)
    return tangent, np.clip(confidence, 0.0, 1.0), energy


def _local_directional_average(
    alpha: FloatImage,
    tangent_degrees: FloatImage,
    *,
    radius: int,
) -> FloatImage:
    height, width = alpha.shape
    y_coords, x_coords = np.indices((height, width), dtype=np.float32)
    radians = np.deg2rad(tangent_degrees).astype(np.float32, copy=False)
    direction_x = np.cos(radians).astype(np.float32, copy=False)
    direction_y = np.sin(radians).astype(np.float32, copy=False)
    accumulated = np.zeros_like(alpha, dtype=np.float32)
    for step in range(-radius, radius + 1):
        sample_y = y_coords - direction_y * np.float32(step)
        sample_x = x_coords - direction_x * np.float32(step)
        accumulated += ndimage.map_coordinates(
            alpha,
            (sample_y, sample_x),
            order=1,
            mode="nearest",
            prefilter=False,
        ).astype(np.float32, copy=False)
    return (accumulated / np.float32(radius * 2 + 1)).astype(np.float32, copy=False)


def _smoothing_gate(
    alpha: FloatImage,
    tangent_degrees: FloatImage,
    confidence: FloatImage,
    energy: FloatImage,
    config: dict[str, Any],
) -> FloatImage:
    smoothing_config = config.get("directional_smoothing", {})
    min_alpha = float(smoothing_config.get("min_alpha", 0.04))
    support_dilate = int(smoothing_config.get("support_dilate_hr_px", 1))
    support_size = support_dilate * 2 + 1
    local_support = ndimage.maximum_filter(alpha, size=support_size) >= np.float32(min_alpha)
    angle_weight = _angle_gate_weight(
        tangent_degrees,
        start_degrees=float(smoothing_config.get("min_angle_from_axis_degrees", 20.0)),
        full_degrees=float(smoothing_config.get("full_strength_angle_from_axis_degrees", 34.0)),
    )
    gate = (
        local_support
        & (
            confidence
            >= np.float32(float(smoothing_config.get("min_orientation_confidence", 0.12)))
        )
        & (energy >= np.float32(float(smoothing_config.get("min_gradient_energy", 1.0e-5))))
    )
    return (gate.astype(np.float32) * angle_weight).astype(np.float32, copy=False)


def _angle_gate_weight(
    tangent_degrees: FloatImage,
    *,
    start_degrees: float,
    full_degrees: float,
) -> FloatImage:
    if start_degrees < 0.0 or start_degrees >= 45.0:
        raise ValueError("start_degrees must be in [0, 45).")
    if full_degrees <= start_degrees or full_degrees > 45.0:
        raise ValueError("full_degrees must be greater than start_degrees and at most 45.")
    axis_distance = _axis_distance_degrees(tangent_degrees)
    weight = (axis_distance - np.float32(start_degrees)) / np.float32(
        max(full_degrees - start_degrees, 1.0e-6)
    )
    return np.clip(weight, 0.0, 1.0).astype(np.float32, copy=False)


def _confidence_weight(confidence: FloatImage, *, minimum: float) -> FloatImage:
    if minimum >= 1.0:
        return (confidence >= np.float32(minimum)).astype(np.float32)
    weight = (confidence - np.float32(minimum)) / np.float32(max(1.0 - minimum, 1.0e-6))
    return np.clip(weight, 0.0, 1.0).astype(np.float32, copy=False)


def _axis_distance_degrees(angle: float | FloatImage) -> float | FloatImage:
    angle_array = np.asarray(angle, dtype=np.float32)
    distance = np.minimum(
        np.minimum(np.abs(angle_array), np.abs(angle_array - np.float32(90.0))),
        np.abs(angle_array - np.float32(180.0)),
    )
    if np.isscalar(angle):
        return float(distance)
    return distance.astype(np.float32, copy=False)


def _validate_alpha(alpha: FloatImage) -> None:
    if alpha.ndim != 2:
        raise ValueError("line_alpha_hr must be a 2D array.")
    if alpha.size == 0:
        raise ValueError("line_alpha_hr must not be empty.")
    if not np.issubdtype(alpha.dtype, np.floating):
        raise ValueError("line_alpha_hr must be a floating point array.")
    if not np.isfinite(alpha).all():
        raise ValueError("line_alpha_hr must not contain NaN or Inf.")
