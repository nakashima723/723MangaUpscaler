"""Signed-distance-field line rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import diplib as dip
import numpy as np
from PIL import Image

from mlu.grayscale import FloatImage
from mlu.mask_extract import BoolImage
from mlu.scales import SUPPORTED_SCALES, SUPPORTED_SCALES_TEXT


@dataclass(frozen=True)
class SDFRenderResult:
    """SDF rendering output maps.

    When diagnostics are retained, `sdf` is source-resolution distance in
    source pixels and `sdf_hr` is high-resolution distance in high-resolution
    pixels. Normal output may omit those diagnostic-only maps when an exact
    alpha fast path is available. `line_alpha_hr` is always float32 [0.0, 1.0],
    where 1.0 means fully covered by black line ink.
    """

    sdf: FloatImage | None
    sdf_hr: FloatImage | None
    line_alpha_hr: FloatImage
    line_soft_hr: FloatImage | None = None
    soft_mask_hr: FloatImage | None = None
    sdf_alpha_before_soft_mode_hr: FloatImage | None = None
    line_geometry_hr: FloatImage | None = None
    sdf_reference_line_alpha_hr: FloatImage | None = None
    directional_smoothing_source_alpha_hr: FloatImage | None = None
    directional_smoothing_weight_hr: FloatImage | None = None
    directional_smoothing_delta_hr: FloatImage | None = None
    directional_smoothing_stats: dict[str, Any] | None = None
    centerline_source: FloatImage | None = None
    centerline_eligible_source: FloatImage | None = None
    centerline_rolled_back_component_source: FloatImage | None = None
    filtered_centerline_source: FloatImage | None = None
    centerline_filter_displacement_source: FloatImage | None = None
    centerline_protected_source: FloatImage | None = None
    centerline_simplification_delta_hr: FloatImage | None = None
    centerline_simplification_stats: dict[str, Any] | None = None
    line_segments: tuple[Any, ...] = ()
    renderer: str = "sdf"
    svg_text: str | None = None
    renderer_metadata: dict[str, Any] | None = None
    sdf_diagnostic_stats: dict[str, float] | None = None


def signed_distance_field(line_mask: BoolImage) -> FloatImage:
    """Create source-resolution SDF with positive values inside line pixels."""

    _validate_mask(line_mask)
    if not line_mask.any():
        return -np.ones(line_mask.shape, dtype=np.float32)
    if line_mask.all():
        return np.ones(line_mask.shape, dtype=np.float32)

    inside = _euclidean_distance_transform(line_mask)
    outside = _euclidean_distance_transform(~line_mask)
    # Reuse the first float32 buffer instead of allocating a third full-size
    # temporary for the subtraction. The values are identical to inside - outside.
    np.subtract(inside, outside, out=inside)
    return inside.astype(np.float32, copy=False)


def render_line_alpha(
    line_mask: BoolImage,
    config: dict[str, Any],
    *,
    line_soft: FloatImage | None = None,
    retain_diagnostics: bool = True,
    collect_metadata: bool = True,
) -> SDFRenderResult:
    """Render high-resolution line alpha from source line maps.

    Set ``retain_diagnostics`` to false for normal final-only output. The alpha
    renderer then calculates only the inside/outside distances that can reach
    the smoothstep transition. Under the usual saturation conditions it skips
    both transforms while the resulting alpha remains bit-for-bit identical.
    """

    scale = int(config.get("pipeline", {}).get("scale", 4))
    if scale not in SUPPORTED_SCALES:
        raise ValueError(f"scale must be {SUPPORTED_SCALES_TEXT}.")

    sdf_config = config.get("sdf", {})
    interpolation = str(sdf_config.get("interpolation", "lanczos"))
    distance_source = str(sdf_config.get("distance_source", "binary_mask"))
    soft_sdf_threshold = float(sdf_config.get("soft_sdf_threshold", 0.30))
    width_bias_source_px = float(sdf_config.get("width_bias_source_px", 0.0))
    aa_radius_hr_px = float(sdf_config.get("aa_radius_hr_px", 0.75))
    if aa_radius_hr_px <= 0.0:
        raise ValueError("aa_radius_hr_px must be greater than 0.")

    sdf: FloatImage | None = None
    sdf_hr: FloatImage | None = None
    line_soft_hr: FloatImage | None = None
    soft_mask_hr_debug: FloatImage | None = None
    alpha: FloatImage | None = None
    alpha_fast_path = False
    high_resolution_edt_count = 0
    if distance_source == "binary_mask":
        sdf = signed_distance_field(line_mask)
        sdf_hr = resize_float_image(
            sdf,
            scale=scale,
            interpolation=interpolation,
        ) * np.float32(scale)
    elif distance_source == "soft_mask_hr":
        if line_soft is None:
            raise ValueError("line_soft is required when sdf.distance_source is 'soft_mask_hr'.")
        if not 0.0 <= soft_sdf_threshold <= 1.0:
            raise ValueError("soft_sdf_threshold must be between 0.0 and 1.0.")
        _validate_float_image(line_soft, shape=line_mask.shape)
        line_soft_hr = _resize_line_soft(line_soft, scale=scale, interpolation=interpolation)
        soft_mask_hr = line_soft_hr >= np.float32(soft_sdf_threshold)
        if not retain_diagnostics:
            alpha, high_resolution_edt_count = _render_alpha_without_retained_sdf(
                soft_mask_hr,
                width_bias_hr_px=np.float32(width_bias_source_px * scale),
                aa_radius_hr_px=np.float32(aa_radius_hr_px),
            )
            alpha_fast_path = _is_binary_alpha_fast_path(
                scale=scale,
                soft_alpha_mode=str(sdf_config.get("soft_alpha_mode", "none")),
                width_bias_source_px=width_bias_source_px,
                aa_radius_hr_px=aa_radius_hr_px,
            )
        else:
            sdf_hr = signed_distance_field(soft_mask_hr)
            high_resolution_edt_count = 2
        if retain_diagnostics:
            sdf = signed_distance_field(line_mask)
            soft_mask_hr_debug = soft_mask_hr.astype(np.float32)
    else:
        raise ValueError(f"Unsupported sdf.distance_source: {distance_source}")

    if alpha is None:
        if sdf_hr is None:
            raise RuntimeError("SDF rendering did not produce a high-resolution distance map.")
        sdf_adjusted = sdf_hr + np.float32(width_bias_source_px * scale)
        alpha = smoothstep(-aa_radius_hr_px, aa_radius_hr_px, sdf_adjusted)
    alpha_before_soft_mode = (
        alpha.astype(np.float32, copy=True) if retain_diagnostics else None
    )

    soft_mode = str(sdf_config.get("soft_alpha_mode", "none"))
    soft_gain = float(sdf_config.get("soft_gain", 0.0))
    if soft_mode in {"max", "blend"} and soft_gain > 0.0:
        if line_soft is None:
            raise ValueError(f"line_soft is required when soft_alpha_mode is {soft_mode!r}.")
        _validate_float_image(line_soft, shape=line_mask.shape)
        if line_soft_hr is None:
            line_soft_hr = _resize_line_soft(line_soft, scale=scale, interpolation=interpolation)
        soft_alpha = np.clip(line_soft_hr, 0.0, 1.0).astype(np.float32, copy=False)
        if soft_mode == "max":
            alpha = np.maximum(alpha, np.clip(soft_alpha * np.float32(soft_gain), 0.0, 1.0))
        else:
            gain = np.float32(np.clip(soft_gain, 0.0, 1.0))
            alpha = alpha * (np.float32(1.0) - gain) + soft_alpha * gain
    elif soft_mode != "none":
        raise ValueError(f"Unsupported soft_alpha_mode: {soft_mode}")

    diagnostic_stats: dict[str, float] | None = None
    if collect_metadata and line_soft_hr is not None:
        diagnostic_stats = {
            "line_soft_hr_min": float(line_soft_hr.min()),
            "line_soft_hr_max": float(line_soft_hr.max()),
            "line_soft_hr_mean": float(line_soft_hr.mean()),
        }
        if distance_source == "soft_mask_hr":
            diagnostic_stats["soft_mask_hr_area_ratio"] = float(
                np.mean(
                    line_soft_hr >= np.float32(soft_sdf_threshold),
                    dtype=np.float32,
                )
            )

    return SDFRenderResult(
        sdf=sdf if retain_diagnostics else None,
        sdf_hr=(
            sdf_hr.astype(np.float32, copy=False)
            if retain_diagnostics and sdf_hr is not None
            else None
        ),
        line_alpha_hr=alpha.astype(np.float32, copy=False),
        line_soft_hr=line_soft_hr if retain_diagnostics else None,
        soft_mask_hr=soft_mask_hr_debug if retain_diagnostics else None,
        sdf_alpha_before_soft_mode_hr=alpha_before_soft_mode,
        line_geometry_hr=None,
        line_segments=(),
        renderer_metadata={
            "renderer": "sdf",
            "alpha_fast_path": alpha_fast_path,
            "high_resolution_edt_count": high_resolution_edt_count,
            "diagnostics_retained": retain_diagnostics,
        },
        sdf_diagnostic_stats=diagnostic_stats,
    )


def _render_alpha_without_retained_sdf(
    mask: BoolImage,
    *,
    width_bias_hr_px: np.float32,
    aa_radius_hr_px: np.float32,
) -> tuple[FloatImage, int]:
    """Render exact SDF alpha while retaining no high-resolution distance map.

    A non-empty pixel in an exact EDT has distance at least +1 and an empty
    pixel at most -1. A side that is already beyond the smoothstep transition
    at that minimum distance needs no EDT. If a side does need distances, it is
    calculated independently and released before the other side is considered.
    """

    if not mask.any():
        value = smoothstep(
            -float(aa_radius_hr_px),
            float(aa_radius_hr_px),
            np.array([[-np.float32(1.0) + width_bias_hr_px]], dtype=np.float32),
        )[0, 0]
        return np.full(mask.shape, value, dtype=np.float32), 0
    if mask.all():
        value = smoothstep(
            -float(aa_radius_hr_px),
            float(aa_radius_hr_px),
            np.array([[np.float32(1.0) + width_bias_hr_px]], dtype=np.float32),
        )[0, 0]
        return np.full(mask.shape, value, dtype=np.float32), 0

    alpha = np.empty(mask.shape, dtype=np.float32)
    edt_count = 0
    inside_needs_distance = (
        np.float32(1.0) + width_bias_hr_px < aa_radius_hr_px
    )
    outside_needs_distance = (
        -np.float32(1.0) + width_bias_hr_px > -aa_radius_hr_px
    )

    if inside_needs_distance:
        inside = _euclidean_distance_transform(mask)
        inside_alpha = smoothstep(
            -float(aa_radius_hr_px),
            float(aa_radius_hr_px),
            inside + width_bias_hr_px,
        )
        alpha[mask] = inside_alpha[mask]
        edt_count += 1
        del inside, inside_alpha
    else:
        alpha[mask] = np.float32(1.0)

    if outside_needs_distance:
        outside = _euclidean_distance_transform(~mask)
        outside_alpha = smoothstep(
            -float(aa_radius_hr_px),
            float(aa_radius_hr_px),
            -outside + width_bias_hr_px,
        )
        alpha[~mask] = outside_alpha[~mask]
        edt_count += 1
    else:
        alpha[~mask] = np.float32(0.0)
    return alpha, edt_count


def _is_binary_alpha_fast_path(
    *,
    scale: int,
    soft_alpha_mode: str,
    width_bias_source_px: float,
    aa_radius_hr_px: float,
) -> bool:
    """Return whether the final SDF alpha is exactly a binary soft-mask copy."""

    if soft_alpha_mode != "none":
        return False
    aa_radius = np.float32(aa_radius_hr_px)
    bias_hr = np.float32(width_bias_source_px * scale)
    return bool(
        np.float32(1.0) + bias_hr >= aa_radius
        and -np.float32(1.0) + bias_hr <= -aa_radius
    )


def _euclidean_distance_transform(mask: BoolImage) -> FloatImage:
    """Return DIPlib's separable exact EDT with SciPy-compatible borders."""

    distance = dip.EuclideanDistanceTransform(mask, "object", "separable")
    return np.asarray(distance, dtype=np.float32)


