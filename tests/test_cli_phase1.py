from __future__ import annotations

import json

import numpy as np
from PIL import Image

from mlu.cli import main


def test_upscale_writes_scaled_final_png(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    image = np.full((2, 3), 255, dtype=np.uint8)
    image[1, :] = 0
    Image.fromarray(image).save(input_path)

    exit_code = main(
        [
            "upscale",
            str(input_path),
            "-o",
            str(output_path),
            "--scale",
            "2",
        ]
    )

    assert exit_code == 0
    run_json = output_path.with_suffix(".mlus-run.json")
    assert not run_json.exists()
    with Image.open(output_path) as output:
        assert output.mode == "L"
        assert output.size == (6, 4)


def test_inspect_writes_input_gray_debug_layer(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    debug_dir = tmp_path / "debug"
    Image.fromarray(np.array([[0, 255]], dtype=np.uint8)).save(input_path)

    exit_code = main(["inspect", str(input_path), "--debug-dir", str(debug_dir)])

    assert exit_code == 0
    assert (debug_dir / "00_input_gray.png").exists()
    assert (debug_dir / "01_darkness.png").exists()
    assert (debug_dir / "02_line_prob.png").exists()
    assert (debug_dir / "03_line_mask.png").exists()
    assert (debug_dir / "04_sdf_hr_preview.png").exists()
    assert (debug_dir / "05_line_alpha_hr.png").exists()
    assert (debug_dir / "06_final.png").exists()
    assert (debug_dir / "06_final.mlus-run.json").exists()


def test_upscale_records_invert_in_run_json(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    Image.fromarray(np.array([[0, 255]], dtype=np.uint8)).save(input_path)

    exit_code = main(
        [
            "upscale",
            str(input_path),
            "-o",
            str(output_path),
            "--invert",
            "--save-run-json",
        ]
    )

    assert exit_code == 0
    metadata = json.loads(output_path.with_suffix(".mlus-run.json").read_text(encoding="utf-8"))
    assert metadata["input"]["invert"] is True


def test_upscale_can_override_line_stabilizer_settings(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    Image.fromarray(np.array([[0, 255], [255, 0]], dtype=np.uint8)).save(input_path)

    exit_code = main(
        [
            "upscale",
            str(input_path),
            "-o",
            str(output_path),
            "--disable-line-stabilizer",
            "--line-stabilizer-strength",
            "0.55",
            "--save-run-json",
        ]
    )

    assert exit_code == 0
    metadata = json.loads(output_path.with_suffix(".mlus-run.json").read_text(encoding="utf-8"))
    assert metadata["config"]["line_stabilizer"]["enabled"] is False
    assert metadata["config"]["line_stabilizer"]["strength"] == 0.55


def test_upscale_line_stabilizer_strength_alone_keeps_experimental_feature_disabled(
    tmp_path,
) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    Image.fromarray(np.array([[0, 255], [255, 0]], dtype=np.uint8)).save(input_path)

    exit_code = main(
        [
            "upscale",
            str(input_path),
            "-o",
            str(output_path),
            "--line-stabilizer-strength",
            "0.55",
            "--save-run-json",
        ]
    )

    assert exit_code == 0
    metadata = json.loads(output_path.with_suffix(".mlus-run.json").read_text(encoding="utf-8"))
    assert metadata["config"]["line_stabilizer"]["enabled"] is False
    assert metadata["config"]["line_stabilizer"]["strength"] == 0.55


def test_upscale_can_override_directional_smoothing_settings(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    Image.fromarray(np.array([[0, 255], [255, 0]], dtype=np.uint8)).save(input_path)

    exit_code = main(
        [
            "upscale",
            str(input_path),
            "-o",
            str(output_path),
            "--disable-directional-smoothing",
            "--directional-smoothing-strength",
            "0.25",
            "--directional-smoothing-radius-hr-px",
            "1",
            "--directional-smoothing-min-angle-from-axis-degrees",
            "12",
            "--directional-smoothing-full-strength-angle-from-axis-degrees",
            "30",
            "--save-run-json",
        ]
    )

    assert exit_code == 0
    metadata = json.loads(output_path.with_suffix(".mlus-run.json").read_text(encoding="utf-8"))
    assert metadata["config"]["directional_smoothing"]["enabled"] is False
    assert metadata["config"]["directional_smoothing"]["strength"] == 0.25
    assert metadata["config"]["directional_smoothing"]["radius_hr_px"] == 1
    assert metadata["config"]["directional_smoothing"]["min_angle_from_axis_degrees"] == 12
    assert (
        metadata["config"]["directional_smoothing"]["full_strength_angle_from_axis_degrees"] == 30
    )
    assert metadata["directional_smoothing"]["applied"] is False


def test_upscale_can_override_sdf_distance_source_and_threshold(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    Image.fromarray(np.array([[0, 255], [255, 0]], dtype=np.uint8)).save(input_path)

    exit_code = main(
        [
            "upscale",
            str(input_path),
            "-o",
            str(output_path),
            "--sdf-distance-source",
            "binary_mask",
            "--soft-sdf-threshold",
            "0.25",
            "--save-run-json",
        ]
    )

    assert exit_code == 0
    metadata = json.loads(output_path.with_suffix(".mlus-run.json").read_text(encoding="utf-8"))
    assert metadata["config"]["sdf"]["distance_source"] == "binary_mask"
    assert metadata["config"]["sdf"]["soft_sdf_threshold"] == 0.25


def test_upscale_can_override_line_soft_coverage_settings(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    Image.fromarray(np.array([[0, 255], [255, 0]], dtype=np.uint8)).save(input_path)

    exit_code = main(
        [
            "upscale",
            str(input_path),
            "-o",
            str(output_path),
            "--line-soft-coverage-mode",
            "max_probability",
            "--line-soft-coverage-gamma",
            "1.2",
            "--save-run-json",
        ]
    )

    assert exit_code == 0
    metadata = json.loads(output_path.with_suffix(".mlus-run.json").read_text(encoding="utf-8"))
    assert metadata["config"]["mask"]["soft_coverage"]["mode"] == "max_probability"
    assert metadata["config"]["mask"]["soft_coverage"]["gamma"] == 1.2


def test_upscale_can_override_tone_upscaler(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    Image.fromarray(np.array([[0, 255], [255, 0]], dtype=np.uint8)).save(input_path)

    exit_code = main(
        [
            "upscale",
            str(input_path),
            "-o",
            str(output_path),
            "--upscaler",
            "lanczos",
            "--upscaler-fallback",
            "none",
            "--tone-usage",
            "always",
            "--save-run-json",
        ]
    )

    assert exit_code == 0
    metadata = json.loads(output_path.with_suffix(".mlus-run.json").read_text(encoding="utf-8"))
    assert metadata["config"]["upscaler"]["engine"] == "lanczos"
    assert metadata["config"]["upscaler"]["fallback"] == "none"
    assert metadata["config"]["composite"]["tone_usage"] == "always"
    assert metadata["upscaler"]["engine"] == "lanczos"


def test_upscale_can_override_tone_usage(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    Image.fromarray(np.array([[0, 255], [255, 0]], dtype=np.uint8)).save(input_path)

    exit_code = main(
        [
            "upscale",
            str(input_path),
            "-o",
            str(output_path),
            "--tone-usage",
            "never",
            "--save-run-json",
        ]
    )

    assert exit_code == 0
    metadata = json.loads(output_path.with_suffix(".mlus-run.json").read_text(encoding="utf-8"))
    assert metadata["config"]["composite"]["tone_usage"] == "never"
    assert metadata["tone_composite"]["tone_usage"] == "never"
    assert metadata["tone_composite"]["used_tone_hr"] is False


def test_upscale_can_enable_experimental_line_stabilizer(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    Image.fromarray(np.array([[0, 255], [255, 0]], dtype=np.uint8)).save(input_path)

    exit_code = main(
        [
            "upscale",
            str(input_path),
            "-o",
            str(output_path),
            "--enable-line-stabilizer",
            "--save-run-json",
        ]
    )

    assert exit_code == 0
    metadata = json.loads(output_path.with_suffix(".mlus-run.json").read_text(encoding="utf-8"))
    assert metadata["config"]["line_stabilizer"]["enabled"] is True


def test_upscale_rejects_existing_output_without_overwrite(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    Image.fromarray(np.array([[0, 255]], dtype=np.uint8)).save(input_path)
    output_path.write_bytes(b"already here")

    try:
        main(["upscale", str(input_path), "-o", str(output_path)])
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("Expected SystemExit")
