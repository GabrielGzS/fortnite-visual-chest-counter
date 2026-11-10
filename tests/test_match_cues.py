"""
Match-recognition cues (v0.3.0, M1): real screens reach the threshold, wrong screens stay low, frames are never touched, and it is cheap.

tests/fixtures/match/frames.npz holds, for 83 real frames, only the true/false text masks inside the cue boxes, the scores they gave and
which signals should or should not be present (made by research/match_cues_eval.py --write-fixtures). -1 means "too close to a labelled
edge to judge". The tests rebuild a frame from those masks, so they run without any footage.

Run:   python tests/test_match_cues.py     (or pytest)
"""

import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "src"))   # run without installing

import ast
import json
import time
from pathlib import Path

import numpy as np

from fortnite_chest_counter import match_cues as M
from fortnite_chest_counter.detection import visual as V

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = np.load(HERE / "fixtures" / "match" / "frames.npz")
SIGNALS = [str(s) for s in DATA["signals"]]
READER = M.CueReader()
BLANK = 90


def frame_of(row):
    bits = np.unpackbits(DATA["masks"][row])
    frame = np.full((720, 1280, 3), BLANK, np.uint8)
    offset = 0
    for cue in M.CUES:
        x0, y0, x1, y1 = cue.box
        size = (y1 - y0) * (x1 - x0)
        mask = bits[offset:offset + size].reshape(y1 - y0, x1 - x0).astype(bool)
        offset += size
        ink, paper = (255, BLANK) if cue.ink == M.WHITE else (20, 230)
        frame[y0:y1, x0:x1] = np.where(mask[..., None], ink, paper).astype(np.uint8)
    return frame


FRAMES = [frame_of(i) for i in range(len(DATA["masks"]))]


def row_where(signal, value=1):
    return next(i for i in range(len(FRAMES)) if DATA["expected"][i][SIGNALS.index(signal)] == value)


def blank_cue(frame, name):
    x0, y0, x1, y1 = M._CUE[name].box
    frame[y0:y1, x0:x1] = BLANK


def test_every_template_loads_and_fits_inside_its_box():
    for cue in M.CUES:
        x0, y0, x1, y1 = cue.box
        template = np.load(M.TEMPLATE_DIR / f"{cue.name}.npy")
        assert template.dtype == bool and 0.2 < template.mean() < 0.8, cue.name
        assert template.shape[0] < y1 - y0 and template.shape[1] < x1 - x0, cue.name
        assert 0 <= x0 < x1 <= 1280 and 0 <= y0 < y1 <= 720, cue.name


def test_signals_use_only_known_templates():
    assert {name for names in M.SIGNALS.values() for name in names} == {cue.name for cue in M.CUES}
    assert M.PROVISIONAL_SIGNALS <= set(M.SIGNALS) and M.NOT_ENGLISH_SPECIFIC <= set(M.SIGNALS)
    assert list(M.SIGNALS) == SIGNALS, "the fixtures must be rebuilt when the signals change"
    assert M.SCORE_THRESHOLD == 0.70, "the agreed acceptance threshold"


def test_the_fixtures_cover_every_signal_both_ways():
    for j, signal in enumerate(SIGNALS):
        assert sum(DATA["expected"][:, j] == 1) >= 2 and sum(DATA["expected"][:, j] == 0) >= 20, signal


def test_real_screens_reach_the_threshold():
    for i, frame in enumerate(FRAMES):
        scores = READER.read(frame)
        for j, signal in enumerate(SIGNALS):
            if DATA["expected"][i][j] == 1:
                assert scores[signal] >= M.SCORE_THRESHOLD, (signal, str(DATA["where"][i]), scores[signal])


def test_wrong_screens_stay_at_or_below_the_limit():
    for i, frame in enumerate(FRAMES):
        scores = READER.read(frame)
        for j, signal in enumerate(SIGNALS):
            if DATA["expected"][i][j] == 0:
                assert scores[signal] <= 0.40, (signal, str(DATA["where"][i]), scores[signal])


def test_the_scores_are_exactly_the_measured_ones():
    for i, frame in enumerate(FRAMES):
        scores = READER.read(frame)
        for j, signal in enumerate(SIGNALS):
            assert abs(scores[signal] - DATA["scores"][i][j]) < 1e-5, (signal, str(DATA["where"][i]))


