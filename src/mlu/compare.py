"""Quality comparison grid helpers."""

from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from mlu import __version__
from mlu.config import ConfigError, deep_merge, load_yaml_file, validate_config
from mlu.pipeline import PipelineResult, upscale_image


@dataclass(frozen=True)
class CompareVariant:
    """One expanded comparison variant."""

    name: str
    overrides: dict[str, Any]


@dataclass(frozen=True)
class CompareItemResult:
    """Output paths and metadata for one comparison variant."""

    variant: CompareVariant
    output_path: Path
    debug_dir: Path | None
    result: PipelineResult


@dataclass(frozen=True)
class CompareResult:
    """Result paths for a comparison run."""

    output_dir: Path
    items: tuple[CompareItemResult, ...]
    contact_sheet_path: Path
    center_crop_1x_path: Path
    center_crop_200_path: Path
    summary_json_path: Path


def run_compare(
    input_path: str | Path,
    output_dir: str | Path,
    base_config: dict[str, Any],
    *,
    preset: str | None,
    grid_path: str | Path,
    invert: bool = False,
    debug_dir: str | Path | None = None,
    thumbnail_width: int = 420,
    crop_source_size: int = 256,
) -> CompareResult:
    """Run multiple pipeline variants and build visual comparison sheets."""

    if thumbnail_width <= 0:
        raise ValueError("--thumbnail-width must be greater than 0.")
    if crop_source_size <= 0:
        raise ValueError("--crop-source-size must be greater than 0.")

    variants = load_compare_variants(grid_path)
    destination = Path(output_dir)
    variants_dir = destination / "variants"
    debug_base = Path(debug_dir) if debug_dir is not None else None

    items: list[CompareItemResult] = []
    for index, variant in enumerate(variants, start=1):
        config = deep_merge(base_config, variant.overrides)
        config = deep_merge(config, {"debug": {"save_run_json": True}})
        validate_config(config)
        output_path = variants_dir / f"{index:02d}_{variant.name}.png"
        item_debug_dir = (
            debug_base / f"{index:02d}_{variant.name}" if debug_base is not None else None
        )
        result = upscale_image(
            input_path,
            output_path,
            config,
            invert=invert,
            debug_dir=item_debug_dir,
            preset=preset,
        )
        items.append(
            CompareItemResult(
                variant=variant,
                output_path=output_path,
                debug_dir=item_debug_dir,
                result=result,
            )
        )

    item_tuple = tuple(items)
    contact_sheet_path = destination / "contact_sheet.png"
    center_crop_1x_path = destination / "center_crop_1x.png"
    center_crop_200_path = destination / "center_crop_200pct.png"
    summary_json_path = destination / "compare-summary.json"

    build_contact_sheet(
        item_tuple,
        contact_sheet_path,
        thumbnail_width=thumbnail_width,
    )
    build_center_crop_sheet(
        item_tuple,
        center_crop_1x_path,
        crop_size=int(crop_source_size) * int(base_config["pipeline"]["scale"]),
        zoom=1,
    )
    build_center_crop_sheet(
        item_tuple,
        center_crop_200_path,
        crop_size=int(crop_source_size) * int(base_config["pipeline"]["scale"]),
        zoom=2,
    )
    save_compare_summary(
        summary_json_path,
        input_path=Path(input_path),
        output_dir=destination,
        preset=preset,
        grid_path=Path(grid_path),
        invert=invert,
        thumbnail_width=thumbnail_width,
        crop_source_size=crop_source_size,
        items=item_tuple,
    )

    return CompareResult(
        output_dir=destination,
        items=item_tuple,
        contact_sheet_path=contact_sheet_path,
        center_crop_1x_path=center_crop_1x_path,
        center_crop_200_path=center_crop_200_path,
        summary_json_path=summary_json_path,
    )


