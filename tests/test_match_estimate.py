"""
The end-of-match chest estimate (match_estimate.py): when a complete match ends, a chosen share of the chests detected in it is added to
APPROX as estimated broken chests, minus the Broken chest +1s already made for it. Exactly once per match, never CERTAIN, never for a
match cut off by Stop, kept apart from your own +1s everywhere (counter, history, Analytics, the app), and taken back by Undo like a +1.
No video is decoded here.

Run:   python tests/test_match_estimate.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))                                     # run without installing
sys.path.insert(0, str(ROOT / "tests"))

import io
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fortnite_chest_counter import counter as C
from fortnite_chest_counter import match_analytics as A
from fortnite_chest_counter import match_estimate as E
from fortnite_chest_counter import match_history as H
from fortnite_chest_counter import match_tracker as T
from fortnite_chest_counter import settings

import test_corrections as TC
import test_match_analytics as MA
import test_update_gui as G

RUN = "run-1"


def complete(number=3, approx=100, certain=40, **extra):
    return {"match_number": number, "completion": "complete", "english_confirmed": True, "approx": approx, "certain": certain,
            "ended_by": "victory", **extra}


def session_with_history(tmp, certain=40, approx=1000):
    session, cfg = TC.session_in(tmp, certain=certain, approx=approx)
    session.history = H.HistoryWriter(TC.history(tmp), [].append, run_id=RUN)
    session.history.start_run("file", "0.6.0", 15, ["en"], certain, approx, 0, 60)
    return session, cfg


def estimates(tmp):
    return [c for c in TC.corrections(tmp) if c.get("estimate")]


# ------------------------------------------------------------------ the arithmetic

def test_the_rounding_table():
    for base, expected in ((0, 0), (1, 0), (2, 0), (3, 1), (7, 1), (8, 2), (58, 12), (100, 20), (150, 30)):
        assert E.amount(base, 0, 0, 20) == (base, expected, expected), base
    assert E.amount(5, 0, 0, 10)[2] == 1, "half rounds up"
    assert E.amount(7, 0, 0, 100)[2] == 7 and E.amount(7, 0, 0, 1)[2] == 0


def test_your_broken_chest_plus_ones_are_topped_up_not_counted_twice():
    assert E.amount(60, 0, 5, 20) == (60, 12, 7)
    assert E.amount(60, 0, 12, 20) == (60, 12, 0)
    assert E.amount(60, 0, 15, 20) == (60, 12, 0), "never below 0"


def test_your_minus_ones_are_no_chests_to_estimate_from():
    assert E.amount(60, 10, 0, 20) == (50, 10, 10)
    assert E.amount(3, 9, 0, 20) == (0, 0, 0)


def test_a_confirmed_match_qualifies_when_complete_or_partial_with_your_ending_seen():
    from fortnite_chest_counter import match_state as S
    assert set(E.PLAYER_ENDINGS) == {S.PLACED, S.VICTORY}
    assert E.eligible(complete())
    for ending in E.PLAYER_ENDINGS:                              # a short video gap made it partial: the detected chests still count
        assert E.eligible(complete(completion="partial", ended_by=ending)), ending
    for match in ([complete(completion="partial", ended_by=e) for e in (S.STOPPED, S.LOST, S.DISCONTINUITY, S.LEFT_OR_UNKNOWN, None)]
                  + [complete(completion="unconfirmed"), complete(english_confirmed=False), complete(english_confirmed=None), {}, None]):
        assert not E.eligible(match), match
    assert E.valid_percent(20) and not E.valid_percent(0) and not E.valid_percent(101) and not E.valid_percent(True) and not E.valid_percent(20.0)


# ------------------------------------------------------------------ the counter applies it

def test_100_detected_at_20_percent_adds_20_to_approx_only():
    with tempfile.TemporaryDirectory() as tmp:
        session, cfg = session_with_history(tmp)
        types_before = json.dumps(session.state["types"])
        result = session.apply_estimate(complete(approx=100), 20)
        assert result["status"] == "applied" and result["delta"] == 20 and result["base"] == 100 and result["recorded"] is True
        assert (session.state["certain"], session.state["approximate"]) == (40, 1020)
        disk = TC.on_disk(tmp)
        assert (disk["certain"], disk["approximate"]) == (40, 1020) and json.dumps(disk["types"]) == types_before
        assert "1,020" in (Path(tmp) / "o" / "approximate_chests.txt").read_text(encoding="utf-8") or \
               "1020" in (Path(tmp) / "o" / "approximate_chests.txt").read_text(encoding="utf-8"), "the OBS text shows the new APPROX"
        [row] = estimates(tmp)
        assert (row["id"], row["delta"], row["base"], row["percent"], row["match_number"], row["run_id"]) == (E.estimate_id(RUN, 3), 20, 100, 20, 3, RUN)
        totals = H.correction_totals(TC.corrections(tmp), C.counter_token(session.state))
        assert (totals["net"], totals["estimated"], totals["added"], totals["removed"]) == (20, 20, 0, 0)
        assert row["detector_approximate"] == 1000 == session.state["approximate"] - totals["net"], "the Overview's Detector figure stays right"


def test_150_detected_adds_30():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_with_history(tmp)
        assert session.apply_estimate(complete(approx=150), 20)["delta"] == 30 and session.state["approximate"] == 1030


def test_never_twice_for_the_same_match():
    with tempfile.TemporaryDirectory() as tmp:
        session, cfg = session_with_history(tmp)
        assert session.apply_estimate(complete(approx=100), 20)["status"] == "applied"
        for _ in range(3):                                                     # offered again, resent
            assert session.apply_estimate(complete(approx=140), 25)["status"] == "already"
        again = C.CounterSession(cfg)                                          # a fresh session of the same run reads the history
        again.history = H.HistoryWriter(TC.history(tmp), [].append, run_id=RUN)
        assert again.apply_estimate(complete(approx=100), 20)["status"] == "already"
        assert session.state["approximate"] == 1020 and len(estimates(tmp)) == 1


def test_a_new_run_never_reaches_back_to_an_earlier_runs_match():
    """Match numbers start again in every run, so match 3 of the next run is a different match with its own estimate; the earlier one stays."""
    with tempfile.TemporaryDirectory() as tmp:
        session, cfg = session_with_history(tmp)
        session.apply_estimate(complete(approx=100), 20)
        later = C.CounterSession(cfg)
        later.history = H.HistoryWriter(TC.history(tmp), [].append, run_id="run-2")
        assert later.apply_estimate(complete(approx=50), 20)["delta"] == 10
        assert sorted(e["run_id"] for e in estimates(tmp)) == [RUN, "run-2"] and later.state["approximate"] == 1030


def test_a_partial_match_that_ended_with_placed_gets_its_estimate_once():
    """A short video gap makes a match partial; with your Placed seen it still gets 20 % of what was detected - once, CERTAIN untouched."""
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_with_history(tmp)
        certain = session.state["certain"]
        result = session.apply_estimate(complete(approx=54, completion="partial", ended_by="placed", discontinuity=True), 20)
        assert result["status"] == "applied" and result["delta"] == 11
        assert session.state["approximate"] == 1011 and session.state["certain"] == certain
        assert session.apply_estimate(complete(approx=54, completion="partial", ended_by="placed"), 20)["status"] != "applied"
        assert [e["delta"] for e in estimates(tmp)] == [11] and estimates(tmp)[0]["percent"] == 20


def test_partial_unconfirmed_or_without_history_nothing_happens():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_with_history(tmp)
        for match in (complete(completion="partial", ended_by="stopped"), complete(completion="unconfirmed"), complete(english_confirmed=False)):
            assert session.apply_estimate(match, 20) is None
        assert session.apply_estimate(complete(), 0) is None and session.apply_estimate(complete(), 101) is None
        session.history = None                                                 # match tracking not "on"
        assert session.apply_estimate(complete(), 20) is None
        assert session.state["approximate"] == 1000 and estimates(tmp) == []


def test_nothing_to_add_writes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_with_history(tmp)
        result = session.apply_estimate(complete(approx=2), 20)
        assert result["status"] == "none" and result["delta"] == 0 and session.state["approximate"] == 1000 and estimates(tmp) == []
        assert session.apply_estimate(complete(approx=100), 20)["status"] == "already", "decided once, even when it was 0"


def test_broken_chest_plus_ones_for_the_match_are_topped_up_and_stay_yours():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_with_history(tmp)
        for _ in range(5):
            session.apply_correction({**TC.request(1, "broken_chest"), "match_number": 3})
        session.apply_correction({**TC.request(1, "broken_chest"), "match_number": 4})          # another match's: not counted here
        session.apply_correction({**TC.request(-1, "false_positive"), "match_number": 3})
        result = session.apply_estimate(complete(approx=61), 20)
        assert (result["base"], result["target"], result["broken_logged"], result["delta"]) == (60, 12, 5, 7)
        assert session.state["approximate"] == 1000 + 6 - 1 + 7 and session.state["certain"] == 40
        everything = TC.corrections(tmp)
        assert H.corrections_by_match(everything)[RUN, 3] == [5, 1, 5], "your +1s and -1s are untouched by the estimate"
        assert H.estimates_by_match(everything) == {(RUN, 3): 7}
        totals = H.correction_totals(everything)
        assert (totals["added"], totals["removed"], totals["broken_chests"], totals["estimated"], totals["unknown"]) == (6, 1, 6, 7, 0)


def test_undo_takes_an_estimate_back_once_and_never_below_certain():
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_with_history(tmp, certain=40, approx=60)
        estimate_id = session.apply_estimate(complete(approx=60), 20)["id"]
        undo = session.apply_correction({"id": "undo-1", "undoes": estimate_id})
        assert undo["status"] == "applied" and undo["delta"] == -12 and undo["reason"] == H.ESTIMATED and undo["match_number"] == 3
        assert session.state["approximate"] == 60 and H.estimates_by_match(TC.corrections(tmp)) == {}
        assert session.apply_correction({"id": "undo-2", "undoes": estimate_id})["status"] == "already"
        assert session.apply_estimate(complete(approx=60), 20)["status"] == "already", "undone is not a reason to add it again"
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_with_history(tmp, certain=40, approx=60)
        estimate_id = session.apply_estimate(complete(approx=60), 20)["id"]           # APPROX 72
        session.state["certain"] = 65                                                 # CERTAIN rose meanwhile
        assert session.apply_correction({"id": "u", "undoes": estimate_id})["status"] == "refused"
        assert session.state["approximate"] == 72


def test_reset_or_edit_counts_never_recalculates_and_ends_undo():
    with tempfile.TemporaryDirectory() as tmp:
        session, cfg = session_with_history(tmp)
        estimate_id = session.apply_estimate(complete(approx=100), 20)["id"]
        C.set_counts(cfg, 10, 500)                                                    # Edit counts from the app (another program)
        session.sync_external_changes()
        assert (session.state["certain"], session.state["approximate"]) == (10, 500)
        assert session.apply_correction({"id": "u", "undoes": estimate_id})["status"] == "refused"
        assert session.apply_estimate(complete(approx=100), 20)["status"] == "already" and session.state["approximate"] == 500
        assert len(estimates(tmp)) == 1 and estimates(tmp)[0]["delta"] == 20, "the finished match's estimate stays in the history as it was"


def test_the_row_is_invisible_to_versions_before_it():
    """In matches.jsonl, a kind no earlier reader handles: v0.5.1 skips it there without counting a damaged line (in chests.jsonl it would)."""
    with tempfile.TemporaryDirectory() as tmp:
        session, _ = session_with_history(tmp)
        session.apply_estimate(complete(approx=100), 20)
        folder = TC.history(tmp)
        rows = [json.loads(line) for line in (folder / H.MATCHES).read_text(encoding="utf-8").splitlines()]
        assert [r["kind"] for r in rows].count("chest_estimate") == 1
        assert not (folder / H.CHESTS).exists() or "chest_estimate" not in (folder / H.CHESTS).read_text(encoding="utf-8")
        assert "chest_estimate" not in H.CORRECTION_KINDS | H.MATCH_KINDS, "the kinds v0.5.1 reads"
        history = H.read(folder)
        assert history.bad_lines == 0 and [c["delta"] for c in history.chest_corrections if c.get("estimate")] == [20]


# ------------------------------------------------------------------ when: once its late chests are in

def tracker_with(closed_t=100.0, chests=((50.0, True), (98.5, False), (99.0, True), (120.0, True))):
    tracker = T.MatchTracker([].append, print)
    tracker._closed = {"match_number": 3, "completion": "complete", "english_confirmed": True, "ended_by": "victory", "reasons": [],
                       "active_seconds": 90.0, "opened_t": 0.0, "played_from_t": 10.0, "ended_t": 99.5, "closed_t": closed_t, "out_at": None}
    for t, certain in chests:
        tracker._counted.append((t, certain, True))
    return tracker


def test_a_match_settles_ten_seconds_after_it_closed_with_its_late_chests_and_once():
    tracker = tracker_with()
    assert tracker.settled_match(105.0) is None
    settled = tracker.settled_match(T.SETTLE_SECONDS + 100.0)
    assert settled["match_number"] == 3 and (settled["certain"], settled["approx"]) == (2, 3), "the chest finished late (98.5) is in; 120 is after"
    assert tracker.settled_match(500.0) is None and tracker.settled_match(500.0, final=True) is None


def test_stopping_or_the_next_match_settles_it_at_once():
    tracker = tracker_with()
    assert tracker.settled_match(101.0, final=True)["match_number"] == 3
    tracker = tracker_with()
    tracker._machine._match = type("Open", (), {"number": 4})()                     # the next match has opened
    assert tracker.settled_match(101.0)["match_number"] == 3


def test_a_failed_tracker_offers_nothing():
    tracker = tracker_with()
    tracker.failed = True
    assert tracker.settled_match(1000.0, final=True) is None


# ------------------------------------------------------------------ the live loop

class FakeTracker:
    def __init__(self, match):
        self.match, self.calls = match, []

    def settled_match(self, t, final=False):
        self.calls.append((t, final))
        match, self.match = self.match, None
        return match


class FakeSession:
    def __init__(self):
        self.applied, self.announced = [], 0

    def apply_estimate(self, match, percent):
        self.applied.append((match["match_number"], percent))
        return {"status": "applied", "id": "x", "match_number": match["match_number"], "delta": 9, "base": 46, "percent": percent,
                "broken_logged": 0, "estimate": True, "certain": 1, "approx": 2}

    def announce(self):
        self.announced += 1


def test_the_setting_at_the_moment_a_match_settles_counts():
    off = {"enabled": False, "percent": 20, "tracking": True}
    session, tracker = FakeSession(), FakeTracker(complete())
    C._apply_estimate(tracker, session, off, 200.0)
    C._apply_estimate(tracker, session, {**off, "enabled": True}, 201.0)
    assert session.applied == [], "off when it settled: turning it on later does not reach back"
    session, tracker = FakeSession(), FakeTracker(complete())
    C._apply_estimate(tracker, session, {**off, "enabled": True, "percent": 25}, 200.0)
    assert session.applied == [(3, 25)] and session.announced == 1
    C._apply_estimate(None, session, {**off, "enabled": True}, 300.0)                    # no tracking: nothing, no error


def test_settings_come_from_config_then_from_the_app():
    cfg = settings.load_config(None, {})[0]
    assert C._estimate_start(cfg) == {"enabled": False, "percent": 20, "tracking": True}, "off by default, 20 %"
    cfg["chest_estimate"] = {"enabled": True, "percent": 30}
    assert C._estimate_start(cfg)["enabled"] and C._estimate_start(cfg)["percent"] == 30
    cfg["match"]["mode"] = "shadow"
    assert not C._estimate_start(cfg)["enabled"], "needs match history"
    control = C.AppControl(io.StringIO('estimate {"enabled": true, "percent": 25}\nestimate {"enabled": true, "percent": 0}\nestimate nonsense\n'))
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and len(control._estimates) < 2:
        time.sleep(0.01)
    now = C._estimate_settings(control, {"enabled": False, "percent": 20, "tracking": True})
    assert now == {"enabled": True, "percent": 25, "tracking": True}, "an invalid percentage keeps the last good one"
    assert C._estimate_settings(control, now) == now
    off = C._estimate_settings(None, {"enabled": False, "percent": 20, "tracking": False})
    assert off["enabled"] is False


def test_config_validates_the_percentage():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.toml"
        path.write_text("[chest_estimate]\nenabled = true\npercent = 250\n", encoding="utf-8")
        cfg, _, warnings = settings.load_config(path)
        assert cfg["chest_estimate"] == {"enabled": True, "percent": 20} and any("percent" in w for w in warnings)


def test_the_real_live_loop_with_it_on_leaves_a_match_cut_off_by_stop_alone():
    """The scripted run's only match is cut off when the video ends (partial, stopped): on or off, the run counts exactly the same."""
    import test_match_tracker as MT
    results = {}
    for enabled in ("false", "true"):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "c.toml"
            config.write_text(f"[chest_estimate]\nenabled = {enabled}\npercent = 20\n", encoding="utf-8")
            result, log = MT.run_command(tmp, "live", "on", extra=["--config", str(config)])
            history = H.read(next(Path(tmp).rglob("matches.jsonl")).parent)
            assert [(m["completion"], m["ended_by"]) for m in history.matches] == [("partial", "stopped")]
            assert not [c for c in history.chest_corrections if c.get("estimate")] and not [r for r in log if r.get("event") == "chest_estimate"]
            results[enabled] = (result["state"], result["obs"])
    assert results["false"] == results["true"]


