# v0.4.0 validation

Results of each v0.4.0 milestone, in order. Plan and decisions: [V0_4_0_PLAN.md](V0_4_0_PLAN.md). Tests are run with the project's own
virtual environment (`.venv\Scripts\python.exe tests\<file>.py`); mutation checks with `PYTHONPATH=src` (`research\<name>_mutations.py`).
The detector is not touched in v0.4.0, so the full-video regression (`research\regress.py`) is not rerun; detector files are compared
byte for byte with v0.3.0 at release qualification.

## M1 — Timing foundation

### What changed

| Area | Change |
|---|---|
| History (D7) | `counter._open_history` keeps history whenever counts are saved, with match tracking on, off or in shadow mode. Match rows are still written only in "on" mode (`_tracker_history`). Analysing a recording still never enters history |
| Heartbeats | `counter.HistoryHeartbeat` writes the same heartbeat row every `[match] heartbeat_seconds` of source time when the tracker does not: tracking off, shadow mode, or a tracker that stopped after an error (`MatchTracker.keeps_history`). With the tracker running it writes nothing, so there are no duplicates |
| Reading | `match_history.last_heartbeats(folder, run_ids)` finds the newest heartbeat of the given runs, parsing only those lines |
| Time model | New pure module `timeline.py`: runs as wall-clock intervals, sessions, local days and weeks (section 3 of the plan) |
| Settings | The match tracking card says that chest history is kept either way; the checkbox is now **Track matches**; **Save progress every** is always enabled because it applies to history in general. The `[match]` keys are unchanged, so every existing `config.toml` keeps working |
| Messages | A history write or start failure now says "chest and match history could not ..." |

No file format changed: the same row kinds and `schema = 1` as v0.3.0.

### Behaviour changed on purpose

v0.3.0 kept no history with tracking off. These v0.3.0 checks encoded that rule and were rewritten to the approved rule, not deleted:

| v0.3.0 check | Now |
|---|---|
| `test_only_on_keeps_a_history` | `test_only_on_keeps_match_rows`: every mode keeps the run and its chests; only "on" adds match rows |
| `test_off_and_shadow_load_no_history_code` | `test_off_and_shadow_load_no_match_code`: tracking off still loads none of the match code (tracker, cues, state machine) |
| `test_the_desktop_app_sees_no_difference` | Compares a run with no history at all (saving off) with tracking on, since tracking off now keeps history too |
| `test_settings_start_on_at_a_minute`, `test_turning_it_on_is_saved_and_read_back` | The save interval is enabled with tracking off |

Mutation checks that pointed at moved code were re-anchored (recording 3, UI 2, history 1, tracker 4); none was dropped.

### How the time model handles the hard cases (all tested)

| Case | Result |
|---|---|
| Clean run | Lasts its own `elapsed_seconds`; a wall clock that disagrees by more than 2 minutes is flagged, never used |
| Crash, not yet recovered | Ends at its last heartbeat ("at least") |
| Crash, recovered days later | Ends at `last_seen_at`. The recovery row's own `at` (the moment of recovery) is never used: tested with a three-day gap |
| Crash before any heartbeat | Zero length, cut short |
| The run counting now | Lasts until now |
| `simulate` runs | Left out |
| A time with no UTC offset | Not guessed at |
| Runs 29:59 apart / exactly 30:00 apart | One session / two sessions; the gap is reported, never counted as counting |
| Overlapping runs | Counted once |
| Midnight | A run is split between the two days |
| Daylight saving | The spring day has 23 hours and the autumn day 25 (tested with a real Central European zone written into the test fixtures, because Windows Python has no time zone database) |

### Size and speed

`research/history_scale.py` wrote a synthetic year shaped like the maintainer's real session (per counted hour: 180 chests, 40 manual
corrections, 60 heartbeats, 6 matches), 2 hours a day for 365 days: **81.8 MB**, 131,400 chests, 4,380 matches, 29,200 corrections.

| Step | Time (main PC) |
|---|---:|
| Read everything but heartbeats | 0.90 s |
| Match statistics (`summarize`) | 0.22 s |
| Runs and sessions | < 0.01 s |
| Time counting by day | < 0.01 s |
| Last heartbeat of one run | 0.03 s |

A year of heavy use stays around one second, off the window's thread. **Decision: no cache in v0.4.0.**

### Compatibility with v0.3.0

`match_history.py` taken from the `v0.3.0` tag read histories written by this code in all three modes: 1 run and 3 chests each (and 1 match
in "on" mode), **0 damaged rows, 0 newer rows**. A rollback to v0.3.0 therefore reads v0.4.0's history normally. A structural test
(`test_history_writes_only_row_kinds_v030_knows`) keeps it that way.

