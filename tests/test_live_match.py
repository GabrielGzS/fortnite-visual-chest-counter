"""
The current match on screen (v0.3.0, M9F): its own chests and rate, kept apart from the lifetime totals; the one live preview; match tracking on by
default without overriding anyone's choice; the chest type in the log; and the per-match rate in Analytics.

Run:   python tests/test_live_match.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))                                     # run without installing
sys.path.insert(0, str(ROOT / "tests"))

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import test_match_analytics as MA
import test_match_recording as MR
import test_match_state as M2
import test_match_tracker as T
import test_match_ui as U
import test_update_gui as G
from fortnite_chest_counter import console as CON
from fortnite_chest_counter import match_history as H
from fortnite_chest_counter import settings
from fortnite_chest_counter.detection import chest_types

HP = M2.HP
DASH = "—"


def tracker():
    from fortnite_chest_counter import match_tracker
    return match_tracker


def analytics():
    from fortnite_chest_counter import match_analytics
    return match_analytics


def ui():
    from fortnite_chest_counter.gui import app
    return app


def console():
    from fortnite_chest_counter import console as module
    return module


class Live(T.Rig):
    """A tracker that remembers each status it sent the app."""

    def __init__(self, **options):
        self.seen = []
        options.setdefault("status", lambda **fields: self.seen.append(fields))
        super().__init__(**options)

    def counted(self, t, certain=True):
        self.tracker.chest(T.chest_event(t, certain=certain))
        return self

    @property
    def latest(self):
        return self.seen[-1]


def in_match():
    return M2.start_match(Live())


# ------------------------------------------------------------------ the tracker's live numbers

def test_a_match_starts_at_zero_chests():
    rig = in_match().show(1, health=HP)
    assert rig.latest["chests"] == {"certain": 0, "approx": 0}, rig.latest["chests"]


def test_no_match_means_no_numbers():
    rig = Live().show(3, "lobby_menu")
    assert rig.latest["match"] is None and rig.latest["chests"] is None


def test_certain_and_approx_are_counted_apart():
    rig = in_match().show(2, health=HP)
    rig.counted(rig.t - 1).counted(rig.t - 1, certain=False)
    rig.show(1, health=HP)
    assert rig.latest["chests"] == {"certain": 1, "approx": 2}, rig.latest["chests"]


def test_a_rejected_candidate_is_not_counted():
    rig = in_match().show(2, health=HP)
    rig.tracker.chest({"time": rig.t - 1, "certain_counted": False, "approx_counted": False, "popup_template": "en:CHEST"})
    rig.show(1, health=HP)
    assert rig.latest["chests"] == {"certain": 0, "approx": 0}


def test_a_chest_before_play_began_is_not_this_matchs():
    rig = Live().show(5, "lobby_menu").show(8, "connecting").show(20, "waiting_for_players", health=HP)
    rig.counted(rig.t - 2)                                                  # on the waiting island
    rig.show(10, "bus_launching", health=HP).show(6).show(3, health=HP)
    assert rig.latest["chests"]["approx"] == 0, rig.latest["chests"]


def test_a_chest_finishing_late_still_counts_by_its_own_time():
    rig = in_match().show(30, health=HP)
    rig.counted(rig.t - 12)                                                 # the detector finished it late
    rig.show(1, health=HP)
    assert rig.latest["chests"]["approx"] == 1


def test_after_elimination_chests_are_not_this_players():
    rig = in_match().show(20, health=HP).show(3, "spectating", health=HP)
    rig.counted(rig.t - 1)
    rig.show(1, "spectating", health=HP)
    assert rig.latest["chests"]["approx"] == 0, rig.latest["chests"]


def test_a_new_match_starts_again_from_zero():
    rig = in_match().show(30, health=HP)
    rig.counted(rig.t - 1).show(2, health=HP)
    assert rig.latest["chests"]["approx"] == 1
    rig.show(6, "you_placed").show(4, "connecting")
    M2.start_match(rig).show(3, health=HP)
    assert rig.latest["match"]["match_number"] == 2 and rig.latest["chests"] == {"certain": 0, "approx": 0}, rig.latest


def test_the_finished_match_keeps_its_numbers():
    rig = in_match().show(30, health=HP)
    rig.counted(rig.t - 1).counted(rig.t - 1, certain=False).show(6, "you_placed").show(4, "connecting").show(2, "lobby_menu")
    last = rig.latest["last_match"]
    assert (last["certain"], last["approx"], last["completion"], last["ended_by"]) == (1, 2, "complete", "placed"), last
    assert rig.latest["match"] is None


def test_a_chest_finishing_after_the_match_closed_still_joins_it():
    rig = in_match().show(30, health=HP)
    during = rig.t - 1
    rig.show(6, "lobby_menu")
    assert rig.latest["last_match"]["approx"] == 0
    rig.counted(during).show(1, "lobby_menu")
    assert rig.latest["last_match"]["approx"] == 1, rig.latest["last_match"]


def test_a_chest_after_the_match_closed_is_not_its():
    rig = in_match().show(30, health=HP).show(6, "lobby_menu")
    rig.counted(rig.t - 1).show(1, "lobby_menu")                            # in the lobby, after the record closed
    assert rig.latest["last_match"]["approx"] == 0, rig.latest["last_match"]


def test_chests_after_being_out_do_not_join_the_finished_match():
    """Out with no YOU PLACED, so the moment comes only from the state change: what the history's rule also uses."""
    rig = in_match().show(20, health=HP).show(5, "spectating", health=HP)
    rig.counted(rig.t - 1).show(6, "lobby_menu")
    last = rig.latest["last_match"]
    assert last["ended_by"] == "left_or_unknown" and last["approx"] == 0, last


