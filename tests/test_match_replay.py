"""Offline scorecard tests: no videos, profile state, Qt or detector regressions.

Run: python tests/test_match_replay.py (also discoverable by pytest).
"""

import copy
import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "tests"))

import match_replay as R
import match_scorecard as C
import test_match_state as M2


def record(number=1, offset=0):
    return {"match_number": number, "completion": "complete", "english_confirmed": True,
            "ended_by": "placed", "observed_from_start": True, "opened_t": offset,
            "played_from_t": offset + 2, "ended_t": offset + 8, "closed_t": offset + 10,
            "observed_seconds": 10, "active_seconds": 6, "spectating_seconds": 2,
            "uncertain_seconds": 0, "complete_duration_seconds": 6,
            "start_confidence": "high", "end_confidence": "high", "discontinuity": False,
            "respawns": 0, "english_chests": 0, "portuguese_chests": 0, "reasons": [], "evidence": []}


def truth_source():
    return {"review": {"status": "human_reviewed", "reviewer": "synthetic test author", "basis": "constructed timeline; not a claim about footage"},
            "matches": [{"id": "one", "anchor": [2, 8], "opened_t": [0, 1], "played_from_t": [2, 3],
                         "ended_t": [8, 9], "closed_t": [10, 11], "completion": "complete",
                         "english_confirmed": True, "observed_from_start": True, "ended_by": "placed"}],
            "transitions": [{"state": "IN_MATCH", "time": [2, 4]}, {"state": "ELIMINATED", "time": [8, 10]}]}


def prediction():
    return {"records": [record()], "transitions": [{"t": 3, "state": "IN_MATCH"}, {"t": 9, "state": "ELIMINATED"}]}


def compare(p=None, t=None, **kwargs):
    return C.compare_source(p or prediction(), t or truth_source(), **kwargs)


