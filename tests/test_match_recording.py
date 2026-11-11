"""
Match recording, "on" mode (v0.3.0, M6): the live loop writes match history, checkpoints at a chosen interval, recovers from a real process
kill, and cannot change counting. The whole-loop tests run the real live and simulate commands with a scripted source and detector. No video
is decoded here; research/match_shadow_check.py does that on short windows of the reference clips.

Run:   python tests/test_match_recording.py     (or pytest)
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
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from fortnite_chest_counter import counter as C
from fortnite_chest_counter import match_cues as M
from fortnite_chest_counter import match_history as H
from fortnite_chest_counter import match_state as S
from fortnite_chest_counter import match_tracker as MT
from fortnite_chest_counter import profiles, settings

import match_scorecard as SC
import test_match_state as M2
import test_match_tracker as T

HP = M2.HP
INTERVALS = (30, 60, 300, 600)


class Recording(T.Rig):
    """test_match_state.Script's interface, with every sample going through a tracker wired to a real history."""

    def __init__(self, folder, heartbeat=60, fps=1, run_id=None):
        self.folder, self.history_warnings = Path(folder), []
        self.writer = H.HistoryWriter(folder, self.history_warnings.append, run_id=run_id)
        self.writer.start_run("file", "0.3.0", 15, ["en"], 0, 0, 0, heartbeat)
        self.counted = 0
        super().__init__(fps=fps, history=self.writer, heartbeat_seconds=heartbeat, frames=lambda: (0, 0))

    def add_chest(self, onset, language="en", certain=True):
        self.counted += 1
        self.writer.chest({"event_id": f"E{self.counted:04d}", "time": onset, "certain_counted": certain, "approx_counted": True, "popup_template": f"{language}:CHEST",
                           "adjusted_tier": "HIGH", "source": "popup"}, self.counted, self.counted)
        return self

    def end(self, reason="Q pressed"):
        self.tracker.close(reason)
        self.writer.end_run(self.t, reason, 0, 0, 1.0, self.counted, self.counted, self.counted)
        return self

    def stored(self):
        return H.read(self.folder)

    def rows(self, kind):
        return [row for row in rows_of(self.folder) if row["kind"] == kind]


def rows_of(folder):
    return [json.loads(line) for line in (Path(folder) / H.MATCHES).read_bytes().splitlines() if line]


def assert_sound(records):
    """Per run: match numbers and source time both start again in each one."""
    for run_id in {row.get("run_id") for row in records}:
        errors = SC.record_errors([row for row in records if row.get("run_id") == run_id])
        assert not errors, errors


@contextlib.contextmanager
def folder():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp) / "history" / "someone"


def recover(f, certain=0, approximate=0):
    H.HistoryWriter(f, [].append).start_run("file", "0.3.0", 15, ["en"], certain, approximate, 0, 60)
    return H.read(f)


def toml(tmp, text):
    path = Path(tmp) / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def history_of(tmp):
    return Path(tmp) / "history" / "s"


# ------------------------------------------------------------------ settings

def test_recording_is_off_by_default_and_the_interval_is_a_minute():
    assert settings.DEFAULTS["match"] == {"mode": "off", "heartbeat_seconds": 60}


def test_every_offered_interval_is_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        for seconds in INTERVALS:
            cfg, _, warnings = settings.load_config(toml(tmp, f"[match]\nheartbeat_seconds = {seconds}\n"))
            assert cfg["match"]["heartbeat_seconds"] == seconds and warnings == [], (seconds, warnings)


def test_anything_else_falls_back_to_a_minute():
    with tempfile.TemporaryDirectory() as tmp:
        for value in ("0", "1", "59", "61", "-60", "60.0", '"60"', "true", "[60]"):
            cfg, _, warnings = settings.load_config(toml(tmp, f"[match]\nheartbeat_seconds = {value}\n"))
            assert cfg["match"]["heartbeat_seconds"] == 60 and len(warnings) == 1, (value, warnings)


# ------------------------------------------------------------------ the interval

