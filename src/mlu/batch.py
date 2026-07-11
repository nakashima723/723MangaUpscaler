"""Sequential batch processing helpers."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mlu import __version__
from mlu.pipeline import PipelineResult, upscale_image

DEFAULT_EXTENSIONS = ("png", "jpg", "jpeg", "tif", "tiff")


@dataclass(frozen=True)
class BatchItemResult:
    """Summary for one input image in a batch run."""

    status: str
    input_path: Path
    output_path: Path
    run_json_path: Path | None
    debug_dir: Path | None
    error: str | None
    warnings: tuple[str, ...]
    input_size: tuple[int, int] | None
    output_size: tuple[int, int] | None
    mask_area_ratio: float | None
    tone_used_in_final: bool | None
    upscaler_engine: str | None
    upscaler_used_fallback: bool | None


@dataclass(frozen=True)
class BatchResult:
    """Summary for a sequential batch run."""

    input_dir: Path
    output_dir: Path
    summary_json_path: Path
    summary_csv_path: Path
    workers: int
    items: tuple[BatchItemResult, ...]

    @property
    def total_count(self) -> int:
        return len(self.items)

    @property
    def succeeded_count(self) -> int:
        return sum(1 for item in self.items if item.status == "ok")

    @property
    def failed_count(self) -> int:
        return sum(1 for item in self.items if item.status == "failed")


def run_batch(
    input_dir: str | Path,
    output_dir: str | Path,
    config: dict[str, Any],
    *,
    preset: str | None,
    invert: bool = False,
    debug_dir: str | Path | None = None,
    extensions: tuple[str, ...] = DEFAULT_EXTENSIONS,
    workers: int = 1,
    summary_json: str | Path | None = None,
    summary_csv: str | Path | None = None,
) -> BatchResult:
    """Run the single-image pipeline over a directory, sequentially by default."""

    if workers != 1:
        raise ValueError("Only --workers 1 is currently supported.")

    source_dir = Path(input_dir)
    target_dir = Path(output_dir)
    input_paths = discover_input_images(source_dir, extensions=extensions)
    if not input_paths:
        raise ValueError(f"No supported image files found in: {source_dir}")

    summary_json_path = (
        Path(summary_json) if summary_json is not None else target_dir / "summary.json"
    )
    summary_csv_path = Path(summary_csv) if summary_csv is not None else target_dir / "summary.csv"
    debug_base = Path(debug_dir) if debug_dir is not None else None

    items: list[BatchItemResult] = []
    seen_outputs: set[str] = set()
    for input_path in input_paths:
        relative = input_path.relative_to(source_dir)
        output_path = batch_output_path(
            relative,
            target_dir,
            scale=int(config["pipeline"]["scale"]),
        )
        output_key = str(output_path).casefold()
        item_debug_dir = batch_debug_dir(relative, debug_base) if debug_base is not None else None
        if output_key in seen_outputs:
            items.append(
                BatchItemResult(
                    status="failed",
                    input_path=input_path,
                    output_path=output_path,
                    run_json_path=None,
                    debug_dir=item_debug_dir,
                    error=f"Duplicate output path in batch: {output_path}",
                    warnings=(),
                    input_size=None,
                    output_size=None,
                    mask_area_ratio=None,
                    tone_used_in_final=None,
                    upscaler_engine=None,
                    upscaler_used_fallback=None,
                )
            )
            continue
        seen_outputs.add(output_key)

        try:
            result = upscale_image(
                input_path,
                output_path,
                config,
                invert=invert,
                debug_dir=item_debug_dir,
                preset=preset,
            )
        except Exception as exc:
            items.append(
                BatchItemResult(
                    status="failed",
                    input_path=input_path,
                    output_path=output_path,
                    run_json_path=None,
                    debug_dir=item_debug_dir,
                    error=str(exc),
                    warnings=(),
                    input_size=None,
                    output_size=None,
                    mask_area_ratio=None,
                    tone_used_in_final=None,
                    upscaler_engine=None,
                    upscaler_used_fallback=None,
                )
            )
        else:
            items.append(batch_item_from_pipeline(result, debug_dir=item_debug_dir))

    batch_result = BatchResult(
        input_dir=source_dir,
        output_dir=target_dir,
        summary_json_path=summary_json_path,
        summary_csv_path=summary_csv_path,
        workers=workers,
        items=tuple(items),
    )
    save_batch_summary_json(batch_result, config=config, preset=preset, invert=invert)
    save_batch_summary_csv(batch_result)
    return batch_result


def parse_extensions(text: str) -> tuple[str, ...]:
    """Parse comma-separated extensions into normalized names without dots."""

    extensions: list[str] = []
    for part in text.split(","):
        extension = part.strip().lower().lstrip(".")
        if extension and extension not in extensions:
            extensions.append(extension)
    if not extensions:
        raise ValueError("--extensions must contain at least one image extension.")
    return tuple(extensions)


def discover_input_images(
    input_dir: str | Path,
    *,
    extensions: tuple[str, ...],
) -> tuple[Path, ...]:
    """Return supported image paths below a directory in deterministic order."""

    source_dir = Path(input_dir)
    if not source_dir.exists():
        raise ValueError(f"Input directory does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise ValueError(f"Input path is not a directory: {source_dir}")

    normalized = {extension.lower().lstrip(".") for extension in extensions}
    paths = [
        path
        for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower().lstrip(".") in normalized
    ]
    return tuple(sorted(paths, key=lambda path: path.relative_to(source_dir).as_posix().lower()))


def batch_output_path(relative_input_path: Path, output_dir: str | Path, *, scale: int) -> Path:
    """Return the output PNG path for one relative input path."""

    relative_path = Path(relative_input_path)
    stem = relative_path.stem
    relative_parent = relative_path.parent
    return Path(output_dir) / relative_parent / f"{stem}_x{scale}.png"


def batch_debug_dir(relative_input_path: Path, debug_base_dir: str | Path) -> Path:
    """Return the per-image debug directory for a relative input path."""

    relative_path = Path(relative_input_path)
    return Path(debug_base_dir) / relative_path.parent / relative_path.stem


def batch_item_from_pipeline(
    result: PipelineResult,
    *,
    debug_dir: Path | None,
) -> BatchItemResult:
    """Create a batch summary record from a successful pipeline result."""

    return BatchItemResult(
        status="ok",
        input_path=(
            Path(result.input_image.path) if result.input_image.path is not None else Path("")
        ),
        output_path=result.output_path,
        run_json_path=result.run_json_path,
        debug_dir=debug_dir,
        error=None,
        warnings=tuple(result.line_maps.warnings),
        input_size=(result.input_image.array.shape[1], result.input_image.array.shape[0]),
        output_size=(result.final.shape[1], result.final.shape[0]),
        mask_area_ratio=result.line_maps.mask_area_ratio,
        tone_used_in_final=result.tone_used_in_final,
        upscaler_engine=result.upscaler_result.engine,
        upscaler_used_fallback=result.upscaler_result.used_fallback,
    )


def save_batch_summary_json(
    result: BatchResult,
    *,
    config: dict[str, Any],
    preset: str | None,
    invert: bool,
) -> Path:
    """Save a JSON summary for a batch run."""

    payload = {
        "schema_version": 1,
        "tool": {
            "name": "manga-lineart-upscaler",
            "version": __version__,
        },
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "input_dir": str(result.input_dir),
        "output_dir": str(result.output_dir),
        "preset": preset,
        "scale": int(config["pipeline"]["scale"]),
        "workers": result.workers,
        "invert": bool(invert),
        "total": result.total_count,
        "succeeded": result.succeeded_count,
        "failed": result.failed_count,
        "items": [batch_item_to_dict(item) for item in result.items],
    }
    result.summary_json_path.parent.mkdir(parents=True, exist_ok=True)
    with result.summary_json_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
    return result.summary_json_path


def save_batch_summary_csv(result: BatchResult) -> Path:
    """Save a CSV summary for a batch run."""

    result.summary_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with result.summary_csv_path.open("w", encoding="utf-8", newline="") as file:
        fieldnames = [
            "status",
            "input_path",
            "output_path",
            "run_json_path",
            "debug_dir",
            "error",
            "warnings",
            "input_width",
            "input_height",
            "output_width",
            "output_height",
            "mask_area_ratio",
            "tone_used_in_final",
            "upscaler_engine",
            "upscaler_used_fallback",
        ]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for item in result.items:
            row = batch_item_to_dict(item)
            row["warnings"] = "|".join(item.warnings)
            writer.writerow(row)
    return result.summary_csv_path


def batch_item_to_dict(item: BatchItemResult) -> dict[str, Any]:
    """Return a JSON/CSV friendly dict for one batch item."""

    return {
        "status": item.status,
        "input_path": str(item.input_path),
        "output_path": str(item.output_path),
        "run_json_path": str(item.run_json_path) if item.run_json_path is not None else "",
        "debug_dir": str(item.debug_dir) if item.debug_dir is not None else "",
        "error": item.error or "",
        "warnings": list(item.warnings),
        "input_width": item.input_size[0] if item.input_size is not None else None,
        "input_height": item.input_size[1] if item.input_size is not None else None,
        "output_width": item.output_size[0] if item.output_size is not None else None,
        "output_height": item.output_size[1] if item.output_size is not None else None,
        "mask_area_ratio": item.mask_area_ratio,
        "tone_used_in_final": item.tone_used_in_final,
        "upscaler_engine": item.upscaler_engine or "",
        "upscaler_used_fallback": item.upscaler_used_fallback,
    }