def test_the_tracker_never_changes_the_event():
    ev = T.chest_event(5.0)
    before = dict(ev)
    Live().tracker.chest(ev)
    assert ev == before


def test_counts_do_not_depend_on_the_counter_at_all():
    """Reset, Edit counts and manual corrections all change the counter. None of them reach the tracker: only finished chests do."""
    source = (ROOT / "src/fortnite_chest_counter/match_tracker.py").read_text(encoding="utf-8")
    assert "certain_total" not in source and "approximate_total" not in source and "apply_correction" not in source


def test_live_numbers_equal_the_history_after_the_match():
    """The one rule: what the app showed live is what Analytics will say."""
    with MR.folder() as f:
        seen = []
        rig = MR.Recording(f)
        rig.tracker._status = lambda **fields: seen.append(fields)
        M2.start_match(rig)
        chests = []
        early = rig.t - 3
        chests.append(early)
        for _ in range(4):
            rig.show(10, health=HP)
            chests.append(rig.t - 2)
        rig.show(6, "you_placed", health=HP)
        chests.append(rig.t - 1)                                            # after the ending: must not count
        for number, t in enumerate(chests, 1):
            rig.add_chest(t)
            rig.tracker.chest(T.chest_event(t))
        rig.show(4, "connecting").show(3, "lobby_menu").end()
        credited = [c for c in H.attribute(rig.stored()) if c["credited"]]
        last = seen[-1]["last_match"]
        assert last["approx"] == len(credited) and last["certain"] == sum(c["certain_counted"] for c in credited), (last, len(credited))
        assert 0 < len(credited) < len(chests), "the example must include chests on both sides of the rule"


def test_back_to_back_matches_share_no_chest():
    with MR.folder() as f:
        rig = MR.Recording(f)
        seen = []
        rig.tracker._status = lambda **fields: seen.append(fields)
        totals = []
        for _ in range(2):
            M2.start_match(rig).show(20, health=HP)
            t = rig.t - 2
            rig.add_chest(t)
            rig.tracker.chest(T.chest_event(t))
            rig.show(6, "you_placed", health=HP).show(4, "connecting").show(3, "lobby_menu")
            totals.append(seen[-1]["last_match"]["approx"])
        rig.end()
        matches = rig.stored().matches
        assert totals == [1, 1] and len(matches) == 2 and matches[0]["closed_t"] <= matches[1]["opened_t"], (totals, matches)


# ------------------------------------------------------------------ one match's rate

def test_the_rate_uses_active_play():
    rate = analytics().match_rate(23, 28, 319.4)
    assert abs(rate.approx_per_minute - 28 / (319.4 / 60)) < 1e-9 and abs(rate.certain_per_minute - 23 / (319.4 / 60)) < 1e-9