def test_checkpoints_follow_the_interval():
    for interval in INTERVALS:
        with folder() as f:
            rec = M2.start_match(Recording(f, heartbeat=interval)).show(1300, health=HP)
            beats = [row["t"] for row in rec.rows("heartbeat")]
            forced = {row["t"] for row in rec.rows("match_opened")}
            spacing = [(b - a, b) for a, b in zip(beats, beats[1:])]
            assert all(gap <= interval + 1 for gap, _ in spacing), (interval, spacing)
            assert all(gap >= interval - 1e-6 for gap, later in spacing if later not in forced), (interval, spacing)
            assert len(beats) >= 1300 // interval, (interval, len(beats))


def test_the_interval_changes_only_the_checkpoints():
    results = []
    for interval in INTERVALS:
        with folder() as f:
            rec = M2.played_match(Recording(f, heartbeat=interval)).show(700, health=HP).show(10, "you_placed", health=40).show(5, "connecting").end()
            results.append((json.dumps(rec.records), json.dumps(rec.lines("transition")), len(rec.cues.seen), json.dumps([{k: v for k, v in m.items() if k not in ("at", "id", "run_id")} for m in rec.stored().matches])))
    assert len(set(results)) == 1, [r[2] for r in results]


def test_sampling_stays_at_one_per_second_for_every_interval():
    for interval in INTERVALS:
        with folder() as f:
            rec = Recording(f, heartbeat=interval, fps=15).show(120, health=HP)
            assert len(rec.cues.seen) == 120, (interval, len(rec.cues.seen))


def test_a_checkpoint_holds_the_running_totals():
    with folder() as f:
        rec = M2.played_match(Recording(f, heartbeat=30)).show(8, black=True).show(200, health=HP)
        beats = [row for row in rec.rows("heartbeat") if row["match"]]
        assert len(beats) > 4
        for beat in beats:
            snap = beat["match"]
            assert abs(snap["observed_seconds"] + snap["uncertain_seconds"] - (beat["t"] - snap["opened_t"])) < 0.01, beat
            assert snap["active_seconds"] + snap["spectating_seconds"] <= snap["observed_seconds"] + 0.01, beat


def test_checkpoints_are_written_at_match_boundaries():
    with folder() as f:
        rec = M2.played_match(Recording(f, heartbeat=600)).show(10, "you_placed", health=40).show(5, "connecting")
        beats = {row["t"] for row in rec.rows("heartbeat")}
        opened, (closed,) = rec.rows("match_opened")[0]["t"], rec.rows("match_closed")
        assert opened in beats and closed["closed_t"] in beats, (opened, closed["closed_t"], beats)


def test_stopping_writes_a_final_checkpoint():
    with folder() as f:
        rec = M2.played_match(Recording(f, heartbeat=600))
        last = rec.t - 1
        rec.end()
        assert rec.rows("heartbeat")[-1]["t"] == last


def test_no_checkpoint_covers_a_gap_in_the_video():
    with folder() as f:
        rec = M2.played_match(Recording(f, heartbeat=30))
        gap_from = rec.t
        rec.jump(40).show(3, health=HP)
        beats = rec.rows("heartbeat")
        assert not [b for b in beats if gap_from <= b["t"] < gap_from + 40]
        after = next(b for b in beats if b["t"] >= gap_from + 40)
        assert after["match"]["uncertain_seconds"] >= 40, after


def test_every_interval_recovers_without_inventing_time():
    for interval in INTERVALS:
        for played in (13, 61, 301, 650):
            with folder() as f:
                rec = M2.start_match(Recording(f, heartbeat=interval, run_id="dead")).show(played, health=HP)
                truth = rec.tracker._machine.snapshot()
                history = recover(f)
                (row,) = history.matches
                assert row["interrupted"] is True and row["completion"] != S.COMPLETE and row["ended_by"] == H.INTERRUPTED, (interval, played)
                assert row["active_seconds"] <= truth["active_seconds"] and row["observed_seconds"] <= truth["observed_seconds"], (interval, played, row, truth)
                assert truth["active_seconds"] - row["active_seconds"] <= interval + 1, (interval, played, row, truth)
                assert_sound(history.matches)


