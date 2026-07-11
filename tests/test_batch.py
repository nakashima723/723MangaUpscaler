from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image

from mlu.batch import (
    batch_debug_dir,
    batch_output_path,
    discover_input_images,
    parse_extensions,
)
from mlu.cli import main


def test_parse_extensions_normalizes_and_deduplicates() -> None:
    assert parse_extensions(".PNG, jpg, png") == ("png", "jpg")


def test_discover_input_images_is_recursive_and_sorted(tmp_path) -> None:
    input_dir = tmp_path / "input"
    nested = input_dir / "nested"
    nested.mkdir(parents=True)
    (input_dir / "b.png").write_bytes(b"png")
    (nested / "a.JPG").write_bytes(b"jpg")
    (input_dir / "ignored.txt").write_text("no", encoding="utf-8")

    paths = discover_input_images(input_dir, extensions=("png", "jpg"))

    assert [path.relative_to(input_dir).as_posix() for path in paths] == [
        "b.png",
        "nested/a.JPG",
    ]


def test_batch_path_helpers_preserve_relative_dirs() -> None:
    relative = batch_output_path("nested/input.jpg", "out", scale=4)
    debug = batch_debug_dir("nested/input.jpg", "debug")

    assert relative.as_posix() == "out/nested/input_x4.png"
    assert debug.as_posix() == "debug/nested/input"


def test_batch_processes_supported_images_and_writes_summaries(tmp_path) -> None:
    input_dir = tmp_path / "input"
    nested = input_dir / "nested"
    nested.mkdir(parents=True)
    image = np.full((4, 5), 255, dtype=np.uint8)
    image[2, :] = 0
    Image.fromarray(image).save(input_dir / "ok.png")
    Image.fromarray(image).save(nested / "also_ok.jpg", format="JPEG")
    (input_dir / "ignored.txt").write_text("not an image", encoding="utf-8")
    output_dir = tmp_path / "output"
    debug_dir = tmp_path / "debug"

    exit_code = main(
        [
            "batch",
            str(input_dir),
            str(output_dir),
            "--scale",
            "2",
            "--debug-dir",
            str(debug_dir),
            "--overwrite",
        ]
    )

    assert exit_code == 0
    assert (output_dir / "ok_x2.png").exists()
    assert (output_dir / "nested" / "also_ok_x2.png").exists()
    assert (debug_dir / "ok" / "00_input_gray.png").exists()
    assert (debug_dir / "nested" / "also_ok" / "00_input_gray.png").exists()

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["total"] == 2
    assert summary["succeeded"] == 2
    assert summary["failed"] == 0
    assert summary["workers"] == 1
    assert [item["status"] for item in summary["items"]] == ["ok", "ok"]
    assert summary["items"][0]["output_path"].endswith("ok_x2.png")
    assert summary["items"][0]["run_json_path"].endswith("also_ok_x2.mlus-run.json")
    assert summary["items"][0]["input_width"] == 5
    assert summary["items"][0]["input_height"] == 4
    assert summary["items"][0]["output_width"] == 10
    assert summary["items"][0]["output_height"] == 8
    assert summary["items"][0]["upscaler_engine"] == "none"

    with (output_dir / "summary.csv").open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 2
    assert rows[0]["status"] == "ok"
    assert rows[0]["output_width"] == "10"


def test_batch_continues_after_one_file_fails(tmp_path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    image = np.full((4, 5), 255, dtype=np.uint8)
    image[2, :] = 0
    Image.fromarray(image).save(input_dir / "ok.png")
    (input_dir / "broken.png").write_bytes(b"not a png")
    output_dir = tmp_path / "output"

    exit_code = main(
        [
            "batch",
            str(input_dir),
            str(output_dir),
            "--scale",
            "2",
            "--overwrite",
        ]
    )

    assert exit_code == 1
    assert (output_dir / "ok_x2.png").exists()
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["total"] == 2
    assert summary["succeeded"] == 1
    assert summary["failed"] == 1
    statuses = {Path(item["input_path"]).name: item["status"] for item in summary["items"]}
    assert statuses["ok.png"] == "ok"
    assert statuses["broken.png"] == "failed"
    ok_item = next(item for item in summary["items"] if item["status"] == "ok")
    assert ok_item["run_json_path"] == ""
    assert not (output_dir / "ok_x2.mlus-run.json").exists()
    broken = next(item for item in summary["items"] if item["status"] == "failed")
    assert "Could not read image" in broken["error"]