def test_no_rate_in_the_first_minute():
    assert analytics().match_rate(5, 5, 59.9) is None and analytics().match_rate(5, 5, 60.0) is not None


def test_an_unknown_time_gives_no_rate():
    for active in (None, "x", float("nan")):
        assert analytics().match_rate(1, 1, active) is None, active


def test_zero_chests_over_real_play_is_a_real_zero():
    assert analytics().match_rate(0, 0, 120).approx_per_minute == 0


# ------------------------------------------------------------------ how a match ended

def ending(reason, ended_by="left_or_unknown"):
    return analytics().ending_text({"ended_by": ended_by, "reasons": ["started: countdown ended", reason]})


def test_leaving_says_where_play_went():
    assert ending("menu_seen") == "Returned to lobby" and ending("connecting_seen") == "Left the match" and ending("next match countdown seen") == "Next match began"


def test_leaving_never_claims_why():
    for text in analytics().LEFT_ENDINGS.values():
        for claim in ("quit", "disconnect", "surrender", "eliminat", "gave up"):
            assert claim not in text.lower(), text


def test_a_seen_ending_is_not_relabelled():
    assert ending("connecting_seen", "placed") == "Placed" and ending("connecting_seen", "victory") == "Victory Royale"


def test_an_unknown_reason_keeps_the_careful_label():
    assert ending("something else") == "Left or not seen"


def test_leaving_stays_partial():
    """No ending on screen means not complete, however much of the match was seen."""
    s = M2.played_match().show(4, "connecting").finish()
    assert s.records[0].completion == M2.S.PARTIAL and s.records[0].ended_by == M2.S.LEFT_OR_UNKNOWN


# ------------------------------------------------------------------ recent matches

def recent(f):
    return analytics().summarize(H.read(f, only=analytics().READ_KINDS)).recent


def test_each_recent_match_has_its_own_rate():
    with MR.folder() as f:
        MA.worked_example(f)
        by_quality = recent(f)
        complete = [m for m in by_quality if m.quality == "complete"]
        assert sorted(round(m.rate.approx_per_minute, 2) for m in complete) == [0.2, 0.3], [m.rate for m in complete]
        partial = next(m for m in by_quality if m.quality == "partial")
        assert round(partial.rate.approx_per_minute, 2) == 0.5


def test_an_unconfirmed_match_has_no_rate():
    with MR.folder() as f:
        MA.worked_example(f)
        assert next(m for m in recent(f) if m.quality == "unconfirmed").rate is None


def test_a_match_marked_not_a_match_has_no_rate():
    with MR.folder() as f:
        MA.worked_example(f)
        target = next(m for m in recent(f) if m.quality == "complete")
        H.correct_match(f, target.run_id, target.match_number, True)
        again = next(m for m in recent(f) if m.match_number == target.match_number and m.run_id == target.run_id)
        assert again.excluded and again.rate is None


def test_the_table_shows_the_rate_and_marks_partial():
    with G.window() as w:
        MA.worked_example(MA.history_folder(w))
        page = w.win.analytics
        page.refresh()
        MA.settle(w)
        assert page.COLUMNS[4] == "Chests/min"
        cells = {page.table.item(r, 5).text(): page.table.item(r, 4).text() for r in range(page.table.rowCount())}
        assert cells["Partial"] == "0.50 seen" and cells["Unconfirmed"] == DASH and cells["Complete"] in ("0.20", "0.30"), cells


def test_the_rate_wording_is_plain():
    with G.window() as w:
        page = w.win.analytics
        titles = page.observed_rate.findChildren(ui().QLabel)[0].text(), page.complete_rate.findChildren(ui().QLabel)[0].text()
        assert titles == ("AVERAGE DETECTED CHESTS / MIN", "COMPLETE MATCHES ONLY"), titles
        hint = page.rate_hint.text()
        assert "detected by itself" in hint and "time actively playing" in hint and "Manual" in hint and "not your Fortnite total" in hint