def test_changing_the_setting_between_runs_is_safe():
    with folder() as f:
        first = M2.start_match(Recording(f, heartbeat=600, run_id="first")).show(100, health=HP)
        truth = first.tracker._machine.snapshot()
        second = M2.played_match(Recording(f, heartbeat=30, run_id="second")).show(10, "you_placed", health=40).show(5, "connecting").end()
        history = second.stored()
        by_run = {m["run_id"]: m for m in history.matches}
        assert by_run["first"]["interrupted"] and by_run["first"]["active_seconds"] <= truth["active_seconds"] and by_run["second"]["completion"] == S.COMPLETE
        assert (history.runs["first"]["start"]["heartbeat_seconds"], history.runs["second"]["start"]["heartbeat_seconds"]) == (600, 30)
        assert_sound(history.matches)


def test_a_setting_changed_while_counting_waits_for_the_next_run():
    class Rewriting(T.ScriptedSource):
        def frames(self):
            for index, item in enumerate(super().frames()):
                if index == 100:
                    Rewriting.config.write_text('[match]\nheartbeat_seconds = 600\n', encoding="utf-8")
                    time.sleep(1.2)                                       # long enough for the running counter to re-read its settings
                yield item

    with tempfile.TemporaryDirectory() as tmp, patch.object(T, "ScriptedSource", Rewriting):
        Rewriting.config = toml(tmp, '[match]\nheartbeat_seconds = 30\n')
        T.run_command(tmp, "live", "on", items=T.scripted_frames(seconds=100), extra=["--config", str(Rewriting.config)])
        beats = [row["t"] for row in rows_of(history_of(tmp)) if row["kind"] == "heartbeat"]
    assert len(beats) >= 100 // 30, beats


# ------------------------------------------------------------------ what a run records

def run_all(command, modes=("off", "shadow", "on")):
    results = {}
    for mode in modes:
        with tempfile.TemporaryDirectory() as tmp:
            results[mode] = T.run_command(tmp, command, mode)[0]
    return results


def test_live_counts_the_same_in_every_mode():
    results = run_all("live")
    assert results["off"] == results["shadow"] == results["on"]
    assert (results["on"]["state"]["certain"], results["on"]["state"]["approximate"]) == (2, 3)


def test_simulate_counts_the_same_in_every_mode():
    results = run_all("simulate")
    assert results["off"] == results["shadow"] == results["on"]


def test_the_desktop_app_sees_no_difference():
    def shape(messages):
        return [(m["type"], sorted(m)) for m in messages if m["type"] != "status"]

    with tempfile.TemporaryDirectory() as off, tempfile.TemporaryDirectory() as on:
        plain, _, plain_messages = T.run_app(off, "off")
        recorded, _, recorded_messages = T.run_app(on, "on")
    assert plain == recorded and shape(plain_messages) == shape(recorded_messages), (shape(plain_messages), shape(recorded_messages))


def test_only_on_keeps_a_history():
    for mode in ("off", "shadow"):
        with tempfile.TemporaryDirectory() as tmp:
            T.run_command(tmp, "live", mode)
            assert not (Path(tmp) / "history").exists(), mode


def test_off_and_shadow_load_no_history_code():
    code = ("import sys; sys.path.insert(0, 'src')\n"
            "from fortnite_chest_counter import counter as C\n"
            "class Session: persist = True\n"
            "for mode in ('off', 'shadow'):\n"
            "    assert C._open_history({'match': {'mode': mode}}, Session(), 'file') is None\n"
            "assert 'fortnite_chest_counter.match_history' not in sys.modules\n")
    subprocess.run([sys.executable, "-c", code], check=True, cwd=ROOT, capture_output=True, timeout=120)


