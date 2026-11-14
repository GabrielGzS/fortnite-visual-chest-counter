"""
Real-world detection cases (tests/cases/cases.json, docs/INVESTIGATION_2026-11-08.md) as permanent regression tests.

Each case's pop-up box masks (tests/fixtures/popups/<case>.npz, made by research/cases.py fixtures from the user's
diagnostic captures) are replayed through the real ChestEstimator. The pop-up channels work on that mask only, so the
pop-up decisions are the ones the full footage gives (research/cases.py run checks the full frames when the footage is
present). The other clues (prompt, sprite tag, ammo) see an empty picture here.

Every confirmed failure becomes a case: add it to cases.json, run `research/cases.py fetch` + `fixtures`, add a check.
A case with "profile_hud" is footage of that Fortnite HUD Scale: it is checked with that profile setting (v0.5.1).

Speed (v0.5.1): a replay is the real detector, about 16 ms a frame, and many checks replay the same case under the same rules. Each
distinct replay - case, channel switches, HUD Scale and the value of every detector constant - now runs once per process and is reused
(as a copy): 21 checks took 5 min 45 s before, 24 checks with six more cases take about 3 min 40 s. REPLAY_CACHE = False turns that
off, for a check that changes the detector's code rather than its constants.
Run:   python tests/test_cases.py          (or pytest)
       python tests/test_cases.py 75       only the checks with "75" in their name: the HUD Scale checks, about 1 min
"""

import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "src"))   # run without installing

import copy
import json
import types
from pathlib import Path

import numpy as np

from fortnite_chest_counter import estimator as E
from fortnite_chest_counter import settings
from fortnite_chest_counter.detection import visual as V

HERE = Path(__file__).resolve().parent
CASES = json.loads((HERE / "cases" / "cases.json").read_text(encoding="utf-8"))["cases"]
BEFORE, AFTER = 0.5, 2.5
REPLAY_CACHE = True
_REPLAYS = {}


def frames(name):
    d = np.load(HERE / "fixtures" / "popups" / f"{name}.npz")
    h, w = (int(v) for v in d["shape"])
    frame = np.zeros((V.NORMALIZED_HEIGHT, V.NORMALIZED_WIDTH, 3), np.uint8)
    for t, packed in zip(d["times"], d["masks"]):
        mask = np.unpackbits(packed)[:h * w].reshape(h, w).astype(bool)
        roi = np.where(mask[..., None], np.array([232, 196, 250], np.uint8), np.array([40, 36, 60], np.uint8))
        frame[V.ROI_Y:V.ROI_Y + h, V.ROI_X:V.ROI_X + w] = roi
        yield float(t), frame


def _value(v):
    return ("array", v.shape, str(v.dtype), hash(v.tobytes())) if isinstance(v, np.ndarray) else repr(v)


def _rules():
    """The value of every upper-case constant of the estimator and the detection modules: what configure() and _with() change."""
    mods = [E] + [m for n, m in sorted(sys.modules.items()) if n.startswith("fortnite_chest_counter.detection.") and m is not None]
    return tuple((m.__name__, k, _value(v)) for m in mods for k, v in sorted(vars(m).items())
                 if k.isupper() and not callable(v) and not isinstance(v, types.ModuleType))


def _replay(name, hud, channels):
    E.configure(dict(settings.DEFAULTS["detector"], hud=hud))
    key = (name, hud, tuple(sorted(channels.items())), _rules())
    if not REPLAY_CACHE or key not in _REPLAYS:
        est = E.ChestEstimator(**channels)
        events = []
        for t, f in frames(name):
            events += est.process_frame(t, f)
        events += est.flush()
        _REPLAYS[key] = [e for e in events if e["approx_counted"]]
    return copy.deepcopy(_REPLAYS[key])


def replay(name, **channels):
    return _replay(name, "standard", channels)


def score(name, counted):
    """-> (found, missed, duplicates, false) against the case's truth."""
    chests = [dict(r, hits=0) for r in CASES[name]["truth"] if r["what"] != "not_chest"]
    dup = false = 0
    for e in sorted(counted, key=lambda e: e["time"]):
        near = [c for c in chests if c["t"] - BEFORE <= e["time"] <= c["t"] + AFTER]
        free = [c for c in near if not c["hits"]]
        if free:
            min(free, key=lambda c: abs(c["t"] - e["time"]))["hits"] += 1
        elif near:
            dup += 1
        else:
            false += 1
    found = sum(1 for c in chests if c["hits"])
    return found, len(chests) - found, dup, false