def test_the_headline_is_the_fuller_rate_with_approx_first():
    with G.window() as w:
        MA.worked_example(MA.history_folder(w))
        page = w.win.analytics
        page.refresh()
        MA.settle(w)
        assert page.observed_rate.value.text() == "0.32" and page.observed_rate.sub.text().startswith("APPROX per minute  ·  0.21 CERTAIN"), page.observed_rate.sub.text()
        assert "complete and partial matches" in page.observed_rate.sub.text()
        assert page.complete_rate.value.text() == "0.27" and "0.20 CERTAIN" in page.complete_rate.sub.text()


def test_the_headline_stands_out():
    with G.window() as w:
        page = w.win.analytics
        assert isinstance(page.observed_rate, ui().CountCard) and isinstance(page.complete_rate, ui().StatTile)


def test_no_internal_words_remain_on_the_page():
    with G.window() as w:
        page = w.win.analytics
        text = " ".join(item.text() for item in page.findChildren(ui().QLabel)).lower()
        for word in ("observed rate", "complete-match rate", "confirmed play", "observed match time"):
            assert word not in text, word


def test_an_unfinished_match_says_what_it_is_left_out_of():
    note = ui().analytics_notes(analytics().Summary(unfinished=1))
    assert "1 match still in progress" in note and "match count, match time and chests per minute" in note and "so not counted" not in note


# ------------------------------------------------------------------ the Game view

def counting(w):
    w.win.worker.is_running = True
    w.win.set_mode("counting")


def status(chests={"certain": 23, "approx": 28}, last=None, **match):
    return {**U.status("IN_MATCH", {**U.match(active=319.4), **match}), "chests": chests, "last_match": last}


def test_the_game_shows_this_matchs_numbers_not_the_totals():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.set_counts(500, 700)
        w.win.handle(status())
        assert (d.game_approx.value.text(), d.game_certain.value.text()) == ("28", "23")
        assert (d.approx.value.text(), d.certain.value.text()) == ("700", "500"), "the Overview keeps the lifetime totals"
        assert d.game_approx_rate.value.text() == "5.26" and d.game_certain_rate.value.text() == "4.32"


def test_a_correction_does_not_touch_the_match_numbers():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle(status())
        w.win.handle({"type": "correction", "status": "applied", "id": "c1", "delta": 1, "certain": 23, "approx": 29, "recorded": True})
        assert d.game_approx.value.text() == "28"


def test_no_match_shows_dashes_not_zeros():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle(U.status("LOBBY"))
        assert (d.game_approx.value.text(), d.game_certain.value.text(), d.game_approx_rate.value.text()) == (DASH, DASH, DASH)
        assert d.game_approx.sub.text() == "No match right now"


def test_an_unconfirmed_match_shows_no_numbers():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle(status(english_confirmed=False))
        assert d.game_approx.value.text() == DASH and d.game_approx_rate.value.text() == DASH and d.game_approx.sub.text() == "Not confirmed as a match yet"


def test_a_late_join_says_so():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle(status(observed_from_start=False))
        assert d.game_approx.value.text() == "28" and d.game_approx.sub.text() == "Since the app joined this match"


def test_a_break_says_so():
    with G.window() as w:
        counting(w)
        w.win.handle(status(discontinuity=True))
        assert w.win.dashboard.game_approx.sub.text() == "Part of this match was not seen"


def test_too_little_play_gives_no_rate():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle(status(active_seconds=30.0))
        assert d.game_approx.value.text() == "28" and d.game_approx_rate.value.text() == DASH and d.game_approx_rate.sub.text() == "Needs a minute of play"


def test_a_new_match_clears_the_old_numbers():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle(status())
        w.win.handle(status(chests={"certain": 0, "approx": 0}, match_number=2))
        assert d.game_approx.value.text() == "0"


def test_stalled_video_stops_the_rate_but_keeps_the_count():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle(status())
        w.win.match_seen_at -= 60
        w.win._check_match_video()
        assert d.game_approx.value.text() == "28" and d.game_approx_rate.value.text() == DASH and d.game_approx_rate.sub.text() == "No video right now"


def test_stopping_clears_the_match():
    with G.window() as w:
        d = w.win.dashboard
        w.win.session_match_mode = "on"
        counting(w)
        w.win.handle(status(last={"certain": 1, "approx": 2, "active_seconds": 300, "completion": "complete", "ended_by": "placed", "reasons": [], "english_confirmed": True, "match_number": 1}))
        assert not d.game_last.isHidden()
        w.win.set_mode("stopped")
        assert d.game_approx.value.text() == DASH and d.game_last.isHidden()