def test_on_records_the_whole_run():
    with tempfile.TemporaryDirectory() as tmp:
        result, log = T.run_command(tmp, "live", "on")
        history = H.read(history_of(tmp))
        rows = rows_of(history_of(tmp))
    (run,) = history.runs.values()
    start, end = run["start"], run["end"]
    assert start["source_type"] == "file" and start["configured_analysis_fps"] == 15 and start["languages"] == ["en", "pt"] and start["heartbeat_seconds"] == 60 and start["app_version"]
    assert (start["certain_total"], start["approximate_total"], start["events_logged"]) == (0, 0, 0)
    assert end["stop_reason"] == "stream ended" and end["frames_processed"] == 100 and end["frames_dropped"] == 0 and end["elapsed_seconds"] is not None and not end.get("interrupted")
    assert (end["certain_total"], end["approximate_total"]) == (2, 3)
    assert {"run_start", "heartbeat", "transition", "match_opened", "match_closed", "run_end"} <= {row["kind"] for row in rows}
    assert next(row for row in log if row.get("event") == "session_end")["match_mode"] == "on"


def test_simulate_runs_end_cleanly():
    with tempfile.TemporaryDirectory() as tmp:
        T.run_command(tmp, "simulate", "on")
        (run,) = H.read(history_of(tmp)).runs.values()
    assert run["start"]["source_type"] == "simulate" and run["end"]["stop_reason"] == "stream ended" and run["end"]["frames_processed"] == 100 and not run["end"].get("interrupted")


def test_history_chests_equal_the_runs_increase_in_the_totals():
    for command in ("live", "simulate"):
        with tempfile.TemporaryDirectory() as tmp:
            result, _ = T.run_command(tmp, command, "on")
            chests = H.read(history_of(tmp)).chests
        assert sum(c["certain_counted"] for c in chests) == result["state"]["certain"], command
        assert sum(c["approx_counted"] for c in chests) == result["state"]["approximate"], command
        assert all(c["language"] in ("en", "pt") and c["adjusted_tier"] and c["at"] for c in chests), chests


def test_a_second_run_continues_from_the_saved_totals():
    with tempfile.TemporaryDirectory() as tmp, T.scripted_pipeline(T.scripted_frames()), contextlib.redirect_stdout(io.StringIO()):
        for _ in range(2):
            assert C.main(["live", "--source", "file", *T.folders(tmp), "--match-mode", "on"]) == 0
        history = H.read(history_of(tmp))
    starts = [run["start"]["certain_total"] for run in history.runs.values()]
    assert starts == [0, 2] and len(history.chests) == 6 and history.gaps == [], (starts, history.gaps)


def real_cfg(tmp):
    cfg, _, _ = settings.load_config(None, {("state", "path"): str(Path(tmp) / "s.json"), ("state", "obs_dir"): str(Path(tmp) / "o"), ("logging", "dir"): str(Path(tmp) / "l"), ("match", "mode"): "on"})
    return cfg


def event(t, certain=True, approx=True):
    return {"time": t, "source": "popup", "adjusted_tier": "HIGH", "certain_counted": certain, "approx_counted": approx, "reason": "check", "popup_template": "en:CHEST"}


@contextlib.contextmanager
def real_session():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = real_cfg(tmp)
        session = C.CounterSession(cfg, reset=True)
        session.save()
        session.history = H.HistoryWriter(Path(tmp) / "h", [].append)
        session.history.start_run("file", "0.3.0", 15, ["en"], 0, 0, 0, 60)
        yield session, cfg, Path(tmp) / "h"


def test_the_totals_are_saved_before_history():
    with real_session() as (session, cfg, _):
        seen = []
        real = session.history.chest

        def spy(ev, certain, approximate):
            seen.append(json.loads(Path(cfg["state"]["path"]).read_text(encoding="utf-8"))["certain"])
            return real(ev, certain, approximate)

        with patch.object(session.history, "chest", spy):
            session.apply([event(10.0)], 13.0, quiet=True)
        assert seen == [1], seen


def test_uncounted_events_never_reach_history():
    with real_session() as (session, _, f):
        session.apply([event(10.0, certain=False, approx=False)], 13.0, quiet=True)
        assert H.read(f).chests == []


