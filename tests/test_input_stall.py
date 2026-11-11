"""
A live input that stays open and stops delivering pictures (v0.3.0, M9): the app must say so, without restarting anything, without changing what is
analysed, and without warning about a finished video file, a short hitch or a normal stop.

Run:   python tests/test_input_stall.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))                                     # run without installing
sys.path.insert(0, str(ROOT / "tests"))

import contextlib
import io
import json
import os
import socket
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

import test_update_gui as G
from fortnite_chest_counter.console import CONSOLE
from fortnite_chest_counter.input import video_sources as _real_sources

STALL = 0.3
PICTURE = np.zeros((_real_sources.HEIGHT, _real_sources.WIDTH, 3), np.uint8)


def sources():
    """Looked up on each use, so a sabotage check can replace it."""
    from fortnite_chest_counter.input import video_sources
    return video_sources


def ui():
    from fortnite_chest_counter.gui import app
    return app


def fed(watch_stalls=True):
    """A live source with the FFmpeg side replaced: the test decides when each picture arrives."""
    class Fed(sources().LiveSource):
        STALL_AFTER, IDLE_WAIT = STALL, 0.02

        def __init__(self):
            super().__init__("device: test", [], 15, watch_stalls=watch_stalls)
            self._t0 = time.monotonic()

        def feed(self, picture=PICTURE):
            with self._cond:
                self._latest = (time.monotonic() - self._t0, picture)
                self._seq += 1
                self.frames_read += 1
                self._cond.notify_all()

        def finish(self):
            with self._cond:
                self._eof = True
                self._cond.notify_all()

    return Fed()


@contextlib.contextmanager
def machine_mode():
    buffer = io.StringIO()
    CONSOLE.machine = True
    try:
        with contextlib.redirect_stdout(buffer):
            yield buffer
    finally:
        CONSOLE.machine = False


def messages(buffer):
    return [json.loads(line) for line in buffer.getvalue().splitlines() if line.startswith("{")]


def states(buffer):
    return [m.get("state") for m in messages(buffer) if m.get("type") == "stream"]


@contextlib.contextmanager
def running(source, slow=0.0):
    """Reads the source on a thread, like the counting loop does."""
    got = []

    def read():
        for item in source.frames():
            got.append(item)
            if slow:
                time.sleep(slow)

    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    try:
        yield got
    finally:
        source.request_stop()
        thread.join(5)
        assert not thread.is_alive(), "frames() did not end"


def wait_until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


# ------------------------------------------------------------------ the warning

def test_a_stall_warns_once():
    s = fed()
    with machine_mode() as buffer, running(s) as got:
        s.feed()
        assert wait_until(lambda: got)
        time.sleep(STALL * 4)
    assert states(buffer) == ["no_video"], states(buffer)


def test_the_warning_says_what_is_known_and_not_why():
    s = fed()
    with machine_mode() as buffer, running(s) as got:
        s.feed()
        assert wait_until(lambda: got)
        time.sleep(STALL * 2)
    text = next(m["text"] for m in messages(buffer) if m.get("state") == "no_video").lower()
    assert "not receiving video" in text and "counts are kept" in text
    for claim in ("disconnected", "unplugged", "camera", "capture card", "closed"):
        assert claim not in text, claim


def test_a_short_hitch_stays_silent():
    s = fed()
    with machine_mode() as buffer, running(s) as got:
        for count in range(1, 6):
            s.feed()
            assert wait_until(lambda: len(got) == count)
            time.sleep(STALL * 0.4)
    assert states(buffer) == [], states(buffer)


def test_recovery_clears_it_and_reports_what_may_be_missing():
    s = fed()
    with machine_mode() as buffer, running(s) as got:
        s.feed()
        assert wait_until(lambda: got)
        time.sleep(STALL * 2)
        s.feed()
        assert wait_until(lambda: len(got) == 2)
    assert states(buffer) == ["no_video", "live", "incomplete"], states(buffer)
    text = next(m["text"] for m in messages(buffer) if m.get("state") == "incomplete")
    assert "may be missing" in text and "not received" in text


def test_the_gap_reported_is_the_real_one():
    s = fed()
    s.STALL_AFTER = 1.0
    with machine_mode() as buffer, running(s) as got:
        s.feed()
        assert wait_until(lambda: got)
        time.sleep(3.2)
        s.feed()
        assert wait_until(lambda: len(got) == 2)
    text = next(m["text"] for m in messages(buffer) if m.get("state") == "incomplete")
    assert text.startswith("about 3 s"), text


def test_a_second_stall_warns_again():
    s = fed()
    with machine_mode() as buffer, running(s) as got:
        for count in (1, 2):
            s.feed()
            assert wait_until(lambda: len(got) == count)
            time.sleep(STALL * 2)
    assert states(buffer).count("no_video") == 2, states(buffer)


def test_the_terminal_gets_a_warning_too():
    s = fed()
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer), running(s) as got:
        s.feed()
        assert wait_until(lambda: got)
        time.sleep(STALL * 2)
    assert "NOT RECEIVING VIDEO" in buffer.getvalue()


# ------------------------------------------------------------------ what must not warn

def test_a_finished_recording_is_not_a_stall():
    s = fed()
    with machine_mode() as buffer:
        with running(s) as got:
            s.feed()
            assert wait_until(lambda: got)
            s.finish()
            time.sleep(STALL * 3)
    assert states(buffer) == [], states(buffer)


def test_a_video_file_is_never_watched():
    assert sources().make_source("file", 15, video="x.mp4").watch_stalls is False
    s = fed(watch_stalls=False)
    with machine_mode() as buffer, running(s) as got:
        s.feed()
        assert wait_until(lambda: got)
        time.sleep(STALL * 3)
    assert states(buffer) == [], states(buffer)


def test_live_inputs_are_watched():
    made = (sources().make_source("obs-camera", 15), sources().make_source("device", 15, device="Card"), sources().WindowSource("Projector", 15))
    assert all(source.watch_stalls for source in made)
    assert sources().LiveSource.STALL_AFTER == 10.0


def test_a_slow_detector_is_not_a_stall():
    s = fed()
    stop = threading.Event()

    def feeder():
        while not stop.is_set():
            s.feed()
            time.sleep(0.02)

    thread = threading.Thread(target=feeder, daemon=True)
    with machine_mode() as buffer:
        with running(s, slow=STALL * 1.5) as got:
            thread.start()
            assert wait_until(lambda: len(got) >= 3)
            stop.set()
    thread.join(2)
    assert states(buffer) == [], states(buffer)


def test_stopping_during_a_stall_ends_at_once():
    s = fed()
    with machine_mode(), running(s) as got:
        s.feed()
        assert wait_until(lambda: got)
        time.sleep(STALL * 2)
        started = time.monotonic()
        s.request_stop()
    assert time.monotonic() - started < 1.0


# ------------------------------------------------------------------ nothing else changes

def test_every_picture_still_arrives_unchanged_and_in_order():
    s = fed()
    pictures = [np.full_like(PICTURE, value) for value in range(4)]
    with machine_mode(), running(s) as got:
        for count, picture in enumerate(pictures, 1):
            s.feed(picture)
            assert wait_until(lambda: len(got) == count)
            if count == 2:
                time.sleep(STALL * 2)                                     # a stall in the middle
    assert [item[1] is picture for item, picture in zip(got, pictures)] == [True] * 4
    assert [item[0] for item in got] == sorted(item[0] for item in got)
    assert s.frames_processed == 4 and s.frames_dropped == 0


def test_a_stall_restarts_nothing():
    s = fed()
    calls = []
    s.open = lambda *a, **k: calls.append("open")
    s.close = lambda *a, **k: calls.append("close")
    with machine_mode(), running(s) as got:
        s.feed()
        assert wait_until(lambda: got)
        time.sleep(STALL * 3)
    assert calls == [], calls


def test_the_detector_and_counter_are_not_involved():
    source = (ROOT / "src/fortnite_chest_counter/input/video_sources.py").read_text(encoding="utf-8")
    for name in ("estimator", "write_obs", "CounterSession", "obs_output"):
        assert name not in source, name


def test_a_real_ffmpeg_that_stays_open():
    """Real FFmpeg, reading raw video from a socket that stays open with nothing on it."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    s = sources().LiveSource("device: test", ["-f", "rawvideo", "-video_size", "1280x720", "-pixel_format", "rgb24", "-framerate", "15", "-i", f"tcp://127.0.0.1:{port}?listen=1"], 15)
    s.STALL_AFTER = 1.5
    picture = bytes(1280 * 720 * 3)
    connection = {}

    def sender():
        for _ in range(200):
            try:
                connection["socket"] = socket.create_connection(("127.0.0.1", port), timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        send(1.5)

    def send(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            connection["socket"].sendall(picture)
            time.sleep(1 / 15)

    thread = threading.Thread(target=sender, daemon=True)
    thread.start()
    try:
        with machine_mode() as buffer:
            s.open()
            with running(s) as got:
                thread.join(10)
                assert wait_until(lambda: "no_video" in states(buffer), timeout=8), states(buffer)
                assert s._process.poll() is None, "FFmpeg should still be running"
                before = len(got)
                send(1.0)
                assert wait_until(lambda: "incomplete" in states(buffer), timeout=8), states(buffer)
                assert len(got) > before
    finally:
        s.close()
        if "socket" in connection:
            connection["socket"].close()
    assert states(buffer) == ["no_video", "live", "incomplete"], states(buffer)


# ------------------------------------------------------------------ the window

def counting(w, fps=14.9):
    w.win.worker.is_running = True
    w.win.set_mode("counting")
    w.win.started_at = time.monotonic()
    w.win.last_status = {"fps": fps, "ms_per_frame": 11.0, "dropped": 0}


def test_the_dashboard_says_no_video():
    with G.window() as w:
        counting(w)
        w.win.handle({"type": "stream", "state": "no_video", "text": "NOT RECEIVING VIDEO"})
        assert w.win.dashboard.pill.text().endswith("No video"), w.win.dashboard.pill.text()


def test_the_old_rate_is_not_shown_during_a_stall():
    with G.window() as w:
        counting(w)
        w.win._tick_slow()
        assert "analysing 14.9" in w.win.dashboard.metrics.text()
        w.win.handle({"type": "stream", "state": "no_video", "text": "x"})
        w.win._tick_slow()
        text = w.win.dashboard.metrics.text()
        assert "analysing" not in text and "no new video" in text, text


def test_the_warning_clears_when_video_returns():
    with G.window() as w:
        counting(w)
        w.win.handle({"type": "stream", "state": "no_video", "text": "x"})
        w.win.handle({"type": "stream", "state": "live", "text": "y"})
        assert w.win.dashboard.pill.text().endswith("Counting"), w.win.dashboard.pill.text()
        w.win.handle({"type": "status", "fps": 15.0, "ms_per_frame": 11.0, "dropped": 0, "certain": 0, "approx": 0})
        w.win._tick_slow()
        text = w.win.dashboard.metrics.text()
        assert "analysing 15.0" in text and "no new video" not in text, text


def test_the_old_rate_does_not_come_back_with_the_video():
    with G.window() as w:
        counting(w)
        w.win.handle({"type": "stream", "state": "no_video", "text": "x"})
        w.win.handle({"type": "stream", "state": "live", "text": "y"})
        w.win._tick_slow()
        assert "analysing" not in w.win.dashboard.metrics.text(), w.win.dashboard.metrics.text()


def test_the_preview_keeps_the_message_not_the_last_picture():
    with G.window() as w:
        counting(w)
        w.win.handle({"type": "stream", "state": "no_video", "text": "x"})
        assert "NO VIDEO" in w.win.dashboard.preview.view.text()
        called = []
        w.win.preview_reader.read = lambda: called.append(1)
        w.win._tick_preview()
        assert not called


def test_the_message_reaches_the_activity_log():
    with G.window() as w:
        counting(w)
        w.win.handle({"type": "stream", "state": "no_video", "text": "NOT RECEIVING VIDEO - test"})
        w.qt.processEvents()
        assert "NOT RECEIVING VIDEO" in w.win.dashboard.log.toPlainText()


def test_it_is_forgotten_when_counting_stops():
    with G.window() as w:
        counting(w)
        w.win.handle({"type": "stream", "state": "no_video", "text": "x"})
        w.win.set_mode("stopped")
        assert w.win.stream_state is None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"ok    {t.__name__}")
        except Exception as error:
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {t.__name__}: {error!r}")
    print(f"{len(tests) - failed}/{len(tests)} input stall checks passed")
    raise SystemExit(1 if failed else 0)
