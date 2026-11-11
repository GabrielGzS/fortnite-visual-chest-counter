"""Diagnostic review retains the live clock, independently of encoded video FPS."""

import json

import pytest

from fortnite_chest_counter import estimator, review


def test_replay_uses_original_frame_gaps_and_maps_events_back_to_video(tmp_path, monkeypatch):
    (tmp_path / "video").mkdir()
    (tmp_path / "capture.json").write_text(json.dumps({"fps": 10}), encoding="utf-8")
    (tmp_path / "video" / "clips.json").write_text(json.dumps([
        {"file": "video/first.mkv", "start": 0, "end": .3},
        {"file": "video/second.mkv", "start": .3, "end": .5},
    ]), encoding="utf-8")
    (tmp_path / "timeline.csv").write_text(
        "frame,live_t\n0,100.0\n1,100.1\n2,100.5\n3,110.0\n4,110.8\n", encoding="utf-8")
    instances, closed, progress = [], [], []

    class TemporalEstimator:
        def __init__(self):
            self.times = []
            instances.append(self)

        def process_frame(self, t, frame):
            self.times.append(t)
            # A real temporal gate distinguishes the irregular live clock from 10 FPS playback.
            if len(self.times) > 1 and t - self.times[-2] >= .3:
                return [{"time": t, "approx_counted": True, "_snapshot": frame}]
            return []

        def flush(self):
            return [{"time": self.times[-1] / 2, "source": "flush"}]

    def recorded_frames(path, fps):
        assert fps == 10
        try:
            for i in range(3 if path.name == "first.mkv" else 2):
                yield i / fps, object()
        finally:
            closed.append(path.name)

    monkeypatch.setattr(estimator, "configure", lambda cfg: None)
    monkeypatch.setattr(estimator, "ChestEstimator", TemporalEstimator)
    monkeypatch.setattr(review, "frames", recorded_frames)
    events = review.replay(tmp_path, {}, progress=progress.append)

    assert instances[0].times == pytest.approx([0, .1, .5])
    assert instances[1].times == pytest.approx([0, .8])
    assert closed == ["first.mkv", "second.mkv"]
    assert len(events) == 4  # Both original-clock temporal gates fired, plus the flushed events.
    assert [event["clip_time"] for event in events] == [.2, .138, .1, .05]
    assert [event["live_time"] for event in events] == pytest.approx([100.5, 100.25, 110.8, 110.4])
    assert [event["clip"] for event in events] == ["video/first.mkv"] * 2 + ["video/second.mkv"] * 2
    assert all("_snapshot" not in event for event in events)
    assert progress[-1] == pytest.approx(.5)
