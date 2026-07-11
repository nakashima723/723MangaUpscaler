"""Tkinter GUI for the manga line-art upscaler."""

from __future__ import annotations

import argparse
import re
import tempfile
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk
from PIL import Image, ImageOps, ImageTk

from mlu import __version__
from mlu.config import ConfigError, load_config
from mlu.pipeline import separated_tone_path, upscale_image
from mlu.scales import SUPPORTED_SCALES

BRIGHTNESS_MIN = -10
BRIGHTNESS_MAX = 10
BRIGHTNESS_THRESHOLD_MIN = 0.06
BRIGHTNESS_THRESHOLD_DEFAULT = 0.291
BRIGHTNESS_THRESHOLD_MAX = 0.621
PREVIEW_MAX_DIMENSION = 8000
PREVIEW_MIN_INPUT_DISPLAY_SCALE = 0.01
PREVIEW_MAX_INPUT_DISPLAY_SCALE = 16.0
OUTPUT_PREVIEW_CONFIRM_PIXELS = 36_000_000
OUTPUT_PREVIEW_DEBOUNCE_MS = 200
SUPPORTED_GUI_EXTENSIONS = ("png", "jpg", "jpeg", "tif", "tiff", "bmp")
ALL_EXTENSIONS_LABEL = "すべての対応画像"
GRAYSCALE_MODE_LABELS = {
    "線画と黒ベタのみ": "legacy",
    "グレー部分を除去して線画のみ出力": "line_only",
    "線画とグレー部分を分けて出力": "separate",
    "グレー部分を線画と合成して出力": "composite",
}
DEFAULT_GRAYSCALE_MODE_LABEL = next(iter(GRAYSCALE_MODE_LABELS))
INVALID_FILENAME_FILTER_CHARS = frozenset('<>:"/\\|?*')
GUI_OUTPUT_NAME_PATTERN = re.compile(
    r".+_x(?:2|3|4|6|8)_thr\d{3}(?:_\d+)?(?:(?:_tone)?\.png|\.psd)",
    re.IGNORECASE,
)

APP_BACKGROUND = "#EEF1F5"
SURFACE = "#FFFFFF"
SURFACE_SUBTLE = "#F7F8FA"
BORDER = "#D8DEE8"
TEXT_PRIMARY = "#1D2939"
TEXT_MUTED = "#667085"
PRIMARY = "#2563EB"
PRIMARY_HOVER = "#1D4ED8"
SECONDARY = "#F2F4F7"
SECONDARY_HOVER = "#E4E7EC"
PREVIEW_BACKGROUND = "#191B1F"

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


@dataclass(frozen=True)
class OutputPreviewRequest:
    """Frozen GUI settings for one live output-preview render."""

    revision: int
    input_path: Path
    scale: int
    threshold: float
    output_size: tuple[int, int]
    grayscale_mode: str = "legacy"


@dataclass(frozen=True)
class PreviewViewState:
    """Zoom and center expressed in stable input-image coordinates."""

    input_display_scale: float
    center_input_x: float
    center_input_y: float


def threshold_from_brightness(brightness: int) -> float:
    """Map the user-facing brightness level to soft_sdf_threshold."""

    level = max(BRIGHTNESS_MIN, min(BRIGHTNESS_MAX, int(brightness)))
    if level <= 0:
        position = (level - BRIGHTNESS_MIN) / -BRIGHTNESS_MIN
        threshold = BRIGHTNESS_THRESHOLD_MIN + position * (
            BRIGHTNESS_THRESHOLD_DEFAULT - BRIGHTNESS_THRESHOLD_MIN
        )
    else:
        position = level / BRIGHTNESS_MAX
        threshold = BRIGHTNESS_THRESHOLD_DEFAULT + position * (
            BRIGHTNESS_THRESHOLD_MAX - BRIGHTNESS_THRESHOLD_DEFAULT
        )
    return round(threshold, 3)


def format_brightness_label(brightness: int) -> str:
    """Return the localized brightness label shown beside the slider."""

    level = max(BRIGHTNESS_MIN, min(BRIGHTNESS_MAX, int(brightness)))
    level_text = "0" if level == 0 else f"{level:+d}"
    return f"明るさ: {level_text}"


def selected_grayscale_mode(gui: object) -> str:
    """Resolve the current GUI mode, defaulting old/test callers to legacy."""

    variable = getattr(gui, "grayscale_mode_label", None)
    if variable is None:
        return "legacy"
    label = variable.get()
    try:
        return GRAYSCALE_MODE_LABELS[label]
    except KeyError as exc:
        raise ValueError(f"未対応の階調処理モードです: {label}") from exc


def selected_separate_psd(gui: object, grayscale_mode: str) -> bool:
    """Return the frozen PSD choice, defaulting old/test callers to PNG."""

    variable = getattr(gui, "separate_psd_enabled", None)
    return bool(
        grayscale_mode == "separate"
        and variable is not None
        and variable.get()
    )


def load_export_config(
    *,
    scale: int,
    threshold: float,
    overwrite: bool = False,
    grayscale_mode: str = "legacy",
    separate_output_format: str = "png",
) -> dict[str, Any]:
    """Load the exact processing configuration used by GUI exports."""

    return load_config(
        preset="line_only",
        cli_overrides={
            "io": {"overwrite": overwrite},
            "pipeline": {
                "scale": scale,
                "line_renderer": "sdf",
                "tone_mode": "white_canvas",
            },
            "sdf": {
                "distance_source": "soft_mask_hr",
                "soft_sdf_threshold": threshold,
                "soft_alpha_mode": "none",
                "soft_gain": 0.0,
            },
            "upscaler": {"engine": "none"},
            "grayscale_processing": {
                "mode": grayscale_mode,
                "separate_output_format": separate_output_format,
            },
            "debug": {"save_layers": False, "save_run_json": False},
        },
    )


def make_output_path(
    input_path: Path,
    output_dir: Path,
    *,
    scale: int,
    threshold: float,
    grayscale_mode: str = "legacy",
    separate_psd: bool = False,
) -> Path:
    """Return a unique GUI output path in the selected folder."""

    threshold_text = f"{int(round(threshold * 100)):03d}"
    extension = ".psd" if grayscale_mode == "separate" and separate_psd else ".png"
    base = output_dir / f"{input_path.stem}_x{scale}_thr{threshold_text}{extension}"
    if _gui_output_path_available(
        base,
        grayscale_mode=grayscale_mode,
        separate_psd=separate_psd,
    ):
        return base
    for index in range(2, 10_000):
        candidate = output_dir / (
            f"{input_path.stem}_x{scale}_thr{threshold_text}_{index}{extension}"
        )
        if _gui_output_path_available(
            candidate,
            grayscale_mode=grayscale_mode,
            separate_psd=separate_psd,
        ):
            return candidate
    raise FileExistsError("Could not create a unique output filename.")


def make_batch_output_paths(
    input_paths: tuple[Path, ...],
    output_dir: Path,
    *,
    scale: int,
    threshold: float,
    grayscale_mode: str = "legacy",
    separate_psd: bool = False,
) -> tuple[Path, ...]:
    """Return unique output paths for a frozen GUI batch input list."""

    threshold_text = f"{int(round(threshold * 100)):03d}"
    reserved: set[str] = set()
    output_paths: list[Path] = []
    extension = ".psd" if grayscale_mode == "separate" and separate_psd else ".png"
    for input_path in input_paths:
        base = output_dir / f"{input_path.stem}_x{scale}_thr{threshold_text}{extension}"
        candidate = base
        for index in range(1, 10_000):
            key = str(candidate.absolute()).casefold()
            if (
                _gui_output_path_available(
                    candidate,
                    grayscale_mode=grayscale_mode,
                    separate_psd=separate_psd,
                )
                and key not in reserved
            ):
                reserved.add(key)
                output_paths.append(candidate)
                break
            candidate = output_dir / (
                f"{input_path.stem}_x{scale}_thr{threshold_text}_{index + 1}{extension}"
            )
        else:
            raise FileExistsError("Could not create a unique output filename.")
    return tuple(output_paths)


