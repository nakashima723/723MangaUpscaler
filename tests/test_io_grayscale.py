from __future__ import annotations

import numpy as np
from PIL import Image

from mlu.grayscale import rgb_to_grayscale, rgba_to_grayscale_on_white
from mlu.io import load_image, save_grayscale_png


def test_rgb_to_grayscale_uses_srgb_coefficients() -> None:
    rgb = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255]]], dtype=np.uint8)

    gray = rgb_to_grayscale(rgb)

    assert gray.dtype == np.float32
    assert np.allclose(gray[0], [0.2126, 0.7152, 0.0722], atol=1e-4)


def test_rgba_is_composited_on_white() -> None:
    rgba = np.array([[[0, 0, 0, 0], [0, 0, 0, 255]]], dtype=np.uint8)

    gray = rgba_to_grayscale_on_white(rgba)

    assert np.allclose(gray[0], [1.0, 0.0])


def test_load_image_invert_and_save_8bit_png(tmp_path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    Image.fromarray(np.array([[0, 128, 255]], dtype=np.uint8)).save(input_path)

    image = load_image(input_path, invert=True)
    save_grayscale_png(output_path, image.array, overwrite=False)

    with Image.open(output_path) as saved:
        saved_array = np.asarray(saved)

    assert image.array.shape == (1, 3)
    assert saved.mode == "L"
    assert saved_array.tolist() == [[255, 127, 0]]
