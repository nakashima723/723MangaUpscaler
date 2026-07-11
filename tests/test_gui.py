from __future__ import annotations

from pathlib import Path
from tkinter import messagebox
from types import SimpleNamespace

import customtkinter as ctk
import numpy as np
import pytest
from PIL import Image

import mlu.gui as gui_module
from mlu.config import load_config
from mlu.gui import (
    ALL_EXTENSIONS_LABEL,
    BRIGHTNESS_MAX,
    BRIGHTNESS_MIN,
    GRAYSCALE_MODE_LABELS,
    OutputPreviewRequest,
    PreviewViewState,
    UpscalerGui,
    capture_preview_view_state,
    comparison_scale_for_images,
    discover_gui_batch_images,
    format_brightness_label,
    generate_output_preview_image,
    load_export_config,
    main,
    make_batch_output_paths,
    make_output_path,
    normalize_filename_filter,
    output_preview_confirmation_message,
    output_preview_requires_confirmation,
    output_preview_size,
    preview_geometry_from_view_state,
    selected_separate_psd,
    threshold_from_brightness,
)
from mlu.pipeline import upscale_image


def test_gui_uses_customtkinter_root() -> None:
    assert issubclass(UpscalerGui, ctk.CTk)


def test_threshold_from_brightness_uses_continuous_monotonic_remap() -> None:
    assert (BRIGHTNESS_MIN, BRIGHTNESS_MAX) == (-10, 10)
    assert threshold_from_brightness(-10) == 0.06
    assert threshold_from_brightness(-9) == 0.083
    assert threshold_from_brightness(-1) == 0.268
    assert threshold_from_brightness(0) == 0.291
    assert threshold_from_brightness(1) == 0.324
    assert threshold_from_brightness(9) == 0.588
    assert threshold_from_brightness(10) == 0.621
    assert threshold_from_brightness(-11) == 0.06
    assert threshold_from_brightness(11) == 0.621
    thresholds = [threshold_from_brightness(level) for level in range(-10, 11)]
    assert np.all(np.diff(thresholds) > 0.0)
    assert np.allclose(np.diff(thresholds[10:]), 0.033)


def test_format_brightness_label_uses_signed_integer_display() -> None:
    assert format_brightness_label(0) == "明るさ: 0"
    assert format_brightness_label(1) == "明るさ: +1"
    assert format_brightness_label(-1) == "明るさ: -1"


def test_load_export_config_carries_grayscale_mode() -> None:
    config = load_export_config(
        scale=2,
        threshold=0.36,
        grayscale_mode="composite",
    )

    assert config["grayscale_processing"]["mode"] == "composite"
    assert config["grayscale_processing"]["separate_output_format"] == "png"

    psd_config = load_export_config(
        scale=2,
        threshold=0.36,
        grayscale_mode="separate",
        separate_output_format="psd",
    )
    assert psd_config["grayscale_processing"]["separate_output_format"] == "psd"


def test_selected_separate_psd_only_applies_to_separate_mode() -> None:
    app = SimpleNamespace(separate_psd_enabled=_StubVariable(True))

    assert selected_separate_psd(app, "separate") is True
    assert selected_separate_psd(app, "legacy") is False
    app.separate_psd_enabled.set(False)
    assert selected_separate_psd(app, "separate") is False
    assert selected_separate_psd(SimpleNamespace(), "separate") is False


def test_brightness_buttons_adjust_one_step_and_do_not_repeat_at_bounds() -> None:
    slider_updates: list[int] = []
    label_updates: list[bool] = []
    preview_updates: list[bool] = []
    app = SimpleNamespace(
        brightness_value=_StubVariable(0),
        brightness_scale=SimpleNamespace(set=slider_updates.append),
        _update_brightness_label=lambda: label_updates.append(True),
        _schedule_output_preview=lambda: preview_updates.append(True),
    )

    UpscalerGui._adjust_brightness(app, -1)
    assert app.brightness_value.get() == -1
    UpscalerGui._adjust_brightness(app, 1)
    assert app.brightness_value.get() == 0
    assert slider_updates == [-1, 0]
    assert len(label_updates) == 2
    assert len(preview_updates) == 2

    app.brightness_value.set(BRIGHTNESS_MIN)
    UpscalerGui._adjust_brightness(app, -1)
    app.brightness_value.set(BRIGHTNESS_MAX)
    UpscalerGui._adjust_brightness(app, 1)
    assert slider_updates == [-1, 0]
    assert len(preview_updates) == 2


