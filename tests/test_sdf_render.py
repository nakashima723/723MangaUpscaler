from __future__ import annotations

import numpy as np
import pytest
from scipy import ndimage

from mlu.config import load_config
from mlu.sdf_render import (
    render_line_alpha,
    resize_float_image,
    sdf_preview,
    signed_distance_field,
    smoothstep,
)


def _config(
    *,
    scale: int = 4,
    interpolation: str = "nearest",
    width_bias_source_px: float = 0.0,
    aa_radius_hr_px: float = 0.75,
    distance_source: str = "binary_mask",
    soft_sdf_threshold: float = 0.30,
    soft_alpha_mode: str = "none",
    soft_gain: float = 0.0,
) -> dict:
    return load_config(
        cli_overrides={
            "pipeline": {"scale": scale},
            "sdf": {
                "interpolation": interpolation,
                "distance_source": distance_source,
                "soft_sdf_threshold": soft_sdf_threshold,
                "width_bias_source_px": width_bias_source_px,
                "aa_radius_hr_px": aa_radius_hr_px,
                "soft_alpha_mode": soft_alpha_mode,
                "soft_gain": soft_gain,
            },
        }
    )


def test_signed_distance_field_uses_positive_inside_negative_outside() -> None:
    mask = np.zeros((5, 5), dtype=np.bool_)
    mask[2, 2] = True

    sdf = signed_distance_field(mask)

    assert sdf[2, 2] > 0.0
    assert sdf[0, 0] < 0.0


def test_parallel_signed_distance_field_matches_sequential_scipy_reference() -> None:
    rng = np.random.default_rng(723)
    mask = rng.random((73, 91)) > 0.68
    expected = (
        ndimage.distance_transform_edt(mask)
        - ndimage.distance_transform_edt(~mask)
    ).astype(np.float32)

    actual = signed_distance_field(mask)

    assert np.array_equal(actual, expected)


def test_render_line_alpha_has_scaled_size_and_scale_corrected_distance() -> None:
    mask = np.zeros((3, 3), dtype=np.bool_)
    mask[1, 1] = True

    result = render_line_alpha(mask, _config(scale=3, interpolation="nearest"))

    assert result.line_alpha_hr.shape == (9, 9)
    assert result.sdf_hr.shape == (9, 9)
    assert result.sdf_hr[4, 4] == pytest.approx(3.0)
    assert result.sdf_hr[0, 0] < 0.0
    assert result.line_alpha_hr[4, 4] == pytest.approx(1.0)
    assert result.line_alpha_hr[0, 0] == pytest.approx(0.0)


def test_width_bias_changes_alpha_area_monotonically() -> None:
    mask = np.zeros((5, 5), dtype=np.bool_)
    mask[:, 2] = True

    thin = render_line_alpha(mask, _config(width_bias_source_px=-1.0)).line_alpha_hr
    normal = render_line_alpha(mask, _config(width_bias_source_px=0.0)).line_alpha_hr
    thick = render_line_alpha(mask, _config(width_bias_source_px=1.0)).line_alpha_hr

    assert float(thin.sum()) < float(normal.sum()) < float(thick.sum())


def test_aa_radius_changes_fractional_edge_amount() -> None:
    mask = np.zeros((5, 5), dtype=np.bool_)
    mask[:, 2] = True

    sharp = render_line_alpha(mask, _config(aa_radius_hr_px=0.5)).line_alpha_hr
    soft = render_line_alpha(mask, _config(aa_radius_hr_px=5.0)).line_alpha_hr

    sharp_fractional = np.count_nonzero((sharp > 0.0) & (sharp < 1.0))
    soft_fractional = np.count_nonzero((soft > 0.0) & (soft < 1.0))
    assert sharp_fractional < soft_fractional


def test_diagonal_line_alpha_contains_fractional_antialiasing() -> None:
    mask = np.eye(8, dtype=np.bool_)

    alpha = render_line_alpha(mask, _config(scale=4, interpolation="lanczos")).line_alpha_hr

    assert alpha.shape == (32, 32)
    assert np.any((alpha > 0.0) & (alpha < 1.0))


def test_line_soft_max_mode_can_raise_alpha() -> None:
    mask = np.zeros((3, 3), dtype=np.bool_)
    line_soft = np.zeros((3, 3), dtype=np.float32)
    line_soft[0, 0] = 0.8

    none = render_line_alpha(mask, _config(scale=2), line_soft=line_soft)
    with_soft = render_line_alpha(
        mask,
        _config(scale=2, soft_alpha_mode="max", soft_gain=0.5),
        line_soft=line_soft,
    )

    assert none.line_soft_hr is None
    assert with_soft.line_soft_hr is not None
    assert float(with_soft.line_alpha_hr.max()) > float(none.line_alpha_hr.max())


