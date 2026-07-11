from __future__ import annotations

import json

import numpy as np
from PIL import Image, ImageDraw

from mlu.composite import composite_black_lines, white_canvas
from mlu.config import load_config
from mlu.pipeline import upscale_image


def _line_fixture(path) -> None:
    image = np.full((8, 10), 255, dtype=np.uint8)
    image[4, 1:9] = 0
    image[1:7, 5] = 0
    Image.fromarray(image).save(path)


def test_pipeline_outputs_scaled_final_png_for_each_mvp_scale(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    _line_fixture(input_path)

    for scale in (2, 3, 4, 6, 8):
        output_path = tmp_path / f"out_x{scale}.png"
        config = load_config(
            cli_overrides={
                "pipeline": {"scale": scale},
                "io": {"overwrite": True},
            }
        )

        result = upscale_image(input_path, output_path, config)

        assert result.final.shape == (8 * scale, 10 * scale)
        assert result.run_json_path is None
        assert not output_path.with_suffix(".mlus-run.json").exists()
        with Image.open(output_path) as output:
            assert output.mode == "L"
            assert output.size == (10 * scale, 8 * scale)


def test_pipeline_can_enable_run_json_for_debugging(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "out.png"
    _line_fixture(input_path)
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 2},
            "io": {"overwrite": True},
            "debug": {"save_run_json": True},
        }
    )

    result = upscale_image(input_path, output_path, config)

    assert result.run_json_path == output_path.with_suffix(".mlus-run.json")
    assert result.run_json_path.exists()
    metadata = json.loads(result.run_json_path.read_text(encoding="utf-8"))
    assert metadata["run"]["preset"] == "line_only"
    assert metadata["run"]["scale"] == 2
    assert metadata["config"]["sdf"]["distance_source"] == "soft_mask_hr"
    assert metadata["config"]["line_stabilizer"]["enabled"] is False
    assert metadata["config"]["directional_smoothing"]["enabled"] is False
    assert metadata["upscaler"]["engine"] == "none"
    assert metadata["renderer"]["alpha_fast_path"] is True
    assert metadata["renderer"]["high_resolution_edt_count"] == 0
    assert "line_soft_hr_mean" in metadata["sdf_diagnostics"]
    assert result.sdf_result.sdf is None
    assert result.sdf_result.sdf_hr is None


def test_pipeline_writes_debug_layers(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "out.png"
    debug_dir = tmp_path / "debug"
    _line_fixture(input_path)
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 2},
            "directional_smoothing": {"enabled": False},
            "io": {"overwrite": True},
        }
    )

    result = upscale_image(input_path, output_path, config, debug_dir=debug_dir)

    expected = [
        "00_input_gray.png",
        "01_darkness.png",
        "02_line_prob.png",
        "03_line_mask.png",
        "04_sdf_hr_preview.png",
        "05_line_alpha_hr.png",
        "06_final.png",
        "07_line_soft_hr.png",
        "08_soft_mask_hr.png",
        "09_sdf_alpha_before_soft_mode_hr.png",
    ]
    assert [path.name for path in result.debug_paths] == expected
    assert all((debug_dir / name).exists() for name in expected)
    assert not (debug_dir / "07_line_geometry_hr.png").exists()
    assert result.run_json_path == output_path.with_suffix(".mlus-run.json")
    metadata = json.loads(result.run_json_path.read_text(encoding="utf-8"))
    assert metadata["debug"]["paths"] == [str(debug_dir / name) for name in expected]
    assert metadata["sdf_diagnostics"]["soft_sdf_threshold"] == 0.22
    assert "soft_mask_hr_area_ratio" in metadata["sdf_diagnostics"]


