"""The HDR preparation stage overlaps detection without queueing old captures."""

import threading
from types import SimpleNamespace

import numpy as np
import pytest

from fortnite_chest_counter.input import video_sources as S


def publish(source, sequence, *, eof=False):
    with source._cond:
        source._latest = (sequence / 15, np.full((2, 3, 4), sequence, dtype=np.float16))
        source._seq = source.frames_read = sequence
        source._eof = eof
        source._cond.notify_all()


def ready(source, predicate):
    with source._cond:
        assert source._cond.wait_for(predicate, timeout=2), "HDR stage did not make progress"


def test_conversion_runs_while_the_consumer_processes_the_previous_frame(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def convert(frame):
        if frame[0, 0, 0] == 2:
            entered.set()
            assert release.wait(2)
        return frame[..., :3].astype(np.uint8)

    monkeypatch.setattr(S, "tone_map_scrgb", convert)
    source = S.LiveSource("HDR fixture", [], 15, hdr=True)
    try:
        source._start_hdr_conversion()
        publish(source, 1)
        stream = source.frames()
        t, frame = next(stream)
        assert t == 1 / 15 and np.all(frame == 1)
        publish(source, 2, eof=True)
        assert entered.wait(2)  # frames() is suspended at yield: detector still owns frame 1
        assert np.all(frame == 1)  # in-flight conversion cannot mutate its predecessor
        release.set()
        t, frame = next(stream)
        assert t == 2 / 15 and np.all(frame == 2)
        assert list(stream) == []
        assert source.frames_processed == 2 and source.frames_dropped == 0
    finally:
        release.set()
        source.close()
    assert not source._tone_thread.is_alive()


def test_slow_conversion_drops_raw_frames_and_slow_consumer_drops_results(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def convert(frame):
        if frame[0, 0, 0] == 1:
            entered.set()
            assert release.wait(2)
        return frame[..., :3].astype(np.uint8)

    monkeypatch.setattr(S, "tone_map_scrgb", convert)
    source = S.LiveSource("HDR fixture", [], 15, hdr=True)
    try:
        source._start_hdr_conversion()
        publish(source, 1)
        assert entered.wait(2)
        publish(source, 2)
        publish(source, 3)
        release.set()
        ready(source, lambda: source._converted_seq == 3)
        # Neither raw frame 2 nor converted frame 1 is queued for this consumer.
        stream = source.frames()
        t, frame = next(stream)
        assert t == 3 / 15 and np.all(frame == 3)
        publish(source, 4)
        ready(source, lambda: source._converted_seq == 4)
        publish(source, 5, eof=True)
        ready(source, lambda: source._conversion_eof)
        t, frame = next(stream)
        assert t == 5 / 15 and np.all(frame == 5)
        assert list(stream) == []
        assert source.frames_read == 5 and source.frames_processed == 2 and source.frames_dropped == 3
    finally:
        release.set()
        source.close()


def test_hdr_conversion_failure_reaches_consumer_and_thread_ends(monkeypatch):
    def broken(_frame):
        raise ValueError("bad HDR pixels")

    monkeypatch.setattr(S, "tone_map_scrgb", broken)
    source = S.LiveSource("HDR fixture", [], 15, hdr=True)
    publish(source, 1, eof=True)
    try:
        with pytest.raises(RuntimeError, match="HDR conversion failed.*bad HDR pixels"):
            next(source.frames())
    finally:
        source.close()
    assert not source._tone_thread.is_alive()


def test_stop_wakes_converter_waiting_for_capture():
    source = S.LiveSource("HDR fixture", [], 15, hdr=True)
    source._start_hdr_conversion()
    source.close()
    assert not source._tone_thread.is_alive()
    assert list(source.frames()) == []


def test_hdr_eof_keeps_last_frame_and_the_real_tone_map_pixels():
    source = S.LiveSource("HDR fixture", [], 15, hdr=True)
    publish(source, 1, eof=True)
    expected = S.tone_map_scrgb(source._latest[1])
    try:
        frames = list(source.frames())
    finally:
        source.close()
    assert len(frames) == 1 and frames[0][0] == 1 / 15
    assert np.array_equal(frames[0][1], expected)


def test_sdr_capture_does_not_start_an_hdr_thread():
    source = S.LiveSource("SDR fixture", [], 15)
    publish(source, 1, eof=True)
    frames = list(source.frames())
    assert source._tone_thread is None
    assert frames[0][1] is source._latest[1]


def test_capture_error_wakes_hdr_consumer_instead_of_hanging():
    class BrokenPipe:
        def read(self, _size):
            raise OSError("capture pipe closed")

    source = S.LiveSource("HDR fixture", [], 15, hdr=True)
    source._process = SimpleNamespace(stdout=BrokenPipe())
    source._read_frames()
    try:
        with pytest.raises(RuntimeError, match="Video capture failed.*capture pipe closed"):
            next(source.frames())
    finally:
        source._process = None
        source.close()
    assert not source._tone_thread.is_alive()


def test_stop_returns_before_an_inflight_conversion_finishes(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def convert(frame):
        entered.set()
        assert release.wait(2)
        return frame[..., :3].astype(np.uint8)

    monkeypatch.setattr(S, "tone_map_scrgb", convert)
    source = S.LiveSource("HDR fixture", [], 15, hdr=True)
    source._start_hdr_conversion()
    publish(source, 1)
    try:
        assert entered.wait(2)
        source.request_stop()
        assert list(source.frames()) == []
    finally:
        release.set()
        source.close()
    assert not source._tone_thread.is_alive()


def test_preview_only_capture_never_starts_a_converter(monkeypatch):
    import io

    frame = np.ones((S.HEIGHT, S.WIDTH, 4), dtype="<f2")
    source = S.LiveSource("HDR fixture", [], 15, hdr=True)
    offered = []
    source.preview = SimpleNamespace(offer=lambda t, pixels, convert: offered.append((t, pixels, convert)))
    source._process = SimpleNamespace(stdout=io.BytesIO(frame.tobytes()))
    source._t0 = 0
    source._read_frames()
    assert source._tone_thread is None and source._converted is None
    assert len(offered) == 1 and np.array_equal(offered[0][1], frame)
