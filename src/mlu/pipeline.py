"""Pipeline orchestration helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from mlu.centerline_simplification import simplify_centerline_alpha
from mlu.composite import composite_black_lines, white_canvas
from mlu.debug_layers import build_run_metadata, run_json_path, save_debug_layers, save_run_json
from mlu.directional_smoothing import smooth_directional_alpha
from mlu.grayscale import FloatImage
from mlu.io import (
    ImageData,
    load_image,
    save_grayscale_png,
    save_luminance_as_alpha_png,
)
from mlu.layer_separation import LayerSeparationResult, separate_relative_layers
from mlu.line_stabilizer import stabilize_line_alpha
from mlu.mask_extract import LineMaps, extract_line_maps
from mlu.potrace_render import render_potrace_line_alpha
from mlu.psd_output import save_layered_grayscale_psd
from mlu.sdf_render import SDFRenderResult, render_line_alpha
from mlu.tone_source import (
    ToneSourceResult,
    detect_likely_pure_lineart,
    generate_tone_source,
)
from mlu.upscaler_external import UpscalerResult, upscale_tone_source


@dataclass(frozen=True)
class PipelineResult:
    """Result of the MVP single-image pipeline."""

    input_image: ImageData
    line_maps: LineMaps
    tone_source_result: ToneSourceResult
    upscaler_result: UpscalerResult
    sdf_result: SDFRenderResult
    final: FloatImage
    tone_used_in_final: bool
    tone_skip_reason: str | None
    output_path: Path
    debug_paths: tuple[Path, ...]
    run_json_path: Path | None
    run_metadata: dict[str, Any] | None
    separation_result: LayerSeparationResult | None = None
    tone_output_path: Path | None = None
    grayscale_mode: str = "legacy"
    separate_output_format: str | None = None


def upscale_image(
    input_path: str | Path,
    output_path: str | Path,
    config: dict,
    *,
    invert: bool = False,
    debug_dir: str | Path | None = None,
    preset: str | None = "line_only",
) -> PipelineResult:
    """Run the MVP line-art upscaling pipeline for one image."""

    grayscale_mode = str(config.get("grayscale_processing", {}).get("mode", "legacy"))
    if grayscale_mode not in {"legacy", "line_only", "separate", "composite"}:
        raise ValueError(f"Unsupported grayscale_processing.mode: {grayscale_mode}")
    output = Path(output_path)
    separate_output_format: str | None = None
    if grayscale_mode == "separate":
        separate_output_format = str(
            config.get("grayscale_processing", {}).get(
                "separate_output_format",
                "png",
            )
        )
    _validate_output_extension(
        output,
        grayscale_mode=grayscale_mode,
        separate_output_format=separate_output_format,
    )

    image = load_image(input_path, invert=invert)
    separation_result: LayerSeparationResult | None = None
    if grayscale_mode == "legacy":
        line_maps = extract_line_maps(image.array, config)
        tone_source_result = generate_tone_source(image.array, line_maps, config)
        tone_used_in_final, tone_skip_reason = decide_tone_usage(tone_source_result, config)
        if tone_used_in_final:
            upscaler_result = upscale_tone_source(tone_source_result.image, config)
        else:
            upscaler_result = white_canvas_upscaler_result(
                tone_source_result.image.shape,
                config,
                reason=tone_skip_reason,
            )
    else:
        separation_result = separate_relative_layers(image.array, config)
        line_maps = separation_result.line_maps
        tone_source_result = tone_source_from_separation(
            image.array,
            separation_result,
            line_maps,
        )
        tone_used_in_final = grayscale_mode == "composite"
        if grayscale_mode in {"separate", "composite"}:
            upscaler_result = upscale_separated_tone(tone_source_result.image, config)
            tone_skip_reason = None if tone_used_in_final else "tone written as a separate layer"
        else:
            tone_skip_reason = "grayscale_processing.mode is line_only"
            upscaler_result = white_canvas_upscaler_result(
                tone_source_result.image.shape,
                config,
                reason=tone_skip_reason,
            )

    save_metadata = debug_dir is not None or bool(
        config.get("debug", {}).get("save_run_json", False)
    )
    sdf_result = render_line_branch(
        line_maps,
        config,
        retain_diagnostics=debug_dir is not None,
        collect_metadata=save_metadata,
    )
    if bool(config.get("line_stabilizer", {}).get("enabled", False)):
        stabilization = stabilize_line_alpha(
            sdf_result.line_alpha_hr,
            line_maps.line_mask,
            line_maps.line_soft,
            config,
        )
        sdf_result = replace(
            sdf_result,
            line_alpha_hr=stabilization.line_alpha_hr,
            line_geometry_hr=stabilization.line_geometry_hr,
            line_segments=stabilization.segments,
        )
    smoothing_enabled = bool(config.get("directional_smoothing", {}).get("enabled", False))
    if smoothing_enabled:
        smoothing = smooth_directional_alpha(
            sdf_result.line_alpha_hr,
            config,
            renderer=sdf_result.renderer,
        )
        sdf_result = replace(
            sdf_result,
            line_alpha_hr=smoothing.line_alpha_hr,
            directional_smoothing_source_alpha_hr=smoothing.source_alpha_hr,
            directional_smoothing_weight_hr=smoothing.weight_hr,
            directional_smoothing_delta_hr=smoothing.delta_hr,
            directional_smoothing_stats=smoothing.stats,
        )
    simplification = simplify_centerline_alpha(
        sdf_result.line_alpha_hr,
        config,
        renderer=sdf_result.renderer,
    )
    sdf_result = replace(
        sdf_result,
        line_alpha_hr=simplification.line_alpha_hr,
        centerline_source=simplification.centerline_source,
        centerline_eligible_source=simplification.eligible_centerline_source,
        centerline_rolled_back_component_source=(
            simplification.rolled_back_component_source
        ),
        filtered_centerline_source=simplification.filtered_centerline_source,
        centerline_filter_displacement_source=(
            simplification.filter_displacement_source
        ),
        centerline_protected_source=simplification.protected_source,
        centerline_simplification_delta_hr=simplification.delta_hr,
        centerline_simplification_stats=simplification.stats,
    )
    composite_config = config.get("composite", {})
    if grayscale_mode == "legacy" and _can_use_binary_composite_fast_path(
        sdf_result,
        config,
        tone_used_in_final=tone_used_in_final,
    ):
        final = np.float32(1.0) - sdf_result.line_alpha_hr
    else:
        composite_base = (
            upscaler_result.image
            if tone_used_in_final
            else white_canvas(sdf_result.line_alpha_hr.shape)
        )
        final = composite_black_lines(
            composite_base,
            sdf_result.line_alpha_hr,
            line_darkness=float(composite_config.get("line_darkness", 1.0)),
            edge_alpha_gamma=float(composite_config.get("edge_alpha_gamma", 1.0)),
            clamp=bool(composite_config.get("clamp", True)),
        )

    tone_output: Path | None = None
    if grayscale_mode == "separate":
        if separate_output_format == "png":
            tone_output = separated_tone_path(output)
            if tone_output.exists() and not bool(config["io"]["overwrite"]):
                raise FileExistsError(f"Output already exists: {tone_output}")

    output_bit_depth = int(config["io"]["output_bit_depth"])
    overwrite = bool(config["io"]["overwrite"])
    if grayscale_mode == "separate" and separate_output_format == "psd":
        save_layered_grayscale_psd(
            output,
            line_image=final,
            tone_image=upscaler_result.image,
            bit_depth=output_bit_depth,
            overwrite=overwrite,
        )
    else:
        save_grayscale_png(
            output,
            final,
            bit_depth=output_bit_depth,
            overwrite=overwrite,
        )
    if tone_output is not None:
        save_luminance_as_alpha_png(
            tone_output,
            upscaler_result.image,
            overwrite=overwrite,
        )

    debug_paths: tuple[Path, ...] = ()
    if debug_dir is not None:
        debug_paths = save_debug_layers(
            debug_dir,
            image,
            line_maps,
            sdf_result,
            final,
            tone_source_result=tone_source_result,
            upscaler_result=upscaler_result,
            separation_result=separation_result,
        )

    metadata: dict[str, Any] | None = None
    metadata_path: Path | None = None
    if save_metadata:
        metadata_path = run_json_path(output)
        metadata = build_run_metadata(
            input_path=image.path,
            output_path=output,
            preset=preset,
            invert=invert,
            config=config,
            input_size=(image.array.shape[1], image.array.shape[0]),
            output_size=(final.shape[1], final.shape[0]),
            input_bit_depth=image.bit_depth,
            input_format=image.metadata.get("format"),
            input_mode=image.metadata.get("mode"),
            mask_area_ratio=line_maps.mask_area_ratio,
            warnings=line_maps.warnings,
            debug_paths=debug_paths,
        )
        metadata["line_stabilizer"] = {
            "segment_count": len(sdf_result.line_segments),
        }
        metadata["sdf_diagnostics"] = build_sdf_diagnostics(
            sdf_result,
            config,
        )
        metadata["directional_smoothing"] = sdf_result.directional_smoothing_stats or {
            "enabled": bool(config.get("directional_smoothing", {}).get("enabled", False)),
            "applied": False,
        }
        metadata["centerline_simplification"] = (
            sdf_result.centerline_simplification_stats
            or {
                "enabled": bool(
                    config.get("centerline_simplification", {}).get("enabled", False)
                ),
                "applied": False,
            }
        )
        metadata["renderer"] = sdf_result.renderer_metadata or {"renderer": sdf_result.renderer}
        metadata["tone_source"] = {
            "mode": tone_source_result.mode,
            "is_likely_pure_lineart": tone_source_result.is_likely_pure_lineart,
            "line_lift_ratio": tone_source_result.line_lift_ratio,
            "midtone_ratio": tone_source_result.midtone_ratio,
        }
        metadata["tone_composite"] = {
            "tone_usage": config.get("composite", {}).get("tone_usage", "auto"),
            "used_tone_hr": tone_used_in_final,
            "skip_reason": tone_skip_reason,
        }
        metadata["upscaler"] = upscaler_result.to_metadata()
        metadata["grayscale_processing"] = {
            "mode": grayscale_mode,
            "separate_output_format": separate_output_format,
            "tone_output_path": str(tone_output) if tone_output is not None else None,
            "alpha_convention": (
                "black grayscale pixels with transparency channels"
                if separate_output_format == "psd"
                else "alpha = 1 - tone_luminance"
                if tone_output is not None
                else None
            ),
            "separation": (
                separation_result.to_metadata() if separation_result is not None else None
            ),
        }
        save_run_json(metadata_path, metadata)

    return PipelineResult(
        input_image=image,
        line_maps=line_maps,
        tone_source_result=tone_source_result,
        upscaler_result=upscaler_result,
        sdf_result=sdf_result,
        final=final,
        tone_used_in_final=tone_used_in_final,
        tone_skip_reason=tone_skip_reason,
        output_path=output,
        debug_paths=debug_paths,
        run_json_path=metadata_path,
        run_metadata=metadata,
        separation_result=separation_result,
        tone_output_path=tone_output,
        grayscale_mode=grayscale_mode,
        separate_output_format=separate_output_format,
    )


def _validate_output_extension(
    output_path: Path,
    *,
    grayscale_mode: str,
    separate_output_format: str | None,
) -> None:
    expected_suffix = (
        ".psd"
        if grayscale_mode == "separate" and separate_output_format == "psd"
        else ".png"
    )
    if output_path.suffix.lower() != expected_suffix:
        raise ValueError(
            f"Output path must use {expected_suffix} for grayscale mode "
            f"{grayscale_mode!r}."
        )


def tone_source_from_separation(
    source: FloatImage,
    separation: LayerSeparationResult,
    line_maps: LineMaps,
) -> ToneSourceResult:
    """Adapt a relative separation result to the existing tone branch."""

    is_pure, midtone_ratio = detect_likely_pure_lineart(
        separation.tone,
        line_maps.line_mask,
    )
    if line_maps.line_mask.any():
        line_lift_ratio = float(
            np.mean((separation.tone - source)[line_maps.line_mask])
        )
    else:
        line_lift_ratio = 0.0
    return ToneSourceResult(
        image=separation.tone,
        mode="relative_separation",
        is_likely_pure_lineart=is_pure,
        line_lift_ratio=line_lift_ratio,
        midtone_ratio=midtone_ratio,
    )


def upscale_separated_tone(
    tone_source: FloatImage,
    config: dict[str, Any],
) -> UpscalerResult:
    """Upscale separated tone, using Lanczos when no tone engine was selected."""

    requested_engine = str(config.get("upscaler", {}).get("engine", "none"))
    if requested_engine != "none":
        return upscale_tone_source(tone_source, config)
    lanczos_config = {
        **config,
        "upscaler": {**config.get("upscaler", {}), "engine": "lanczos"},
    }
    return upscale_tone_source(tone_source, lanczos_config)


def separated_tone_path(output_path: str | Path) -> Path:
    """Return the sibling RGBA path used by separate grayscale mode."""

    output = Path(output_path)
    return output.with_name(f"{output.stem}_tone.png")


def render_line_branch(
    line_maps: LineMaps,
    config: dict[str, Any],
    *,
    retain_diagnostics: bool = True,
    collect_metadata: bool = True,
) -> SDFRenderResult:
    """Render line alpha using the configured line renderer."""

    renderer = str(config.get("pipeline", {}).get("line_renderer", "sdf"))
    if renderer == "sdf":
        return render_line_alpha(
            line_maps.line_mask,
            config,
            line_soft=line_maps.line_soft,
            retain_diagnostics=retain_diagnostics,
            collect_metadata=collect_metadata,
        )
    if renderer == "potrace":
        return render_potrace_line_alpha(line_maps.line_mask, config, line_soft=line_maps.line_soft)
    raise ValueError(f"Unsupported pipeline.line_renderer: {renderer}")


def build_sdf_diagnostics(
    sdf_result: SDFRenderResult,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Build lightweight SDF diagnostics for run JSON."""

    sdf_config = config.get("sdf", {})
    diagnostics: dict[str, Any] = {
        "distance_source": sdf_config.get("distance_source"),
        "soft_sdf_threshold": sdf_config.get("soft_sdf_threshold"),
        "width_bias_source_px": sdf_config.get("width_bias_source_px"),
        "soft_alpha_mode": sdf_config.get("soft_alpha_mode"),
        "soft_gain": sdf_config.get("soft_gain"),
    }
    if sdf_result.line_soft_hr is not None:
        diagnostics["line_soft_hr_min"] = float(sdf_result.line_soft_hr.min())
        diagnostics["line_soft_hr_max"] = float(sdf_result.line_soft_hr.max())
        diagnostics["line_soft_hr_mean"] = float(sdf_result.line_soft_hr.mean())
    if sdf_result.soft_mask_hr is not None:
        diagnostics["soft_mask_hr_area_ratio"] = float(sdf_result.soft_mask_hr.mean())
    if sdf_result.sdf_diagnostic_stats is not None:
        diagnostics.update(sdf_result.sdf_diagnostic_stats)
    return diagnostics