def test_pipeline_writes_tone_source_debug_layer_for_lift_lines(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "out.png"
    debug_dir = tmp_path / "debug"
    _line_fixture(input_path)
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 2, "tone_mode": "lift_lines"},
            "tone_source": {
                "mode": "lift_lines",
                "dilate_radius": 1.2,
                "lift_strength": 0.85,
                "background_blur_radius": 1.5,
                "protect_midtones": True,
            },
            "upscaler": {"engine": "none"},
            "directional_smoothing": {"enabled": False},
            "io": {"overwrite": True},
        }
    )

    result = upscale_image(input_path, output_path, config, debug_dir=debug_dir)

    expected_prefix = [
        "00_input_gray.png",
        "01_darkness.png",
        "02_line_prob.png",
        "03_line_mask.png",
        "04_sdf_hr_preview.png",
        "05_line_alpha_hr.png",
        "06_final.png",
        "07_tone_source.png",
    ]
    names = [path.name for path in result.debug_paths]
    assert names[: len(expected_prefix)] == expected_prefix
    assert any(name.endswith("_line_soft_hr.png") for name in names)
    assert any(name.endswith("_soft_mask_hr.png") for name in names)
    assert result.tone_source_result.mode == "lift_lines"
    assert result.tone_source_result.line_lift_ratio > 0.0
    metadata = json.loads(result.run_json_path.read_text(encoding="utf-8"))
    assert metadata["tone_source"]["mode"] == "lift_lines"
    assert metadata["tone_source"]["line_lift_ratio"] > 0.0


def test_pipeline_writes_directional_smoothing_debug_layers(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "out.png"
    debug_dir = tmp_path / "debug"
    image = np.full((24, 24), 255, dtype=np.uint8)
    for x in range(4, 20):
        y = 6 + int(round(0.55 * (x - 4))) + (1 if (x // 3) % 2 else -1)
        image[max(0, y - 1) : min(24, y + 2), x] = 0
    Image.fromarray(image).save(input_path)
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 4},
            "directional_smoothing": {
                "enabled": True,
                "strength": 1.0,
                "radius_hr_px": 3,
                "min_orientation_confidence": 0.05,
                "min_gradient_energy": 1.0e-6,
            },
            "io": {"overwrite": True},
        }
    )

    result = upscale_image(input_path, output_path, config, debug_dir=debug_dir)

    names = [path.name for path in result.debug_paths]
    assert any(name.endswith("_directional_smoothing_source_alpha_hr.png") for name in names)
    assert any(name.endswith("_directional_smoothing_weight_hr.png") for name in names)
    assert any(name.endswith("_directional_smoothing_delta_hr.png") for name in names)
    metadata = json.loads(result.run_json_path.read_text(encoding="utf-8"))
    assert metadata["directional_smoothing"]["applied"] is True
    assert metadata["directional_smoothing"]["changed_pixel_ratio"] > 0.0


def test_pipeline_writes_centerline_and_component_rollback_debug_layers(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "out.png"
    debug_dir = tmp_path / "debug"
    image = np.full((32, 48), 255, dtype=np.uint8)
    points = []
    for x in range(4, 44):
        y = 12 + x // 8
        points.append((x, y))
    pil_image = Image.fromarray(image)
    ImageDraw.Draw(pil_image).line(points, fill=0, width=3)
    pil_image.save(input_path)
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 4},
            "centerline_simplification": {
                "enabled": True,
                "filter_sigma_source_px": 0.75,
                "strength": 1.0,
                "min_path_length_source_px": 8.0,
                "endpoint_protection_source_px": 2.0,
                "long_stroke_gate": {"enabled": False},
            },
            "io": {"overwrite": True},
        }
    )

    result = upscale_image(input_path, output_path, config, debug_dir=debug_dir)

    names = [path.name for path in result.debug_paths]
    assert any(name.endswith("_centerline_source.png") for name in names)
    assert any(name.endswith("_long_stroke_eligible_source.png") for name in names)
    assert any(name.endswith("_component_rollback_source.png") for name in names)
    assert any(name.endswith("_filtered_centerline_source.png") for name in names)
    assert any(
        name.endswith("_centerline_filter_displacement_source.png") for name in names
    )
    assert any(name.endswith("_centerline_protected_source.png") for name in names)
    metadata = json.loads(result.run_json_path.read_text(encoding="utf-8"))
    assert metadata["centerline_simplification"]["applied"] is True
    assert metadata["centerline_simplification"]["filtered_path_count"] >= 1
    assert metadata["centerline_simplification"]["component_rollback"][
        "accepted_component_count"
    ] >= 1
    assert metadata["centerline_simplification"][
        "fractional_pixel_ratio_after_binarization"
    ] == 0.0
    assert set(np.unique(result.final)).issubset({0.0, 1.0})


