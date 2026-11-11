"""
Match tracker, shadow mode (v0.3.0, M4): it reads frames about once a second of source time, reports only to the session log, and cannot
change or stop counting. The whole-loop tests run the real live and simulate commands with a scripted source and detector. No video is
decoded here; research/match_shadow_check.py does that on short windows of the reference clips.

Run:   python tests/test_match_tracker.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))                                     # run without installing
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "tests"))

import ast
import contextlib
import hashlib
import io
import json
import os
import random
import subprocess
import tempfile
import time
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from fortnite_chest_counter import counter as C
from fortnite_chest_counter import match_cues as M
from fortnite_chest_counter import match_state as S
from fortnite_chest_counter import match_tracker as MT
from fortnite_chest_counter import paths, settings
from fortnite_chest_counter.console import CONSOLE

import match_replay as R
import match_scorecard as SC
import test_match_state as M2

HP = M2.HP


class Cues:
    """Stands in for match_cues: here a "frame" is a dict saying what the sample should report."""

    def __init__(self):
        self.seen, self.boom_at = [], None

    def CueReader(self):
        return self

    def read(self, frame):
        self.seen.append(frame)
        if len(self.seen) == self.boom_at:
            raise RuntimeError("injected reader failure")
        return frame["scores"]

    def hud_in_view(self, frame):
        return frame.get("hud")

    def health_bar_pixels(self, frame):
        return frame["health"]

    def picture_evidence(self, frame, previous):
        return SimpleNamespace(black=frame["black"], frozen=frame["frozen"], sample=None)


def fake_frame(t=0.0, scores=None, health=0, black=False, frozen=False):
    return {"t": t, "scores": scores or {}, "health": health, "black": black, "frozen": frozen}


def chest_event(t, language="en", certain=True, approx=True):
    return {"time": t, "popup_template": f"{language}:CHEST", "certain_counted": certain, "approx_counted": approx}


class Rig:
    """test_match_state.Script's interface, with every sample going through the tracker."""

    def __init__(self, start=0.0, fps=1, **kwargs):
        self.t, self.fps = start, fps
        self.log, self.warnings, self.cues = [], [], Cues()
        self.tracker = MT.MatchTracker(self.log.append, self.warnings.append, cues=self.cues, **kwargs)

    def show(self, seconds, *signals, health=0, black=False, frozen=False):
        start, count = self.t, round(seconds * self.fps)
        for i in range(count):
            t = start + i / self.fps
            self.tracker.offer(t, fake_frame(t, {s: 0.95 for s in signals}, health, black, frozen))
        self.t = start + count / self.fps
        return self

    def chest(self, language="en", onset=None, **kwargs):
        self.tracker.chest(chest_event(self.t - 3 if onset is None else onset, language, **kwargs))
        return self

    def jump(self, seconds):
        self.t += seconds
        return self

    def finish(self, reason="stream ended"):
        self.tracker.close(reason)
        return self

    def lines(self, kind):
        return [line for line in self.log if line["kind"] == kind]

    @property
    def records(self):
        return self.lines("record")

    @property
    def path(self):
        return [line["state"] for line in self.lines("transition")]

    @property
    def state(self):
        return self.tracker._machine.state


def assert_sound(records):
    errors = SC.record_errors(records)
    assert not errors, errors


def toml(tmp, text):
    path = Path(tmp) / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------------------ the [match] setting

def test_tracking_is_on_by_default():
    assert settings.DEFAULTS["match"]["mode"] == "on"


def test_shadow_can_be_chosen_in_the_config_and_on_the_command_line():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, _, warnings = settings.load_config(toml(tmp, '[match]\nmode = "shadow"\n'))
        assert cfg["match"]["mode"] == "shadow" and warnings == []
        cfg, _, warnings = settings.load_config(toml(tmp, ""), {("match", "mode"): "shadow"})
        assert cfg["match"]["mode"] == "shadow" and warnings == []


def test_on_can_be_chosen_explicitly():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, _, warnings = settings.load_config(toml(tmp, '[match]\nmode = "on"\n'))
        assert cfg["match"]["mode"] == "on" and warnings == [], warnings
        cfg, _, warnings = settings.load_config(toml(tmp, ""), {("match", "mode"): "on"})
        assert cfg["match"]["mode"] == "on" and warnings == [], warnings


def test_a_nonsense_mode_falls_back_to_off():
    with tempfile.TemporaryDirectory() as tmp:
        for value in ('"maybe"', "1", "true", "[]"):
            cfg, _, warnings = settings.load_config(toml(tmp, f"[match]\nmode = {value}\n"))
            assert cfg["match"]["mode"] == "off" and len(warnings) == 1, (value, warnings)