def test_line_soft_blend_mode_mixes_source_coverage_into_alpha() -> None:
    mask = np.zeros((3, 3), dtype=np.bool_)
    mask[1, 1] = True
    line_soft = np.zeros((3, 3), dtype=np.float32)
    line_soft[0, 0] = 1.0

    hard = render_line_alpha(mask, _config(scale=2, soft_alpha_mode="none"))
    blend = render_line_alpha(
        mask,
        _config(scale=2, soft_alpha_mode="blend", soft_gain=0.75),
        line_soft=line_soft,
    )

    assert blend.line_soft_hr is not None
    assert float(blend.line_alpha_hr[0, 0]) > float(hard.line_alpha_hr[0, 0])
    assert float(blend.line_alpha_hr[2, 2]) < float(hard.line_alpha_hr[2, 2])


def test_soft_mask_hr_distance_source_requires_line_soft() -> None:
    mask = np.zeros((3, 3), dtype=np.bool_)
    mask[1, 1] = True

    with pytest.raises(ValueError, match="line_soft"):
        render_line_alpha(mask, _config(scale=2, distance_source="soft_mask_hr"))


def test_soft_mask_hr_distance_source_uses_soft_support_not_binary_mask() -> None:
    mask = np.zeros((3, 3), dtype=np.bool_)
    mask[1, 1] = True
    line_soft = np.zeros((3, 3), dtype=np.float32)

    result = render_line_alpha(
        mask,
        _config(scale=2, distance_source="soft_mask_hr"),
        line_soft=line_soft,
    )

    assert result.line_soft_hr is not None
    assert not result.line_alpha_hr.any()


def test_soft_mask_hr_distance_field_is_created_at_high_resolution() -> None:
    mask = np.zeros((3, 3), dtype=np.bool_)
    mask[1, 1] = True
    line_soft = np.zeros((3, 3), dtype=np.float32)
    line_soft[1, 1] = 1.0

    binary = render_line_alpha(mask, _config(scale=3, interpolation="nearest"))
    soft_hr = render_line_alpha(
        mask,
        _config(scale=3, interpolation="nearest", distance_source="soft_mask_hr"),
        line_soft=line_soft,
    )

    assert soft_hr.line_alpha_hr.shape == (9, 9)
    assert soft_hr.sdf_hr[4, 4] < binary.sdf_hr[4, 4]
    assert soft_hr.sdf_hr[4, 4] > 0.0


@pytest.mark.parametrize("scale", [2, 3, 4, 6, 8])
def test_final_only_fast_path_matches_full_sdf_alpha_exactly(scale: int) -> None:
    rng = np.random.default_rng(723 + scale)
    mask = rng.random((13, 17)) > 0.75
    line_soft = rng.random(mask.shape, dtype=np.float32)
    config = _config(
        scale=scale,
        interpolation="lanczos",
        distance_source="soft_mask_hr",
        soft_sdf_threshold=0.22,
        aa_radius_hr_px=0.75,
    )

    full = render_line_alpha(mask, config, line_soft=line_soft)
    fast = render_line_alpha(
        mask,
        config,
        line_soft=line_soft,
        retain_diagnostics=False,
    )

    assert np.array_equal(fast.line_alpha_hr, full.line_alpha_hr)
    assert full.sdf is not None
    assert full.sdf_hr is not None
    assert fast.sdf is None
    assert fast.sdf_hr is None
    assert fast.renderer_metadata == {
        "renderer": "sdf",
        "alpha_fast_path": True,
        "high_resolution_edt_count": 0,
        "diagnostics_retained": False,
    }


@pytest.mark.parametrize(
    ("width_bias_source_px", "expected_fast_path"),
    [
        (-0.0626, False),
        (-0.0625, True),
        (0.0625, True),
        (0.0626, False),
    ],
)
def test_final_only_fast_path_respects_exact_width_bias_boundary(
    width_bias_source_px: float,
    expected_fast_path: bool,
) -> None:
    mask = np.zeros((7, 9), dtype=np.bool_)
    mask[2:5, 3:6] = True
    line_soft = mask.astype(np.float32)
    config = _config(
        scale=4,
        interpolation="nearest",
        distance_source="soft_mask_hr",
        width_bias_source_px=width_bias_source_px,
        aa_radius_hr_px=0.75,
    )

    full = render_line_alpha(mask, config, line_soft=line_soft)
    final_only = render_line_alpha(
        mask,
        config,
        line_soft=line_soft,
        retain_diagnostics=False,
    )

    assert np.array_equal(final_only.line_alpha_hr, full.line_alpha_hr)
    assert final_only.renderer_metadata is not None
    assert final_only.renderer_metadata["alpha_fast_path"] is expected_fast_path


