# M6 validation record

Date: 2026-11-11. Branch: `dev/v0.3.0`, on top of `38f1c18`. M6 connects the match tracker and match history to the
live loop. It stays off by default and adds no Dashboard, Analytics tab or packaging.

## What was added

`[match] mode` now accepts `on`, which keeps match history, for explicitly enabled testing. The default stays `off`.

`[match] heartbeat_seconds` is 30, 60 (default), 300 or 600; anything else warns and falls back to 60. It is read
once when counting starts. It decides only how often running totals reach the disk: sampling stays at one per
second and time is accumulated continuously. The graphical setting is M7.

| Where | Change |
|---|---|
| `CounterSession.apply` | Appends each counted chest, after the totals are saved |
| `CounterSession.apply_type_updates` | Appends a chest-type change |
| `CounterSession.sync_external_changes` | Records a counter change, even when the counts look unchanged |
| `_run_live`, `cmd_simulate` | Open and end the run |
| `match_tracker.py` | Passes state changes and matches to history; writes checkpoints |
| `match_state.py` | `snapshot()`, read-only running totals |
| `match_history.py` | `attribute()`; a run never ends with a match left open |

Checkpoints are written on the interval of source time, at every match opening and closing, and on normal
shutdown. `cmd_video` is not connected, so analysed recordings never enter history. Saving turned off means no
history. An explicit `--state` file gets `history/<file name>` beside it.

`attribute()` works out each chest's match from its own time. A chest is credited only during active play. One
after elimination or the ending is flagged as spectating and not credited, and one outside every match belongs to
none. A real reboot is therefore not credited; that is the conservative M2 behaviour.

Two M5 behaviours changed. Ending a run now closes a match the tracker never closed, as interrupted. The repeat
check now compares source time to the millisecond, matching how the counter identifies a chest for type updates.
Identity is still `run_id` + `counter_epoch` + `event_id`.

## Results

| Check | Result |
|---|---:|
| M6 recording suite (`tests/test_match_recording.py`) | 50/50 pass |
| M6 targeted mutations (`research/match_recording_mutations.py`) | 37/37 caught |
| M5 history suite and mutations | 98/98, 57/57 |
| M4 tracker suite and mutations | 63/63, 35/35 |
| M2 lifecycle and audit | 78/78, 26/26 |
| M3 scorecard and mutations | 38/38, 11/11 |
| M1 cues | 25/25 |
| Basics, profiles, types, stream, release, app | 6, 10/10, 9/9, 8/8, 77/77, 30/30 |
| OBS | 17/18, see below |

**The OBS failure is not from M6.** `test_wrong_password_and_kick_are_not_retried` fails intermittently: 1 full
run, then 3 of 6 re-runs here. An untouched export of the published v0.2.3 code failed the same check in 2 of 8
runs, and the OBS code is unchanged since then. It was left alone as out of scope.

Existing tests changed because M6 deliberately ends what they stated: `test_on_is_refused_until_it_exists` became
`test_on_can_be_chosen_explicitly`; `test_on_requested_on_the_command_line_runs_nothing` became
`test_a_mode_that_does_not_exist_runs_nothing`; `test_tracking_is_off_by_default` now checks only the mode; M5's
`test_nothing_in_the_program_uses_history_yet` now requires a lazy import; and M5's test that a finished run keeps
an unclosed match became `test_a_run_never_ends_with_a_match_left_open`.

Three mutations survived at first. One was harmless by construction, because the writer also refuses uncounted
chests, and was dropped. Two exposed weak tests, now tightened. Auditing how mutations were caught also found one
caught for the wrong reason, a crash from mixing two copies of a module; that test now compares real values.

### Real video, first 100 s (`research/match_shadow_check.py`)

Pinned M0 FFmpeg, one process per mode, one clip at a time. Events, OBS files and saved counts were identical across
`off`, `shadow` and `on`, ignoring only clock fields in the state file. Events starting in the first 90 s match the
frozen M0 baseline exactly. In `on`, history held exactly the counted chests, ended cleanly with no gaps, and
reported the same matches and state changes as shadow.

| Clip | Events | Compared with M0 | CERTAIN | APPROX | History chests | Result |
|---|---:|---:|---:|---:|---:|---|
| `en` | 6 | 6 | 6 | 6 | 6 | Pass |
| `ps5` | 6 | 5 | 1 | 5 | 5 | Pass |

The sixth `ps5` event was not counted, so it is correctly absent from history.

### A real process kill on real video

The real `live` pipeline on the English clip, in `on` mode, was force-killed after about 80 s and restarted. The
last checkpoint was at 65.45 s, so the recovered match is closed there as interrupted and partial, claiming 65.3 s of
active play and nothing after it. The four chests counted before the kill are all in history, the totals were 4 and
4 before and after, no gap was reported, and the time rules hold. A separate automated test kills a scripted run with
`TerminateProcess` at every test run.

### CPU in the real live loop (100 s real time, English clip, alternating)

| Pair | Off, whole process | On, whole process | Tracker share of one core |
|---|---:|---:|---:|
| 1 | 46.7% | 47.8% | 0.221% |
| 2 | 47.5% | 47.8% | 0.223% |
| 3 (machine busy) | 59.5% | 69.3% | 0.374% |

The budget is 1% of one core. In pair 3 both runs rose and so did detection time, which M6 does not touch, so that
pair reflects other programs competing for the CPU. No frames were dropped in any run. A chest's history write
happens in the counting thread, after that chest is counted and saved, and adds about 6 ms to that one frame:
the worst frame was 61 ms with `on` against 53 to 56 ms with `off`, inside the 66.7 ms frame budget. Checkpoints are
written outside the detector's timing.

### Heartbeat options

All four intervals pass: spacing follows the setting, matches and state changes are identical across them, sampling
stays at one per second, and recovery after a crash at four different moments never claims more than was really
observed and never loses more than one interval. Changing the setting between runs is safe; a change during a run
waits for the next run.

The frozen detector check passes against `032df3b`. The 25-minute full regression was not repeated. Local, git-ignored
evidence is under `analysis_output/m6/`.

## Limits retained

- A real livestream, OBS camera or capture card has not been run in `on` mode. Live checks used `--source file`.
- Real-video windows only exercise joining late and stopping. Full lifecycles use cached timelines and synthetic
  scripts, because no real footage holds a whole match yet. No complete match has come from real footage.
- The edited English recording still fails the M3 scorecard, on purpose. Cached replay remains 4/5.
- Annotations remain provisional.
- `simulate` is not covered by the single-instance guard, so running it in `on` mode against a profile that is
  counting live could mark that run as crashed. It is a development command.
- `packaging/build_release.py` does not ship `templates/match/` yet. In a packaged build the tracker warns and stays
  off; chests would still be recorded. This belongs to M9.

Nothing was pushed, merged, tagged or published. Stop for review before M7.
