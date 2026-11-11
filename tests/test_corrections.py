"""
Manual corrections (v0.3.0, M8C): +1 and -1 on the chest count, and Not a match / Restore. They go through the counter's own save path, are reversible, keep
everything they change on record, and a +1 is never taken as proof that the detector failed. Runs the real session, the real worker loop and the real window.

Run:   python tests/test_corrections.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))                                     # run without installing
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "tests"))

import contextlib
import io
import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fortnite_chest_counter import counter as C
from fortnite_chest_counter import match_analytics as A
from fortnite_chest_counter import match_history as H
from fortnite_chest_counter import paths, profiles, settings
from fortnite_chest_counter.console import CONSOLE

import test_match_analytics as MA
import test_match_tracker as T
import test_update_gui as G


def cfg_for(tmp, **extra):
    cfg, _, _ = settings.load_config(None, {("state", "path"): str(Path(tmp) / "s.json"), ("state", "obs_dir"): str(Path(tmp) / "o"), ("logging", "dir"): str(Path(tmp) / "l"), **extra})
    return cfg


def session_in(tmp, certain=2, approx=5):
    cfg = cfg_for(tmp)
    session = C.CounterSession(cfg, reset=True)
    session.state["certain"], session.state["approximate"] = certain, approx
    session.save()
    return session, cfg


def request(delta=1, reason="manual", correction_id=None):
    return {"id": correction_id or uuid.uuid4().hex, "delta": delta, "reason": reason}


def history(tmp):
    return Path(tmp) / "history" / "s"


def on_disk(tmp):
    return json.loads((Path(tmp) / "s.json").read_text(encoding="utf-8"))


def corrections(tmp):
    return H.read_chest_corrections(history(tmp))


# ------------------------------------------------------------------ what a correction changes

def test_plus_one_changes_only_approx():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        result = session.apply_correction(request(1))
        assert result["status"] == "applied" and (session.state["certain"], session.state["approximate"]) == (2, 6)
        assert (on_disk(tmp)["certain"], on_disk(tmp)["approximate"]) == (2, 6)


def test_minus_one_changes_only_approx():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        assert session.apply_correction(request(-1))["status"] == "applied" and (session.state["certain"], session.state["approximate"]) == (2, 4)


def test_obs_shows_the_corrected_total():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        session.apply_correction(request(1))
        assert "6" in (Path(tmp) / "o" / "approximate_chests.txt").read_text(encoding="utf-8")


def test_approx_can_never_go_below_certain():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp, 3, 3)
        result = session.apply_correction(request(-1))
        assert result["status"] == "refused" and "CERTAIN" in result["message"] and (session.state["certain"], session.state["approximate"]) == (3, 3) and corrections(tmp) == []


def test_it_cannot_go_below_zero():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp, 0, 0)
        assert session.apply_correction(request(-1))["status"] == "refused" and session.state["approximate"] == 0


def test_the_maximum_is_respected():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp, 0, C.MAX_STARTING_COUNT)
        assert session.apply_correction(request(1))["status"] == "refused"


def test_event_ids_are_not_disturbed():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        before = session.state["events_logged"]
        session.apply_correction(request(1))
        assert session.state["events_logged"] == before


def test_the_chest_type_split_still_adds_up():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp, 0, 0)
        session.apply_correction(request(1))
        breakdown = C.type_breakdown(session.state)
        assert breakdown["unclassified"]["approx"] == 1 and breakdown["unclassified"]["certain"] == 0


def test_bad_requests_are_refused_and_change_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        for bad in ({}, {"id": ""}, {"id": 5, "delta": 1}, {"id": "a", "delta": 2}, {"id": "b", "delta": 0}, {"id": "c", "delta": True}, {"id": "d", "delta": "1"}, {"id": "e", "delta": [1]},
                    {"id": "f", "delta": 1, "reason": "false_positive"}, {"id": "g", "delta": -1, "reason": "missed"}, {"id": "h", "delta": 1, "reason": "nonsense"}):
            assert session.apply_correction(bad)["status"] == "refused", bad
        assert session.state["approximate"] == 5 and corrections(tmp) == []


def test_the_session_log_line_is_not_read_as_a_chest():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        session.apply_correction(request(1))
        rows = [json.loads(line) for line in session.log.path.read_text(encoding="utf-8").splitlines()]
        line = next(row for row in rows if row.get("event") == "chest_correction")
        assert "time" not in line and line["delta"] == 1


# ------------------------------------------------------------------ what is kept

def test_the_record_keeps_identity_reason_and_both_numbers():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        session.apply_correction(request(1, "not_visible", "abc"))
        (row,) = corrections(tmp)
        assert row["id"] == "abc" and row["delta"] == 1 and row["reason"] == "not_visible" and row["at"] and row["undone"] is False
        assert (row["certain_total"], row["approximate_total"], row["detector_approximate"]) == (2, 6, 5) and row["counter_token"] == C.counter_token(session.state)


def test_detector_count_stays_separate_over_several_corrections():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        for delta in (1, 1, -1, 1):
            session.apply_correction(request(delta))
        assert [row["detector_approximate"] for row in corrections(tmp)] == [5, 5, 5, 5] and session.state["approximate"] == 7
        assert H.correction_totals(corrections(tmp), C.counter_token(session.state))["net"] == 2


def test_a_correction_with_tracking_on_names_its_run():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        session.history = H.HistoryWriter(history(tmp), [].append, run_id="live-run")
        session.history.start_run("file", "0.3.0", 15, ["en"], 2, 5, 0, 60)
        session.apply_correction(request(1))
        assert corrections(tmp)[0]["run_id"] == "live-run"


def test_a_correction_with_tracking_off_has_no_run():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        session.apply_correction(request(1))
        assert corrections(tmp)[0]["run_id"] is None


def test_nothing_is_recorded_when_saving_is_off():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        session.persist = False
        assert session.apply_correction(request(1))["recorded"] is False and not history(tmp).exists()


# ------------------------------------------------------------------ a +1 is not a detector failure

def test_only_explicit_reasons_count_as_detector_errors():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp, 0, 10)
        for delta, reason in ((1, "not_visible"), (1, "not_visible"), (1, "manual"), (1, "missed"), (-1, "manual"), (-1, "false_positive")):
            session.apply_correction(request(delta, reason))
        totals = H.correction_totals(corrections(tmp))
        assert (totals["not_visible"], totals["unknown"], totals["detector_misses"], totals["detector_false_positives"]) == (2, 2, 1, 1)


def test_the_default_reason_makes_no_claim():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        session.apply_correction({"id": "x", "delta": 1})
        totals = H.correction_totals(corrections(tmp))
        assert corrections(tmp)[0]["reason"] == H.MANUAL and totals["detector_misses"] == 0 and totals["unknown"] == 1


def test_a_reason_can_be_given_later_and_the_latest_wins():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        session.apply_correction(request(1, "manual", "abc"))
        before = (history(tmp) / H.CHESTS).read_bytes()
        H.set_correction_reason(history(tmp), "abc", "missed")
        H.set_correction_reason(history(tmp), "abc", "not_visible")
        assert (history(tmp) / H.CHESTS).read_bytes().startswith(before) and corrections(tmp)[0]["reason"] == "not_visible" and session.state["approximate"] == 6


def test_an_undone_correction_makes_no_claim():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        session.apply_correction(request(1, "missed", "abc"))
        session.apply_correction({"id": "u", "undoes": "abc"})
        totals = H.correction_totals(corrections(tmp))
        assert totals["detector_misses"] == 0 and totals["reversed"] == 1 and totals["net"] == 0


# ------------------------------------------------------------------ undo, repeats and resets

def test_undo_restores_the_total_and_keeps_the_record():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        session.apply_correction(request(1, "manual", "abc"))
        before = (history(tmp) / H.CHESTS).read_bytes()
        result = session.apply_correction({"id": "u", "undoes": "abc"})
        assert result["status"] == "applied" and result["delta"] == -1 and session.state["approximate"] == 5
        assert (history(tmp) / H.CHESTS).read_bytes().startswith(before)
        (row,) = corrections(tmp)
        assert row["id"] == "abc" and row["undone"] is True


def test_undoing_a_minus_adds_it_back():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        session.apply_correction(request(-1, "manual", "abc"))
        session.apply_correction({"id": "u", "undoes": "abc"})
        assert session.state["approximate"] == 5


def test_undoing_twice_does_nothing_more():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        session.apply_correction(request(1, "manual", "abc"))
        session.apply_correction({"id": "u1", "undoes": "abc"})
        assert session.apply_correction({"id": "u2", "undoes": "abc"})["status"] == "already" and session.state["approximate"] == 5


def test_undoing_something_unknown_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        assert session.apply_correction({"id": "u", "undoes": "nope"})["status"] == "refused" and session.state["approximate"] == 5


def test_an_undo_that_would_break_the_invariant_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp, 5, 5)
        session.apply_correction(request(1, "manual", "abc"))
        session.state["certain"] = 6                                      # a CERTAIN chest arrived and used up the room
        session.save()
        assert session.apply_correction({"id": "u", "undoes": "abc"})["status"] == "refused" and session.state["approximate"] == 6


def test_the_same_request_twice_counts_once():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        session.apply_correction(request(1, "manual", "abc"))
        assert session.apply_correction(request(1, "manual", "abc"))["status"] == "already" and session.state["approximate"] == 6 and len(corrections(tmp)) == 1


def test_the_same_request_after_a_restart_counts_once():
    with tempfile.TemporaryDirectory() as tmp:
        session, cfg = session_in(tmp)
        session.apply_correction(request(1, "manual", "abc"))
        again = C.CounterSession(cfg)
        assert again.apply_correction(request(1, "manual", "abc"))["status"] == "already" and again.state["approximate"] == 6


def test_corrections_survive_a_restart_and_can_still_be_undone():
    with tempfile.TemporaryDirectory() as tmp:
        session, cfg = session_in(tmp)
        session.apply_correction(request(1, "manual", "abc"))
        again = C.CounterSession(cfg)
        assert again.state["approximate"] == 6 and again.apply_correction({"id": "u", "undoes": "abc"})["status"] == "applied" and again.state["approximate"] == 5


def test_a_reset_ends_the_corrections_but_keeps_the_record():
    with tempfile.TemporaryDirectory() as tmp:
        session, cfg = session_in(tmp)
        session.apply_correction(request(1, "manual", "abc"))
        time.sleep(0.05)
        C.set_counts(cfg, 0, 0, "reset")
        live = C.CounterSession(cfg)
        assert H.correction_totals(corrections(tmp), C.counter_token(live.state))["net"] == 0 and len(corrections(tmp)) == 1
        result = live.apply_correction({"id": "u", "undoes": "abc"})
        assert result["status"] == "refused" and "reset or edited" in result["message"] and live.state["approximate"] == 0


def test_edit_counts_ends_them_too():
    with tempfile.TemporaryDirectory() as tmp:
        session, cfg = session_in(tmp)
        session.apply_correction(request(1, "manual", "abc"))
        C.set_counts(cfg, 1, 40)
        live = C.CounterSession(cfg)
        assert live.apply_correction({"id": "u", "undoes": "abc"})["status"] == "refused" and live.state["approximate"] == 40


def test_the_set_count_command_ends_them_too():
    with tempfile.TemporaryDirectory() as tmp:
        session, cfg = session_in(tmp)
        session.apply_correction(request(1, "manual", "abc"))
        token = C.counter_token(session.state)
        with contextlib.redirect_stdout(io.StringIO()):
            C.main(["set-count", "150", "--state", str(Path(tmp) / "s.json"), "--obs-dir", str(Path(tmp) / "o"), "--log-dir", str(Path(tmp) / "l")])
        assert C.counter_token(on_disk(tmp)) != token


def test_the_reset_command_ends_them_too():
    with tempfile.TemporaryDirectory() as tmp:
        session, cfg = session_in(tmp)
        before = on_disk(tmp).get("counter_life", 0)
        with contextlib.redirect_stdout(io.StringIO()):
            C.main(["reset", "--state", str(Path(tmp) / "s.json"), "--obs-dir", str(Path(tmp) / "o"), "--log-dir", str(Path(tmp) / "l")])
        assert on_disk(tmp)["counter_life"] == before + 1


def test_a_running_session_adopts_a_reset_before_correcting():
    with tempfile.TemporaryDirectory() as tmp:
        session, cfg = session_in(tmp)
        time.sleep(0.05)
        C.set_counts(cfg, 0, 0, "reset")
        session.apply_correction(request(1))
        assert (session.state["certain"], session.state["approximate"]) == (0, 1) and on_disk(tmp)["approximate"] == 1


# ------------------------------------------------------------------ failures

def test_a_history_failure_keeps_the_total_and_warns_once():
    with tempfile.TemporaryDirectory() as tmp, patch.object(CONSOLE, "warn") as warn:
        session, _ = session_in(tmp)
        with patch.object(H, "append_chest_correction", side_effect=OSError("disk full")):
            first = session.apply_correction(request(1))
            second = session.apply_correction(request(1))
        assert first["status"] == second["status"] == "applied" and first["recorded"] is False and session.state["approximate"] == 7 and warn.call_count == 1


def test_a_bug_cannot_stop_counting():
    with tempfile.TemporaryDirectory() as tmp, patch.object(CONSOLE, "warn"):
        session, _ = session_in(tmp)
        with patch.object(H, "read_chest_corrections", side_effect=RuntimeError("injected")):
            assert session.apply_correction(request(1))["status"] == "refused"
        assert session.state["approximate"] == 5


def test_the_total_is_saved_before_the_record():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        seen = []
        real = H.append_chest_correction

        def spy(*args):
            seen.append(on_disk(tmp)["approximate"])
            return real(*args)

        with patch.object(H, "append_chest_correction", spy):
            session.apply_correction(request(1))
        assert seen == [6]


def test_a_correction_is_not_read_as_lost_chests_after_a_crash():
    with tempfile.TemporaryDirectory() as tmp:
        session, cfg = session_in(tmp)
        session.history = H.HistoryWriter(history(tmp), [].append, run_id="dead")
        session.history.start_run("file", "0.3.0", 15, ["en"], 2, 5, 0, 60)
        session.apply_correction(request(1))                              # then the process dies
        H.HistoryWriter(history(tmp), [].append).start_run("file", "0.3.0", 15, ["en"], 2, 6, 0, 60)
        assert H.read(history(tmp)).gaps == []


def test_corrupt_correction_rows_are_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        session.apply_correction(request(1, "manual", "abc"))
        path = history(tmp) / H.CHESTS
        H._append_line(path, b'{"kind":"chest_correction","schema":1,"id":"bad","delta":7}\n')
        H._append_line(path, b'{"kind":"chest_correction_undone","schema":1,"id":"z","undoes":"missing"}\n')
        H._append_line(path, b"{broken\n")
        assert [row["id"] for row in corrections(tmp)] == ["abc"]


def test_correction_rows_do_not_disturb_reading_chests():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_in(tmp)
        session.apply_correction(request(1))
        read = H.read(history(tmp))
        assert read.chests == [] and read.bad_lines == 0 and len(read.chest_corrections) == 1


# ------------------------------------------------------------------ profiles

def test_profiles_keep_their_own_corrections():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "state" / "chest_state.json"
        config = Path(tmp) / "c.toml"
        config.write_text(f'[state]\npath = "{base.as_posix()}"\nobs_dir = "{(Path(tmp) / "o").as_posix()}"\n[logging]\ndir = "{(Path(tmp) / "l").as_posix()}"\n', encoding="utf-8")
        entry = profiles.create(base, "Alice", activate=False)
        first, _, _ = settings.load_config(config)
        profiles.apply(first, "Alice")
        session = C.CounterSession(first)
        session.apply_correction(request(1, "manual", "alice-1"))
        second, _, _ = settings.load_config(config)
        profiles.apply(second)
        other = C.CounterSession(second)
        assert other.state["approximate"] == 0 and [c["id"] for c in H.read_chest_corrections(profiles.history_folder(base, entry["id"]))] == ["alice-1"]
        assert H.read_chest_corrections(profiles.history_folder(base, "default")) == []


# ------------------------------------------------------------------ the running counter

def run_worker(tmp, lines, mode="off", items=None, source=None):
    """The real worker with `correct` lines already waiting on its stdin. -> (state on disk, messages)."""
    read, write = os.pipe()
    stdin = sys.stdin
    buffer = io.StringIO()
    try:
        for line in lines:
            os.write(write, (line + "\n").encode())
        sys.stdin = os.fdopen(read, "r")
        with T.scripted_pipeline(items or T.scripted_frames()), contextlib.redirect_stdout(buffer):
            assert C.main(["live", "--gui", "--source", "file", "--reset", *T.folders(tmp), "--match-mode", mode]) == 0
    finally:
        sys.stdin = stdin
        CONSOLE.machine, paths.HIDE_CHILD_CONSOLES = False, False
        os.close(write)
    return on_disk(tmp), [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]


def test_the_worker_applies_corrections_on_top_of_counted_chests():
    with tempfile.TemporaryDirectory() as tmp:
        state, messages = run_worker(tmp, ['correct {"id": "a", "delta": 1, "reason": "not_visible"}', 'correct {"id": "b", "delta": 1}'])
        assert (state["certain"], state["approximate"]) == (2, 5)         # 2 / 3 counted, plus 2 by hand
        assert [m["status"] for m in messages if m["type"] == "correction"] == ["applied", "applied"]
        assert [c["reason"] for c in corrections(tmp)] == ["not_visible", "manual"]
        assert "5" in (Path(tmp) / "o" / "approximate_chests.txt").read_text(encoding="utf-8")


def test_corrections_apply_while_counting_not_only_at_the_end():
    with tempfile.TemporaryDirectory() as tmp:
        _, messages = run_worker(tmp, ['correct {"id": "a", "delta": 1}'])
        kinds = [m["type"] for m in messages]
        assert kinds.index("correction") < kinds.index("event"), kinds    # waiting at the start, so applied before the first chest


def test_the_worker_ignores_broken_commands():
    with tempfile.TemporaryDirectory() as tmp:
        state, messages = run_worker(tmp, ["correct not json", "correct [1,2]", 'correct {"id": "a", "delta": 9}'])
        assert state["approximate"] == 3 and [m["status"] for m in messages if m["type"] == "correction"] == ["refused"]


def test_a_correction_just_before_stopping_is_not_lost():
    class LateLine(T.ScriptedSource):
        write_end = None

        def frames(self):
            yield from super().frames()
            os.write(LateLine.write_end, b'correct {"id": "late", "delta": 1}\n')
            time.sleep(0.3)

    with tempfile.TemporaryDirectory() as tmp, patch.object(T, "ScriptedSource", LateLine):
        read, write = os.pipe()
        LateLine.write_end = write
        stdin = sys.stdin
        try:
            sys.stdin = os.fdopen(read, "r")
            with T.scripted_pipeline(T.scripted_frames()), contextlib.redirect_stdout(io.StringIO()):
                assert C.main(["live", "--gui", "--source", "file", "--reset", *T.folders(tmp), "--match-mode", "off"]) == 0
        finally:
            sys.stdin = stdin
            CONSOLE.machine, paths.HIDE_CHILD_CONSOLES = False, False
            os.close(write)
        assert on_disk(tmp)["approximate"] == 4


def test_tracking_on_or_off_gives_the_same_totals():
    results = {}
    for mode in ("off", "on"):
        with tempfile.TemporaryDirectory() as tmp:
            state, _ = run_worker(tmp, ['correct {"id": "a", "delta": 1}'], mode=mode)
            results[mode] = (state["certain"], state["approximate"])
    assert results["off"] == results["on"] == (2, 4)


# ------------------------------------------------------------------ the Dashboard

def seed(w, certain=2, approx=5):
    base = w.dir / "state" / "chest_state.json"
    base.parent.mkdir(parents=True, exist_ok=True)
    state = C.fresh_state()
    state.update(certain=certain, approximate=approx)
    base.write_text(json.dumps(state), encoding="utf-8")
    w.win.read_state(force=True)
    return base


def ui_history(w):
    return w.dir / "state" / "history" / "default"


def test_the_buttons_are_on_the_overview():
    with G.window() as w:
        from fortnite_chest_counter.gui import app
        d = w.win.dashboard
        for widget in (d.plus, d.minus, d.correction_row):
            assert d.views.widget(app.OVERVIEW_VIEW).isAncestorOf(widget)
        assert d.correction_row.isHidden()


def test_plus_one_when_not_counting():
    with G.window() as w:
        base = seed(w)
        d = w.win.dashboard
        d.plus.click()
        assert json.loads(base.read_text(encoding="utf-8"))["approximate"] == 6 and w.win.counts == (2, 6)
        assert not d.correction_row.isHidden() and d.correction_text.text() == "Detector 5   ·   Manual +1   ·   Total 6"
        assert d.types.text() == "not classified 6", d.types.text()       # the existing line that holds everything the detector did not classify


def test_minus_is_disabled_when_approx_equals_certain():
    with G.window() as w:
        seed(w, 3, 3)
        d = w.win.dashboard
        assert not d.minus.isEnabled() and "cannot go below CERTAIN" in d.minus.toolTip() and d.plus.isEnabled()


def test_minus_one_offers_its_own_reasons():
    with G.window() as w:
        seed(w)
        d = w.win.dashboard
        d.minus.click()
        assert d.correction_text.text() == "Detector 5   ·   Manual -1   ·   Total 4"
        assert [d.correction_reason.itemData(i) for i in range(d.correction_reason.count())] == ["manual", "false_positive"]


def test_plus_one_offers_the_broken_chest_reason():
    with G.window() as w:
        seed(w)
        d = w.win.dashboard
        d.plus.click()
        items = [d.correction_reason.itemData(i) for i in range(d.correction_reason.count())]
        assert items == ["manual", "not_visible", "missed"] and "broken chest" in d.correction_reason.itemText(1)


def test_undo_from_the_dashboard():
    with G.window() as w:
        base = seed(w)
        d = w.win.dashboard
        d.plus.click()
        d.correction_undo.click()
        assert json.loads(base.read_text(encoding="utf-8"))["approximate"] == 5 and d.correction_row.isHidden()
        assert H.read_chest_corrections(ui_history(w))[0]["undone"] is True


def test_undo_walks_back_through_corrections():
    with G.window() as w:
        seed(w)
        d = w.win.dashboard
        d.plus.click()
        d.minus.click()
        d.correction_undo.click()
        assert w.win.counts == (2, 6) and w.win.last_correction["delta"] == 1 and not d.correction_row.isHidden()


def test_choosing_a_reason_is_saved_and_remembered():
    with G.window() as w:
        seed(w)
        d = w.win.dashboard
        d.plus.click()
        d.correction_reason.setCurrentIndex(d.correction_reason.findData("not_visible"))
        w.win.correction_reason_chosen()
        assert H.read_chest_corrections(ui_history(w))[0]["reason"] == "not_visible"
        d.plus.click()
        assert H.read_chest_corrections(ui_history(w))[1]["reason"] == "not_visible"


def test_while_counting_the_worker_makes_the_change():
    with G.window() as w:
        base = seed(w)
        before = base.read_bytes()
        w.win.worker.is_running = True
        w.win.set_mode("counting")
        sent = []
        w.win.worker.send = lambda line: (sent.append(line), True)[1]
        w.win.dashboard.plus.click()
        assert base.read_bytes() == before and len(sent) == 1 and sent[0].startswith("correct ")
        request_sent = json.loads(sent[0][len("correct "):])
        assert request_sent["delta"] == 1 and request_sent["reason"] == "manual" and request_sent["id"]


def test_the_buttons_wait_while_stopping():
    with G.window() as w:
        seed(w)
        w.win.worker.is_running = True
        w.win.set_mode("stopping")
        assert not w.win.dashboard.plus.isEnabled() and not w.win.dashboard.minus.isEnabled()


def test_a_refused_correction_is_logged():
    with G.window() as w:
        w.win.handle({"type": "correction", "status": "refused", "message": "no room"})
        assert "no room" in w.win.dashboard.log.toPlainText()


def test_a_reset_clears_the_line():
    with G.window() as w:
        seed(w)
        d = w.win.dashboard
        d.plus.click()
        w.win._set(0, 0, "reset")
        assert d.correction_row.isHidden() and w.win.last_correction is None


def test_each_profile_shows_its_own_line():
    with G.window() as w:
        base = seed(w)
        entry = profiles.create(base, "Alice", activate=False)
        w.win.fill_profiles()
        d = w.win.dashboard
        d.plus.click()
        assert not d.correction_row.isHidden()
        d.profile.setCurrentIndex(d.profile.findData(entry["id"]))
        w.win.switch_profile(d.profile.currentIndex())
        assert d.correction_row.isHidden() and w.win.last_correction is None


def test_the_line_comes_back_after_reopening():
    with G.window() as w:
        seed(w)
        w.win.dashboard.plus.click()
        w.win.dashboard.correction_row.hide()
        w.win.last_correction = None
        w.win.read_state(force=True)
        assert not w.win.dashboard.correction_row.isHidden() and w.win.last_correction is not None


# ------------------------------------------------------------------ Not a match

def page_with_matches(w):
    MA.worked_example(MA.history_folder(w))
    page = w.win.analytics
    page.refresh()
    MA.settle(w)
    return page


def action(page, row):
    return page.table.cellWidget(row, len(page.COLUMNS) - 1)


def test_every_recent_match_offers_the_action():
    with G.window() as w:
        page = page_with_matches(w)
        assert [action(page, r).text() for r in range(page.table.rowCount())] == ["Not a match"] * 4


def test_not_a_match_updates_the_statistics():
    with G.window() as w:
        page = page_with_matches(w)
        action(page, 3).click()
        MA.settle(w)
        assert page.matches.value.text() == "3" and page.matches.sub.text() == "1 complete · 1 partial · 1 unconfirmed" and page.table.item(3, 4).text() == "Not a match" and action(page, 3).text() == "Restore"
        assert "marked as not a match" in page.notes.text() and page.table.rowCount() == 4


def test_restore_puts_it_back_exactly():
    with G.window() as w:
        page = page_with_matches(w)
        before = (page.matches.value.text(), page.observed.value.text(), page.complete_rate.value.text())
        action(page, 3).click()
        MA.settle(w)
        action(page, 3).click()
        MA.settle(w)
        assert (page.matches.value.text(), page.observed.value.text(), page.complete_rate.value.text()) == before and page.table.item(3, 4).text() == "Complete"


def test_not_a_match_deletes_nothing():
    with G.window() as w:
        page = page_with_matches(w)
        f = MA.history_folder(w)
        matches, chests = (f / H.MATCHES).read_bytes(), (f / H.CHESTS).read_bytes()
        action(page, 3).click()
        MA.settle(w)
        assert (f / H.MATCHES).read_bytes().startswith(matches) and (f / H.CHESTS).read_bytes() == chests


def test_not_a_match_leaves_the_counter_alone():
    with G.window() as w:
        base = seed(w)
        before = base.read_bytes()
        page = page_with_matches(w)
        action(page, 3).click()
        MA.settle(w)
        assert base.read_bytes() == before and w.win.counts == (2, 5)


def test_replaced_buttons_do_not_stay_on_screen():
    with G.window() as w:
        page = page_with_matches(w)
        old = [action(page, row) for row in range(page.table.rowCount())]
        page.refresh()
        MA.settle(w)
        assert all(button.isHidden() for button in old) and all(action(page, row) not in old for row in range(page.table.rowCount()))


def fits(page):
    """No column is narrower than its own heading, its widest text, or its buttons."""
    table, header, last = page.table, page.table.horizontalHeader(), len(page.COLUMNS) - 1
    for column in range(last):
        assert table.columnWidth(column) >= max(header.sectionSizeHint(column), table.sizeHintForColumn(column)), (column, table.columnWidth(column))
    assert all(table.columnWidth(last) >= action(page, row).sizeHint().width() for row in range(table.rowCount())), table.columnWidth(last)


def test_the_longest_labels_are_not_cut_off():
    with G.window() as w:
        page = page_with_matches(w)
        for width in (1400, 700, 300):                          # wide, the minimum window, and far narrower than that
            page.table.resize(width, 300)
            w.qt.processEvents()
            page._fit_columns()
            fits(page)


def test_a_wide_table_uses_its_width():
    with G.window() as w:
        page = page_with_matches(w)
        page.table.resize(1600, 300)
        w.qt.processEvents()
        page._fit_columns()
        total = sum(page.table.columnWidth(column) for column in range(len(page.COLUMNS)))
        assert total >= page.table.viewport().width() - len(page.COLUMNS), (total, page.table.viewport().width())


def test_a_narrow_table_scrolls_instead_of_cutting_off():
    from PySide6.QtWidgets import QAbstractItemView
    with G.window() as w:
        page = page_with_matches(w)
        assert page.table.horizontalScrollMode() == QAbstractItemView.ScrollPerPixel
        page.table.resize(300, 300)
        w.qt.processEvents()
        page._fit_columns()
        assert sum(page.table.columnWidth(column) for column in range(len(page.COLUMNS))) > page.table.viewport().width()


def test_resizing_the_window_fits_the_columns_again():
    from PySide6.QtCore import QEvent, QSize
    from PySide6.QtGui import QResizeEvent
    with G.window() as w:
        page = page_with_matches(w)
        calls = []
        real = page._fit_columns
        page._fit_columns = lambda: (calls.append(1), real())
        w.qt.sendEvent(page.table.viewport(), QResizeEvent(QSize(900, 300), QSize(800, 300)))
        assert calls, "a resize must fit the columns again"


def test_a_failed_save_is_explained():
    with G.window() as w:
        page = page_with_matches(w)
        with patch.object(H, "correct_match", side_effect=OSError("locked")):
            action(page, 3).click()
        assert w.errors and "could not be saved" in w.errors[0] and page.matches.value.text() == "4"


def test_the_page_says_manual_corrections_are_not_included():
    with G.window() as w:
        seed(w)
        w.win.dashboard.plus.click()
        page = w.win.analytics
        page.refresh()
        MA.settle(w)
        assert "Manual chest corrections are not part of these statistics (+1, −0)" in page.notes.text()


def test_statistics_ignore_manual_corrections():
    with MA.folder() as f:
        MA.worked_example(f)
        H.append_chest_correction(f, "x", None, 1, "not_visible", "t", 6, 10, 9)
        s = A.load(f)
        assert (s.certain_chests, s.approx_chests, s.credited_approx) == (6, 9, 6) and s.manual_added == 1


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
    print(f"{len(tests) - failed}/{len(tests)} correction checks passed")
    sys.exit(1 if failed else 0)
