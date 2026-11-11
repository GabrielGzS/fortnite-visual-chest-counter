"""Enlarged French HUDs use the same line tracking and type votes as native HUDs."""

import numpy as np
import pytest

from fortnite_chest_counter import estimator as E, settings
from fortnite_chest_counter.detection import chest_types as CT, visual as V


@pytest.fixture(autouse=True)
def french_detector():
    E.configure(dict(settings.DEFAULTS["detector"], languages=["fr"]))
    yield
    E.configure(settings.DEFAULTS["detector"])


def picture(est, scale=1.0, *, dx=0, fade=1.0, qualifier=False):
    roi = np.zeros((V.ROI_H, V.ROI_W, 3), np.uint8)
    th, tw = est.french_template.shape
    roi[80:80 + th, 120 + dx:120 + dx + tw][est.french_template > 0] = np.array([232, 196, 250]) * fade
    if qualifier:
        # Unreadable text after COFFRE must not become Normal just because the
        # word itself is recognized. This is deliberately not a rare template.
        roi[80:80 + th, 120 + dx + tw + 3:120 + dx + tw + 12] = (232, 196, 250)
    if scale != 1:
        roi = V.resize_box(roi, round(V.ROI_W / scale), round(V.ROI_H / scale))[:V.ROI_H, :V.ROI_W]
    frame = np.zeros((V.NORMALIZED_HEIGHT, V.NORMALIZED_WIDTH, 3), np.uint8)
    frame[V.ROI_Y:V.ROI_Y + V.ROI_H, V.ROI_X:V.ROI_X + V.ROI_W] = roi
    return frame


def finish(est, observations):
    events = []
    for t, frame in observations:
        events.extend(est.process_frame(t, frame))
    return [e for e in events + est.flush() if e["approx_counted"]]


@pytest.mark.parametrize("scale", [1.0, .9, .85])
@pytest.mark.parametrize("fps", [7.5, 15])
def test_three_separate_normal_chests_are_typed_once_each(scale, fps):
    est = E.ChestEstimator()
    chest = picture(est, scale)
    blank = np.zeros_like(chest)
    observations = [(i / fps, chest if int(i / fps) % 3 < 2 else blank)
                    for i in range(round(9 * fps))]
    counted = finish(est, observations)
    assert len(counted) == 3
    assert all(e["chest_type"] == CT.NORMAL for e in counted)
    assert all(e["certain_counted"] for e in counted)


def test_static_enlarged_popup_reflows_and_fades_without_another_opening():
    est = E.ChestEstimator()
    observations = [(i / 15, picture(est, .9, dx=(i // 12) % 3,
                                   fade=1 if i < 36 else .9)) for i in range(48)]
    counted = finish(est, observations)
    assert len(counted) == 1 and counted[0]["chest_type"] == CT.NORMAL


def test_unreadable_scaled_qualifier_cannot_be_called_normal():
    est = E.ChestEstimator()
    counted = finish(est, [(i / 15, picture(est, .9, qualifier=True)) for i in range(30)])
    assert len(counted) == 1
    assert counted[0]["chest_type"] == "unknown"


def test_french_recovery_votes_cannot_mix_glyph_scales():
    est = E.ChestEstimator()
    frame = picture(est)
    roi = frame[V.ROI_Y:V.ROI_Y + V.ROI_H, V.ROI_X:V.ROI_X + V.ROI_W]
    mask = V.lavender_mask(roi)
    th, tw = est.french_template.shape
    readings = [est._recover_french_line(i / 15, roi, mask, .95,
                                        80 + th // 2, 120 + tw // 2, scale=scale)
                for i, scale in enumerate((.9, .85, 1.0))]
    assert readings == [None, None, None]