# ------------------------------------------------------------------ sampling by source time

def sampled_times(times):
    rig = Rig()
    for t in times:
        rig.tracker.offer(t, fake_frame(t))
    return [frame["t"] for frame in rig.cues.seen]


def test_one_sample_per_second_at_every_frame_rate():
    for fps in (5, 10, 15, 30):
        got = sampled_times([i / fps for i in range(120 * fps)])
        assert len(got) == 120, (fps, len(got))
        assert all(abs(b - a - 1) < 1e-6 for a, b in zip(got, got[1:])), fps


def test_the_sample_rate_does_not_drift_with_an_awkward_start_time():
    for fps in (5, 15):
        got = sampled_times([37.1 + i / fps for i in range(60 * fps)])
        assert len(got) == 60, (fps, len(got))


def test_samples_are_never_closer_than_a_second_when_the_frame_rate_varies():
    for seed in range(20):
        rng, t, times = random.Random(seed), 0.0, []
        while t < 300:
            times.append(t)
            t += rng.uniform(0.02, 0.4)
        got = sampled_times(times)
        spacing = [b - a for a, b in zip(got, got[1:])]
        assert min(spacing) >= 1 - 1e-6 and max(spacing) <= 1.4 + 1e-6, (seed, min(spacing), max(spacing))
        assert len(got) >= 300 / 1.4 - 1, (seed, len(got))


def test_a_jump_in_time_is_sampled_at_once():
    assert sampled_times([0.0, 1.0, 20.0, 20.1]) == [0.0, 1.0, 20.0]
    assert sampled_times([50.0, 51.0, 3.0, 3.1]) == [50.0, 51.0, 3.0]


# ------------------------------------------------------------------ real frames

def painted(*names, shade=90):
    """A 720p frame with the named cue words drawn where the game draws them."""
    frame = np.full((720, 1280, 3), shade, np.uint8)
    frame[200:400, 100:1100] = 60 + 3 * (shade % 7)
    for name in names:
        cue, template = M._CUE[name], np.load(M.TEMPLATE_DIR / f"{name}.npy")
        x0, y0 = cue.box[:2]
        height, width = template.shape
        ink, paper = (255, shade) if cue.ink == M.WHITE else (20, 230)
        frame[y0 + 2:y0 + 2 + height, x0 + 2:x0 + 2 + width] = np.where(template[..., None], ink, paper).astype(np.uint8)
    return frame


def with_health_bar(frame):
    frame[650:660, 50:200] = (30, 220, 30)
    return frame


def test_real_cues_reach_the_real_state_machine():
    log, warnings = [], []
    tracker = MT.MatchTracker(log.append, warnings.append)
    for i in range(4):
        tracker.offer(float(i), painted("connecting", shade=90 + i))
    assert warnings == [] and not tracker.failed
    assert [(line["previous"], line["state"]) for line in log if line["kind"] == "transition"] == [(S.UNKNOWN, S.LOADING)], log


def test_frames_are_only_read():
    log, warnings = [], []
    tracker = MT.MatchTracker(log.append, warnings.append)
    for i in range(5):
        frame = with_health_bar(painted("connecting", "spectating", shade=90 + i))
        before = hashlib.sha256(frame.tobytes()).hexdigest()
        frame.flags.writeable = False                                     # the same as a frame straight from FFmpeg
        tracker.offer(float(i), frame)
        assert hashlib.sha256(frame.tobytes()).hexdigest() == before
        assert not np.shares_memory(tracker._picture, frame)
    assert warnings == [] and not tracker.failed and tracker.stats()["match_samples"] == 5


def test_frames_are_not_changed_even_when_writable():
    log, warnings = [], []
    tracker = MT.MatchTracker(log.append, warnings.append)
    frame = with_health_bar(painted("you_placed_screen"))
    before = frame.copy()
    tracker.offer(0.0, frame)
    assert np.array_equal(frame, before) and not tracker.failed


# ------------------------------------------------------------------ chest evidence

def delivered(rig):
    return rig.tracker._chests["delivered"]


def test_only_counted_chests_are_evidence():
    rig = Rig().show(1)
    rig.tracker.chest(chest_event(0.5, certain=False, approx=False))
    rig.show(1)
    assert delivered(rig) == 0
    rig.tracker.chest(chest_event(1.5, certain=False, approx=True))
    rig.show(1)
    assert delivered(rig) == 1


def test_a_chest_is_delivered_once_with_its_language():
    machine = S.MatchStateMachine()
    observations = []
    real_update = machine.update
    machine.update = lambda o: (observations.append(o), real_update(o))[1]
    rig = Rig(machine=machine).show(1).chest("en").chest("pt").show(1).show(1)
    rig.tracker.chest({"time": 2.5, "popup_template": None, "certain_counted": False, "approx_counted": True})
    rig.show(1)
    assert [o.chests for o in observations] == [(), ("en", "pt"), (), ("unknown",)], observations


