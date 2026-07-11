from __future__ import annotations

import subprocess

import numpy as np
import pytest

from mlu.config import load_config
from mlu.io import save_grayscale_png
from mlu.upscaler_external import (
    ExternalUpscalerError,
    ToolNotFoundError,
    build_external_command,
    resolve_tool_path,
    upscale_tone_source,
)


def _tone_source() -> np.ndarray:
    return np.array(
        [
            [1.0, 0.75],
            [0.25, 0.0],
        ],
        dtype=np.float32,
    )


def _config(**overrides: object) -> dict:
    return load_config(
        cli_overrides={
            "pipeline": {"scale": 2},
            "upscaler": {
                "engine": "none",
                "fallback": "none",
                "realcugan": {"noise": -1, "tile_size": 128},
                "waifu2x": {"noise": 0, "model": "models-cunet", "tile_size": 64},
                "realesrgan": {"model": "realesrgan-x4plus-anime", "tile_size": 256},
            },
            **overrides,
        }
    )


def test_none_engine_returns_white_canvas() -> None:
    result = upscale_tone_source(_tone_source(), _config())

    assert result.engine == "none"
    assert result.image.shape == (4, 4)
    assert np.allclose(result.image, 1.0)


def test_lanczos_engine_resizes_tone_source() -> None:
    result = upscale_tone_source(_tone_source(), _config(upscaler={"engine": "lanczos"}))

    assert result.engine == "lanczos"
    assert result.image.shape == (4, 4)
    assert 0.0 <= float(result.image.min()) <= float(result.image.max()) <= 1.0


def test_missing_external_tool_falls_back_to_lanczos() -> None:
    config = _config(
        upscaler={"engine": "realcugan", "fallback": "lanczos"},
        external_tools={"realcugan": "Z:/missing/realcugan.exe"},
    )

    result = upscale_tone_source(_tone_source(), config)

    assert result.requested_engine == "realcugan"
    assert result.engine == "lanczos"
    assert result.used_fallback is True
    assert "does not exist" in str(result.error)


def test_missing_external_tool_without_fallback_raises() -> None:
    config = _config(
        upscaler={"engine": "realcugan", "fallback": "none"},
        external_tools={"realcugan": "Z:/missing/realcugan.exe"},
    )

    with pytest.raises(ToolNotFoundError):
        upscale_tone_source(_tone_source(), config)


def test_external_command_failure_falls_back_and_records_stderr(monkeypatch, tmp_path) -> None:
    tool_path = tmp_path / "realcugan.exe"
    tool_path.write_text("fake", encoding="utf-8")
    config = _config(
        upscaler={"engine": "realcugan", "fallback": "lanczos"},
        external_tools={"realcugan": str(tool_path)},
    )

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=7, stdout="out", stderr="bad")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = upscale_tone_source(_tone_source(), config)

    assert result.engine == "lanczos"
    assert result.used_fallback is True
    assert result.returncode == 7
    assert result.stdout == "out"
    assert result.stderr == "bad"
    assert "exit code 7" in str(result.error)


def test_external_command_success_loads_output(monkeypatch, tmp_path) -> None:
    tool_path = tmp_path / "waifu2x.exe"
    tool_path.write_text("fake", encoding="utf-8")
    config = _config(
        upscaler={"engine": "waifu2x", "fallback": "none"},
        external_tools={"waifu2x": str(tool_path)},
    )

    def fake_run(command, **kwargs):
        output_path = command[command.index("-o") + 1]
        save_grayscale_png(output_path, np.ones((4, 4), dtype=np.float32) * 0.5, overwrite=True)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = upscale_tone_source(_tone_source(), config)

    assert result.engine == "waifu2x"
    assert result.used_fallback is False
    assert result.returncode == 0
    assert result.stdout == "ok"
    assert result.image.shape == (4, 4)
    assert result.command[0] == str(tool_path)


def test_build_external_commands_use_list_style_arguments(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    config = _config()

    realcugan = build_external_command(
        engine="realcugan",
        executable="realcugan.exe",
        input_path=input_path,
        output_path=output_path,
        config=config,
    )
    waifu2x = build_external_command(
        engine="waifu2x",
        executable="waifu2x.exe",
        input_path=input_path,
        output_path=output_path,
        config=config,
    )
    realesrgan = build_external_command(
        engine="realesrgan",
        executable="realesrgan.exe",
        input_path=input_path,
        output_path=output_path,
        config=config,
    )

    assert realcugan[:5] == ("realcugan.exe", "-i", str(input_path), "-o", str(output_path))
    assert "-m" not in realcugan
    assert "-m" in waifu2x
    assert "-n" in realesrgan


def test_resolve_tool_path_rejects_missing_configured_path() -> None:
    config = _config(external_tools={"realesrgan": "Z:/missing/realesrgan.exe"})

    with pytest.raises(ToolNotFoundError, match="does not exist"):
        resolve_tool_path("realesrgan", config)


def test_external_output_wrong_size_raises(monkeypatch, tmp_path) -> None:
    tool_path = tmp_path / "realesrgan.exe"
    tool_path.write_text("fake", encoding="utf-8")
    config = _config(
        upscaler={"engine": "realesrgan", "fallback": "none"},
        external_tools={"realesrgan": str(tool_path)},
    )

    def fake_run(command, **kwargs):
        output_path = command[command.index("-o") + 1]
        save_grayscale_png(output_path, np.ones((3, 3), dtype=np.float32), overwrite=True)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ExternalUpscalerError, match="output size"):
        upscale_tone_source(_tone_source(), config)