def test_a_better_chest_type_reaches_history():
    with real_session() as (session, _, f):
        session.apply([{**event(10.123456), "chest_type": "unknown"}], 13.0, quiet=True)
        session.apply_type_updates([{"time": 10.123456, "chest_type": "rare", "type_confidence": 0.9, "type_evidence": "x"}])
        assert H.read(f).chests[0]["chest_type"] == "rare"


def test_a_reset_while_counting_keeps_both_chests():
    with real_session() as (session, cfg, f):
        first = session.apply([event(10.0)], 13.0, quiet=True)[0]
        time.sleep(0.05)
        C.CounterSession(cfg, reset=True).save()
        second = session.apply([event(50.0)], 53.0, quiet=True)[0]
        history = H.read(f)
        assert first["event_id"] == second["event_id"] and len(history.chests) == 2 and len(history.counter_changes) == 1


def test_a_reset_that_leaves_the_counts_unchanged_still_starts_a_new_epoch():
    """sync_external_changes reports "no change" here, because the numbers match, though the event ids restarted."""
    with real_session() as (session, cfg, f):
        session.apply([event(10.0)], 13.0, quiet=True)
        time.sleep(0.05)
        other = C.CounterSession(cfg)
        other.state["events_logged"] = 0
        other.save()
        assert session.sync_external_changes() is False
        session.apply([event(50.0)], 53.0, quiet=True)
        history = H.read(f)
        assert [c["counter_epoch"] for c in history.chests] == [0, 1] and len(history.counter_changes) == 1


def test_repeated_delivery_through_the_session_counts_once():
    with real_session() as (session, _, f):
        applied = session.apply([event(10.0)], 13.0, quiet=True)[0]
        session.history.chest(applied, 1, 1)
        assert len(H.read(f).chests) == 1


# ------------------------------------------------------------------ failures cannot reach counting

def test_a_history_that_cannot_be_written_cannot_touch_the_session():
    with tempfile.TemporaryDirectory() as off, tempfile.TemporaryDirectory() as on:
        (Path(on) / "history").write_text("a file where the folder should be", encoding="utf-8")
        plain, _, _ = T.run_app(off, "off")
        recorded, _, messages = T.run_app(on, "on")
    assert plain == recorded and messages[-1]["type"] == "stopped"
    warnings = [m for m in messages if m["type"] == "warn" and "match history" in m["text"]]
    assert len(warnings) == 1, messages


def test_a_bug_in_history_cannot_touch_the_session():
    with tempfile.TemporaryDirectory() as off, tempfile.TemporaryDirectory() as on:
        plain, _, _ = T.run_app(off, "off")
        with patch.object(H, "_encode", side_effect=RuntimeError("injected")):
            recorded, _, messages = T.run_app(on, "on")
    assert plain == recorded and len([m for m in messages if m["type"] == "warn" and "match history" in m["text"]]) == 1


def test_a_history_that_cannot_start_cannot_touch_the_session():
    with tempfile.TemporaryDirectory() as off, tempfile.TemporaryDirectory() as on:
        plain, _ = T.run_command(off, "live", "off")
        with patch.object(H.HistoryWriter, "__init__", side_effect=RuntimeError("injected")):
            recorded, log = T.run_command(on, "live", "on")
    assert plain == recorded and next(row for row in log if row.get("event") == "session_end")["match_mode"] == "shadow"


def test_a_tracker_failure_loses_only_match_data():
    calls = []
    real_read = M.CueReader.read

    def failing(self, frame, signals=None):
        calls.append(1)
        if len(calls) == 12:
            raise RuntimeError("injected")
        return real_read(self, frame, signals)

    with tempfile.TemporaryDirectory() as off, tempfile.TemporaryDirectory() as on:
        plain, _ = T.run_command(off, "live", "off")
        with patch.object(M.CueReader, "read", failing):
            recorded, _ = T.run_command(on, "live", "on")
        history = H.read(history_of(on))
    assert plain == recorded and len(history.chests) == 3
    (row,) = history.matches
    assert row["interrupted"] is True and row["completion"] != S.COMPLETE and history.open_matches == [], row
    assert_sound(history.matches)