def test_the_event_is_not_changed():
    rig, ev = Rig().show(1), chest_event(0.5)
    before = dict(ev)
    rig.tracker.chest(ev)
    rig.show(1)
    assert ev == before


def test_a_chest_from_before_a_break_is_not_evidence_after_it():
    rig = M2.played_match(Rig()).jump(70)
    rig.tracker.chest(chest_event(rig.t - 75))                            # finished by the first frame after the outage
    rig.show(1)
    assert rig.tracker._machine.open_match_number is None and rig.state == S.UNKNOWN, rig.path
    assert rig.tracker._chests["dropped_at_break"] == 1 and delivered(rig) == 0


def test_a_chest_finishing_late_after_a_break_is_dropped_too():
    rig = M2.played_match(Rig()).jump(70).show(2)
    rig.tracker.chest(chest_event(rig.t - 72))
    rig.show(1)
    assert rig.tracker._machine.open_match_number is None and rig.tracker._chests["dropped_at_break"] == 1


def test_a_chest_after_the_break_counts():
    rig = M2.played_match(Rig()).jump(20).show(5, health=HP)
    rig.chest("en", onset=rig.t - 1).show(1, health=HP)
    assert delivered(rig) == 1 and rig.tracker._chests["dropped_at_break"] == 0


def test_a_chest_on_a_black_sample_is_not_saved_for_later():
    rig = Rig().show(5, health=HP).show(1, health=HP)
    rig.chest("en").show(1, black=True).show(3, health=HP)
    assert rig.tracker._chests["no_picture"] == 1 and delivered(rig) == 0


def test_chests_waiting_at_the_end_are_reported_not_used():
    rig = M2.played_match(Rig()).chest("en").finish()
    assert rig.lines("summary")[0]["chests_undelivered"] == 1 and rig.records[0]["english_chests"] == 0


# ------------------------------------------------------------------ same story as the offline replay

def test_the_tracker_tells_the_same_story_as_the_offline_replay():
    baselines = {"new": "en", "ps5": "ps5"}
    for name, rows in M2.TIMELINES.items():
        chests = []
        if name in baselines:
            frozen = json.loads((ROOT / "tests" / "baselines" / f"{baselines[name]}_v0.3.0-base.json").read_text(encoding="utf-8"))
            chests = [e for e in frozen if rows[0][0] <= e["time"] < rows[-1][0]]
        expected = R.replay({"samples": rows, "finish_t": rows[-1][0]}, chests)
        waiting = deque(sorted((e for e in chests if e["certain_counted"] or e["approx_counted"]), key=lambda e: e["time"]))
        rig = Rig()
        for t, scores, health, black, frozen_picture in rows:
            while waiting and waiting[0]["time"] + 3 <= t:
                rig.tracker.chest(waiting.popleft())
            rig.tracker.offer(t, fake_frame(t, scores, health, bool(black), bool(frozen_picture)))
        rig.finish()
        assert not rig.tracker.failed and len(rig.cues.seen) == len(rows), name
        records = [{k: v for k, v in line.items() if k not in ("event", "kind")} for line in rig.records]
        assert json.loads(json.dumps(records)) == json.loads(json.dumps(expected["records"])), name
        transitions = [{k: v for k, v in line.items() if k not in ("event", "kind")} for line in rig.lines("transition") if line["reason"] != S.STOPPED]
        assert transitions == expected["transitions"], name


def test_the_known_miss_stays_missed():
    """Conservative on purpose (docs/M2_CORRECTION_PROPOSAL.md, section 4): the edited English recording's second win has no boundary M1 can see."""
    rig = Rig()
    for t, scores, health, black, frozen in M2.TIMELINES["new"]:
        rig.tracker.offer(t, fake_frame(t, scores, health, bool(black), bool(frozen)))
    rig.finish()
    assert len(rig.records) == 1 and rig.records[0]["completion"] != S.COMPLETE, rig.records


# ------------------------------------------------------------------ gaps, jumps and stopping invent nothing

def complete_records(rig):
    return [r for r in rig.records if r["completion"] == S.COMPLETE]


def test_control_a_whole_uninterrupted_match_is_complete():
    rig = M2.played_match(Rig()).show(10, "you_placed", health=40).show(5, "connecting").finish()
    assert len(complete_records(rig)) == 1 and not rig.warnings
    assert_sound(rig.records)