def load_compare_variants(grid_path: str | Path) -> tuple[CompareVariant, ...]:
    """Load comparison variants from a YAML grid file."""

    data = load_yaml_file(grid_path)
    version = data.get("version", 1)
    if version != 1:
        raise ConfigError("Only compare grid version 1 is supported.")

    base = data.get("base", {})
    if not isinstance(base, dict):
        raise ConfigError("compare grid base must be a mapping.")

    if "variants" in data:
        variants = _load_named_variants(data["variants"])
    elif "parameters" in data:
        variants = _expand_parameter_grid(data["parameters"])
    else:
        raise ConfigError("Compare grid must contain 'parameters' or 'variants'.")

    if not variants:
        raise ConfigError("Compare grid must define at least one variant.")
    if base:
        variants = tuple(
            CompareVariant(
                name=variant.name,
                overrides=deep_merge(base, variant.overrides),
            )
            for variant in variants
        )
    return variants


def build_contact_sheet(
    items: tuple[CompareItemResult, ...],
    output_path: str | Path,
    *,
    thumbnail_width: int,
) -> Path:
    """Build a thumbnail contact sheet for all comparison outputs."""

    cells: list[tuple[str, Image.Image]] = []
    all_binary = True
    for item in items:
        with Image.open(item.output_path) as image:
            grayscale = image.convert("L")
            is_binary = _is_binary_grayscale(grayscale)
            all_binary &= is_binary
            ratio = thumbnail_width / grayscale.width
            thumbnail_height = max(1, int(round(grayscale.height * ratio)))
            thumbnail = grayscale.resize(
                (thumbnail_width, thumbnail_height),
                Image.Resampling.NEAREST if is_binary else Image.Resampling.LANCZOS,
            )
        cells.append((item.variant.name, thumbnail))

    sheet = _compose_horizontal_sheet(cells, force_binary=all_binary)
    sheet_path = Path(output_path)
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(sheet_path, format="PNG")
    return sheet_path


def build_center_crop_sheet(
    items: tuple[CompareItemResult, ...],
    output_path: str | Path,
    *,
    crop_size: int,
    zoom: int,
) -> Path:
    """Build a horizontal sheet of centered crops at 1x or 200% zoom."""

    cells: list[tuple[str, Image.Image]] = []
    all_binary = True
    for item in items:
        with Image.open(item.output_path) as image:
            grayscale = image.convert("L")
            all_binary &= _is_binary_grayscale(grayscale)
            crop = center_crop(grayscale, crop_size)
            if zoom != 1:
                crop = crop.resize(
                    (crop.width * zoom, crop.height * zoom),
                    Image.Resampling.NEAREST,
                )
        cells.append((item.variant.name, crop))

    sheet = _compose_horizontal_sheet(cells, force_binary=all_binary)
    sheet_path = Path(output_path)
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(sheet_path, format="PNG")
    return sheet_path