def test_the_last_match_is_shown_with_its_ending():
    text = ui().last_match_text({"certain": 23, "approx": 28, "active_seconds": 319.4, "completion": "partial", "ended_by": "left_or_unknown", "reasons": ["connecting_seen"], "english_confirmed": True})
    assert "APPROX 28" in text and "CERTAIN 23" in text and "5.26 per minute" in text and "Partial" in text and "Left the match" in text


def test_a_weak_record_does_not_replace_the_last_match():
    weak = {"certain": 0, "approx": 0, "active_seconds": 9.3, "completion": "partial", "ended_by": "left_or_unknown", "reasons": ["next match countdown seen"], "english_confirmed": True}
    assert ui().last_match_text(weak) == "" and ui().last_match_text({**weak, "english_confirmed": False, "approx": 3, "active_seconds": 300}) == ""


def test_the_overview_line_names_this_match():
    assert ui().match_summary(status()) == "   ·   28 chests this match   ·   5.26 per minute"
    assert ui().match_summary(status(english_confirmed=False)) == "" and ui().match_summary(U.status("LOBBY")) == ""


def test_profiles_do_not_carry_match_numbers_over():
    with G.window() as w:
        d = w.win.dashboard
        w.win.session_match_mode = "on"
        counting(w)
        w.win.handle(status())
        w.win.set_mode("stopped")
        w.win.fill_profiles()
        assert d.game_approx.value.text() == DASH


# ------------------------------------------------------------------ the preview

def preview_rig(w):
    w.win.preview_reader = MagicMock()
    w.win.preview_reader.read.return_value = None
    counting(w)


def done(w):
    w.win.preview_timer.stop()
    w.win.preview_reader = None


def wanted(w):
    return w.win.preview_reader.set_wanted.call_args[0][0]


def test_the_preview_is_on_by_default_on_the_overview():
    with G.window() as w:
        d, A = w.win.dashboard, ui()
        preview_rig(w)
        assert d.show_mini.isChecked() and d.show_preview.isChecked() and not d.mini_preview.isHidden()
        assert wanted(w) is True and w.win.active_preview() is d.mini_preview and d.views.widget(A.OVERVIEW_VIEW).isAncestorOf(d.mini_preview)
        done(w)


def test_only_the_visible_preview_is_active():
    with G.window() as w:
        d, A = w.win.dashboard, ui()
        preview_rig(w)
        d.show_view(A.GAME_VIEW)
        assert w.win.active_preview() is d.preview and wanted(w) is True
        d.show_view(A.OVERVIEW_VIEW)
        assert w.win.active_preview() is d.mini_preview and wanted(w) is True
        d.show_view(A.CONSOLE_VIEW)
        assert w.win.active_preview() is None and wanted(w) is False and not w.win.preview_timer.isActive()
        done(w)


def test_there_is_one_reader_and_one_timer():
    from PySide6.QtCore import QTimer
    with G.window() as w:
        source = Path(ui().__file__).read_text(encoding="utf-8")
        assert source.count("PreviewReader(") == 1 and source.count("self.preview_timer = QTimer(") == 1


def test_a_picture_goes_only_to_the_visible_preview():
    with G.window() as w:
        d, A = w.win.dashboard, ui()
        preview_rig(w)
        w.win.preview_reader.read.return_value = (1.0, 640, 360, bytes(640 * 360 * 3))
        d.show_view(A.GAME_VIEW)
        with patch.object(d.preview, "show_frame") as large, patch.object(d.mini_preview, "show_frame") as small:
            w.win._tick_preview()
        assert large.called and not small.called
        d.show_view(A.OVERVIEW_VIEW)
        with patch.object(d.preview, "show_frame") as large, patch.object(d.mini_preview, "show_frame") as small:
            w.win._tick_preview()
        assert small.called and not large.called
        done(w)


def test_another_page_stops_the_preview():
    with G.window() as w:
        preview_rig(w)
        assert wanted(w) is True
        w.win.show_page(w.win.settings_page)
        assert wanted(w) is False and w.win.active_preview() is None
        w.win.show_page(w.win.dashboard)
        assert wanted(w) is True
        done(w)