def test_a_tracker_that_cannot_start_still_keeps_the_chests():
    with tempfile.TemporaryDirectory() as on, tempfile.TemporaryDirectory() as empty, patch.object(M, "TEMPLATE_DIR", Path(empty)):
        T.run_command(on, "live", "on")
        history = H.read(history_of(on))
    assert len(history.chests) == 3 and history.matches == [] and next(iter(history.runs.values()))["end"] is not None


def test_nothing_is_kept_when_saving_is_turned_off():
    with tempfile.TemporaryDirectory() as tmp:
        config = toml(tmp, "[state]\npersist = false\n")
        with T.scripted_pipeline(T.scripted_frames()), contextlib.redirect_stdout(io.StringIO()) as out:
            code = C.main(["live", "--source", "file", "--config", str(config), "--state", str(Path(tmp) / "s.json"), "--obs-dir", str(Path(tmp) / "o"), "--log-dir", str(Path(tmp) / "l"), "--match-mode", "on"])
        assert code == 0 and not (Path(tmp) / "history").exists() and "needs saving turned on" in out.getvalue(), out.getvalue()


def test_analysing_a_recording_never_enters_history():
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "clip.mp4"
        video.write_bytes(b"not read: the frames are scripted")
        config = toml(tmp, '[match]\nmode = "on"\n')
        with T.scripted_pipeline(T.scripted_frames()), contextlib.redirect_stdout(io.StringIO()):
            assert C.main(["video", str(video), "--config", str(config), "--state", str(Path(tmp) / "s.json"), "--obs-dir", str(Path(tmp) / "o"), "--log-dir", str(Path(tmp) / "l")]) == 0
        assert not (Path(tmp) / "history").exists()


# ------------------------------------------------------------------ where history goes

def test_two_explicit_state_files_stay_apart():
    with tempfile.TemporaryDirectory() as tmp:
        a = C._history_folder({"state": {"path": str(Path(tmp) / "one.json")}})
        b = C._history_folder({"state": {"path": str(Path(tmp) / "two.json")}})
        assert a != b and a.parent == b.parent == Path(tmp) / "history"


def test_each_profile_records_into_its_own_history():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "state" / "chest_state.json"
        config = toml(tmp, f'[state]\npath = "{base.as_posix()}"\nobs_dir = "{(Path(tmp) / "o").as_posix()}"\n[logging]\ndir = "{(Path(tmp) / "l").as_posix()}"\n[match]\nmode = "on"\n')
        entry = profiles.create(base, "Alice", activate=False)
        with T.scripted_pipeline(T.scripted_frames()), contextlib.redirect_stdout(io.StringIO()):
            assert C.main(["live", "--source", "file", "--config", str(config)]) == 0
        with T.scripted_pipeline(T.scripted_frames()), contextlib.redirect_stdout(io.StringIO()):
            assert C.main(["live", "--source", "file", "--config", str(config), "--profile", "Alice"]) == 0
        default, alice = profiles.history_folder(base, "default"), profiles.history_folder(base, entry["id"])
        assert len(H.read(default).chests) == 3 and len(H.read(alice).chests) == 3
        assert {c["run_id"] for c in H.read(default).chests}.isdisjoint({c["run_id"] for c in H.read(alice).chests})
        profiles.rename(base, entry["id"], "Someone Else")
        assert len(H.read(alice).chests) == 3
        profiles.delete(base, entry["id"])
        assert not alice.exists() and len(H.read(default).chests) == 3


# ------------------------------------------------------------------ which match a chest belongs to

def attributed(rec):
    return H.attribute(H.read(rec.folder))


def test_a_chest_finishing_after_you_placed_counts_by_its_own_time():
    with folder() as f:
        rec = M2.played_match(Recording(f))
        onset = rec.t - 1
        rec.show(10, "you_placed", health=40).add_chest(onset).show(5, "connecting").end()
        (row,) = attributed(rec)
        assert row["match_number"] == 1 and row["credited"] is True and row["spectating"] is False, row


