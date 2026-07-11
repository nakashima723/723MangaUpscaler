from __future__ import annotations

import numpy as np
import pytest
from scipy import ndimage

from mlu.mask_extract import LineMaps
from mlu.tone_source import (
    detect_likely_pure_lineart,
    dilated_line_mask,
    distance_from_line,
    generate_tone_source,
    lift_line_regions,
)


def _line_maps(gray: np.ndarray, line_mask: np.ndarray) -> LineMaps:
    darkness = (np.float32(1.0) - gray).astype(np.float32, copy=False)
    line_soft = np.where(line_mask, np.float32(1.0), np.float32(0.0)).astype(np.float32)
    return LineMaps(
        line_prob=line_soft.copy(),
        line_mask=line_mask.astype(np.bool_),
        line_soft=line_soft,
        darkness=darkness,
    )


def _config(**tone_source: object) -> dict:
    return {
        "tone_source": {
            "mode": "lift_lines",
            "dilate_radius": 1.2,
            "lift_strength": 0.85,
            "background_blur_radius": 1.5,
            "protect_midtones": True,
            **tone_source,
        }
    }


def test_white_canvas_and_passthrough_modes() -> None:
    gray = np.array([[0.0, 0.5, 1.0]], dtype=np.float32)
    line_mask = np.array([[True, False, False]], dtype=np.bool_)
    maps = _line_maps(gray, line_mask)

    white = generate_tone_source(gray, maps, _config(mode="white_canvas"))
    passthrough = generate_tone_source(gray, maps, _config(mode="passthrough"))

    assert np.allclose(white.image, 1.0)
    assert np.array_equal(passthrough.image, gray)
    assert white.line_lift_ratio == pytest.approx(1.0)


def test_lift_lines_lightens_black_line_while_protecting_remote_midtone() -> None:
    gray = np.ones((9, 11), dtype=np.float32)
    gray[:, 0] = 0.50
    gray[:, 5] = 0.0
    line_mask = np.zeros_like(gray, dtype=np.bool_)
    line_mask[:, 5] = True
    maps = _line_maps(gray, line_mask)

    result = generate_tone_source(gray, maps, _config())

    assert float(result.image[:, 5].mean()) > 0.60
    assert float(result.image[:, 0].mean()) < 0.65
    assert result.line_lift_ratio > 0.60


def test_lift_strength_and_dilate_radius_control_lifting() -> None:
    gray = np.ones((7, 9), dtype=np.float32)
    gray[:, 4] = 0.0
    gray[:, 5] = 0.40
    line_mask = np.zeros_like(gray, dtype=np.bool_)
    line_mask[:, 4] = True
    maps = _line_maps(gray, line_mask)

    weak = lift_line_regions(
        gray,
        maps,
        dilate_radius=1.5,
        lift_strength=0.25,
        background_blur_radius=0.0,
        protect_midtones=False,
    )
    strong = lift_line_regions(
        gray,
        maps,
        dilate_radius=1.5,
        lift_strength=1.0,
        background_blur_radius=0.0,
        protect_midtones=False,
    )
    no_dilate = lift_line_regions(
        gray,
        maps,
        dilate_radius=0.0,
        lift_strength=1.0,
        background_blur_radius=0.0,
        protect_midtones=False,
    )

    assert float(strong[:, 4].mean()) > float(weak[:, 4].mean())
    assert float(strong[:, 5].mean()) > float(no_dilate[:, 5].mean())


def test_pure_lineart_detection_uses_background_midtone_ratio() -> None:
    lineart = np.ones((8, 8), dtype=np.float32)
    lineart[4, :] = 0.0
    line_mask = lineart == 0.0

    shaded = lineart.copy()
    shaded[:3, :] = 0.50

    pure, pure_ratio = detect_likely_pure_lineart(lineart, line_mask)
    not_pure, shaded_ratio = detect_likely_pure_lineart(shaded, line_mask)

    assert pure is True
    assert pure_ratio == pytest.approx(0.0)
    assert not_pure is False
    assert shaded_ratio > 0.02


def test_dilated_line_mask_uses_euclidean_radius() -> None:
    line_mask = np.zeros((5, 5), dtype=np.bool_)
    line_mask[2, 2] = True

    dilated = dilated_line_mask(line_mask, radius=1.1)

    assert dilated[2, 2]
    assert dilated[2, 3]
    assert not dilated[0, 0]


def test_distance_from_line_matches_scipy_for_random_and_border_lines() -> None:
    rng = np.random.default_rng(723)
    line_mask = rng.random((41, 53)) > 0.91
    line_mask[0, 4:19] = True
    line_mask[-1, 30:47] = True

    actual = distance_from_line(line_mask)
    expected = ndimage.distance_transform_edt(~line_mask).astype(np.float32)

    assert np.array_equal(actual, expected)


def test_invalid_tone_source_parameters_are_rejected() -> None:
    gray = np.ones((2, 2), dtype=np.float32)
    maps = _line_maps(gray, np.zeros_like(gray, dtype=np.bool_))

    with pytest.raises(ValueError, match="dilate_radius"):
        lift_line_regions(
            gray,
            maps,
            dilate_radius=-1.0,
            lift_strength=0.5,
            background_blur_radius=1.0,
            protect_midtones=True,
        )

    with pytest.raises(ValueError, match="lift_strength"):
        lift_line_regions(
            gray,
            maps,
            dilate_radius=1.0,
            lift_strength=1.5,
            background_blur_radius=1.0,
            protect_midtones=True,
        )

    with pytest.raises(ValueError, match="tone_source.mode"):
        generate_tone_source(gray, maps, _config(mode="unknown"))