def test_minimising_stops_the_preview():
    with G.window() as w:
        preview_rig(w)
        with patch.object(w.win, "isMinimized", return_value=True):
            w.win.preview_visibility_changed()
            assert wanted(w) is False
        w.win.preview_visibility_changed()
        assert wanted(w) is True
        done(w)


def test_a_minimise_event_is_noticed():
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QWindowStateChangeEvent
    with G.window() as w:
        calls = []
        w.win.preview_visibility_changed = lambda: calls.append(1)
        w.qt.sendEvent(w.win, QWindowStateChangeEvent(Qt.WindowNoState))
        assert calls


def test_hiding_it_stops_it_without_stopping_counting():
    with G.window() as w:
        d = w.win.dashboard
        preview_rig(w)
        d.show_mini.setChecked(False)
        assert d.mini_preview.isHidden() and d.preview.isHidden() and wanted(w) is False and w.win.worker.is_running and w.win.mode == "counting"
        done(w)


def test_the_two_buttons_are_one_setting():
    with G.window() as w:
        d = w.win.dashboard
        assert d.show_preview.isChecked() and d.show_mini.isChecked()
        d.show_preview.setChecked(False)
        assert not d.show_mini.isChecked()
        d.show_mini.setChecked(True)
        assert d.show_preview.isChecked()


def test_the_choice_is_remembered():
    with G.window() as w:
        w.win.dashboard.show_mini.setChecked(False)
        cfg, _, warnings = settings.load_config(str(w.dir / "config.toml"))
        assert cfg["app"]["show_preview"] is False and warnings == []
    with G.window(config='[app]\nshow_preview = false\n') as w:
        assert not w.win.dashboard.show_mini.isChecked() and w.win.dashboard.mini_preview.isHidden()


def test_the_overview_preview_makes_room_for_the_link_help_until_counting():
    with G.window() as w:
        d = w.win.dashboard
        d.source.addItem("Livestream URL", {"source": "stream"})
        d.source.setCurrentIndex(d.source.count() - 1)
        assert d.mini_preview.isHidden() and not d.url_note.isHidden() and not d.stability_hint.isHidden()
        counting(w)
        assert not d.mini_preview.isHidden() and d.url_note.isHidden() and d.stability_hint.isHidden()
        w.win.worker.is_running = False
        w.win.set_mode("stopped")
        assert d.mini_preview.isHidden() and not d.url_note.isHidden()


def test_another_source_shows_the_preview_box_before_counting():
    with G.window() as w:
        d = w.win.dashboard
        d.source.addItem("Livestream URL", {"source": "stream"})
        d.source.addItem("OBS Virtual Camera", {"source": "obs-camera"})
        d.source.setCurrentIndex(d.source.findText("Livestream URL"))
        assert d.mini_preview.isHidden()
        d.source.setCurrentIndex(d.source.findText("OBS Virtual Camera"))
        assert not d.mini_preview.isHidden()


def test_the_picture_cannot_make_the_page_longer():
    from PySide6.QtWidgets import QSizePolicy
    with G.window() as w:
        for panel in (w.win.dashboard.preview, w.win.dashboard.mini_preview):
            assert panel.view.sizePolicy().verticalPolicy() == QSizePolicy.Ignored and panel.view.sizePolicy().horizontalPolicy() == QSizePolicy.Ignored


def test_not_counting_means_no_preview_work():
    with G.window() as w:
        w.win.preview_reader = MagicMock()
        w.win.set_mode("stopped")
        assert wanted(w) is False and not w.win.preview_timer.isActive()
        w.win.preview_reader = None


def test_a_message_reaches_both_panels():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle({"type": "stream", "state": "no_video", "text": "x"})
        assert "NO VIDEO" in d.preview.view.text() and "NO VIDEO" in d.mini_preview.view.text()


def test_stopping_clears_both_panels():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle({"type": "stream", "state": "no_video", "text": "x"})
        w.win.set_mode("stopped")
        assert "NO VIDEO" not in d.preview.view.text() and "NO VIDEO" not in d.mini_preview.view.text()


# ------------------------------------------------------------------ the default