def test_make_output_path_is_unique(tmp_path) -> None:
    input_path = Path("sample01.png")
    first = make_output_path(input_path, tmp_path, scale=4, threshold=0.34)
    first.write_bytes(b"")

    second = make_output_path(input_path, tmp_path, scale=4, threshold=0.34)

    assert first.name == "sample01_x4_thr034.png"
    assert second.name == "sample01_x4_thr034_2.png"


def test_make_output_path_reserves_separate_tone_sidecar(tmp_path) -> None:
    input_path = Path("sample01.png")
    (tmp_path / "sample01_x4_thr034_tone.png").write_bytes(b"existing")

    output = make_output_path(
        input_path,
        tmp_path,
        scale=4,
        threshold=0.34,
        grayscale_mode="separate",
    )

    assert output.name == "sample01_x4_thr034_2.png"


def test_make_output_path_uses_and_reserves_psd_for_separate_mode(tmp_path) -> None:
    input_path = Path("sample01.png")
    first = make_output_path(
        input_path,
        tmp_path,
        scale=4,
        threshold=0.34,
        grayscale_mode="separate",
        separate_psd=True,
    )
    first.write_bytes(b"existing")

    second = make_output_path(
        input_path,
        tmp_path,
        scale=4,
        threshold=0.34,
        grayscale_mode="separate",
        separate_psd=True,
    )

    assert first.name == "sample01_x4_thr034.psd"
    assert second.name == "sample01_x4_thr034_2.psd"


def test_make_batch_output_paths_reserves_duplicate_stems(tmp_path) -> None:
    (tmp_path / "same_x4_thr036.png").write_bytes(b"")

    output_paths = make_batch_output_paths(
        (Path("same.jpg"), Path("same.png")),
        tmp_path,
        scale=4,
        threshold=0.36,
    )

    assert [path.name for path in output_paths] == [
        "same_x4_thr036_2.png",
        "same_x4_thr036_3.png",
    ]

    psd_paths = make_batch_output_paths(
        (Path("first.png"), Path("second.png")),
        tmp_path,
        scale=2,
        threshold=0.291,
        grayscale_mode="separate",
        separate_psd=True,
    )
    assert [path.name for path in psd_paths] == [
        "first_x2_thr029.psd",
        "second_x2_thr029.psd",
    ]


def test_normalize_filename_filter_removes_windows_invalid_characters() -> None:
    assert normalize_filename_filter("  背景:*?  ") == "背景"
    assert normalize_filename_filter(' <>:"/\\|?*\t ') == ""


def test_discover_gui_batch_images_applies_extension_and_name_as_and_condition(
    tmp_path,
) -> None:
    (tmp_path / "背景_A.PNG").write_bytes(b"")
    (tmp_path / "背景_B.jpg").write_bytes(b"")
    (tmp_path / "人物_背景.png").write_bytes(b"")
    (tmp_path / "背景.txt").write_bytes(b"")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "背景_C.png").write_bytes(b"")

    paths = discover_gui_batch_images(
        tmp_path,
        extension=".png",
        filename_filter_enabled=True,
        filename_filter_text="背景:*?",
    )

    assert [path.name for path in paths] == ["人物_背景.png", "背景_A.PNG"]


