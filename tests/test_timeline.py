"""
Real-life time (v0.4.0, M1): runs become wall-clock intervals, runs group into sessions without pretending the gaps were watched, days and weeks
fall where the calendar puts them (daylight saving included), and history is kept whenever counts are saved, with match rows only when match
tracking is on. Every expected value was worked out by hand.

Run:   python tests/test_timeline.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "tests"))

import contextlib
import io
import json
import subprocess
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fortnite_chest_counter import counter as C
from fortnite_chest_counter import match_analytics as A
from fortnite_chest_counter import match_history as H
from fortnite_chest_counter import match_tracker as MT
from fortnite_chest_counter import timeline as TL

import history_fixtures as F
import test_match_recording as MR
import test_match_tracker as T

UTC = timezone.utc
V030_KINDS = {"run_start", "run_end", "heartbeat", "transition", "match_opened", "match_closed", "counter_change", "gap", "correction",
              "chest", "chest_type", "chest_correction", "chest_correction_undone", "chest_correction_reason"}


@contextlib.contextmanager
def recorder():
    with tempfile.TemporaryDirectory() as tmp:
        yield F.Recorder(Path(tmp) / "history" / "p")


def timeline_of(rec, now=None, running=None, full=False):
    history = rec.read(full)
    unended = [run_id for run_id, run in history.runs.items() if run["end"] is None]
    return TL.runs(history, H.last_heartbeats(rec.folder, unended), now=now, running=running)


# ------------------------------------------------------------------ one run

def test_a_clean_run_lasts_its_own_elapsed_time():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 03:38:12")).chests(88.6, 422).beats(4300).end(4345.5)
        (run,) = timeline_of(rec)
    assert run.start == F.moment("2026-11-12 03:38:12") and run.seconds == 4345.5 and run.ended_cleanly and not run.cut_short
    assert run.end == F.moment("2026-11-12 04:50:37.5")


def test_a_changed_clock_cannot_stretch_a_run():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 20:00:00")).end(600, clock_drift=3600)      # the PC's clock jumped an hour forward meanwhile
        (run,) = timeline_of(rec)
    assert run.seconds == 600 and run.clock_changed


def test_a_small_difference_is_not_a_clock_change():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 20:00:00")).end(600, clock_drift=90)
        (run,) = timeline_of(rec)
    assert run.seconds == 600 and not run.clock_changed


def test_a_crashed_run_lasts_until_its_last_heartbeat_at_least():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 21:00:00")).chests(30, 400).beats(1500).crash()           # heartbeats at 0, 60, ..., 1500
        (run,) = timeline_of(rec)
        full = TL.runs(rec.read(full=True))                     # the same, from a full read that carries the heartbeats itself
    assert run.seconds == 1500 and run.cut_short and not run.ended_cleanly
    assert full[0].seconds == 1500


def test_a_crashed_run_without_its_heartbeats_read_is_not_stretched():
    with recorder() as rec:
        rec.run(F.moment("2026-11-01 21:00:00")).beats(1500).crash()
        (run,) = TL.runs(rec.read(), now=F.moment("2026-11-12 21:00:00"))    # heartbeats not read and none given: only its start is known
    assert run.seconds == 0 and run.cut_short


def test_recovery_days_later_does_not_count_as_counting():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 21:00:00")).beats(1200).crash()
        rec.run(F.moment("2026-11-15 18:00:00")).end(300)       # three days later: recovery writes the old run's run_end now
        rows = MR.rows_of(rec.folder)
        first, second = timeline_of(rec)
    recovery = next(row for row in rows if row["kind"] == "run_end" and row.get("interrupted"))
    assert TL.parse_at(recovery["at"]) == F.moment("2026-11-15 18:00:00")                     # the trap: its `at` is the recovery
    assert first.seconds == 1200 and first.cut_short and second.seconds == 300


def test_a_run_that_crashed_before_any_heartbeat_has_no_length():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 21:00:00")).crash()
        rec.run(F.moment("2026-11-12 22:00:00")).end(60)
        first, _ = timeline_of(rec)
    assert first.seconds == 0 and first.cut_short


def test_the_run_counting_now_lasts_until_now():
    with recorder() as rec:
        writer = rec.run(F.moment("2026-11-12 21:00:00")).beats(120)
        (run,) = timeline_of(rec, now=F.moment("2026-11-12 21:10:00"), running=writer.run_id)
    assert run.seconds == 600 and run.in_progress and not run.cut_short


def test_simulate_runs_are_nobodys_play():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 21:00:00"), source="simulate").chests(10).end(60)
        rec.run(F.moment("2026-11-12 22:00:00"), source="stream").end(60)
        runs = timeline_of(rec)
    assert [run.source_type for run in runs] == ["stream"]


def test_a_time_without_its_offset_is_not_guessed():
    assert TL.parse_at("2026-11-12T21:00:00") is None and TL.parse_at(None) is None and TL.parse_at("soon") is None
    assert TL.parse_at("2026-11-12T21:00:00.000+01:00") == datetime(2026, 11, 12, 20, 0, tzinfo=UTC)


def test_runs_come_out_oldest_first():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 22:00:00"), run_id="later").end(60)
        rec.run(F.moment("2026-11-12 21:00:00"), run_id="earlier").end(60)
        assert [run.run_id for run in timeline_of(rec)] == ["earlier", "later"]


# ------------------------------------------------------------------ last heartbeats

def test_last_heartbeats_reads_only_the_runs_asked_for():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 21:00:00"), run_id="a").beats(180).match(1, 190, 190, 200, 5).crash()     # match rows come after
        rec.run(F.moment("2026-11-12 22:00:00"), run_id="b").beats(120).end(130)
        with open(rec.folder / H.MATCHES, "ab") as f:
            f.write(b'{"kind":"heartbeat","run_id":"a", damaged\n')
        found = H.last_heartbeats(rec.folder, ["a", "missing"])
    assert set(found) == {"a"} and found["a"]["t"] == 180.0


def test_last_heartbeats_takes_the_newest_by_write_order():
    with recorder() as rec:
        writer = rec.run(F.moment("2026-11-12 21:00:00"), run_id="a").beats(120)
        lines = (rec.folder / H.MATCHES).read_bytes().splitlines(keepends=True)
        beats = [line for line in lines if line.startswith(b'{"kind":"heartbeat"')]
        rest = [line for line in lines if not line.startswith(b'{"kind":"heartbeat"')]
        (rec.folder / H.MATCHES).write_bytes(b"".join(rest + beats[::-1]))       # reversed on disk
        assert H.last_heartbeats(rec.folder, ["a"])["a"]["t"] == 120.0
        assert H.last_heartbeats(rec.folder / "nowhere", ["a"]) == {} and H.last_heartbeats(rec.folder, []) == {}
        writer.crash()


# ------------------------------------------------------------------ sessions

def test_runs_less_than_thirty_minutes_apart_are_one_session_and_the_gap_is_not_counting():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 20:00:00")).end(3600)                          # 20:00-21:00
        rec.run(F.moment("2026-11-12 21:29:59")).end(1800)                          # 29:59 later, until 21:59:59
        rec.run(F.moment("2026-11-12 22:29:59")).end(600)                           # exactly 30:00 later: a new session
        first, second = TL.sessions(timeline_of(rec))
    assert len(first.runs) == 2 and first.span_seconds == 3600 + 1799 + 1800 and first.counted_seconds == 5400 and first.gap_seconds == 1799
    assert len(second.runs) == 1 and second.span_seconds == 600 and second.gap_seconds == 0


def test_overlapping_runs_are_not_counted_twice():
    a = TL.Run("a", "desktop", F.moment("2026-11-12 20:00:00"), F.moment("2026-11-12 21:00:00"), True)
    b = TL.Run("b", "desktop", F.moment("2026-11-12 20:30:00"), F.moment("2026-11-12 21:10:00"), True)
    (session,) = TL.sessions([b, a])
    assert session.counted_seconds == 70 * 60 and session.span_seconds == 70 * 60 and session.gap_seconds == 0
    assert session.start == a.start and session.end == b.end


def test_a_session_with_a_crashed_run_is_cut_short_and_one_counting_now_is_in_progress():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 20:00:00")).beats(600).crash()
        live = rec.run(F.moment("2026-11-12 20:20:00")).beats(60)
        (session,) = TL.sessions(timeline_of(rec, now=F.moment("2026-11-12 20:30:00"), running=live.run_id))
    assert session.cut_short and session.in_progress and session.counted_seconds == 600 + 600 and session.gap_seconds == 600


def test_the_break_limit_can_be_given():
    a = TL.Run("a", "desktop", F.moment("2026-11-12 20:00:00"), F.moment("2026-11-12 20:10:00"), True)
    b = TL.Run("b", "desktop", F.moment("2026-11-12 20:20:00"), F.moment("2026-11-12 20:30:00"), True)
    assert len(TL.sessions([a, b])) == 1 and len(TL.sessions([a, b], break_seconds=600)) == 2


# ------------------------------------------------------------------ calendar

def test_a_run_across_midnight_is_split_between_the_two_days():
    run = TL.Run("a", "desktop", F.moment("2026-11-12 23:30:00"), F.moment("2026-11-13 01:15:00"), True)
    assert TL.counted_by_day([run], F.CET) == {date(2026, 11, 12): 1800.0, date(2026, 11, 13): 4500.0}


def test_overlapping_runs_count_once_on_their_day():
    a = TL.Run("a", "desktop", F.moment("2026-11-12 20:00:00"), F.moment("2026-11-12 21:00:00"), True)
    b = TL.Run("b", "desktop", F.moment("2026-11-12 20:30:00"), F.moment("2026-11-12 21:30:00"), True)
    assert TL.counted_by_day([a, b], F.CET) == {date(2026, 11, 12): 5400.0}


def test_the_spring_day_has_23_hours_and_the_autumn_day_25():
    spring = TL.Run("s", "desktop", F.moment("2026-03-28 22:00:00"), F.moment("2026-03-30 02:00:00"), True)
    autumn = TL.Run("a", "desktop", F.moment("2026-10-24 22:00:00"), F.moment("2026-10-26 02:00:00"), True)
    assert TL.counted_by_day([spring], F.CET)[date(2026, 3, 29)] == 23 * 3600
    assert TL.counted_by_day([autumn], F.CET)[date(2026, 10, 25)] == 25 * 3600
    assert spring.seconds == 27 * 3600 and autumn.seconds == 29 * 3600


def test_a_session_across_the_autumn_change_keeps_its_real_length():
    with recorder() as rec:
        rec.run(F.moment("2026-10-25 01:30:00")).end(2 * 3600)                     # 01:30 CEST to 02:30 CET: two real hours
        (run,) = timeline_of(rec)
    assert run.seconds == 7200 and TL.local(run.end, F.CET).hour == 2


def test_day_start_and_week_start():
    assert TL.day_start(date(2026, 3, 29), F.CET) == datetime(2026, 3, 28, 23, 0, tzinfo=UTC)
    assert TL.day_start(date(2026, 3, 30), F.CET) == datetime(2026, 3, 29, 22, 0, tzinfo=UTC)
    assert TL.week_start(date(2026, 11, 12)) == date(2026, 11, 9) and TL.week_start(date(2026, 11, 9)) == date(2026, 11, 9)
    assert TL.week_start(date(2026, 11, 15)) == date(2026, 11, 9)
    assert TL.days_from(date(2026, 11, 30), date(2026, 12, 2)) == [date(2026, 11, 30), date(2026, 12, 1), date(2026, 12, 2)]
    assert TL.days_from(date(2026, 12, 2), date(2026, 11, 30)) == []


def test_the_pcs_own_zone_is_used_when_none_is_given():
    moment = datetime(2026, 11, 12, 23, 30, tzinfo=UTC)                     # on the next day wherever the PC is east of UTC
    assert TL.local(moment).utcoffset() == moment.astimezone().utcoffset() and TL.day_of(moment) == moment.astimezone().date()
    start = TL.day_start(date(2026, 11, 12))
    assert start.astimezone().date() == date(2026, 11, 12) and start.astimezone().hour == 0


def test_clip_and_totals():
    a, b = F.moment("2026-11-12 20:00:00"), F.moment("2026-11-12 22:00:00")
    assert TL.total_seconds(TL.clip([(a, b)], F.moment("2026-11-12 21:00:00"), F.moment("2026-11-13 00:00:00"))) == 3600
    assert TL.clip([(a, b)], b, F.moment("2026-11-13 00:00:00")) == []


# ------------------------------------------------------------------ the live loop (D7)

def rows_written(tmp):
    folder = MR.history_of(tmp)
    matches = [json.loads(line) for line in (folder / H.MATCHES).read_bytes().splitlines() if line]
    chests = [json.loads(line) for line in (folder / H.CHESTS).read_bytes().splitlines() if line]
    return matches, chests


def test_history_is_kept_with_match_tracking_off_or_in_shadow_but_without_match_rows():
    for mode in ("off", "shadow"):
        with tempfile.TemporaryDirectory() as tmp:
            T.run_command(tmp, "live", mode, items=T.scripted_frames(seconds=130))
            matches, chests = rows_written(tmp)
        kinds = [row["kind"] for row in matches]
        assert kinds[0] == "run_start" and kinds[-1] == "run_end" and "heartbeat" in kinds, (mode, kinds)
        assert not {"match_opened", "match_closed", "transition"} & set(kinds), (mode, kinds)
        assert len([row for row in chests if row["kind"] == "chest"]) == 3, mode
        beats = [row["t"] for row in matches if row["kind"] == "heartbeat"]
        assert len(beats) >= 130 // 60 and beats == sorted(set(beats)), (mode, beats)
        assert all(b - a >= 59 for a, b in zip(beats, beats[1:])), (mode, beats)                 # every heartbeat_seconds, not every frame


def test_with_tracking_on_only_the_tracker_writes_heartbeats():
    with tempfile.TemporaryDirectory() as on, patch.object(C.HistoryHeartbeat, "offer", lambda self, t, tracker: None):
        T.run_command(on, "live", "on", items=T.scripted_frames(seconds=130))
        tracked = [row["t"] for row in rows_written(on)[0] if row["kind"] == "heartbeat"]
    with tempfile.TemporaryDirectory() as both:
        T.run_command(both, "live", "on", items=T.scripted_frames(seconds=130))
        written = [row["t"] for row in rows_written(both)[0] if row["kind"] == "heartbeat"]
    assert tracked and written == tracked, (written, tracked)              # the fallback added nothing while the tracker kept history


def test_a_tracker_that_stops_after_an_error_hands_the_heartbeats_over():
    calls = {"n": 0}
    real = MT.MatchTracker._offer

    def failing(self, t, frame):
        calls["n"] += 1
        if t >= 30:
            raise RuntimeError("broken")
        return real(self, t, frame)

    with tempfile.TemporaryDirectory() as tmp, patch.object(MT.MatchTracker, "_offer", failing):
        T.run_command(tmp, "live", "on", items=T.scripted_frames(seconds=200))
        beats = [row["t"] for row in rows_written(tmp)[0] if row["kind"] == "heartbeat"]
    assert max(beats) >= 150 and beats == sorted(beats), beats             # tracking stopped near 30 s, the run stayed visible


def test_counting_is_the_same_whether_history_is_kept_or_not():
    def counted(tmp, extra):
        with T.scripted_pipeline(T.scripted_frames()), contextlib.redirect_stdout(io.StringIO()) as out:
            assert C.main(["live", "--source", "file", "--reset", *T.folders(tmp), "--match-mode", "off", *extra]) == 0, out.getvalue()
        tmp = Path(tmp)
        log = [json.loads(line) for line in next((tmp / "l").glob("*.jsonl")).read_text(encoding="utf-8").splitlines()]
        return ({f.name: f.read_bytes() for f in sorted((tmp / "o").iterdir())},
                [{k: v for k, v in row.items() if k not in ("logged_at", "latency_s", "obs_write_s")} for row in log if "time" in row])

    with tempfile.TemporaryDirectory() as kept, tempfile.TemporaryDirectory() as unsaved:
        result = counted(kept, [])
        plain = counted(unsaved, ["--config", str(MR.toml(unsaved, "[state]\npersist = false\n"))])
        assert (Path(kept) / "history").exists() and not (Path(unsaved) / "history").exists()
    assert result == plain and len(result[1]) >= 3, (result, plain)


def test_tracking_off_loads_the_history_writer_but_none_of_the_match_code():
    code = ("import sys; sys.path.insert(0, 'src')\n"
            "from fortnite_chest_counter import counter as C\n"
            "assert C._tracker_history({'match': {'mode': 'off'}}, object()) is None\n"
            "assert C._tracker_history({'match': {'mode': 'shadow'}}, object()) is None\n"
            "assert C._open_tracker({'match': {'mode': 'off'}, 'logging': {'enabled': True}}, None) is None\n"
            "assert not [m for m in sys.modules if m.split('.')[-1] in ('match_tracker', 'match_cues', 'match_state')]\n")
    subprocess.run([sys.executable, "-c", code], check=True, cwd=ROOT, capture_output=True, timeout=120)


def test_history_writes_only_row_kinds_v030_knows():
    for mode in ("off", "on"):
        with tempfile.TemporaryDirectory() as tmp:
            T.run_command(tmp, "live", mode)
            matches, chests = rows_written(tmp)
        assert {row["kind"] for row in matches + chests} <= V030_KINDS and {row["schema"] for row in matches + chests} == {1}, mode


def test_analysing_a_recording_still_never_enters_history():
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "clip.mp4"
        video.write_bytes(b"not read: the frames are scripted")
        config = MR.toml(tmp, '[match]\nmode = "off"\n')
        with T.scripted_pipeline(T.scripted_frames()), contextlib.redirect_stdout(io.StringIO()):
            assert C.main(["video", str(video), "--config", str(config), "--state", str(Path(tmp) / "s.json"), "--obs-dir", str(Path(tmp) / "o"),
                           "--log-dir", str(Path(tmp) / "l")]) == 0
        assert not (Path(tmp) / "history").exists()


def test_a_real_off_run_reads_as_one_clean_run_of_its_length():
    with tempfile.TemporaryDirectory() as tmp:
        T.run_command(tmp, "live", "off", items=T.scripted_frames(seconds=130))
        history = H.read(MR.history_of(tmp), only=A.READ_KINDS)
    (run,) = TL.runs(history)
    assert run.ended_cleanly and run.source_type == "file" and run.seconds >= 0


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
    print(f"{len(tests) - failed}/{len(tests)} timeline checks passed")
    sys.exit(1 if failed else 0)
