# v0.5.1 validation

A focused patch after the maintainer's live test at Fortnite HUD Scale 75% reported APPROX only, never CERTAIN, every match Partial, and
Console reasons "blurred match", "near-normal pop-up, shape not exact". Budget set at the start: diagnosis on frames and short windows,
at most one whole-video run per HUD setting, then the fast fixtures, one packaging check.

## Evidence

`samples/video tests/2026-11-14 23-27-13.mp4` (SHA-256 d0939dd3…094197c). ffprobe: H.264 High, 1280x720, 30/1 fps, 4.00 Mbps, 1,048 s,
the same format as the 2026-11-12 recording the 75% templates were cut from. Ground truth: `tests/cases/user_20261114.json` (17 chests,
17 non-chest pop-ups, the match screens). Candidates came from two whole-video sweeps of the pop-up box only (31 s and 98 s): lavender
bursts, and both CHEST templates' exact and blurred scores on every frame. Every candidate was then checked by eye, with frame strips
where a pop-up spans a camera turn. One label was corrected while checking: 360-364 s is one pop-up holding two chests (+600 / MAXIMUM AMMO
/ NEW STORM PHASE / +600 = +2,350 XP), not a duplicate.

## Root cause

1. **The live session ran with the Standard HUD Scale.** None of the installed profiles on the main PC has a `hud` entry, and Settings
   discarded unsaved choices without a word (`SettingsPage.load()` ran on every visit; Save sat below every card). The session log had
   no HUD field, so the run could not prove otherwise.
2. **Every symptom is Standard on a 75% HUD, by design.** The 27 px Standard CHEST template scores 0.47-0.58 exact on these pop-ups, so the
   exact path never fires. Only the scale-aware blurred channel at x1.0 finds them, and that channel is APPROX only
   (`estimator.SCALE_AWARE_POPUPS`). Its Console wording is `console._why`: "near-normal pop-up, shape not exact" and
   `console._evidence`: "blurred match 0.8x (MEDIUM)". The countdown, LAUNCHING IN and YOU PLACED at 75% are read only by the 75% cue
   templates (`match_cues.HUD_SCALE_CUES`, loaded only for a 75% profile), so the start is not observed and the end reads as "stopped":
   Partial.

Whole video, real pipeline (`research/pipeline_baseline.py`, one run per setting, about 12.7 minutes each, run side by side):

| | Standard | 75% |
|---|---:|---:|
| Chests found (of 17) | 12 | 17 |
| CERTAIN | 0 | 15 (the APPROX two: exact 0.70 at 761 s; the added line at 361.5 s) |
| Duplicates / false | 0 / 0 | 0 / 0 |
| Match | partial, ended by stopped, start not observed | complete, countdown 46 s, YOU PLACED 1001 s, 938 s |
| Detector ms/frame (mean, p95) | 12.7, 39.0 | 12.8, 38.9 |

The 75% templates came from a different recording, so this is the first independent check of them: they hold. **No detector change.**

## Known weakness, pinned and not changed

At 361.5 s, the NEW STORM PHASE line added below a chest pop-up scored 0.73-0.79 (blurred) against the 75% template for a few frames.
That is over the stacked tracker's 0.75 chest-line level (`STACKED_LINE_MIN`, measured on the Standard template, where the same line
scores 0.63-0.71). The tracker counted it as the added chest line 0.4 s before the real CHEST line (0.85-0.88) arrived, and the real line
then fell inside the 0.6 s settle time. The total is right; without a following chest it would be one false APPROX. One example, and
real chest lines dip to 0.72 on the same frames, so no level separates them: `test_a_storm_phase_line_added_to_a_75_pop_up_can_pass_for_a_chest_line`
pins it.

## Changes

- Settings (`gui/app.py`): Save changes and a status in a bar that stays at the top (`page_layout(header=...)`); dirty tracking over
  every setting; Save enabled only when there is something to save; "Settings saved" only after the detector settings are read back from
  `config.toml` and the profile; a failed save keeps the changes and says why; leaving the page or closing the app with unsaved changes
  asks save / discard / stay (`ask_unsaved`, only when the page is visible); the mouse wheel over a drop-down or number box scrolls the page
  (`WheelToPage`); the HUD card shows the saved value.
- The HUD Scale a run uses (`counter.hud_line`): announced when counting starts (live and simulate), recorded in `session_start` as
  `"hud"`, and in the diagnostics report for the active profile.
- Fixtures: six pop-up cases from the new recording (`user1114_*`, `"profile_hud": "75"`), its 75% cue frames
  (`user_20261114_cues75.npz`), and both runs' match Observations (`user_20261114_observations{,_hud75}.json.gz`): 161 KB with the
  truth file.
  `research/cases.py run` honours `profile_hud` (`--hud` overrides).
- `tests/test_cases.py`: each distinct replay (case, channels, HUD Scale and every detector constant's value) runs once per process,
  `REPLAY_CACHE = False` turns that off, and `python tests/test_cases.py 75` runs only the HUD Scale checks.

## Fast checks

| What | Kind | Time |
|---|---|---:|
| `tests/test_settings_ui.py` (16) | the real window off screen, at its smallest size | 5 s |
| `tests/test_cases.py 75` (5) | pop-up masks: 75% on both recordings, Standard on the 75% footage, the pinned weakness | 1 min |
| `tests/test_cases.py` (24; was 21 in 5 min 45 s) | every pop-up case | 3 min 40 s |
| `tests/test_match_cues.py` (40) | cue boxes, incl. the new 75% screens and that Standard does not read them | 4 s |
| `tests/test_user_recording.py` (8) | match Observations through the state machine: Complete at 75%, Partial at Standard | 0.3 s |
| `research/cases.py run --case user1114_…` (needs the video) | full frames of the six windows, about 45 s of video | 38 s (75%), 28 s (Standard) |

The full-frame windows give exactly the mask fixtures' events (times, CERTAIN / APPROX), so the masks are a faithful fast stand-in for
the pop-up decisions; frame order and state transitions over a whole match are covered by the Observation replays.

Sabotage checks of the new Settings tests (each must fail): wheel guard off, leave guard off (page and close), dirty tracking off: all
four caught.

## Regression run for this patch

test_settings_ui 16/16, test_cases 24/24, test_match_cues 40/40, test_user_recording 8/8, test_types 9/9 (the profile cases are read with
their own HUD; 0 wrong types; unknown 2 of 11 on 75% footage), test_match_ui 50/50, test_dashboard_views 27/27, test_update_gui 70/70,
test_live_match 88/88, test_update_release 68/68, test_release_notes 6/6, test_profiles 12/12, test_basics 6/6, test_app 30/30
(293 s: it replays a sample video through the worker), test_release 79/79. The detector code is unchanged, so the en / PS5 `regress.py` snapshots from v0.4.0 (byte-identical since
v0.3.0) are reused, not rerun; the Standard cases in `test_cases.py` (Replays, Thiefs, the 2026-11-12 Standard gaps) all pass unchanged.

## Remaining limits

- 75% is one player, one resolution (2560x1440 → 1280x720 30 fps, NVENC 4 Mbps), two recordings. Other HUD Scales and qualities are
  untested; a live session with 75% saved is still pending.
- The chest line NEW STORM PHASE can stand in for, described above.
- The pop-up counted at 382.2 s (true onset 380.6 s) passed the 0.75 exact trigger late; it counts once, CERTAIN, typed unknown.
