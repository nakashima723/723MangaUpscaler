"""Straight-line stabilization for architectural line art."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import ndimage

from mlu.grayscale import FloatImage
from mlu.mask_extract import BoolImage
from mlu.scales import SUPPORTED_SCALES, SUPPORTED_SCALES_TEXT


@dataclass(frozen=True)
class LineSegment:
    """A fitted source-resolution line segment."""

    x0: float
    y0: float
    x1: float
    y1: float
    width_source_px: float
    coverage: float
    rms_error_source_px: float
    support_x: tuple[int, ...] = ()
    support_y: tuple[int, ...] = ()

    @property
    def length_source_px(self) -> float:
        return float(np.hypot(self.x1 - self.x0, self.y1 - self.y0))


@dataclass(frozen=True)
class LineStabilizationResult:
    """Result of straight-line alpha stabilization."""

    line_alpha_hr: FloatImage
    line_geometry_hr: FloatImage
    segments: tuple[LineSegment, ...]


def stabilize_line_alpha(
    line_alpha_hr: FloatImage,
    line_mask: BoolImage,
    line_soft: FloatImage | None,
    config: dict[str, Any],
) -> LineStabilizationResult:
    """Blend fitted straight segments into high-resolution line alpha."""

    stabilizer_config = config.get("line_stabilizer", {})
    if not bool(stabilizer_config.get("enabled", False)) or line_soft is None:
        return LineStabilizationResult(
            line_alpha_hr=line_alpha_hr,
            line_geometry_hr=np.zeros_like(line_alpha_hr, dtype=np.float32),
            segments=(),
        )

    _validate_alpha(line_alpha_hr)
    _validate_mask(line_mask)
    _validate_soft(line_soft, line_mask.shape)

    scale = int(config.get("pipeline", {}).get("scale", 4))
    if scale not in SUPPORTED_SCALES:
        raise ValueError(f"scale must be {SUPPORTED_SCALES_TEXT}.")

    segments = detect_straight_segments(line_mask, line_soft, config)
    if not segments:
        return LineStabilizationResult(
            line_alpha_hr=line_alpha_hr,
            line_geometry_hr=np.zeros_like(line_alpha_hr, dtype=np.float32),
            segments=(),
        )

    stabilized = line_alpha_hr.astype(np.float32, copy=True)
    geometry = np.zeros_like(stabilized, dtype=np.float32)
    strength = float(stabilizer_config.get("strength", 0.35))
    strength = float(np.clip(strength, 0.0, 1.0))
    aa_radius_hr_px = float(config.get("sdf", {}).get("aa_radius_hr_px", 0.75))
    if aa_radius_hr_px <= 0.0:
        raise ValueError("sdf.aa_radius_hr_px must be greater than 0.0.")
    for segment in segments:
        _blend_segment(
            stabilized,
            geometry,
            segment,
            scale=scale,
            strength=strength,
            aa_radius_hr_px=aa_radius_hr_px,
            width_scale=float(stabilizer_config.get("width_scale", 1.0)),
            band_margin_hr_px=float(stabilizer_config.get("band_margin_hr_px", 1.5)),
            support_dilate_hr_px=int(stabilizer_config.get("support_dilate_hr_px", 3)),
        )

    return LineStabilizationResult(
        line_alpha_hr=stabilized.astype(np.float32, copy=False),
        line_geometry_hr=geometry.astype(np.float32, copy=False),
        segments=segments,
    )


def detect_straight_segments(
    line_mask: BoolImage,
    line_soft: FloatImage,
    config: dict[str, Any],
) -> tuple[LineSegment, ...]:
    """Detect long, low-error straight segments from source-resolution line maps."""

    _validate_mask(line_mask)
    _validate_soft(line_soft, line_mask.shape)
    stabilizer_config = config.get("line_stabilizer", {})
    min_coverage = float(stabilizer_config.get("min_coverage", 0.35))
    support = line_mask & (line_soft >= np.float32(min_coverage))
    ys, xs = np.nonzero(support)
    if xs.size == 0:
        return ()

    weights = line_soft[ys, xs].astype(np.float32, copy=False)
    min_length = float(stabilizer_config.get("min_length_source_px", 32.0))
    max_rms = float(stabilizer_config.get("max_rms_error_source_px", 0.55))
    min_density = float(stabilizer_config.get("min_density", 0.35))
    max_gap = float(stabilizer_config.get("max_gap_source_px", 4.0))
    angle_step = float(stabilizer_config.get("angle_step_degrees", 5.0))
    rho_tolerance = float(stabilizer_config.get("rho_tolerance_source_px", 0.75))
    max_segments = int(stabilizer_config.get("max_segments", 96))
    candidate_limit = max(max_segments * 8, max_segments)
    max_candidates_per_angle = int(stabilizer_config.get("max_candidates_per_angle", 24))
    min_votes = max(4, int(round(min_length * min_density)))

    height, width = line_mask.shape
    rho_offset = int(np.ceil(np.hypot(width, height))) + 2
    accepted: list[LineSegment] = []

    angles = np.arange(0.0, 180.0, angle_step, dtype=np.float32)
    for angle_degrees in angles:
        theta = np.deg2rad(float(angle_degrees))
        cos_t = np.float32(np.cos(theta))
        sin_t = np.float32(np.sin(theta))
        rhos = xs.astype(np.float32) * cos_t + ys.astype(np.float32) * sin_t
        rho_bins = np.rint(rhos).astype(np.int32) + rho_offset
        counts = np.bincount(rho_bins, minlength=rho_offset * 2 + 5)
        candidates = _local_maxima(counts, min_votes=min_votes)
        if candidates.size == 0:
            continue
        candidate_counts = counts[candidates]
        order = np.argsort(candidate_counts)[::-1][:max_candidates_per_angle]

        direction_x = -sin_t
        direction_y = cos_t
        projections = xs.astype(np.float32) * direction_x + ys.astype(np.float32) * direction_y
        for candidate in candidates[order]:
            if len(accepted) >= candidate_limit:
                break
            rho_value = np.float32(candidate - rho_offset)
            member = np.abs(rhos - rho_value) <= np.float32(rho_tolerance)
            if int(np.count_nonzero(member)) < min_votes:
                continue
            _add_segments_from_hough_band(
                accepted,
                xs[member].astype(np.float32),
                ys[member].astype(np.float32),
                projections[member].astype(np.float32),
                weights[member].astype(np.float32),
                min_length=min_length,
                max_rms=max_rms,
                min_density=min_density,
                max_gap=max_gap,
                max_segments=candidate_limit,
                min_width_source_px=float(stabilizer_config.get("min_width_source_px", 0.85)),
                max_width_source_px=float(stabilizer_config.get("max_width_source_px", 2.25)),
            )

    accepted.sort(key=_segment_score, reverse=True)
    return tuple(accepted[:max_segments])


def _add_segments_from_hough_band(
    accepted: list[LineSegment],
    xs: FloatImage,
    ys: FloatImage,
    projections: FloatImage,
    weights: FloatImage,
    *,
    min_length: float,
    max_rms: float,
    min_density: float,
    max_gap: float,
    max_segments: int,
    min_width_source_px: float,
    max_width_source_px: float,
) -> None:
    order = np.argsort(projections)
    sorted_projection = projections[order]
    if sorted_projection.size == 0:
        return

    gaps = np.diff(sorted_projection)
    splits = np.where(gaps > np.float32(max_gap))[0] + 1
    starts = np.concatenate(([0], splits))
    ends = np.concatenate((splits, [sorted_projection.size]))
    for start, end in zip(starts, ends, strict=True):
        if len(accepted) >= max_segments:
            return
        if end - start < 4:
            continue
        group = order[start:end]
        length = float(sorted_projection[end - 1] - sorted_projection[start])
        if length < min_length:
            continue
        density = float(group.size) / max(length, 1.0)
        if density < min_density:
            continue
        segment = _fit_segment(
            xs[group],
            ys[group],
            weights[group],
            min_width_source_px=min_width_source_px,
            max_width_source_px=max_width_source_px,
        )
        if segment is None:
            continue
        if segment.length_source_px < min_length:
            continue
        if segment.rms_error_source_px > max_rms:
            continue
        if _is_duplicate(segment, accepted):
            continue
        accepted.append(segment)


def _fit_segment(
    xs: FloatImage,
    ys: FloatImage,
    weights: FloatImage,
    *,
    min_width_source_px: float,
    max_width_source_px: float,
) -> LineSegment | None:
    weight_sum = float(weights.sum())
    if weight_sum <= 0.0:
        return None

    x_mean = float(np.sum(xs * weights) / weight_sum)
    y_mean = float(np.sum(ys * weights) / weight_sum)
    centered_x = xs - np.float32(x_mean)
    centered_y = ys - np.float32(y_mean)
    cov_xx = float(np.sum(weights * centered_x * centered_x) / weight_sum)
    cov_xy = float(np.sum(weights * centered_x * centered_y) / weight_sum)
    cov_yy = float(np.sum(weights * centered_y * centered_y) / weight_sum)
    covariance = np.array([[cov_xx, cov_xy], [cov_xy, cov_yy]], dtype=np.float64)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    direction = eigenvectors[:, int(np.argmax(eigenvalues))]
    direction_x = float(direction[0])
    direction_y = float(direction[1])
    if direction_x < 0.0:
        direction_x = -direction_x
        direction_y = -direction_y

    projections = centered_x * np.float32(direction_x) + centered_y * np.float32(direction_y)
    orthogonal = -centered_x * np.float32(direction_y) + centered_y * np.float32(direction_x)
    rms = float(np.sqrt(np.sum(weights * orthogonal * orthogonal) / weight_sum))
    projection_min = float(projections.min())
    projection_max = float(projections.max())
    width = float(np.clip(0.75 + 2.0 * rms, min_width_source_px, max_width_source_px))
    coverage = float(np.clip(np.percentile(weights, 90), 0.0, 1.0))

    return LineSegment(
        x0=x_mean + direction_x * projection_min,
        y0=y_mean + direction_y * projection_min,
        x1=x_mean + direction_x * projection_max,
        y1=y_mean + direction_y * projection_max,
        width_source_px=width,
        coverage=coverage,
        rms_error_source_px=rms,
        support_x=tuple(np.rint(xs).astype(np.int32).tolist()),
        support_y=tuple(np.rint(ys).astype(np.int32).tolist()),
    )


def _blend_segment(
    alpha: FloatImage,
    geometry: FloatImage,
    segment: LineSegment,
    *,
    scale: int,
    strength: float,
    aa_radius_hr_px: float,
    width_scale: float,
    band_margin_hr_px: float,
    support_dilate_hr_px: int,
) -> None:
    height, width = alpha.shape
    x0 = (segment.x0 + 0.5) * scale
    y0 = (segment.y0 + 0.5) * scale
    x1 = (segment.x1 + 0.5) * scale
    y1 = (segment.y1 + 0.5) * scale
    dx = x1 - x0
    dy = y1 - y0
    length_sq = dx * dx + dy * dy
    if length_sq <= 0.0:
        return

    half_width = max(0.25, segment.width_source_px * width_scale * scale * 0.5)
    margin = half_width + aa_radius_hr_px + band_margin_hr_px
    xmin = max(0, int(np.floor(min(x0, x1) - margin)))
    xmax = min(width, int(np.ceil(max(x0, x1) + margin)) + 1)
    ymin = max(0, int(np.floor(min(y0, y1) - margin)))
    ymax = min(height, int(np.ceil(max(y0, y1) + margin)) + 1)
    if xmin >= xmax or ymin >= ymax:
        return

    yy, xx = np.mgrid[ymin:ymax, xmin:xmax].astype(np.float32)
    numerator = (xx - np.float32(x0)) * np.float32(dx)
    numerator += (yy - np.float32(y0)) * np.float32(dy)
    t = numerator / np.float32(length_sq)
    t = np.clip(t, 0.0, 1.0)
    nearest_x = np.float32(x0) + t * np.float32(dx)
    nearest_y = np.float32(y0) + t * np.float32(dy)
    distance = np.sqrt((xx - nearest_x) ** 2 + (yy - nearest_y) ** 2)
    geometric = _coverage_from_distance(
        distance,
        half_width=half_width,
        aa_radius=aa_radius_hr_px,
    ) * np.float32(segment.coverage)
    band = _coverage_from_distance(
        distance,
        half_width=half_width + band_margin_hr_px,
        aa_radius=aa_radius_hr_px,
    )
    gate = _segment_support_gate(
        segment,
        xmin=xmin,
        ymin=ymin,
        width=xmax - xmin,
        height=ymax - ymin,
        scale=scale,
        dilate_hr_px=support_dilate_hr_px,
    ).astype(np.float32, copy=False)
    geometric *= gate
    blend = np.clip(band * gate * np.float32(strength), 0.0, 1.0)
    region = alpha[ymin:ymax, xmin:xmax]
    strengthened = region * (np.float32(1.0) - blend) + geometric * blend
    alpha[ymin:ymax, xmin:xmax] = np.maximum(region, strengthened)
    geometry[ymin:ymax, xmin:xmax] = np.maximum(geometry[ymin:ymax, xmin:xmax], geometric)


def _segment_support_gate(
    segment: LineSegment,
    *,
    xmin: int,
    ymin: int,
    width: int,
    height: int,
    scale: int,
    dilate_hr_px: int,
) -> BoolImage:
    gate = np.zeros((height, width), dtype=np.bool_)
    for source_x, source_y in zip(segment.support_x, segment.support_y, strict=True):
        x0 = source_x * scale - xmin
        y0 = source_y * scale - ymin
        x1 = x0 + scale
        y1 = y0 + scale
        if x1 <= 0 or y1 <= 0 or x0 >= width or y0 >= height:
            continue
        gate[max(0, y0) : min(height, y1), max(0, x0) : min(width, x1)] = True
    if dilate_hr_px <= 0:
        return gate
    structure = np.ones((dilate_hr_px * 2 + 1, dilate_hr_px * 2 + 1), dtype=np.bool_)
    return ndimage.binary_dilation(gate, structure=structure).astype(np.bool_)


def _coverage_from_distance(
    distance: FloatImage,
    *,
    half_width: float,
    aa_radius: float,
) -> FloatImage:
    if aa_radius <= 0.0:
        return (distance <= np.float32(half_width)).astype(np.float32)
    t = np.clip(
        (np.float32(half_width + aa_radius) - distance) / np.float32(2.0 * aa_radius),
        0.0,
        1.0,
    )
    return (t * t * (np.float32(3.0) - np.float32(2.0) * t)).astype(np.float32, copy=False)


def _local_maxima(counts: np.ndarray, *, min_votes: int) -> np.ndarray:
    if counts.size < 3:
        return np.array([], dtype=np.int64)
    middle = counts[1:-1]
    mask = (middle >= min_votes) & (middle >= counts[:-2]) & (middle >= counts[2:])
    return np.nonzero(mask)[0].astype(np.int64) + 1


def _is_duplicate(segment: LineSegment, accepted: list[LineSegment]) -> bool:
    sx = segment.x1 - segment.x0
    sy = segment.y1 - segment.y0
    sl = max(float(np.hypot(sx, sy)), 1.0)
    scx = (segment.x0 + segment.x1) * 0.5
    scy = (segment.y0 + segment.y1) * 0.5
    for other in accepted:
        ox = other.x1 - other.x0
        oy = other.y1 - other.y0
        ol = max(float(np.hypot(ox, oy)), 1.0)
        dot = abs((sx * ox + sy * oy) / (sl * ol))
        if dot < 0.996:
            continue
        ocx = (other.x0 + other.x1) * 0.5
        ocy = (other.y0 + other.y1) * 0.5
        center_distance = float(np.hypot(scx - ocx, scy - ocy))
        if center_distance < 3.0:
            return True
    return False


def _segment_score(segment: LineSegment) -> float:
    return segment.length_source_px * segment.coverage / (1.0 + segment.rms_error_source_px)


def _validate_alpha(image: FloatImage) -> None:
    if image.ndim != 2:
        raise ValueError("line_alpha_hr must be a 2D array.")
    if not np.issubdtype(image.dtype, np.floating):
        raise ValueError("line_alpha_hr must be a floating point array.")
    if not np.isfinite(image).all():
        raise ValueError("line_alpha_hr must not contain NaN or Inf.")


def _validate_mask(mask: BoolImage) -> None:
    if mask.ndim != 2:
        raise ValueError("line_mask must be a 2D array.")
    if mask.dtype != np.bool_:
        raise ValueError("line_mask must be a boolean array.")


def _validate_soft(image: FloatImage, shape: tuple[int, int]) -> None:
    if image.shape != shape:
        raise ValueError(f"line_soft shape must be {shape}.")
    if image.ndim != 2:
        raise ValueError("line_soft must be a 2D array.")
    if not np.issubdtype(image.dtype, np.floating):
        raise ValueError("line_soft must be a floating point array.")
    if not np.isfinite(image).all():
        raise ValueError("line_soft must not contain NaN or Inf.")
