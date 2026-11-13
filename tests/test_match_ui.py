"""
Match status and settings in the desktop app (v0.3.0, M7): the Dashboard line says only what the evidence supports, the Settings page maps to
[match], and neither can touch counting. Runs the real window off screen and the real worker with a scripted source. No video is decoded here.

Run:   python tests/test_match_ui.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))                                     # run without installing
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "tests"))

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fortnite_chest_counter import counter as C
from fortnite_chest_counter import match_cues as M
from fortnite_chest_counter import match_history as H
from fortnite_chest_counter import match_state as S
from fortnite_chest_counter import match_tracker as MT
from fortnite_chest_counter import settings

import test_match_state as M2
import test_match_tracker as T
import test_update_gui as G


def ui():
    """Looked up on each use, so a sabotage check can replace it."""
    from fortnite_chest_counter.gui import app
    return app


def match(active=754.0, english=True, from_start=True, discontinuity=False, ended_by=None):
    return {"match_number": 1, "opened_t": 0.0, "played_from_t": 30.0, "observed_seconds": 800.0, "active_seconds": active, "spectating_seconds": 0.0, "uncertain_seconds": 0.0,
            "english_confirmed": english, "observed_from_start": from_start, "discontinuity": discontinuity, "ended_by": ended_by}


def status(state, m=None, picture="live"):
    return {"type": "match", "state": state, "t": 100.0, "picture": picture, "match": m}


def text_of(message):
    return ui().match_line(message)[0]


# ------------------------------------------------------------------ what the line says

def test_each_screen_has_its_own_words():
    assert text_of(status("LOBBY")) == "In the lobby"
    assert text_of(status("LOADING")) == "Loading"
    assert text_of(status("PRE_GAME")) == "Waiting for the match to start"
    assert text_of(status("UNKNOWN")) == "Not sure yet"


def test_a_match_seen_from_the_start_shows_its_time():
    assert text_of(status("IN_MATCH", match())) == "In match, 12:34"


def test_long_matches_show_hours():
    assert text_of(status("IN_MATCH", match(active=3723.0))) == "In match, 1:02:03"


def test_joining_late_is_shown_as_partial():
    text = text_of(status("IN_MATCH", match(from_start=False)))
    assert text.startswith("In match, 12:34 seen") and "partial" in text and "joined after the start" in text, text


def test_a_break_is_shown_as_partial():
    text = text_of(status("IN_MATCH", match(discontinuity=True)))
    assert text.startswith("In match, 12:34 seen") and "part of it was not seen" in text, text


def test_a_game_without_english_evidence_is_only_possibly_a_match():
    text = text_of(status("IN_MATCH", match(english=False, from_start=False)))
    assert text.startswith("Possibly in a match") and "not confirmed yet" in text and "no English game text seen" in text, text


def test_spectating_is_not_called_a_finished_match():
    text = text_of(status("ELIMINATED", match()))
    assert text == "Spectating or out of the match", text


def test_an_ending_is_never_called_complete():
    for ended_by in ("placed", "victory"):
        for kwargs in ({}, {"from_start": False}, {"english": False}, {"discontinuity": True}):
            text = text_of(status("ELIMINATED", match(ended_by=ended_by, **kwargs)))
            assert text.startswith("Match over") and "complete" not in text.lower(), text


def test_an_ending_in_a_partial_match_says_partial():
    assert "partial" in text_of(status("ELIMINATED", match(ended_by="placed", from_start=False)))
    assert "not confirmed" in text_of(status("ELIMINATED", match(ended_by="victory", english=False)))


def test_out_of_a_match_with_no_record_is_handled():
    assert text_of(status("ELIMINATED", None)) == "Spectating or out of the match"


def test_no_picture_is_said_out_loud():
    for picture in ("black", "frozen"):
        assert "no picture right now" in text_of(status("IN_MATCH", match(), picture))
    assert "no picture" not in text_of(status("IN_MATCH", match()))


def test_an_unknown_time_is_never_shown_as_zero():
    for value in (None, "12", float("nan"), float("inf"), -1, True):
        text = text_of(status("IN_MATCH", match(active=value)))
        assert text == "In match" and "00:00" not in text, (value, text)


def test_a_real_zero_is_still_shown():
    assert text_of(status("IN_MATCH", match(active=0.0))) == "In match, 00:00"


def test_broken_messages_mean_not_sure():
    for message in ({"type": "match"}, status("NONSENSE"), status(None), status("IN_MATCH", None), status(123)):
        assert text_of(message) == "Not sure yet", message


def test_failures_say_counting_is_fine():
    for message in ({"failed": True}, {"unavailable": True}):
        assert "Counting is not affected" in text_of(message)


# ------------------------------------------------------------------ what the worker sends

def messages_for(mode, **kwargs):
    with tempfile.TemporaryDirectory() as tmp:
        result, log, messages = T.run_app(tmp, mode, **kwargs)
    return result, log, messages


def matches_in(messages):
    return [m for m in messages if m["type"] == "match"]


def test_only_on_reports_a_status():
    for mode in ("off", "shadow"):
        assert matches_in(messages_for(mode)[2]) == [], mode


def test_on_reports_once_per_second_of_video():
    reported = matches_in(messages_for("on")[2])
    assert len(reported) == 20, len(reported)
    assert all(b["t"] - a["t"] >= 0.9 for a, b in zip(reported, reported[1:]))
    assert reported[0]["state"] == S.UNKNOWN and reported[-1]["state"] == S.IN_MATCH and reported[-1]["match"]["active_seconds"] > 0, reported[-1]


def test_status_is_the_same_at_every_interval():
    results = []
    for seconds in settings.MATCH_HEARTBEATS:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            config.write_text(f"[match]\nheartbeat_seconds = {seconds}\n", encoding="utf-8")
            read, write = os.pipe()
            stdin = sys.stdin
            import contextlib
            import io
            buffer = io.StringIO()
            try:
                sys.stdin = os.fdopen(read, "r")
                with T.scripted_pipeline(T.scripted_frames()), contextlib.redirect_stdout(buffer):
                    assert C.main(["live", "--gui", "--source", "file", "--reset", *T.folders(tmp), "--config", str(config), "--match-mode", "on"]) == 0
            finally:
                sys.stdin = stdin
                T.CONSOLE.machine, T.paths.HIDE_CHILD_CONSOLES = False, False
                os.close(write)
        results.append(json.dumps(matches_in([json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()])))
    assert len(set(results)) == 1


def test_counts_are_unchanged_by_the_status():
    off, _, _ = messages_for("off")
    on, _, _ = messages_for("on")
    assert off == on


def test_a_tracker_failure_is_reported_once():
    calls = []
    real = M.CueReader.read

    def failing(self, frame, signals=None):
        calls.append(1)
        if len(calls) == 5:
            raise RuntimeError("injected")
        return real(self, frame, signals)

    off, _, _ = messages_for("off")
    with patch.object(M.CueReader, "read", failing):
        on, _, messages = messages_for("on")
    reported = matches_in(messages)
    assert off == on and [m for m in reported if m.get("failed")] == [reported[-1]], reported
    assert len(reported) == 5


def test_a_tracker_that_cannot_start_is_reported():
    with tempfile.TemporaryDirectory() as empty, patch.object(M, "TEMPLATE_DIR", Path(empty)):
        _, _, messages = messages_for("on")
    assert [m.get("unavailable") for m in matches_in(messages)] == [True]


def test_a_history_that_cannot_start_is_reported():
    with patch.object(H.HistoryWriter, "__init__", side_effect=RuntimeError("injected")):
        _, _, messages = messages_for("on")
    assert [m.get("unavailable") for m in matches_in(messages)] == [True]


def test_a_failing_status_cannot_stop_recording():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "h"
        writer = H.HistoryWriter(f, [].append)
        writer.start_run("file", "0.3.0", 15, ["en"], 0, 0, 0, 60)
        calls = []

        def broken(**fields):
            calls.append(fields)
            raise OSError("the app is gone")

        rig = T.Rig(history=writer, heartbeat_seconds=60, frames=lambda: (0, 0), status=broken)
        M2.played_match(rig).show(10, "you_placed", health=40).show(5, "connecting").finish()
        assert len(calls) == 1 and not rig.tracker.failed and len(H.read(f).matches) == 1


def test_the_status_carries_what_the_line_needs():
    seen = []
    rig = T.Rig(status=lambda **fields: seen.append(fields))
    M2.played_match(rig)
    last = seen[-1]
    assert last["state"] == S.IN_MATCH and last["picture"] == "live" and last["match"]["observed_from_start"] is True and last["match"]["english_confirmed"] is True
    assert last["match"]["ended_by"] is None and last["match"]["discontinuity"] is False


def test_the_status_reports_a_black_picture():
    seen = []
    T.Rig(status=lambda **fields: seen.append(fields)).show(2, black=True)
    assert seen[-1]["picture"] == "black"


def test_shadow_has_no_status_channel():
    with patch.object(C.CONSOLE, "warn"):
        tracker = C._open_tracker({"match": {"mode": "shadow"}, "logging": {"enabled": True}}, type("S", (), {"log": type("L", (), {"write": staticmethod(lambda r: None)})})())
    assert tracker._status is None


# ------------------------------------------------------------------ the Dashboard

def counting(w):
    w.win.worker.is_running = True
    w.win.set_mode("counting")


def test_the_line_is_hidden_until_there_is_something_to_report():
    with G.window() as w:
        d = w.win.dashboard
        assert d.match_row.isHidden() and d.match.text() == ""
        counting(w)
        w.win.handle({"type": "status", "text": "15 fps", "fps": 15.0})
        w.win.handle({"type": "counts", "certain": 1, "approx": 1})
        assert d.match_row.isHidden(), "off mode sends no match messages, so nothing may appear"


def test_the_line_follows_the_worker():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle(status("LOBBY"))
        assert not d.match_row.isHidden() and d.match.text() == "In the lobby"
        w.win.handle(status("IN_MATCH", match()))
        assert d.match.text() == "In match, 12:34"
        w.win.handle(status("UNKNOWN"))
        assert d.match.text() == "Not sure yet"


def test_the_line_is_cleared_on_stop():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle(status("IN_MATCH", match()))
        w.win.worker.is_running = False
        w.win.handle({"type": "exit", "code": 0})
        assert d.match_row.isHidden() and d.match.text() == "" and w.win.match_seen_at is None


def test_a_late_message_after_stopping_is_ignored():
    with G.window() as w:
        w.win.set_mode("stopped")
        w.win.handle(status("IN_MATCH", match()))
        assert w.win.dashboard.match_row.isHidden()


def test_a_new_session_starts_with_no_old_status():
    with G.window() as w:
        counting(w)
        w.win.handle(status("IN_MATCH", match()))
        w.win.worker.is_running = False
        w.win.set_mode("stopped")
        w.win.worker.is_running = True
        w.win.set_mode("connecting")
        assert w.win.dashboard.match_row.isHidden() and w.win.dashboard.match.text() == ""


def test_an_error_stop_clears_it_too():
    with G.window() as w:
        counting(w)
        w.win.handle(status("IN_MATCH", match()))
        w.win.worker.is_running = False
        w.win.handle({"type": "error", "text": "broken"})
        w.win.handle({"type": "exit", "code": 1})
        assert w.win.dashboard.match_row.isHidden() and w.win.mode == "error"


def test_silence_means_no_video():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle(status("IN_MATCH", match()))
        w.win._check_match_video()
        assert d.match.text() == "In match, 12:34"
        w.win.match_seen_at -= ui().MATCH_STALE_SECONDS + 1
        w.win._check_match_video()
        assert d.match.text() == "No video right now"
        w.win.handle(status("IN_MATCH", match(active=760.0)))
        assert d.match.text() == "In match, 12:40"


def test_the_slow_timer_checks_for_silence():
    with G.window() as w:
        counting(w)
        w.win.handle(status("IN_MATCH", match()))
        w.win.match_seen_at -= ui().MATCH_STALE_SECONDS + 1
        w.win._tick_slow()
        assert w.win.dashboard.match.text() == "No video right now"


def test_a_failure_stays_on_screen():
    with G.window() as w:
        counting(w)
        w.win.handle({"type": "match", "failed": True})
        assert "Stopped for this session" in w.win.dashboard.match.text() and w.win.match_seen_at is None
        w.win._check_match_video()
        assert "Stopped for this session" in w.win.dashboard.match.text()


def test_the_line_is_read_only():
    with G.window() as w:
        counting(w)
        before = (w.win.counts, w.win.mode, w.win.dashboard.certain.value.text(), w.win.dashboard.approx.value.text(), w.win.dashboard.viewers.text(), sorted(p.name for p in w.dir.rglob("*")))
        with patch.object(w.win.worker, "send", create=True) as send:
            for message in (status("IN_MATCH", match()), status("ELIMINATED", match(ended_by="victory")), {"type": "match", "failed": True}):
                w.win.handle(message)
        assert send.call_count == 0
        assert before == (w.win.counts, w.win.mode, w.win.dashboard.certain.value.text(), w.win.dashboard.approx.value.text(), w.win.dashboard.viewers.text(), sorted(p.name for p in w.dir.rglob("*")))


def test_it_does_not_appear_in_the_activity_log():
    assert ui().log_entries(status("IN_MATCH", match())) == []


def test_the_layout_keeps_its_pages_and_order():
    with G.window() as w:
        assert w.win.pages.count() == 6 and w.win.nav.count() == 6            # v0.5.0: Predictions after Analytics
        layout = w.win.dashboard.match_row.parentWidget().layout()
        order = [layout.itemAt(i) for i in range(layout.count())]
        position = next(i for i, item in enumerate(order) if item.widget() is w.win.dashboard.match_row)
        def texts(item):
            inner = item.layout()
            return [inner.itemAt(k).widget().text() for k in range(inner.count()) if inner.itemAt(k).widget() is not None and hasattr(inner.itemAt(k).widget(), "text")] if inner is not None else []
        assert "Chest types:" in texts(order[position - 1]) and "Viewers see:" in texts(order[position + 1])


def test_recorded_worker_messages_drive_the_real_window():
    result, _, messages = messages_for("on")
    with G.window() as w:
        d = w.win.dashboard
        w.win.worker.is_running = True
        w.win.set_mode("connecting")
        shown = []
        for message in messages:
            w.win.handle(message)
            if message["type"] == "match":
                shown.append(d.match.text())
        assert shown[0] == "Not sure yet" and shown[-1].startswith("In match") and "seen" in shown[-1] and "joined after the start" in shown[-1], shown
        assert w.win.counts == (result["state"]["certain"], result["state"]["approximate"])
        w.win.worker.is_running = False
        w.win.handle({"type": "exit", "code": 0})
        assert d.match_row.isHidden()


# ------------------------------------------------------------------ Settings

def saved(w):
    return settings.load_config(w.dir / "config.toml")


def test_settings_start_on_at_a_minute():
    with G.window() as w:
        page = w.win.settings_page
        page.load()
        assert page.match_on.isChecked() and page.heartbeat.currentData() == 60 and page.heartbeat.isEnabled()
    with G.window(config='[match]\nmode = "off"\n') as w:
        page = w.win.settings_page
        page.load()
        assert not page.match_on.isChecked() and page.heartbeat.isEnabled()      # v0.4.0 (D7): history is kept with tracking off too


def test_the_choices_are_the_supported_ones_and_shadow_is_not_offered():
    with G.window() as w:
        page = w.win.settings_page
        assert [page.heartbeat.itemData(i) for i in range(page.heartbeat.count())] == list(settings.MATCH_HEARTBEATS)
        assert "recommended" in page.heartbeat.itemText(1)
        everything = " ".join(widget.text() for widget in page.findChildren(type(page.saved)))
        assert "shadow" not in everything.lower()


def test_turning_it_on_is_saved_and_read_back():
    with G.window(config='[match]\nmode = "off"\n') as w:
        page = w.win.settings_page
        page.load()
        page.match_on.setChecked(True)
        page.heartbeat.setCurrentIndex(page.heartbeat.findData(300))
        page.save()
        cfg, _, warnings = saved(w)
        assert warnings == [] and cfg["match"] == {"mode": "on", "heartbeat_seconds": 300}
        page.match_on.setChecked(False)
        page.load()
        assert page.match_on.isChecked() and page.heartbeat.currentData() == 300


def test_every_interval_saves():
    with G.window() as w:
        page = w.win.settings_page
        page.load()
        for seconds in settings.MATCH_HEARTBEATS:
            page.heartbeat.setCurrentIndex(page.heartbeat.findData(seconds))
            page.save()
            assert saved(w)[0]["match"]["heartbeat_seconds"] == seconds


def test_turning_it_off_is_saved():
    with G.window(config='[match]\nmode = "on"\n') as w:
        page = w.win.settings_page
        page.load()
        assert page.match_on.isChecked()
        page.match_on.setChecked(False)
        page.save()
        assert saved(w)[0]["match"]["mode"] == "off"


def test_shadow_is_kept_unless_the_user_turns_tracking_on():
    with G.window(config='[match]\nmode = "shadow"\n') as w:
        page = w.win.settings_page
        page.load()
        assert not page.match_on.isChecked()
        page.save()
        assert saved(w)[0]["match"]["mode"] == "shadow"
        page.match_on.setChecked(True)
        page.save()
        assert saved(w)[0]["match"]["mode"] == "on"
        page.match_on.setChecked(False)
        page.save()
        assert saved(w)[0]["match"]["mode"] == "off"


def test_invalid_config_values_show_the_safe_defaults():
    with G.window(config='[match]\nmode = "maybe"\nheartbeat_seconds = 7\n') as w:
        page = w.win.settings_page
        page.load()
        assert not page.match_on.isChecked() and page.heartbeat.currentData() == 60
        page.save()
        cfg, _, warnings = saved(w)
        assert warnings == [] and cfg["match"] == {"mode": "off", "heartbeat_seconds": 60}


def test_a_config_from_before_this_version_gains_the_section():
    with G.window(config='[display]\nshow = "certain"\n') as w:
        page = w.win.settings_page
        page.load()
        page.save()
        cfg, _, warnings = saved(w)
        assert warnings == [] and cfg["match"] == {"mode": "on", "heartbeat_seconds": 60} and cfg["display"]["show"] == "certain"


def test_saving_keeps_comments_and_other_sections():
    with G.window(config='# my note\n[obs_websocket]\nport = 4460\n') as w:
        page = w.win.settings_page
        page.load()
        page.save()
        text = (w.dir / "config.toml").read_text(encoding="utf-8")
        assert "# my note" in text and saved(w)[0]["obs_websocket"]["port"] == 4460


def test_changes_while_counting_wait_for_the_next_session():
    with G.window() as w:
        page = w.win.settings_page
        page.load()
        counting(w)
        page.match_on.setChecked(True)
        page.save()
        assert "Stop and start counting" in page.saved.text()
        assert w.win.dashboard.match_row.isHidden()


def test_saving_settings_changes_no_counts():
    with G.window() as w:
        base = w.dir / "state" / "chest_state.json"
        base.parent.mkdir(parents=True, exist_ok=True)
        base.write_text(json.dumps({"certain": 3, "approximate": 7}), encoding="utf-8")
        before = base.read_bytes()
        page = w.win.settings_page
        page.load()
        page.match_on.setChecked(True)
        page.save()
        assert base.read_bytes() == before and not (w.dir / "state" / "history").exists()


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}", flush=True)
        except Exception:
            failed += 1
            import traceback
            print(f"  FAIL  {name}", flush=True)
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} match UI checks passed")
    sys.exit(1 if failed else 0)