def test_each_signal_gets_its_own_plain_score():
    scores = READER.read(FRAMES[0])
    assert list(scores) == list(M.SIGNALS) and all(type(v) is float and 0.0 <= v <= 1.0 for v in scores.values())
    assert json.loads(json.dumps(scores)) == scores, "the state machine must receive plain numbers, not images"
    assert list(READER.read(FRAMES[0], ["connecting", "spectating"])) == ["connecting", "spectating"]
    try:
        READER.read(FRAMES[0], ["no_such_signal"])
    except KeyError:
        return
    raise AssertionError("an unknown signal was accepted")


def test_frames_are_never_written_to():
    frame = FRAMES[row_where("lobby_menu")].copy()
    before = frame.tobytes()
    frame.flags.writeable = False                 # any write now raises an error
    READER.read(frame)
    READER.template_scores(frame)
    evidence = M.picture_evidence(frame, M.picture_evidence(frame).sample)
    M.health_bar_pixels(frame)
    assert frame.tobytes() == before and evidence.sample.flags.owndata


def test_the_reader_keeps_nothing_about_a_frame():
    reader = M.CueReader()
    before = set(vars(reader))
    reader.read(FRAMES[0])
    assert set(vars(reader)) == before == {"_templates", "_ink"}


def test_a_frame_of_the_wrong_shape_is_refused():
    for call in (READER.read, M.picture_evidence, M.health_bar_pixels):
        try:
            call(np.zeros((360, 640, 3), np.uint8))
        except ValueError:
            continue
        raise AssertionError(f"{call} accepted a wrong size")


def test_only_the_cancel_button_is_dark_text():
    assert {cue.name for cue in M.CUES if cue.ink == M.DARK} == {"matchmaking_cancel"}
    assert all(cue.ink == M.WHITE for cue in M.CUES if cue.name != "matchmaking_cancel")


def test_ink_is_decided_on_every_colour_channel():
    pixels = np.array([[[200, 200, 200], [199, 255, 255], [255, 199, 255], [255, 255, 199]]], np.uint8)
    assert M._ink_mask(pixels, M.WHITE).tolist() == [[True, False, False, False]]
    pixels = np.array([[[90, 90, 90], [91, 0, 0], [0, 91, 0], [0, 0, 91]]], np.uint8)
    assert M._ink_mask(pixels, M.DARK).tolist() == [[True, False, False, False]]


def test_the_menu_needs_two_of_its_three_words():
    frame = FRAMES[row_where("lobby_menu")].copy()
    assert READER.read(frame, ["lobby_menu"])["lobby_menu"] >= M.SCORE_THRESHOLD
    blank_cue(frame, "menu_quests")
    assert READER.read(frame, ["lobby_menu"])["lobby_menu"] >= M.SCORE_THRESHOLD, "one covered word must not lose the lobby"
    blank_cue(frame, "menu_career")
    assert READER.read(frame, ["lobby_menu"])["lobby_menu"] <= 0.40, "one word alone is not enough"


def test_either_position_of_you_placed_counts():
    template = np.load(M.TEMPLATE_DIR / "you_placed_bar.npy")
    frame = np.full((720, 1280, 3), BLANK, np.uint8)
    x0, y0, _, _ = M._CUE["you_placed_bar"].box
    frame[y0 + 10:y0 + 10 + template.shape[0], x0 + 20:x0 + 20 + template.shape[1]][template] = 255
    assert READER.read(frame, ["you_placed"])["you_placed"] > 0.99


def test_either_banner_size_counts_as_victory():
    for name in ("victory_large", "victory_small"):
        template = np.load(M.TEMPLATE_DIR / f"{name}.npy")
        frame = np.full((720, 1280, 3), BLANK, np.uint8)
        x0, y0, _, _ = M._CUE[name].box
        frame[y0 + 12:y0 + 12 + template.shape[0], x0 + 25:x0 + 25 + template.shape[1]][template] = 255
        assert READER.read(frame, ["victory_royale"])["victory_royale"] > 0.99, name


