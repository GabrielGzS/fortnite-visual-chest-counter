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


@pytest.mark.parametrize(('scores', 'expected_type'), [((.86, .76), CT.UNKNOWN),
                                                      ((.86, .76, .74), CT.NORMAL),
                                                      ((.76, .74, .86), CT.NORMAL)])
def test_aligned_blurred_frames_label_an_estimate_without_a_settled_tracker(monkeypatch, scores, expected_type):
    est = E.ChestEstimator(stacked=False)
    frame = picture(est)
    roi = frame[V.ROI_Y:V.ROI_Y + V.ROI_H, V.ROI_X:V.ROI_X + V.ROI_W]
    mask = V.lavender_mask(roi)
    height, width = est.french_template.shape

    readings = iter(scores)

    def blurred_match(rgb, lavender):
        est.french_plane = (1.0, rgb, lavender)
        return next(readings), 80 + height // 2, 120 + width // 2, 1.0, 'fr:COFFRE', False

    monkeypatch.setattr(est, '_scaled_best', blurred_match)
    monkeypatch.setattr(est, '_recover_french_line', lambda *args, **kwargs: None)
    for index in range(len(scores)):
        est._scaled_popup(index / 15, roi, mask, exact_fired=False)
    counted = [event for event in est.flush() if event['approx_counted']]
    assert len(counted) == 1
    assert counted[0]['chest_type'] == expected_type
    assert not counted[0]['certain_counted']


@pytest.mark.parametrize('aligned', [False, True])
def test_faint_french_pair_requires_three_aligned_xp_reads(monkeypatch, aligned):
    est = E.ChestEstimator(stacked=False)
    frame = picture(est)
    roi = frame[V.ROI_Y:V.ROI_Y + V.ROI_H, V.ROI_X:V.ROI_X + V.ROI_W]
    mask = V.lavender_mask(roi)
    height, width = est.french_template.shape
    cy, cx = 80 + height // 2, 120 + width // 2
    xp = (.55, 80 - 46, 120 - 108 - est.french_xp_templates[CT.NORMAL][1] + (0 if aligned else 12))

    def match(rgb, lavender):
        est.french_plane = (1.0, rgb, lavender)
        return .77, cy, cx, 1.0, 'fr:COFFRE', False

    def faint(t, rgb, lavender, score, y, x):
        return est._recover_faint_french(t, lavender, score, y, x, 1.0, xp)

    monkeypatch.setattr(est, '_scaled_best', match)
    monkeypatch.setattr(est, '_recover_french_line', faint)
    for i in range(2):
        est._scaled_popup(i / 15, roi, mask, exact_fired=False)
    assert not est.pending_scaled
    est._scaled_popup(2 / 15, roi, mask, exact_fired=False)
    counted = [event for event in est.flush() if event['approx_counted']]
    assert len(counted) == int(aligned)
    if aligned:
        assert counted[0]['chest_type'] == CT.NORMAL
        assert not counted[0]['certain_counted']

def test_saturated_background_requires_three_aligned_header_and_word_reads():
    est = E.ChestEstimator()
    roi = np.full((V.ROI_H, V.ROI_W, 3), (190, 120, 240), dtype=np.uint8)
    xp, dx = est.french_xp_templates[CT.NORMAL]
    y, x = 55, 160
    h, w = xp.shape
    roi[y:y + h, x:x + w][xp > 0.5] = (230, 200, 250)
    assert est._recover_saturated_french(0, roi, V.lavender_mask(roi)) is None
    h, w = est.french_template.shape
    roi[y + 14:y + 14 + h, x + dx:x + dx + w][est.french_template > 0.5] = (230, 200, 250)
    mask = V.lavender_mask(roi)
    assert est._recover_saturated_french(.1, roi, mask) is None
    assert est._recover_saturated_french(.2, roi, mask) is None
    assert est._recover_saturated_french(.3, roi, mask)[2:] == (CT.NORMAL, False)

def test_bright_french_header_confirms_only_an_aligned_bare_chest():
    est = E.ChestEstimator()
    roi = np.zeros((182, 324, 3), dtype=np.uint8)
    xp, dx = est.french_xp_templates[CT.NORMAL]
    y, x = 47, 138
    header = xp[:14]
    h, w = header.shape
    roi[y:y + h, x:x + w][header > 0.5] = (230, 200, 250)
    assert est._recover_bright_french(0, roi) is None
    h, w = est.french_template.shape
    roi[y + 14:y + 14 + h, x + dx:x + dx + w][est.french_template > 0.5] = (230, 200, 250)
    assert est._recover_bright_french(.1, roi) is None
    assert est._recover_bright_french(.2, roi) is None
    assert est._recover_bright_french(.3, roi)[2:] == (CT.NORMAL, True)
    roi[y + 12:y + 14 + h, x + dx + w + 3:x + dx + w + 10] = (230, 200, 250)
    assert est._recover_bright_french(.4, roi) is None

def test_bright_stacked_word_needs_its_exp_header():
    est = E.ChestEstimator()
    roi = np.zeros((182, 324, 3), dtype=np.uint8)
    y, x = 70, 116
    word = est.french_template
    h, w = word.shape
    roi[y:y + h, x:x + w][word > 0.5] = (230, 200, 250)
    assert all(est._recover_bright_exp_line(t, roi) is None for t in (0, .1, .2))
    exp = est.french_xp_templates[CT.NORMAL][0][:14, :22]
    h, w = exp.shape
    roi[y - 29:y - 29 + h, x + 25:x + 25 + w][exp > 0.5] = (230, 200, 250)
    assert est._recover_bright_exp_line(.3, roi) is None
    assert est._recover_bright_exp_line(.4, roi) is None
    assert est._recover_bright_exp_line(.5, roi)[2:] == (CT.NORMAL, False)

def test_bright_exp_fallback_waits_for_existing_popup_and_counts_only_unmatched(monkeypatch):
    est = E.ChestEstimator()
    calls = []

    def popup(candidate):
        calls.append(candidate)
        return {"time": candidate["onset"], "approx_counted": True}

    monkeypatch.setattr(est, "_popup_event", popup)
    roi = np.zeros((182, 324, 3), dtype=np.uint8)
    line = (70, 116, CT.NORMAL, False)
    est._queue_french_exp(2.0, line, .7, roi)
    est._queue_french_exp(2.2, line, .7, roi)
    assert est._finish(3.0, False) == []
    est.pending_popups.append({"onset": 1.9, "until": 4.0, "template": "fr:COFFRE", "y": 78, "x": 129})
    assert est._finish(5.3, False) == [{"time": 1.9, "approx_counted": True}]
    assert len(calls) == 1 and not calls[0].get("bright_exp")
    assert calls[0]["french_type"] == CT.NORMAL
    est._queue_french_exp(8.0, line, .7, roi)
    assert est._finish(9.0, False) == []
    assert est._finish(11.3, False) == [{"time": 8.0, "approx_counted": True}]
    assert calls[-1]["bright_exp"]