def test_control_the_frame_rate_does_not_change_the_result():
    results = []
    for fps in (5, 15):
        rig = M2.played_match(Rig(fps=fps)).show(10, "you_placed", health=40).show(5, "connecting").finish()
        results.append([(r["completion"], r["ended_by"], r["observed_from_start"]) for r in rig.records])
    assert results[0] == results[1] == [(S.COMPLETE, S.PLACED, True)], results


def test_a_gap_before_the_ending_cannot_be_complete():
    rig = M2.played_match(Rig()).jump(20).show(20, health=HP).show(10, "you_placed", health=40).show(5, "connecting").finish()
    assert len(rig.records) == 1 and not complete_records(rig) and rig.records[0]["discontinuity"]
    assert_sound(rig.records)


def test_a_long_outage_closes_the_match_as_lost():
    rig = M2.played_match(Rig()).jump(70).show(3).finish()
    assert [r["ended_by"] for r in rig.records] == [S.LOST] and not complete_records(rig)
    assert_sound(rig.records)


def test_time_running_backwards_closes_the_match():
    rig = M2.played_match(Rig())
    rig.t = 3.0
    rig.show(3).finish()
    assert [r["ended_by"] for r in rig.records] == [S.DISCONTINUITY] and not complete_records(rig)
    assert_sound(rig.records)


def test_a_long_black_picture_cannot_be_complete():
    rig = M2.played_match(Rig()).show(8, black=True).show(20, health=HP).show(10, "you_placed", health=40).show(5, "connecting").finish()
    assert len(rig.records) == 1 and not complete_records(rig) and rig.records[0]["discontinuity"]
    assert_sound(rig.records)


def test_stopping_mid_match_is_partial_and_says_so():
    rig = M2.played_match(Rig()).finish("Q pressed")
    assert [(r["completion"], r["ended_by"]) for r in rig.records] == [(S.PARTIAL, S.STOPPED)]
    assert rig.lines("summary")[0]["stop_reason"] == "Q pressed"
    assert_sound(rig.records)


def test_a_source_that_vanishes_is_recorded_as_lost():
    rig = M2.played_match(Rig()).finish("video source stopped")
    assert [(r["completion"], r["ended_by"]) for r in rig.records] == [(S.PARTIAL, S.LOST)]


def test_stopping_closes_at_the_last_frame_seen():
    rig = M2.played_match(Rig(fps=5))
    last = rig.t - 1 / 5
    rig.finish()
    assert abs(rig.records[0]["closed_t"] - last) < 1e-6


def test_stopping_before_any_frame_records_nothing():
    rig = Rig().finish()
    assert rig.records == [] and rig.lines("summary")[0]["match_samples"] == 0 and not rig.warnings


def test_closing_twice_and_offering_after_closing_do_nothing():
    rig = M2.played_match(Rig()).finish().finish()
    seen = len(rig.cues.seen)
    rig.show(5, health=HP).chest("en")
    assert len(rig.records) == 1 and len(rig.lines("summary")) == 1 and len(rig.cues.seen) == seen


# ------------------------------------------------------------------ failures stay inside

def assert_disabled_once(rig, where):
    assert rig.tracker.failed and len(rig.warnings) == 1 and "counting is not affected" in rig.warnings[0], rig.warnings
    lines = rig.lines("tracker_disabled")
    assert len(lines) == 1 and lines[0]["where"] == where, lines


def test_a_reader_failure_warns_once_and_stops_tracking():
    rig = Rig()
    rig.cues.boom_at = 5
    rig.show(30, health=HP).chest("en").finish()
    assert_disabled_once(rig, "offer")
    assert len(rig.cues.seen) == 5 and rig.records == [] and rig.lines("summary") == []


def test_a_failure_leaves_an_open_match_unrecorded():
    rig = M2.played_match(Rig())
    rig.cues.boom_at = len(rig.cues.seen) + 1
    rig.show(5, health=HP).finish()
    assert_disabled_once(rig, "offer")
    assert rig.records == []


def test_a_state_machine_failure_is_contained():
    machine = S.MatchStateMachine()
    machine.update = lambda observation: 1 / 0
    rig = Rig(machine=machine).show(3)
    assert_disabled_once(rig, "offer")


def test_a_failure_while_closing_is_contained():
    machine = S.MatchStateMachine()
    machine.finish = lambda t, reason: 1 / 0
    rig = Rig(machine=machine).show(3).finish()
    assert_disabled_once(rig, "close")


def test_a_malformed_event_is_contained():
    rig = Rig().show(1)
    rig.tracker.chest(None)
    assert_disabled_once(rig, "chest")
    rig = Rig().show(1).jump(20).show(1)                                  # after a break the chest's time is read
    rig.tracker.chest({"certain_counted": True})
    assert_disabled_once(rig, "chest")