def test_pipeline_uses_lanczos_fallback_for_missing_external_upscaler(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "out.png"
    debug_dir = tmp_path / "debug"
    image = np.full((8, 10), 255, dtype=np.uint8)
    image[4, 1:9] = 0
    image[0:2, :] = 210
    Image.fromarray(image).save(input_path)
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 2, "tone_mode": "lift_lines"},
            "tone_source": {"mode": "lift_lines"},
            "upscaler": {"engine": "realcugan", "fallback": "lanczos"},
            "external_tools": {"realcugan": str(tmp_path / "missing_realcugan.exe")},
            "io": {"overwrite": True},
        }
    )

    result = upscale_image(input_path, output_path, config, debug_dir=debug_dir)

    assert result.upscaler_result.requested_engine == "realcugan"
    assert result.upscaler_result.engine == "lanczos"
    assert result.upscaler_result.used_fallback is True
    assert (debug_dir / "07_tone_source.png").exists()
    assert (debug_dir / "08_tone_hr.png").exists()
    metadata = json.loads(result.run_json_path.read_text(encoding="utf-8"))
    assert metadata["upscaler"]["requested_engine"] == "realcugan"
    assert metadata["upscaler"]["engine"] == "lanczos"
    assert metadata["upscaler"]["used_fallback"] is True


def test_pipeline_auto_tone_usage_skips_tone_hr_for_pure_lineart(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "out.png"
    debug_dir = tmp_path / "debug"
    _line_fixture(input_path)
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 2, "tone_mode": "lift_lines"},
            "tone_source": {"mode": "lift_lines"},
            "upscaler": {"engine": "lanczos", "fallback": "none"},
            "composite": {"tone_usage": "auto"},
            "io": {"overwrite": True},
        }
    )

    result = upscale_image(input_path, output_path, config, debug_dir=debug_dir)

    expected = composite_black_lines(
        white_canvas(result.sdf_result.line_alpha_hr.shape),
        result.sdf_result.line_alpha_hr,
        line_darkness=config["composite"]["line_darkness"],
        edge_alpha_gamma=config["composite"]["edge_alpha_gamma"],
    )
    assert result.tone_source_result.is_likely_pure_lineart is True
    assert result.tone_used_in_final is False
    assert result.upscaler_result.requested_engine == "lanczos"
    assert result.upscaler_result.engine == "none"
    assert result.tone_skip_reason == "input looks like pure line art"
    assert np.allclose(result.final, expected)
    assert (debug_dir / "07_tone_source.png").exists()
    assert not (debug_dir / "08_tone_hr.png").exists()
    metadata = json.loads(result.run_json_path.read_text(encoding="utf-8"))
    assert metadata["tone_composite"]["tone_usage"] == "auto"
    assert metadata["tone_composite"]["used_tone_hr"] is False


def test_pipeline_tone_usage_always_keeps_tone_hr_for_pure_lineart(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "out.png"
    debug_dir = tmp_path / "debug"
    _line_fixture(input_path)
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 2, "tone_mode": "lift_lines"},
            "tone_source": {"mode": "lift_lines"},
            "upscaler": {"engine": "lanczos", "fallback": "none"},
            "composite": {"tone_usage": "always"},
            "io": {"overwrite": True},
        }
    )

    result = upscale_image(input_path, output_path, config, debug_dir=debug_dir)

    assert result.tone_source_result.is_likely_pure_lineart is True
    assert result.tone_used_in_final is True
    assert result.upscaler_result.engine == "lanczos"
    assert result.tone_skip_reason is None
    assert (debug_dir / "08_tone_hr.png").exists()