def _gui_output_path_available(
    path: Path,
    *,
    grayscale_mode: str,
    separate_psd: bool,
) -> bool:
    if path.exists():
        return False
    if separate_psd:
        return True
    return grayscale_mode != "separate" or not separated_tone_path(path).exists()


def normalize_filename_filter(text: str) -> str:
    """Remove characters that cannot occur in a Windows filename filter."""

    return "".join(
        character
        for character in text.strip()
        if character not in INVALID_FILENAME_FILTER_CHARS and ord(character) >= 32
    ).strip()


def discover_gui_batch_images(
    input_dir: str | Path,
    *,
    extension: str,
    filename_filter_enabled: bool,
    filename_filter_text: str,
    output_dir: str | Path | None = None,
) -> tuple[Path, ...]:
    """Return matching supported images directly inside a selected GUI folder."""

    source_dir = Path(input_dir)
    if not source_dir.exists():
        raise ValueError(f"Input directory does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise ValueError(f"Input path is not a directory: {source_dir}")

    if extension == ALL_EXTENSIONS_LABEL:
        extensions = set(SUPPORTED_GUI_EXTENSIONS)
    else:
        normalized_extension = extension.lower().lstrip(".")
        if normalized_extension not in SUPPORTED_GUI_EXTENSIONS:
            raise ValueError(f"Unsupported image extension: {extension}")
        extensions = {normalized_extension}

    filename_filter = (
        normalize_filename_filter(filename_filter_text) if filename_filter_enabled else ""
    )
    filter_key = filename_filter.casefold()
    output_is_input = output_dir is not None and (
        str(Path(output_dir).absolute()).casefold() == str(source_dir.absolute()).casefold()
    )
    paths = [
        path
        for path in source_dir.iterdir()
        if path.is_file()
        and path.suffix.lower().lstrip(".") in extensions
        and (not filter_key or filter_key in path.stem.casefold())
        and not (output_is_input and GUI_OUTPUT_NAME_PATTERN.fullmatch(path.name))
    ]
    return tuple(sorted(paths, key=lambda path: path.name.casefold()))


def comparison_scale_for_images(input_size: tuple[int, int], output_size: tuple[int, int]) -> float:
    """Return the display scale needed to align input pixels to output pixels."""

    input_width, input_height = input_size
    output_width, output_height = output_size
    if input_width <= 0 or input_height <= 0 or output_width <= 0 or output_height <= 0:
        raise ValueError("Image sizes must be positive.")
    return min(output_width / input_width, output_height / input_height)


def capture_preview_view_state(
    *,
    preview_scale: float,
    preview_offset: tuple[int, int],
    pane_size: tuple[int, int],
    input_to_output_scale: float,
) -> PreviewViewState:
    """Capture the visible center and zoom in input-image coordinates."""

    if preview_scale <= 0.0 or input_to_output_scale <= 0.0:
        raise ValueError("Preview scales must be positive.")
    pane_width, pane_height = pane_size
    offset_x, offset_y = preview_offset
    input_display_scale = preview_scale * input_to_output_scale
    return PreviewViewState(
        input_display_scale=input_display_scale,
        center_input_x=(pane_width / 2.0 - offset_x) / input_display_scale,
        center_input_y=(pane_height / 2.0 - offset_y) / input_display_scale,
    )


def preview_geometry_from_view_state(
    state: PreviewViewState,
    *,
    pane_size: tuple[int, int],
    input_to_output_scale: float,
) -> tuple[float, int, int]:
    """Restore input-coordinate zoom and center for a new output scale."""

    if input_to_output_scale <= 0.0:
        raise ValueError("Input-to-output scale must be positive.")
    pane_width, pane_height = pane_size
    preview_scale = state.input_display_scale / input_to_output_scale
    offset_x = int(
        round(pane_width / 2.0 - state.center_input_x * state.input_display_scale)
    )
    offset_y = int(
        round(pane_height / 2.0 - state.center_input_y * state.input_display_scale)
    )
    return preview_scale, offset_x, offset_y


def output_preview_size(input_size: tuple[int, int], scale: int) -> tuple[int, int]:
    """Return the actual output dimensions for a source image and integer scale."""

    width, height = input_size
    if width <= 0 or height <= 0 or scale <= 0:
        raise ValueError("Image size and scale must be positive.")
    return width * scale, height * scale


def output_preview_requires_confirmation(output_size: tuple[int, int]) -> bool:
    """Return whether a live preview is large enough to require confirmation."""

    width, height = output_size
    if width <= 0 or height <= 0:
        raise ValueError("Output size must be positive.")
    # The requirement cites 6000x6000 as the boundary example, so equality is included.
    return width * height >= OUTPUT_PREVIEW_CONFIRM_PIXELS


def output_preview_confirmation_message(output_size: tuple[int, int]) -> str:
    """Return the localized large-preview confirmation text."""

    width, height = output_size
    return (
        f"出力サイズが縦{height}px・横{width}pxと大きいため、変換に時間がかかります。"
        "出力プレビューを表示しますか？"
    )


def generate_output_preview_image(
    input_path: Path,
    config: dict[str, Any],
) -> Image.Image:
    """Render the exact output PNG in a self-cleaning temporary directory."""

    with tempfile.TemporaryDirectory(prefix="723UpScaler_preview_") as temp_dir:
        preview_path = Path(temp_dir) / "preview.png"
        upscale_image(input_path, preview_path, config, preset="line_only")
        with Image.open(preview_path) as image:
            return ImageOps.exif_transpose(image).convert("L").copy()


class UpscalerGui(ctk.CTk):
    """Desktop GUI for single-image and folder batch line-art upscaling."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"723モノクロ線画拡大ツール　{__version__}")
        self.geometry("1240x820")
        self.minsize(940, 640)
        self.configure(fg_color=APP_BACKGROUND)

        self.input_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.scale_value = tk.StringVar(value="4")
        self.grayscale_mode_label = tk.StringVar(value=DEFAULT_GRAYSCALE_MODE_LABEL)
        self.separate_psd_enabled = tk.BooleanVar(value=True)
        self.brightness_value = tk.IntVar(value=0)
        self.brightness_label = tk.StringVar()
        self.output_preview_enabled = tk.BooleanVar(value=True)
        self.batch_filter_enabled = tk.BooleanVar(value=False)
        self.batch_filter_text = tk.StringVar()
        self.batch_extension = tk.StringVar(value=ALL_EXTENSIONS_LABEL)
        self.status_text = tk.StringVar(value="入力画像を選択してください。")
        self.input_mode = "file"
        self.batch_preview_input_path: Path | None = None
        self._output_dir_is_automatic = True

        self.input_preview_image: Image.Image | None = None
        self.output_preview_image: Image.Image | None = None
        self.preview_photos: list[ImageTk.PhotoImage] = []
        self.input_to_output_preview_scale = 1.0
        self.preview_scale = 1.0
        self.preview_offset_x = 0
        self.preview_offset_y = 0
        self._drag_origin: tuple[int, int] | None = None
        self._processing_controls: list[Any] = []
        self._preview_source_path: Path | None = None
        self._large_preview_approved_source: Path | None = None
        self._preview_revision = 0
        self._preview_after_id: str | None = None
        self._preview_worker_running = False
        self._queued_preview_request: OutputPreviewRequest | None = None
        self._export_running = False
        self._pipeline_lock = threading.Lock()

        self.ui_font = ctk.CTkFont(family="Segoe UI", size=13)
        self.label_font = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        self.section_font = ctk.CTkFont(family="Segoe UI", size=15, weight="bold")

        self._build_widgets()
        self._update_brightness_label()

    def _build_widgets(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        controls = ctk.CTkFrame(
            self,
            fg_color=SURFACE,
            corner_radius=8,
            border_width=1,
            border_color=BORDER,
        )
        controls.grid(row=0, column=0, padx=16, pady=(16, 12), sticky="ew")
        controls.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            controls,
            text="出力設定",
            font=self.section_font,
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, columnspan=6, padx=16, pady=(14, 8), sticky="ew")

        self._build_input_row(controls, row=1)
        self._build_batch_options(controls, row=2)
        self._build_path_row(
            controls,
            row=3,
            label="出力先",
            variable=self.output_dir,
            command=self._choose_output_dir,
        )

        grayscale_mode_heading = ctk.CTkLabel(
            controls,
            text="グレー部分の扱い",
            font=self.label_font,
            text_color=TEXT_PRIMARY,
            anchor="w",
            width=112,
        )
        grayscale_mode_heading.grid(
            row=4,
            column=0,
            padx=(16, 10),
            pady=(4, 8),
            sticky="w",
        )
        self.grayscale_mode_heading = grayscale_mode_heading
        grayscale_mode_box = ctk.CTkOptionMenu(
            controls,
            variable=self.grayscale_mode_label,
            values=list(GRAYSCALE_MODE_LABELS),
            command=self._on_grayscale_mode_changed,
            width=300,
            height=36,
            corner_radius=6,
            fg_color=SECONDARY,
            button_color="#E4E7EC",
            button_hover_color="#D0D5DD",
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=SURFACE,
            dropdown_hover_color=SECONDARY,
            dropdown_text_color=TEXT_PRIMARY,
            font=self.ui_font,
            dropdown_font=self.ui_font,
        )
        grayscale_mode_box.grid(
            row=4,
            column=1,
            columnspan=3,
            padx=(0, 24),
            pady=(4, 8),
            sticky="w",
        )
        self.grayscale_mode_box = grayscale_mode_box
        separate_psd_checkbox = ctk.CTkCheckBox(
            controls,
            text="PSDで出力する",
            variable=self.separate_psd_enabled,
            checkbox_width=20,
            checkbox_height=20,
            border_width=2,
            corner_radius=4,
            fg_color=PRIMARY,
            hover_color=PRIMARY_HOVER,
            border_color="#98A2B3",
            text_color=TEXT_PRIMARY,
            font=self.ui_font,
        )
        separate_psd_checkbox.grid(
            row=4,
            column=4,
            columnspan=2,
            padx=(0, 16),
            pady=(4, 8),
            sticky="w",
        )
        separate_psd_checkbox.grid_remove()
        self.separate_psd_checkbox = separate_psd_checkbox

        ctk.CTkLabel(
            controls,
            text="出力倍率",
            font=self.label_font,
            text_color=TEXT_PRIMARY,
            anchor="w",
            width=88,
        ).grid(row=5, column=0, padx=(16, 10), pady=(10, 16), sticky="w")
        scale_controls = ctk.CTkFrame(controls, fg_color="transparent")
        scale_controls.grid(row=5, column=1, padx=(0, 24), pady=(10, 16), sticky="w")
        scale_box = ctk.CTkOptionMenu(
            scale_controls,
            variable=self.scale_value,
            values=[str(scale) for scale in SUPPORTED_SCALES],
            command=lambda _value: self._on_output_settings_changed(),
            width=100,
            height=36,
            corner_radius=6,
            fg_color=SECONDARY,
            button_color="#E4E7EC",
            button_hover_color="#D0D5DD",
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=SURFACE,
            dropdown_hover_color=SECONDARY,
            dropdown_text_color=TEXT_PRIMARY,
            font=self.ui_font,
            dropdown_font=self.ui_font,
        )
        scale_box.grid(row=0, column=0, sticky="w")
        self.scale_box = scale_box
        output_preview_checkbox = ctk.CTkCheckBox(
            scale_controls,
            text="プレビューを表示する",
            variable=self.output_preview_enabled,
            command=self._on_output_preview_toggled,
            checkbox_width=20,
            checkbox_height=20,
            border_width=2,
            corner_radius=4,
            fg_color=PRIMARY,
            hover_color=PRIMARY_HOVER,
            border_color="#98A2B3",
            text_color=TEXT_PRIMARY,
            font=self.ui_font,
        )
        output_preview_checkbox.grid(row=0, column=1, padx=(14, 0), sticky="w")
        self.output_preview_checkbox = output_preview_checkbox

        ctk.CTkLabel(
            controls,
            textvariable=self.brightness_label,
            font=self.label_font,
            text_color=TEXT_PRIMARY,
            anchor="e",
            width=92,
        ).grid(row=5, column=2, padx=(0, 12), pady=(10, 16), sticky="e")

        slider_frame = ctk.CTkFrame(controls, fg_color="transparent")
        slider_frame.grid(
            row=5,
            column=3,
            columnspan=2,
            padx=(0, 24),
            pady=(10, 16),
            sticky="ew",
        )
        slider_frame.grid_columnconfigure(1, weight=1)
        brightness_decrease_button = ctk.CTkButton(
            slider_frame,
            text="-",
            command=lambda: self._adjust_brightness(-1),
            font=self.ui_font,
            width=30,
            height=30,
            corner_radius=6,
            fg_color=SECONDARY,
            hover_color=SECONDARY_HOVER,
            text_color=TEXT_PRIMARY,
        )
        brightness_decrease_button.grid(row=0, column=0, padx=(0, 8))
        self.brightness_decrease_button = brightness_decrease_button
        brightness_scale = ctk.CTkSlider(
            slider_frame,
            from_=BRIGHTNESS_MIN,
            to=BRIGHTNESS_MAX,
            number_of_steps=BRIGHTNESS_MAX - BRIGHTNESS_MIN,
            variable=self.brightness_value,
            command=self._on_brightness_changed,
            height=18,
            border_width=0,
            fg_color="#D0D5DD",
            progress_color=PRIMARY,
            button_color=PRIMARY,
            button_hover_color=PRIMARY_HOVER,
        )
        brightness_scale.grid(row=0, column=1, sticky="ew")
        self.brightness_scale = brightness_scale
        brightness_increase_button = ctk.CTkButton(
            slider_frame,
            text="+",
            command=lambda: self._adjust_brightness(1),
            font=self.ui_font,
            width=30,
            height=30,
            corner_radius=6,
            fg_color=SECONDARY,
            hover_color=SECONDARY_HOVER,
            text_color=TEXT_PRIMARY,
        )
        brightness_increase_button.grid(row=0, column=2, padx=(8, 0))
        self.brightness_increase_button = brightness_increase_button

        export_button = ctk.CTkButton(
            controls,
            text="出力する",
            command=self._start_export,
            width=140,
            height=42,
            corner_radius=7,
            fg_color=PRIMARY,
            hover_color=PRIMARY_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        )
        export_button.grid(row=5, column=5, padx=(0, 16), pady=(8, 14), sticky="e")
        self._processing_controls.extend(
            [
                scale_box,
                grayscale_mode_box,
                separate_psd_checkbox,
                output_preview_checkbox,
                self.brightness_decrease_button,
                brightness_scale,
                self.brightness_increase_button,
                export_button,
            ]
        )

        preview_shell = ctk.CTkFrame(
            self,
            fg_color=PREVIEW_BACKGROUND,
            corner_radius=8,
            border_width=1,
            border_color=BORDER,
        )
        preview_shell.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")
        preview_shell.grid_rowconfigure(1, weight=1)
        preview_shell.grid_columnconfigure(0, weight=1)
        self._build_preview_toolbar(preview_shell)

        self.preview_canvas = tk.Canvas(
            preview_shell,
            background=PREVIEW_BACKGROUND,
            highlightthickness=0,
            cursor="hand2",
        )
        self.preview_canvas.grid(row=1, column=0, padx=1, pady=(0, 1), sticky="nsew")
        self.preview_canvas.bind("<ButtonPress-1>", self._start_pan)
        self.preview_canvas.bind("<B1-Motion>", self._drag_pan)
        self.preview_canvas.bind("<ButtonRelease-1>", self._end_pan)
        self.preview_canvas.bind("<Configure>", lambda _event: self._render_preview())

    def _build_input_row(self, parent: ctk.CTkFrame, *, row: int) -> None:
        ctk.CTkLabel(
            parent,
            text="入力画像",
            font=self.label_font,
            text_color=TEXT_PRIMARY,
            anchor="w",
            width=88,
        ).grid(row=row, column=0, padx=(16, 10), pady=6, sticky="w")
        path_entry = ctk.CTkEntry(
            parent,
            textvariable=self.input_path,
            height=36,
            corner_radius=6,
            border_width=1,
            border_color=BORDER,
            fg_color=SURFACE_SUBTLE,
            text_color=TEXT_PRIMARY,
            font=self.ui_font,
        )
        path_entry.grid(row=row, column=1, columnspan=3, padx=(0, 10), pady=6, sticky="ew")
        path_entry.bind("<Key>", lambda _event: "break")

        file_button = ctk.CTkButton(
            parent,
            text="ファイルを選択",
            command=self._choose_input,
            width=116,
            height=36,
            corner_radius=6,
            fg_color=SECONDARY,
            hover_color=SECONDARY_HOVER,
            text_color=TEXT_PRIMARY,
            font=self.label_font,
        )
        file_button.grid(row=row, column=4, padx=(0, 8), pady=6, sticky="e")
        folder_button = ctk.CTkButton(
            parent,
            text="フォルダを指定して一括変換",
            command=self._choose_batch_folder,
            width=210,
            height=36,
            corner_radius=6,
            fg_color=SECONDARY,
            hover_color=SECONDARY_HOVER,
            text_color=TEXT_PRIMARY,
            font=self.label_font,
        )
        folder_button.grid(row=row, column=5, padx=(0, 16), pady=6, sticky="e")
        self._processing_controls.extend([file_button, folder_button])

    def _build_batch_options(self, parent: ctk.CTkFrame, *, row: int) -> None:
        self.batch_options_frame = ctk.CTkFrame(parent, fg_color=SURFACE_SUBTLE, corner_radius=6)
        self.batch_options_frame.grid(
            row=row,
            column=1,
            columnspan=5,
            padx=(0, 16),
            pady=(2, 6),
            sticky="ew",
        )
        self.batch_options_frame.grid_columnconfigure(1, weight=1)

        filter_checkbox = ctk.CTkCheckBox(
            self.batch_options_frame,
            text="指定した文字列を含むファイルのみ変換",
            variable=self.batch_filter_enabled,
            command=self._toggle_batch_filter,
            checkbox_width=20,
            checkbox_height=20,
            font=self.ui_font,
            text_color=TEXT_PRIMARY,
            fg_color=PRIMARY,
            hover_color=PRIMARY_HOVER,
        )
        filter_checkbox.grid(row=0, column=0, padx=(12, 10), pady=10, sticky="w")
        self.batch_filter_entry = ctk.CTkEntry(
            self.batch_options_frame,
            textvariable=self.batch_filter_text,
            placeholder_text="ファイル名に含まれる文字列",
            height=32,
            corner_radius=6,
            border_width=1,
            border_color=BORDER,
            fg_color=SURFACE,
            text_color=TEXT_PRIMARY,
            font=self.ui_font,
        )
        self.batch_filter_entry.grid(row=0, column=1, padx=(0, 16), pady=8, sticky="ew")
        self.batch_filter_entry.bind("<KeyRelease>", lambda _event: self._refresh_batch_preview())

        ctk.CTkLabel(
            self.batch_options_frame,
            text="拡張子を指定",
            font=self.label_font,
            text_color=TEXT_PRIMARY,
        ).grid(row=0, column=2, padx=(0, 8), pady=8, sticky="e")
        extension_menu = ctk.CTkOptionMenu(
            self.batch_options_frame,
            variable=self.batch_extension,
            values=[ALL_EXTENSIONS_LABEL, *[f".{item}" for item in SUPPORTED_GUI_EXTENSIONS]],
            command=lambda _value: self._refresh_batch_preview(),
            width=162,
            height=32,
            corner_radius=6,
            fg_color=SECONDARY,
            button_color="#E4E7EC",
            button_hover_color="#D0D5DD",
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=SURFACE,
            dropdown_hover_color=SECONDARY,
            dropdown_text_color=TEXT_PRIMARY,
            font=self.ui_font,
            dropdown_font=self.ui_font,
        )
        extension_menu.grid(row=0, column=3, padx=(0, 12), pady=8, sticky="e")
        self._processing_controls.extend(
            [filter_checkbox, self.batch_filter_entry, extension_menu]
        )
        self.batch_filter_entry.grid_remove()
        self.batch_options_frame.grid_remove()

    def _build_path_row(
        self,
        parent: ctk.CTkFrame,
        *,
        row: int,
        label: str,
        variable: tk.StringVar,
        command: Any,
    ) -> None:
        ctk.CTkLabel(
            parent,
            text=label,
            font=self.label_font,
            text_color=TEXT_PRIMARY,
            anchor="w",
            width=88,
        ).grid(row=row, column=0, padx=(16, 10), pady=6, sticky="w")
        path_entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            height=36,
            corner_radius=6,
            border_width=1,
            border_color=BORDER,
            fg_color=SURFACE_SUBTLE,
            text_color=TEXT_PRIMARY,
            font=self.ui_font,
        )
        path_entry.grid(row=row, column=1, columnspan=4, padx=(0, 10), pady=6, sticky="ew")
        path_entry.bind("<Key>", lambda _event: "break")
        button = ctk.CTkButton(
            parent,
            text="選択",
            command=command,
            width=92,
            height=36,
            corner_radius=6,
            fg_color=SECONDARY,
            hover_color=SECONDARY_HOVER,
            text_color=TEXT_PRIMARY,
            font=self.label_font,
        )
        button.grid(row=row, column=5, padx=(0, 16), pady=6, sticky="e")
        self._processing_controls.append(button)

    def _build_preview_toolbar(self, parent: ctk.CTkFrame) -> None:
        toolbar = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=0, height=52)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.grid_columnconfigure(1, weight=1)
        toolbar.grid_propagate(False)

        ctk.CTkLabel(
            toolbar,
            text="プレビュー",
            font=self.section_font,
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, padx=(16, 20), pady=10, sticky="w")
        ctk.CTkLabel(
            toolbar,
            textvariable=self.status_text,
            font=self.ui_font,
            text_color=TEXT_MUTED,
            anchor="w",
        ).grid(row=0, column=1, padx=(0, 16), pady=10, sticky="ew")

        zoom_controls = ctk.CTkFrame(toolbar, fg_color="transparent")
        zoom_controls.grid(row=0, column=2, padx=(0, 12), pady=8, sticky="e")
        self._build_zoom_button(
            zoom_controls,
            column=0,
            text="+",
            command=lambda: self._zoom(1.25),
        )
        self._build_zoom_button(zoom_controls, column=1, text="−", command=lambda: self._zoom(0.8))
        ctk.CTkButton(
            zoom_controls,
            text="全体表示",
            command=self._fit_preview,
            width=88,
            height=34,
            corner_radius=6,
            fg_color=SECONDARY,
            hover_color=SECONDARY_HOVER,
            text_color=TEXT_PRIMARY,
            font=self.ui_font,
        ).grid(row=0, column=2)

    def _build_zoom_button(
        self,
        parent: ctk.CTkFrame,
        *,
        column: int,
        text: str,
        command: Any,
    ) -> None:
        ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=38,
            height=34,
            corner_radius=6,
            fg_color=SECONDARY,
            hover_color=SECONDARY_HOVER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=18),
        ).grid(row=0, column=column, padx=(0, 6))

    def _choose_input(self) -> None:
        patterns = " ".join(f"*.{extension}" for extension in SUPPORTED_GUI_EXTENSIONS)
        path = filedialog.askopenfilename(
            title="入力画像を選択",
            filetypes=[
                ("Image files", patterns),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self.input_mode = "file"
        self.batch_preview_input_path = None
        self.batch_options_frame.grid_remove()
        self.input_path.set(path)
        if self._output_dir_is_automatic:
            self.output_dir.set(str(Path(path).parent))
        try:
            self._load_input_preview(Path(path))
        except OSError as exc:
            self.status_text.set("入力画像のプレビューに失敗しました。")
            messagebox.showerror("プレビューエラー", str(exc))
            return
        self.status_text.set("入力画像をプレビューしています。出力条件を確認してください。")

    def _choose_batch_folder(self) -> None:
        initial_dir = self._input_parent_or_cwd()
        path = filedialog.askdirectory(title="一括変換するフォルダを選択", initialdir=initial_dir)
        if not path:
            return
        self.input_mode = "folder"
        self.input_path.set(path)
        self.batch_options_frame.grid()
        self._sync_batch_filter_entry()
        if self._output_dir_is_automatic:
            self.output_dir.set(str(Path(path) / "723UpScaler_output"))
        self._refresh_batch_preview()

    def _toggle_batch_filter(self) -> None:
        self._sync_batch_filter_entry()
        if self.batch_filter_enabled.get():
            self.batch_filter_entry.focus_set()
        self._refresh_batch_preview()

    def _sync_batch_filter_entry(self) -> None:
        if self.input_mode == "folder" and self.batch_filter_enabled.get():
            self.batch_filter_entry.grid()
        else:
            self.batch_filter_entry.grid_remove()

    def _selected_batch_input_paths(self) -> tuple[Path, ...]:
        return discover_gui_batch_images(
            self.input_path.get(),
            extension=self.batch_extension.get(),
            filename_filter_enabled=self.batch_filter_enabled.get(),
            filename_filter_text=self.batch_filter_text.get(),
            output_dir=self.output_dir.get() or None,
        )

    def _refresh_batch_preview(self) -> None:
        if self.input_mode != "folder" or not self.input_path.get():
            return
        try:
            input_paths = self._selected_batch_input_paths()
        except (OSError, ValueError) as exc:
            self._clear_preview()
            self.status_text.set(str(exc))
            return
        if not input_paths:
            self.batch_preview_input_path = None
            self._clear_preview()
            self.status_text.set("条件に一致する画像はありません。")
            return

        first_path = input_paths[0]
        self.batch_preview_input_path = first_path
        try:
            self._load_input_preview(first_path)
        except OSError as exc:
            self.batch_preview_input_path = None
            self._clear_preview()
            self.status_text.set(f"先頭画像のプレビューに失敗しました: {exc}")
            return
        self.status_text.set(
            f"{len(input_paths)}枚が対象です。最初の1枚をプレビューしています。"
        )

    def _choose_output_dir(self) -> None:
        initial_dir = self.output_dir.get() or self._input_parent_or_cwd()
        path = filedialog.askdirectory(title="出力フォルダを選択", initialdir=initial_dir)
        if path:
            self.output_dir.set(path)
            self._output_dir_is_automatic = False

    def _input_parent_or_cwd(self) -> str:
        if self.input_path.get():
            input_path = Path(self.input_path.get())
            if input_path.is_dir():
                return str(input_path)
            return str(input_path.parent)
        return str(Path.cwd())

    def _update_brightness_label(self) -> None:
        self.brightness_label.set(format_brightness_label(self.brightness_value.get()))

    def _on_brightness_changed(self, _value: float) -> None:
        self._update_brightness_label()
        self._schedule_output_preview()

    def _adjust_brightness(self, delta: int) -> None:
        current = max(
            BRIGHTNESS_MIN,
            min(BRIGHTNESS_MAX, int(self.brightness_value.get())),
        )
        updated = max(BRIGHTNESS_MIN, min(BRIGHTNESS_MAX, current + int(delta)))
        if updated == current:
            return
        self.brightness_scale.set(updated)
        self.brightness_value.set(updated)
        self._update_brightness_label()
        self._schedule_output_preview()

    def _on_output_settings_changed(self) -> None:
        self._schedule_output_preview()

    def _on_grayscale_mode_changed(self, _label: str) -> None:
        self._update_separate_psd_visibility()
        self._schedule_output_preview()

    def _update_separate_psd_visibility(self) -> None:
        if selected_grayscale_mode(self) == "separate":
            self.separate_psd_checkbox.grid()
        else:
            self.separate_psd_checkbox.grid_remove()

    def _separate_psd_requested(self, grayscale_mode: str) -> bool:
        return selected_separate_psd(self, grayscale_mode)

    def _grayscale_mode(self) -> str:
        return selected_grayscale_mode(self)

    def _on_output_preview_toggled(self) -> None:
        if self.output_preview_enabled.get():
            self._schedule_output_preview(delay_ms=0)
            return
        self._large_preview_approved_source = None
        self._invalidate_output_preview(clear_output=True)
        if self.input_preview_image is not None:
            self.status_text.set("出力プレビューは無効です。")

    def _schedule_output_preview(
        self,
        *,
        delay_ms: int = OUTPUT_PREVIEW_DEBOUNCE_MS,
    ) -> None:
        self._preview_revision += 1
        revision = self._preview_revision
        self._queued_preview_request = None
        self._cancel_scheduled_output_preview()
        if (
            not self.output_preview_enabled.get()
            or self._preview_source_path is None
            or self.input_preview_image is None
            or self._export_running
        ):
            return
        self._preview_after_id = self.after(
            max(0, int(delay_ms)),
            lambda current_revision=revision: self._prepare_output_preview(
                current_revision
            ),
        )

    def _cancel_scheduled_output_preview(self) -> None:
        if self._preview_after_id is None:
            return
        try:
            self.after_cancel(self._preview_after_id)
        except tk.TclError:
            pass
        self._preview_after_id = None

    def _invalidate_output_preview(self, *, clear_output: bool) -> None:
        self._preview_revision += 1
        self._queued_preview_request = None
        self._cancel_scheduled_output_preview()
        if clear_output:
            self._clear_output_preview()

    def _prepare_output_preview(self, revision: int) -> None:
        self._preview_after_id = None
        if (
            revision != self._preview_revision
            or not self.output_preview_enabled.get()
            or self._preview_source_path is None
            or self.input_preview_image is None
            or self._export_running
        ):
            return
        try:
            scale = int(self.scale_value.get())
            threshold = self._threshold_value()
            output_size = output_preview_size(self.input_preview_image.size, scale)
        except (TypeError, ValueError) as exc:
            self.status_text.set(f"出力プレビュー設定エラー: {exc}")
            return

        source_path = self._preview_source_path
        if (
            output_preview_requires_confirmation(output_size)
            and self._large_preview_approved_source != source_path
        ):
            approved = messagebox.askyesno(
                "出力プレビューの確認",
                output_preview_confirmation_message(output_size),
            )
            if not approved:
                self.output_preview_enabled.set(False)
                self._large_preview_approved_source = None
                self._invalidate_output_preview(clear_output=True)
                self.status_text.set("大きな出力プレビューを表示しません。")
                return
            self._large_preview_approved_source = source_path

        request = OutputPreviewRequest(
            revision=revision,
            input_path=source_path,
            scale=scale,
            threshold=threshold,
            output_size=output_size,
            grayscale_mode=selected_grayscale_mode(self),
        )
        if self._preview_worker_running:
            self._queued_preview_request = request
            self.status_text.set("最新設定の出力プレビューを予約しました。")
            return
        self._start_output_preview_worker(request)

    def _start_output_preview_worker(self, request: OutputPreviewRequest) -> None:
        if (
            request.revision != self._preview_revision
            or not self.output_preview_enabled.get()
            or self._export_running
        ):
            return
        self._preview_worker_running = True
        self.status_text.set("現在の設定で出力プレビューを生成中です。")
        threading.Thread(
            target=self._run_output_preview_worker,
            args=(request,),
            daemon=True,
        ).start()

    def _run_output_preview_worker(self, request: OutputPreviewRequest) -> None:
        preview_image: Image.Image | None = None
        error: BaseException | None = None
        try:
            config = self._load_export_config(
                scale=request.scale,
                threshold=request.threshold,
                grayscale_mode=request.grayscale_mode,
            )
            with self._pipeline_lock:
                preview_image = generate_output_preview_image(request.input_path, config)
        except Exception as exc:  # noqa: BLE001 - report preview failures in the GUI.
            error = exc
        try:
            self.after(
                0,
                lambda: self._finish_output_preview(request, preview_image, error),
            )
        except tk.TclError:
            if preview_image is not None:
                preview_image.close()

    def _finish_output_preview(
        self,
        request: OutputPreviewRequest,
        preview_image: Image.Image | None,
        error: BaseException | None,
    ) -> None:
        self._preview_worker_running = False
        is_current = bool(
            request.revision == self._preview_revision
            and self.output_preview_enabled.get()
            and request.input_path == self._preview_source_path
            and not self._export_running
        )
        if is_current and error is None and preview_image is not None:
            self._set_output_preview_image(preview_image)
            preview_image = None
            self.status_text.set("現在の設定で出力プレビューを表示しています。")
        elif is_current and error is not None:
            self.status_text.set(f"出力プレビューの生成に失敗しました: {error}")
        if preview_image is not None:
            preview_image.close()

        queued = self._queued_preview_request
        self._queued_preview_request = None
        if (
            queued is not None
            and queued.revision == self._preview_revision
            and self.output_preview_enabled.get()
            and not self._export_running
        ):
            self._start_output_preview_worker(queued)

    def _threshold_value(self) -> float:
        return threshold_from_brightness(int(self.brightness_value.get()))

    def _start_export(self) -> None:
        if not self.input_path.get():
            messagebox.showerror("入力エラー", "入力ファイルまたはフォルダを選択してください。")
            return
        if not self.output_dir.get():
            messagebox.showerror("入力エラー", "出力フォルダを選択してください。")
            return

        if self.input_mode == "folder":
            self._start_batch_export()
            return

        input_path = Path(self.input_path.get())
        output_dir = Path(self.output_dir.get())
        try:
            scale = int(self.scale_value.get())
            threshold = self._threshold_value()
            grayscale_mode = selected_grayscale_mode(self)
            separate_psd = selected_separate_psd(self, grayscale_mode)
            output_path = make_output_path(
                input_path,
                output_dir,
                scale=scale,
                threshold=threshold,
                grayscale_mode=grayscale_mode,
                separate_psd=separate_psd,
            )
        except Exception as exc:  # noqa: BLE001 - show GUI-friendly errors.
            messagebox.showerror("設定エラー", str(exc))
            return

        self.status_text.set("処理中です。")
        self._export_running = True
        self._invalidate_output_preview(clear_output=False)
        self._set_controls_enabled(False)
        thread = threading.Thread(
            target=self._run_export_worker,
            args=(
                input_path,
                output_path,
                scale,
                threshold,
                grayscale_mode,
                "psd" if separate_psd else "png",
            ),
            daemon=True,
        )
        thread.start()

    def _start_batch_export(self) -> None:
        output_dir = Path(self.output_dir.get())
        try:
            input_paths = self._selected_batch_input_paths()
            scale = int(self.scale_value.get())
            threshold = self._threshold_value()
            grayscale_mode = selected_grayscale_mode(self)
            separate_psd = selected_separate_psd(self, grayscale_mode)
        except Exception as exc:  # noqa: BLE001 - show GUI-friendly errors.
            messagebox.showerror("設定エラー", str(exc))
            return
        if not input_paths:
            messagebox.showerror("入力エラー", "条件に一致する画像はありません。")
            return
        if not messagebox.askyesno(
            "一括変換の確認",
            f"{len(input_paths)}枚の画像を一括変換します。よろしいですか？",
        ):
            return
        try:
            output_paths = make_batch_output_paths(
                input_paths,
                output_dir,
                scale=scale,
                threshold=threshold,
                grayscale_mode=grayscale_mode,
                separate_psd=separate_psd,
            )
        except Exception as exc:  # noqa: BLE001 - show GUI-friendly errors.
            messagebox.showerror("設定エラー", str(exc))
            return

        self.status_text.set(f"一括変換を開始します（全{len(input_paths)}枚）。")
        self._export_running = True
        self._invalidate_output_preview(clear_output=False)
        self._set_controls_enabled(False)
        jobs = tuple(zip(input_paths, output_paths, strict=True))
        thread = threading.Thread(
            target=self._run_batch_export_worker,
            args=(
                jobs,
                scale,
                threshold,
                grayscale_mode,
                "psd" if separate_psd else "png",
            ),
            daemon=True,
        )
        thread.start()

    def _run_export_worker(
        self,
        input_path: Path,
        output_path: Path,
        scale: int,
        threshold: float,
        grayscale_mode: str = "legacy",
        separate_output_format: str = "png",
    ) -> None:
        try:
            config = self._load_export_config(
                scale=scale,
                threshold=threshold,
                grayscale_mode=grayscale_mode,
                separate_output_format=separate_output_format,
            )
            with self._pipeline_lock:
                upscale_image(input_path, output_path, config, preset="line_only")
        except (ConfigError, OSError, ValueError, RuntimeError) as exc:
            self.after(0, lambda error=exc: self._finish_export(None, error))
        except Exception as exc:  # noqa: BLE001 - keep GUI from crashing.
            self.after(0, lambda error=exc: self._finish_export(None, error))
        else:
            self.after(0, lambda: self._finish_export(output_path, None))

    def _run_batch_export_worker(
        self,
        jobs: tuple[tuple[Path, Path], ...],
        scale: int,
        threshold: float,
        grayscale_mode: str = "legacy",
        separate_output_format: str = "png",
    ) -> None:
        try:
            config = self._load_export_config(
                scale=scale,
                threshold=threshold,
                grayscale_mode=grayscale_mode,
                separate_output_format=separate_output_format,
            )
        except Exception as exc:  # noqa: BLE001 - keep GUI from crashing.
            self.after(0, lambda error=exc: self._finish_batch_export(None, 0, (), error))
            return

        failures: list[tuple[Path, str]] = []
        succeeded_count = 0
        first_output_path: Path | None = None
        for index, (input_path, output_path) in enumerate(jobs, start=1):
            self.after(
                0,
                lambda current=index, total=len(jobs): self.status_text.set(
                    f"一括変換中です（{current}/{total}枚）。"
                ),
            )
            try:
                with self._pipeline_lock:
                    upscale_image(input_path, output_path, config, preset="line_only")
            except Exception as exc:  # noqa: BLE001 - continue with the remaining images.
                failures.append((input_path, str(exc)))
            else:
                succeeded_count += 1
                if index == 1:
                    first_output_path = output_path

        self.after(
            0,
            lambda: self._finish_batch_export(
                first_output_path,
                succeeded_count,
                tuple(failures),
                None,
            ),
        )

    def _load_export_config(
        self,
        *,
        scale: int,
        threshold: float,
        grayscale_mode: str = "legacy",
        separate_output_format: str = "png",
    ) -> dict[str, Any]:
        return load_export_config(
            scale=scale,
            threshold=threshold,
            grayscale_mode=grayscale_mode,
            separate_output_format=separate_output_format,
        )

    def _finish_export(self, output_path: Path | None, error: BaseException | None) -> None:
        self._export_running = False
        self._set_controls_enabled(True)
        if error is not None:
            self.status_text.set("出力に失敗しました。")
            messagebox.showerror("出力エラー", str(error))
            if self.output_preview_enabled.get():
                self._schedule_output_preview(delay_ms=0)
            return
        if output_path is None:
            return
        self.status_text.set(f"出力しました: {output_path}")
        if self.output_preview_enabled.get():
            self._load_output_preview(output_path)

    def _finish_batch_export(
        self,
        first_output_path: Path | None,
        succeeded_count: int,
        failures: tuple[tuple[Path, str], ...],
        error: BaseException | None,
    ) -> None:
        self._export_running = False
        self._set_controls_enabled(True)
        if error is not None:
            self.status_text.set("一括変換に失敗しました。")
            messagebox.showerror("一括変換エラー", str(error))
            if self.output_preview_enabled.get():
                self._schedule_output_preview(delay_ms=0)
            return

        total_count = succeeded_count + len(failures)
        if first_output_path is not None and self.output_preview_enabled.get():
            self._load_output_preview(first_output_path)
        if not failures:
            self.status_text.set(f"{succeeded_count}枚の一括変換が完了しました。")
            return

        self.status_text.set(
            f"一括変換が完了しました（成功{succeeded_count}枚、失敗{len(failures)}枚）。"
        )
        failure_lines = [f"{path.name}: {message}" for path, message in failures[:5]]
        if len(failures) > 5:
            failure_lines.append(f"ほか{len(failures) - 5}件")
        messagebox.showwarning(
            "一括変換完了",
            f"全{total_count}枚中、{succeeded_count}枚を出力しました。\n\n"
            + "\n".join(failure_lines),
        )

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in self._processing_controls:
            widget.configure(state=state)
        if enabled:
            self._sync_batch_filter_entry()

    def _clear_preview(self) -> None:
        self._preview_revision += 1
        self._queued_preview_request = None
        self._cancel_scheduled_output_preview()
        self._preview_source_path = None
        self._large_preview_approved_source = None
        if self.input_preview_image is not None:
            self.input_preview_image.close()
        if self.output_preview_image is not None:
            self.output_preview_image.close()
        self.input_preview_image = None
        self.output_preview_image = None
        self.preview_photos.clear()
        self.input_to_output_preview_scale = 1.0
        self.preview_scale = 1.0
        self.preview_offset_x = 0
        self.preview_offset_y = 0
        self._render_preview()

    def _clear_output_preview(self) -> None:
        if self.output_preview_image is not None:
            self.output_preview_image.close()
        self.output_preview_image = None
        self.input_to_output_preview_scale = 1.0
        if self.input_preview_image is not None:
            self._fit_preview()
        else:
            self._render_preview()

    def _load_input_preview(
        self,
        path: Path,
        *,
        schedule_output_preview: bool = True,
    ) -> None:
        source_path = Path(path).absolute()
        if source_path != self._preview_source_path:
            self._large_preview_approved_source = None
        self._preview_source_path = source_path
        if self.input_preview_image is not None:
            self.input_preview_image.close()
        with Image.open(path) as image:
            self.input_preview_image = ImageOps.exif_transpose(image).convert("L").copy()
        self._clear_output_preview()
        if schedule_output_preview:
            self._schedule_output_preview(delay_ms=0)

    def _set_output_preview_image(self, image: Image.Image) -> None:
        view_state: PreviewViewState | None = None
        if self.input_preview_image is not None and self.output_preview_image is not None:
            view_state = capture_preview_view_state(
                preview_scale=self.preview_scale,
                preview_offset=(self.preview_offset_x, self.preview_offset_y),
                pane_size=self._preview_pane_size(),
                input_to_output_scale=self.input_to_output_preview_scale,
            )
        if self.output_preview_image is not None:
            self.output_preview_image.close()
        self.output_preview_image = image
        if self.input_preview_image is not None:
            self.input_to_output_preview_scale = comparison_scale_for_images(
                self.input_preview_image.size,
                self.output_preview_image.size,
            )
        if view_state is None:
            self._fit_preview()
            return
        (
            self.preview_scale,
            self.preview_offset_x,
            self.preview_offset_y,
        ) = preview_geometry_from_view_state(
            view_state,
            pane_size=self._preview_pane_size(),
            input_to_output_scale=self.input_to_output_preview_scale,
        )
        self._render_preview()

    def _load_output_preview(self, path: Path) -> None:
        if self.input_preview_image is None and self.input_path.get():
            input_preview_path = (
                self.batch_preview_input_path
                if self.input_mode == "folder"
                else Path(self.input_path.get())
            )
            if input_preview_path is not None:
                self._load_input_preview(
                    input_preview_path,
                    schedule_output_preview=False,
                )
        with Image.open(path) as image:
            output_image = ImageOps.exif_transpose(image).convert("L").copy()
        self._set_output_preview_image(output_image)

    def _fit_preview(self) -> None:
        base_size = self._preview_base_size()
        if base_size is None:
            return
        base_width, base_height = base_size
        pane_width, pane_height = self._preview_pane_size()
        fit = min(pane_width / base_width, pane_height / base_height)
        self.preview_scale = min(1.0, max(0.01, fit))
        self.preview_offset_x = 0
        self.preview_offset_y = 0
        self._render_preview()

    def _zoom(self, factor: float) -> None:
        if self._preview_base_size() is None:
            return
        pane_width, pane_height = self._preview_pane_size()
        center_x = pane_width / 2.0
        center_y = pane_height / 2.0
        old_scale = self.preview_scale
        old_image_x = (center_x - self.preview_offset_x) / old_scale
        old_image_y = (center_y - self.preview_offset_y) / old_scale
        self.preview_scale = self._bounded_preview_scale(old_scale * factor)
        self.preview_offset_x = int(round(center_x - old_image_x * self.preview_scale))
        self.preview_offset_y = int(round(center_y - old_image_y * self.preview_scale))
        self._render_preview()

    def _bounded_preview_scale(self, scale: float) -> float:
        if self.input_preview_image is None:
            return scale
        input_to_output_scale = (
            self.input_to_output_preview_scale if self._is_comparison_preview() else 1.0
        )
        input_display_scale = scale * input_to_output_scale
        max_input_display_scale = min(
            PREVIEW_MAX_INPUT_DISPLAY_SCALE,
            PREVIEW_MAX_DIMENSION / max(self.input_preview_image.size),
        )
        bounded_input_display_scale = max(
            PREVIEW_MIN_INPUT_DISPLAY_SCALE,
            min(max_input_display_scale, input_display_scale),
        )
        return bounded_input_display_scale / input_to_output_scale

    def _render_preview(self) -> None:
        self.preview_canvas.delete("all")
        base_size = self._preview_base_size()
        if base_size is None:
            self.preview_canvas.create_text(
                max(1, self.preview_canvas.winfo_width()) // 2,
                max(1, self.preview_canvas.winfo_height()) // 2,
                fill="#dddddd",
                font=("Segoe UI", 13),
                text="入力画像および出力結果のプレビューがここに表示されます。",
            )
            return

        self.preview_scale = self._bounded_preview_scale(self.preview_scale)
        base_width, base_height = base_size
        content_width = max(1, int(round(base_width * self.preview_scale)))
        content_height = max(1, int(round(base_height * self.preview_scale)))
        pane_width, pane_height = self._preview_pane_size()
        self._clamp_preview_offset(content_width, content_height, pane_width, pane_height)
        self.preview_photos.clear()

        if self._is_comparison_preview():
            self._render_comparison_preview(content_width, content_height)
        else:
            assert self.input_preview_image is not None
            self._draw_preview_image(
                self.input_preview_image,
                pane_x=0,
                pane_y=0,
                pane_width=pane_width,
                pane_height=pane_height,
                source_to_base_scale=1.0,
            )

    def _render_comparison_preview(self, content_width: int, content_height: int) -> None:
        assert self.input_preview_image is not None
        assert self.output_preview_image is not None
        canvas_width = max(1, self.preview_canvas.winfo_width())
        canvas_height = max(1, self.preview_canvas.winfo_height())
        label_height = self._comparison_label_height()
        divider_x = max(1, canvas_width // 2)
        left_width = max(1, divider_x)
        right_x = min(canvas_width - 1, divider_x + 1)
        right_width = max(1, canvas_width - right_x)
        pane_height = max(1, canvas_height - label_height)

        self.preview_canvas.create_rectangle(
            0,
            0,
            left_width,
            canvas_height,
            fill="#202020",
            outline="",
        )
        self.preview_canvas.create_rectangle(
            right_x,
            0,
            canvas_width,
            canvas_height,
            fill="#202020",
            outline="",
        )
        self.preview_canvas.create_line(divider_x, 0, divider_x, canvas_height, fill="#777777")
        self.preview_canvas.create_text(
            max(4, left_width // 2),
            label_height // 2,
            fill="#dddddd",
            font=("Segoe UI", 12, "bold"),
            text="出力前",
        )
        self.preview_canvas.create_text(
            right_x + max(4, right_width // 2),
            label_height // 2,
            fill="#dddddd",
            font=("Segoe UI", 12, "bold"),
            text="出力後",
        )

        self._draw_preview_image(
            self.input_preview_image,
            pane_x=0,
            pane_y=label_height,
            pane_width=left_width,
            pane_height=pane_height,
            source_to_base_scale=self.input_to_output_preview_scale,
        )
        self._draw_preview_image(
            self.output_preview_image,
            pane_x=right_x,
            pane_y=label_height,
            pane_width=right_width,
            pane_height=pane_height,
            source_to_base_scale=1.0,
        )

    def _draw_preview_image(
        self,
        image: Image.Image,
        *,
        pane_x: int,
        pane_y: int,
        pane_width: int,
        pane_height: int,
        source_to_base_scale: float,
    ) -> None:
        display_scale = self.preview_scale * source_to_base_scale
        if display_scale <= 0.0:
            return
        pane_image = Image.new("L", (pane_width, pane_height), color=32)
        source_left = max(0.0, -self.preview_offset_x / display_scale)
        source_top = max(0.0, -self.preview_offset_y / display_scale)
        source_right = min(
            float(image.width),
            (pane_width - self.preview_offset_x) / display_scale,
        )
        source_bottom = min(
            float(image.height),
            (pane_height - self.preview_offset_y) / display_scale,
        )
        if source_right > source_left and source_bottom > source_top:
            crop_left = max(0, int(source_left))
            crop_top = max(0, int(source_top))
            crop_right = min(image.width, int(source_right + 0.9999))
            crop_bottom = min(image.height, int(source_bottom + 0.9999))
            crop = image.crop((crop_left, crop_top, crop_right, crop_bottom))
            width = max(1, int(round(crop.width * display_scale)))
            height = max(1, int(round(crop.height * display_scale)))
            resampling = (
                Image.Resampling.NEAREST
                if display_scale >= 1.0
                else Image.Resampling.LANCZOS
            )
            resized = crop.resize((width, height), resampling)
            paste_x = int(round(self.preview_offset_x + crop_left * display_scale))
            paste_y = int(round(self.preview_offset_y + crop_top * display_scale))
            pane_image.paste(resized, (paste_x, paste_y))
        photo = ImageTk.PhotoImage(pane_image)
        self.preview_photos.append(photo)
        self.preview_canvas.create_image(
            pane_x,
            pane_y,
            image=photo,
            anchor=tk.NW,
        )
        self.preview_canvas.create_rectangle(
            pane_x,
            pane_y,
            pane_x + pane_width,
            pane_y + pane_height,
            outline="#666666",
        )

    def _clamp_preview_offset(
        self,
        image_width: int,
        image_height: int,
        pane_width: int,
        pane_height: int,
    ) -> None:
        if image_width <= pane_width:
            self.preview_offset_x = (pane_width - image_width) // 2
        else:
            self.preview_offset_x = min(0, max(pane_width - image_width, self.preview_offset_x))

        if image_height <= pane_height:
            self.preview_offset_y = (pane_height - image_height) // 2
        else:
            self.preview_offset_y = min(0, max(pane_height - image_height, self.preview_offset_y))

    def _preview_base_size(self) -> tuple[int, int] | None:
        if self._is_comparison_preview():
            assert self.output_preview_image is not None
            return self.output_preview_image.size
        if self.input_preview_image is not None:
            return self.input_preview_image.size
        return None

    def _preview_pane_size(self) -> tuple[int, int]:
        canvas_width = max(1, self.preview_canvas.winfo_width())
        canvas_height = max(1, self.preview_canvas.winfo_height())
        if self._is_comparison_preview():
            return (
                max(1, canvas_width // 2),
                max(1, canvas_height - self._comparison_label_height()),
            )
        return canvas_width, canvas_height

    def _is_comparison_preview(self) -> bool:
        return self.input_preview_image is not None and self.output_preview_image is not None

    def _comparison_label_height(self) -> int:
        return 24

    def _start_pan(self, event: tk.Event[Any]) -> None:
        self._drag_origin = (event.x, event.y)
        self.preview_canvas.configure(cursor="fleur")

    def _drag_pan(self, event: tk.Event[Any]) -> None:
        if self._drag_origin is None:
            return
        last_x, last_y = self._drag_origin
        self.preview_offset_x += event.x - last_x
        self.preview_offset_y += event.y - last_y
        self._drag_origin = (event.x, event.y)
        self._render_preview()

    def _end_pan(self, _event: tk.Event[Any]) -> None:
        self._drag_origin = None
        self.preview_canvas.configure(cursor="hand2")


def main(argv: list[str] | None = None) -> int:
    """Run the GUI app."""

    parser = argparse.ArgumentParser(description="723モノクロ線画拡大ツール")
    parser.add_argument("--version", action="store_true", help="Print version and exit.")
    parser.add_argument("--check-config", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--check-ui", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--check-upscale",
        nargs=2,
        metavar=("INPUT", "OUTPUT"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--check-separate-psd",
        nargs=2,
        metavar=("INPUT", "OUTPUT"),
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    if args.version:
        print(f"723モノクロ線画拡大ツール　{__version__}")
        return 0
    if args.check_config:
        load_config(preset="line_only")
        return 0
    if args.check_ui:
        app = UpscalerGui()
        app.withdraw()
        app.update_idletasks()
        app.destroy()
        return 0
    if args.check_upscale:
        input_text, output_text = args.check_upscale
        config = load_export_config(
            scale=4,
            threshold=threshold_from_brightness(0),
            overwrite=True,
        )
        upscale_image(Path(input_text), Path(output_text), config, preset="line_only")
        return 0
    if args.check_separate_psd:
        input_text, output_text = args.check_separate_psd
        config = load_export_config(
            scale=2,
            threshold=threshold_from_brightness(0),
            overwrite=True,
            grayscale_mode="separate",
            separate_output_format="psd",
        )
        upscale_image(Path(input_text), Path(output_text), config, preset="line_only")
        return 0
    app = UpscalerGui()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