def center_crop(image: Image.Image, size: int) -> Image.Image:
    """Return a centered square crop, clamped to the image bounds."""

    crop_width = min(size, image.width)
    crop_height = min(size, image.height)
    left = max(0, (image.width - crop_width) // 2)
    top = max(0, (image.height - crop_height) // 2)
    return image.crop((left, top, left + crop_width, top + crop_height))


def save_compare_summary(
    path: str | Path,
    *,
    input_path: Path,
    output_dir: Path,
    preset: str | None,
    grid_path: Path,
    invert: bool,
    thumbnail_width: int,
    crop_source_size: int,
    items: tuple[CompareItemResult, ...],
) -> Path:
    """Save compare summary JSON."""

    payload = {
        "schema_version": 1,
        "tool": {
            "name": "manga-lineart-upscaler",
            "version": __version__,
        },
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "input_path": str(input_path),
        "output_dir": str(output_dir),
        "preset": preset,
        "grid_path": str(grid_path),
        "invert": bool(invert),
        "thumbnail_width": int(thumbnail_width),
        "crop_source_size": int(crop_source_size),
        "items": [compare_item_to_dict(item) for item in items],
    }
    summary_path = Path(path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
    return summary_path


def compare_item_to_dict(item: CompareItemResult) -> dict[str, Any]:
    """Return a JSON-friendly compare item."""

    return {
        "name": item.variant.name,
        "overrides": item.variant.overrides,
        "output_path": str(item.output_path),
        "run_json_path": str(item.result.run_json_path) if item.result.run_json_path else "",
        "debug_dir": str(item.debug_dir) if item.debug_dir is not None else "",
        "mask_area_ratio": item.result.line_maps.mask_area_ratio,
        "warnings": list(item.result.line_maps.warnings),
        "tone_used_in_final": item.result.tone_used_in_final,
        "upscaler_engine": item.result.upscaler_result.engine,
        "upscaler_used_fallback": item.result.upscaler_result.used_fallback,
    }


def _load_named_variants(raw_variants: object) -> tuple[CompareVariant, ...]:
    if not isinstance(raw_variants, list):
        raise ConfigError("compare variants must be a list.")

    variants: list[CompareVariant] = []
    for index, item in enumerate(raw_variants, start=1):
        if not isinstance(item, dict):
            raise ConfigError("Each compare variant must be a mapping.")
        raw_name = item.get("name", f"variant_{index:02d}")
        if not isinstance(raw_name, str) or not raw_name:
            raise ConfigError("compare variant name must be a non-empty string.")
        raw_overrides = item.get("overrides", {})
        if not isinstance(raw_overrides, dict):
            raise ConfigError("compare variant overrides must be a mapping.")
        variants.append(CompareVariant(name=slugify_name(raw_name), overrides=raw_overrides))
    return tuple(variants)


def _expand_parameter_grid(parameters: object) -> tuple[CompareVariant, ...]:
    if not isinstance(parameters, dict):
        raise ConfigError("compare parameters must be a mapping.")

    names = list(parameters.keys())
    values: list[list[Any]] = []
    for name in names:
        raw_values = parameters[name]
        if not isinstance(name, str) or not name:
            raise ConfigError("compare parameter names must be non-empty strings.")
        if not isinstance(raw_values, list) or not raw_values:
            raise ConfigError(f"compare parameter {name!r} must be a non-empty list.")
        values.append(raw_values)

    variants: list[CompareVariant] = []
    for combination in itertools.product(*values):
        overrides: dict[str, Any] = {}
        label_parts: list[str] = []
        for dotted_name, value in zip(names, combination, strict=True):
            overrides = deep_merge(overrides, dotted_override(dotted_name, value))
            label_parts.append(f"{dotted_name}_{value_slug(value)}")
        variants.append(
            CompareVariant(
                name=slugify_name("__".join(label_parts)),
                overrides=overrides,
            )
        )
    return tuple(variants)


def dotted_override(path: str, value: Any) -> dict[str, Any]:
    """Create a nested override dict from a dotted path."""

    parts = [part.strip() for part in path.split(".")]
    if any(not part for part in parts):
        raise ConfigError(f"Invalid compare parameter path: {path!r}")

    result: dict[str, Any] = {}
    cursor = result
    for part in parts[:-1]:
        next_cursor: dict[str, Any] = {}
        cursor[part] = next_cursor
        cursor = next_cursor
    cursor[parts[-1]] = value
    return result


def slugify_name(name: str) -> str:
    """Return a filesystem-friendly ASCII-ish label."""

    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip())
    slug = slug.strip("._-")
    return slug[:96] if slug else "variant"


def value_slug(value: Any) -> str:
    """Return a short slug for a scalar parameter value."""

    text = str(value).lower().replace("-", "m").replace(".", "p")
    return slugify_name(text)


def _compose_horizontal_sheet(
    cells: list[tuple[str, Image.Image]],
    *,
    force_binary: bool = False,
) -> Image.Image:
    if not cells:
        raise ValueError("Cannot build a comparison sheet without cells.")

    font = ImageFont.load_default()
    padding = 12
    label_height = 28
    max_height = max(image.height for _, image in cells)
    total_width = sum(image.width for _, image in cells) + padding * (len(cells) + 1)
    total_height = max_height + label_height + padding * 2
    sheet = Image.new("L", (total_width, total_height), 255)
    draw = ImageDraw.Draw(sheet)

    x = padding
    for label, image in cells:
        draw.text((x, padding), label, fill=0, font=font)
        sheet.paste(image, (x, label_height + padding))
        x += image.width + padding
    if force_binary:
        sheet = sheet.point([0] * 128 + [255] * 128, mode="L")
    return sheet


def _is_binary_grayscale(image: Image.Image) -> bool:
    histogram = image.histogram()
    return sum(histogram[1:255]) == 0