def test_discover_gui_batch_images_ignores_empty_or_disabled_name_filter(tmp_path) -> None:
    (tmp_path / "a.png").write_bytes(b"")
    (tmp_path / "b.jpg").write_bytes(b"")

    invalid_only = discover_gui_batch_images(
        tmp_path,
        extension=ALL_EXTENSIONS_LABEL,
        filename_filter_enabled=True,
        filename_filter_text=' <>:"/\\|?* ',
    )
    disabled = discover_gui_batch_images(
        tmp_path,
        extension=ALL_EXTENSIONS_LABEL,
        filename_filter_enabled=False,
        filename_filter_text="一致しない文字列",
    )

    assert [path.name for path in invalid_only] == ["a.png", "b.jpg"]
    assert disabled == invalid_only


def test_discover_gui_batch_images_excludes_gui_outputs_when_output_is_input(tmp_path) -> None:
    (tmp_path / "source.png").write_bytes(b"")
    (tmp_path / "source_x4_thr036.png").write_bytes(b"")
    (tmp_path / "source_x4_thr036_2.png").write_bytes(b"")
    (tmp_path / "source_x4_thr036_tone.png").write_bytes(b"")
    (tmp_path / "source_x4_thr036_2_tone.png").write_bytes(b"")

    paths = discover_gui_batch_images(
        tmp_path,
        extension=ALL_EXTENSIONS_LABEL,
        filename_filter_enabled=False,
        filename_filter_text="",
        output_dir=tmp_path,
    )

    assert [path.name for path in paths] == ["source.png"]


def test_comparison_scale_for_images_uses_output_to_input_ratio() -> None:
    assert comparison_scale_for_images((100, 50), (400, 200)) == 4.0
    assert comparison_scale_for_images((100, 50), (600, 310)) == 6.0


def test_comparison_scale_for_images_rejects_empty_sizes() -> None:
    with pytest.raises(ValueError, match="positive"):
        comparison_scale_for_images((0, 50), (400, 200))


def test_preview_view_state_preserves_input_center_and_zoom_across_output_scales() -> None:
    state = capture_preview_view_state(
        preview_scale=0.5,
        preview_offset=(-120, -80),
        pane_size=(600, 400),
        input_to_output_scale=4.0,
    )

    preview_scale, offset_x, offset_y = preview_geometry_from_view_state(
        state,
        pane_size=(600, 400),
        input_to_output_scale=8.0,
    )

    assert state == PreviewViewState(2.0, 210.0, 140.0)
    assert preview_scale == 0.25
    assert (offset_x, offset_y) == (-120, -80)
    restored = capture_preview_view_state(
        preview_scale=preview_scale,
        preview_offset=(offset_x, offset_y),
        pane_size=(600, 400),
        input_to_output_scale=8.0,
    )
    assert restored == state


def test_replacing_output_preview_preserves_existing_pan_and_zoom() -> None:
    old_output = Image.new("L", (400, 200), 255)
    new_output = Image.new("L", (800, 400), 255)
    rendered: list[bool] = []
    app = SimpleNamespace(
        input_preview_image=Image.new("L", (100, 50), 255),
        output_preview_image=old_output,
        input_to_output_preview_scale=4.0,
        preview_scale=0.5,
        preview_offset_x=-120,
        preview_offset_y=-80,
        _preview_pane_size=lambda: (600, 400),
        _fit_preview=lambda: pytest.fail("an update must not reset the view"),
        _render_preview=lambda: rendered.append(True),
    )

    UpscalerGui._set_output_preview_image(app, new_output)

    try:
        assert app.input_to_output_preview_scale == 8.0
        assert app.preview_scale == 0.25
        assert (app.preview_offset_x, app.preview_offset_y) == (-120, -80)
        assert rendered == [True]
    finally:
        app.input_preview_image.close()
        new_output.close()


def test_preview_zoom_bound_is_stable_in_input_coordinates_across_scales() -> None:
    input_image = Image.new("L", (100, 100), 255)
    output_image = Image.new("L", (800, 800), 255)
    app = SimpleNamespace(
        input_preview_image=input_image,
        output_preview_image=output_image,
        input_to_output_preview_scale=8.0,
        _is_comparison_preview=lambda: True,
    )

    try:
        assert UpscalerGui._bounded_preview_scale(app, 2.0) == 2.0
        app.input_to_output_preview_scale = 2.0
        assert UpscalerGui._bounded_preview_scale(app, 8.0) == 8.0
    finally:
        input_image.close()
        output_image.close()