def test_at_stop_the_estimate_is_decided_before_the_tracker_closes():
    """close() records the match that Stop cuts off as the last one; a complete match that ended just before must be settled first."""
    source = (ROOT / "src" / "fortnite_chest_counter" / "counter.py").read_text(encoding="utf-8")
    body = source[source.index("def _run_live("):]
    body = body[:body.index("\ndef ", 1)]
    final = body.index("_apply_estimate(tracker, session, _estimate_settings(control, estimate), last_t, final=True)")
    assert final < body.index("tracker.close(stop_reason)") and body.index("tracker.chest(ev)", body.index("finally:")) < final


# ------------------------------------------------------------------ Analytics

def test_analytics_shows_it_in_the_match_and_keeps_it_out_of_rates_unless_asked():
    with MA.folder() as f:
        MA.worked_example(f)                                     # match 1: 3 APPROX credited, 600 s
        H.append_chest_estimate(f, E.estimate_id("run", 1), "run", 2, "t", 6, 11, 9, 1, 3, 50, 0)
        H.append_chest_correction(f, "b", "run", 1, "broken_chest", "t", 6, 12, 9, match_number=1)
        off, on = A.load(f), A.load(f, include_manual=True)
        row = next(m for m in off.recent if m.match_number == 1)
        assert (row.approx, row.estimated, row.manual_added, row.broken_chests) == (6, 2, 1, 1)
        assert off.estimated_chests == 2 and off.manual_added == 1, "the estimate is not one of your +1s"
        assert (off.credited_approx, on.credited_approx) == (6, 9), "rates: like a +1, only when asked"
        assert (row.estimate_percent, row.estimate_base) == (50, 3), "the recorded share and base, never recalculated"