def _resize_line_soft(
    line_soft: FloatImage,
    *,
    scale: int,
    interpolation: str,
) -> FloatImage:
    resized = resize_float_image(line_soft, scale=scale, interpolation=interpolation)
    return np.clip(resized, 0.0, 1.0).astype(np.float32, copy=False)


def resize_float_image(
    image: FloatImage,
    *,
    scale: int,
    interpolation: str = "lanczos",
) -> FloatImage:
    """Resize a 2D float32 image by an integer scale."""

    _validate_float_image(image)
    if scale not in SUPPORTED_SCALES:
        raise ValueError(f"scale must be {SUPPORTED_SCALES_TEXT}.")

    height, width = image.shape
    target_size = (width * scale, height * scale)
    resampling = _resampling_filter(interpolation)
    resized = Image.fromarray(image.astype(np.float32, copy=False)).resize(target_size, resampling)
    array = np.asarray(resized, dtype=np.float32)
    if not np.isfinite(array).all():
        raise ValueError("resized image contains NaN or Inf.")
    return array


def smoothstep(edge0: float, edge1: float, x: FloatImage) -> FloatImage:
    """Apply smoothstep interpolation to a float32 array."""

    if edge1 <= edge0:
        raise ValueError("edge1 must be greater than edge0.")
    t = np.clip((x - np.float32(edge0)) / np.float32(edge1 - edge0), 0.0, 1.0)
    return (t * t * (np.float32(3.0) - np.float32(2.0) * t)).astype(np.float32, copy=False)