### Tests

| Suite | Result |
|---|---:|
| `test_timeline` (new) | 32/32 |
| `research/timeline_mutations.py` (new) | 28/28 caught |
| `test_match_recording`, `test_match_history`, `test_match_tracker` | 50/50, 98/98, 68/68 |
| `test_live_match`, `test_corrections`, `test_match_analytics`, `test_match_ui` | 88/88, 82/82, 61/61, 50/50 |
| `test_profiles`, `test_dashboard_views`, `test_app`, `test_basics`, `test_release`, `test_stream`, `test_types` | all pass |
| Mutations: recording, UI, history, tracker, live match, corrections, stall, Dashboard, analytics | 37/37, 40/40, 57/57, 43/43, 59/59, 58/58, 19/19, 25/25, 51/51 |

`test_listing_5000_matches_takes_under_100_ms` failed once while other suites ran in parallel and passed when rerun alone: a wall-clock
check under load, as seen in v0.3.0.

### Limitations

- During a video stall the loop gets no frames, so no heartbeats: if the app then crashes, the run's length is a lower bound.
- Days use the PC's current time zone rules. Changing the PC's time zone re-dates history accordingly.
- Two mutation checks (17, 18 in `timeline_mutations.py`) need the PC's zone to differ from UTC, which it does here.

## M2 — Progress metrics

New pure module `progression.py`: one `Snapshot` per history read gives chests per hour of session time, today / this week / last 7 /
last 30 days / all time, days and weeks with their status (chests, known zero, not counted), averages per monitored, active and
calendar day and week (completed days only), best day and week, sessions with their rates, and the current and best hour.

Rules as tested (`tests/test_progression.py`, a hand-worked fortnight in a real daylight-saving zone):

- Recorded chests = detected + standing +1s − standing −1s (D3); undone corrections never happened; `simulate` runs left out.
- Spectated chests leave progress only inside a recognised English Complete or Partial match not marked Not a match (D4); elsewhere they count.
- Chests per hour = recorded chests inside sessions ÷ session time, needing 30 minutes; never per-minute × 60 (tested).
- Active play is unknown (a dash) without a recognised match, and "at least" when chests fell outside recognised matches.
- The best hour lies inside counting (runs up to 2 minutes apart join, an app restart); a correction made after counting stopped stays out.
- The calendar-week average is the calendar-day average × 7 over completed weeks, so a history that began mid-week is not a short week.

| Check | Result |
|---|---:|
| `test_progression` | 32/32 |
| `research/progression_mutations.py` | 28/28 caught |
| `test_match_history` (read-only allowlist now includes `progression.py`) | 98/98 |
| Synthetic year (82 MB, 151,840 events): snapshot / all five periods / best hour | 1.44 s / 0.84 s / 0.06 s |

Broad regressions are deferred to the end of phase B (M2 + M3), per the batched workflow adopted 2026-11-12.

## M3 — Personal Bests engine (records)

New pure module `records.py`: `personal_bests()` derives every best from history on each call (nothing stored, so Not a match, Restore
and Undo change them at the next refresh), and `load()` reads history once for the whole Analytics page (match summary, snapshot, the
five periods and the bests). `match_analytics.summarize` now also returns every match (`all_matches`, newest first) with its active time;
`recent` is the first 25 of it, as before.

| Best | Eligible |
|---|---|
| Most chests in a match | Complete, not Not a match; count includes your corrections for it (D3), shown apart |
| Best chests per minute | Complete, at least 5 minutes of active play; same counts as the per-minute rate (checkbox respected) |
| Best hour | 60 real minutes all counted, at least one chest |
| Best day, best week | Any day or calendar week with recorded chests |
| Most chests in a session, longest session | Any session |
| Best session pace | Sessions of an hour or more |
| Most broken chests in a match | Complete or Partial, as you reported them |

Ties go to the first time a best was reached. Each best carries when, how long, CERTAIN where it applies, the manual part, and whether
it was cut short (interrupted run or lost history rows).

### Phase B check (M2 + M3 together)

| Check | Result |
|---|---:|
| `test_records`, `test_progression` | 14/14, 32/32 |
| `test_match_analytics`, `test_corrections`, `test_match_ui`, `test_match_history` | 61/61, 82/82, 50/50, 98/98 |
| Mutations: Personal Bests, progression, analytics, corrections | 8/8, 28/28, 51/51, 58/58 |

Two mutation candidates were dropped as equivalent: excluding a Not a match match again in `records.py` (match_analytics already credits
it with no chests), and a re-ranking that could not change the winner. Three analytics/correction mutations were re-anchored to the new
loop over every match.