def check(name, expect_found=None, **channels):
    counted = replay(name, **channels)
    found, missed, dup, false = score(name, counted)
    real = len([r for r in CASES[name]["truth"] if r["what"] != "not_chest"])
    want = real if expect_found is None else expect_found
    assert (found, dup, false) == (want, 0, 0), f"{name}: found {found}/{real}, missed {missed}, duplicates {dup}, false {false}"
    return counted


def test_fixtures_and_truth_exist_for_every_case():
    for name, case in CASES.items():
        if case.get("known_limitation"):
            continue
        assert (HERE / "fixtures" / "popups" / f"{name}.npz").exists(), name
        assert case["truth"] and all(r["what"] in ("new_popup", "new_line", "multiplier", "not_chest") for r in case["truth"])


def test_thiefs_small_hud_all_five_chests_and_only_strong_new_pop_ups_certain():
    counted = check("thiefs_small_hud")
    assert len(counted) == 5
    assert [e.get("increment", {}).get("kind") for e in counted] == [None, None, "new_line", "multiplier", "multiplier"]
    # M9H: a new small-HUD pop-up whose two small-word matches both reach SMALL_HIGH_* is CERTAIN (here 1.00 / 1.00, the pop-up the
    # template was cut from, and 0.90 / 0.98); stacked steps stay APPROX only, as before
    assert [e["certain_counted"] for e in counted] == [True, True, False, False, False]
    assert all(e["approx_counted"] for e in counted)
    assert all(e["scaled_popup"]["scale"] == E.SMALL_SCALE for e in counted)
    assert not replay("thiefs_small_hud", small_hud=False, stacked=False)                # v0.2.1: nothing at all


def _with(**constants):
    """Run with some estimator constants changed, then put them back."""
    class Patch:
        def __enter__(self):
            self.old = {k: getattr(E, k) for k in constants}
            for k, v in constants.items():
                setattr(E, k, v)

        def __exit__(self, *exc):
            for k, v in self.old.items():
                setattr(E, k, v)
    return Patch()


def test_small_hud_chests_on_a_720p_stream_are_found():
    """M9H: on a 720p stream the small word's exact match stayed at 0.68-0.73, under rc5's 0.75 trigger; the blurred match did not."""
    counted = check("thiefs_720p_stream_chests")
    assert not any(e["certain_counted"] for e in counted)                              # a 720p small word never reaches the CERTAIN bar
    with _with(SMALL_TRIGGER=0.75):
        assert not replay("thiefs_720p_stream_chests")                                 # rc5: all three missed


def test_a_pop_up_hidden_for_a_moment_by_the_map_counts_once():
    assert len(check("thiefs_720p_map_flash")) == 1
    with _with(SMALL_SAME_POPUP_SECONDS=0):
        assert len(replay("thiefs_720p_map_flash")) == 2                                # without the rule, the same pop-up twice


def _covered(name, seconds):
    """Replay a case with the pop-up box blanked for `seconds`, 0.5 s after every new pop-up (an inventory panel or the map)."""
    truth = [r["t"] for r in CASES[name]["truth"] if r["what"] == "new_popup"]
    E.configure(settings.DEFAULTS["detector"])
    est, events = E.ChestEstimator(), []
    for t, f in frames(name):
        if any(c + 0.5 <= t <= c + 0.5 + seconds for c in truth):
            f = f.copy()
            f[V.ROI_Y:V.ROI_Y + V.ROI_H, V.ROI_X:V.ROI_X + V.ROI_W] = np.array([40, 36, 60], np.uint8)
        events += est.process_frame(t, f)
    events += est.flush()
    return score(name, [e for e in events if e["approx_counted"]])


def test_the_maintainers_pop_up_covered_by_the_inventory_counts_once():
    counted = check("user_inventory_hides_popup")                      # v0.4.0: twice (66.07 and 67.80)
    assert len(counted) == 1 and counted[0]["scaled_popup"]["scale"] == 1.0
    with _with(SAME_POPUP_SECONDS=0):
        assert len(replay("user_inventory_hides_popup")) == 2          # without the rule, the same pop-up twice


