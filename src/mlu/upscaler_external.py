"""External grayscale upscaler adapter helpers."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from mlu.composite import white_canvas
from mlu.grayscale import FloatImage
from mlu.io import load_image, save_grayscale_png
from mlu.scales import SUPPORTED_SCALES, SUPPORTED_SCALES_TEXT
from mlu.sdf_render import resize_float_image

UPSCALER_ENGINES = {"none", "lanczos", "realcugan", "waifu2x", "realesrgan"}
EXTERNAL_ENGINES = {"realcugan", "waifu2x", "realesrgan"}

EXECUTABLE_NAMES = {
    "realcugan": "realcugan-ncnn-vulkan.exe",
    "waifu2x": "waifu2x-ncnn-vulkan.exe",
    "realesrgan": "realesrgan-ncnn-vulkan.exe",
}


class ToolNotFoundError(FileNotFoundError):
    """Raised when a requested external upscaler executable is unavailable."""


class ExternalUpscalerError(RuntimeError):
    """Raised when an external upscaler exits unsuccessfully."""

    def __init__(
        self,
        message: str,
        *,
        command: tuple[str, ...] = (),
        returncode: int | None = None,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@dataclass(frozen=True)
class UpscalerResult:
    """High-resolution tone image and execution diagnostics."""

    image: FloatImage
    requested_engine: str
    engine: str
    used_fallback: bool
    command: tuple[str, ...] = ()
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        """Return a JSON-serializable execution summary."""

        return {
            "requested_engine": self.requested_engine,
            "engine": self.engine,
            "used_fallback": self.used_fallback,
            "command": list(self.command),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error": self.error,
        }


def upscale_tone_source(tone_source: FloatImage, config: dict[str, Any]) -> UpscalerResult:
    """Upscale a source-resolution tone image according to `config`."""

    _validate_float_image(tone_source, name="tone_source")
    scale = int(config.get("pipeline", {}).get("scale", 4))
    if scale not in SUPPORTED_SCALES:
        raise ValueError(f"scale must be {SUPPORTED_SCALES_TEXT}.")

    upscaler_config = config.get("upscaler", {})
    engine = str(upscaler_config.get("engine", "none"))
    if engine not in UPSCALER_ENGINES:
        raise ValueError(f"Unsupported upscaler.engine: {engine}")

    if engine == "none":
        return UpscalerResult(
            image=white_canvas((tone_source.shape[0] * scale, tone_source.shape[1] * scale)),
            requested_engine=engine,
            engine=engine,
            used_fallback=False,
        )
    if engine == "lanczos":
        return _lanczos_result(tone_source, scale=scale, requested_engine=engine)

    try:
        return _run_external_upscaler(tone_source, config, engine=engine, scale=scale)
    except (ToolNotFoundError, ExternalUpscalerError) as exc:
        fallback = str(upscaler_config.get("fallback", "none"))
        if fallback == "lanczos":
            return _lanczos_result(
                tone_source,
                scale=scale,
                requested_engine=engine,
                used_fallback=True,
                error=str(exc),
                command=getattr(exc, "command", ()),
                returncode=getattr(exc, "returncode", None),
                stdout=getattr(exc, "stdout", ""),
                stderr=getattr(exc, "stderr", ""),
            )
        raise


def build_external_command(
    *,
    engine: str,
    executable: str,
    input_path: str | Path,
    output_path: str | Path,
    config: dict[str, Any],
) -> tuple[str, ...]:
    """Build an external upscaler command without executing it."""

    scale = int(config.get("pipeline", {}).get("scale", 4))
    upscaler_config = config.get("upscaler", {})
    engine_config = upscaler_config.get(engine, {})
    input_text = str(Path(input_path))
    output_text = str(Path(output_path))

    if engine == "realcugan":
        command = [
            executable,
            "-i",
            input_text,
            "-o",
            output_text,
            "-s",
            str(scale),
            "-n",
            str(int(engine_config.get("noise", -1))),
            "-t",
            str(int(engine_config.get("tile_size", 256))),
            "-f",
            "png",
        ]
    elif engine == "waifu2x":
        command = [
            executable,
            "-i",
            input_text,
            "-o",
            output_text,
            "-s",
            str(scale),
            "-n",
            str(int(engine_config.get("noise", -1))),
            "-t",
            str(int(engine_config.get("tile_size", 256))),
            "-m",
            str(engine_config.get("model", "models-cunet")),
            "-f",
            "png",
        ]
    elif engine == "realesrgan":
        command = [
            executable,
            "-i",
            input_text,
            "-o",
            output_text,
            "-n",
            str(engine_config.get("model", "realesrgan-x4plus-anime")),
            "-s",
            str(scale),
            "-t",
            str(int(engine_config.get("tile_size", 256))),
            "-f",
            "png",
        ]
    else:
        raise ValueError(f"Unsupported external upscaler engine: {engine}")
    return tuple(command)


def resolve_tool_path(engine: str, config: dict[str, Any]) -> str:
    """Resolve a configured or PATH-provided executable for an external engine."""

    if engine not in EXTERNAL_ENGINES:
        raise ValueError(f"Unsupported external upscaler engine: {engine}")

    configured = config.get("external_tools", {}).get(engine)
    if configured:
        path = Path(str(configured))
        if path.exists():
            return str(path)
        raise ToolNotFoundError(f"{engine} executable does not exist: {path}")

    executable = EXECUTABLE_NAMES[engine]
    found = shutil.which(executable)
    if found:
        return found
    raise ToolNotFoundError(f"{engine} executable is not configured and was not found on PATH.")


def _run_external_upscaler(
    tone_source: FloatImage,
    config: dict[str, Any],
    *,
    engine: str,
    scale: int,
) -> UpscalerResult:
    executable = resolve_tool_path(engine, config)
    with tempfile.TemporaryDirectory(prefix="mlu_upscale_") as temp_dir_text:
        temp_dir = Path(temp_dir_text)
        input_path = temp_dir / "tone_source.png"
        output_path = temp_dir / "tone_hr.png"
        save_grayscale_png(input_path, tone_source, bit_depth=8, overwrite=True)
        command = build_external_command(
            engine=engine,
            executable=executable,
            input_path=input_path,
            output_path=output_path,
            config=config,
        )
        completed = subprocess.run(command, capture_output=True, check=False, text=True)
        if completed.returncode != 0:
            raise ExternalUpscalerError(
                f"{engine} failed with exit code {completed.returncode}.",
                command=command,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        if not output_path.exists():
            raise ExternalUpscalerError(
                f"{engine} did not create output image.",
                command=command,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        image = load_image(output_path).array
        _validate_scaled_shape(image, tone_source.shape, scale=scale)
        return UpscalerResult(
            image=image,
            requested_engine=engine,
            engine=engine,
            used_fallback=False,
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def _lanczos_result(
    tone_source: FloatImage,
    *,
    scale: int,
    requested_engine: str,
    used_fallback: bool = False,
    error: str | None = None,
    command: tuple[str, ...] = (),
    returncode: int | None = None,
    stdout: str = "",
    stderr: str = "",
) -> UpscalerResult:
    image = resize_float_image(tone_source, scale=scale, interpolation="lanczos")
    return UpscalerResult(
        image=np.clip(image, 0.0, 1.0).astype(np.float32, copy=False),
        requested_engine=requested_engine,
        engine="lanczos",
        used_fallback=used_fallback,
        command=command,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        error=error,
    )


def _validate_scaled_shape(image: FloatImage, source_shape: tuple[int, int], *, scale: int) -> None:
    expected = (source_shape[0] * scale, source_shape[1] * scale)
    if image.shape != expected:
        raise ExternalUpscalerError(
            f"External upscaler output size must be {expected[1]}x{expected[0]}."
        )


def _validate_float_image(image: FloatImage, *, name: str) -> None:
    if image.ndim != 2:
        raise ValueError(f"{name} must be a 2D array.")
    if image.size == 0:
        raise ValueError(f"{name} must not be empty.")
    if not np.issubdtype(image.dtype, np.floating):
        raise ValueError(f"{name} must be a floating point array.")
    if not np.isfinite(image).all():
        raise ValueError(f"{name} must not contain NaN or Inf.")
    if float(image.min()) < 0.0 or float(image.max()) > 1.0:
        raise ValueError(f"{name} values must be in [0.0, 1.0].")
