from __future__ import annotations

import json

import numpy as np
from PIL import Image

from mlu.cli import main
from mlu.compare import _compose_horizontal_sheet, dotted_override, load_compare_variants


def test_dotted_override_builds_nested_config() -> None:
    assert dotted_override("sdf.width_bias_source_px", -0.25) == {
        "sdf": {"width_bias_source_px": -0.25}
    }
    assert dotted_override("directional_smoothing.strength", 0.75) == {
        "directional_smoothing": {"strength": 0.75}
    }


def test_load_compare_variants_expands_parameter_grid(tmp_path) -> None:
    grid_path = tmp_path / "grid.yaml"
    grid_path.write_text(
        """
version: 1
base:
  composite:
    edge_alpha_gamma: 1.1
parameters:
  sdf.width_bias_source_px:
    - -0.25
    - 0.0
  sdf.soft_sdf_threshold:
    - 0.25
""".strip(),
        encoding="utf-8",
    )

    variants = load_compare_variants(grid_path)

    assert len(variants) == 2
    assert variants[0].name == "sdf.width_bias_source_px_m0p25__sdf.soft_sdf_threshold_0p25"
    assert variants[0].overrides["composite"]["edge_alpha_gamma"] == 1.1
    assert variants[0].overrides["sdf"]["width_bias_source_px"] == -0.25
    assert variants[0].overrides["sdf"]["soft_sdf_threshold"] == 0.25
    assert variants[1].overrides["sdf"]["width_bias_source_px"] == 0.0


def test_compare_command_writes_variants_sheets_and_summary(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    image = np.full((8, 10), 255, dtype=np.uint8)
    image[4, 1:9] = 0
    Image.fromarray(image).save(input_path)
    grid_path = tmp_path / "grid.yaml"
    grid_path.write_text(
        """
version: 1
variants:
  - name: thin
    overrides:
      sdf:
        width_bias_source_px: -0.25
  - name: default
    overrides: {}
""".strip(),
        encoding="utf-8",
    )
    output_dir = tmp_path / "compare"

    exit_code = main(
        [
            "compare",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--grid",
            str(grid_path),
            "--scale",
            "2",
            "--crop-source-size",
            "4",
            "--thumbnail-width",
            "12",
            "--overwrite",
        ]
    )

    assert exit_code == 0
    assert (output_dir / "variants" / "01_thin.png").exists()
    assert (output_dir / "variants" / "02_default.png").exists()
    assert (output_dir / "contact_sheet.png").exists()
    assert (output_dir / "center_crop_1x.png").exists()
    assert (output_dir / "center_crop_200pct.png").exists()
    assert (output_dir / "compare-summary.json").exists()

    with Image.open(output_dir / "center_crop_1x.png") as crop_1x:
        assert crop_1x.width > 0
        assert crop_1x.height > 0
    with Image.open(output_dir / "center_crop_200pct.png") as crop_200:
        assert crop_200.width > crop_1x.width
        assert crop_200.height > crop_1x.height

    summary = json.loads((output_dir / "compare-summary.json").read_text(encoding="utf-8"))
    assert [item["name"] for item in summary["items"]] == ["thin", "default"]
    assert summary["items"][0]["output_path"].endswith("01_thin.png")
    assert summary["items"][0]["run_json_path"].endswith("01_thin.mlus-run.json")


def test_binary_sheet_composition_thresholds_antialiased_labels() -> None:
    binary = Image.fromarray(np.array([[0, 255], [255, 0]], dtype=np.uint8))

    sheet = _compose_horizontal_sheet([("binary", binary)], force_binary=True)

    assert set(sheet.getdata()).issubset({0, 255})