def test_a_bad_frame_time_is_contained():
    rig = Rig()
    rig.tracker.offer(float("nan"), fake_frame())
    assert_disabled_once(rig, "offer")


def test_a_wrong_sized_frame_is_contained():
    log, warnings = [], []
    tracker = MT.MatchTracker(log.append, warnings.append)
    tracker.offer(0.0, np.zeros((10, 10, 3), np.uint8))
    assert tracker.failed and len(warnings) == 1


def test_a_failing_log_is_contained():
    calls = []

    def write(record):
        calls.append(record)
        if len(calls) > 1:
            raise OSError("disk full")

    warnings = []
    tracker = MT.MatchTracker(write, warnings.append, cues=Cues())
    for i in range(80):
        tracker.offer(float(i), fake_frame(i, {"lobby_menu": 0.95}))
    assert tracker.failed and len(warnings) == 1


def test_a_failing_warning_is_contained():
    def warn(message):
        raise OSError("the console is gone")

    cues = Cues()
    cues.boom_at = 1
    log = []
    tracker = MT.MatchTracker(log.append, warn, cues=cues)
    tracker.offer(0.0, fake_frame())
    assert tracker.failed and [line["kind"] for line in log] == ["started", "tracker_disabled"]


def test_the_user_stopping_is_not_swallowed():
    cues = Cues()
    cues.read = lambda frame: (_ for _ in ()).throw(KeyboardInterrupt())
    tracker = MT.MatchTracker([].append, [].append, cues=cues)
    try:
        tracker.offer(0.0, fake_frame())
    except KeyboardInterrupt:
        return
    raise AssertionError("Ctrl+C was swallowed")


def test_missing_templates_mean_no_tracker_and_one_warning():
    with tempfile.TemporaryDirectory() as tmp, patch.object(M, "TEMPLATE_DIR", Path(tmp)), patch.object(CONSOLE, "warn") as warn:
        session = SimpleNamespace(log=SimpleNamespace(write=lambda record: None))
        assert C._open_tracker({"match": {"mode": "shadow"}, "logging": {"enabled": True}}, session) is None
    assert warn.call_count == 1 and "could not start" in warn.call_args[0][0]


def test_shadow_without_logging_does_not_run():
    with patch.object(CONSOLE, "warn") as warn:
        assert C._open_tracker({"match": {"mode": "shadow"}, "logging": {"enabled": False}}, None) is None
    assert warn.call_count == 1 and "[logging]" in warn.call_args[0][0]


# ------------------------------------------------------------------ what it writes

def test_every_line_is_a_match_state_line_and_none_looks_like_a_chest():
    rig = M2.played_match(Rig()).chest("en").show(10, "you_placed", health=40).show(5, "connecting").finish()
    assert {line["kind"] for line in rig.log} == {"started", "transition", "opened", "record", "summary"}
    assert all(line["event"] == MT.LOG_EVENT and "time" not in line and "source" not in line for line in rig.log)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "session.jsonl"
        path.write_text("".join(json.dumps(line) + "\n" for line in rig.log), encoding="utf-8")
        assert R.load_chests(path) == []


def test_evidence_order_does_not_depend_on_the_python_hash_seed():
    rig = M2.played_match(Rig()).show(10, "you_placed", "eliminated_by", health=40).show(5, "connecting").finish()
    evidence = rig.records[0]["evidence"]
    assert len(evidence) > 2 and evidence == sorted(evidence, key=lambda item: (item[0], item[1]))