def sdf_preview(sdf_hr: FloatImage, *, radius_px: float = 8.0) -> FloatImage:
    """Convert high-resolution SDF to a preview image in [0.0, 1.0]."""

    _validate_float_image(sdf_hr)
    if radius_px <= 0.0:
        raise ValueError("radius_px must be greater than 0.")
    normalized = np.clip(sdf_hr / np.float32(radius_px), -1.0, 1.0)
    return (normalized * np.float32(0.5) + np.float32(0.5)).astype(np.float32, copy=False)


def _validate_mask(line_mask: BoolImage) -> None:
    if line_mask.ndim != 2:
        raise ValueError("line_mask must be a 2D array.")
    if line_mask.size == 0:
        raise ValueError("line_mask must not be empty.")
    if line_mask.dtype != np.bool_:
        raise ValueError("line_mask must be a boolean array.")


def _validate_float_image(image: FloatImage, *, shape: tuple[int, int] | None = None) -> None:
    if image.ndim != 2:
        raise ValueError("image must be a 2D array.")
    if image.size == 0:
        raise ValueError("image must not be empty.")
    if not np.issubdtype(image.dtype, np.floating):
        raise ValueError("image must be a floating point array.")
    if shape is not None and image.shape != shape:
        raise ValueError(f"image shape must be {shape}.")
    if not np.isfinite(image).all():
        raise ValueError("image must not contain NaN or Inf.")


def _resampling_filter(interpolation: str) -> Image.Resampling:
    normalized = interpolation.lower()
    if normalized == "nearest":
        return Image.Resampling.NEAREST
    if normalized in {"bilinear", "linear"}:
        return Image.Resampling.BILINEAR
    if normalized in {"bicubic", "cubic"}:
        return Image.Resampling.BICUBIC
    if normalized == "lanczos":
        return Image.Resampling.LANCZOS
    raise ValueError(f"Unsupported interpolation: {interpolation}")