def test_the_matches_table_says_what_the_estimate_added_or_why_it_added_nothing():
    from fortnite_chest_counter.gui import app as App
    row = A.RecentMatch(None, 600, True, 2, 54, False, "complete", False, "Placed", "run", 1, False, None, 0, 0, 0, 600,
                        estimated=11, estimate_percent=20, estimate_base=54, estimate_eligible=True)
    tip = App.estimate_tip(row, True)
    assert "11 estimated broken chests: 20% of the 54 chests detected" in tip and "not detected" in tip
    stopped = A.RecentMatch(None, 600, False, 37, 54, False, "partial", False, "Stopped", "run", 2, False, None, 0, 0, 0, 600)
    assert "Placed or Victory" in App.estimate_tip(stopped, True) and "Stopped" in App.estimate_tip(stopped, True)
    assert App.estimate_tip(stopped, False) == "", "nothing about an estimate that is switched off"
    covered = A.RecentMatch(None, 600, True, 22, 41, False, "complete", False, "Placed", "run", 3, False, None, 8, 0, 8, 600,
                            estimate_eligible=True)
    tip = App.estimate_tip(covered, True)
    assert "+8 manual" in tip and "8 broken" in tip and "already covered it" in tip


# ------------------------------------------------------------------ the app

def test_the_dashboard_setting_saves_at_once_and_reaches_a_running_counter():
    with G.window() as w:
        if not w:
            return
        d, sent = w.win.dashboard, []
        w.win.worker.is_running = True
        w.win.worker.send = lambda line: sent.append(line) or True
        assert not d.estimate_on.isChecked() and d.estimate_percent.value() == 20
        d.estimate_on.setChecked(True)
        d.estimate_percent.setValue(25)
        cfg = settings.load_config(w.dir / "config.toml")[0]
        assert cfg["chest_estimate"] == {"enabled": True, "percent": 25}
        assert [json.loads(line.split(" ", 1)[1]) for line in sent] == [{"enabled": True, "percent": 20}, {"enabled": True, "percent": 25}]
        w.win.worker.is_running = False


