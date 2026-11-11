"""
Match history storage (v0.3.0, M5): append-only rows, stable identity, crash recovery, visible gaps, profile handling, and no way to reach
the totals. Nothing here decodes video, and nothing in the program uses this module yet.

Run:   python tests/test_match_history.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))                                     # run without installing
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "tests"))

import ast
import contextlib
import dataclasses
import io
import json
import statistics
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from fortnite_chest_counter import counter as C
from fortnite_chest_counter import match_history as H
from fortnite_chest_counter import match_state as S
from fortnite_chest_counter import profiles, settings

import match_scorecard as SC
import test_match_state as M2


class Rig:
    def __init__(self, folder, **kwargs):
        self.folder, self.warnings = Path(folder), []
        self.writer = H.HistoryWriter(folder, self.warnings.append, **kwargs)

    def start(self, certain=0, approximate=0, events_logged=0):
        self.writer.start_run("stream", "0.3.0", 15, ["en", "pt"], certain, approximate, events_logged)
        return self

    def end(self, certain=0, approximate=0, events_logged=0, t=100.0):
        self.writer.end_run(t, "Q pressed", 1500, 3, 100.5, certain, approximate, events_logged)
        return self

    def read(self):
        return H.read(self.folder)


def chest(number, t, certain=True, approx=True, template="en:CHEST", chest_type="rare"):
    return {"event_id": f"E{number:04d}", "time": t, "certain_counted": certain, "approx_counted": approx, "popup_template": template, "chest_type": chest_type,
            "adjusted_tier": "HIGH", "source": "popup", "latency_s": 1.0}


def opened(number=1, t=10.0, from_start=True, confidence="high"):
    return {"t": t, "match_number": number, "observed_from_start": from_start, "start_confidence": confidence}


def snapshot(number=1, opened_t=8.0, played=20.0, observed=50.0, active=40.0, spectating=5.0, uncertain=2.0, english=True):
    return {"match_number": number, "opened_t": opened_t, "played_from_t": played, "observed_seconds": observed, "active_seconds": active,
            "spectating_seconds": spectating, "uncertain_seconds": uncertain, "english_confirmed": english}


def record(number=1, opened_t=10.0, closed_t=110.0, active=80.0, completion="complete", ended_by="placed"):
    span = closed_t - opened_t
    return {"match_number": number, "completion": completion, "english_confirmed": True, "ended_by": ended_by, "observed_from_start": True, "opened_t": opened_t,
            "played_from_t": opened_t + 5, "ended_t": closed_t - 5, "closed_t": closed_t, "observed_seconds": span, "active_seconds": active, "spectating_seconds": 5.0,
            "uncertain_seconds": 0.0, "complete_duration_seconds": closed_t - 5 - (opened_t + 5) if completion == "complete" else None, "start_confidence": "high",
            "end_confidence": "high", "discontinuity": False, "respawns": 0, "english_chests": 2, "portuguese_chests": 0, "reasons": ["started"], "evidence": [(9.0, "you_placed", 0.9)]}


def file_rows(folder, name):
    return [json.loads(line) for line in (Path(folder) / name).read_bytes().splitlines() if line]


@contextlib.contextmanager
def folder():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp) / "history" / "someone"


# ------------------------------------------------------------------ what is stored

def test_every_row_has_kind_schema_and_a_unique_id():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 5.0), 1, 1)
        rig.writer.transition({"t": 1.0, "previous": "UNKNOWN", "state": "LOBBY", "reason": "menu_seen", "match_number": None})
        rig.end(1, 1, 1)
        rows = file_rows(f, H.MATCHES) + file_rows(f, H.CHESTS)
        assert len(rows) == 4 and all(r["schema"] == 1 and r["kind"] and r["run_id"] == rig.writer.run_id and r["at"] for r in rows)
        assert len({r["id"] for r in rows}) == 4
        assert all(line.startswith(b'{"kind":"') for line in (f / H.MATCHES).read_bytes().splitlines())


def test_only_the_two_planned_files_are_written():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 5.0), 1, 1)
        rig.writer.heartbeat(30.0, 450, 0)
        rig.end(1, 1, 1)
        assert sorted(p.name for p in f.iterdir()) == [H.CHESTS, H.MATCHES]


def test_a_run_records_its_settings_and_what_was_really_processed():
    with folder() as f:
        run = Rig(f).start(3, 7, 9).end(4, 8, 10).read().runs
        (only,) = run.values()
        assert only["start"]["configured_analysis_fps"] == 15 and "fps" not in only["start"] and only["start"]["languages"] == ["en", "pt"]
        assert only["start"]["source_type"] == "stream" and only["start"]["app_version"] == "0.3.0" and only["start"]["events_logged"] == 9
        assert (only["start"]["certain_total"], only["start"]["approximate_total"]) == (3, 7)
        assert only["end"]["frames_processed"] == 1500 and only["end"]["frames_dropped"] == 3 and only["end"]["elapsed_seconds"] == 100.5 and only["end"]["t"] == 100.0
        assert only["end"]["stop_reason"] == "Q pressed" and only["start"]["at"] and only["end"]["at"]


def test_a_chest_keeps_its_evidence():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 37.25, certain=False, approx=True, template="pt:BAU", chest_type="normal"), 0, 1)
        (row,) = rig.read().chests
        assert row["t"] == 37.25 and row["at"] and row["certain_counted"] is False and row["approx_counted"] is True and row["chest_type"] == "normal"
        assert row["language"] == "pt" and row["popup_template"] == "pt:BAU" and row["adjusted_tier"] == "HIGH" and row["detector_source"] == "popup"
        assert (row["certain_total"], row["approximate_total"]) == (0, 1) and "latency_s" not in row


def test_uncounted_events_are_not_chests():
    with folder() as f:
        rig = Rig(f).start()
        assert rig.writer.chest(chest(1, 5.0, certain=False, approx=False), 0, 0) is False
        assert rig.read().chests == []


def test_languages_agree_with_the_state_machine():
    for value in ("en:CHEST", "pt:BAÚ", None, "", "xx:THING"):
        assert H.chest_language(value) == S.chest_language(value), value


def test_a_real_match_record_round_trips_without_respawns():
    script = M2.played_match().show(10, "you_placed", health=40).show(5, "connecting").finish()
    (real,) = script.records
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.match_closed(real.to_dict())
        (row,) = rig.read().matches
        expected = json.loads(json.dumps(real.to_dict()))
        expected.pop("respawns")
        expected["evidence"] = sorted(expected["evidence"], key=lambda item: (item[0], item[1]))
        assert {k: row[k] for k in expected} == expected and "respawns" not in row
        assert_sound([row])


def test_the_stored_fields_track_the_state_machine():
    names = {item.name for item in dataclasses.fields(S.MatchRecord)}
    assert set(H.MATCH_FIELDS) == names - {"respawns"}, names ^ set(H.MATCH_FIELDS)


def test_time_values_stay_separate():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.match_closed({**record(), "observed_seconds": 90.0, "active_seconds": 70.0, "spectating_seconds": 15.0, "uncertain_seconds": 10.0})
        (row,) = rig.read().matches
        assert (row["observed_seconds"], row["active_seconds"], row["spectating_seconds"], row["uncertain_seconds"]) == (90.0, 70.0, 15.0, 10.0)


def assert_sound(records):
    errors = SC.record_errors(records)
    assert not errors, errors


# ------------------------------------------------------------------ chest identity

def real_session(tmp):
    cfg, _, _ = settings.load_config(None, {("state", "path"): str(Path(tmp) / "s.json"), ("state", "obs_dir"): str(Path(tmp) / "o"), ("logging", "dir"): str(Path(tmp) / "l")})
    return cfg


def event(t):
    return {"time": t, "source": "popup", "adjusted_tier": "HIGH", "certain_counted": True, "approx_counted": True, "reason": "check", "popup_template": "en:CHEST"}


def test_a_real_reset_during_a_run_keeps_both_chests():
    """The defect found while reviewing the plan: the counter really does give two chests in one run the id E0001."""
    with tempfile.TemporaryDirectory() as tmp, folder() as f:
        cfg = real_session(tmp)
        session = C.CounterSession(cfg, reset=True)
        session.save()
        rig = Rig(f).start()
        first = session.apply([event(10.0)], 13.0, quiet=True)[0]
        rig.writer.chest(first, session.state["certain"], session.state["approximate"])
        time.sleep(0.05)
        C.CounterSession(cfg, reset=True).save()                          # what the `reset` command does, as a separate program
        second = session.apply([event(50.0)], 53.0, quiet=True)[0]
        rig.writer.chest(second, session.state["certain"], session.state["approximate"])
        assert first["event_id"] == second["event_id"] == "E0001"
        got = rig.read().chests
        assert [row["t"] for row in got] == [10.0, 50.0] and len({row["counter_epoch"] for row in got}) == 2


def test_an_announced_reset_separates_even_identical_ids_and_times():
    with folder() as f:
        rig = Rig(f).start()
        assert rig.writer.chest(chest(1, 10.0), 1, 1) is True
        rig.writer.counter_changed("reset", 0, 0)
        assert rig.writer.chest(chest(1, 10.0), 1, 1) is True
        assert len(rig.read().chests) == 2


def test_the_same_event_given_twice_is_recorded_once():
    with folder() as f:
        rig = Rig(f).start()
        assert rig.writer.chest(chest(1, 10.0), 1, 1) is True
        assert rig.writer.chest(chest(1, 10.0), 1, 1) is False
        assert len(file_rows(f, H.CHESTS)) == 1


def test_an_unannounced_restart_is_noticed():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 10.0), 1, 1)
        rig.writer.chest(chest(2, 20.0), 2, 2)
        rig.writer.chest(chest(1, 30.0), 1, 1)
        got = rig.read().chests
        assert [(r["event_id"], r["counter_epoch"]) for r in got] == [("E0001", 0), ("E0002", 0), ("E0001", 1)]


def test_identity_does_not_depend_on_source_time():
    """Video time can repeat or run backwards. Different events stay different, whatever their times."""
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 50.0), 1, 1)
        rig.writer.chest(chest(2, 50.0), 2, 2)
        rig.writer.chest(chest(3, 3.0), 3, 3)
        assert len(rig.read().chests) == 3


def test_event_ids_may_repeat_in_another_run():
    with folder() as f:
        first = Rig(f, run_id="run-a").start()
        first.writer.chest(chest(1, 10.0), 1, 1)
        first.end(1, 1, 1)
        second = Rig(f, run_id="run-b").start(1, 1, 1)
        second.writer.chest(chest(1, 10.0), 2, 2)
        assert len(second.read().chests) == 2


def test_a_row_repeated_in_the_file_counts_once():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 10.0), 1, 1)
        path = f / H.CHESTS
        path.write_bytes(path.read_bytes() * 3)
        assert len(rig.read().chests) == 1


def test_the_same_chest_under_a_new_row_id_counts_once():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 10.0), 1, 1)
        path = f / H.CHESTS
        (row,) = file_rows(f, H.CHESTS)
        H._append_line(path, H._encode({**row, "id": "recovery:9"}))
        assert len(rig.read().chests) == 1


def test_a_repeated_row_of_any_kind_counts_once():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.transition({"t": 1.0, "previous": "UNKNOWN", "state": "LOBBY", "reason": "menu_seen", "match_number": None})
        path = f / H.MATCHES
        path.write_bytes(path.read_bytes() * 2)
        assert len(rig.read().transitions) == 1


def test_a_retry_after_an_uncertain_write_keeps_the_same_identity():
    with folder() as f:
        rig = Rig(f).start()
        real = rig.writer._append
        calls = []

        def write_then_fail(name, line):
            real(name, line)
            calls.append(1)
            if len(calls) == 1:
                raise OSError("reported a failure after writing")

        with patch.object(rig.writer, "_append", write_then_fail):
            rig.writer.chest(chest(1, 10.0), 1, 1)
            rig.writer.chest(chest(2, 20.0), 2, 2)
        rows = file_rows(f, H.CHESTS)
        assert len(rows) == 3 and rows[0]["id"] == rows[1]["id"], rows
        assert [r["event_id"] for r in rig.read().chests] == ["E0001", "E0002"]


def test_a_later_type_change_wins_without_rewriting_the_chest():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 10.0, chest_type="unknown"), 1, 1)
        before = (f / H.CHESTS).read_bytes()
        rig.writer.chest_type("E0001", 10.0, "rare")
        assert (f / H.CHESTS).read_bytes().startswith(before)
        assert rig.read().chests[0]["chest_type"] == "rare"


def test_a_type_change_reaches_the_right_chest_after_a_reset():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 10.0, chest_type="old"), 1, 1)
        rig.writer.counter_changed("reset", 0, 0)
        rig.writer.chest(chest(1, 50.0, chest_type="new"), 1, 1)
        rig.writer.chest_type("E0001", 10.0, "corrected")
        got = {r["t"]: r["chest_type"] for r in rig.read().chests}
        assert got == {10.0: "corrected", 50.0: "new"}


def test_a_type_change_for_an_unknown_chest_writes_nothing():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest_type("E0099", 10.0, "rare")
        assert not (f / H.CHESTS).exists()


# ------------------------------------------------------------------ damaged files

def sample_file(f):
    rig = Rig(f).start()
    rig.writer.chest(chest(1, 10.0, template="pt:BAÚ"), 1, 1)
    rig.writer.chest(chest(2, 20.0, template="pt:BAÚ"), 2, 2)
    rig.writer.match_opened(opened())
    rig.writer.match_closed(record())
    rig.writer.transition({"t": 1.0, "previous": "UNKNOWN", "state": "LOBBY", "reason": "menu_ção", "match_number": None})
    return rig


def test_cutting_the_chests_file_at_every_byte():
    with folder() as f:
        sample_file(f)
        whole = (f / H.CHESTS).read_bytes()
        first_end = whole.index(b"\n") + 1
        for cut in range(len(whole) + 1):
            (f / H.CHESTS).write_bytes(whole[:cut])
            got = H.read(f).chests
            expected = 2 if cut >= len(whole) - 1 else 1 if cut >= first_end - 1 else 0
            assert len(got) == expected, (cut, len(got))
            assert all(row["event_id"] in ("E0001", "E0002") and row["language"] == "pt" for row in got)


def test_cutting_the_matches_file_at_every_byte():
    with folder() as f:
        sample_file(f)
        whole = (f / H.MATCHES).read_bytes()
        complete = len(whole.splitlines())
        ends = [i for i, byte in enumerate(whole) if byte == 10]
        for cut in range(len(whole) + 1):
            (f / H.MATCHES).write_bytes(whole[:cut])
            history = H.read(f)
            rows = sum(1 for end in ends if cut >= end)
            assert history.bad_lines == (1 if cut and whole[cut - 1] != 10 and cut not in ends and rows < complete else 0), cut
            assert len(history.transitions) == (1 if rows == complete else 0), cut


def test_a_cut_line_does_not_swallow_the_next_row():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 10.0), 1, 1)
        path = f / H.CHESTS
        path.write_bytes(path.read_bytes()[:-20])
        rig.writer.chest(chest(2, 20.0), 2, 2)
        history = rig.read()
        assert [r["event_id"] for r in history.chests] == ["E0002"] and history.bad_lines == 1


def test_junk_lines_are_skipped_anywhere():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 10.0), 1, 1)
        path = f / H.CHESTS
        junk = [b"\xff\xfe not text", b"123", b"[1,2]", b'{"kind":"chest"}', b'{"kind":"chest","schema":"1","id":"x"}', b'{"kind":"chest","schema":0,"id":"x"}',
                b'{"kind":"chest","schema":1,"id":"x"}']
        path.write_bytes(b"\n".join(junk) + b"\n" + path.read_bytes() + b"\n".join(junk) + b"\n")
        history = rig.read()
        assert len(history.chests) == 1 and history.bad_lines >= 6


def test_a_row_missing_fields_is_skipped_in_the_matches_file():
    with folder() as f:
        rig = Rig(f).start()
        H._append_line(f / H.MATCHES, b'{"kind":"match_opened","schema":1,"id":"x:9","run_id":"x"}\n')
        assert rig.read().bad_lines == 1


# ------------------------------------------------------------------ write failures

def test_a_failed_write_is_retried_and_nothing_is_lost():
    with folder() as f:
        rig = Rig(f).start()
        with patch.object(rig.writer, "_append", side_effect=OSError("locked")):
            rig.writer.chest(chest(1, 10.0), 1, 1)
            rig.writer.chest(chest(2, 20.0), 2, 2)
        assert len(rig.warnings) == 1 and "counting is not affected" in rig.warnings[0], rig.warnings
        assert not (f / H.CHESTS).exists()
        rig.writer.chest(chest(3, 30.0), 3, 3)
        history = rig.read()
        assert [r["event_id"] for r in history.chests] == ["E0001", "E0002", "E0003"] and history.gaps == []


def test_a_retried_row_keeps_its_original_wall_clock():
    with folder() as f:
        ticks = iter(f"tick-{i}" for i in range(50))
        rig = Rig(f, now=lambda: next(ticks)).start()
        with patch.object(rig.writer, "_append", side_effect=OSError("locked")):
            rig.writer.chest(chest(1, 10.0), 1, 1)
        rig.writer.chest(chest(2, 20.0), 2, 2)
        got = rig.read().chests
        assert got[0]["at"] == "tick-1" and got[1]["at"] == "tick-2", got


def test_a_real_write_error_is_contained_and_recovers():
    with folder() as f:
        rig = Rig(f).start()
        target = f / H.CHESTS
        target.mkdir()                                                    # a real failure: this path cannot be opened as a file
        rig.writer.chest(chest(1, 10.0), 1, 1)
        assert len(rig.warnings) == 1
        target.rmdir()
        rig.writer.chest(chest(2, 20.0), 2, 2)
        assert [r["event_id"] for r in rig.read().chests] == ["E0001", "E0002"]


def test_a_write_cut_off_by_an_error_leaves_the_retry_readable():
    with folder() as f:
        rig = Rig(f).start()
        calls = []

        def partial(name, line):
            calls.append(1)
            if len(calls) == 1:
                with open(f / name, "ab") as stream:
                    stream.write(line[:15])
                raise OSError("disk full")
            H._append_line(f / name, line)

        with patch.object(rig.writer, "_append", partial):
            rig.writer.chest(chest(1, 10.0), 1, 1)
            rig.writer.chest(chest(2, 20.0), 2, 2)
        history = rig.read()
        assert [r["event_id"] for r in history.chests] == ["E0001", "E0002"] and history.bad_lines == 1


def test_rows_really_lost_become_a_gap_row_at_the_next_successful_write():
    with folder() as f, patch.object(H, "MAX_WAITING", 2):
        rig = Rig(f).start()
        rig.writer.match_opened(opened())
        with patch.object(rig.writer, "_append", side_effect=OSError("disk full")):
            for i in range(1, 6):
                rig.writer.chest(chest(i, i * 10.0, certain=i % 2 == 1), i, i)
        assert len(rig.warnings) == 1
        rig.writer.match_closed(record())
        history = rig.read()
        (gap,) = history.gaps
        assert gap["reason"] == H.WRITE_FAILED and gap["lost_rows"] == 3 and gap["missing_certain"] == 2 and gap["missing_approximate"] == 3 and gap["match_number"] == 1, gap
        assert len(history.chests) == 2 and history.matches[0]["history_incomplete"] is True


def test_every_writer_call_contains_bad_input():
    with folder() as f:
        rig = Rig(f)
        calls = [lambda: rig.writer.chest(None, 0, 0), lambda: rig.writer.chest({"certain_counted": True}, 0, 0), lambda: rig.writer.chest(chest(1, float("nan")), 0, 0),
                 lambda: rig.writer.transition({}), lambda: rig.writer.match_opened({}), lambda: rig.writer.match_closed({}), lambda: rig.writer.heartbeat(1.0, 0, 0, match={}),
                 lambda: rig.writer.counter_changed("x", float("inf"), 0)]
        for call in calls:
            call()
        assert len(rig.warnings) == 1, rig.warnings


def test_an_impossible_number_is_never_written():
    with folder() as f:
        rig = Rig(f)
        rig.writer.chest(chest(1, float("nan")), 1, 1)
        assert not (f / H.CHESTS).exists() and len(rig.warnings) == 1


def test_each_row_reaches_the_disk_before_returning():
    with folder() as f, patch.object(H.os, "fsync") as sync:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 10.0), 1, 1)
        assert sync.call_count == 2


def test_evidence_is_stored_in_a_stable_order():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.match_closed({**record(), "evidence": [(9.0, "b", 0.9), (2.0, "z", 0.8), (9.0, "a", 0.7)]})
        assert rig.read().matches[0]["evidence"] == [[2.0, "z", 0.8], [9.0, "a", 0.7], [9.0, "b", 0.9]]


def test_a_failing_warning_is_contained():
    def warn(message):
        raise OSError("the console is gone")

    with folder() as f:
        writer = H.HistoryWriter(f, warn)
        writer.chest(None, 0, 0)


def test_the_user_stopping_is_not_swallowed():
    with folder() as f:
        rig = Rig(f).start()
        with patch.object(rig.writer, "_append", side_effect=KeyboardInterrupt):
            try:
                rig.writer.chest(chest(1, 10.0), 1, 1)
            except KeyboardInterrupt:
                return
    raise AssertionError("Ctrl+C was swallowed")


def test_nothing_is_written_after_the_run_ends():
    with folder() as f:
        rig = Rig(f).start().end()
        before = (f / H.MATCHES).read_bytes()
        rig.writer.chest(chest(1, 10.0), 1, 1)
        rig.writer.heartbeat(1.0, 0, 0)
        assert (f / H.MATCHES).read_bytes() == before and not (f / H.CHESTS).exists()


# ------------------------------------------------------------------ recovery after a crash

def crashed(f, certain=1, approximate=1, run_id="crashed"):
    rig = Rig(f, run_id=run_id).start()
    rig.writer.chest(chest(1, 10.0), certain, approximate)
    return rig


def test_a_clean_run_needs_no_recovery():
    with folder() as f:
        first = Rig(f).start()
        first.writer.chest(chest(1, 10.0), 1, 1)
        first.end(1, 1, 1)
        second = Rig(f).start(1, 1, 1)
        history = second.read()
        assert history.gaps == [] and all(run["end"] is None or not run["end"].get("interrupted") for run in history.runs.values())


def test_a_crash_is_found_and_the_run_is_closed():
    with folder() as f:
        rig = crashed(f)
        rig.writer.heartbeat(60.0, 900, 2)
        Rig(f).start(1, 1, 1)
        end = H.read(f).runs["crashed"]["end"]
        assert end["interrupted"] is True and end["stop_reason"] == H.INTERRUPTED and end["t"] == 60.0 and end["frames_processed"] == 900 and end["elapsed_seconds"] is None and end["last_seen_at"]


def test_a_crash_between_the_totals_and_history_leaves_a_gap_row():
    with folder() as f:
        crashed(f, 1, 1)
        Rig(f).start(2, 3, 5)                                             # the totals got ahead of history
        (gap,) = H.read(f).gaps
        assert gap["reason"] == H.INTERRUPTED and gap["run_id"] == "crashed" and (gap["missing_certain"], gap["missing_approximate"]) == (1, 2), gap


def test_recovery_never_touches_the_totals():
    with tempfile.TemporaryDirectory() as tmp, folder() as f:
        cfg = real_session(tmp)
        session = C.CounterSession(cfg, reset=True)
        session.state["certain"], session.state["approximate"] = 5, 9
        session.save()
        before = Path(cfg["state"]["path"]).read_bytes()
        crashed(f, 1, 1)
        Rig(f).start(5, 9, 9)
        assert Path(cfg["state"]["path"]).read_bytes() == before and H.read(f).gaps


def test_matching_totals_leave_no_gap():
    with folder() as f:
        crashed(f, 1, 1)
        Rig(f).start(1, 1, 1)
        assert H.read(f).gaps == []


def test_a_reset_before_the_crash_is_not_a_gap():
    with folder() as f:
        rig = crashed(f, 4, 4)
        rig.writer.counter_changed("reset", 0, 0)
        rig.writer.chest(chest(1, 50.0), 1, 1)
        Rig(f).start(1, 1, 1)
        assert H.read(f).gaps == []


def test_a_reset_as_the_last_thing_before_a_crash_is_not_a_gap():
    with folder() as f:
        rig = crashed(f, 4, 4)
        rig.writer.counter_changed("reset", 0, 0)
        Rig(f).start(0, 0, 0)
        assert H.read(f).gaps == []


def test_totals_lowered_after_a_crash_are_recorded_but_lose_no_chests():
    with folder() as f:
        rig = crashed(f, 5, 5)
        rig.writer.match_opened(opened(t=10.0))
        Rig(f).start(0, 0, 0)                                             # Reset while the counter was not running
        history = H.read(f)
        (gap,) = history.gaps
        assert gap["reason"] == H.TOTALS_LOWERED and gap["match_number"] is None and (gap["missing_certain"], gap["missing_approximate"]) == (-5, -5), gap
        assert history.matches[0]["history_incomplete"] is False


def test_a_disk_that_never_recovers_is_found_at_the_next_start():
    with folder() as f:
        rig = Rig(f, run_id="doomed").start()
        with patch.object(rig.writer, "_append", side_effect=OSError("disk full")):
            rig.writer.chest(chest(1, 10.0), 1, 1)
            rig.writer.chest(chest(2, 20.0), 2, 2)
            rig.end(2, 2, 2)
        assert len(rig.warnings) == 1
        Rig(f).start(2, 2, 2)
        history = H.read(f)
        (gap,) = history.gaps
        assert gap["run_id"] == "doomed" and (gap["missing_certain"], gap["missing_approximate"]) == (2, 2) and history.runs["doomed"]["end"]["interrupted"]


def test_a_run_with_no_start_row_cannot_hide_the_newest_run():
    with folder() as f:
        crashed(f, 1, 1, run_id="real")
        H._append_line(f / H.CHESTS, H._encode({"kind": "chest", "schema": 1, "id": "headless:1", "run_id": "headless", "counter_epoch": 0, "event_id": "E0001", "t": 1.0,
                                                "certain_total": 1, "approximate_total": 1}))
        Rig(f).start(3, 3, 3)
        (gap,) = H.read(f).gaps
        assert gap["run_id"] == "real", gap


def test_an_open_match_closes_as_interrupted_at_the_last_heartbeat():
    with folder() as f:
        rig = crashed(f)
        rig.writer.match_opened(opened(t=10.0))
        rig.writer.heartbeat(60.0, 900, 0, match=snapshot(opened_t=8.0, observed=50.0, active=40.0, spectating=5.0))
        Rig(f).start(1, 1, 1)
        history = H.read(f)
        (row,) = history.matches
        assert history.open_matches == [] and row["run_id"] == "crashed" and row["interrupted"] is True and row["ended_by"] == H.INTERRUPTED
        assert row["completion"] == "partial" and row["closed_t"] == 60.0 and row["ended_t"] is None and row["complete_duration_seconds"] is None
        assert (row["observed_seconds"], row["active_seconds"], row["spectating_seconds"], row["uncertain_seconds"]) == (50.0, 40.0, 5.0, 2.0)
        assert row["discontinuity"] is True and row["end_confidence"] == "low"
        assert_sound(history.matches)


def test_no_heartbeat_means_no_claimed_time():
    with folder() as f:
        rig = crashed(f)
        rig.writer.match_opened(opened(t=10.0))
        Rig(f).start(1, 1, 1)
        (row,) = H.read(f).matches
        assert row["closed_t"] == 10.0 and (row["observed_seconds"], row["active_seconds"], row["spectating_seconds"], row["uncertain_seconds"]) == (0.0, 0.0, 0.0, 0.0)
        assert row["completion"] == "unconfirmed" and row["english_chests"] is None


def test_a_heartbeat_without_this_match_claims_no_time_either():
    with folder() as f:
        rig = crashed(f)
        rig.writer.match_opened(opened(t=10.0))
        rig.writer.heartbeat(60.0, 900, 0)
        Rig(f).start(1, 1, 1)
        history = H.read(f)
        (row,) = history.matches
        assert row["closed_t"] == 60.0 and row["observed_seconds"] == 0.0 and row["active_seconds"] == 0.0 and row["uncertain_seconds"] == 50.0
        assert_sound(history.matches)


def test_a_heartbeat_from_an_earlier_match_is_not_used():
    with folder() as f:
        rig = crashed(f)
        rig.writer.match_opened(opened(number=2, t=70.0))
        rig.writer.heartbeat(80.0, 900, 0, match=snapshot(number=1))
        Rig(f).start(1, 1, 1)
        (row,) = H.read(f).matches
        assert row["match_number"] == 2 and row["observed_seconds"] == 0.0


def test_an_interrupted_match_is_never_complete():
    with folder() as f:
        rig = crashed(f)
        rig.writer.match_opened(opened(t=10.0))
        rig.writer.heartbeat(60.0, 900, 0, match=snapshot())
        rig.writer.transition({"t": 58.0, "previous": "IN_MATCH", "state": "ELIMINATED", "reason": "you_placed_seen", "match_number": 1})
        Rig(f).start(1, 1, 1)
        assert H.read(f).matches[0]["completion"] != "complete"


def test_an_unconfirmed_match_stays_unconfirmed():
    with folder() as f:
        rig = crashed(f)
        rig.writer.match_opened(opened(t=10.0))
        rig.writer.heartbeat(60.0, 900, 0, match=snapshot(english=False))
        Rig(f).start(1, 1, 1)
        assert H.read(f).matches[0]["completion"] == "unconfirmed"


def test_impossible_heartbeat_totals_cannot_break_the_time_rules():
    with folder() as f:
        rig = crashed(f)
        rig.writer.match_opened(opened(t=10.0))
        rig.writer.heartbeat(60.0, 900, 0, match=snapshot(opened_t=8.0, observed=500.0, active=400.0, spectating=300.0))
        Rig(f).start(1, 1, 1)
        history = H.read(f)
        assert_sound(history.matches)


def test_a_gap_marks_the_interrupted_match_incomplete():
    with folder() as f:
        rig = crashed(f, 1, 1)
        rig.writer.match_opened(opened(t=10.0))
        Rig(f).start(2, 2, 2)
        history = H.read(f)
        assert history.matches[0]["history_incomplete"] is True and history.gaps[0]["match_number"] == 1


def test_recovering_twice_changes_nothing():
    with folder() as f:
        rig = crashed(f, 1, 1)
        rig.writer.match_opened(opened(t=10.0))
        Rig(f).start(2, 2, 2).end(2, 2, 2)
        before = H.read(f)
        Rig(f).start(2, 2, 2)
        after = H.read(f)
        assert len(after.matches) == len(before.matches) == 1 and len(after.gaps) == len(before.gaps) == 1
        assert sum(1 for row in file_rows(f, H.MATCHES) if row["kind"] == "run_end" and row["run_id"] == "crashed") == 1


def test_a_finished_run_is_left_alone_when_another_one_crashed():
    with folder() as f:
        clean = Rig(f, run_id="clean").start()
        clean.writer.match_opened(opened(t=10.0))
        clean.writer.match_closed(record())
        clean.writer.chest(chest(1, 20.0), 1, 1)
        clean.end(1, 1, 1)
        crashed(f, 2, 2, run_id="crashed")
        before = {name: (f / name).read_bytes() for name in (H.MATCHES, H.CHESTS)}
        Rig(f).start(2, 2, 2)
        for name, content in before.items():
            assert (f / name).read_bytes().startswith(content), name
        rows = [row for row in file_rows(f, H.MATCHES) if row["run_id"] == "clean"]
        assert sum(row["kind"] == "run_end" for row in rows) == 1 and sum(row["kind"] == "match_closed" for row in rows) == 1
        history = H.read(f)
        assert not history.runs["clean"]["end"].get("interrupted") and history.runs["crashed"]["end"]["interrupted"]


def test_a_run_never_ends_with_a_match_left_open():
    """If the tracker stopped early, nothing closed the match. Ending the run closes it as interrupted, and recovery adds nothing later."""
    with folder() as f:
        clean = Rig(f, run_id="clean").start()
        clean.writer.match_opened(opened(t=10.0))
        clean.writer.heartbeat(60.0, 900, 0, match=snapshot(opened_t=8.0, observed=50.0, active=40.0, spectating=5.0))
        clean.end()
        crashed(f, 0, 0, run_id="crashed")
        Rig(f).start(0, 0, 0)
        history = H.read(f)
        (row,) = [m for m in history.matches if m["run_id"] == "clean"]
        assert row["interrupted"] is True and row["completion"] != "complete" and row["active_seconds"] == 40.0 and history.open_matches == []
        assert_sound([row])


def test_a_restarted_session_cannot_reuse_an_identity():
    """The epoch restarts at 0 in a new process, which is safe only because the run id is always new."""
    with folder() as f:
        first = Rig(f)
        first.start()
        first.writer.chest(chest(1, 10.0), 1, 1)                          # then the process dies
        second = Rig(f)
        second.start(1, 1, 1)
        second.writer.chest(chest(1, 10.0), 2, 2)                         # same event id, epoch and source time
        assert first.writer.run_id != second.writer.run_id
        got = H.read(f).chests
        assert len(got) == 2 and {row["counter_epoch"] for row in got} == {0} and {row["run_id"] for row in got} == {first.writer.run_id, second.writer.run_id}


def test_run_ids_do_not_repeat_within_the_same_second():
    assert len({H.new_run_id() for _ in range(5000)}) == 5000


def test_recovery_rows_cannot_collide_with_the_crashed_runs_rows():
    with folder() as f:
        rig = crashed(f, 1, 1, run_id="crashed")
        rig.writer.match_opened(opened(t=10.0))
        recovering = Rig(f, run_id="recovering")
        recovering.start(2, 2, 2)
        rows = file_rows(f, H.MATCHES)
        assert len({row["id"] for row in rows}) == len(rows)
        assert {row["id"].rpartition(":")[0] for row in rows if row["run_id"] == "crashed" and row["kind"] in ("match_closed", "gap", "run_end")} == {"recovering"}


def test_an_epoch_within_a_run_survives_a_failed_write():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 10.0), 1, 1)
        with patch.object(rig.writer, "_append", side_effect=OSError("locked")):
            rig.writer.counter_changed("reset", 0, 0)
            rig.writer.chest(chest(1, 20.0), 1, 1)
        rig.writer.chest(chest(2, 30.0), 2, 2)
        got = rig.read().chests
        assert [(r["counter_epoch"], r["event_id"]) for r in got] == [(0, "E0001"), (1, "E0001"), (1, "E0002")]


def test_repeated_delivery_is_still_ignored_after_a_reset():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 10.0), 1, 1)
        rig.writer.counter_changed("reset", 0, 0)
        assert rig.writer.chest(chest(1, 50.0), 1, 1) is True
        assert rig.writer.chest(chest(1, 50.0), 1, 1) is False
        rig.writer.chest(chest(2, 60.0), 2, 2)
        rig.writer.chest(chest(1, 70.0), 1, 1)                            # an unannounced restart
        assert rig.writer.chest(chest(1, 70.0), 1, 1) is False
        assert len(rig.read().chests) == 4


def test_a_truncated_history_never_invents_time_during_recovery():
    """Cut the file at every byte of the last heartbeat, then recover. Whatever survives, no record may claim more than was reported."""
    with tempfile.TemporaryDirectory() as tmp, patch.object(H.os, "fsync"):
        source = Path(tmp) / "source"
        rig = crashed(source, 1, 1)
        rig.writer.match_opened(opened(t=10.0))
        rig.writer.heartbeat(30.0, 450, 0, match=snapshot(opened_t=8.0, observed=20.0, active=10.0, spectating=0.0))
        before_last = (source / H.MATCHES).read_bytes()
        rig.writer.heartbeat(60.0, 900, 0, match=snapshot(opened_t=8.0, observed=50.0, active=40.0, spectating=5.0))
        whole, chests = (source / H.MATCHES).read_bytes(), (source / H.CHESTS).read_bytes()
        for cut in range(len(before_last), len(whole) + 1):
            f = Path(tmp) / f"cut{cut}"
            f.mkdir()
            (f / H.MATCHES).write_bytes(whole[:cut])
            (f / H.CHESTS).write_bytes(chests)
            Rig(f).start(1, 1, 1)
            history = H.read(f)
            (row,) = history.matches
            full = cut >= len(whole) - 1
            assert row["closed_t"] == (60.0 if full else 30.0), (cut, row["closed_t"])
            assert row["active_seconds"] == (40.0 if full else 10.0) and row["completion"] != "complete", cut
            assert_sound(history.matches)


def test_a_reset_between_clean_runs_is_not_a_gap():
    with folder() as f:
        first = Rig(f, run_id="first").start()
        first.writer.chest(chest(1, 10.0), 5, 5)
        first.end(5, 5, 1)
        Rig(f, run_id="second").start(0, 0, 0)
        history = H.read(f)
        assert history.gaps == [] and not history.runs["first"]["end"].get("interrupted")


def test_a_recovery_cut_short_is_finished_without_duplicates():
    with folder() as f:
        rig = crashed(f, 1, 1)
        rig.writer.match_opened(opened(t=10.0))
        interrupted = Rig(f)
        real, calls = interrupted.writer._append, []

        def fail_on_run_end(name, line):
            if b'"kind":"run_end"' in line:
                raise OSError("disk full")
            real(name, line)

        with patch.object(interrupted.writer, "_append", fail_on_run_end):
            interrupted.start(2, 2, 2)                                    # closed the match and wrote the gap, then died
        history = H.read(f)
        assert history.runs["crashed"]["end"] is None and len(history.gaps) == 1 and len(history.matches) == 1
        Rig(f).start(2, 2, 2)
        history = H.read(f)
        assert history.runs["crashed"]["end"] is not None and len(history.gaps) == 1 and len(history.matches) == 1


def test_a_real_close_beats_an_interrupted_one():
    with folder() as f:
        rig = crashed(f)
        rig.writer.match_opened(opened(t=10.0))
        Rig(f).start(1, 1, 1)
        rig.writer.match_closed(record())
        (row,) = H.read(f).matches
        assert not row.get("interrupted") and row["completion"] == "complete"


def test_only_the_newest_unfinished_run_is_compared_with_the_totals():
    with folder() as f:
        crashed(f, 1, 1, run_id="older")
        history_writer = H.HistoryWriter(f, [].append, run_id="newer")
        history_writer._add(H.MATCHES, "run_start", source_type="stream", app_version="0.3.0", configured_analysis_fps=15, languages=[], certain_total=9, approximate_total=9, events_logged=9)
        Rig(f).start(9, 9, 9)
        history = H.read(f)
        assert history.gaps == [] and history.runs["older"]["end"]["interrupted"] and history.runs["newer"]["end"]["interrupted"]


def test_a_history_that_cannot_be_read_does_not_stop_a_new_run():
    with folder() as f:
        rig = Rig(f)
        with patch.object(H, "read", side_effect=PermissionError("locked")):
            rig.start()
        assert len(rig.warnings) == 1 and H.read(f).runs[rig.writer.run_id]["start"] is not None


# ------------------------------------------------------------------ newer versions and corrections

def newer_row(run_id="future"):
    return b'{"kind":"chest","schema":2,"id":"future:1","run_id":"' + run_id.encode() + b'","new_field":[1,2]}\n'


def test_a_newer_row_is_skipped_with_a_notice_and_left_alone():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 10.0), 1, 1)
        H._append_line(f / H.CHESTS, newer_row())
        before = (f / H.CHESTS).read_bytes()
        notices = []
        history = H.read(f, warn=notices.append)
        assert len(history.chests) == 1 and history.newer_rows == 1 and len(notices) == 1 and "newer version" in notices[0]
        rig.writer.chest(chest(2, 20.0), 2, 2)
        assert (f / H.CHESTS).read_bytes().startswith(before)


def test_recovery_leaves_newer_rows_alone():
    with folder() as f:
        H._append_line(f / H.MATCHES, b'{"kind":"run_start","schema":2,"id":"future:1","run_id":"future"}\n')
        before = (f / H.MATCHES).read_bytes()
        Rig(f).start()
        history = H.read(f)
        assert (f / H.MATCHES).read_bytes().startswith(before) and "future" not in history.runs


def test_extra_fields_on_a_known_row_are_tolerated():
    with folder() as f:
        rig = Rig(f).start()
        H._append_line(f / H.CHESTS, H._encode({"kind": "chest", "schema": 1, "id": "other:1", "run_id": "other", "counter_epoch": 0, "event_id": "E0001", "t": 1.0,
                                                "certain_total": 1, "approximate_total": 1, "added_later": True}))
        assert len(rig.read().chests) == 1


def test_not_a_match_changes_only_the_derived_view():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 20.0), 1, 1)
        rig.writer.match_closed(record())
        chests_before, matches_before = (f / H.CHESTS).read_bytes(), (f / H.MATCHES).read_bytes()
        H.correct_match(f, rig.writer.run_id, 1)
        assert rig.read().matches[0]["not_a_match"] is True
        assert (f / H.CHESTS).read_bytes() == chests_before and (f / H.MATCHES).read_bytes().startswith(matches_before)


def test_the_latest_correction_wins():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.match_closed(record())
        H.correct_match(f, rig.writer.run_id, 1)
        H.correct_match(f, rig.writer.run_id, 1, not_a_match=False)
        assert rig.read().matches[0]["not_a_match"] is False
        H.correct_match(f, rig.writer.run_id, 1)
        assert rig.read().matches[0]["not_a_match"] is True


def test_a_correction_targets_one_run_only():
    with folder() as f:
        one = Rig(f, run_id="one").start()
        one.writer.match_closed(record())
        one.end()
        two = Rig(f, run_id="two").start()
        two.writer.match_closed(record())
        H.correct_match(f, "one", 1)
        got = {m["run_id"]: m["not_a_match"] for m in H.read(f).matches}
        assert got == {"one": True, "two": False}


def test_reset_and_edit_keep_history_and_are_logged():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.chest(chest(1, 10.0), 1, 1)
        rig.writer.counter_changed("reset", 0, 0)
        rig.writer.counter_changed("edit", 150, 150)
        history = rig.read()
        assert len(history.chests) == 1 and [(c["action"], c["certain_total"]) for c in history.counter_changes] == [("reset", 0), ("edit", 150)]


# ------------------------------------------------------------------ profiles

def state_base(tmp):
    return Path(tmp) / "state" / "chest_state.json"


def seeded(base, profile_id):
    f = profiles.history_folder(base, profile_id)
    rig = Rig(f).start()
    rig.writer.chest(chest(1, 10.0), 1, 1)
    return f


def test_each_profile_has_its_own_folder():
    with tempfile.TemporaryDirectory() as tmp:
        base = state_base(tmp)
        assert profiles.history_folder(base, "default") == base.parent / "history" / "default"
        a, b = seeded(base, "alice"), profiles.history_folder(base, "bob")
        assert len(H.read(a).chests) == 1 and H.read(b).chests == [] and not b.exists()


def test_renaming_a_profile_leaves_its_history_in_place():
    with tempfile.TemporaryDirectory() as tmp:
        base = state_base(tmp)
        entry = profiles.create(base, "Alice")
        f = seeded(base, entry["id"])
        profiles.rename(base, entry["id"], "Someone Else")
        assert profiles.history_folder(base, entry["id"]) == f and len(H.read(f).chests) == 1


def test_deleting_a_profile_moves_its_history_and_erases_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        base = state_base(tmp)
        entry = profiles.create(base, "Alice")
        f = seeded(base, entry["id"])
        contents = (f / H.CHESTS).read_bytes()
        moved = profiles.delete(base, entry["id"])
        assert moved is not None and moved.exists() and not f.exists()
        (kept,) = (base.parent / "history" / "deleted").iterdir()
        assert kept.name.startswith(entry["id"] + "-") and (kept / H.CHESTS).read_bytes() == contents


def test_a_new_profile_reusing_the_id_starts_empty():
    with tempfile.TemporaryDirectory() as tmp:
        base = state_base(tmp)
        entry = profiles.create(base, "Alice")
        seeded(base, entry["id"])
        profiles.delete(base, entry["id"])
        again = profiles.create(base, "Alice")
        assert again["id"] == entry["id"] and H.read(profiles.history_folder(base, again["id"])).chests == []


def test_deleting_twice_in_one_second_keeps_both_histories():
    with tempfile.TemporaryDirectory() as tmp, patch.object(profiles.time, "strftime", lambda *a: "same"):
        base = state_base(tmp)
        for _ in range(2):
            entry = profiles.create(base, "Alice")
            seeded(base, entry["id"])
            with patch.object(profiles, "profile_state_path", lambda b, p: Path(tmp) / "absent.json"):
                profiles.delete(base, entry["id"])
            profiles.profile_state_path(base, entry["id"]).unlink()
        assert len(list((base.parent / "history" / "deleted").iterdir())) == 2


def test_a_locked_history_stops_the_delete_with_nothing_changed():
    with tempfile.TemporaryDirectory() as tmp:
        base = state_base(tmp)
        entry = profiles.create(base, "Alice")
        f = seeded(base, entry["id"])
        counter = profiles.profile_state_path(base, entry["id"])
        real = Path.replace

        def locked(self, target):
            if self == f:
                raise PermissionError("in use")
            return real(self, target)

        with patch.object(Path, "replace", locked):
            try:
                profiles.delete(base, entry["id"])
            except profiles.ProfileError as error:
                assert "Nothing was deleted" in str(error)
            else:
                raise AssertionError("the delete went ahead")
        assert f.exists() and counter.exists() and profiles.get(profiles.load(base), entry["id"])


def test_a_failed_counter_move_puts_the_history_back():
    with tempfile.TemporaryDirectory() as tmp:
        base = state_base(tmp)
        entry = profiles.create(base, "Alice")
        f = seeded(base, entry["id"])
        counter = profiles.profile_state_path(base, entry["id"])
        real = Path.replace

        def locked(self, target):
            if self == counter:
                raise PermissionError("in use")
            return real(self, target)

        with patch.object(Path, "replace", locked):
            try:
                profiles.delete(base, entry["id"])
            except OSError:
                pass
            else:
                raise AssertionError("the delete went ahead")
        assert f.exists() and len(H.read(f).chests) == 1


def test_deleting_a_profile_without_history_works_as_before():
    with tempfile.TemporaryDirectory() as tmp:
        base = state_base(tmp)
        entry = profiles.create(base, "Alice")
        assert profiles.delete(base, entry["id"]).exists() and not (base.parent / "history").exists()


def test_the_default_profile_is_still_protected():
    with tempfile.TemporaryDirectory() as tmp:
        base = state_base(tmp)
        f = seeded(base, "default")
        try:
            profiles.delete(base, "default")
        except profiles.ProfileError:
            assert f.exists()
            return
    raise AssertionError("Default was deleted")


def test_history_cannot_be_mistaken_for_a_profile():
    with tempfile.TemporaryDirectory() as tmp:
        base = state_base(tmp)
        seeded(base, "alice")
        registry = profiles._rebuild(base)
        assert [p["id"] for p in registry["profiles"]] == ["default"]


# ------------------------------------------------------------------ isolation

def test_history_depends_only_on_the_standard_library():
    tree = ast.parse((ROOT / "src/fortnite_chest_counter/match_history.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert imported == {"bisect", "functools", "json", "os", "uuid", "collections", "dataclasses", "datetime", "pathlib"}, imported


def test_only_the_counter_opens_history_and_only_lazily():
    src = ROOT / "src/fortnite_chest_counter"
    for file in src.rglob("*.py"):
        if file.name not in ("match_history.py", "counter.py", "match_tracker.py", "match_analytics.py", "app.py"):
            assert "match_history" not in file.read_text(encoding="utf-8"), file.name
    tree = ast.parse((src / "counter.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert "match" not in " ".join([alias.name for alias in node.names] + [getattr(node, "module", None) or ""]), ast.dump(node)
    tracker = ast.parse((src / "match_tracker.py").read_text(encoding="utf-8"))
    assert not [n for n in ast.walk(tracker) if isinstance(n, ast.ImportFrom) and "match_history" in " ".join(a.name for a in n.names)]


def test_reading_creates_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "history" / "nobody"
        history = H.read(f)
        assert not f.exists() and history.runs == {} and history.chests == []


def test_a_session_only_ever_appends():
    with folder() as f:
        rig = Rig(f).start()
        sizes = {}
        steps = [lambda: rig.writer.chest(chest(1, 10.0), 1, 1), lambda: rig.writer.match_opened(opened()), lambda: rig.writer.heartbeat(20.0, 300, 0),
                 lambda: rig.writer.chest_type("E0001", 10.0, "rare"), lambda: rig.writer.counter_changed("reset", 0, 0), lambda: rig.writer.match_closed(record()),
                 lambda: H.correct_match(f, rig.writer.run_id, 1), lambda: rig.end()]
        for step in steps:
            before = {p.name: p.read_bytes() for p in f.iterdir()}
            step()
            for name, content in before.items():
                assert (f / name).read_bytes().startswith(content), name
        assert not rig.warnings


def test_two_writers_interleaved_stay_separate():
    with folder() as f:
        one, two = Rig(f, run_id="one"), Rig(f, run_id="two")
        for i in range(1, 6):
            one.writer.chest(chest(i, i * 1.0), i, i)
            two.writer.chest(chest(i, i * 1.0), i, i)
        got = H.read(f).chests
        assert len(got) == 10 and {r["run_id"] for r in got} == {"one", "two"}


def test_the_updater_keeps_history_and_the_build_rejects_it():
    staging = (ROOT / "src/fortnite_chest_counter/update/staging.py").read_text(encoding="utf-8")
    assert 'USER_OWNED = ("state",' in staging
    assert '".jsonl"' in (ROOT / "packaging/build_release.py").read_text(encoding="utf-8")


# ------------------------------------------------------------------ the evidence future statistics need

def test_the_stored_evidence_can_answer_the_planned_statistics():
    """Calculated here, in the test, on purpose: M5 stores evidence and implements no statistics. Proves nothing was thrown away."""
    with folder() as f:
        rig = Rig(f, run_id="run").start()
        steps = [(0.0, "UNKNOWN", "LOBBY"), (30.0, "LOBBY", "LOADING"), (50.0, "LOADING", "PRE_GAME"), (100.0, "PRE_GAME", "IN_MATCH"), (400.0, "IN_MATCH", "ELIMINATED"), (420.0, "ELIMINATED", "LOBBY")]
        for t, previous, state in steps:
            rig.writer.transition({"t": t, "previous": previous, "state": state, "reason": "x", "match_number": 1 if state in ("IN_MATCH", "ELIMINATED") else None})
        rig.writer.match_closed({**record(1, 50.0, 420.0, active=300.0), "observed_seconds": 370.0, "spectating_seconds": 20.0, "uncertain_seconds": 0.0, "played_from_t": 100.0,
                                 "ended_t": 400.0, "complete_duration_seconds": 300.0})
        rig.writer.match_closed({**record(2, 500.0, 560.0, active=60.0, completion="partial", ended_by="stopped"), "observed_seconds": 60.0, "spectating_seconds": 0.0, "complete_duration_seconds": None, "ended_t": None})
        for i, (t, certain) in enumerate([(120.0, True), (180.0, True), (240.0, False), (520.0, True)], 1):
            rig.writer.chest(chest(i, t, certain=certain), i, i)
        rig.end(t=560.0)
        history = rig.read()
        matches = sorted(history.matches, key=lambda m: m["match_number"])
        complete = [m for m in matches if m["completion"] == "complete"]
        assert statistics.mean(m["complete_duration_seconds"] for m in complete) == 300.0
        assert sum(m["active_seconds"] for m in matches) == 360.0 and sum(m["observed_seconds"] for m in matches) == 430.0
        moments = [(row["t"], row["state"]) for row in history.transitions] + [(560.0, None)]
        in_state = {}
        for (t, state), (following, _) in zip(moments, moments[1:]):
            in_state[state] = in_state.get(state, 0) + following - t
        assert in_state["LOADING"] == 20.0 and in_state["PRE_GAME"] == 50.0 and in_state["IN_MATCH"] == 300.0 and in_state["ELIMINATED"] == 20.0
        first = matches[0]
        inside = [c for c in history.chests if first["played_from_t"] <= c["t"] < first["ended_t"]]
        certain_rate = sum(c["certain_counted"] for c in inside) / (first["active_seconds"] / 60)
        approx_rate = sum(c["approx_counted"] for c in inside) / (first["active_seconds"] / 60)
        assert (certain_rate, approx_rate) == (0.4, 0.6)
        times = sorted(c["t"] for c in inside)
        assert statistics.mean(b - a for a, b in zip(times, times[1:])) == 60.0
        run = history.runs["run"]
        assert run["end"]["frames_processed"] / run["end"]["elapsed_seconds"] != run["start"]["configured_analysis_fps"]     # achieved and configured stay distinct


# ------------------------------------------------------------------ reading at scale

def synthetic_history(f, matches=5000, heartbeats=4, transitions=6):
    """A realistic file: the rows a listing skips still have to be read past. Four heartbeats is one every five minutes of a 20-minute match."""
    f.mkdir(parents=True, exist_ok=True)
    at, out, n = "2026-11-11T10:00:00.000+01:00", bytearray(), 0
    for i in range(1, matches + 1):
        row = {k: v for k, v in record(i, i * 1000.0, i * 1000.0 + 900.0).items() if k != "respawns"}
        for kind, fields, repeat in (("heartbeat", {"t": i * 1000.0, "frames_processed": 900, "frames_dropped": 0, "match": snapshot(i)}, heartbeats),
                                     ("transition", {"t": i * 1000.0, "previous": "IN_MATCH", "state": "ELIMINATED", "reason": "you_placed_seen", "match_number": i}, transitions),
                                     ("match_closed", row, 1)):
            for _ in range(repeat):
                n += 1
                out += H._encode({"kind": kind, "schema": 1, "id": f"run:{n}", "run_id": "run", "at": at, **fields})
    (f / H.MATCHES).write_bytes(bytes(out))


def test_a_normal_start_does_not_parse_the_whole_history():
    with folder() as f:
        Rig(f).start().end()
        real, kinds = H.read, []
        with patch.object(H, "read", lambda folder, only=None, warn=None: (kinds.append(only), real(folder, only, warn))[1]):
            Rig(f).start()
        assert kinds == [H.RUN_KINDS], kinds


def test_listing_5000_matches_takes_under_100_ms():
    with folder() as f:
        synthetic_history(f)
        measured = []
        for _ in range(5):
            begin = time.perf_counter()
            history = H.read(f, only=H.MATCH_KINDS)
            measured.append(1000 * (time.perf_counter() - begin))
            assert len(history.matches) == 5000
            if measured[-1] < 100:
                return
    raise AssertionError(f"{measured} ms is over the 100 ms budget")


def test_limiting_the_kinds_skips_the_rest():
    with folder() as f:
        rig = Rig(f).start()
        rig.writer.heartbeat(10.0, 150, 0)
        rig.writer.transition({"t": 1.0, "previous": "UNKNOWN", "state": "LOBBY", "reason": "x", "match_number": None})
        rig.writer.chest(chest(1, 5.0), 1, 1)
        history = H.read(f, only=H.MATCH_KINDS)
        assert history.transitions == [] and history.chests == [] and history.runs[rig.writer.run_id]["last_heartbeat"] is None
        assert history.runs[rig.writer.run_id]["start"] is not None


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
    print(f"{len(tests) - failed}/{len(tests)} match history checks passed")
    sys.exit(1 if failed else 0)