def test_a_chest_while_spectating_is_flagged_and_not_credited():
    with folder() as f:
        rec = M2.played_match(Recording(f)).show(5, "spectating", health=HP)
        rec.show(5, health=HP).add_chest(rec.t - 1).show(5, "connecting").end()
        (row,) = attributed(rec)
        assert row["match_number"] == 1 and row["spectating"] is True and row["credited"] is False, row


def test_a_chest_after_the_ending_is_not_credited():
    with folder() as f:
        rec = M2.played_match(Recording(f)).show(10, "victory_royale", health=HP)
        rec.show(20, health=HP).add_chest(rec.t - 1).show(5, "connecting").end()
        (row,) = attributed(rec)
        assert row["spectating"] is True and row["credited"] is False, row


def test_a_chest_outside_every_match_belongs_to_none():
    with folder() as f:
        rec = M2.played_match(Recording(f).add_chest(0.5)).show(10, "you_placed", health=40).show(5, "connecting").end()     # a match exists, later in the run
        assert len(rec.stored().matches) == 1
        (row,) = attributed(rec)
        assert row["match_number"] is None and row["credited"] is False, row


def test_a_chest_on_the_pre_game_island_is_not_credited():
    with folder() as f:
        rec = Recording(f).show(5, "lobby_menu").show(8, "connecting").show(20, "waiting_for_players", health=HP)
        onset = rec.t - 5
        rec.show(10, "bus_launching", health=HP).show(6).show(60, health=HP).add_chest(onset).show(10, "you_placed", health=40).show(5, "connecting").end()
        (row,) = attributed(rec)
        assert row["match_number"] == 1 and row["credited"] is False and row["spectating"] is False, row


def test_a_chest_in_a_not_a_match_is_not_credited():
    with folder() as f:
        rec = M2.played_match(Recording(f, run_id="r"))
        rec.add_chest(rec.t - 1).show(10, "you_placed", health=40).show(5, "connecting").end()
        assert attributed(rec)[0]["credited"] is True
        H.correct_match(f, "r", 1)
        assert attributed(rec)[0]["credited"] is False


def test_attribution_stays_within_a_run():
    with folder() as f:
        first = M2.played_match(Recording(f, run_id="a")).show(5, "connecting").end()
        second = Recording(f, run_id="b").add_chest(50.0).end()
        (row,) = H.attribute(H.read(f))
        assert row["run_id"] == "b" and row["match_number"] is None, row


def test_joining_late_is_partial_with_its_observed_time():
    with folder() as f:
        rec = Recording(f).show(60, health=HP).add_chest(30.0).show(1, health=HP).end()
        (row,) = rec.stored().matches
        assert row["completion"] != S.COMPLETE and row["observed_from_start"] is False and row["observed_seconds"] > 50 and row["complete_duration_seconds"] is None, row
        assert_sound([row])


def test_stopping_mid_match_is_partial_ending_as_stopped():
    with folder() as f:
        rec = M2.played_match(Recording(f)).end("Q pressed")
        (row,) = rec.stored().matches
        assert (row["completion"], row["ended_by"]) == (S.PARTIAL, S.STOPPED) and not row.get("interrupted"), row


def test_a_gap_in_the_live_loop_stays_honest():
    items = T.scripted_frames(seconds=20)
    items = items[:50] + [(t + 90, frame) for t, frame in items[50:]]     # 90 s with no video, after 10 s of play
    with tempfile.TemporaryDirectory() as tmp:
        T.run_command(tmp, "live", "on", items=items)
        history = H.read(history_of(tmp))
    assert history.matches and not [m for m in history.matches if m["completion"] == S.COMPLETE]
    assert history.matches[0]["ended_by"] == S.LOST and history.matches[0]["active_seconds"] <= 11
    assert_sound(history.matches)


# ------------------------------------------------------------------ a real process kill

KILLED_RUN = """
import pathlib, sys, time
root = pathlib.Path(sys.argv[1])
for name in ("src", "research", "tests"):
    sys.path.insert(0, str(root / name))
import test_match_tracker as T
tmp, config = pathlib.Path(sys.argv[2]), sys.argv[3]

class Hanging(T.ScriptedSource):
    def frames(self):
        for index, item in enumerate(super().frames()):
            if index == 200:                       # 40 s of source time: after the checkpoint at 30 s
                (tmp / "ready").write_text("x")
                time.sleep(600)
            yield item

T.ScriptedSource = Hanging
T.run_command(tmp, "live", "on", items=T.scripted_frames(seconds=60), extra=["--config", config])
"""