def test_the_tracker_touches_only_what_it_is_given():
    tree = ast.parse((ROOT / "src/fortnite_chest_counter/match_tracker.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported |= {f"{node.module}.{alias.name}" for alias in node.names}
    assert imported == {"math", "time", "dataclasses.asdict", "fortnite_chest_counter.match_cues", "fortnite_chest_counter.match_state"}, imported
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not names & {"open", "print", "Path", "CONSOLE"}, names


def test_counting_code_reaches_the_tracker_only_through_open_tracker():
    src = ROOT / "src/fortnite_chest_counter"
    for file in src.rglob("*.py"):
        if file.name in ("match_tracker.py", "counter.py"):
            continue
        assert "match_tracker" not in file.read_text(encoding="utf-8"), file.name
    tree = ast.parse((src / "counter.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert "match" not in " ".join([alias.name for alias in node.names] + [getattr(node, "module", None) or ""]), ast.dump(node)
    opener = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_open_tracker")
    assert any(isinstance(node, ast.ImportFrom) and node.module.endswith("match_tracker") for node in ast.walk(opener))


def test_off_loads_none_of_it():
    code = ("import sys; sys.path.insert(0, 'src')\n"
            "from fortnite_chest_counter import counter as C\n"
            "assert C._open_tracker({'match': {'mode': 'off'}, 'logging': {'enabled': True}}, None) is None\n"
            "assert not [m for m in sys.modules if m.split('.')[-1] in ('match_tracker', 'match_cues', 'match_state')]\n")
    subprocess.run([sys.executable, "-c", code], check=True, cwd=ROOT, capture_output=True, timeout=120)


# ------------------------------------------------------------------ overhead

def test_recognition_stays_within_one_percent_of_one_core():
    """Every cue drawn, so the costly comparisons really run. Retried because other programs can steal the CPU for a moment."""
    names = [cue.name for cue in M.CUES]
    frames = [with_health_bar(painted(*names, shade=90 + i)) for i in range(4)]
    measured = []
    for _ in range(4):
        log, warnings = [], []
        tracker = MT.MatchTracker(log.append, warnings.append)
        for i in range(60 * 15):
            tracker.offer(i / 15, frames[(i // 15) % 4])
        stats = tracker.stats()
        assert not tracker.failed and stats["match_samples"] == 60, stats
        measured.append(stats["match_percent_of_one_core"])
        if measured[-1] <= 1.0:
            return
    raise AssertionError(f"{measured} percent of one core is over the 1% budget")


# ------------------------------------------------------------------ the whole loop

class ScriptedSource:
    label = "scripted"

    def __init__(self, items, interrupt_at=None):
        self.items, self.interrupt_at = items, interrupt_at
        self.frames_processed = self.frames_dropped = 0

    def open(self, timeout=15.0):
        return {"input_resolution": (1280, 720), "input_fps": 30.0}

    def request_stop(self):
        pass

    def frames(self):
        for index, (t, frame) in enumerate(self.items):
            if index == self.interrupt_at:
                raise KeyboardInterrupt
            self.frames_processed += 1
            yield t, frame

    def elapsed(self):
        return self.items[-1][0]

    def close(self, wait=True):
        pass


def scripted_event(t, certain, approx, template="en:CHEST"):
    return {"time": t, "source": "popup", "popup_score": 0.9, "popup_template": template, "adjusted_tier": "HIGH" if certain else "MEDIUM",
            "certain_counted": certain, "approx_counted": approx, "reason": "scripted"}


class ScriptedDetector:
    """Stands in for the chest detector, which M4 must not touch. Remembers every frame it was given."""
    digests = []

    def __init__(self):
        self.waiting = deque([(5.0, scripted_event(2.0, True, True)), (9.0, scripted_event(6.0, False, True, "pt:BAÚ")), (12.0, scripted_event(9.0, False, False))])

    def process_frame(self, t, frame):
        ScriptedDetector.digests.append(hashlib.sha256(frame.tobytes()).hexdigest())
        done = []
        while self.waiting and self.waiting[0][0] <= t:
            done.append(self.waiting.popleft()[1])
        return done

    def take_type_updates(self):
        return []

    def flush(self):
        return [scripted_event(14.5, True, True)]


def scripted_frames(seconds=20, fps=5, health=True):
    """A changing picture (a still one would count as frozen), read-only like a frame from FFmpeg."""
    pictures = []
    for shade in range(4):
        frame = painted(shade=90 + shade)
        pictures.append(with_health_bar(frame) if health else frame)
        pictures[-1].flags.writeable = False
    return [(i / fps, pictures[(i // fps) % 4]) for i in range(seconds * fps)]


@contextlib.contextmanager
def scripted_pipeline(items, interrupt_at=None):
    from fortnite_chest_counter import estimator
    from fortnite_chest_counter.input import video_sources as sources

    ScriptedDetector.digests = []
    make = lambda *a, **k: ScriptedSource(items, interrupt_at)
    with patch.object(sources, "make_source", make), patch.object(C, "Mp4FrameSource", make), patch.object(estimator, "ChestEstimator", ScriptedDetector), \
            patch.object(paths, "ffmpeg_executable", lambda: "ffmpeg"):
        yield


def folders(tmp):
    tmp = Path(tmp)
    return ["--state", str(tmp / "s.json"), "--obs-dir", str(tmp / "o"), "--log-dir", str(tmp / "l")]


def outcome(tmp):
    """Everything counting produces, minus the clock."""
    tmp = Path(tmp)
    log = [json.loads(line) for line in next((tmp / "l").glob("*.jsonl")).read_text(encoding="utf-8").splitlines()]
    state = json.loads((tmp / "s.json").read_text(encoding="utf-8"))
    return {"obs": {f.name: f.read_bytes() for f in sorted((tmp / "o").iterdir())},
            "state": {k: v for k, v in state.items() if k not in ("updated_at", "session_started_at", "types_since")},
            "events": [{k: v for k, v in row.items() if k not in ("logged_at", "latency_s", "obs_write_s")} for row in log if "time" in row],
            "frames": list(ScriptedDetector.digests)}, log


def run_command(tmp, command, mode, items=None, interrupt_at=None, extra=()):
    with scripted_pipeline(items or scripted_frames(), interrupt_at), contextlib.redirect_stdout(io.StringIO()) as out:
        argv = [command] + (["--video", "x.mp4", "--no-evaluate"] if command == "simulate" else ["--source", "file"]) + ["--reset", *folders(tmp), *extra]
        code = C.main(argv + (["--match-mode", mode] if mode else []))
    assert code == 0, out.getvalue()
    return outcome(tmp)


def run_app(tmp, mode, items=None):
    """Through --gui, as the desktop app runs it. -> (outcome, log, the app's messages)."""
    read, write = os.pipe()
    stdin = sys.stdin
    buf = io.StringIO()
    try:
        sys.stdin = os.fdopen(read, "r")
        with scripted_pipeline(items or scripted_frames()), contextlib.redirect_stdout(buf):
            code = C.main(["live", "--gui", "--source", "file", "--reset", *folders(tmp), "--match-mode", mode])
        assert code == 0, buf.getvalue()
        result, log = outcome(tmp)
    finally:
        sys.stdin = stdin
        CONSOLE.machine, paths.HIDE_CHILD_CONSOLES = False, False
        os.close(write)
    return result, log, [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]


def match_lines(log):
    return [row for row in log if row.get("event") == MT.LOG_EVENT]


def test_live_counts_the_same_with_tracking_off_and_in_shadow():
    with tempfile.TemporaryDirectory() as off, tempfile.TemporaryDirectory() as shadow:
        plain, plain_log = run_command(off, "live", "off")
        watched, watched_log = run_command(shadow, "live", "shadow")
    assert plain == watched
    assert plain["state"]["certain"] == 2 and plain["state"]["approximate"] == 3 and len(plain["frames"]) == 100
    assert match_lines(plain_log) == [] and len(match_lines(watched_log)) >= 3


def test_simulate_counts_the_same_with_tracking_off_and_in_shadow():
    with tempfile.TemporaryDirectory() as off, tempfile.TemporaryDirectory() as shadow:
        plain, plain_log = run_command(off, "simulate", "off")
        watched, watched_log = run_command(shadow, "simulate", "shadow")
    assert plain == watched and plain["state"]["certain"] == 2
    assert match_lines(plain_log) == [] and len(match_lines(watched_log)) >= 3


def test_counted_chests_reach_the_tracker_from_both_loops():
    """The script has two counted chests during the run, one that is not counted, and one counted at the final flush."""
    for command in ("live", "simulate"):
        with tempfile.TemporaryDirectory() as tmp:
            _, log = run_command(tmp, command, "shadow")
        summary = next(row for row in match_lines(log) if row["kind"] == "summary")
        assert (summary["chests_delivered"], summary["chests_undelivered"]) == (2, 1), (command, summary)
        assert summary["match_samples"] == 20 and summary["stop_reason"] == "stream ended", (command, summary)


def test_off_leaves_the_session_log_as_it_was():
    with tempfile.TemporaryDirectory() as tmp:
        _, log = run_command(tmp, "live", "off")
    end = next(row for row in log if row.get("event") == "session_end")
    assert match_lines(log) == [] and not [key for key in end if key.startswith("match_")]


def test_session_start_stays_first_in_shadow():
    with tempfile.TemporaryDirectory() as tmp:
        _, log = run_command(tmp, "live", "shadow")
    assert log[0]["event"] == "session_start" and log[1]["event"] == MT.LOG_EVENT and log[1]["kind"] == "started"


def test_shadow_reports_its_time_apart_from_detection():
    real_read = M.CueReader.read

    def slow_read(self, frame, signals=None):
        time.sleep(0.06)
        return real_read(self, frame, signals)

    with tempfile.TemporaryDirectory() as tmp, patch.object(M.CueReader, "read", slow_read):
        _, log = run_command(tmp, "live", "shadow")
    end = next(row for row in log if row.get("event") == "session_end")
    assert end["match_samples"] == 20 and end["match_ms_avg"] >= 60 and end["match_ms_max"] >= 60, end
    assert end["max_frame_ms"] < 50, end                                  # the detector's own timing does not include it


def test_the_desktop_app_sees_no_difference():
    def shape(messages):
        return [(m["type"], sorted(m)) for m in messages if m["type"] != "status"]

    with tempfile.TemporaryDirectory() as off, tempfile.TemporaryDirectory() as shadow:
        plain, _, plain_messages = run_app(off, "off")
        watched, _, watched_messages = run_app(shadow, "shadow")
    assert plain == watched and shape(plain_messages) == shape(watched_messages), (shape(plain_messages), shape(watched_messages))
    assert plain_messages[-1]["type"] == "stopped" and not [key for key in watched_messages[-1] if key.startswith("match_")]


def test_an_injected_failure_cannot_touch_the_session():
    calls = []
    real_read = M.CueReader.read

    def failing_read(self, frame, signals=None):
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError("injected")
        return real_read(self, frame, signals)

    with tempfile.TemporaryDirectory() as off, tempfile.TemporaryDirectory() as shadow:
        plain, _, _ = run_app(off, "off")
        with patch.object(M.CueReader, "read", failing_read):
            watched, log, messages = run_app(shadow, "shadow")
    assert plain == watched and len(calls) == 3
    warnings = [m for m in messages if m["type"] == "warn" and "match tracking" in m["text"]]
    assert len(warnings) == 1 and messages[-1]["type"] == "stopped", messages
    assert [row["kind"] for row in match_lines(log) if row["kind"] == "tracker_disabled"] == ["tracker_disabled"]
    assert next(row for row in log if row.get("event") == "session_end")["match_failed"] is True
    assert not [row for row in match_lines(log) if row["kind"] == "record"]


def test_a_tracker_that_cannot_start_cannot_touch_the_session():
    with tempfile.TemporaryDirectory() as off, tempfile.TemporaryDirectory() as shadow, tempfile.TemporaryDirectory() as empty:
        plain, _ = run_command(off, "live", "off")
        with patch.object(M, "TEMPLATE_DIR", Path(empty)):
            watched, log = run_command(shadow, "live", "shadow")
    assert plain == watched and match_lines(log) == []


def test_a_mode_that_does_not_exist_runs_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        _, log = run_command(tmp, "live", "maybe")
    assert match_lines(log) == []


def test_ctrl_c_closes_the_open_match_and_keeps_the_counts():
    with tempfile.TemporaryDirectory() as tmp:
        result, log = run_command(tmp, "live", "shadow", interrupt_at=60)
    records = [row for row in match_lines(log) if row["kind"] == "record"]
    assert len(records) == 1 and records[0]["ended_by"] == S.STOPPED and records[0]["completion"] != S.COMPLETE, records
    assert next(row for row in match_lines(log) if row["kind"] == "summary")["stop_reason"] == "Ctrl+C"
    assert result["state"]["approximate"] == 3                            # the two seen plus the one flushed


def test_a_source_lost_in_the_live_loop_is_recorded_as_lost():
    with tempfile.TemporaryDirectory() as tmp, scripted_pipeline(scripted_frames()), contextlib.redirect_stdout(io.StringIO()):
        assert C.main(["live", "--source", "desktop", "--reset", *folders(tmp), "--match-mode", "shadow"]) == 0
        _, log = outcome(tmp)
    records = [row for row in match_lines(log) if row["kind"] == "record"]
    assert len(records) == 1 and records[0]["ended_by"] == S.LOST and records[0]["completion"] != S.COMPLETE, records


def test_a_gap_in_the_live_loop_invents_nothing():
    items = scripted_frames(seconds=20)
    items = items[:50] + [(t + 90, frame) for t, frame in items[50:]]     # 90 s with no video, after 10 s of play
    with tempfile.TemporaryDirectory() as off, tempfile.TemporaryDirectory() as shadow:
        plain, _ = run_command(off, "live", "off", items=items)
        watched, log = run_command(shadow, "live", "shadow", items=items)
    records = [row for row in match_lines(log) if row["kind"] == "record"]
    assert plain == watched and records and not [r for r in records if r["completion"] == S.COMPLETE], records
    assert records[0]["ended_by"] == S.LOST
    assert_sound(records)


def test_what_the_hud_shows_reaches_the_state_machine():
    class Machine:
        state = "UNKNOWN"
        seen = []

        def update(self, observation):
            self.seen.append(observation.hud_in_view)
            return []

        def snapshot(self):
            return None

    tracker = MT.MatchTracker(lambda row: None, lambda text: None, cues=Cues(), machine=Machine())
    tracker.offer(0.0, {**fake_frame(), "hud": True})
    tracker.offer(1.0, {**fake_frame(), "hud": False})
    assert Machine.seen == [True, False]


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
    print(f"{len(tests) - failed}/{len(tests)} match tracker checks passed")
    sys.exit(1 if failed else 0)