def test_output_preview_size_and_confirmation_include_6000_square_boundary() -> None:
    output_size = output_preview_size((1500, 1500), 4)

    assert output_size == (6000, 6000)
    assert output_preview_requires_confirmation(output_size) is True
    assert output_preview_requires_confirmation((5999, 6000)) is False
    assert output_preview_confirmation_message((6400, 6000)) == (
        "出力サイズが縦6000px・横6400pxと大きいため、変換に時間がかかります。"
        "出力プレビューを表示しますか？"
    )


def test_generated_preview_pixels_match_actual_output_exactly(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "actual.png"
    source = np.full((10, 12), 255, dtype=np.uint8)
    source[2:8, 6] = 0
    source[5, 2:10] = 0
    Image.fromarray(source).save(input_path)
    config = load_config(
        preset="line_only",
        cli_overrides={
            "io": {"overwrite": True},
            "pipeline": {"scale": 4},
            "sdf": {"soft_sdf_threshold": 0.36},
        },
    )

    preview = generate_output_preview_image(input_path, config)
    upscale_image(input_path, output_path, config, preset="line_only")
    try:
        with Image.open(output_path) as actual:
            assert np.array_equal(np.asarray(preview), np.asarray(actual.convert("L")))
    finally:
        preview.close()


def test_minimum_brightness_preview_is_not_solid_black(tmp_path) -> None:
    input_path = tmp_path / "synthetic_lineart.png"
    source = np.full((64, 80), 255, dtype=np.uint8)
    source[8:56, 37:43] = 0
    source[29:35, 8:72] = 0
    source[7:9, 36:44] = 96
    source[56:58, 36:44] = 96
    Image.fromarray(source).save(input_path)
    config = load_config(
        preset="line_only",
        cli_overrides={
            "io": {"overwrite": True},
            "pipeline": {"scale": 2},
            "sdf": {"soft_sdf_threshold": threshold_from_brightness(-10)},
        },
    )

    preview = generate_output_preview_image(input_path, config)
    try:
        pixels = np.asarray(preview)
        assert np.max(pixels) == 255
        assert np.mean(pixels == 0) < 0.5
    finally:
        preview.close()


def test_preview_temporary_directory_is_removed_after_failure(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "input.png"
    input_path.write_bytes(b"input")
    temporary_paths: list[Path] = []

    def fail_after_writing(_input, output, _config, *, preset) -> None:
        assert preset == "line_only"
        output_path = Path(output)
        temporary_paths.append(output_path.parent)
        Image.fromarray(np.zeros((2, 2), dtype=np.uint8)).save(output_path)
        raise RuntimeError("preview failed")

    monkeypatch.setattr(gui_module, "upscale_image", fail_after_writing)

    with pytest.raises(RuntimeError, match="preview failed"):
        generate_output_preview_image(input_path, {})

    assert len(temporary_paths) == 1
    assert not temporary_paths[0].exists()


def test_loading_input_schedules_immediate_output_preview(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    Image.fromarray(np.full((4, 5), 255, dtype=np.uint8)).save(input_path)
    scheduled: list[int] = []
    app = SimpleNamespace(
        _preview_source_path=None,
        _large_preview_approved_source=Path("old.png"),
        input_preview_image=None,
        _clear_output_preview=lambda: None,
        _schedule_output_preview=lambda *, delay_ms: scheduled.append(delay_ms),
    )

    UpscalerGui._load_input_preview(app, input_path)

    try:
        assert app._preview_source_path == input_path.absolute()
        assert app._large_preview_approved_source is None
        assert app.input_preview_image.size == (5, 4)
        assert scheduled == [0]
    finally:
        app.input_preview_image.close()


def test_large_preview_no_unchecks_and_blocks_until_reenabled(monkeypatch) -> None:
    source_path = Path("large.png").absolute()
    prompts: list[tuple[str, str]] = []
    started: list[OutputPreviewRequest] = []
    invalidated: list[bool] = []
    enabled = _StubVariable(True)
    app = SimpleNamespace(
        _preview_after_id="timer",
        _preview_revision=1,
        output_preview_enabled=enabled,
        _preview_source_path=source_path,
        input_preview_image=SimpleNamespace(size=(1500, 1500)),
        _export_running=False,
        scale_value=_StubVariable("4"),
        _threshold_value=lambda: 0.36,
        _large_preview_approved_source=None,
        _preview_worker_running=False,
        status_text=_StubVariable(""),
        _start_output_preview_worker=started.append,
        _invalidate_output_preview=lambda *, clear_output: invalidated.append(clear_output),
    )
    monkeypatch.setattr(
        messagebox,
        "askyesno",
        lambda title, text: prompts.append((title, text)) or False,
    )

    UpscalerGui._prepare_output_preview(app, 1)
    UpscalerGui._prepare_output_preview(app, 1)

    assert enabled.get() is False
    assert started == []
    assert invalidated == [True]
    assert len(prompts) == 1
    assert prompts[0][1] == output_preview_confirmation_message((6000, 6000))

    enabled.set(True)
    app._preview_revision = 2
    UpscalerGui._prepare_output_preview(app, 2)
    assert len(prompts) == 2
    assert started == []


def test_large_preview_yes_is_only_asked_once_for_current_input(monkeypatch) -> None:
    source_path = Path("large.png").absolute()
    prompt_count = 0
    started: list[OutputPreviewRequest] = []
    app = SimpleNamespace(
        _preview_after_id=None,
        _preview_revision=1,
        output_preview_enabled=_StubVariable(True),
        _preview_source_path=source_path,
        input_preview_image=SimpleNamespace(size=(1500, 1500)),
        _export_running=False,
        scale_value=_StubVariable("4"),
        _threshold_value=lambda: 0.36,
        _large_preview_approved_source=None,
        _preview_worker_running=False,
        status_text=_StubVariable(""),
        _start_output_preview_worker=started.append,
    )

    def approve(*_args) -> bool:
        nonlocal prompt_count
        prompt_count += 1
        return True

    monkeypatch.setattr(messagebox, "askyesno", approve)

    UpscalerGui._prepare_output_preview(app, 1)
    app._preview_revision = 2
    UpscalerGui._prepare_output_preview(app, 2)

    assert prompt_count == 1
    assert [request.revision for request in started] == [1, 2]


def test_preview_schedule_debounces_to_latest_revision() -> None:
    callbacks: dict[str, object] = {}
    cancelled: list[str] = []
    prepared: list[int] = []

    def after(_delay, callback):
        timer_id = f"timer-{len(callbacks) + 1}"
        callbacks[timer_id] = callback
        return timer_id

    app = SimpleNamespace(
        _preview_revision=0,
        _queued_preview_request=None,
        _preview_after_id=None,
        output_preview_enabled=_StubVariable(True),
        _preview_source_path=Path("input.png"),
        input_preview_image=SimpleNamespace(size=(10, 10)),
        _export_running=False,
        after=after,
        after_cancel=cancelled.append,
        _prepare_output_preview=prepared.append,
    )
    app._cancel_scheduled_output_preview = lambda: (
        UpscalerGui._cancel_scheduled_output_preview(app)
    )

    UpscalerGui._schedule_output_preview(app)
    UpscalerGui._schedule_output_preview(app)

    assert cancelled == ["timer-1"]
    assert app._preview_revision == 2
    assert app._preview_after_id == "timer-2"
    callbacks["timer-2"]()
    assert prepared == [2]


def test_preview_worker_discards_stale_result_and_starts_latest_request() -> None:
    source_path = Path("input.png").absolute()
    old_request = OutputPreviewRequest(1, source_path, 2, 0.36, (20, 20))
    latest_request = OutputPreviewRequest(3, source_path, 4, 0.40, (40, 40))
    applied: list[Image.Image] = []
    started: list[OutputPreviewRequest] = []
    stale_image = Image.new("L", (20, 20), 255)
    app = SimpleNamespace(
        _preview_worker_running=True,
        _preview_revision=3,
        output_preview_enabled=_StubVariable(True),
        _preview_source_path=source_path,
        _export_running=False,
        _queued_preview_request=latest_request,
        status_text=_StubVariable(""),
        _set_output_preview_image=applied.append,
        _start_output_preview_worker=started.append,
    )

    UpscalerGui._finish_output_preview(app, old_request, stale_image, None)

    assert applied == []
    assert started == [latest_request]
    assert app._queued_preview_request is None


def test_running_preview_worker_keeps_only_latest_pending_settings() -> None:
    source_path = Path("input.png").absolute()
    started: list[OutputPreviewRequest] = []
    app = SimpleNamespace(
        _preview_after_id=None,
        _preview_revision=2,
        output_preview_enabled=_StubVariable(True),
        _preview_source_path=source_path,
        input_preview_image=SimpleNamespace(size=(10, 10)),
        _export_running=False,
        scale_value=_StubVariable("2"),
        _threshold_value=lambda: 0.36,
        _large_preview_approved_source=None,
        _preview_worker_running=True,
        _queued_preview_request=None,
        status_text=_StubVariable(""),
        _start_output_preview_worker=started.append,
    )

    UpscalerGui._prepare_output_preview(app, 2)
    app._preview_revision = 3
    app.scale_value.set("4")
    UpscalerGui._prepare_output_preview(app, 3)

    assert started == []
    assert app._queued_preview_request is not None
    assert app._queued_preview_request.revision == 3
    assert app._queued_preview_request.scale == 4


def test_disabled_preview_does_not_schedule_processing() -> None:
    after_calls: list[object] = []
    app = SimpleNamespace(
        _preview_revision=0,
        _queued_preview_request=None,
        _preview_after_id=None,
        output_preview_enabled=_StubVariable(False),
        _preview_source_path=Path("input.png"),
        input_preview_image=SimpleNamespace(size=(10, 10)),
        _export_running=False,
        after=lambda *_args: after_calls.append(_args),
    )
    app._cancel_scheduled_output_preview = lambda: (
        UpscalerGui._cancel_scheduled_output_preview(app)
    )

    UpscalerGui._schedule_output_preview(app)

    assert after_calls == []
    assert app._preview_revision == 1


def test_finished_export_does_not_display_output_when_preview_is_disabled(tmp_path) -> None:
    output_path = tmp_path / "output.png"
    loaded: list[Path] = []
    app = SimpleNamespace(
        _export_running=True,
        _set_controls_enabled=lambda _enabled: None,
        status_text=_StubVariable(""),
        output_preview_enabled=_StubVariable(False),
        _load_output_preview=loaded.append,
    )

    UpscalerGui._finish_export(app, output_path, None)

    assert app._export_running is False
    assert loaded == []
    assert str(output_path) in app.status_text.get()


def test_gui_check_config_loads_bundled_preset() -> None:
    assert main(["--check-config"]) == 0


def test_gui_check_upscale_uses_exact_default_export_config(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    calls: list[tuple[Path, Path, dict[str, object], str]] = []

    def fake_upscale(input_value, output_value, config, *, preset) -> None:
        calls.append((input_value, output_value, config, preset))

    monkeypatch.setattr(gui_module, "upscale_image", fake_upscale)

    assert main(["--check-upscale", str(input_path), str(output_path)]) == 0
    assert len(calls) == 1
    actual_input, actual_output, config, preset = calls[0]
    assert actual_input == input_path
    assert actual_output == output_path
    assert preset == "line_only"
    assert config["io"]["overwrite"] is True
    assert config["pipeline"]["scale"] == 4
    assert config["sdf"]["soft_sdf_threshold"] == threshold_from_brightness(0)


def test_gui_check_separate_psd_writes_layered_output(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.psd"
    image = np.full((12, 16), 220, dtype=np.uint8)
    image[5:7, 2:14] = 40
    Image.fromarray(image).save(input_path)

    assert main(["--check-separate-psd", str(input_path), str(output_path)]) == 0

    payload = output_path.read_bytes()
    assert payload[:4] == b"8BPS"
    assert b"Line Art" in payload
    assert b"Grayscale Tone" in payload


def test_gui_check_ui_builds_preview_checkbox_next_to_scale() -> None:
    app = UpscalerGui()
    app.withdraw()
    app.update_idletasks()
    try:
        assert app.title() == "723モノクロ線画拡大ツール　1.00"
        app._render_preview()
        placeholder_texts = [
            app.preview_canvas.itemcget(item_id, "text")
            for item_id in app.preview_canvas.find_all()
            if app.preview_canvas.type(item_id) == "text"
        ]
        assert "入力画像および出力結果のプレビューがここに表示されます。" in placeholder_texts
        assert app.output_preview_enabled.get() is True
        assert app.grayscale_mode_heading.cget("text") == "グレー部分の扱い"
        assert app.grayscale_mode_label.get() == "線画と黒ベタのみ"
        assert list(app.grayscale_mode_box.cget("values")) == list(GRAYSCALE_MODE_LABELS)
        assert app.separate_psd_enabled.get() is True
        assert app.separate_psd_checkbox.cget("text") == "PSDで出力する"
        assert app.separate_psd_checkbox in app._processing_controls
        assert app.separate_psd_checkbox.grid_info() == {}
        app.grayscale_mode_label.set("線画とグレー部分を分けて出力")
        app._on_grayscale_mode_changed(app.grayscale_mode_label.get())
        assert app.separate_psd_checkbox.grid_info()
        app.separate_psd_enabled.set(False)
        app.grayscale_mode_label.set("線画と黒ベタのみ")
        app._on_grayscale_mode_changed(app.grayscale_mode_label.get())
        assert app.separate_psd_checkbox.grid_info() == {}
        app.grayscale_mode_label.set("線画とグレー部分を分けて出力")
        app._on_grayscale_mode_changed(app.grayscale_mode_label.get())
        assert app.separate_psd_enabled.get() is False
        assert app.scale_box.master is app.output_preview_checkbox.master
        assert int(app.scale_box.grid_info()["column"]) == 0
        assert int(app.output_preview_checkbox.grid_info()["column"]) == 1
        assert app.brightness_decrease_button.cget("text") == "-"
        assert app.brightness_increase_button.cget("text") == "+"
        assert app.brightness_decrease_button.master is app.brightness_scale.master
        assert app.brightness_increase_button.master is app.brightness_scale.master
        assert int(app.brightness_decrease_button.grid_info()["column"]) == 0
        assert int(app.brightness_scale.grid_info()["column"]) == 1
        assert int(app.brightness_increase_button.grid_info()["column"]) == 2
        assert app.brightness_decrease_button in app._processing_controls
        assert app.brightness_increase_button in app._processing_controls
    finally:
        app.destroy()


def test_batch_export_cancel_uses_exact_count_and_does_not_start_worker(
    tmp_path, monkeypatch
) -> None:
    prompts: list[tuple[str, str]] = []
    input_paths = tuple(tmp_path / f"input_{index}.png" for index in range(3))
    app = SimpleNamespace(
        output_dir=_StubVariable(str(tmp_path)),
        scale_value=_StubVariable("4"),
        _selected_batch_input_paths=lambda: input_paths,
        _threshold_value=lambda: 0.36,
    )
    monkeypatch.setattr(
        messagebox,
        "askyesno",
        lambda title, text: prompts.append((title, text)) or False,
    )

    UpscalerGui._start_batch_export(app)

    assert prompts == [
        ("一括変換の確認", "3枚の画像を一括変換します。よろしいですか？")
    ]


def test_batch_export_ok_freezes_jobs_and_starts_one_worker(tmp_path, monkeypatch) -> None:
    input_paths = tuple(tmp_path / f"input_{index}.png" for index in range(2))
    started: list[tuple[object, tuple[object, ...], bool]] = []
    enabled_states: list[bool] = []

    class FakeThread:
        def __init__(self, *, target, args, daemon) -> None:
            self.record = (target, args, daemon)

        def start(self) -> None:
            started.append(self.record)

    app = SimpleNamespace(
        output_dir=_StubVariable(str(tmp_path)),
        scale_value=_StubVariable("4"),
        status_text=_StubVariable(""),
        _selected_batch_input_paths=lambda: input_paths,
        _threshold_value=lambda: 0.36,
        _run_batch_export_worker=lambda *_args: None,
        _set_controls_enabled=enabled_states.append,
        _invalidate_output_preview=lambda **_kwargs: None,
    )
    monkeypatch.setattr(messagebox, "askyesno", lambda *_args: True)
    monkeypatch.setattr(gui_module.threading, "Thread", FakeThread)

    UpscalerGui._start_batch_export(app)

    assert enabled_states == [False]
    assert len(started) == 1
    target, args, daemon = started[0]
    assert target is app._run_batch_export_worker
    assert tuple(input_path for input_path, _output_path in args[0]) == input_paths
    assert args[1:] == (4, 0.36, "legacy", "png")
    assert daemon is True
    assert app.status_text.get() == "一括変換を開始します（全2枚）。"


def test_batch_preview_loads_only_the_first_matching_image(tmp_path) -> None:
    (tmp_path / "b.png").write_bytes(b"")
    (tmp_path / "a.png").write_bytes(b"")
    loaded: list[Path] = []
    input_paths = (tmp_path / "a.png", tmp_path / "b.png")
    app = SimpleNamespace(
        input_mode="folder",
        input_path=_StubVariable(str(tmp_path)),
        batch_preview_input_path=None,
        status_text=_StubVariable(""),
        _selected_batch_input_paths=lambda: input_paths,
        _load_input_preview=loaded.append,
        _clear_preview=lambda: None,
    )

    UpscalerGui._refresh_batch_preview(app)

    assert loaded == [tmp_path / "a.png"]
    assert app.batch_preview_input_path == tmp_path / "a.png"


def test_batch_preview_handles_folder_scan_os_error() -> None:
    cleared: list[bool] = []
    app = SimpleNamespace(
        input_mode="folder",
        input_path=_StubVariable("unreadable"),
        status_text=_StubVariable(""),
        _selected_batch_input_paths=lambda: (_ for _ in ()).throw(PermissionError("denied")),
        _clear_preview=lambda: cleared.append(True),
    )

    UpscalerGui._refresh_batch_preview(app)

    assert cleared == [True]
    assert "denied" in app.status_text.get()


def test_batch_worker_continues_after_a_file_fails(tmp_path, monkeypatch) -> None:
    jobs = tuple(
        (tmp_path / f"input_{index}.png", tmp_path / f"output_{index}.png")
        for index in range(3)
    )
    calls: list[Path] = []
    finished: list[tuple[Path | None, int, tuple[tuple[Path, str], ...], object]] = []

    def fake_upscale(input_path, _output_path, _config, *, preset) -> None:
        assert preset == "line_only"
        calls.append(input_path)
        if input_path == jobs[1][0]:
            raise ValueError("broken image")

    app = SimpleNamespace(
        status_text=_StubVariable(""),
        _load_export_config=lambda **_kwargs: {},
        after=lambda _delay, callback: callback(),
        _finish_batch_export=lambda first, succeeded, failures, error: finished.append(
            (first, succeeded, failures, error)
        ),
        _pipeline_lock=gui_module.threading.Lock(),
    )
    monkeypatch.setattr(gui_module, "upscale_image", fake_upscale)

    UpscalerGui._run_batch_export_worker(app, jobs, 4, 0.36)

    assert calls == [job[0] for job in jobs]
    assert finished == [(jobs[0][1], 2, ((jobs[1][0], "broken image"),), None)]


class _StubVariable:
    def __init__(self, value: object) -> None:
        self.value = value

    def get(self) -> object:
        return self.value

    def set(self, value: object) -> None:
        self.value = value
