from __future__ import annotations

import sys

import pytest

from mlu.config import ConfigError, deep_merge, load_config, repo_root


def test_deep_merge_preserves_nested_values() -> None:
    merged = deep_merge(
        {"mask": {"black_threshold": 0.72, "cleanup": {"min_component_area": 6}}},
        {"mask": {"cleanup": {"min_component_area": 4}}},
    )

    assert merged["mask"]["black_threshold"] == 0.72
    assert merged["mask"]["cleanup"]["min_component_area"] == 4


def test_load_config_merges_default_preset_user_and_cli(tmp_path) -> None:
    user_config = tmp_path / "user.yaml"
    user_config.write_text(
        """
version: 1
mask:
  black_threshold: 0.5
io:
  overwrite: true
""".strip(),
        encoding="utf-8",
    )

    config = load_config(
        preset="line_only",
        config_path=user_config,
        cli_overrides={"pipeline": {"scale": 2}},
    )

    assert config["mask"]["black_threshold"] == 0.5
    assert config["mask"]["cleanup"]["min_component_area"] == 4
    assert config["pipeline"]["scale"] == 2
    assert config["io"]["overwrite"] is True


def test_repo_root_uses_pyinstaller_meipass(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert repo_root() == tmp_path


def test_line_only_default_uses_high_resolution_soft_sdf_without_line_stabilizer() -> None:
    config = load_config(preset="line_only")

    assert config["sdf"]["distance_source"] == "soft_mask_hr"
    assert config["mask"]["soft_coverage"]["mode"] == "darkness"
    assert config["mask"]["soft_coverage"]["gamma"] == 1.0
    assert config["sdf"]["soft_sdf_threshold"] == 0.22
    assert config["sdf"]["soft_alpha_mode"] == "none"
    assert config["sdf"]["soft_gain"] == 0.0
    assert config["line_stabilizer"]["enabled"] is False
    assert config["line_stabilizer"]["strength"] == 0.55
    assert config["directional_smoothing"]["enabled"] is False
    assert config["directional_smoothing"]["strength"] == 0.55
    assert config["directional_smoothing"]["radius_hr_px"] == 2
    assert config["directional_smoothing"]["min_angle_from_axis_degrees"] == 20.0
    assert config["directional_smoothing"]["full_strength_angle_from_axis_degrees"] == 34.0
    assert config["centerline_simplification"]["enabled"] is False
    assert config["centerline_simplification"]["filter_sigma_source_px"] == 0.0
    assert config["centerline_simplification"]["filter_sample_step_source_px"] == 0.50
    assert config["centerline_simplification"]["max_filter_displacement_source_px"] == 0.75
    assert config["centerline_simplification"]["binarize_output"] is True
    assert config["centerline_simplification"]["binary_threshold"] == 0.50
    assert config["centerline_simplification"]["max_new_component_area"] == 2
    assert config["debug"]["save_run_json"] is False
    assert config["centerline_simplification"]["corner_angle_degrees"] == 45.0
    assert config["centerline_simplification"]["corner_window_source_px"] == 3.0
    assert config["centerline_simplification"]["geometry_strength"] == 1.0
    assert config["centerline_simplification"]["min_path_length_source_px"] == 64.0
    assert config["centerline_simplification"]["max_radius_source_px"] == 2.25
    gate = config["centerline_simplification"]["long_stroke_gate"]
    assert gate["enabled"] is True
    assert gate["min_chord_arc_ratio"] == 0.985
    assert gate["max_line_fit_rms_source_px"] == 0.35
    assert gate["max_line_fit_deviation_source_px"] == 1.0
    assert gate["max_width_cv"] == 0.20
    assert gate["max_width_ratio"] == 1.50
    assert gate["skip_paths_with_corners"] is True
    rollback = config["centerline_simplification"]["component_rollback"]
    assert rollback["enabled"] is True
    assert rollback["preserve_component_count"] is True
    assert rollback["min_ink_ratio"] == 0.80
    assert rollback["max_ink_ratio"] == 1.20


def test_gray_tone_preset_uses_adopted_reduced_width_bias() -> None:
    config = load_config(preset="gray_tone")

    assert config["sdf"]["width_bias_source_px"] == -0.25


def test_load_config_rejects_invalid_scale() -> None:
    with pytest.raises(ConfigError, match="pipeline.scale"):
        load_config(cli_overrides={"pipeline": {"scale": 5}})


def test_load_config_accepts_supported_gui_scales() -> None:
    for scale in (2, 3, 4, 6, 8):
        config = load_config(cli_overrides={"pipeline": {"scale": scale}})

        assert config["pipeline"]["scale"] == scale


def test_load_config_rejects_invalid_line_renderer() -> None:
    with pytest.raises(ConfigError, match="pipeline.line_renderer"):
        load_config(cli_overrides={"pipeline": {"line_renderer": "unknown"}})


def test_load_config_rejects_invalid_soft_coverage_settings() -> None:
    with pytest.raises(ConfigError, match="mask.soft_coverage.mode"):
        load_config(cli_overrides={"mask": {"soft_coverage": {"mode": "unknown"}}})

    with pytest.raises(ConfigError, match="mask.soft_coverage.gamma"):
        load_config(cli_overrides={"mask": {"soft_coverage": {"gamma": 0.0}}})


def test_load_config_validates_experimental_grayscale_processing() -> None:
    config = load_config(
        cli_overrides={"grayscale_processing": {"mode": "separate"}}
    )
    assert config["grayscale_processing"]["closing_radius"] == 6
    assert config["grayscale_processing"]["separate_output_format"] == "png"
    assert config["grayscale_processing"]["line_coverage_mode"] == "quality_hybrid"
    assert config["grayscale_processing"]["relative_coverage_gain"] == 2.425

    with pytest.raises(ConfigError, match="grayscale_processing.mode"):
        load_config(cli_overrides={"grayscale_processing": {"mode": "unknown"}})
    with pytest.raises(ConfigError, match="separate_output_format"):
        load_config(
            cli_overrides={
                "grayscale_processing": {"separate_output_format": "tiff"}
            }
        )
    with pytest.raises(ConfigError, match="strong_relative_contrast"):
        load_config(
            cli_overrides={
                "grayscale_processing": {
                    "weak_relative_contrast": 0.2,
                    "strong_relative_contrast": 0.1,
                }
            }
        )
    with pytest.raises(ConfigError, match="line_coverage_mode"):
        load_config(
            cli_overrides={
                "grayscale_processing": {"line_coverage_mode": "probability_only"}
            }
        )
    with pytest.raises(ConfigError, match="relative_coverage_gain"):
        load_config(
            cli_overrides={
                "grayscale_processing": {"relative_coverage_gain": 0.0}
            }
        )
    with pytest.raises(ConfigError, match="legacy_blend_end"):
        load_config(
            cli_overrides={
                "grayscale_processing": {
                    "legacy_blend_start": 0.95,
                    "legacy_blend_end": 0.90,
                }
            }
        )


def test_load_config_rejects_invalid_soft_alpha_mode() -> None:
    with pytest.raises(ConfigError, match="sdf.soft_alpha_mode"):
        load_config(cli_overrides={"sdf": {"soft_alpha_mode": "unknown"}})


def test_load_config_rejects_invalid_distance_source() -> None:
    with pytest.raises(ConfigError, match="sdf.distance_source"):
        load_config(cli_overrides={"sdf": {"distance_source": "unknown"}})


def test_load_config_rejects_invalid_soft_sdf_threshold() -> None:
    with pytest.raises(ConfigError, match="sdf.soft_sdf_threshold"):
        load_config(cli_overrides={"sdf": {"soft_sdf_threshold": 1.5}})


def test_load_config_rejects_non_boolean_save_run_json() -> None:
    with pytest.raises(ConfigError, match="debug.save_run_json"):
        load_config(cli_overrides={"debug": {"save_run_json": "false"}})


def test_load_config_rejects_invalid_soft_gain() -> None:
    with pytest.raises(ConfigError, match="sdf.soft_gain"):
        load_config(cli_overrides={"sdf": {"soft_gain": 1.5}})


def test_load_config_rejects_invalid_line_stabilizer_enabled() -> None:
    with pytest.raises(ConfigError, match="line_stabilizer.enabled"):
        load_config(cli_overrides={"line_stabilizer": {"enabled": "yes"}})


def test_load_config_rejects_line_stabilizer_with_potrace_renderer() -> None:
    with pytest.raises(ConfigError, match="line_stabilizer.enabled"):
        load_config(
            cli_overrides={
                "pipeline": {"line_renderer": "potrace"},
                "line_stabilizer": {"enabled": True},
            }
        )


def test_load_config_rejects_invalid_line_stabilizer_number() -> None:
    with pytest.raises(ConfigError, match="line_stabilizer.strength"):
        load_config(cli_overrides={"line_stabilizer": {"strength": -0.1}})


def test_load_config_rejects_invalid_directional_smoothing_settings() -> None:
    with pytest.raises(ConfigError, match="directional_smoothing.enabled"):
        load_config(cli_overrides={"directional_smoothing": {"enabled": "yes"}})

    with pytest.raises(ConfigError, match="directional_smoothing.strength"):
        load_config(cli_overrides={"directional_smoothing": {"strength": 1.2}})

    with pytest.raises(ConfigError, match="directional_smoothing.radius_hr_px"):
        load_config(cli_overrides={"directional_smoothing": {"radius_hr_px": -1}})

    with pytest.raises(ConfigError, match="directional_smoothing.min_angle_from_axis_degrees"):
        load_config(
            cli_overrides={
                "directional_smoothing": {"min_angle_from_axis_degrees": 45.0}
            }
        )


def test_load_config_rejects_invalid_centerline_simplification_settings() -> None:
    with pytest.raises(ConfigError, match="centerline_simplification.enabled"):
        load_config(cli_overrides={"centerline_simplification": {"enabled": "yes"}})

    with pytest.raises(ConfigError, match="centerline_simplification.filter_sigma_source_px"):
        load_config(
            cli_overrides={"centerline_simplification": {"filter_sigma_source_px": -0.1}}
        )

    with pytest.raises(
        ConfigError,
        match="centerline_simplification.filter_sample_step_source_px",
    ):
        load_config(
            cli_overrides={
                "centerline_simplification": {"filter_sample_step_source_px": 0.0}
            }
        )

    with pytest.raises(ConfigError, match="centerline_simplification.alpha_threshold"):
        load_config(cli_overrides={"centerline_simplification": {"alpha_threshold": 0.0}})

    with pytest.raises(ConfigError, match="centerline_simplification.strength"):
        load_config(cli_overrides={"centerline_simplification": {"strength": 1.1}})

    with pytest.raises(ConfigError, match="centerline_simplification.binarize_output"):
        load_config(
            cli_overrides={"centerline_simplification": {"binarize_output": "yes"}}
        )

    with pytest.raises(ConfigError, match="centerline_simplification.binary_threshold"):
        load_config(
            cli_overrides={"centerline_simplification": {"binary_threshold": 1.0}}
        )

    with pytest.raises(ConfigError, match="centerline_simplification.max_new_component_area"):
        load_config(
            cli_overrides={"centerline_simplification": {"max_new_component_area": -1}}
        )

    with pytest.raises(ConfigError, match="centerline_simplification.corner_angle_degrees"):
        load_config(
            cli_overrides={"centerline_simplification": {"corner_angle_degrees": 180.0}}
        )

    with pytest.raises(ConfigError, match="centerline_simplification.corner_window_source_px"):
        load_config(
            cli_overrides={"centerline_simplification": {"corner_window_source_px": 0.0}}
        )

    with pytest.raises(ConfigError, match="centerline_simplification.geometry_strength"):
        load_config(
            cli_overrides={"centerline_simplification": {"geometry_strength": 1.1}}
        )

    with pytest.raises(
        ConfigError,
        match="centerline_simplification.long_stroke_gate.min_chord_arc_ratio",
    ):
        load_config(
            cli_overrides={
                "centerline_simplification": {
                    "long_stroke_gate": {"min_chord_arc_ratio": 1.1}
                }
            }
        )

    with pytest.raises(
        ConfigError,
        match="centerline_simplification.long_stroke_gate.max_width_ratio",
    ):
        load_config(
            cli_overrides={
                "centerline_simplification": {
                    "long_stroke_gate": {"max_width_ratio": 0.5}
                }
            }
        )

    with pytest.raises(
        ConfigError,
        match="centerline_simplification.component_rollback.min_ink_ratio",
    ):
        load_config(
            cli_overrides={
                "centerline_simplification": {
                    "component_rollback": {"min_ink_ratio": 0.0}
                }
            }
        )

    with pytest.raises(
        ConfigError,
        match="centerline_simplification.component_rollback.max_ink_ratio",
    ):
        load_config(
            cli_overrides={
                "centerline_simplification": {
                    "component_rollback": {"max_ink_ratio": 0.5}
                }
            }
        )


def test_load_config_rejects_centerline_simplification_with_potrace() -> None:
    with pytest.raises(ConfigError, match="centerline_simplification.enabled"):
        load_config(
            cli_overrides={
                "pipeline": {"line_renderer": "potrace"},
                "centerline_simplification": {"enabled": True},
            }
        )

    with pytest.raises(
        ConfigError,
        match="directional_smoothing.full_strength_angle_from_axis_degrees",
    ):
        load_config(
            cli_overrides={
                "directional_smoothing": {
                    "min_angle_from_axis_degrees": 20.0,
                    "full_strength_angle_from_axis_degrees": 16.0,
                }
            }
        )


def test_load_config_rejects_invalid_potrace_settings() -> None:
    with pytest.raises(ConfigError, match="potrace.turdsize"):
        load_config(cli_overrides={"potrace": {"turdsize": -1}})

    with pytest.raises(ConfigError, match="potrace.rasterizer"):
        load_config(cli_overrides={"potrace": {"rasterizer": "unknown"}})


def test_load_config_rejects_invalid_tone_source_mode() -> None:
    with pytest.raises(ConfigError, match="tone_source.mode"):
        load_config(cli_overrides={"tone_source": {"mode": "unknown"}})


def test_load_config_rejects_invalid_tone_source_number() -> None:
    with pytest.raises(ConfigError, match="tone_source.dilate_radius"):
        load_config(cli_overrides={"tone_source": {"dilate_radius": -0.1}})

    with pytest.raises(ConfigError, match="tone_source.lift_strength"):
        load_config(cli_overrides={"tone_source": {"lift_strength": 1.1}})


def test_load_config_rejects_invalid_protect_midtones() -> None:
    with pytest.raises(ConfigError, match="tone_source.protect_midtones"):
        load_config(cli_overrides={"tone_source": {"protect_midtones": "yes"}})


def test_load_config_rejects_invalid_upscaler_engine() -> None:
    with pytest.raises(ConfigError, match="upscaler.engine"):
        load_config(cli_overrides={"upscaler": {"engine": "unknown"}})


def test_load_config_rejects_invalid_upscaler_fallback() -> None:
    with pytest.raises(ConfigError, match="upscaler.fallback"):
        load_config(cli_overrides={"upscaler": {"fallback": "realcugan"}})


def test_load_config_rejects_invalid_upscaler_tile_size() -> None:
    with pytest.raises(ConfigError, match="upscaler.realcugan.tile_size"):
        load_config(cli_overrides={"upscaler": {"realcugan": {"tile_size": 0}}})


def test_load_config_rejects_invalid_external_tool_path_type() -> None:
    with pytest.raises(ConfigError, match="external_tools.realcugan"):
        load_config(cli_overrides={"external_tools": {"realcugan": 123}})


def test_load_config_rejects_invalid_tone_usage() -> None:
    with pytest.raises(ConfigError, match="composite.tone_usage"):
        load_config(cli_overrides={"composite": {"tone_usage": "sometimes"}})