def test_the_app_shows_an_applied_estimate_and_its_undo():
    with G.window() as w:
        if not w:
            return
        d = w.win.dashboard
        d.estimate_on.setChecked(True)
        w.win.handle({"type": "estimate", "status": "applied", "id": "estimate:r:3", "match_number": 3, "delta": 9, "base": 46, "percent": 20,
                      "broken_logged": 0, "estimate": True, "recorded": True, "certain": 1, "approx": 2})
        assert d.game_estimate_by_match == {3: 9} and "Match 3: +9 estimated broken chests (20 % of 46 detected)" in d.estimate_note.text()
        d._show_last_match({"match_number": 3, "certain": 1, "approx": 46, "english_confirmed": True, "completion": "complete", "ended_by": "victory",
                            "active_seconds": 600, "reasons": []})
        assert "+9 estimated" in d.game_last.text() and "APPROX 55" in d.game_last.text()
        w.win.correction_done({"status": "applied", "id": "u", "undoes": "estimate:r:3", "delta": -9, "match_number": 3, "reason": H.ESTIMATED})
        assert d.game_estimate_by_match == {3: 0} and d.game_manual_by_match.get(3, [0, 0]) == [0, 0], "an undone estimate is not one of your -1s"


def test_broken_chest_plus_ones_feed_the_preview():
    with G.window() as w:
        if not w:
            return
        d = w.win.dashboard
        d.estimate_on.setChecked(True)
        w.win.correction_done({"status": "applied", "id": "b", "delta": 1, "match_number": 5, "reason": H.BROKEN_CHEST})
        d.show_estimate_note({"match_number": 5, "english_confirmed": True}, {"certain": 10, "approx": 60})
        assert d.game_broken_by_match == {5: 1} and "about +11" in d.estimate_note.text() and "minus your 1 Broken chest" in d.estimate_note.text()
        d.estimate_on.setChecked(False)
        assert not d.estimate_note.isVisibleTo(d) and not d.estimate_percent.isEnabled()


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
    print(f"{len(tests) - failed}/{len(tests)} end-of-match estimate checks passed")
    sys.exit(1 if failed else 0)