def test_a_killed_process_is_recovered_at_the_next_start():
    """TerminateProcess: no Python cleanup runs, exactly like Task Manager or a power cut to the process."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        config = toml(tmp, "[match]\nheartbeat_seconds = 30\n")
        process = subprocess.Popen([sys.executable, "-c", KILLED_RUN, str(ROOT), str(tmp), str(config)], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 90
        while not (tmp / "ready").exists():
            assert time.monotonic() < deadline and process.poll() is None, "the run never reached the kill point"
            time.sleep(0.05)
        process.kill()
        process.wait(timeout=30)
        before = H.read(history_of(tmp))
        assert len(before.open_matches) == 1 and next(iter(before.runs.values()))["end"] is None
        state_before = json.loads((tmp / "s.json").read_text(encoding="utf-8"))
        with T.scripted_pipeline(T.scripted_frames(seconds=5)), contextlib.redirect_stdout(io.StringIO()):
            assert C.main(["live", "--source", "file", *T.folders(tmp), "--config", str(config), "--match-mode", "on"]) == 0
        history = H.read(history_of(tmp))
        dead = next(iter(history.runs.values()))
        (row,) = [m for m in history.matches if m["run_id"] == dead["start"]["run_id"]]
        assert dead["end"]["interrupted"] is True and row["interrupted"] is True and row["completion"] != S.COMPLETE, row
        assert row["closed_t"] <= 40.0 and row["active_seconds"] <= row["closed_t"], row
        assert history.gaps == [] and len([c for c in history.chests if c["run_id"] == dead["start"]["run_id"]]) == 2, history.gaps
        assert (state_before["certain"], state_before["approximate"]) == (1, 2)
        assert_sound(history.matches)


# ------------------------------------------------------------------ the state machine is only read

def test_taking_a_snapshot_changes_no_decision():
    for name, rows in M2.TIMELINES.items():
        plain, watched, outcomes = S.MatchStateMachine(), S.MatchStateMachine(), ([], [])
        for t, scores, health, black, frozen in rows:
            observation = S.Observation(t, scores, health, bool(black), bool(frozen))
            outcomes[0].extend(plain.update(observation))
            outcomes[1].extend(watched.update(observation))
            watched.snapshot()
        outcomes[0].extend(plain.finish(rows[-1][0] + 1))
        outcomes[1].extend(watched.finish(rows[-1][0] + 1))
        assert [repr(e) for e in outcomes[0]] == [repr(e) for e in outcomes[1]], name


def test_a_snapshot_reports_the_open_match_and_nothing_otherwise():
    machine = S.MatchStateMachine()
    assert machine.snapshot() is None
    script = M2.Script()
    script.machine = machine
    M2.played_match(script).show(2, black=True)
    snap = script.machine.snapshot()
    assert snap["match_number"] == 1 and snap["active_seconds"] > 50 and snap["uncertain_seconds"] > 0 and snap["english_confirmed"] is True and set(snap) == set(H.SNAPSHOT_FIELDS)
    (record,) = [e for e in script.machine.finish(script.t - 1) if isinstance(e, S.MatchRecord)]      # closing at the snapshot's own moment adds no time
    assert (snap["observed_seconds"], snap["active_seconds"], snap["spectating_seconds"], snap["uncertain_seconds"]) == (record.observed_seconds, record.active_seconds, record.spectating_seconds, record.uncertain_seconds)
    assert (snap["opened_t"], snap["played_from_t"]) == (record.opened_t, record.played_from_t) and snap["active_seconds"] < snap["observed_seconds"]
    assert script.machine.snapshot() is None


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
    print(f"{len(tests) - failed}/{len(tests)} match recording checks passed")
    sys.exit(1 if failed else 0)
