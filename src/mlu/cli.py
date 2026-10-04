"""Command line interface skeleton for the manga line-art upscaler."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path

from mlu import __version__
from mlu.batch import DEFAULT_EXTENSIONS, BatchResult, parse_extensions, run_batch
from mlu.compare import CompareResult, run_compare
from mlu.config import ConfigError, load_config
from mlu.pipeline import inspect_image, upscale_image
from mlu.potrace_render import TOOL_EXECUTABLE_NAMES, resolve_renderer_tool
from mlu.scales import SUPPORTED_SCALES
from mlu.upscaler_external import (
    EXECUTABLE_NAMES,
    ExternalUpscalerError,
    ToolNotFoundError,
    resolve_tool_path,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""

    parser = argparse.ArgumentParser(
        prog="mlu",
        description="Local line-art upscaler for white-background manga images.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="command")

    upscale = subparsers.add_parser("upscale", help="Upscale a single line-art image.")
    upscale.add_argument("input", help="Input image path.")
    upscale.add_argument("-o", "--output", required=True, help="Output PNG or PSD path.")
    upscale.add_argument("--scale", type=int, choices=SUPPORTED_SCALES, default=4)
    upscale.add_argument("--preset", default="line_only")
    upscale.add_argument("--config", help="YAML config path.")
    upscale.add_argument("--debug-dir", help="Directory for debug layers.")
    upscale.add_argument(
        "--save-run-json",
        action="store_true",
        help="Write a debug JSON sidecar containing the effective parameters.",
    )
    upscale.add_argument("--line-renderer", choices=("sdf", "potrace"), help="Line renderer.")
    upscale.add_argument("--invert", action="store_true", help="Treat input as inverted.")
    upscale.add_argument("--overwrite", action="store_true", help="Overwrite existing output.")
    upscale.add_argument(
        "--output-bit-depth",
        type=int,
        choices=(8, 16),
        help="Output PNG or PSD depth.",
    )
    upscale.add_argument(
        "--upscaler",
        choices=("none", "lanczos", "realcugan", "waifu2x", "realesrgan"),
        help="Tone-source upscaler engine.",
    )
    upscale.add_argument(
        "--upscaler-fallback",
        choices=("none", "lanczos"),
        help="Fallback if an external tone upscaler is unavailable or fails.",
    )
    upscale.add_argument(
        "--tone-usage",
        choices=("auto", "always", "never"),
        help="Whether tone_hr is used as the final composite base.",
    )
    upscale.add_argument(
        "--grayscale-mode",
        choices=("legacy", "line_only", "separate", "composite"),
        help="Experimental grayscale handling and output mode.",
    )
    upscale.add_argument(
        "--separate-output-format",
        choices=("png", "psd"),
        help="Output format used when --grayscale-mode=separate.",
    )
    upscale.add_argument(
        "--sdf-distance-source",
        choices=("binary_mask", "soft_mask_hr"),
        help="Distance source for SDF line rendering.",
    )
    upscale.add_argument(
        "--soft-sdf-threshold",
        type=float,
        help="Soft coverage threshold used when --sdf-distance-source=soft_mask_hr.",
    )
    upscale.add_argument("--width-bias-source-px", type=float, help="Line width bias in source px.")
    upscale.add_argument("--aa-radius-hr-px", type=float, help="AA radius in high-resolution px.")
    upscale.add_argument(
        "--line-soft-coverage-mode",
        choices=("darkness", "line_probability", "max_probability"),
        help="Coverage source for line_soft.",
    )
    upscale.add_argument(
        "--line-soft-coverage-gamma",
        type=float,
        help="Gamma applied to line_soft coverage.",
    )
    upscale.add_argument(
        "--enable-line-stabilizer",
        action="store_true",
        help="Enable experimental straight-line stabilization.",
    )
    upscale.add_argument(
        "--disable-line-stabilizer",
        action="store_true",
        help="Disable straight-line stabilization.",
    )
    upscale.add_argument(
        "--line-stabilizer-strength",
        type=float,
        help="Straight-line stabilization blend strength.",
    )

    inspect = subparsers.add_parser("inspect", help="Inspect line mask extraction.")
    inspect.add_argument("input", help="Input image path.")
    inspect.add_argument("--preset", default="line_only")
    inspect.add_argument("--config", help="YAML config path.")
    inspect.add_argument("--debug-dir", required=True, help="Directory for debug layers.")
    inspect.add_argument("--line-renderer", choices=("sdf", "potrace"), help="Line renderer.")
    inspect.add_argument("--invert", action="store_true", help="Treat input as inverted.")
    inspect.add_argument(
        "--upscaler",
        choices=("none", "lanczos", "realcugan", "waifu2x", "realesrgan"),
        help="Tone-source upscaler engine.",
    )
    inspect.add_argument(
        "--upscaler-fallback",
        choices=("none", "lanczos"),
        help="Fallback if an external tone upscaler is unavailable or fails.",
    )
    inspect.add_argument(
        "--tone-usage",
        choices=("auto", "always", "never"),
        help="Whether tone_hr is used as the final composite base.",
    )
    inspect.add_argument(
        "--grayscale-mode",
        choices=("legacy", "line_only", "separate", "composite"),
        help="Experimental grayscale handling and output mode.",
    )
    inspect.add_argument(
        "--sdf-distance-source",
        choices=("binary_mask", "soft_mask_hr"),
        help="Distance source for SDF line rendering.",
    )
    inspect.add_argument(
        "--soft-sdf-threshold",
        type=float,
        help="Soft coverage threshold used when --sdf-distance-source=soft_mask_hr.",
    )
    inspect.add_argument("--width-bias-source-px", type=float, help="Line width bias in source px.")
    inspect.add_argument("--aa-radius-hr-px", type=float, help="AA radius in high-resolution px.")
    inspect.add_argument(
        "--line-soft-coverage-mode",
        choices=("darkness", "line_probability", "max_probability"),
        help="Coverage source for line_soft.",
    )
    inspect.add_argument(
        "--line-soft-coverage-gamma",
        type=float,
        help="Gamma applied to line_soft coverage.",
    )
    inspect.add_argument(
        "--enable-line-stabilizer",
        action="store_true",
        help="Enable experimental straight-line stabilization.",
    )
    inspect.add_argument(
        "--disable-line-stabilizer",
        action="store_true",
        help="Disable straight-line stabilization.",
    )
    inspect.add_argument(
        "--line-stabilizer-strength",
        type=float,
        help="Straight-line stabilization blend strength.",
    )

    batch = subparsers.add_parser("batch", help="Upscale all supported images in a directory.")
    batch.add_argument("input_dir", help="Input image directory.")
    batch.add_argument("output_dir", help="Output directory.")
    batch.add_argument("--scale", type=int, choices=SUPPORTED_SCALES, default=4)
    batch.add_argument("--preset", default="line_only")
    batch.add_argument("--config", help="YAML config path.")
    batch.add_argument("--line-renderer", choices=("sdf", "potrace"), help="Line renderer.")
    batch.add_argument(
        "--extensions",
        default=",".join(DEFAULT_EXTENSIONS),
        help="Comma-separated input extensions. Default: png,jpg,jpeg,tif,tiff.",
    )
    batch.add_argument("--workers", type=int, default=1, help="Worker count. Only 1 is supported.")
    batch.add_argument("--debug-dir", help="Base directory for per-image debug layers.")
    batch.add_argument(
        "--save-run-json",
        action="store_true",
        help="Write a debug JSON sidecar for each output image.",
    )
    batch.add_argument(
        "--summary-json",
        help="Summary JSON path. Defaults to output_dir/summary.json.",
    )
    batch.add_argument(
        "--summary-csv",
        help="Summary CSV path. Defaults to output_dir/summary.csv.",
    )
    batch.add_argument("--invert", action="store_true", help="Treat inputs as inverted.")
    batch.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs.")
    batch.add_argument(
        "--output-bit-depth",
        type=int,
        choices=(8, 16),
        help="Output PNG or PSD depth.",
    )
    batch.add_argument(
        "--upscaler",
        choices=("none", "lanczos", "realcugan", "waifu2x", "realesrgan"),
        help="Tone-source upscaler engine.",
    )
    batch.add_argument(
        "--upscaler-fallback",
        choices=("none", "lanczos"),
        help="Fallback if an external tone upscaler is unavailable or fails.",
    )
    batch.add_argument(
        "--tone-usage",
        choices=("auto", "always", "never"),
        help="Whether tone_hr is used as the final composite base.",
    )
    batch.add_argument(
        "--grayscale-mode",
        choices=("legacy", "line_only", "separate", "composite"),
        help="Experimental grayscale handling and output mode.",
    )
    batch.add_argument(
        "--separate-output-format",
        choices=("png", "psd"),
        help="Output format used when --grayscale-mode=separate.",
    )
    batch.add_argument(
        "--sdf-distance-source",
        choices=("binary_mask", "soft_mask_hr"),
        help="Distance source for SDF line rendering.",
    )
    batch.add_argument(
        "--soft-sdf-threshold",
        type=float,
        help="Soft coverage threshold used when --sdf-distance-source=soft_mask_hr.",
    )
    batch.add_argument("--width-bias-source-px", type=float, help="Line width bias in source px.")
    batch.add_argument("--aa-radius-hr-px", type=float, help="AA radius in high-resolution px.")
    batch.add_argument(
        "--line-soft-coverage-mode",
        choices=("darkness", "line_probability", "max_probability"),
        help="Coverage source for line_soft.",
    )
    batch.add_argument(
        "--line-soft-coverage-gamma",
        type=float,
        help="Gamma applied to line_soft coverage.",
    )
    batch.add_argument(
        "--enable-line-stabilizer",
        action="store_true",
        help="Enable experimental straight-line stabilization.",
    )
    batch.add_argument(
        "--disable-line-stabilizer",
        action="store_true",
        help="Disable straight-line stabilization.",
    )
    batch.add_argument(
        "--line-stabilizer-strength",
        type=float,
        help="Straight-line stabilization blend strength.",
    )

    compare = subparsers.add_parser(
        "compare",
        help="Run a parameter grid and build comparison sheets.",
    )
    compare.add_argument("input", help="Input image path.")
    compare.add_argument("-o", "--output-dir", required=True, help="Comparison output directory.")
    compare.add_argument("--grid", required=True, help="YAML grid file.")
    compare.add_argument("--scale", type=int, choices=SUPPORTED_SCALES, default=4)
    compare.add_argument("--preset", default="line_only")
    compare.add_argument("--config", help="YAML config path.")
    compare.add_argument("--debug-dir", help="Base directory for per-variant debug layers.")
    compare.add_argument("--line-renderer", choices=("sdf", "potrace"), help="Line renderer.")
    compare.add_argument("--invert", action="store_true", help="Treat input as inverted.")
    compare.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs.")
    compare.add_argument("--output-bit-depth", type=int, choices=(8, 16), help="Output PNG depth.")
    compare.add_argument("--thumbnail-width", type=int, default=420)
    compare.add_argument("--crop-source-size", type=int, default=256)
    compare.add_argument(
        "--upscaler",
        choices=("none", "lanczos", "realcugan", "waifu2x", "realesrgan"),
        help="Tone-source upscaler engine.",
    )
    compare.add_argument(
        "--upscaler-fallback",
        choices=("none", "lanczos"),
        help="Fallback if an external tone upscaler is unavailable or fails.",
    )
    compare.add_argument(
        "--tone-usage",
        choices=("auto", "always", "never"),
        help="Whether tone_hr is used as the final composite base.",
    )
    compare.add_argument(
        "--grayscale-mode",
        choices=("legacy", "line_only", "separate", "composite"),
        help="Experimental grayscale handling and output mode.",
    )
    compare.add_argument(
        "--sdf-distance-source",
        choices=("binary_mask", "soft_mask_hr"),
        help="Distance source for SDF line rendering.",
    )
    compare.add_argument(
        "--soft-sdf-threshold",
        type=float,
        help="Soft coverage threshold used when --sdf-distance-source=soft_mask_hr.",
    )
    compare.add_argument("--width-bias-source-px", type=float, help="Line width bias in source px.")
    compare.add_argument("--aa-radius-hr-px", type=float, help="AA radius in high-resolution px.")
    compare.add_argument(
        "--line-soft-coverage-mode",
        choices=("darkness", "line_probability", "max_probability"),
        help="Coverage source for line_soft.",
    )
    compare.add_argument(
        "--line-soft-coverage-gamma",
        type=float,
        help="Gamma applied to line_soft coverage.",
    )
    compare.add_argument(
        "--enable-line-stabilizer",
        action="store_true",
        help="Enable experimental straight-line stabilization.",
    )
    compare.add_argument(
        "--disable-line-stabilizer",
        action="store_true",
        help="Disable straight-line stabilization.",
    )
    compare.add_argument(
        "--line-stabilizer-strength",
        type=float,
        help="Straight-line stabilization blend strength.",
    )

    for command_parser in (upscale, inspect, batch, compare):
        _add_directional_smoothing_args(command_parser)

    doctor = subparsers.add_parser("doctor", help="Check the local development environment.")
    doctor.add_argument("--config", help="YAML config path.")

    return parser


def _add_directional_smoothing_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--enable-directional-smoothing",
        action="store_true",
        help="Enable directional smoothing for non-axis-aligned SDF lines.",
    )
    parser.add_argument(
        "--disable-directional-smoothing",
        action="store_true",
        help="Disable directional smoothing for non-axis-aligned SDF lines.",
    )
    parser.add_argument(
        "--directional-smoothing-strength",
        type=float,
        help="Directional smoothing blend strength.",
    )
    parser.add_argument(
        "--directional-smoothing-radius-hr-px",
        type=int,
        help="Directional smoothing radius in high-resolution px.",
    )
    parser.add_argument(
        "--directional-smoothing-min-angle-from-axis-degrees",
        type=float,
        help="Angle away from horizontal/vertical where directional smoothing starts.",
    )
    parser.add_argument(
        "--directional-smoothing-full-strength-angle-from-axis-degrees",
        type=float,
        help=(
            "Angle away from horizontal/vertical where directional smoothing reaches "
            "full strength."
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    try:
        if args.command == "doctor":
            _run_doctor(args)
            return 0

        if args.command == "upscale":
            _run_upscale(args)
            return 0

        if args.command == "inspect":
            _run_inspect(args)
            return 0

        if args.command == "batch":
            result = _run_batch(args)
            return 0 if result.failed_count == 0 else 1

        if args.command == "compare":
            _run_compare(args)
            return 0
    except (
        ConfigError,
        ExternalUpscalerError,
        FileExistsError,
        ToolNotFoundError,
        ValueError,
    ) as exc:
        parser.exit(1, f"mlu: error: {exc}\n")

    parser.error(f"Unknown command: {args.command}")
    return 2


def _config_overrides(args: argparse.Namespace) -> dict[str, object]:
    overrides: dict[str, object] = {
        "io": {
            "overwrite": getattr(args, "overwrite", False),
        },
    }
    pipeline_overrides: dict[str, object] = {}
    if hasattr(args, "scale"):
        pipeline_overrides["scale"] = args.scale
    line_renderer = getattr(args, "line_renderer", None)
    if line_renderer is not None:
        pipeline_overrides["line_renderer"] = line_renderer
    if pipeline_overrides:
        overrides["pipeline"] = pipeline_overrides
    output_bit_depth = getattr(args, "output_bit_depth", None)
    if output_bit_depth is not None:
        overrides["io"] = {
            "overwrite": args.overwrite,
            "output_bit_depth": output_bit_depth,
        }
    sdf_overrides: dict[str, object] = {}
    if args.sdf_distance_source is not None:
        sdf_overrides["distance_source"] = args.sdf_distance_source
    if args.soft_sdf_threshold is not None:
        sdf_overrides["soft_sdf_threshold"] = args.soft_sdf_threshold
    if args.width_bias_source_px is not None:
        sdf_overrides["width_bias_source_px"] = args.width_bias_source_px
    if args.aa_radius_hr_px is not None:
        sdf_overrides["aa_radius_hr_px"] = args.aa_radius_hr_px
    if sdf_overrides:
        overrides["sdf"] = sdf_overrides
    mask_overrides: dict[str, object] = {}
    soft_coverage_overrides: dict[str, object] = {}
    coverage_mode = getattr(args, "line_soft_coverage_mode", None)
    if coverage_mode is not None:
        soft_coverage_overrides["mode"] = coverage_mode
    coverage_gamma = getattr(args, "line_soft_coverage_gamma", None)
    if coverage_gamma is not None:
        soft_coverage_overrides["gamma"] = coverage_gamma
    if soft_coverage_overrides:
        mask_overrides["soft_coverage"] = soft_coverage_overrides
    if mask_overrides:
        overrides["mask"] = mask_overrides
    upscaler_overrides: dict[str, object] = {}
    upscaler = getattr(args, "upscaler", None)
    if upscaler is not None:
        upscaler_overrides["engine"] = upscaler
    fallback = getattr(args, "upscaler_fallback", None)
    if fallback is not None:
        upscaler_overrides["fallback"] = fallback
    if upscaler_overrides:
        overrides["upscaler"] = upscaler_overrides
    composite_overrides: dict[str, object] = {}
    tone_usage = getattr(args, "tone_usage", None)
    if tone_usage is not None:
        composite_overrides["tone_usage"] = tone_usage
    if composite_overrides:
        overrides["composite"] = composite_overrides
    grayscale_overrides: dict[str, object] = {}
    grayscale_mode = getattr(args, "grayscale_mode", None)
    if grayscale_mode is not None:
        grayscale_overrides["mode"] = grayscale_mode
    separate_output_format = getattr(args, "separate_output_format", None)
    if separate_output_format is not None:
        grayscale_overrides["separate_output_format"] = separate_output_format
    if grayscale_overrides:
        overrides["grayscale_processing"] = grayscale_overrides
    line_stabilizer_overrides: dict[str, object] = {}
    strength = getattr(args, "line_stabilizer_strength", None)
    if getattr(args, "disable_line_stabilizer", False):
        line_stabilizer_overrides["enabled"] = False
    elif getattr(args, "enable_line_stabilizer", False):
        line_stabilizer_overrides["enabled"] = True
    if strength is not None:
        line_stabilizer_overrides["strength"] = strength
    if line_stabilizer_overrides:
        overrides["line_stabilizer"] = line_stabilizer_overrides
    directional_smoothing_overrides: dict[str, object] = {}
    if getattr(args, "disable_directional_smoothing", False):
        directional_smoothing_overrides["enabled"] = False
    elif getattr(args, "enable_directional_smoothing", False):
        directional_smoothing_overrides["enabled"] = True
    smoothing_strength = getattr(args, "directional_smoothing_strength", None)
    if smoothing_strength is not None:
        directional_smoothing_overrides["strength"] = smoothing_strength
    smoothing_radius = getattr(args, "directional_smoothing_radius_hr_px", None)
    if smoothing_radius is not None:
        directional_smoothing_overrides["radius_hr_px"] = smoothing_radius
    smoothing_min_axis = getattr(
        args,
        "directional_smoothing_min_angle_from_axis_degrees",
        None,
    )
    if smoothing_min_axis is not None:
        directional_smoothing_overrides["min_angle_from_axis_degrees"] = smoothing_min_axis
    smoothing_full_axis = getattr(
        args,
        "directional_smoothing_full_strength_angle_from_axis_degrees",
        None,
    )
    if smoothing_full_axis is not None:
        directional_smoothing_overrides["full_strength_angle_from_axis_degrees"] = (
            smoothing_full_axis
        )
    if directional_smoothing_overrides:
        overrides["directional_smoothing"] = directional_smoothing_overrides
    if getattr(args, "save_run_json", False):
        overrides["debug"] = {"save_run_json": True}
    return overrides


def _run_upscale(args: argparse.Namespace) -> None:
    config = load_config(
        preset=args.preset,
        config_path=args.config,
        cli_overrides=_config_overrides(args),
    )
    result = upscale_image(
        args.input,
        args.output,
        config,
        invert=args.invert,
        debug_dir=args.debug_dir,
        preset=args.preset,
    )
    image = result.input_image
    print(f"Input: {Path(args.input)} {image.array.shape[1]}x{image.array.shape[0]}")
    print(
        "Scale: "
        f"{config['pipeline']['scale']}x -> "
        f"{result.final.shape[1]}x{result.final.shape[0]}"
    )
    print(f"Line mask: {result.line_maps.mask_area_ratio * 100:.2f}%")
    print(f"Grayscale mode: {config['grayscale_processing']['mode']}")
    print(
        "Line renderer: "
        f"{config['pipeline']['line_renderer']} "
        f"sdf source={config['sdf']['distance_source']} "
        f"threshold={config['sdf']['soft_sdf_threshold']} "
        f"aa={config['sdf']['aa_radius_hr_px']} "
        f"width_bias={config['sdf']['width_bias_source_px']} source px "
        f"soft={config['sdf']['soft_alpha_mode']}:{config['sdf']['soft_gain']}"
    )
    if config.get("line_stabilizer", {}).get("enabled", False):
        print(f"Line stabilizer: {len(result.sdf_result.line_segments)} segments")
    smoothing_stats = result.sdf_result.directional_smoothing_stats or {}
    print(
        "Directional smoothing: "
        f"enabled={config['directional_smoothing']['enabled']} "
        f"applied={smoothing_stats.get('applied', False)} "
        f"strength={config['directional_smoothing']['strength']} "
        f"radius={config['directional_smoothing']['radius_hr_px']}hrpx"
    )
    _print_upscaler_result(result)
    for warning in result.line_maps.warnings:
        print(f"Warning: {warning}")
    print(f"Output: {Path(args.output)}")
    if result.tone_output_path is not None:
        print(f"Tone layer: {result.tone_output_path}")
    if result.run_json_path is not None:
        print(f"Run JSON: {result.run_json_path}")
    if args.debug_dir:
        print(f"Debug: {Path(args.debug_dir)}")


def _run_inspect(args: argparse.Namespace) -> None:
    config = load_config(
        preset=args.preset,
        config_path=args.config,
        cli_overrides=_config_overrides(args),
    )
    result = inspect_image(
        args.input,
        config,
        invert=args.invert,
        debug_dir=args.debug_dir,
        preset=args.preset,
    )
    image = result.input_image
    print(f"Input: {Path(args.input)} {image.array.shape[1]}x{image.array.shape[0]}")
    print(f"Preset: {args.preset} scale={config['pipeline']['scale']}")
    print(f"Line mask: {result.line_maps.mask_area_ratio * 100:.2f}%")
    print(
        "Line alpha: "
        f"{result.sdf_result.line_alpha_hr.shape[1]}x{result.sdf_result.line_alpha_hr.shape[0]}"
    )
    print(
        "Line renderer: "
        f"{config['pipeline']['line_renderer']} "
        f"sdf source={config['sdf']['distance_source']} "
        f"threshold={config['sdf']['soft_sdf_threshold']} "
        f"aa={config['sdf']['aa_radius_hr_px']} "
        f"width_bias={config['sdf']['width_bias_source_px']} source px "
        f"soft={config['sdf']['soft_alpha_mode']}:{config['sdf']['soft_gain']}"
    )
    if config.get("line_stabilizer", {}).get("enabled", False):
        print(f"Line stabilizer: {len(result.sdf_result.line_segments)} segments")
    smoothing_stats = result.sdf_result.directional_smoothing_stats or {}
    print(
        "Directional smoothing: "
        f"enabled={config['directional_smoothing']['enabled']} "
        f"applied={smoothing_stats.get('applied', False)} "
        f"strength={config['directional_smoothing']['strength']} "
        f"radius={config['directional_smoothing']['radius_hr_px']}hrpx"
    )
    _print_upscaler_result(result)
    for warning in result.line_maps.warnings:
        print(f"Warning: {warning}")
    print(f"Debug: {Path(args.debug_dir)}")
    if result.run_json_path is not None:
        print(f"Run JSON: {result.run_json_path}")


def _run_batch(args: argparse.Namespace) -> BatchResult:
    config = load_config(
        preset=args.preset,
        config_path=args.config,
        cli_overrides=_config_overrides(args),
    )
    result = run_batch(
        args.input_dir,
        args.output_dir,
        config,
        preset=args.preset,
        invert=args.invert,
        debug_dir=args.debug_dir,
        extensions=parse_extensions(args.extensions),
        workers=args.workers,
        summary_json=args.summary_json,
        summary_csv=args.summary_csv,
    )
    print(
        "Batch: "
        f"{result.succeeded_count}/{result.total_count} succeeded, "
        f"{result.failed_count} failed"
    )
    for index, item in enumerate(result.items, start=1):
        if item.status == "ok":
            print(f"[{index}/{result.total_count}] OK {item.input_path} -> {item.output_path}")
        else:
            print(f"[{index}/{result.total_count}] FAILED {item.input_path}: {item.error}")
    print(f"Summary JSON: {result.summary_json_path}")
    print(f"Summary CSV: {result.summary_csv_path}")
    return result


def _run_compare(args: argparse.Namespace) -> CompareResult:
    config = load_config(
        preset=args.preset,
        config_path=args.config,
        cli_overrides=_config_overrides(args),
    )
    result = run_compare(
        args.input,
        args.output_dir,
        config,
        preset=args.preset,
        grid_path=args.grid,
        invert=args.invert,
        debug_dir=args.debug_dir,
        thumbnail_width=args.thumbnail_width,
        crop_source_size=args.crop_source_size,
    )
    print(f"Compare: {len(result.items)} variants")
    for index, item in enumerate(result.items, start=1):
        print(f"[{index}/{len(result.items)}] {item.variant.name} -> {item.output_path}")
    print(f"Contact sheet: {result.contact_sheet_path}")
    print(f"Center crop 1x: {result.center_crop_1x_path}")
    print(f"Center crop 200%: {result.center_crop_200_path}")
    print(f"Summary JSON: {result.summary_json_path}")
    return result


def _print_upscaler_result(result) -> None:
    upscaler = result.upscaler_result
    if upscaler.engine == "none" and upscaler.requested_engine == "none":
        return
    if upscaler.engine == "none":
        print(f"Tone upscaler: skipped (requested {upscaler.requested_engine})")
    else:
        fallback = " via fallback" if upscaler.used_fallback else ""
        print(f"Tone upscaler: {upscaler.engine}{fallback}")
    if upscaler.error:
        print(f"Tone upscaler note: {upscaler.error}")


def _run_doctor(args: argparse.Namespace) -> None:
    config = load_config(config_path=args.config)
    print(f"mlu: {__version__}")
    for package in ("numpy", "Pillow", "PyYAML", "scipy", "diplib"):
        try:
            version = metadata.version(package)
        except metadata.PackageNotFoundError:
            print(f"{package}: missing")
        else:
            print(f"{package}: {version}")
    print("External tools:")
    for engine in ("realcugan", "waifu2x", "realesrgan"):
        configured = config.get("external_tools", {}).get(engine)
        try:
            resolved = resolve_tool_path(engine, config)
        except ToolNotFoundError as exc:
            if configured:
                print(f"  {engine}: unavailable ({exc})")
            else:
                print(f"  {engine}: not configured ({EXECUTABLE_NAMES[engine]} not on PATH)")
        else:
            print(f"  {engine}: {resolved}")
    for tool_name in ("potrace", "cairosvg", "inkscape"):
        configured = config.get("external_tools", {}).get(tool_name)
        try:
            resolved = resolve_renderer_tool(tool_name, config)
        except ToolNotFoundError as exc:
            names = "/".join(TOOL_EXECUTABLE_NAMES[tool_name])
            if configured:
                print(f"  {tool_name}: unavailable ({exc})")
            else:
                print(f"  {tool_name}: not configured ({names} not on PATH)")
        else:
            print(f"  {tool_name}: {resolved}")
