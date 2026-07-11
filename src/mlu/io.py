"""Image input and output helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from mlu.grayscale import (
    FloatImage,
    ensure_float_gray,
    rgb_to_grayscale,
    rgba_to_grayscale_on_white,
)


@dataclass(frozen=True)
class ImageData:
    """Loaded grayscale image data.

    The array is float32 [0.0, 1.0], where 0.0 is black and 1.0 is white.
    """

    path: Path | None
    array: FloatImage
    alpha: FloatImage | None
    bit_depth: int
    color_space_hint: str
    metadata: dict[str, Any] = field(default_factory=dict)


def load_image(path: str | Path, *, invert: bool = False) -> ImageData:
    """Load an image as float32 grayscale [0.0, 1.0], 0.0 black and 1.0 white."""

    image_path = Path(path)
    try:
        with Image.open(image_path) as image:
            transposed = ImageOps.exif_transpose(image)
            mode = transposed.mode
            bit_depth = _bit_depth_for_mode(mode)
            gray = _image_to_gray(transposed, invert=invert)
            metadata = {
                "format": image.format,
                "mode": mode,
                "size": transposed.size,
            }
    except OSError as exc:
        raise ValueError(f"Could not read image: {image_path}") from exc

    return ImageData(
        path=image_path,
        array=gray,
        alpha=None,
        bit_depth=bit_depth,
        color_space_hint="srgb",
        metadata=metadata,
    )


def save_grayscale_png(
    path: str | Path,
    array: FloatImage,
    *,
    bit_depth: int = 8,
    overwrite: bool = False,
) -> None:
    """Save float32 grayscale [0.0, 1.0], 0.0 black and 1.0 white, as PNG."""

    output_path = Path(path)
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    clipped = np.clip(array, 0.0, 1.0)
    if bit_depth == 8:
        data = np.rint(clipped * np.float32(255.0)).astype(np.uint8)
        image = Image.fromarray(data)
    elif bit_depth == 16:
        data = np.rint(clipped * np.float32(65535.0)).astype(np.uint16)
        image = Image.fromarray(data)
    else:
        raise ValueError("bit_depth must be 8 or 16.")

    image.save(output_path, format="PNG")


def _image_to_gray(image: Image.Image, *, invert: bool) -> FloatImage:
    if image.mode in {"1", "L", "I;16", "I"}:
        return ensure_float_gray(np.asarray(image), invert=invert)
    if image.mode == "LA":
        rgba = image.convert("RGBA")
        return rgba_to_grayscale_on_white(np.asarray(rgba), invert=invert)
    if image.mode == "RGBA":
        return rgba_to_grayscale_on_white(np.asarray(image), invert=invert)
    if image.mode in {"RGB", "P", "CMYK"}:
        rgb = image.convert("RGB")
        return rgb_to_grayscale(np.asarray(rgb), invert=invert)

    rgb = image.convert("RGB")
    return rgb_to_grayscale(np.asarray(rgb), invert=invert)


def _bit_depth_for_mode(mode: str) -> int:
    if mode == "I;16":
        return 16
    return 8