@pytest.mark.parametrize(
    "config",
    [
        _config(scale=4, distance_source="binary_mask"),
        _config(
            scale=4,
            distance_source="soft_mask_hr",
            aa_radius_hr_px=1.01,
        ),
    ],
)
def test_final_only_path_falls_back_to_sdf_outside_exact_conditions(config: dict) -> None:
    mask = np.zeros((7, 9), dtype=np.bool_)
    mask[2:5, 3:6] = True
    line_soft = mask.astype(np.float32)

    full = render_line_alpha(mask, config, line_soft=line_soft)
    final_only = render_line_alpha(
        mask,
        config,
        line_soft=line_soft,
        retain_diagnostics=False,
    )

    assert np.array_equal(final_only.line_alpha_hr, full.line_alpha_hr)
    assert final_only.renderer_metadata is not None
    assert final_only.renderer_metadata["alpha_fast_path"] is False


def test_final_only_one_sided_edt_matches_full_sdf_with_soft_max_mode() -> None:
    mask = np.zeros((7, 9), dtype=np.bool_)
    mask[2:5, 3:6] = True
    line_soft = np.linspace(0.0, 1.0, mask.size, dtype=np.float32).reshape(mask.shape)
    config = _config(
        scale=4,
        distance_source="soft_mask_hr",
        width_bias_source_px=-0.25,
        aa_radius_hr_px=1.0,
        soft_alpha_mode="max",
        soft_gain=0.5,
    )

    full = render_line_alpha(mask, config, line_soft=line_soft)
    final_only = render_line_alpha(
        mask,
        config,
        line_soft=line_soft,
        retain_diagnostics=False,
    )

    assert np.array_equal(final_only.line_alpha_hr, full.line_alpha_hr)
    assert final_only.renderer_metadata is not None
    assert final_only.renderer_metadata["alpha_fast_path"] is False
    assert final_only.renderer_metadata["high_resolution_edt_count"] == 1


def test_long_shallow_line_uses_soft_coverage_at_stair_transitions() -> None:
    width = 32
    height = 10
    mask = np.zeros((height, width), dtype=np.bool_)
    line_soft = np.zeros((height, width), dtype=np.float32)

    for x in range(width):
        center_y = 3.0 + x * 0.08
        for y in range(height):
            coverage = max(0.0, 1.0 - abs(y - center_y) / 1.25)
            line_soft[y, x] = coverage
        mask[int(round(center_y)), x] = True

    hard = render_line_alpha(mask, _config(scale=4, interpolation="lanczos"))
    blend = render_line_alpha(
        mask,
        _config(scale=4, interpolation="lanczos", soft_alpha_mode="blend", soft_gain=0.85),
        line_soft=line_soft,
    )

    hard_fractional = np.count_nonzero((hard.line_alpha_hr > 0.05) & (hard.line_alpha_hr < 0.95))
    blend_fractional = np.count_nonzero(
        (blend.line_alpha_hr > 0.05) & (blend.line_alpha_hr < 0.95)
    )
    assert blend_fractional > hard_fractional
    assert blend.line_soft_hr is not None


def test_empty_and_full_masks_are_stable() -> None:
    empty = np.zeros((2, 2), dtype=np.bool_)
    full = np.ones((2, 2), dtype=np.bool_)

    empty_alpha = render_line_alpha(empty, _config(scale=2)).line_alpha_hr
    full_alpha = render_line_alpha(full, _config(scale=2)).line_alpha_hr

    assert not empty_alpha.any()
    assert np.allclose(full_alpha, 1.0)


def test_sdf_preview_maps_to_unit_range() -> None:
    sdf = np.array([[-8.0, 0.0, 8.0]], dtype=np.float32)

    preview = sdf_preview(sdf, radius_px=8.0)

    assert np.allclose(preview, [[0.0, 0.5, 1.0]])


def test_smoothstep_maps_edges() -> None:
    values = np.array([[-1.0, 0.0, 1.0]], dtype=np.float32)

    stepped = smoothstep(-1.0, 1.0, values)

    assert np.allclose(stepped, [[0.0, 0.5, 1.0]])


def test_invalid_aa_radius_is_rejected() -> None:
    mask = np.zeros((2, 2), dtype=np.bool_)

    with pytest.raises(ValueError, match="aa_radius"):
        render_line_alpha(mask, _config(aa_radius_hr_px=0.0))


def test_resize_rejects_invalid_scale() -> None:
    image = np.ones((2, 2), dtype=np.float32)

    with pytest.raises(ValueError, match="scale"):
        resize_float_image(image, scale=5)