def test_covered_pop_ups_count_once_on_every_channel():
    """v0.4.1: blanking real pop-ups for 0.75 s made v0.4.0 count them again on every channel (exact, scale-aware, small-HUD: 11
    duplicates over these cases). Each channel now remembers where its last pop-up's word was last seen. Chests added to a pop-up are
    still counted by the tracker, which resumes on the returning pop-up."""
    for name in ("thiefs_1080p_small_hud", "thiefs_small_hud", "user_plain_popups_approx_only"):
        found, missed, dup, false = _covered(name, 0.75)
        assert (missed, dup, false) == (0, 0, 0), (name, found, missed, dup, false)
    with _with(SAME_POPUP_SECONDS=0, SMALL_SAME_POPUP_SECONDS=0):
        assert _covered("user_plain_popups_approx_only", 0.75)[2] == 3   # v0.4.0's behaviour: every covered pop-up twice


def test_strong_1080p_small_hud_pop_ups_are_certain_and_steps_stay_approx():
    counted = check("thiefs_1080p_small_hud")
    assert [e["certain_counted"] for e in counted] == [True, True, False, False, False, False, False]
    with _with(SMALL_HIGH_EXACT=2.0):
        assert not any(e["certain_counted"] for e in replay("thiefs_1080p_small_hud"))  # rc5: all APPROX


def test_small_hud_channel_alone_finds_the_two_new_pop_ups():
    counted = replay("thiefs_small_hud", stacked=False)
    assert len(counted) == 2 and score("thiefs_small_hud", counted)[2:] == (0, 0)       # stacked steps need the tracker


def test_normal_hud_x2_and_x3_steps_are_counted_once_each():
    counted = check("replays_stack_x2_x3")
    steps = [e for e in counted if e.get("increment")]
    assert [s["increment"]["kind"] for s in steps] == ["multiplier", "multiplier"]
    assert not any(s["certain_counted"] for s in steps)                                  # multiplier steps: APPROX only
    assert len(replay("replays_stack_x2_x3", stacked=False)) == 1                       # v0.2.1: the first chest only


def test_a_new_chest_line_keeps_the_normal_rules():
    counted = check("replays_new_chest_line")
    line = [e for e in counted if e.get("increment")]
    assert len(line) == 1 and line[0]["increment"]["kind"] == "new_line"
    assert line[0]["certain_counted"] == counted[0]["certain_counted"]                   # tiers as for a new pop-up


def test_a_non_chest_line_added_to_the_pop_up_does_not_count_again():
    check("replays_sprite_level_line")
    old = replay("replays_sprite_level_line", stacked=False)                             # v0.2.1's position re-fire
    assert score("replays_sprite_level_line", old)[2] == 1                               # counted the same chest twice


def test_e0015_case_and_storm_phase_and_weakpoint_lines_do_not_count():
    check("replays_e0015_duplicate")
    check("replays_six_chests")


def test_old_position_re_fire_double_counts_the_e0015_pop_up_under_noise_and_the_tracker_does_not():
    """Live E0015 (not reproducible from the MJPEG recording): the same pop-up counted twice when the score hovered at
    0.75 and the scale-in animation had moved the word by 8 px. Same trace + small noise, both rules."""
    d = np.load(HERE / "fixtures" / "popups" / "replays_e0015_duplicate.npz")
    h, w = (int(v) for v in d["shape"])
    tpl = V.load_templates()[0]["array"]
    trace = []
    for t, packed in zip(d["times"], d["masks"]):
        m = np.unpackbits(packed)[:h * w].reshape(h, w).astype(np.float32)
        s, y, x = V.best_template_correlation(m, tpl) if m.sum() >= 20 else (0.0, 0, 0)
        trace.append((float(t), s, y, x))
    rng = np.random.default_rng(7)
    twice = {True: 0, False: 0}
    for _ in range(600):
        noise = rng.normal(0, 0.015, len(trace))
        for jump in (True, False):
            od = E.OnsetDetector(V.EVENT_HIGH_THRESHOLD, V.EVENT_LOW_THRESHOLD, True)
            fires = [t for (t, s, y, x), n in zip(trace, noise) if od.update(t, s + n, y, x, allow_jump=jump)]
            twice[jump] += sum(1 for f in fires if 185.9 <= f <= 188.3) > 1
    assert twice[True] > 0 and twice[False] == 0, twice