def load(tmp, text):
    path = Path(tmp) / "config.toml"
    path.write_text(text, encoding="utf-8")
    return settings.load_config(str(path))


def test_a_new_install_tracks_matches():
    assert settings.DEFAULTS["match"]["mode"] == "on"
    with tempfile.TemporaryDirectory() as tmp:
        assert settings.load_config(str(Path(tmp) / "absent.toml"))[0]["match"]["mode"] == "on"


def test_a_config_from_before_this_version_gets_the_default():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, _, warnings = load(tmp, '[display]\nshow = "certain"\n')
        assert cfg["match"]["mode"] == "on" and cfg["display"]["show"] == "certain" and warnings == []


def test_an_explicit_off_is_kept():
    with tempfile.TemporaryDirectory() as tmp:
        assert load(tmp, '[match]\nmode = "off"\n')[0]["match"]["mode"] == "off"


def test_an_explicit_shadow_is_kept():
    with tempfile.TemporaryDirectory() as tmp:
        assert load(tmp, '[match]\nmode = "shadow"\n')[0]["match"]["mode"] == "shadow"


def test_off_stays_off_through_the_settings_page():
    with G.window(config='[match]\nmode = "off"\n') as w:
        page = w.win.settings_page
        page.load()
        assert not page.match_on.isChecked()
        page.save()
        assert settings.load_config(str(w.dir / "config.toml"))[0]["match"]["mode"] == "off"


def test_the_example_config_says_on():
    text = (ROOT / "config.example.toml").read_text(encoding="utf-8")
    section = text.split("[match]")[1].split("\n[")[0]
    assert '\nmode = "on"' in section and "ON by default" in section


# ------------------------------------------------------------------ the chest type in the log

def event(**fields):
    return {"certain_counted": True, "approx_counted": True, "popup_score": 0.8, "adjusted_tier": "HIGH", **fields}


def test_each_type_has_its_name():
    assert set(CON.CHEST_LABELS) == set(chest_types.KNOWN), "the names must match the detector's own types"
    assert [console().type_label(event(chest_type=t)) for t in (chest_types.NORMAL, chest_types.RARE, chest_types.SPRITE)] == ["Regular chest", "Rare chest", "Sprite chest"]


def test_an_unread_type_is_never_guessed():
    for fields in ({"chest_type": chest_types.UNKNOWN}, {"chest_type": None}, {}, {"chest_type": "something new"}):
        assert console().type_label(event(**fields)) == "Unknown chest", fields


def test_what_was_not_counted_has_no_type():
    assert console().type_label({"certain_counted": False, "approx_counted": False, "chest_type": chest_types.RARE}) == ""


def test_an_approx_only_chest_has_its_type():
    assert console().type_label(event(certain_counted=False, chest_type=chest_types.RARE)) == "Rare chest"


def test_the_app_message_carries_it():
    message = console().event_message(event(chest_type=chest_types.SPRITE), "1", "1", 1, 1)
    assert message["chest_label"] == "Sprite chest" and message["verdict"] == "certain"


def test_the_activity_log_shows_it_and_keeps_the_evidence():
    message = {"type": "event", "verdict": "approx", "chest_label": "Rare chest", "evidence": "match 0.78 (MEDIUM)", "why": "", "certain_text": "12", "approx_text": "15", "clock": "05:05:49"}
    html = ui().log_entries(message)[0][1]
    assert "Rare&nbsp;chest" in html or "Rare chest" in html
    assert "CHEST ~+1" in html and "match 0.78 (MEDIUM)" in html and "CERTAIN 12 | APPROX 15" in html


def test_a_type_read_later_is_reported():
    entries = ui().log_entries({"type": "type_update", "event_id": "E1", "previous": "unknown", "chest_type": chest_types.RARE, "clock": "05:05:49"})
    assert entries and "Rare chest" in entries[0][1] and entries[0][0] is False


def test_the_terminal_shows_it_too():
    import contextlib
    import io
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        console().CONSOLE.event(event(chest_type=chest_types.RARE), "1", "1")
    assert "Rare chest" in buffer.getvalue()


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
    print(f"{len(tests) - failed}/{len(tests)} live match checks passed")
    raise SystemExit(1 if failed else 0)