def test_pipeline_can_disable_run_json(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "out.png"
    _line_fixture(input_path)
    config = load_config(
        cli_overrides={
            "pipeline": {"scale": 2},
            "io": {"overwrite": True},
            "debug": {"save_run_json": False},
        }
    )

    result = upscale_image(input_path, output_path, config)

    assert result.run_json_path is None
    assert not output_path.with_suffix(".mlus-run.json").exists()


def test_pipeline_handles_blank_and_black_images_with_warnings(tmp_path) -> None:
    config = load_config(cli_overrides={"pipeline": {"scale": 2}, "io": {"overwrite": True}})

    blank_path = tmp_path / "blank.png"
    blank_out = tmp_path / "blank_out.png"
    Image.fromarray(np.full((8, 8), 255, dtype=np.uint8)).save(blank_path)
    blank = upscale_image(blank_path, blank_out, config)

    black_path = tmp_path / "black.png"
    black_out = tmp_path / "black_out.png"
    Image.fromarray(np.zeros((8, 8), dtype=np.uint8)).save(black_path)
    black = upscale_image(black_path, black_out, config)

    assert "line_mask is almost empty" in blank.line_maps.warnings
    assert "line_mask covers too much of the image" in black.line_maps.warnings


def test_pipeline_handles_transparent_png_and_jpeg_inputs(tmp_path) -> None:
    config = load_config(cli_overrides={"pipeline": {"scale": 2}, "io": {"overwrite": True}})

    rgba_path = tmp_path / "transparent.png"
    rgba = np.zeros((4, 4, 4), dtype=np.uint8)
    rgba[..., 3] = 0
    rgba[2, :, :3] = 0
    rgba[2, :, 3] = 255
    Image.fromarray(rgba).save(rgba_path)
    rgba_result = upscale_image(rgba_path, tmp_path / "transparent_out.png", config)

    jpg_path = tmp_path / "input.jpg"
    jpg = np.full((4, 5, 3), 255, dtype=np.uint8)
    jpg[2, :, :] = 0
    Image.fromarray(jpg).save(jpg_path, format="JPEG")
    jpg_result = upscale_image(jpg_path, tmp_path / "jpg_out.png", config)

    assert rgba_result.final.shape == (8, 8)
    assert jpg_result.final.shape == (8, 10)


def test_pipeline_output_pixels_are_deterministic_for_same_input_and_config(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    _line_fixture(input_path)
    config = load_config(cli_overrides={"pipeline": {"scale": 3}, "io": {"overwrite": True}})

    first = upscale_image(input_path, tmp_path / "first.png", config)
    second = upscale_image(input_path, tmp_path / "second.png", config)

    assert np.array_equal(first.final, second.final)
    with Image.open(tmp_path / "first.png") as first_png:
        first_pixels = np.asarray(first_png)
    with Image.open(tmp_path / "second.png") as second_png:
        second_pixels = np.asarray(second_png)
    assert np.array_equal(first_pixels, second_pixels)


def test_final_only_fast_path_matches_full_debug_pipeline_exactly(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    fast_path = tmp_path / "fast.png"
    full_path = tmp_path / "full.png"
    _line_fixture(input_path)
    config = load_config(
        cli_overrides={"pipeline": {"scale": 4}, "io": {"overwrite": True}}
    )

    fast = upscale_image(input_path, fast_path, config)
    full = upscale_image(input_path, full_path, config, debug_dir=tmp_path / "debug")

    assert np.array_equal(fast.final, full.final)
    assert fast_path.read_bytes() == full_path.read_bytes()
    assert fast.sdf_result.renderer_metadata is not None
    assert fast.sdf_result.renderer_metadata["alpha_fast_path"] is True
    assert fast.sdf_result.line_geometry_hr is None
    assert fast.sdf_result.directional_smoothing_weight_hr is None
    assert full.sdf_result.sdf is not None
    assert full.sdf_result.sdf_hr is not None