def _can_use_binary_composite_fast_path(
    sdf_result: SDFRenderResult,
    config: dict[str, Any],
    *,
    tone_used_in_final: bool,
) -> bool:
    """Return whether white-canvas compositing reduces exactly to ``1 - alpha``."""

    renderer_metadata = sdf_result.renderer_metadata or {}
    composite_config = config.get("composite", {})
    return bool(
        renderer_metadata.get("alpha_fast_path", False)
        and not tone_used_in_final
        and float(composite_config.get("line_darkness", 1.0)) == 1.0
        and not bool(config.get("line_stabilizer", {}).get("enabled", False))
        and not bool(config.get("directional_smoothing", {}).get("enabled", False))
        and not bool(config.get("centerline_simplification", {}).get("enabled", False))
    )


def decide_tone_usage(
    tone_source_result: ToneSourceResult,
    config: dict[str, Any],
) -> tuple[bool, str | None]:
    """Return whether `tone_hr` should be used as the final composite base."""

    tone_usage = str(config.get("composite", {}).get("tone_usage", "auto"))
    requested_engine = str(config.get("upscaler", {}).get("engine", "none"))
    if tone_usage == "never":
        return False, "composite.tone_usage is never"
    if requested_engine == "none":
        return False, "upscaler.engine is none"
    if tone_usage == "always":
        return True, None
    if tone_usage == "auto":
        if tone_source_result.is_likely_pure_lineart:
            return False, "input looks like pure line art"
        return True, None
    raise ValueError(f"Unsupported composite.tone_usage: {tone_usage}")


def white_canvas_upscaler_result(
    source_shape: tuple[int, int],
    config: dict[str, Any],
    *,
    reason: str | None,
) -> UpscalerResult:
    """Create an upscaler result that explicitly uses a white HR canvas."""

    scale = int(config.get("pipeline", {}).get("scale", 4))
    requested_engine = str(config.get("upscaler", {}).get("engine", "none"))
    return UpscalerResult(
        image=white_canvas((source_shape[0] * scale, source_shape[1] * scale)),
        requested_engine=requested_engine,
        engine="none",
        used_fallback=False,
        error=reason,
    )


def inspect_image(
    input_path: str | Path,
    config: dict,
    *,
    invert: bool = False,
    debug_dir: str | Path,
    preset: str | None = "line_only",
) -> PipelineResult:
    """Run analysis and debug output without writing a separate final output path."""

    debug_path = Path(debug_dir)
    inspect_config = {
        **config,
        "io": {**config["io"], "overwrite": True},
        "grayscale_processing": {
            **config.get("grayscale_processing", {}),
            "separate_output_format": "png",
        },
    }
    return upscale_image(
        input_path,
        debug_path / "06_final.png",
        inspect_config,
        invert=invert,
        debug_dir=debug_path,
        preset=preset,
    )
