"""Potrace-based optional line renderer."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from mlu.grayscale import FloatImage
from mlu.io import load_image
from mlu.mask_extract import BoolImage
from mlu.scales import SUPPORTED_SCALES, SUPPORTED_SCALES_TEXT
from mlu.sdf_render import SDFRenderResult, render_line_alpha, signed_distance_field
from mlu.upscaler_external import ExternalUpscalerError, ToolNotFoundError

TOOL_EXECUTABLE_NAMES = {
    "potrace": ("potrace", "potrace.exe"),
    "cairosvg": ("cairosvg", "cairosvg.exe"),
    "inkscape": ("inkscape", "inkscape.exe"),
}


def render_potrace_line_alpha(
    line_mask: BoolImage,
    config: dict[str, Any],
    *,
    line_soft: FloatImage | None = None,
) -> SDFRenderResult:
    """Render high-resolution line alpha through Potrace and an SVG rasterizer."""

    scale = int(config.get("pipeline", {}).get("scale", 4))
    if scale not in SUPPORTED_SCALES:
        raise ValueError(f"scale must be {SUPPORTED_SCALES_TEXT}.")

    height, width = line_mask.shape
    target_size = (width * scale, height * scale)
    potrace_executable = resolve_renderer_tool("potrace", config)
    rasterizer = str(config.get("potrace", {}).get("rasterizer", "cairosvg"))
    rasterizer_executable = resolve_renderer_tool(rasterizer, config)

    with tempfile.TemporaryDirectory(prefix="mlu_potrace_") as temp_dir_text:
        temp_dir = Path(temp_dir_text)
        pbm_path = temp_dir / "line_mask.pbm"
        svg_path = temp_dir / "line_mask.svg"
        png_path = temp_dir / "line_alpha.png"

        write_pbm(line_mask, pbm_path)
        potrace_command = build_potrace_command(
            executable=potrace_executable,
            input_path=pbm_path,
            output_path=svg_path,
            config=config,
        )
        potrace_completed = subprocess.run(
            potrace_command,
            capture_output=True,
            check=False,
            text=True,
        )
        _check_external_result(
            "potrace",
            svg_path,
            potrace_command,
            potrace_completed,
        )

        rasterize_command = build_rasterize_command(
            rasterizer=rasterizer,
            executable=rasterizer_executable,
            input_path=svg_path,
            output_path=png_path,
            target_size=target_size,
        )
        rasterize_completed = subprocess.run(
            rasterize_command,
            capture_output=True,
            check=False,
            text=True,
        )
        _check_external_result(
            rasterizer,
            png_path,
            rasterize_command,
            rasterize_completed,
        )

        svg_text = svg_path.read_text(encoding="utf-8", errors="replace")
        alpha = load_potrace_alpha(png_path, target_size=target_size)

    sdf_reference = render_sdf_reference(line_mask, config, line_soft=line_soft)
    return SDFRenderResult(
        sdf=signed_distance_field(line_mask),
        sdf_hr=np.zeros_like(alpha, dtype=np.float32),
        line_alpha_hr=alpha,
        line_soft_hr=None,
        line_geometry_hr=None,
        sdf_reference_line_alpha_hr=sdf_reference,
        line_segments=(),
        renderer="potrace",
        svg_text=svg_text,
        renderer_metadata={
            "renderer": "potrace",
            "rasterizer": rasterizer,
            "potrace": {
                "command": list(potrace_command),
                "returncode": potrace_completed.returncode,
                "stdout": potrace_completed.stdout,
                "stderr": potrace_completed.stderr,
            },
            "rasterize": {
                "command": list(rasterize_command),
                "returncode": rasterize_completed.returncode,
                "stdout": rasterize_completed.stdout,
                "stderr": rasterize_completed.stderr,
            },
        },
    )


def write_pbm(line_mask: BoolImage, path: str | Path) -> Path:
    """Write a boolean line mask as PBM with black line pixels."""

    if line_mask.ndim != 2 or line_mask.dtype != np.bool_:
        raise ValueError("line_mask must be a 2D boolean array.")
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(np.where(line_mask, 0, 255).astype(np.uint8))
    image.convert("1").save(output_path, format="PPM")
    return output_path


def render_sdf_reference(
    line_mask: BoolImage,
    config: dict[str, Any],
    *,
    line_soft: FloatImage | None,
) -> FloatImage:
    """Render an SDF reference alpha for Potrace debug comparison."""

    if line_soft is not None:
        return render_line_alpha(line_mask, config, line_soft=line_soft).line_alpha_hr

    reference_config = {
        **config,
        "sdf": {
            **config.get("sdf", {}),
            "distance_source": "binary_mask",
            "soft_alpha_mode": "none",
            "soft_gain": 0.0,
        },
    }
    return render_line_alpha(line_mask, reference_config).line_alpha_hr


def load_potrace_alpha(path: str | Path, *, target_size: tuple[int, int]) -> FloatImage:
    """Load a rasterized black-on-white Potrace image as line alpha."""

    image = load_image(path).array
    expected_shape = (target_size[1], target_size[0])
    if image.shape != expected_shape:
        raise ExternalUpscalerError(
            f"Potrace rasterizer output size must be {target_size[0]}x{target_size[1]}."
        )
    return np.clip(np.float32(1.0) - image, 0.0, 1.0).astype(np.float32, copy=False)


def build_potrace_command(
    *,
    executable: str,
    input_path: str | Path,
    output_path: str | Path,
    config: dict[str, Any],
) -> tuple[str, ...]:
    """Build a Potrace command without executing it."""

    potrace_config = config.get("potrace", {})
    command = [
        executable,
        str(Path(input_path)),
        "-s",
        "-o",
        str(Path(output_path)),
        "--turdsize",
        str(int(potrace_config.get("turdsize", 2))),
        "--alphamax",
        str(float(potrace_config.get("alphamax", 1.0))),
        "--opttolerance",
        str(float(potrace_config.get("opttolerance", 0.2))),
        "--turnpolicy",
        str(potrace_config.get("turnpolicy", "minority")),
    ]
    if not bool(potrace_config.get("opticurve", True)):
        command.append("--longcurve")
    return tuple(command)


def build_rasterize_command(
    *,
    rasterizer: str,
    executable: str,
    input_path: str | Path,
    output_path: str | Path,
    target_size: tuple[int, int],
) -> tuple[str, ...]:
    """Build an SVG rasterizer command without executing it."""

    width, height = target_size
    if rasterizer == "cairosvg":
        return (
            executable,
            str(Path(input_path)),
            "-o",
            str(Path(output_path)),
            "--output-width",
            str(width),
            "--output-height",
            str(height),
        )
    if rasterizer == "inkscape":
        return (
            executable,
            str(Path(input_path)),
            "--export-type=png",
            f"--export-filename={Path(output_path)}",
            f"--export-width={width}",
            f"--export-height={height}",
        )
    raise ValueError(f"Unsupported potrace.rasterizer: {rasterizer}")


def resolve_renderer_tool(tool_name: str, config: dict[str, Any]) -> str:
    """Resolve a configured or PATH-provided renderer executable."""

    if tool_name not in TOOL_EXECUTABLE_NAMES:
        raise ValueError(f"Unsupported renderer tool: {tool_name}")

    configured = config.get("external_tools", {}).get(tool_name)
    if configured:
        path = Path(str(configured))
        if path.exists():
            return str(path)
        raise ToolNotFoundError(f"{tool_name} executable does not exist: {path}")

    for executable in TOOL_EXECUTABLE_NAMES[tool_name]:
        found = shutil.which(executable)
        if found:
            return found
    names = ", ".join(TOOL_EXECUTABLE_NAMES[tool_name])
    raise ToolNotFoundError(
        f"{tool_name} executable is not configured and was not found on PATH ({names})."
    )


def _check_external_result(
    engine: str,
    output_path: Path,
    command: tuple[str, ...],
    completed: subprocess.CompletedProcess[str],
) -> None:
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
            f"{engine} did not create output file.",
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
