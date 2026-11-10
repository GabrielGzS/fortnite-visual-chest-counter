# M4 validation record

Date: 2026-11-10. Branch: `dev/v0.3.0`, on top of `f722fa0`. M4 connects the corrected M1 and M2 to the live
loop in shadow mode only. It does not change recognition: `match_cues.py`, `match_state.py`, the truth
annotations and the M3 scorecard are unchanged.

## What was added

`src/fortnite_chest_counter/match_tracker.py` has `offer(t, frame)`, `chest(ev)` and `close(reason)`.
`[match] mode` is `off` (the default) or `shadow`. `on` is refused with a warning and falls back to `off`.
`live` and `simulate` also accept `--match-mode`. The `video` command has no tracker.

Shadow mode's only output is `match_state` lines in the session log, plus `match_*` fields on `session_end`.
Those lines never have a `time` key, because `research/regress.py` and `research/match_replay.py` read any line
with one as a chest event. The app's `stopped` message is unchanged.

Decisions worth reviewing:

- Samples are at least one second of source time apart, so at most one per second. Real frame timing makes the
  average slightly slower: 96 to 97 samples in 100 s live.
- A chest that began before a break in the video (a gap over `MAX_SAMPLE_GAP`, or time running backwards) is
  dropped. The detector finishes events late, so without this a chest from before a long outage could arrive
  just after it and open a joined-late match with nothing on screen to support it. This extends M2's rule that
  pending evidence cannot cross a break.
- A chest delivered on a black or frozen sample is ignored by M2 and not carried over, the same as the offline
  replay. Chests still waiting at shutdown are counted in the summary and never given to M2.
- If the tracker fails, any open match is left unrecorded, so a failed tracker makes no claim about it.
- `close` uses the last frame actually seen, not the source's clock.

## Results

| Check | Result |
|---|---:|
| M4 tracker suite (`tests/test_match_tracker.py`) | 63/63 pass |
| M4 targeted mutations (`research/match_tracker_mutations.py`) | 34/34 caught |
| M2 lifecycle suite | 78/78 pass |
| M2 audit regressions | 26/26 pass |
| M3 replay scorecard suite | 38/38 pass |
| M3 targeted mutations | 11/11 caught |
| M1 cue suite | 25/25 pass |
| Affected existing suites: basics, profiles, types, OBS, stream, release, app | 6, 10/10, 9/9, 18/18, 8/8, 77/77, 30/30 pass |

One test in each of the M1 and M2 suites, `test_counting_does_not_use_this_module_yet`, stated a rule that M4
deliberately ends. Both became `test_only_the_tracker_uses_this_module`. The M4 suite adds a stricter check:
counting reaches the tracker only through a lazy import in `_open_tracker`, and `off` loads none of it.

The first mutation run caught 28 of 29. The survivor edited an event after it had been counted and logged, so
it could do no harm, but it exposed that no whole-loop test proved chests reach the tracker. That test was
added and the survivor replaced with mutations that can do harm.

### Real video, first 100 s (`research/match_shadow_check.py`)

Run with the pinned M0 FFmpeg (SHA-256 `7A1CC6F3...1C83F0`), one clip at a time. Off and shadow are separate
processes. Events, OBS files and saved counts were identical between them, ignoring only clock fields in the
state file. Events that began in the first 90 s match the frozen M0 baseline exactly. The last 10 s are left
out because ending the window early can legitimately finish a later event differently.

| Clip | Events in window | Compared with M0 | CERTAIN | APPROX | Result |
|---|---:|---:|---:|---:|---|
| `en` | 6 | 6 | 6 | 6 | Pass |
| `ps5` | 6 | 5 | 1 | 5 | Pass |

### CPU in the real live loop (100 s real time, `live --source file`)

| Run | Samples | ms avg | ms max | Tracker share of one core | Whole process |
|---|---:|---:|---:|---:|---:|
| `en`, off | none | none | none | none | 47.0% |
| `en`, shadow | 97 | 1.957 | 4.288 | 0.192% | 47.2% |
| `ps5`, shadow | 96 | 1.913 | 4.260 | 0.186% | 46.3% |

The budget is 1% of one core. The tracker's figure is wall-clock time inside `offer`, so at worst an
overestimate of its CPU. The whole-process figures are single runs on the main PC, and a 0.2-point difference
is within run-to-run noise. No frames were dropped in any run, and detection held 15 fps.

## Requirements

1. M1, M2 and M3 suites pass (above).
2. At most one sample per second of source time at 5, 10, 15 and 30 fps and over 20 seeded variable-rate runs.
3. Frames are unmodified: hash checks, read-only frames, and no retained reference to a frame.
4. Chest events are identical off and in shadow: scripted whole-loop runs of `live` and `simulate`, and real video.
5. OBS files and saved totals are identical off and in shadow, in the same runs. `match_tracker.py` imports no
   settings, profile, file or console code, enforced by a test.
6. Injected failures in the reader, state machine, log, warning, closing, malformed events, bad frame times and
   missing templates each give at most one warning and leave counting identical. Ctrl+C is not swallowed.
7. Overhead is measured separately and is 0.19% of one core against the 1% budget.
8. Gaps, long outages, time running backwards, long black pictures, Ctrl+C, a vanished source and stopping
   invent no complete match, and every record passes the M3 time invariants. Controls prove a whole
   uninterrupted match is still complete.

Replaying all five cached timelines through the tracker gives the same records and transitions as the offline
replay. The known miss is pinned: the edited English recording still produces one non-complete record.

The frozen detector check passes: `git diff --exit-code 032df3b` on `detection/`, `estimator.py` and
`templates/` (except `match/`) reports no difference. The 25-minute full regression was not repeated.

Local, git-ignored evidence is under `analysis_output/m4/`.

## Limits retained

- The real-video windows only exercise joining late and stopping. Full lifecycles in the tracker are covered by
  cached timelines and synthetic scripts. No real footage yet holds a whole match from pre-game to ending.
- The edited English recording still fails the M3 scorecard, on purpose. Cached replay remains 4/5.
- Annotations remain provisional pending human review.
- A real livestream, OBS camera or capture card has not been run in shadow mode. Live checks used `--source file`.
- A stream reconnect shorter than `MAX_SAMPLE_GAP` (5 s) is treated as continuous, per M2.
- `packaging/build_release.py` does not ship `templates/match/` yet. In a packaged build, shadow mode gives one
  warning and stays off, and counting is unaffected. This belongs to M9.

Nothing was pushed, merged, tagged or published. Stop for review before M5.
