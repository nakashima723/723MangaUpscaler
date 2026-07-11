from __future__ import annotations

from mlu.cli import build_parser, main


def test_main_without_args_prints_help(capsys) -> None:
    assert main([]) == 0

    captured = capsys.readouterr()
    assert "Local line-art upscaler" in captured.out
    assert "upscale" in captured.out


def test_parser_exposes_mvp_commands() -> None:
    help_text = build_parser().format_help()

    assert "upscale" in help_text
    assert "inspect" in help_text
    assert "doctor" in help_text


def test_doctor_prints_external_tool_status(capsys) -> None:
    assert main(["doctor"]) == 0

    captured = capsys.readouterr()
    assert "External tools:" in captured.out
    assert "realcugan" in captured.out
    assert "waifu2x" in captured.out
    assert "realesrgan" in captured.out