def expect_error(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError:
        return
    raise AssertionError("invalid input was accepted")


def test_correct_predictions_pass_and_report_boundary_measurements():
    result = compare()
    assert result["passed"] and result["human_reviewed"]
    assert len(result["match_boundaries"]) == 4 and len(result["transition_boundaries"]) == 2
    assert not any(result["counts"].values())


def test_wrong_truth_fails_without_changing_predictions():
    p, t = prediction(), truth_source()
    original = copy.deepcopy(p)
    t["matches"][0]["ended_by"] = "victory"
    result = compare(p, t)
    assert result["counts"]["false_endings"] == result["counts"]["missed_endings"] == 1
    assert not result["passed"] and p == original


def test_missing_and_extra_matches_are_reported():
    p, t = prediction(), truth_source()
    p["records"].append(record(2, 20))
    result = compare(p, t)
    assert result["counts"]["extra_matches"] == 1 and result["counts"]["false_endings"] == 1
    p["records"] = []
    result = compare(p, t)
    assert result["counts"]["missed_matches"] == result["counts"]["missed_endings"] == 1


def test_duplicate_prediction_cannot_satisfy_the_same_truth_twice():
    p = prediction()
    p["records"].append(record(2))
    result = compare(p)
    assert result["counts"]["duplicate_matches"] == 1 and len(result["match_pairs"]) == 1
    assert result["counts"]["invariant_errors"] == 1


def test_one_prediction_cannot_satisfy_two_truth_matches():
    t = truth_source()
    t["matches"].append({"id": "two", "anchor": [12, 18]})
    p = prediction()
    p["records"][0].update(closed_t=20, observed_seconds=20)
    result = compare(p, t)
    assert len(result["match_pairs"]) == 1 and result["counts"]["missed_matches"] == 1


def test_matching_does_not_hide_wrong_classifications():
    p = prediction()
    p["records"][0].update(completion="unconfirmed", english_confirmed=False, observed_from_start=False, complete_duration_seconds=None)
    result = compare(p)
    assert len(result["match_pairs"]) == 1 and result["counts"]["classification_errors"] == 3
    assert result["classifications"]["unconfirmed"] == 1 and not result["passed"]


def test_unseen_ending_and_unknown_boundary_are_not_estimated():
    t = truth_source()
    t["matches"][0].update(ended_by=None, ended_t=None)
    result = compare(t=t)
    assert result["counts"]["false_endings"] == 1 and result["counts"]["boundary_errors"] == 1
    del t["matches"][0]["ended_t"]
    assert compare(t=t)["counts"]["boundary_errors"] == 0


def test_missing_required_ending_has_a_missing_boundary():
    p = prediction()
    p["records"][0].update(ended_by="stopped", ended_t=None, complete_duration_seconds=None, completion="partial")
    result = compare(p)
    assert result["counts"]["missed_endings"] == 1 and result["counts"]["boundary_errors"] == 1


def test_boundary_errors_are_signed_and_do_not_reclassify_the_match():
    t = truth_source()
    t["matches"][0]["opened_t"] = [1, 2]
    t["matches"][0]["closed_t"] = [7, 8]
    result = compare(t=t)
    assert [e["outside_window_seconds"] for e in result["issues"]["boundary_errors"]] == [-1, 2]
    assert not result["counts"]["missed_matches"]


def test_missing_extra_and_wrong_transitions_are_reported():
    p = prediction()
    p["transitions"][0]["state"] = "LOBBY"
    assert compare(p)["counts"]["incorrect_transitions"] == 1
    p["transitions"] = [{"t": 200, "state": "LOBBY"}]
    result = compare(p)
    assert result["counts"]["missed_transitions"] == 2 and result["counts"]["extra_transitions"] == 1


def test_duplicate_transition_cannot_satisfy_two_expectations():
    t, p = truth_source(), prediction()
    t["transitions"] = [{"state": "IN_MATCH", "time": [2, 4]}, {"state": "IN_MATCH", "time": [5, 7]}]
    p["transitions"] = [{"t": 3, "state": "IN_MATCH"}]
    assert compare(p, t)["counts"]["missed_transitions"] == 1


def test_transition_delay_is_measured_outside_accepted_window():
    p = prediction()
    p["transitions"][1]["t"] = 15
    result = compare(p)
    assert result["counts"]["boundary_errors"] == 1
    assert result["transition_boundaries"][1]["outside_window_seconds"] == 5


def test_unscored_transition_intervals_are_explicit_and_preserved():
    p, t = prediction(), truth_source()
    p["transitions"].append({"t": 30, "state": "UNKNOWN"})
    t["unscored_transitions"] = [{"time": [25, 35], "reason": "player overlay hides the state"}]
    result = compare(p, t)
    assert result["passed"] and len(result["unscored_predictions"]) == 1
    assert result["unscored_transition_intervals"] == t["unscored_transitions"]


def test_provisional_annotations_never_become_human_validated():
    t = truth_source()
    t["review"]["status"] = "provisional"
    assert compare(t=t)["counts"]["unreviewed_sources"] == 1
    result = compare(t=t, allow_provisional=True)
    assert result["passed"] and not result["human_reviewed"]


def test_truth_rejects_typos_invalid_times_and_overlapping_anchors():
    good = {"schema": "match-truth-v1", "sources": {"clip": truth_source()}}
    C.validate_truth(good)
    bad = copy.deepcopy(good)
    bad["sources"]["clip"]["matches"][0]["completino"] = "complete"
    expect_error(C.validate_truth, bad)
    for value in ([3, 2], [0, float("nan")], [False, 2], "1"):
        bad = copy.deepcopy(good)
        bad["sources"]["clip"]["matches"][0]["anchor"] = value
        expect_error(C.validate_truth, bad)
    bad = copy.deepcopy(good)
    bad["sources"]["clip"]["matches"].append({"id": "two", "anchor": [7, 12]})
    expect_error(C.validate_truth, bad)


def test_truth_cannot_both_require_and_ignore_a_transition():
    t = truth_source()
    t["unscored_transitions"] = [{"time": [0, 4], "reason": "hidden"}]
    expect_error(C.validate_truth, {"schema": "match-truth-v1", "sources": {"clip": t}})


def test_record_invariants_detect_each_impossible_time_total():
    assert C.record_errors([record()]) == []
    for field, value in (("observed_seconds", 20), ("uncertain_seconds", 5), ("active_seconds", 12),
                         ("spectating_seconds", -2), ("played_from_t", -1), ("ended_t", 12),
                         ("complete_duration_seconds", 10), ("observed_seconds", float("nan"))):
        r = record()
        r[field] = value
        assert C.record_errors([r]), field


def test_complete_match_needs_its_start_language_continuity_and_end():
    for field, value in (("observed_from_start", False), ("english_confirmed", False),
                         ("discontinuity", True), ("ended_by", "stopped")):
        r = record()
        r[field] = value
        assert C.record_errors([r]), field
    r = record()
    r["completion"] = "partial"
    assert C.record_errors([r])


def test_adjacent_half_open_records_do_not_overlap():
    assert C.record_errors([record(), record(2, 10)]) == []
    assert C.record_errors([record(), record(2, 9)])
    assert C.record_errors([record(), record(1, 10)])


def test_legacy_fixture_reproduces_all_five_M2_results():
    sources = R.load_timelines(ROOT / "tests/fixtures/match/timelines.json.gz")
    for name in sources:
        baseline = "en" if name == "new" else "ps5" if name == "ps5" else None
        chests = R.load_chests(ROOT / f"tests/baselines/{baseline}_v0.3.0-base.json") if baseline else []
        result = R.replay(sources[name], chests)
        old = M2.replay(name, M2.counted_chests(baseline) if baseline else ())
        expected = [r.to_dict() for r in old if isinstance(r, M2.S.MatchRecord)]
        for r in expected:
            r["evidence"] = sorted(r["evidence"], key=lambda item: (item[0], item[1]))
        assert result["records"] == expected, name
        assert [(t["t"], t["state"]) for t in result["transitions"]] == M2.story(old), name
        assert result["provenance"]["kind"] == "legacy_fixture"


def test_frozen_M2_reference_is_reproduced_before_corrections():
    sources = R.load_timelines(ROOT / "tests/fixtures/match/timelines.json.gz")
    reference = R.load_json(ROOT / "tests/fixtures/match/m2_reference.json")["sources"]
    for name, source in sources.items():
        baseline = "en" if name == "new" else "ps5" if name == "ps5" else None
        chests = R.load_chests(ROOT / f"tests/baselines/{baseline}_v0.3.0-base.json") if baseline else []
        result = R.replay(source, chests)
        actual = {"transitions": [[t["t"], t["state"]] for t in result["transitions"]],
                  "completions": [r["completion"] for r in result["records"]],
                  "endings": [r["ended_by"] for r in result["records"]],
                  "ended_t": [r["ended_t"] for r in result["records"]]}
        assert actual == reference[name], (name, actual)


def test_independent_annotations_keep_both_English_wins_and_the_real_cut():
    truth = C.validate_truth(R.load_json(ROOT / "tests/fixtures/match/footage_truth.provisional.json"))
    first, second = truth["sources"]["new"]["matches"]
    assert first["ended_by"] == second["ended_by"] == "victory"
    assert first["closed_t"] == [261, 263] and second["opened_t"] == [261, 264]
    assert all(s["review"]["status"] == "provisional" for s in truth["sources"].values())


def test_portuguese_chest_evidence_preserves_unknowns_and_approx_only_events():
    source = R.load_timelines(ROOT / "tests/fixtures/match/timelines.json.gz")["ps5"]
    chests = R.load_chests(ROOT / "tests/baselines/ps5_v0.3.0-base.json")
    before = copy.deepcopy(chests)
    result = R.replay(source, chests)
    assert result["chest_totals"] == {"en": {"certain": 0, "approx": 0}, "pt": {"certain": 11, "approx": 11}, "unknown": {"certain": 0, "approx": 4}}
    assert [item["event"] for item in result["chest_evidence"]] == before == chests
    assert result["records"][0]["portuguese_chests"] == 11


def test_chest_delivery_time_is_distinct_from_event_time_and_not_lost_at_EOF():
    source = {"samples": [[0, {}, 180, 0, 0], [1, {}, 180, 0, 0]], "finish_t": 2}
    chests = [{"time": 0, "available_t": 1, "certain_counted": True, "approx_counted": True, "popup_template": "en:CHEST"},
              {"time": 1, "certain_counted": False, "approx_counted": True, "popup_template": None}]
    result = R.replay(source, chests)
    first, second = result["chest_evidence"]
    assert first["delivered_t"] == 1 and first["event"]["time"] == 0 and first["availability"] == "recorded"
    assert second["delivered_t"] is None and second["availability"] == "assumed_onset_plus_delay"
    assert result["chest_totals"]["unknown"]["approx"] == 1


def test_chest_evidence_on_black_picture_does_not_claim_usable_delivery():
    source = {"samples": [[0, {}, 0, 1, 0]], "finish_t": 1}
    chest = {"time": 0, "certain_counted": True, "approx_counted": True, "popup_template": "en:CHEST"}
    result = R.replay(source, [chest], chest_delay=0)
    assert not result["chest_evidence"][0]["picture_usable"] and not result["records"]


def test_invalid_chest_flags_and_delivery_times_are_rejected_not_repaired():
    for event in ({"time": 0, "certain_counted": True, "approx_counted": False},
                  {"time": 0, "certain_counted": 1, "approx_counted": True},
                  {"time": 2, "available_t": 1, "certain_counted": True, "approx_counted": True}):
        expect_error(R.validate_chests, [event])


def test_chest_events_from_another_clock_are_not_silently_included():
    source = {"samples": [[0, {}, 180, 0, 0]], "finish_t": 1}
    event = {"time": 500, "certain_counted": True, "approx_counted": True}
    expect_error(R.replay, source, [event])


def test_cue_cache_rejects_empty_nonfinite_and_nonmonotonic_evidence():
    for rows in ([], [[0, {}, 0, 0, 0], [0, {}, 0, 0, 0]], [[1, {}, 0, 0, 0], [0, {}, 0, 0, 0]],
                 [[0, {"invented_cue": 1}, 0, 0, 0]], [[0, {"spectating": float("nan")}, 0, 0, 0]],
                 [[0, {}, 0, "false", 0]]):
        expect_error(R.validate_rows, rows, "test")


def test_saved_cache_roundtrips_without_video_and_is_deterministic():
    sources = R.load_timelines(ROOT / "tests/fixtures/match/timelines.json.gz")
    with tempfile.TemporaryDirectory() as tmp:
        a, b = Path(tmp) / "a.json.gz", Path(tmp) / "b.json.gz"
        data = {"schema": R.CACHE_SCHEMA, "sources": sources}
        R.write_json(a, data)
        R.write_json(b, data)
        assert a.read_bytes() == b.read_bytes() and R.load_timelines(a) == sources


def test_missing_truth_source_is_an_error_not_a_smaller_passing_dataset():
    sources = R.load_timelines(ROOT / "tests/fixtures/match/timelines.json.gz")
    expect_error(R.score, sources, {"schema": "match-truth-v1", "sources": {"clip1": truth_source()}})


def test_missing_playlist_segments_and_remote_directives_fail():
    with tempfile.TemporaryDirectory() as tmp:
        listing = Path(tmp) / "clip.ffconcat"
        for text in ("ffconcat version 1.0\n", "file absent.mkv\n", "file https://example.com/movie\n", "duration 10\n"):
            listing.write_text(text)
            expect_error(R.playlist_files, listing)


def test_capture_clips_stay_separate_and_report_clock_offsets():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        R.write_json(folder / "capture.json", {"fps": 1, "frames_not_recorded": 0, "app": {"profile": "must not be used"}})
        R.write_json(folder / "video/clips.json", [{"file": "video/a.ffconcat", "start": 0, "end": 2}, {"file": "video/b.ffconcat", "start": 5, "end": 7}])
        (folder / "timeline.csv").write_text("frame,live_t\n" + "".join(f"{i},{i + 0.2}\n" for i in range(7)))
        sources = R.capture_sources(folder)
        assert list(sources) == ["clip1", "clip2"] and sources["clip2"]["capture"]["recording_start"] == 5
        assert "profile" not in json.dumps(sources, default=str)
        R.write_json(folder / "capture.json", {"fps": 1, "frames_not_recorded": 1})
        expect_error(R.capture_sources, folder)


class FakeProcess:
    def __init__(self, raw, returncode=0):
        self.stdout = io.BytesIO(raw)
        self.returncode = returncode
    def poll(self):
        return self.returncode
    def wait(self):
        return self.returncode


def test_decoder_checks_failures_empty_streams_and_partial_frames():
    for raw, code in ((b"", 1), (b"", 0), (b"short", 0)):
        with patch.object(R.subprocess, "Popen", return_value=FakeProcess(raw, code)):
            expect_error(lambda: list(R.frames("movie.mp4", "ffmpeg", 1)))


def test_decoder_returns_readonly_RGB_and_correct_sampling_clock():
    raw = bytes(1280 * 720 * 3 * 2)
    with patch.object(R.subprocess, "Popen", return_value=FakeProcess(raw)) as popen:
        items = list(R.frames("clip.ffconcat", "ffmpeg", 2))
        assert [t for t, frame in items] == [0, 0.5]
        assert items[0][1].shape == (720, 1280, 3) and not items[0][1].flags.writeable
        assert "fps=2,scale=1280:720" in popen.call_args.args[0]


def test_extraction_keeps_M1_sampling_phase_and_picture_reference():
    from fortnite_chest_counter import match_cues as M

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        listing = folder / "clip.ffconcat"
        listing.write_text("ffconcat version 1.0\nfile seg.mkv\n")
        (folder / "seg.mkv").write_bytes(b"stub video; decoder mocked")
        executable = folder / "ffmpeg.exe"
        executable.write_bytes(b"stub executable; decoder mocked")
        previous = []

        def picture(frame, before):
            previous.append(before)
            return SimpleNamespace(black=False, frozen=False, sample=frame)

        with patch.object(R, "frames", return_value=((i / 2, i) for i in range(4))) as decoder, \
             patch.object(M, "CueReader") as reader, patch.object(M, "picture_evidence", side_effect=picture), \
             patch.object(M, "health_bar_pixels", return_value=180):
            reader.return_value.read.return_value = {"connecting": 0.9}
            result = R.extract(listing, executable, expected_seconds=2)
        assert decoder.call_args.args == (listing.resolve(), executable, 2)
        assert [call.args[0] for call in reader.return_value.read.call_args_list] == [0, 2]
        assert previous == [None, 0] and [row[0] for row in result["samples"]] == [0, 1]
        assert result["provenance"]["decode_fps"] == 2 and len(result["provenance"]["inputs"]) == 2


def test_CLI_incorrect_truth_returns_nonzero_and_preserves_report():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        # Independent claim: no matches or transitions occurred. Clip 1 visibly
        # contains a match ending, so this must fail through the real CLI.
        truth = {"schema": "match-truth-v1", "sources": {"clip1": {"review": truth_source()["review"], "matches": [], "transitions": []}}}
        R.write_json(folder / "wrong.json", truth)
        private = folder / "profile"
        private.mkdir()
        (private / "config.toml").write_text("invalid config which must never be loaded")
        command = [sys.executable, "-B", str(ROOT / "research/match_replay.py"), "--timelines", str(ROOT / "tests/fixtures/match/timelines.json.gz"),
                   "--source", "clip1", "--truth", str(folder / "wrong.json"), "--out", str(folder / "report.json")]
        result = subprocess.run(command, capture_output=True, text=True, env={**os.environ, "FCC_HOME": str(private)}, timeout=20)
        assert result.returncode == 1, result.stderr + result.stdout
        report = R.load_json(folder / "report.json")
        assert not report["passed"] and report["counts"]["extra_matches"] == 1 and report["counts"]["false_endings"] == 1
        assert sorted(p.name for p in private.iterdir()) == ["config.toml"]
        assert (private / "config.toml").read_text() == "invalid config which must never be loaded"


def test_CLI_input_errors_return_two_without_overwriting_inputs():
    with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        truth = Path(tmp) / "truth.json"
        R.write_json(truth, {"schema": "match-truth-v1", "sources": {"clip1": truth_source()}})
        before = truth.read_bytes()
        result = R.main(["--timelines", str(ROOT / "tests/fixtures/match/timelines.json.gz"), "--source", "clip1", "--truth", str(truth), "--out", str(truth)])
        assert result == 2 and truth.read_bytes() == before


if __name__ == "__main__":
    import traceback
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}", flush=True)
        except Exception:
            failed += 1
            print(f"  FAIL  {name}", flush=True)
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} replay scorecard checks passed")
    raise SystemExit(bool(failed))
