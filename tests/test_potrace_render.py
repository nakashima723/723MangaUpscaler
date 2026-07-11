from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mlu.cli import main
from mlu.config import load_config
from mlu.pipeline import upscale_image
from mlu.potrace_render import (
    build_potrace_command,
    render_potrace_line_alpha,
    write_pbm,
)
from mlu.upscaler_external import ToolNotFoundError


def test_write_pbm_creates_file(tmp_path) -> None:
    mask = np.array([[False, True], [True, False]], dtype=np.bool_)
    path = write_pbm(mask, tmp_path / "mask.pbm")

    assert path.exists()
    assert path.read_bytes().startswith(b"P4")


def test_build_potrace_command_includes_configured_parameters(tmp_path) -> None:
    config = load_config(
        cli_overrides={
            "potrace": {
                "turdsize": 3,
                "alphamax": 0.8,
                "opttolerance": 0.15,
                "opticurve": False,
                "turnpolicy": "black",
            }
        }
    )

    command = build_potrace_command(
        executable="potrace",
        input_path=tmp_path / "in.pbm",
        output_path=tmp_path / "out.svg",
        config=config,
    )

    assert "--turdsize" in command
    assert "3" in command
    assert "--alphamax" in command
    assert "0.8" in command
    assert "--longcurve" in command
    assert "black" in command


def test_render_potrace_line_alpha_with_fake_tools(tmp_path) -> None:
    tools = _fake_potrace_tools(tmp_path)
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 2},
            "external_tools": {
                "potrace": str(tools["potrace"]),
                "cairosvg": str(tools["cairosvg"]),
            },
        }
    )
    mask = np.zeros((4, 5), dtype=np.bool_)
    mask[2, 1:4] = True

    result = render_potrace_line_alpha(mask, config)

    assert result.renderer == "potrace"
    assert result.line_alpha_hr.shape == (8, 10)
    assert result.line_alpha_hr.max() == pytest.approx(1.0)
    assert result.svg_text is not None
    assert "<svg" in result.svg_text
    assert result.sdf_reference_line_alpha_hr is not None
    assert result.renderer_metadata["rasterizer"] == "cairosvg"


def test_pipeline_potrace_renderer_writes_debug_svg_and_metadata(tmp_path) -> None:
    tools = _fake_potrace_tools(tmp_path)
    config_path = tmp_path / "tools.yaml"
    config_path.write_text(
        "\n".join(
            [
                "version: 1",
                "external_tools:",
                f"  potrace: {json.dumps(str(tools['potrace']))}",
                f"  cairosvg: {json.dumps(str(tools['cairosvg']))}",
            ]
        ),
        encoding="utf-8",
    )
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "out.png"
    debug_dir = tmp_path / "debug"
    image = np.full((4, 5), 255, dtype=np.uint8)
    image[2, 1:4] = 0
    Image.fromarray(image).save(input_path)

    exit_code = main(
        [
            "upscale",
            str(input_path),
            "-o",
            str(output_path),
            "--scale",
            "2",
            "--line-renderer",
            "potrace",
            "--config",
            str(config_path),
            "--debug-dir",
            str(debug_dir),
            "--overwrite",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    assert (debug_dir / "04_potrace.svg").exists()
    assert (debug_dir / "05_line_alpha_hr.png").exists()
    assert (debug_dir / "07_sdf_reference_line_alpha_hr.png").exists()
    metadata = json.loads(output_path.with_suffix(".mlus-run.json").read_text(encoding="utf-8"))
    assert metadata["config"]["pipeline"]["line_renderer"] == "potrace"
    assert metadata["renderer"]["renderer"] == "potrace"
    assert metadata["renderer"]["rasterizer"] == "cairosvg"


def test_potrace_renderer_reports_missing_tool(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "out.png"
    image = np.full((4, 5), 255, dtype=np.uint8)
    image[2, 1:4] = 0
    Image.fromarray(image).save(input_path)
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 2, "line_renderer": "potrace"},
            "external_tools": {"potrace": str(tmp_path / "missing-potrace.exe")},
            "io": {"overwrite": True},
        }
    )

    with pytest.raises(ToolNotFoundError, match="potrace executable does not exist"):
        upscale_image(input_path, output_path, config)


def _fake_potrace_tools(tmp_path: Path) -> dict[str, Path]:
    return {
        "potrace": _write_fake_tool(
            tmp_path,
            "fake_potrace",
            """
from pathlib import Path
import sys

args = sys.argv[1:]
out = Path(args[args.index("-o") + 1])
out.write_text(
    "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='8'></svg>",
    encoding="utf-8",
)
""".strip(),
        ),
        "cairosvg": _write_fake_tool(
            tmp_path,
            "fake_cairosvg",
            """
from pathlib import Path
import sys
from PIL import Image, ImageDraw

args = sys.argv[1:]
out = Path(args[args.index("-o") + 1])
width = int(args[args.index("--output-width") + 1])
height = int(args[args.index("--output-height") + 1])
image = Image.new("L", (width, height), 255)
draw = ImageDraw.Draw(image)
draw.line((1, height // 2, width - 2, height // 2), fill=0, width=2)
image.save(out)
""".strip(),
        ),
    }


def _write_fake_tool(tmp_path: Path, name: str, script: str) -> Path:
    script_path = tmp_path / f"{name}.py"
    script_path.write_text(script + "\n", encoding="utf-8")
    if os.name == "nt":
        wrapper = tmp_path / f"{name}.cmd"
        wrapper.write_text(
            f'@echo off\r\n"{sys.executable}" "{script_path}" %*\r\n',
            encoding="utf-8",
        )
    else:
        wrapper = tmp_path / name
        wrapper.write_text(
            f'#!/bin/sh\n"{sys.executable}" "{script_path}" "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    return wrapper
