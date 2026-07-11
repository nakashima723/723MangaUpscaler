from __future__ import annotations

import json
from pathlib import Path

from mlu.debug_layers import run_json_path, save_run_json


def test_run_json_path_replaces_output_suffix() -> None:
    assert run_json_path(Path("out.png")) == Path("out.mlus-run.json")
    assert run_json_path(Path("out")) == Path("out.mlus-run.json")


def test_save_run_json_writes_pretty_utf8_json(tmp_path) -> None:
    path = tmp_path / "nested" / "out.mlus-run.json"

    result = save_run_json(path, {"preset": "line_only", "warnings": ["thin line"]})

    assert result == path
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"preset": "line_only", "warnings": ["thin line"]}
