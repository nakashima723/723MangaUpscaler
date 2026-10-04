"""Debug layer and run metadata output helpers."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mlu import __version__
from mlu.grayscale import FloatImage
from mlu.io import ImageData, save_grayscale_png
from mlu.layer_separation import LayerSeparationResult
from mlu.mask_extract import LineMaps
from mlu.sdf_render import SDFRenderResult, sdf_preview
from mlu.tone_source import ToneSourceResult
from mlu.upscaler_external import UpscalerResult


def save_debug_layers(
    debug_dir: str | Path,
    image: ImageData,
    line_maps: LineMaps,
    sdf_result: SDFRenderResult,
    final: FloatImage,
    tone_source_result: ToneSourceResult | None = None,
    upscaler_result: UpscalerResult | None = None,
    separation_result: LayerSeparationResult | None = None,
) -> tuple[Path, ...]:
    """Save MVP debug layers as 8bit PNG files."""

    debug_path = Path(debug_dir)
    layers: list[tuple[str, FloatImage]] = [
        ("00_input_gray.png", image.array),
        ("01_darkness.png", line_maps.darkness),
        ("02_line_prob.png", line_maps.line_prob),
        ("03_line_mask.png", line_maps.line_mask.astype("float32")),
    ]
    paths: list[Path] = []
    if sdf_result.renderer == "potrace":
        if sdf_result.svg_text is not None:
            svg_path = debug_path / "04_potrace.svg"
            svg_path.parent.mkdir(parents=True, exist_ok=True)
            svg_path.write_text(sdf_result.svg_text, encoding="utf-8")
            paths.append(svg_path)
        layers.extend(
            [
                ("05_line_alpha_hr.png", sdf_result.line_alpha_hr),
                ("06_final.png", final),
            ]
        )
        if sdf_result.sdf_reference_line_alpha_hr is not None:
            layers.append(
                (
                    "07_sdf_reference_line_alpha_hr.png",
                    sdf_result.sdf_reference_line_alpha_hr,
                )
            )
    else:
        if sdf_result.sdf_hr is None:
            raise ValueError("SDF diagnostics are required when saving debug layers.")
        layers.extend(
            [
                ("04_sdf_hr_preview.png", sdf_preview(sdf_result.sdf_hr)),
                ("05_line_alpha_hr.png", sdf_result.line_alpha_hr),
                ("06_final.png", final),
            ]
        )
    has_tone_source_debug = (
        tone_source_result is not None and tone_source_result.mode != "white_canvas"
    )
    if has_tone_source_debug and tone_source_result is not None:
        layers.append(("07_tone_source.png", tone_source_result.image))
    if upscaler_result is not None and upscaler_result.engine != "none":
        layers.append((f"{len(layers):02d}_tone_hr.png", upscaler_result.image))
    if separation_result is not None:
        layers.extend(
            [
                (f"{len(layers):02d}_relative_line_alpha.png", separation_result.line_alpha),
                (
                    f"{len(layers) + 1:02d}_render_line_coverage.png",
                    separation_result.line_maps.line_soft,
                ),
                (
                    f"{len(layers) + 2:02d}_legacy_blend_weight.png",
                    separation_result.legacy_blend_weight,
                ),
                (
                    f"{len(layers) + 3:02d}_relative_contrast.png",
                    separation_result.relative_contrast,
                ),
                (f"{len(layers) + 4:02d}_estimated_tone.png", separation_result.tone),
            ]
        )
    if sdf_result.line_soft_hr is not None:
        layers.append((f"{len(layers):02d}_line_soft_hr.png", sdf_result.line_soft_hr))
    if sdf_result.soft_mask_hr is not None:
        layers.append((f"{len(layers):02d}_soft_mask_hr.png", sdf_result.soft_mask_hr))
    if sdf_result.sdf_alpha_before_soft_mode_hr is not None:
        layers.append(
            (
                f"{len(layers):02d}_sdf_alpha_before_soft_mode_hr.png",
                sdf_result.sdf_alpha_before_soft_mode_hr,
            )
        )
    if sdf_result.directional_smoothing_source_alpha_hr is not None:
        layers.append(
            (
                f"{len(layers):02d}_directional_smoothing_source_alpha_hr.png",
                sdf_result.directional_smoothing_source_alpha_hr,
            )
        )
    if (
        sdf_result.directional_smoothing_weight_hr is not None
        and bool(sdf_result.directional_smoothing_weight_hr.any())
    ):
        layers.append(
            (
                f"{len(layers):02d}_directional_smoothing_weight_hr.png",
                sdf_result.directional_smoothing_weight_hr,
            )
        )
    if (
        sdf_result.directional_smoothing_delta_hr is not None
        and bool(sdf_result.directional_smoothing_delta_hr.any())
    ):
        layers.append(
            (
                f"{len(layers):02d}_directional_smoothing_delta_hr.png",
                sdf_result.directional_smoothing_delta_hr,
            )
        )
    if sdf_result.centerline_source is not None:
        layers.append((f"{len(layers):02d}_centerline_source.png", sdf_result.centerline_source))
    if sdf_result.centerline_eligible_source is not None:
        layers.append(
            (
                f"{len(layers):02d}_long_stroke_eligible_source.png",
                sdf_result.centerline_eligible_source,
            )
        )
    if sdf_result.centerline_rolled_back_component_source is not None:
        layers.append(
            (
                f"{len(layers):02d}_component_rollback_source.png",
                sdf_result.centerline_rolled_back_component_source,
            )
        )
    if sdf_result.filtered_centerline_source is not None:
        layers.append(
            (
                f"{len(layers):02d}_filtered_centerline_source.png",
                sdf_result.filtered_centerline_source,
            )
        )
    if sdf_result.centerline_filter_displacement_source is not None:
        layers.append(
            (
                f"{len(layers):02d}_centerline_filter_displacement_source.png",
                sdf_result.centerline_filter_displacement_source,
            )
        )
    if sdf_result.centerline_protected_source is not None:
        layers.append(
            (
                f"{len(layers):02d}_centerline_protected_source.png",
                sdf_result.centerline_protected_source,
            )
        )
    if (
        sdf_result.centerline_simplification_delta_hr is not None
        and bool(sdf_result.centerline_simplification_delta_hr.any())
    ):
        layers.append(
            (
                f"{len(layers):02d}_centerline_simplification_delta_hr.png",
                sdf_result.centerline_simplification_delta_hr,
            )
        )
    if sdf_result.line_geometry_hr is not None and bool(sdf_result.line_geometry_hr.any()):
        layers.append((f"{len(layers):02d}_line_geometry_hr.png", sdf_result.line_geometry_hr))
    for filename, array in layers:
        path = debug_path / filename
        save_grayscale_png(path, array, bit_depth=8, overwrite=True)
        paths.append(path)
    return tuple(paths)


def run_json_path(output_path: str | Path) -> Path:
    """Return the sidecar run JSON path for a final output image."""

    return Path(output_path).with_suffix(".mlus-run.json")


def build_run_metadata(
    *,
    input_path: str | Path | None,
    output_path: str | Path,
    preset: str | None,
    invert: bool,
    config: dict[str, Any],
    input_size: tuple[int, int],
    output_size: tuple[int, int],
    input_bit_depth: int,
    input_format: str | None,
    input_mode: str | None,
    mask_area_ratio: float,
    warnings: Sequence[str],
    debug_paths: Sequence[Path],
) -> dict[str, Any]:
    """Build a JSON-serializable record of a pipeline run."""

    return {
        "schema_version": 1,
        "tool": {
            "name": "manga-lineart-upscaler",
            "version": __version__,
        },
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "input": {
            "path": _path_or_none(input_path),
            "size": _size_dict(input_size),
            "bit_depth": int(input_bit_depth),
            "format": input_format,
            "mode": input_mode,
            "invert": bool(invert),
        },
        "output": {
            "path": str(Path(output_path)),
            "size": _size_dict(output_size),
            "bit_depth": int(config["io"]["output_bit_depth"]),
        },
        "run": {
            "preset": preset,
            "scale": int(config["pipeline"]["scale"]),
            "line_renderer": config["pipeline"]["line_renderer"],
            "tone_mode": config["pipeline"]["tone_mode"],
            "upscaler": config["upscaler"]["engine"],
        },
        "mask": {
            "area_ratio": float(mask_area_ratio),
            "warnings": list(warnings),
        },
        "debug": {
            "paths": [str(path) for path in debug_paths],
        },
        "config": config,
    }


def save_run_json(path: str | Path, metadata: dict[str, Any]) -> Path:
    """Save run metadata as UTF-8 JSON and return the path."""

    json_path = Path(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
    return json_path


def _size_dict(size: tuple[int, int]) -> dict[str, int]:
    width, height = size
    return {"width": int(width), "height": int(height)}


def _path_or_none(path: str | Path | None) -> str | None:
    if path is None:
        return None
    return str(Path(path))
