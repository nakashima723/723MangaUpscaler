"""Configuration loading and merge helpers."""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from mlu.scales import SUPPORTED_SCALES, SUPPORTED_SCALES_TEXT


class ConfigError(ValueError):
    """Raised when configuration data is invalid."""


DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "io": {
        "output_bit_depth": 8,
        "preserve_alpha": False,
        "overwrite": False,
    },
    "pipeline": {
        "scale": 4,
        "line_renderer": "sdf",
        "tone_mode": "white_canvas",
        "debug": False,
    },
    "mask": {
        "black_threshold": 0.72,
        "adaptive": {
            "enabled": False,
            "method": "sauvola",
            "window_size": 31,
            "k": 0.18,
        },
        "hysteresis": {
            "enabled": True,
            "strong": 0.50,
            "weak": 0.25,
        },
        "cleanup": {
            "min_component_area": 6,
            "close_radius": 0,
            "fill_holes_area": 12,
        },
        "soft_coverage": {
            "mode": "darkness",
            "gamma": 1.0,
        },
    },
    "sdf": {
        "interpolation": "lanczos",
        "distance_source": "soft_mask_hr",
        "soft_sdf_threshold": 0.22,
        "width_bias_source_px": 0.0,
        "aa_radius_hr_px": 0.75,
        "soft_alpha_mode": "none",
        "soft_gain": 0.0,
    },
    "line_stabilizer": {
        "enabled": False,
        "strength": 0.55,
        "min_coverage": 0.35,
        "min_length_source_px": 32.0,
        "max_rms_error_source_px": 0.55,
        "min_density": 0.35,
        "max_gap_source_px": 4.0,
        "angle_step_degrees": 5.0,
        "rho_tolerance_source_px": 0.75,
        "max_segments": 96,
        "max_candidates_per_angle": 24,
        "min_width_source_px": 0.85,
        "max_width_source_px": 2.25,
        "width_scale": 1.0,
        "band_margin_hr_px": 1.5,
        "support_dilate_hr_px": 2,
    },
    "directional_smoothing": {
        "enabled": False,
        "strength": 0.55,
        "radius_hr_px": 2,
        "min_angle_from_axis_degrees": 20.0,
        "full_strength_angle_from_axis_degrees": 34.0,
        "orientation_sigma_hr_px": 1.0,
        "tensor_sigma_hr_px": 2.0,
        "min_orientation_confidence": 0.12,
        "min_gradient_energy": 1.0e-5,
        "min_alpha": 0.04,
        "support_dilate_hr_px": 1,
        "max_delta": 0.35,
    },
    "centerline_simplification": {
        "enabled": False,
        "filter_sigma_source_px": 0.0,
        "filter_sample_step_source_px": 0.50,
        "max_filter_displacement_source_px": 0.75,
        "strength": 1.0,
        "alpha_threshold": 0.50,
        "min_path_length_source_px": 64.0,
        "endpoint_protection_source_px": 3.0,
        "max_radius_source_px": 2.25,
        "support_margin_source_px": 0.75,
        "binarize_output": True,
        "binary_threshold": 0.50,
        "max_new_component_area": 2,
        "corner_angle_degrees": 45.0,
        "corner_window_source_px": 3.0,
        "geometry_strength": 1.0,
        "long_stroke_gate": {
            "enabled": True,
            "min_chord_arc_ratio": 0.985,
            "max_line_fit_rms_source_px": 0.35,
            "max_line_fit_deviation_source_px": 1.0,
            "max_width_cv": 0.20,
            "max_width_ratio": 1.50,
            "skip_paths_with_corners": True,
        },
        "component_rollback": {
            "enabled": True,
            "preserve_component_count": True,
            "min_ink_ratio": 0.80,
            "max_ink_ratio": 1.20,
        },
        "max_thinning_iterations": 128,
    },
    "potrace": {
        "turdsize": 2,
        "alphamax": 1.0,
        "opttolerance": 0.2,
        "opticurve": True,
        "turnpolicy": "minority",
        "rasterizer": "cairosvg",
    },
    "tone_source": {
        "mode": "white_canvas",
        "dilate_radius": 1.2,
        "lift_strength": 0.85,
        "background_blur_radius": 9.0,
        "protect_midtones": True,
    },
    "upscaler": {
        "engine": "none",
        "fallback": "lanczos",
        "realcugan": {
            "noise": -1,
            "tile_size": 256,
        },
        "waifu2x": {
            "model": "models-cunet",
            "noise": -1,
            "tile_size": 256,
        },
        "realesrgan": {
            "model": "realesrgan-x4plus-anime",
            "tile_size": 256,
        },
    },
    "composite": {
        "line_darkness": 1.0,
        "edge_alpha_gamma": 1.2,
        "tone_usage": "auto",
        "clamp": True,
    },
    "debug": {
        "save_layers": False,
        "save_run_json": False,
        "contact_sheet": False,
    },
    "external_tools": {
        "realcugan": None,
        "waifu2x": None,
        "realesrgan": None,
        "potrace": None,
        "cairosvg": None,
        "inkscape": None,
    },
}