def test_every_case_finds_every_chest_once_and_nothing_else():
    for name, case in CASES.items():
        if not case.get("known_limitation") and not case.get("v041_gap") and not case.get("profile_hud"):
            check(name)
    for name, case in CASES.items():                       # footage of another HUD Scale: with that profile setting, as the user runs it
        if case.get("profile_hud"):
            found, missed, dup, false = score(name, replay_hud(name, case["profile_hud"]))
            assert (missed, dup, false) == (0, 0, 0), (name, found, missed, dup, false)


def replay_hud(name, hud):
    try:
        return _replay(name, hud, {})
    finally:
        E.configure(settings.DEFAULTS["detector"])


def test_hud_75_finds_every_chest_of_the_maintainers_cases():
    """v0.4.1, [detector] hud = "75": the CHEST word as the maintainer's game draws it (research/hud75_templates.py). The templates come
    from this recording, so these cases are in-sample; held out: match 1's consensus on match 2's pop-ups, 11 of 13 CERTAIN by today's
    rules, and leave-one-out 17 of 18. Every rule after the template is unchanged."""
    certain, types = {}, {}
    for name in [n for n in CASES if n.startswith("user_")]:
        counted = replay_hud(name, "75")
        found, missed, dup, false = score(name, counted)
        # the CHEST line added to a CROWN BONUS pop-up looks, to the blurred channel, like the non-chest pop-ups that HUD_SCALED_* rejects
        expect = 1 if name == "user_chest_line_on_crown_bonus" else 0
        assert (missed, dup, false) == (expect, 0, 0), (name, found, missed, dup, false)
        certain[name] = sum(e["certain_counted"] for e in counted)
        types[name] = [e["chest_type"] for e in counted]
    assert certain == {"user_inventory_hides_popup": 1, "user_plain_popups_approx_only": 3, "user_chest_line_on_crown_bonus": 0,
                       "user_low_margin_popup": 1, "user_bright_background_popup": 0, "user_two_rares_then_rare_line": 3,
                       "user_storm_phase_popup": 0}, certain     # NEW STORM PHASE: counted without HUD_SCALED_* (blurred channel alone)
    assert types["user_two_rares_then_rare_line"][:2] == ["rare", "rare"]           # v0.4.0: unknown, unknown


USER1114 = {          # case: (found, CERTAIN) with the 75% profile, (found, CERTAIN) with Standard - tests/cases/user_20261114.json
    "user1114_three_close_popups": ((3, 3), (2, 0)), "user1114_chest_storm_phase_chest": ((2, 1), (1, 0)),
    "user1114_late_exact_popup": ((1, 1), (1, 0)), "user1114_approx_only_chest": ((1, 0), (0, 0)),
    "user1114_shields_and_sprite_level": ((0, 0), (0, 0)), "user1114_shield_cracked": ((0, 0), (0, 0))}


def test_hud_75_on_footage_its_templates_were_not_cut_from():
    """v0.5.1: the maintainer's second recording at HUD Scale 75% (720p30, 4 Mbps NVENC), the first the 75% templates did not come from.
    The whole video with the 75% profile: 17 of 17 chests, 15 CERTAIN, 0 false, 0 duplicates, the match Complete. These windows hold
    its three close pop-ups, the chest line added after NEW STORM PHASE, the late exact match, the one APPROX-only pop-up and the
    nearest non-chest words. Every result equals research/cases.py run on the full frames."""
    assert {n for n in CASES if n.startswith("user1114_")} == set(USER1114)
    for name, ((found, certain), _) in USER1114.items():
        counted = replay_hud(name, "75")
        got, missed, dup, false = score(name, counted)
        assert (got, missed, dup, false) == (found, 0, 0, 0), (name, got, missed, dup, false)
        assert sum(e["certain_counted"] for e in counted) == certain, name


def test_standard_on_75_footage_is_what_the_maintainer_saw_live():
    """The live session behind v0.5.1 ran with the Standard HUD Scale (the 75% choice was never saved): only the APPROX-only blurred
    channel ("near-normal pop-up, shape not exact") finds these pop-ups, so nothing is CERTAIN and some are missed, never a false one."""
    for name, (_, (found, certain)) in USER1114.items():
        counted = replay(name)
        got, missed, dup, false = score(name, counted)
        assert (got, dup, false) == (found, 0, 0) and sum(e["certain_counted"] for e in counted) == certain == 0, (name, got, dup, false)
        assert all(e.get("scaled_popup", {}).get("scale") == 1.0 for e in counted), name


