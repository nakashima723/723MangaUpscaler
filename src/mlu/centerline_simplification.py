"""Experimental simplification for long, structurally simple strokes."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

from mlu.grayscale import FloatImage

Point = tuple[int, int]


@dataclass(frozen=True)
class CenterlineSimplificationResult:
    """Output and diagnostics from centerline simplification."""

    line_alpha_hr: FloatImage
    centerline_source: FloatImage | None
    eligible_centerline_source: FloatImage | None
    rolled_back_component_source: FloatImage | None
    filtered_centerline_source: FloatImage | None
    filter_displacement_source: FloatImage | None
    protected_source: FloatImage | None
    delta_hr: FloatImage | None
    stats: dict[str, Any]


def simplify_centerline_alpha(
    line_alpha_hr: FloatImage,
    config: dict[str, Any],
    *,
    renderer: str,
) -> CenterlineSimplificationResult:
    """Simplify long centerline paths without adding ink outside the source alpha."""

    settings = config.get("centerline_simplification", {})
    enabled = bool(settings.get("enabled", False))
    filter_sigma = float(settings.get("filter_sigma_source_px", 0.0))
    filter_sample_step = float(settings.get("filter_sample_step_source_px", 0.50))
    max_filter_displacement = float(
        settings.get("max_filter_displacement_source_px", 0.75)
    )
    strength = float(settings.get("strength", 1.0))
    support_margin_source_px = float(settings.get("support_margin_source_px", 0.75))
    binarize_output = bool(settings.get("binarize_output", True))
    binary_threshold = float(settings.get("binary_threshold", 0.50))
    max_new_component_area = int(settings.get("max_new_component_area", 2))
    corner_angle_degrees = float(settings.get("corner_angle_degrees", 45.0))
    corner_window_source_px = float(settings.get("corner_window_source_px", 3.0))
    geometry_strength = float(settings.get("geometry_strength", 1.0))
    gate = settings.get("long_stroke_gate", {})
    gate_enabled = bool(gate.get("enabled", True))
    min_chord_arc_ratio = float(gate.get("min_chord_arc_ratio", 0.985))
    max_line_fit_rms = float(gate.get("max_line_fit_rms_source_px", 0.35))
    max_line_fit_deviation = float(
        gate.get("max_line_fit_deviation_source_px", 1.0)
    )
    max_width_cv = float(gate.get("max_width_cv", 0.20))
    max_width_ratio = float(gate.get("max_width_ratio", 1.50))
    skip_paths_with_corners = bool(gate.get("skip_paths_with_corners", True))
    rollback = settings.get("component_rollback", {})
    rollback_enabled = bool(rollback.get("enabled", True))
    preserve_component_count = bool(rollback.get("preserve_component_count", True))
    min_ink_ratio = float(rollback.get("min_ink_ratio", 0.80))
    max_ink_ratio = float(rollback.get("max_ink_ratio", 1.20))
    base_stats: dict[str, Any] = {
        "enabled": enabled,
        "applied": False,
        "filter_method": "gaussian_arc_length_normal_v1",
        "filter_sigma_source_px": filter_sigma,
        "filter_sample_step_source_px": filter_sample_step,
        "max_filter_displacement_source_px": max_filter_displacement,
        "strength": strength,
        "support_margin_source_px": support_margin_source_px,
        "binarize_output": binarize_output,
        "binary_threshold": binary_threshold,
        "max_new_component_area": max_new_component_area,
        "corner_angle_degrees": corner_angle_degrees,
        "corner_window_source_px": corner_window_source_px,
        "geometry_strength": geometry_strength,
        "long_stroke_gate": {
            "enabled": gate_enabled,
            "min_chord_arc_ratio": min_chord_arc_ratio,
            "max_line_fit_rms_source_px": max_line_fit_rms,
            "max_line_fit_deviation_source_px": max_line_fit_deviation,
            "max_width_cv": max_width_cv,
            "max_width_ratio": max_width_ratio,
            "skip_paths_with_corners": skip_paths_with_corners,
        },
        "component_rollback": {
            "enabled": rollback_enabled,
            "preserve_component_count": preserve_component_count,
            "min_ink_ratio": min_ink_ratio,
            "max_ink_ratio": max_ink_ratio,
        },
        "renderer": renderer,
    }
    if (
        not enabled
        or filter_sigma <= 0.0
        or geometry_strength <= 0.0
        or renderer != "sdf"
    ):
        reason = "disabled"
        if enabled and filter_sigma <= 0.0:
            reason = "zero_filter_sigma"
        elif enabled and geometry_strength <= 0.0:
            reason = "zero_geometry_strength"
        elif enabled and renderer != "sdf":
            reason = "unsupported_renderer"
        return CenterlineSimplificationResult(
            line_alpha_hr=line_alpha_hr,
            centerline_source=None,
            eligible_centerline_source=None,
            rolled_back_component_source=None,
            filtered_centerline_source=None,
            filter_displacement_source=None,
            protected_source=None,
            delta_hr=None,
            stats={**base_stats, "skip_reason": reason},
        )

    _validate_alpha(line_alpha_hr)
    scale = int(config.get("pipeline", {}).get("scale", 4))
    if line_alpha_hr.shape[0] % scale or line_alpha_hr.shape[1] % scale:
        raise ValueError("line_alpha_hr dimensions must be divisible by pipeline.scale.")

    alpha_threshold = float(settings.get("alpha_threshold", 0.50))
    min_path_length = float(settings.get("min_path_length_source_px", 64.0))
    endpoint_protection = float(settings.get("endpoint_protection_source_px", 3.0))
    max_radius = float(settings.get("max_radius_source_px", 2.25))
    max_thinning_iterations = int(settings.get("max_thinning_iterations", 128))
    source_alpha = _block_mean(line_alpha_hr, scale)
    support = source_alpha >= np.float32(alpha_threshold)
    if not support.any():
        return CenterlineSimplificationResult(
            line_alpha_hr=line_alpha_hr,
            centerline_source=np.zeros_like(source_alpha),
            eligible_centerline_source=np.zeros_like(source_alpha),
            rolled_back_component_source=np.zeros_like(source_alpha),
            filtered_centerline_source=np.zeros_like(source_alpha),
            filter_displacement_source=np.zeros_like(source_alpha),
            protected_source=np.zeros_like(source_alpha),
            delta_hr=np.zeros_like(line_alpha_hr),
            stats={**base_stats, "skip_reason": "empty_support"},
        )

    centerline, thinning_iterations = thin_zhang_suen(
        support,
        max_iterations=max_thinning_iterations,
    )
    paths, closed_path_count, degree = trace_centerline_paths(centerline)
    radius_source = ndimage.distance_transform_edt(support).astype(np.float32, copy=False)
    component_labels, _ = ndimage.label(support, structure=np.ones((3, 3), dtype=np.uint8))

    filtered_map = centerline.copy()
    filter_displacement_map = np.zeros_like(source_alpha, dtype=np.float32)
    eligible_map = np.zeros_like(centerline)
    protected = centerline & (degree != 2)
    affected_centerline = np.zeros_like(centerline)
    affected_radius = np.zeros_like(source_alpha, dtype=np.float32)
    affected_component = np.zeros_like(component_labels, dtype=np.int32)
    render_paths: list[tuple[np.ndarray, np.ndarray]] = []
    filtered_path_count = 0
    displacement_sum = 0.0
    displacement_count = 0
    max_path_displacement = 0.0
    noise_energy_before = 0.0
    noise_energy_after = 0.0
    resampled_sample_count = 0
    filter_clamped_point_count = 0
    displacement_samples: list[np.ndarray] = []
    skipped_short_count = 0
    skipped_wide_count = 0
    protected_corner_count = 0
    eligible_path_count = 0
    rejected_path_counts = {
        "closed": 0,
        "too_short": 0,
        "too_wide": 0,
        "has_corner": 0,
        "low_chord_arc_ratio": 0,
        "line_fit_rms": 0,
        "line_fit_deviation": 0,
        "width_variation": 0,
    }

    for path, is_closed in paths:
        if is_closed:
            rejected_path_counts["closed"] += 1
            _mark_points(protected, path)
            continue
        path_array = np.asarray(path, dtype=np.int32)
        cumulative = _cumulative_lengths(path_array)
        path_length = float(cumulative[-1]) if cumulative.size else 0.0
        radii = radius_source[path_array[:, 0], path_array[:, 1]]
        if path_length < min_path_length or len(path) < 4:
            skipped_short_count += 1
            rejected_path_counts["too_short"] += 1
            _mark_points(protected, path)
            continue
        if float(np.median(radii)) > max_radius:
            skipped_wide_count += 1
            rejected_path_counts["too_wide"] += 1
            _mark_points(protected, path)
            continue

        gate_rejection, _ = _long_stroke_rejection_reason(
            path_array,
            cumulative,
            radii,
            gate_enabled=gate_enabled,
            min_chord_arc_ratio=min_chord_arc_ratio,
            max_line_fit_rms_source_px=max_line_fit_rms,
            max_line_fit_deviation_source_px=max_line_fit_deviation,
            max_width_cv=max_width_cv,
            max_width_ratio=max_width_ratio,
            skip_paths_with_corners=skip_paths_with_corners,
            corner_angle_degrees=corner_angle_degrees,
            corner_window_source_px=corner_window_source_px,
        )
        if gate_rejection is not None:
            rejected_path_counts[gate_rejection] += 1
            _mark_points(protected, path)
            continue
        eligible_path_count += 1
        _mark_points(eligible_map, path)

        render_path, corner_indices, filter_stats = _filter_high_frequency_path(
            path_array,
            cumulative,
            sigma_source_px=filter_sigma,
            sample_step_source_px=filter_sample_step,
            strength=geometry_strength,
            max_displacement_source_px=max_filter_displacement,
            protection=endpoint_protection,
            corner_angle_degrees=corner_angle_degrees,
            corner_window_source_px=corner_window_source_px,
        )
        protected_corner_count += len(corner_indices)
        for index in corner_indices:
            y, x = path[index]
            protected[y, x] = True
        movement = np.linalg.norm(render_path - path_array.astype(np.float32), axis=1)
        moved_indices = np.flatnonzero(movement > np.float32(1.0e-4))
        if moved_indices.size == 0:
            continue

        filtered_path_count += 1
        displacement_sum += float(movement.sum())
        displacement_count += len(movement)
        displacement_samples.append(movement.astype(np.float32, copy=False))
        max_path_displacement = max(max_path_displacement, float(movement.max()))
        noise_energy_before += float(filter_stats["noise_energy_before"])
        noise_energy_after += float(filter_stats["noise_energy_after"])
        resampled_sample_count += int(filter_stats["resampled_sample_count"])
        filter_clamped_point_count += int(filter_stats["clamped_point_count"])
        render_widths_hr = _estimate_widths_hr(
            line_alpha_hr,
            path_array,
            list(range(len(path_array))),
            scale=scale,
            max_radius_source_px=max_radius,
        )
        render_widths_hr = _filter_path_widths(
            render_widths_hr,
            cumulative,
            sigma_source_px=filter_sigma,
            sample_step_source_px=filter_sample_step,
            strength=geometry_strength,
            protection=endpoint_protection,
        )
        render_paths.append((render_path, render_widths_hr))

        _mark_points(filtered_map, path, value=False)
        _draw_float_polyline_on_bool(filtered_map, render_path)
        for (y, x), value in zip(path_array, movement, strict=True):
            filter_displacement_map[y, x] = max(
                filter_displacement_map[y, x],
                np.float32(value),
            )

        changed_start = max(0, int(moved_indices[0]) - 1)
        changed_end = min(len(path), int(moved_indices[-1]) + 2)
        changed_slice = path_array[changed_start:changed_end]

        midpoint = path_array[len(path_array) // 2]
        component_id = int(component_labels[midpoint[0], midpoint[1]])
        for y, x in changed_slice:
            affected_centerline[y, x] = True
            affected_radius[y, x] = max(affected_radius[y, x], radius_source[y, x])
            affected_component[y, x] = component_id

        _mark_protected_path_ends(
            protected,
            path_array,
            cumulative,
            protection=endpoint_protection,
        )

    if not render_paths or not affected_centerline.any():
        return CenterlineSimplificationResult(
            line_alpha_hr=line_alpha_hr,
            centerline_source=centerline.astype(np.float32),
            eligible_centerline_source=eligible_map.astype(np.float32),
            rolled_back_component_source=np.zeros_like(source_alpha),
            filtered_centerline_source=filtered_map.astype(np.float32),
            filter_displacement_source=filter_displacement_map,
            protected_source=protected.astype(np.float32),
            delta_hr=np.zeros_like(line_alpha_hr),
            stats={
                **base_stats,
                "skip_reason": (
                    "no_eligible_paths"
                    if eligible_path_count == 0
                    else "no_filterable_paths"
                ),
                "thinning_iterations": thinning_iterations,
                "path_count": len(paths),
                "closed_path_count": closed_path_count,
                "skipped_short_path_count": skipped_short_count,
                "skipped_wide_path_count": skipped_wide_count,
                "eligible_path_count": eligible_path_count,
                "rejected_path_counts": rejected_path_counts,
            },
        )

    affected_source = _build_affected_mask(
        support,
        component_labels,
        affected_centerline,
        affected_radius,
        affected_component,
        displacement_margin=max_filter_displacement,
    )
    affected_source &= ~_dilate_protected(protected, endpoint_protection)
    reconstructed_hr = _render_paths(
        line_alpha_hr.shape,
        render_paths,
        scale=scale,
    )
    affected_hr = _resize_bool_nearest(affected_source, line_alpha_hr.shape)
    source_support_hr = _resize_bool_nearest(support, line_alpha_hr.shape)
    protected_hr = _resize_bool_nearest(
        _dilate_protected(protected, endpoint_protection),
        line_alpha_hr.shape,
    )
    margin_hr = max(1, int(ceil(support_margin_source_px * scale)))
    local_margin_hr = _dilate_bool_pillow(affected_hr, radius=margin_hr)
    replacement_region_hr = affected_hr | (local_margin_hr & ~source_support_hr)
    replacement_region_hr &= ~protected_hr
    local_alpha_cap = _maximum_filter_alpha_pillow(line_alpha_hr, radius=margin_hr)
    reconstructed_hr = np.minimum(reconstructed_hr, local_alpha_cap)

    simplified_alpha = line_alpha_hr.astype(np.float32, copy=True)
    effective_alpha_strength = 1.0 if binarize_output else strength
    blend = np.float32(effective_alpha_strength)
    simplified_alpha[replacement_region_hr] = (
        simplified_alpha[replacement_region_hr] * (np.float32(1.0) - blend)
        + reconstructed_hr[replacement_region_hr] * blend
    )
    fractional_before_binarization = (
        (simplified_alpha > np.float32(0.0))
        & (simplified_alpha < np.float32(1.0))
    )
    if binarize_output:
        simplified_alpha = (simplified_alpha >= np.float32(binary_threshold)).astype(
            np.float32
        )
    if binarize_output:
        removed_new_pixel_count = _remove_new_small_components(
            simplified_alpha,
            line_alpha_hr >= np.float32(binary_threshold),
            max_area=max_new_component_area,
        )
    else:
        removed_new_pixel_count = 0
    simplified_alpha, rolled_back_source, rollback_stats = _rollback_unsafe_components(
        simplified_alpha,
        line_alpha_hr,
        affected_source,
        component_labels,
        replacement_region_hr,
        scale=scale,
        binary_threshold=binary_threshold,
        binary_output=binarize_output,
        enabled=rollback_enabled,
        preserve_component_count=preserve_component_count,
        min_ink_ratio=min_ink_ratio,
        max_ink_ratio=max_ink_ratio,
    )
    delta = np.abs(simplified_alpha - line_alpha_hr).astype(np.float32, copy=False)
    changed = delta > np.float32(1.0 / 255.0)
    all_displacements = (
        np.concatenate(displacement_samples)
        if displacement_samples
        else np.zeros(1, dtype=np.float32)
    )

    return CenterlineSimplificationResult(
        line_alpha_hr=simplified_alpha,
        centerline_source=centerline.astype(np.float32),
        eligible_centerline_source=eligible_map.astype(np.float32),
        rolled_back_component_source=rolled_back_source.astype(np.float32),
        filtered_centerline_source=filtered_map.astype(np.float32),
        filter_displacement_source=filter_displacement_map,
        protected_source=protected.astype(np.float32),
        delta_hr=delta,
        stats={
            **base_stats,
            "applied": bool(changed.any()),
            "thinning_iterations": thinning_iterations,
            "path_count": len(paths),
            "closed_path_count": closed_path_count,
            "filtered_path_count": filtered_path_count,
            "skipped_short_path_count": skipped_short_count,
            "skipped_wide_path_count": skipped_wide_count,
            "eligible_path_count": eligible_path_count,
            "rejected_path_counts": rejected_path_counts,
            "protected_corner_count": protected_corner_count,
            "mean_path_displacement_source_px": (
                displacement_sum / displacement_count if displacement_count else 0.0
            ),
            "max_path_displacement_source_px": max_path_displacement,
            "p95_path_displacement_source_px": float(
                np.percentile(all_displacements, 95.0)
            ),
            "resampled_sample_count": resampled_sample_count,
            "filter_clamped_point_count": filter_clamped_point_count,
            "filter_clamped_point_ratio": (
                filter_clamped_point_count / displacement_count
                if displacement_count
                else 0.0
            ),
            "high_frequency_energy_reduction_ratio": (
                1.0 - noise_energy_after / noise_energy_before
                if noise_energy_before > 0.0
                else 0.0
            ),
            "affected_source_ratio": float(affected_source.mean()),
            "changed_pixel_ratio": float(changed.mean()),
            "max_alpha_delta": float(delta.max(initial=0.0)),
            "fractional_pixel_ratio_before_binarization": float(
                fractional_before_binarization.mean()
            ),
            "fractional_pixel_ratio_after_binarization": float(
                (
                    (simplified_alpha > np.float32(0.0))
                    & (simplified_alpha < np.float32(1.0))
                ).mean()
            ),
            "removed_new_small_component_pixel_count": removed_new_pixel_count,
            "component_rollback": rollback_stats,
            "effective_alpha_strength": effective_alpha_strength,
            "support_guard": "local_source_neighborhood",
        },
    )


def thin_zhang_suen(mask: np.ndarray, *, max_iterations: int = 128) -> tuple[np.ndarray, int]:
    """Return a one-pixel centerline using vectorized Zhang-Suen thinning."""

    if mask.ndim != 2 or mask.dtype != np.bool_:
        raise ValueError("mask must be a 2D boolean array.")
    work = np.pad(mask, 1, mode="constant", constant_values=False)
    iterations = 0
    for iterations in range(1, max_iterations + 1):
        changed = False
        for step in (0, 1):
            p2 = work[:-2, 1:-1]
            p3 = work[:-2, 2:]
            p4 = work[1:-1, 2:]
            p5 = work[2:, 2:]
            p6 = work[2:, 1:-1]
            p7 = work[2:, :-2]
            p8 = work[1:-1, :-2]
            p9 = work[:-2, :-2]
            center = work[1:-1, 1:-1]
            neighbors = (
                p2.astype(np.uint8)
                + p3
                + p4
                + p5
                + p6
                + p7
                + p8
                + p9
            )
            transitions = (
                (~p2 & p3).astype(np.uint8)
                + (~p3 & p4)
                + (~p4 & p5)
                + (~p5 & p6)
                + (~p6 & p7)
                + (~p7 & p8)
                + (~p8 & p9)
                + (~p9 & p2)
            )
            if step == 0:
                connectivity = ~(p2 & p4 & p6) & ~(p4 & p6 & p8)
            else:
                connectivity = ~(p2 & p4 & p8) & ~(p2 & p6 & p8)
            remove = center & (neighbors >= 2) & (neighbors <= 6) & (transitions == 1)
            remove &= connectivity
            if remove.any():
                center[remove] = False
                changed = True
        if not changed:
            return work[1:-1, 1:-1].copy(), iterations
    return work[1:-1, 1:-1].copy(), iterations


def trace_centerline_paths(
    centerline: np.ndarray,
) -> tuple[list[tuple[list[Point], bool]], int, np.ndarray]:
    """Trace centerline pixels into open graph edges and protected closed loops."""

    degree = ndimage.convolve(
        centerline.astype(np.uint8),
        np.ones((3, 3), dtype=np.uint8),
        mode="constant",
        cval=0,
    ).astype(np.int16) - centerline.astype(np.int16)
    pixels = {tuple(point) for point in np.argwhere(centerline)}
    nodes = {point for point in pixels if degree[point] != 2}
    visited_edges: set[tuple[Point, Point]] = set()
    paths: list[tuple[list[Point], bool]] = []

    for node in nodes:
        for neighbor in _neighbors(node, pixels):
            edge = _edge(node, neighbor)
            if edge in visited_edges:
                continue
            path = _trace_from(node, neighbor, pixels, degree, visited_edges)
            if len(path) >= 2:
                paths.append((path, False))

    closed_path_count = 0
    for point in pixels:
        for neighbor in _neighbors(point, pixels):
            edge = _edge(point, neighbor)
            if edge in visited_edges:
                continue
            path = _trace_loop(point, neighbor, pixels, visited_edges)
            if len(path) >= 3:
                paths.append((path, True))
                closed_path_count += 1
    return paths, closed_path_count, degree


def _trace_from(
    start: Point,
    neighbor: Point,
    pixels: set[Point],
    degree: np.ndarray,
    visited_edges: set[tuple[Point, Point]],
) -> list[Point]:
    path = [start, neighbor]
    visited_edges.add(_edge(start, neighbor))
    previous = start
    current = neighbor
    while degree[current] == 2:
        candidates = [point for point in _neighbors(current, pixels) if point != previous]
        if not candidates:
            break
        next_point = candidates[0]
        edge = _edge(current, next_point)
        if edge in visited_edges:
            break
        visited_edges.add(edge)
        path.append(next_point)
        previous, current = current, next_point
    return path


def _trace_loop(
    start: Point,
    neighbor: Point,
    pixels: set[Point],
    visited_edges: set[tuple[Point, Point]],
) -> list[Point]:
    path = [start, neighbor]
    visited_edges.add(_edge(start, neighbor))
    previous = start
    current = neighbor
    while True:
        candidates = [point for point in _neighbors(current, pixels) if point != previous]
        if not candidates:
            break
        next_point = candidates[0]
        edge = _edge(current, next_point)
        if next_point == start:
            visited_edges.add(edge)
            break
        if edge in visited_edges:
            break
        visited_edges.add(edge)
        path.append(next_point)
        previous, current = current, next_point
    return path


def _filter_high_frequency_path(
    points: np.ndarray,
    cumulative: np.ndarray,
    *,
    sigma_source_px: float,
    sample_step_source_px: float,
    strength: float,
    max_displacement_source_px: float,
    protection: float,
    corner_angle_degrees: float,
    corner_window_source_px: float,
) -> tuple[np.ndarray, list[int], dict[str, float]]:
    """Remove short-period lateral jitter while preserving dense path geometry."""

    original = points.astype(np.float32)
    total_length = float(cumulative[-1]) if cumulative.size else 0.0
    if len(points) < 5 or total_length <= 0.0 or sigma_source_px <= 0.0:
        return original, [], {
            "noise_energy_before": 0.0,
            "noise_energy_after": 0.0,
            "resampled_sample_count": 0.0,
            "clamped_point_count": 0.0,
        }

    sample_count = max(5, int(ceil(total_length / sample_step_source_px)) + 1)
    uniform_arc = np.linspace(0.0, total_length, sample_count, dtype=np.float32)
    actual_step = total_length / max(sample_count - 1, 1)
    uniform_points = np.column_stack(
        [
            np.interp(uniform_arc, cumulative, original[:, dimension])
            for dimension in range(2)
        ]
    ).astype(np.float32)
    sigma_samples = sigma_source_px / max(actual_step, 1.0e-6)
    filtered_uniform = ndimage.gaussian_filter1d(
        uniform_points,
        sigma=sigma_samples,
        axis=0,
        mode="nearest",
        truncate=3.0,
    ).astype(np.float32)
    target = np.column_stack(
        [
            np.interp(cumulative, uniform_arc, filtered_uniform[:, dimension])
            for dimension in range(2)
        ]
    ).astype(np.float32)

    point_indices = np.arange(len(target), dtype=np.int32)
    before = target[np.maximum(point_indices - 2, 0)]
    after = target[np.minimum(point_indices + 2, len(target) - 1)]
    tangent = after - before
    tangent_length = np.linalg.norm(tangent, axis=1, keepdims=True)
    tangent /= np.maximum(tangent_length, np.float32(1.0e-6))
    displacement = target - original
    lateral = displacement - tangent * np.sum(
        displacement * tangent,
        axis=1,
        keepdims=True,
    )

    corner_indices = _corner_anchor_indices(
        points,
        cumulative,
        angle_degrees=corner_angle_degrees,
        window_source_px=corner_window_source_px,
    )
    feather = max(sample_step_source_px, sigma_source_px * 3.0)
    weight = np.ones(len(points), dtype=np.float32)
    protected_locations = [(0.0, protection), (total_length, protection)]
    protected_locations.extend(
        (float(cumulative[index]), corner_window_source_px)
        for index in corner_indices
    )
    for location, radius in protected_locations:
        normalized = np.clip(
            (np.abs(cumulative - np.float32(location)) - np.float32(radius))
            / np.float32(feather),
            0.0,
            1.0,
        )
        smooth_weight = normalized * normalized * (3.0 - 2.0 * normalized)
        weight = np.minimum(weight, smooth_weight)

    movement = lateral * weight[:, None] * np.float32(strength)
    movement_length = np.linalg.norm(movement, axis=1)
    clamped = movement_length > np.float32(max_displacement_source_px)
    if max_displacement_source_px > 0.0:
        limit = np.minimum(
            1.0,
            np.float32(max_displacement_source_px)
            / np.maximum(movement_length, np.float32(1.0e-6)),
        )
        movement *= limit[:, None]
    residual_after = lateral - movement
    return (
        original + movement,
        corner_indices,
        {
            "noise_energy_before": float(np.sum(lateral * lateral)),
            "noise_energy_after": float(np.sum(residual_after * residual_after)),
            "resampled_sample_count": float(sample_count),
            "clamped_point_count": float(np.count_nonzero(clamped)),
        },
    )


def _corner_anchor_indices(
    points: np.ndarray,
    cumulative: np.ndarray,
    *,
    angle_degrees: float,
    window_source_px: float,
) -> list[int]:
    """Return stable sharp corners measured across a source-scale arc window."""

    if len(points) < 3 or window_source_px <= 0.0:
        return []
    point_indices = np.arange(len(points), dtype=np.int32)
    left_indices = np.searchsorted(
        cumulative,
        cumulative - np.float32(window_source_px),
        side="left",
    ).astype(np.int32)
    right_indices = (
        np.searchsorted(
            cumulative,
            cumulative + np.float32(window_source_px),
            side="right",
        ).astype(np.int32)
        - 1
    )
    valid = (left_indices < point_indices) & (right_indices > point_indices)
    if not valid.any():
        return []

    incoming = points.astype(np.float32) - points[left_indices].astype(np.float32)
    outgoing = points[right_indices].astype(np.float32) - points.astype(np.float32)
    incoming_length = np.sqrt(np.sum(incoming * incoming, axis=1))
    outgoing_length = np.sqrt(np.sum(outgoing * outgoing, axis=1))
    denominator = np.maximum(incoming_length * outgoing_length, np.float32(1.0e-6))
    cosine = np.clip(np.sum(incoming * outgoing, axis=1) / denominator, -1.0, 1.0)
    angles = np.degrees(np.arccos(cosine))
    candidates = np.flatnonzero(valid & (angles >= np.float32(angle_degrees))).tolist()
    if not candidates:
        return []

    anchors: list[int] = []
    group = [candidates[0]]
    for index in candidates[1:]:
        if cumulative[index] - cumulative[group[-1]] <= np.float32(window_source_px):
            group.append(index)
            continue
        anchors.append(max(group, key=lambda item: float(angles[item])))
        group = [index]
    anchors.append(max(group, key=lambda item: float(angles[item])))
    return anchors


def _long_stroke_rejection_reason(
    points: np.ndarray,
    cumulative: np.ndarray,
    radii: np.ndarray,
    *,
    gate_enabled: bool,
    min_chord_arc_ratio: float,
    max_line_fit_rms_source_px: float,
    max_line_fit_deviation_source_px: float,
    max_width_cv: float,
    max_width_ratio: float,
    skip_paths_with_corners: bool,
    corner_angle_degrees: float,
    corner_window_source_px: float,
) -> tuple[str | None, list[int]]:
    """Return why a path is unsafe for long-stroke simplification."""

    if not gate_enabled:
        return None, []
    corners = _corner_anchor_indices(
        points,
        cumulative,
        angle_degrees=corner_angle_degrees,
        window_source_px=corner_window_source_px,
    )
    if skip_paths_with_corners and corners:
        return "has_corner", corners

    path_length = float(cumulative[-1]) if cumulative.size else 0.0
    chord_length = float(np.linalg.norm((points[-1] - points[0]).astype(np.float32)))
    chord_arc_ratio = chord_length / path_length if path_length > 0.0 else 0.0
    if chord_arc_ratio < min_chord_arc_ratio:
        return "low_chord_arc_ratio", corners

    xy = points[:, ::-1].astype(np.float64)
    centered = xy - xy.mean(axis=0)
    _, _, axes = np.linalg.svd(centered, full_matrices=False)
    normal = np.array([-axes[0, 1], axes[0, 0]], dtype=np.float64)
    residual = np.abs(centered @ normal)
    rms = float(np.sqrt(np.mean(residual * residual)))
    if rms > max_line_fit_rms_source_px:
        return "line_fit_rms", corners
    if float(residual.max(initial=0.0)) > max_line_fit_deviation_source_px:
        return "line_fit_deviation", corners

    mean_radius = float(radii.mean())
    width_cv = float(radii.std() / max(mean_radius, 1.0e-6))
    if width_cv > max_width_cv:
        return "width_variation", corners
    p10, p90 = np.percentile(radii, (10.0, 90.0))
    if float(p90 / max(p10, 1.0e-6)) > max_width_ratio:
        return "width_variation", corners
    return None, corners


def _build_affected_mask(
    support: np.ndarray,
    component_labels: np.ndarray,
    affected_centerline: np.ndarray,
    affected_radius: np.ndarray,
    affected_component: np.ndarray,
    *,
    displacement_margin: float,
) -> np.ndarray:
    distance, indices = ndimage.distance_transform_edt(
        ~affected_centerline,
        return_indices=True,
    )
    nearest_radius = affected_radius[indices[0], indices[1]]
    nearest_component = affected_component[indices[0], indices[1]]
    return (
        support
        & (component_labels == nearest_component)
        & (distance <= nearest_radius + np.float32(displacement_margin + 0.75))
    )


def _render_paths(
    shape_hr: tuple[int, int],
    render_paths: list[tuple[np.ndarray, np.ndarray]],
    *,
    scale: int,
) -> FloatImage:
    rendered = np.zeros(shape_hr, dtype=np.float32)
    for path, widths_hr in render_paths:
        if len(path) < 2:
            continue
        centers_y = (path[:, 0] + np.float32(0.5)) * scale - np.float32(0.5)
        centers_x = (path[:, 1] + np.float32(0.5)) * scale - np.float32(0.5)
        margin = int(ceil(float(widths_hr.max(initial=1.0)) * 0.5 + 3.0))
        y0 = max(0, int(np.floor(float(centers_y.min()))) - margin)
        y1 = min(shape_hr[0], int(np.ceil(float(centers_y.max()))) + margin + 1)
        x0 = max(0, int(np.floor(float(centers_x.min()))) - margin)
        x1 = min(shape_hr[1], int(np.ceil(float(centers_x.max()))) + margin + 1)
        if y1 <= y0 or x1 <= x0:
            continue
        native_width = x1 - x0
        native_height = y1 - y0
        supersample = 4
        if native_width * native_height * supersample * supersample > 64_000_000:
            supersample = 2
        canvas = Image.new(
            "L",
            (native_width * supersample, native_height * supersample),
            0,
        )
        draw = ImageDraw.Draw(canvas)
        xy = [
            (
                int(round((float(x) - x0) * supersample)),
                int(round((float(y) - y0) * supersample)),
            )
            for y, x in zip(centers_y, centers_x, strict=True)
        ]
        for index, (start, end) in enumerate(zip(xy, xy[1:], strict=False)):
            width_hr = max(
                1,
                int(
                    round(
                        float((widths_hr[index] + widths_hr[index + 1]) * 0.5)
                        * supersample
                    )
                ),
            )
            draw.line((start, end), fill=255, width=width_hr)
        endpoint_widths = (
            max(1, int(round(float(widths_hr[0]) * supersample))),
            max(1, int(round(float(widths_hr[-1]) * supersample))),
        )
        for point, width_hr in zip((xy[0], xy[-1]), endpoint_widths, strict=True):
            circle_radius = width_hr / 2.0
            draw.ellipse(
                (
                    point[0] - circle_radius,
                    point[1] - circle_radius,
                    point[0] + circle_radius,
                    point[1] + circle_radius,
                ),
                fill=255,
            )
        local = canvas.resize(
            (native_width, native_height),
            Image.Resampling.LANCZOS,
        )
        local_alpha = np.asarray(local, dtype=np.float32) / np.float32(255.0)
        np.maximum(rendered[y0:y1, x0:x1], local_alpha, out=rendered[y0:y1, x0:x1])
    return rendered


def _filter_path_widths(
    widths_hr: np.ndarray,
    cumulative: np.ndarray,
    *,
    sigma_source_px: float,
    sample_step_source_px: float,
    strength: float,
    protection: float,
) -> np.ndarray:
    """Remove short-period width noise without changing protected endpoints."""

    total_length = float(cumulative[-1]) if cumulative.size else 0.0
    if len(widths_hr) < 3 or total_length <= 0.0 or sigma_source_px <= 0.0:
        return widths_hr.astype(np.float32, copy=True)
    sample_count = max(3, int(ceil(total_length / sample_step_source_px)) + 1)
    uniform_arc = np.linspace(0.0, total_length, sample_count, dtype=np.float32)
    actual_step = total_length / max(sample_count - 1, 1)
    uniform_widths = np.interp(uniform_arc, cumulative, widths_hr).astype(np.float32)
    filtered_uniform = ndimage.gaussian_filter1d(
        uniform_widths,
        sigma=sigma_source_px / max(actual_step, 1.0e-6),
        mode="nearest",
        truncate=3.0,
    ).astype(np.float32)
    target = np.interp(cumulative, uniform_arc, filtered_uniform).astype(np.float32)
    feather = max(sample_step_source_px, sigma_source_px * 3.0)
    distance_to_endpoint = np.minimum(cumulative, total_length - cumulative)
    normalized = np.clip(
        (distance_to_endpoint - np.float32(protection)) / np.float32(feather),
        0.0,
        1.0,
    )
    weight = normalized * normalized * (3.0 - 2.0 * normalized)
    return widths_hr + (target - widths_hr) * weight * np.float32(strength)


def _estimate_widths_hr(
    line_alpha_hr: FloatImage,
    path: np.ndarray,
    kept_indices: list[int],
    *,
    scale: int,
    max_radius_source_px: float,
) -> np.ndarray:
    """Estimate antialiased line width along normals to the source centerline."""

    indices = np.asarray(kept_indices, dtype=np.int32)
    before = path[np.maximum(indices - 2, 0)].astype(np.float32)
    after = path[np.minimum(indices + 2, len(path) - 1)].astype(np.float32)
    tangent = after - before
    tangent_length = np.sqrt(np.sum(tangent * tangent, axis=1))
    tangent_length = np.maximum(tangent_length, np.float32(1.0e-6))
    normal_y = tangent[:, 1] / tangent_length
    normal_x = -tangent[:, 0] / tangent_length

    centers = path[indices].astype(np.float32)
    center_y = (centers[:, 0] + np.float32(0.5)) * scale - np.float32(0.5)
    center_x = (centers[:, 1] + np.float32(0.5)) * scale - np.float32(0.5)
    sample_radius = max_radius_source_px * scale + 2.0
    offsets = np.arange(-sample_radius, sample_radius + 0.25, 0.25, dtype=np.float32)
    sample_y = center_y[:, None] + normal_y[:, None] * offsets[None, :]
    sample_x = center_x[:, None] + normal_x[:, None] * offsets[None, :]
    samples = ndimage.map_coordinates(
        line_alpha_hr,
        (sample_y, sample_x),
        order=1,
        mode="constant",
        cval=0.0,
        prefilter=False,
    )
    widths = np.empty(samples.shape[0], dtype=np.float32)
    center_candidates = np.flatnonzero(np.abs(offsets) <= np.float32(scale))
    for row_index, row in enumerate(samples):
        anchor = int(center_candidates[int(np.argmax(row[center_candidates]))])
        active = row >= np.float32(0.05)
        if not active[anchor]:
            widths[row_index] = np.float32(scale)
            continue
        left = anchor
        while left > 0 and active[left - 1]:
            left -= 1
        right = anchor
        while right + 1 < len(row) and active[right + 1]:
            right += 1
        if right > left:
            widths[row_index] = np.float32(
                np.trapz(row[left : right + 1], x=offsets[left : right + 1])
            )
        else:
            widths[row_index] = np.float32(max(1.0, float(row[anchor])))
    return np.clip(widths, 1.0, 2.0 * max_radius_source_px * scale)


def _draw_float_polyline_on_bool(target: np.ndarray, points: np.ndarray) -> None:
    if len(points) < 2:
        for y, x in points:
            target[int(round(float(y))), int(round(float(x)))] = True
        return
    image = Image.fromarray(target.astype(np.uint8) * 255)
    draw = ImageDraw.Draw(image)
    xy = [(float(x), float(y)) for y, x in points]
    draw.line(xy, fill=255, width=1)
    target[:] = np.asarray(image) > 0


def _mark_protected_path_ends(
    protected: np.ndarray,
    points: np.ndarray,
    cumulative: np.ndarray,
    *,
    protection: float,
) -> None:
    mask = (cumulative <= protection) | (cumulative >= cumulative[-1] - protection)
    for y, x in points[mask]:
        protected[y, x] = True


def _dilate_protected(protected: np.ndarray, radius: float) -> np.ndarray:
    iterations = max(1, int(ceil(radius)))
    return ndimage.binary_dilation(protected, iterations=iterations)


def _resize_bool_nearest(mask: np.ndarray, shape_hr: tuple[int, int]) -> np.ndarray:
    resized = Image.fromarray(mask.astype(np.uint8) * 255).resize(
        (shape_hr[1], shape_hr[0]),
        Image.Resampling.NEAREST,
    )
    return np.asarray(resized) > 0


def _dilate_bool_pillow(mask: np.ndarray, *, radius: int) -> np.ndarray:
    size = radius * 2 + 1
    image = Image.fromarray(mask.astype(np.uint8) * 255)
    return np.asarray(image.filter(ImageFilter.MaxFilter(size=size))) > 0


def _maximum_filter_alpha_pillow(alpha: FloatImage, *, radius: int) -> FloatImage:
    size = radius * 2 + 1
    quantized = np.clip(np.rint(alpha * np.float32(255.0)), 0.0, 255.0).astype(np.uint8)
    maximum = Image.fromarray(quantized).filter(ImageFilter.MaxFilter(size=size))
    return np.asarray(maximum, dtype=np.float32) / np.float32(255.0)


def _remove_new_small_components(
    binary_alpha: FloatImage,
    original_binary: np.ndarray,
    *,
    max_area: int,
) -> int:
    if max_area <= 0:
        return 0
    labels, count = ndimage.label(
        binary_alpha > np.float32(0.5),
        structure=np.ones((3, 3), dtype=np.uint8),
    )
    if count == 0:
        return 0
    areas = np.bincount(labels.ravel(), minlength=count + 1)
    original_overlap = np.bincount(
        labels[original_binary].ravel(),
        minlength=count + 1,
    )
    removable = (areas <= max_area) & (original_overlap == 0)
    removable[0] = False
    remove_mask = removable[labels]
    removed = int(remove_mask.sum())
    binary_alpha[remove_mask] = np.float32(0.0)
    return removed


def _rollback_unsafe_components(
    candidate_alpha: FloatImage,
    original_alpha: FloatImage,
    affected_source: np.ndarray,
    component_labels: np.ndarray,
    replacement_region_hr: np.ndarray,
    *,
    scale: int,
    binary_threshold: float,
    binary_output: bool,
    enabled: bool,
    preserve_component_count: bool,
    min_ink_ratio: float,
    max_ink_ratio: float,
) -> tuple[FloatImage, np.ndarray, dict[str, Any]]:
    """Restore source-component changes that break global binary topology."""

    base_stats: dict[str, Any] = {
        "enabled": enabled,
        "preserve_component_count": preserve_component_count,
        "min_ink_ratio": min_ink_ratio,
        "max_ink_ratio": max_ink_ratio,
        "evaluated_component_count": 0,
        "accepted_component_count": 0,
        "rolled_back_component_count": 0,
        "rolled_back_component_ids": [],
        "rolled_back_pixel_count": 0,
        "original_component_count": 0,
        "candidate_component_count": 0,
        "final_component_count": 0,
        "rollback_reason_counts": {
            "component_disappeared": 0,
            "component_split": 0,
            "component_merged": 0,
            "new_component": 0,
            "ink_loss": 0,
            "ink_gain": 0,
        },
        "component_reports": [],
    }
    rolled_back_source = np.zeros_like(affected_source, dtype=bool)
    if not enabled:
        return candidate_alpha, rolled_back_source, base_stats

    changed_hr = (
        np.abs(candidate_alpha - original_alpha) > np.float32(1.0 / 255.0)
    )
    if not changed_hr.any() or not affected_source.any():
        return candidate_alpha, rolled_back_source, base_stats

    seed_labels = np.where(affected_source, component_labels, 0)
    if not np.any(seed_labels > 0):
        return candidate_alpha, rolled_back_source, base_stats
    _, nearest_indices = ndimage.distance_transform_edt(
        seed_labels == 0,
        return_indices=True,
    )
    owner_source = seed_labels[nearest_indices[0], nearest_indices[1]]
    original_binary = original_alpha >= np.float32(binary_threshold)
    candidate_binary = candidate_alpha >= np.float32(binary_threshold)
    structure = np.ones((3, 3), dtype=np.uint8)
    original_labels, original_component_count = ndimage.label(
        original_binary,
        structure=structure,
    )
    candidate_labels, candidate_component_count = ndimage.label(
        candidate_binary,
        structure=structure,
    )
    result = candidate_alpha.astype(np.float32, copy=True)
    affected_ids = np.unique(seed_labels[seed_labels > 0])
    reports: list[dict[str, Any]] = []
    rolled_back_ids: list[int] = []
    rolled_back_pixel_count = 0
    reason_counts = dict(base_stats["rollback_reason_counts"])

    for component_id_value in affected_ids:
        component_id = int(component_id_value)
        owner_mask_source = owner_source == component_id
        owner_hr = np.repeat(
            np.repeat(owner_mask_source, scale, axis=0),
            scale,
            axis=1,
        )
        owned_region_hr = replacement_region_hr & owner_hr
        changed_owned_hr = changed_hr & owned_region_hr
        if not changed_owned_hr.any():
            continue
        original_ink = int(np.count_nonzero(original_binary & owned_region_hr))
        candidate_ink = int(np.count_nonzero(candidate_binary & owned_region_hr))
        ink_ratio = candidate_ink / max(original_ink, 1)
        original_ids = np.unique(
            original_labels[owned_region_hr & original_binary]
        )
        original_ids = original_ids[original_ids > 0]
        candidate_ids = np.unique(
            candidate_labels[owned_region_hr & candidate_binary]
        )
        candidate_ids = candidate_ids[candidate_ids > 0]
        reasons: set[str] = set()
        if preserve_component_count:
            for original_id in original_ids:
                mapped_candidate_ids = np.unique(
                    candidate_labels[
                        (original_labels == original_id) & candidate_binary
                    ]
                )
                mapped_candidate_ids = mapped_candidate_ids[mapped_candidate_ids > 0]
                if len(mapped_candidate_ids) == 0:
                    reasons.add("component_disappeared")
                elif len(mapped_candidate_ids) > 1:
                    reasons.add("component_split")
            for candidate_id in candidate_ids:
                mapped_original_ids = np.unique(
                    original_labels[
                        (candidate_labels == candidate_id) & original_binary
                    ]
                )
                mapped_original_ids = mapped_original_ids[mapped_original_ids > 0]
                if len(mapped_original_ids) == 0:
                    reasons.add("new_component")
                elif len(mapped_original_ids) > 1:
                    reasons.add("component_merged")
        if ink_ratio < min_ink_ratio:
            reasons.add("ink_loss")
        elif ink_ratio > max_ink_ratio:
            reasons.add("ink_gain")

        ordered_reasons = sorted(reasons)
        report = {
            "component_id": component_id,
            "changed_pixel_count": int(np.count_nonzero(changed_owned_hr)),
            "original_component_ids": [int(value) for value in original_ids],
            "candidate_component_ids": [int(value) for value in candidate_ids],
            "original_ink_pixel_count": original_ink,
            "candidate_ink_pixel_count": candidate_ink,
            "ink_ratio": float(ink_ratio),
            "rolled_back": bool(reasons),
            "reasons": ordered_reasons,
        }
        reports.append(report)
        if not reasons:
            continue
        if binary_output:
            result[changed_owned_hr] = original_binary[changed_owned_hr].astype(
                np.float32
            )
        else:
            result[changed_owned_hr] = original_alpha[changed_owned_hr]
        rolled_back_source |= affected_source & (component_labels == component_id)
        rolled_back_ids.append(component_id)
        rolled_back_pixel_count += int(np.count_nonzero(changed_owned_hr))
        for reason in ordered_reasons:
            reason_counts[reason] += 1

    del original_labels, candidate_labels
    final_binary = result >= np.float32(binary_threshold)
    _, final_component_count = ndimage.label(final_binary, structure=structure)
    stats = {
        **base_stats,
        "evaluated_component_count": len(reports),
        "accepted_component_count": sum(not report["rolled_back"] for report in reports),
        "rolled_back_component_count": len(rolled_back_ids),
        "rolled_back_component_ids": rolled_back_ids,
        "rolled_back_pixel_count": rolled_back_pixel_count,
        "original_component_count": int(original_component_count),
        "candidate_component_count": int(candidate_component_count),
        "final_component_count": int(final_component_count),
        "rollback_reason_counts": reason_counts,
        "component_reports": reports,
    }
    return result, rolled_back_source, stats


def _block_mean(image: FloatImage, scale: int) -> FloatImage:
    height, width = image.shape
    reshaped = image.reshape(height // scale, scale, width // scale, scale)
    return reshaped.mean(axis=(1, 3), dtype=np.float32).astype(np.float32, copy=False)


def _cumulative_lengths(points: np.ndarray) -> np.ndarray:
    if len(points) == 0:
        return np.empty(0, dtype=np.float32)
    differences = np.diff(points.astype(np.float32), axis=0)
    lengths = np.sqrt(np.sum(differences * differences, axis=1))
    return np.concatenate((np.zeros(1, dtype=np.float32), np.cumsum(lengths)))


def _neighbors(point: Point, pixels: set[Point]) -> list[Point]:
    y, x = point
    result: list[Point] = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            candidate = (y + dy, x + dx)
            if candidate not in pixels:
                continue
            if dy != 0 and dx != 0:
                if (y, x + dx) in pixels or (y + dy, x) in pixels:
                    continue
            result.append(candidate)
    return result


def _edge(first: Point, second: Point) -> tuple[Point, Point]:
    return (first, second) if first <= second else (second, first)


def _mark_points(target: np.ndarray, points: list[Point], *, value: bool = True) -> None:
    for y, x in points:
        target[y, x] = value


def _validate_alpha(alpha: FloatImage) -> None:
    if alpha.ndim != 2 or not np.issubdtype(alpha.dtype, np.floating):
        raise ValueError("line_alpha_hr must be a 2D floating point array.")
    if alpha.size == 0 or not np.isfinite(alpha).all():
        raise ValueError("line_alpha_hr must be non-empty and finite.")
    if float(alpha.min()) < 0.0 or float(alpha.max()) > 1.0:
        raise ValueError("line_alpha_hr must be between 0.0 and 1.0.")