def test_skipping_a_box_with_too_little_ink_can_never_hide_a_match():
    """The shortcut is only safe if a box under the ink limit could not have reached the threshold anyway."""
    random = np.random.default_rng(7)
    for name in ("connecting", "menu_locker", "spectating", "you_placed_screen"):
        template = np.load(M.TEMPLATE_DIR / f"{name}.npy").astype(np.float32)
        ink = np.argwhere(template)
        for _ in range(120):
            kept = ink[random.choice(len(ink), int(len(ink) * (M.MIN_INK_SHARE - 0.001)), replace=False)]
            mask = np.zeros(template.shape, np.float32)
            mask[kept[:, 0], kept[:, 1]] = 1.0                    # the best possible case: every ink pixel is a correct one
            assert V.best_template_correlation(mask, template)[0] < M.SCORE_THRESHOLD, name


def test_a_box_full_of_bright_sky_scores_zero():
    frame = np.full((720, 1280, 3), 255, np.uint8)
    frame[::7, ::5] = 40
    scores = READER.read(frame)
    assert all(value == 0.0 for value in scores.values()), scores


def test_a_black_or_flat_picture_scores_zero():
    for level in (0, 150):
        scores = READER.read(np.full((720, 1280, 3), level, np.uint8))
        assert all(value == 0.0 for value in scores.values()), (level, scores)


def test_a_black_picture_is_reported():
    assert M.picture_evidence(np.zeros((720, 1280, 3), np.uint8)).black is True
    assert M.picture_evidence(np.full((720, 1280, 3), 120, np.uint8)).black is False


def test_a_frozen_picture_is_reported():
    frame = FRAMES[0]
    first = M.picture_evidence(frame)
    assert first.change is None and first.frozen is False, "the first sample has nothing to compare with"
    again = M.picture_evidence(frame, first.sample)
    assert again.change == 0.0 and again.frozen is True
    moved = frame.copy()
    moved[::16, ::16] = 200
    later = M.picture_evidence(moved, first.sample)
    assert later.change > 1.0 and later.frozen is False


def test_the_sample_is_a_copy_of_the_picture():
    frame = FRAMES[0].copy()
    sample = M.picture_evidence(frame).sample
    before = sample.tobytes()
    frame[:] = 0
    assert sample.tobytes() == before


def test_the_health_bar_needs_a_solid_bar():
    frame = np.zeros((720, 1280, 3), np.uint8)
    assert M.health_bar_pixels(frame) == 0
    frame[665:675, 40:230] = (60, 220, 60)
    assert M.health_bar_pixels(frame) >= M.HEALTH_BAR_MIN_PIXELS
    stray = np.zeros((720, 1280, 3), np.uint8)
    stray[665:668, 40:230] = (60, 220, 60)                       # only three rows: not a bar
    assert M.health_bar_pixels(stray) == 0
    shield = np.zeros((720, 1280, 3), np.uint8)
    shield[650:656, 40:230] = (40, 150, 240)
    assert M.health_bar_pixels(shield) >= M.HEALTH_BAR_MIN_PIXELS


def test_the_combined_checks_are_within_budget():
    """Timing on a busy PC is noisy, so a slow first attempt gets two more chances."""
    for attempt in range(3):
        times = []
        for _ in range(4):
            for frame in FRAMES:
                begin = time.perf_counter()
                READER.read(frame)
                M.picture_evidence(frame)
                M.health_bar_pixels(frame)
                times.append(1000 * (time.perf_counter() - begin))
        if np.percentile(times, 99) < 10.0:
            return
    raise AssertionError(f"99th percentile {np.percentile(times, 99):.1f} ms is over the 10 ms budget")


def test_this_module_depends_only_on_what_it_needs():
    tree = ast.parse((ROOT / "src/fortnite_chest_counter/match_cues.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported |= {f"{node.module}.{alias.name}" for alias in node.names}
    visual = "fortnite_chest_counter.detection.visual."
    assert imported == {"dataclasses.dataclass", "pathlib.Path", "numpy", "fortnite_chest_counter.paths", visual + "NORMALIZED_HEIGHT", visual + "NORMALIZED_WIDTH",
                        visual + "best_template_correlation"}, imported


def test_counting_does_not_use_this_module_yet():
    for file in (ROOT / "src/fortnite_chest_counter").rglob("*.py"):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            names = [alias.name for alias in node.names] if isinstance(node, (ast.Import, ast.ImportFrom)) else []
            assert "match_cues" not in " ".join(names + [getattr(node, "module", None) or ""]), file.name


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
    print(f"{len(tests) - failed}/{len(tests)} match cue checks passed")
    sys.exit(1 if failed else 0)
