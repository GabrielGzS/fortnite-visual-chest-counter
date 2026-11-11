"""Qualified French stacks retain their XP gate despite notification reflow."""

from collections import Counter

import numpy as np
import pytest

from fortnite_chest_counter import paths
from fortnite_chest_counter.detection.chest_types import FrenchQualifiedPopups


def notification(rare_x=110, sprite_x=162, quantity=2, heading=True):
    roi = np.zeros((202, 360, 3), dtype=np.uint8)
    folder = paths.TEMPLATES_DIR / "chest/fr"

    def paste(name, y, x):
        template = np.load(folder / f"stack_{name}.npy")
        h, w = template.shape
        roi[y:y + h, x:x + w] = (template[:, :, None] * 255).astype(np.uint8)

    if heading:
        paste("exp", 20, 165)
    paste("x2" if quantity == 2 else "rare", 75, rare_x)
    paste("sprite", 100, sprite_x)
    # Other notifications may occupy space between the heading and the chests.
    roi[45:48, 112:195] = 190
    return roi


@pytest.mark.parametrize("rare_x,sprite_x", [(110, 127), (130, 162), (95, 150)])
def test_reflowed_stack_needs_three_readings_and_never_recounts_static_lines(rare_x, sprite_x):
    reader = FrenchQualifiedPopups()
    roi = notification(rare_x, sprite_x)
    assert reader.observe(0, roi) == []
    assert reader.observe(.1, roi) == []
    added = reader.observe(.2, roi)
    assert Counter(row[3] for row in added) == {"rare": 2, "sprite": 1}
    assert reader.observe(.3, roi) == []
    assert reader.observe(.4, roi) == []


def test_missing_xp_heading_cannot_claim_even_exact_qualified_words():
    reader = FrenchQualifiedPopups()
    roi = notification(heading=False)
    assert all(reader.observe(i / 15, roi) == [] for i in range(8))
    assert not reader.rows and not reader.totals


def test_quantity_growth_counts_only_delta_and_a_flicker_cannot_readd_old_lines():
    reader = FrenchQualifiedPopups()
    one, two = notification(quantity=1), notification(quantity=2)
    first = sum((reader.observe(i / 15, one) for i in range(3)), [])
    assert Counter(row[3] for row in first) == {"rare": 1, "sprite": 1}
    growth = sum((reader.observe((i + 3) / 15, two) for i in range(3)), [])
    assert Counter(row[3] for row in growth) == {"rare": 1}
    # The same group briefly loses a row/quantity, then restores it.
    assert all(reader.observe((i + 6) / 15, one) == [] for i in range(3))
    assert all(reader.observe((i + 9) / 15, two) == [] for i in range(3))


def test_heading_and_unrelated_bright_rows_are_not_chests():
    roi = notification()
    roi[65:] = 0
    reader = FrenchQualifiedPopups()
    assert all(reader.observe(i / 15, roi) == [] for i in range(8))


def test_elapsed_frame_gap_does_not_recount_but_observed_fade_rearms_the_group():
    reader = FrenchQualifiedPopups()
    roi = notification()
    added = sum((reader.observe(t, roi) for t in (0, .1, .2)), [])
    assert Counter(row[3] for row in added) == {"rare": 2, "sprite": 1}
    assert all(reader.observe(t, roi) == [] for t in (.81, .91, 1.01))
    empty = np.zeros_like(roi)
    assert all(reader.observe(t, empty) == [] for t in (1.1, 1.4, 1.7))
    assert not reader.totals
    assert reader.observe(1.8, roi) == []
    assert reader.observe(1.9, roi) == []
    new = reader.observe(2.0, roi)
    assert Counter(row[3] for row in new) == {"rare": 2, "sprite": 1}


def test_subpixel_xp_heading_passes_robust_gate_only_after_three_readings():
    from scipy.ndimage import shift
    from fortnite_chest_counter.detection import visual as V

    reader = FrenchQualifiedPopups()
    roi = notification(heading=False)
    heading = shift(np.pad(reader.exp, 4), (.5, .5), order=1)
    h, w = heading.shape
    roi[15:15 + h, 160:160 + w] = (heading[:, :, None] * 255).astype(np.uint8)
    xp = roi[:74, 95:246].min(axis=2)
    raw = max(V.best_template_correlation((xp > level).astype(np.float32), reader.exp)[0]
              for level in (135, 155))
    robust = max(V.robust_correlation((xp > level).astype(np.float32), reader.exp_blurred, .6)
                 for level in (135, 155))
    assert raw < .60 < robust  # Raster resampling, not a weaker global confidence threshold.
    assert reader.observe(0, roi) == []
    assert reader.observe(.1, roi) == []
    assert Counter(row[3] for row in reader.observe(.2, roi)) == {"rare": 2, "sprite": 1}


@pytest.mark.parametrize("kind", ["rare", "sprite"])
def test_qualified_type_cannot_be_replaced_by_another_generic_stack_row(monkeypatch, kind):
    from fortnite_chest_counter import estimator, settings
    from types import SimpleNamespace

    before = {name: getattr(estimator, name) for name in (
        "CERTAIN_TIERS", "APPROX_COUNTS_MEDIUM_ALONE", "APPROX_MEDIUM_WITH_OBJECT_SUPPORT",
        "INTERACTION_ONLY_COUNTS_APPROX", "ENABLED_LANGUAGES", "SAMPLE_FPS", "PROMPT_EVERY_N_FRAMES")}
    try:
        estimator.configure({**settings.DEFAULTS["detector"], "languages": ["fr"]})
        est = estimator.ChestEstimator()
        est.trackers["normal"] = SimpleNamespace(active=True, run=1)
        monkeypatch.setattr(est, "_label", lambda _: ("chest", 1.0, {"votes": {"chest": 5}}))
        event = est._popup_event({"onset": 1.0, "score": .9, "template": "fr:COFFRE",
                                  "qualified_french": True, "french_type": kind,
                                  "scaled": {"blur": .9, "scale": 1.0, "confirmed": True},
                                  "slot": ("normal", 1, 0)})
        assert event["chest_type"] == kind
        assert event["certain_counted"] and event["approx_counted"]
        assert not est.open_labels
        monkeypatch.setattr(est, "_label", lambda _: ("unknown", 0.0, {}))
        est._refresh_labels(final=True)
        assert event["chest_type"] == kind
        assert est.take_type_updates() == []
    finally:
        for name, value in before.items():
            setattr(estimator, name, value)
