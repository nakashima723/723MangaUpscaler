from __future__ import annotations

import numpy as np

from mlu.mask_extract import compute_line_probability, compute_line_soft


def test_darkness_coverage_does_not_boost_shallow_antialias_variation() -> None:
    x = np.arange(160, dtype=np.float32)
    shallow_line_darkness = (0.30 + 0.055 * np.sin(x / 9.0)).reshape(1, -1).astype(np.float32)
    line_prob = compute_line_probability(shallow_line_darkness, weak=0.20, strong=0.48)
    line_mask = shallow_line_darkness >= np.float32(0.48)

    darkness_soft = compute_line_soft(
        shallow_line_darkness,
        line_prob,
        line_mask,
        weak=0.20,
        coverage_mode="darkness",
    )
    legacy_soft = compute_line_soft(
        shallow_line_darkness,
        line_prob,
        line_mask,
        weak=0.20,
        coverage_mode="max_probability",
    )

    darkness_span = float(darkness_soft.max() - darkness_soft.min())
    legacy_span = float(legacy_soft.max() - legacy_soft.min())
    assert legacy_span > darkness_span * 2.0
    np.testing.assert_allclose(darkness_soft, shallow_line_darkness)