def repo_root() -> Path:
    """Return the repository or bundled application resource root."""

    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(str(bundled_root))
    return Path(__file__).resolve().parents[2]


def preset_path(name: str) -> Path:
    """Return a preset YAML path for a preset name."""

    if not name:
        raise ConfigError("Preset name must not be empty.")
    if any(part in name for part in ("/", "\\", "..")):
        raise ConfigError(f"Invalid preset name: {name!r}")
    return repo_root() / "config" / "presets" / f"{name}.yaml"


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    """Load a YAML mapping from disk."""

    yaml_path = Path(path)
    try:
        with yaml_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except OSError as exc:
        raise ConfigError(f"Could not read config file: {yaml_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Could not parse YAML config file: {yaml_path}") from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config file must contain a YAML mapping: {yaml_path}")
    return data


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a recursive merge of two dictionaries."""

    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_config(
    *,
    preset: str = "line_only",
    config_path: str | Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve config as defaults, preset, user config, then CLI overrides."""

    config = deepcopy(DEFAULT_CONFIG)
    path = preset_path(preset)
    if path.exists():
        config = deep_merge(config, load_yaml_file(path))
    elif preset:
        raise ConfigError(f"Preset does not exist: {preset}")

    if config_path is not None:
        config = deep_merge(config, load_yaml_file(config_path))

    if cli_overrides:
        config = deep_merge(config, cli_overrides)

    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    """Validate the MVP subset of the resolved configuration."""

    if config.get("version") != 1:
        raise ConfigError("Only config version 1 is supported.")

    output_bit_depth = config.get("io", {}).get("output_bit_depth")
    if output_bit_depth not in (8, 16):
        raise ConfigError("io.output_bit_depth must be 8 or 16.")

    scale = config.get("pipeline", {}).get("scale")
    if scale not in SUPPORTED_SCALES:
        raise ConfigError(f"pipeline.scale must be {SUPPORTED_SCALES_TEXT}.")

    line_renderer = config.get("pipeline", {}).get("line_renderer")
    if line_renderer not in {"sdf", "potrace"}:
        raise ConfigError("pipeline.line_renderer must be one of: sdf, potrace.")

    threshold = config.get("mask", {}).get("black_threshold")
    if not isinstance(threshold, int | float) or not 0.0 <= float(threshold) <= 1.0:
        raise ConfigError("mask.black_threshold must be between 0.0 and 1.0.")
    soft_coverage_config = config.get("mask", {}).get("soft_coverage", {})
    soft_coverage_mode = soft_coverage_config.get("mode", "darkness")
    if soft_coverage_mode not in {
        "darkness",
        "line_probability",
        "probability",
        "line_prob",
        "max",
        "max_probability",
        "legacy_max",
    }:
        raise ConfigError(
            "mask.soft_coverage.mode must be one of: darkness, line_probability, "
            "max_probability."
        )
    soft_coverage_gamma = soft_coverage_config.get("gamma", 1.0)
    if not isinstance(soft_coverage_gamma, int | float) or float(soft_coverage_gamma) <= 0.0:
        raise ConfigError("mask.soft_coverage.gamma must be greater than 0.0.")

    overwrite = config.get("io", {}).get("overwrite")
    if not isinstance(overwrite, bool):
        raise ConfigError("io.overwrite must be a boolean.")

    save_run_json = config.get("debug", {}).get("save_run_json")
    if not isinstance(save_run_json, bool):
        raise ConfigError("debug.save_run_json must be a boolean.")

    sdf_config = config.get("sdf", {})
    distance_source = sdf_config.get("distance_source")
    if distance_source not in {"binary_mask", "soft_mask_hr"}:
        raise ConfigError("sdf.distance_source must be one of: binary_mask, soft_mask_hr.")

    soft_sdf_threshold = sdf_config.get("soft_sdf_threshold")
    if (
        not isinstance(soft_sdf_threshold, int | float)
        or not 0.0 <= float(soft_sdf_threshold) <= 1.0
    ):
        raise ConfigError("sdf.soft_sdf_threshold must be between 0.0 and 1.0.")

    soft_alpha_mode = sdf_config.get("soft_alpha_mode")
    if soft_alpha_mode not in {"none", "max", "blend"}:
        raise ConfigError("sdf.soft_alpha_mode must be one of: none, max, blend.")

    soft_gain = sdf_config.get("soft_gain")
    if not isinstance(soft_gain, int | float) or not 0.0 <= float(soft_gain) <= 1.0:
        raise ConfigError("sdf.soft_gain must be between 0.0 and 1.0.")

    aa_radius = sdf_config.get("aa_radius_hr_px")
    if not isinstance(aa_radius, int | float) or float(aa_radius) <= 0.0:
        raise ConfigError("sdf.aa_radius_hr_px must be greater than 0.0.")

    stabilizer_config = config.get("line_stabilizer", {})
    enabled = stabilizer_config.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("line_stabilizer.enabled must be a boolean.")
    if line_renderer == "potrace" and enabled:
        raise ConfigError(
            "line_stabilizer.enabled must be false when pipeline.line_renderer is potrace."
        )

    for key in (
        "strength",
        "min_coverage",
        "min_length_source_px",
        "max_rms_error_source_px",
        "min_density",
        "max_gap_source_px",
        "angle_step_degrees",
        "rho_tolerance_source_px",
        "min_width_source_px",
        "max_width_source_px",
        "width_scale",
        "band_margin_hr_px",
    ):
        value = stabilizer_config.get(key)
        if not isinstance(value, int | float) or float(value) < 0.0:
            raise ConfigError(f"line_stabilizer.{key} must be a non-negative number.")

    for key in ("max_segments", "max_candidates_per_angle"):
        value = stabilizer_config.get(key)
        if not isinstance(value, int) or value <= 0:
            raise ConfigError(f"line_stabilizer.{key} must be a positive integer.")

    support_dilate = stabilizer_config.get("support_dilate_hr_px")
    if not isinstance(support_dilate, int) or support_dilate < 0:
        raise ConfigError("line_stabilizer.support_dilate_hr_px must be a non-negative integer.")

    smoothing_config = config.get("directional_smoothing", {})
    smoothing_enabled = smoothing_config.get("enabled", False)
    if not isinstance(smoothing_enabled, bool):
        raise ConfigError("directional_smoothing.enabled must be a boolean.")
    for key in (
        "strength",
        "min_orientation_confidence",
        "min_alpha",
        "max_delta",
    ):
        value = smoothing_config.get(key)
        if not isinstance(value, int | float) or not 0.0 <= float(value) <= 1.0:
            raise ConfigError(f"directional_smoothing.{key} must be between 0.0 and 1.0.")
    for key in (
        "orientation_sigma_hr_px",
        "tensor_sigma_hr_px",
        "min_gradient_energy",
    ):
        value = smoothing_config.get(key)
        if not isinstance(value, int | float) or float(value) <= 0.0:
            raise ConfigError(f"directional_smoothing.{key} must be greater than 0.0.")
    min_axis = smoothing_config.get("min_angle_from_axis_degrees")
    if not isinstance(min_axis, int | float) or not 0.0 <= float(min_axis) < 45.0:
        raise ConfigError(
            "directional_smoothing.min_angle_from_axis_degrees must be in [0.0, 45.0)."
        )
    full_axis = smoothing_config.get("full_strength_angle_from_axis_degrees")
    if (
        not isinstance(full_axis, int | float)
        or not float(min_axis) < float(full_axis) <= 45.0
    ):
        raise ConfigError(
            "directional_smoothing.full_strength_angle_from_axis_degrees must be greater than "
            "min_angle_from_axis_degrees and at most 45.0."
        )
    radius = smoothing_config.get("radius_hr_px")
    if not isinstance(radius, int) or radius < 0:
        raise ConfigError("directional_smoothing.radius_hr_px must be a non-negative integer.")
    smoothing_support_dilate = smoothing_config.get("support_dilate_hr_px")
    if not isinstance(smoothing_support_dilate, int) or smoothing_support_dilate < 0:
        raise ConfigError(
            "directional_smoothing.support_dilate_hr_px must be a non-negative integer."
        )

    simplification_config = config.get("centerline_simplification", {})
    simplification_enabled = simplification_config.get("enabled", False)
    if not isinstance(simplification_enabled, bool):
        raise ConfigError("centerline_simplification.enabled must be a boolean.")
    if line_renderer == "potrace" and simplification_enabled:
        raise ConfigError(
            "centerline_simplification.enabled must be false when "
            "pipeline.line_renderer is potrace."
        )
    for key in (
        "filter_sigma_source_px",
        "min_path_length_source_px",
        "endpoint_protection_source_px",
        "max_radius_source_px",
        "support_margin_source_px",
    ):
        value = simplification_config.get(key)
        if not isinstance(value, int | float) or float(value) < 0.0:
            raise ConfigError(
                f"centerline_simplification.{key} must be a non-negative number."
            )
    for key in (
        "filter_sample_step_source_px",
        "max_filter_displacement_source_px",
    ):
        value = simplification_config.get(key)
        if not isinstance(value, int | float) or float(value) <= 0.0:
            raise ConfigError(
                f"centerline_simplification.{key} must be greater than 0.0."
            )
    simplification_strength = simplification_config.get("strength")
    if (
        not isinstance(simplification_strength, int | float)
        or not 0.0 <= float(simplification_strength) <= 1.0
    ):
        raise ConfigError("centerline_simplification.strength must be between 0.0 and 1.0.")
    binarize_output = simplification_config.get("binarize_output")
    if not isinstance(binarize_output, bool):
        raise ConfigError("centerline_simplification.binarize_output must be a boolean.")
    binary_threshold = simplification_config.get("binary_threshold")
    if (
        not isinstance(binary_threshold, int | float)
        or not 0.0 < float(binary_threshold) < 1.0
    ):
        raise ConfigError(
            "centerline_simplification.binary_threshold must be between 0.0 and 1.0."
        )
    alpha_threshold = simplification_config.get("alpha_threshold")
    if (
        not isinstance(alpha_threshold, int | float)
        or not 0.0 < float(alpha_threshold) <= 1.0
    ):
        raise ConfigError(
            "centerline_simplification.alpha_threshold must be in (0.0, 1.0]."
        )
    max_thinning_iterations = simplification_config.get("max_thinning_iterations")
    if not isinstance(max_thinning_iterations, int) or max_thinning_iterations <= 0:
        raise ConfigError(
            "centerline_simplification.max_thinning_iterations must be a positive integer."
        )
    max_new_component_area = simplification_config.get("max_new_component_area")
    if not isinstance(max_new_component_area, int) or max_new_component_area < 0:
        raise ConfigError(
            "centerline_simplification.max_new_component_area must be a non-negative integer."
        )
    corner_angle_degrees = simplification_config.get("corner_angle_degrees")
    if (
        not isinstance(corner_angle_degrees, int | float)
        or not 0.0 < float(corner_angle_degrees) < 180.0
    ):
        raise ConfigError(
            "centerline_simplification.corner_angle_degrees must be between 0.0 and 180.0."
        )
    corner_window_source_px = simplification_config.get("corner_window_source_px")
    if (
        not isinstance(corner_window_source_px, int | float)
        or float(corner_window_source_px) <= 0.0
    ):
        raise ConfigError(
            "centerline_simplification.corner_window_source_px must be greater than 0.0."
        )
    geometry_strength = simplification_config.get("geometry_strength")
    if (
        not isinstance(geometry_strength, int | float)
        or not 0.0 <= float(geometry_strength) <= 1.0
    ):
        raise ConfigError(
            "centerline_simplification.geometry_strength must be between 0.0 and 1.0."
        )
    long_stroke_gate = simplification_config.get("long_stroke_gate", {})
    gate_enabled = long_stroke_gate.get("enabled", True)
    if not isinstance(gate_enabled, bool):
        raise ConfigError(
            "centerline_simplification.long_stroke_gate.enabled must be a boolean."
        )
    skip_paths_with_corners = long_stroke_gate.get("skip_paths_with_corners", True)
    if not isinstance(skip_paths_with_corners, bool):
        raise ConfigError(
            "centerline_simplification.long_stroke_gate.skip_paths_with_corners "
            "must be a boolean."
        )
    min_chord_arc_ratio = long_stroke_gate.get("min_chord_arc_ratio")
    if (
        not isinstance(min_chord_arc_ratio, int | float)
        or not 0.0 <= float(min_chord_arc_ratio) <= 1.0
    ):
        raise ConfigError(
            "centerline_simplification.long_stroke_gate.min_chord_arc_ratio "
            "must be between 0.0 and 1.0."
        )
    for key in (
        "max_line_fit_rms_source_px",
        "max_line_fit_deviation_source_px",
        "max_width_cv",
    ):
        value = long_stroke_gate.get(key)
        if not isinstance(value, int | float) or float(value) < 0.0:
            raise ConfigError(
                f"centerline_simplification.long_stroke_gate.{key} "
                "must be a non-negative number."
            )
    max_width_ratio = long_stroke_gate.get("max_width_ratio")
    if not isinstance(max_width_ratio, int | float) or float(max_width_ratio) < 1.0:
        raise ConfigError(
            "centerline_simplification.long_stroke_gate.max_width_ratio "
            "must be at least 1.0."
        )
    component_rollback = simplification_config.get("component_rollback", {})
    rollback_enabled = component_rollback.get("enabled", True)
    if not isinstance(rollback_enabled, bool):
        raise ConfigError(
            "centerline_simplification.component_rollback.enabled must be a boolean."
        )
    preserve_component_count = component_rollback.get(
        "preserve_component_count",
        True,
    )
    if not isinstance(preserve_component_count, bool):
        raise ConfigError(
            "centerline_simplification.component_rollback.preserve_component_count "
            "must be a boolean."
        )
    min_ink_ratio = component_rollback.get("min_ink_ratio")
    if (
        not isinstance(min_ink_ratio, int | float)
        or not 0.0 < float(min_ink_ratio) <= 1.0
    ):
        raise ConfigError(
            "centerline_simplification.component_rollback.min_ink_ratio "
            "must be in (0.0, 1.0]."
        )
    max_ink_ratio = component_rollback.get("max_ink_ratio")
    if not isinstance(max_ink_ratio, int | float) or float(max_ink_ratio) < 1.0:
        raise ConfigError(
            "centerline_simplification.component_rollback.max_ink_ratio "
            "must be at least 1.0."
        )
    potrace_config = config.get("potrace", {})
    turdsize = potrace_config.get("turdsize", 2)
    if not isinstance(turdsize, int) or turdsize < 0:
        raise ConfigError("potrace.turdsize must be a non-negative integer.")
    for key in ("alphamax", "opttolerance"):
        value = potrace_config.get(key)
        if not isinstance(value, int | float) or float(value) < 0.0:
            raise ConfigError(f"potrace.{key} must be a non-negative number.")
    opticurve = potrace_config.get("opticurve", True)
    if not isinstance(opticurve, bool):
        raise ConfigError("potrace.opticurve must be a boolean.")
    turnpolicy = potrace_config.get("turnpolicy", "minority")
    if turnpolicy not in {"black", "white", "left", "right", "minority", "majority"}:
        raise ConfigError(
            "potrace.turnpolicy must be one of: black, white, left, right, minority, majority."
        )
    rasterizer = potrace_config.get("rasterizer", "cairosvg")
    if rasterizer not in {"cairosvg", "inkscape"}:
        raise ConfigError("potrace.rasterizer must be one of: cairosvg, inkscape.")

    tone_config = config.get("tone_source", {})
    tone_mode = tone_config.get("mode")
    if tone_mode not in {"white_canvas", "passthrough", "lift_lines"}:
        raise ConfigError(
            "tone_source.mode must be one of: white_canvas, passthrough, lift_lines."
        )
    for key in ("dilate_radius", "background_blur_radius"):
        value = tone_config.get(key)
        if not isinstance(value, int | float) or float(value) < 0.0:
            raise ConfigError(f"tone_source.{key} must be a non-negative number.")
    lift_strength = tone_config.get("lift_strength")
    if not isinstance(lift_strength, int | float) or not 0.0 <= float(lift_strength) <= 1.0:
        raise ConfigError("tone_source.lift_strength must be between 0.0 and 1.0.")
    protect_midtones = tone_config.get("protect_midtones")
    if not isinstance(protect_midtones, bool):
        raise ConfigError("tone_source.protect_midtones must be a boolean.")

    composite_config = config.get("composite", {})
    tone_usage = composite_config.get("tone_usage", "auto")
    if tone_usage not in {"auto", "always", "never"}:
        raise ConfigError("composite.tone_usage must be one of: auto, always, never.")

    upscaler_config = config.get("upscaler", {})
    engine = upscaler_config.get("engine")
    if engine not in {"none", "lanczos", "realcugan", "waifu2x", "realesrgan"}:
        raise ConfigError(
            "upscaler.engine must be one of: none, lanczos, realcugan, waifu2x, realesrgan."
        )
    fallback = upscaler_config.get("fallback", "none")
    if fallback not in {"none", "lanczos"}:
        raise ConfigError("upscaler.fallback must be one of: none, lanczos.")

    for engine_name in ("realcugan", "waifu2x", "realesrgan"):
        engine_config = upscaler_config.get(engine_name, {})
        tile_size = engine_config.get("tile_size", 256)
        if not isinstance(tile_size, int) or tile_size <= 0:
            raise ConfigError(f"upscaler.{engine_name}.tile_size must be a positive integer.")
    for engine_name in ("realcugan", "waifu2x"):
        noise = upscaler_config.get(engine_name, {}).get("noise", -1)
        if not isinstance(noise, int):
            raise ConfigError(f"upscaler.{engine_name}.noise must be an integer.")
    for engine_name in ("waifu2x", "realesrgan"):
        model = upscaler_config.get(engine_name, {}).get("model", "")
        if not isinstance(model, str) or not model:
            raise ConfigError(f"upscaler.{engine_name}.model must be a non-empty string.")

    external_tools = config.get("external_tools", {})
    for key in ("realcugan", "waifu2x", "realesrgan", "potrace", "cairosvg", "inkscape"):
        value = external_tools.get(key)
        if value is not None and not isinstance(value, str):
            raise ConfigError(f"external_tools.{key} must be null or a path string.")