def test_a_storm_phase_line_added_to_a_75_pop_up_can_pass_for_a_chest_line():
    """Known weakness, pinned (user_20261114.json known_weakness): with the 75% template NEW STORM PHASE scored up to 0.79 for a few
    frames, over the 0.75 chest-line level, so the tracker counted the second chest 0.3 s before its real CHEST line appeared. When this
    changes (the count dated at the real line, about 361.95 s), check the line rule and update this test."""
    added = [e for e in replay_hud("user1114_chest_storm_phase_chest", "75") if e.get("increment")]
    assert len(added) == 1 and added[0]["increment"]["kind"] == "new_line" and added[0]["time"] < 361.8 and added[0]["chest_type"] == "unknown"


def test_hud_75_changes_nothing_on_the_standard_profile():
    for name in ("replays_six_chests", "thiefs_1080p_small_hud", "user_plain_popups_approx_only"):
        assert [e["time"] for e in replay(name)] == [e["time"] for e in replay_hud(name, "standard")], name


def test_v041_gaps_reproduce_exactly_until_fixed():
    """The maintainer's own recording (tests/cases/user_20261112.json): v0.4.0 on a 0.95x pop-up. Each gap is pinned exactly, so a change
    that fixes it fails here on purpose: then remove its "v041_gap" and the case must pass like every other (found all, 0 duplicates,
    0 false)."""
    gaps = {name: case for name, case in CASES.items() if case.get("v041_gap")}
    assert len(gaps) == 5                                                  # 6 in M0; the inventory duplicate is fixed
    for name, case in gaps.items():
        gap = case["v041_gap"]
        counted = replay(name)
        found, missed, dup, false = score(name, counted)
        real = len([r for r in case["truth"] if r["what"] != "not_chest"])
        assert found < real or dup or gap["certain"] < real, f"{name}: a gap entry must describe a failure"
        got = {"found": found, "duplicates": dup, "false": false, "certain": sum(e["certain_counted"] for e in counted)}
        want = {k: gap[k] for k in got}
        assert got == want, f"{name} changed: {got} (pinned v0.4.0 gap {want}). Fixed? Remove its v041_gap. Worse? Investigate."


def test_five_chest_vault_counts_every_step_including_the_third_lines_x2():
    counted = check("replays_vault_five_chests")
    assert sorted((e.get("increment") or {}).get("kind") or "new" for e in counted) == \
        ["multiplier", "multiplier", "new", "new_line", "new_line"]


def test_a_late_exact_match_on_a_pop_up_already_counted_is_the_same_pop_up():
    counted = check("replays_chest_x2_late_exact")                     # scale-aware onset + X2, no third count
    assert len(counted) == 2
    old = replay("replays_chest_x2_late_exact", stacked=False)
    assert len(old) == 2 and not any(e.get("increment") for e in old)  # v0.2.1: right total, for the wrong reason


def test_non_chest_lines_and_an_unchanged_pop_up_are_not_counted_again():
    for name in ("replays_weakpoint_line", "replays_static_popup_refire"):
        assert len(check(name)) == 1
        with _with(SAME_POPUP_SECONDS=0):                                # v0.2.1 had neither the tracker nor the pop-up memory
            _, _, dup, false = score(name, replay(name, stacked=False))
        assert dup + false == 1, name                                    # v0.2.1 counted the same chest twice
    # v0.4.1: the unchanged pop-up's re-fire is the same word at the same place within 2 s, so the memory alone stops it too
    assert score("replays_static_popup_refire", replay("replays_static_popup_refire", stacked=False))[2:] == (0, 0)


def test_portuguese_only_settings_keep_the_position_re_fire_and_no_new_channels():
    E.configure(dict(settings.DEFAULTS["detector"], languages=["pt"], medium_counts_alone_languages=[]))
    try:
        est = E.ChestEstimator()
        assert est.small is None and not est.stacked and est.popup.use_position
    finally:
        E.configure(settings.DEFAULTS["detector"])


if __name__ == "__main__":
    # python tests/test_cases.py [WORD ...]: only the checks whose name holds one of the words, e.g. "75" for the HUD Scale checks
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)
             and (len(sys.argv) < 2 or any(word in n for word in sys.argv[1:]))]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except Exception:
            failed += 1
            import traceback
            print(f"  FAIL  {name}")
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} case checks passed")
    sys.exit(1 if failed else 0)
