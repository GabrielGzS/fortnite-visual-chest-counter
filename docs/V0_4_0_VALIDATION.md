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

## Phase C — Analytics page and UX (M4, M5, M6, M7, M10)

Committed as M7 (the Game status, `fc87e45`) and the Analytics page (M4, M5, M6, M10, `ba4a167`).

### What the page is now

Four tabs, as on the Dashboard (D9): **Performance** (opens first), **Days & weeks**, **Personal Bests**, **History**. One background read
(`records.load`) feeds every tab, so the calculations stay out of the window code.

| Tab | Contents |
|---|---|
| Performance | Period choice (Today, This week, Last 7 days, Last 30 days, All time; All time first). Headline: **chests per hour** of session time beside **chests per minute of play**. Chests, session time, active play, matches; a build-up chart with the counted stretches shaded; details (time counting, between matches, match time seen, CERTAIN, per complete match, including partial); **Where your chests came from** (M10): detected, broken, missed, other +1s and your −1s, each with its share and per hour of counting |
| Days & weeks | Today, yesterday, this week, last 7 and 30 days with how many days were counted; a 30-day chart (bars = chests, a short line = counted with none, a ring = not counted); per day counted, per day with chests, per calendar day (with the days not counted), per week; best day and week; a 12-week chart |
| Personal Bests | One card per best: value, when, how long, CERTAIN, the manual part, Complete/Partial, "at least" when cut short; what it needs when there is none yet |
| History | Matches (up to 100, newest first, Not a match / Restore as before) or Sessions; the table fills the tab |

Charts are drawn with `QPainter` (`gui/charts.py`): QtCharts is not in the package and nothing was added to it.

### UX fixes

| ID | Fix | Checked by |
|---|---|---|
| UX-04 | History does not scroll as a page; its table is the only scroller. The other tabs scroll as one page with no scroller inside | `test_history_has_one_scroller` |
| UX-05 | Game status at 13 pt on its own line in a calm colour; partial, unconfirmed or no picture as a small tinted note | `test_partial_is_a_small_note_not_a_large_warning`, Dashboard views |
| UX-06 | The list jumps to the top only when its newest match (run id + match number) is new; refreshes, corrections and the checkbox keep the position | `test_a_new_match_comes_into_view_and_nothing_else_moves_the_list` |
| UX-07 | When a match ends while Analytics is open, history is read again 5 seconds later (after the detector's last chests); nothing happens while another page is open | `test_a_match_ending_refreshes_the_page_only_while_it_is_open` |
| UX-08 | Every tab fits 920 × 640 with no sideways scroll and no text cut off: tighter table padding, minutes in the list ("18m", "20m seen"), "10 (+2)" with the details on hover, "Per min" | `test_every_tab_fits_the_smallest_window_without_scrolling_sideways` (real fonts) |

Screenshots of every tab at 1120 × 800 and 920 × 640, and of the Game view with a partial match, were rendered with real fonts and
reviewed. Two problems found that way were fixed: the "&" of "Days & weeks" shown as a shortcut underline, and the chest-source row too
wide at 920.

### Meanings that changed on purpose (tests updated)

- **Active play** covers Complete and Partial matches (v0.3.0's tile showed Complete only; that time stays in the per-minute figure's
  line), shown as "at least" when some play was not recognised.
- **Chests / CERTAIN** on Performance are recorded chests (D3, D4): the worked example's chest seen after its match ended is someone
  else's, so 8 and 5 instead of 9 and 6.
- The match list shows durations in minutes.

### D12 — decided: not built in v0.4.0

The Overview "Today · last hour" line was to be built only if the same code as Analytics could keep it current cheaply. It cannot: a full
read of a heavy year takes about two seconds, so keeping it current chest by chest would need a second, incremental calculation that could
disagree with Analytics (spectated chests, corrections), and refreshing it only when a match ends would show stale numbers on a live
screen. Performance > Today shows the same figures. Deferred, as the decision allowed.

### Tests

| Check | Result |
|---|---:|
| `test_analytics_ui` (new; includes the real-font fit check) | 12/12 |
| `test_match_analytics`, `test_dashboard_views`, `test_match_ui`, `test_live_match`, `test_corrections` | 61/61, 27/27, 50/50, 88/88, 82/82 |
| `test_app`, `test_update_gui` | 30/30, 70/70 |
| Mutations: analytics, live match, corrections, Dashboard, match UI | 51/51, 59/59, 58/58, 25/25, 40/40 |

Six mutation anchors moved to the new page code with the same intent. The analytics and corrections runners now also swap the module the
page reads through (`records`, `progression`); without that, one mutation could not reach the page.

## M8 — Update notice, Updates card and release notes (UX-01 to UX-03)

Presentation only. `git diff v0.3.0 -- src/fortnite_chest_counter/update/` is empty: download, signature checks, staging, installation and
rollback are byte for byte what v0.3.0 shipped, and a test keeps it that way while v0.4.0 is developed.

**Why no notice appeared on PC B (UX-01).** By design in v0.2.3 and v0.3.0, an automatic check never opens anything: a found update shows
only the small sidebar link, and a check that fails says nothing and logs nothing. Whether PC B's check ran and failed, or succeeded and
showed only the link, cannot be told afterwards. v0.3.0 behaves the same, so the v0.3.0 to v0.4.0 update will again be found through the
sidebar link or Settings; these changes help from v0.4.0's own next update.

| ID | Change |
|---|---|
| UX-01 | Every automatic check writes one quiet Console line (up to date, available, did not finish, or did not verify). A verified update shows a one-line notice on the Dashboard with **What's new** and **Later** (put away for that version, never a pop-up). Help & diagnostics has an **Updates** card: your version, the last check and its result, Check for updates, Open the update, Update settings |
| UX-02 | Release notes are Markdown (headings, lists, bold, tables) with raw HTML switched off, nothing fetched (an image in the notes stays empty), and a link followed only if it is one of this project's GitHub pages (`gui/release_notes.link_allowed`) |
| UX-03 | The window opens on the highlights: the notes up to `<!-- highlights end -->` (invisible on GitHub), else up to the second section heading, at most 40 lines. **Show all the notes** shows the rest |

For the v0.4.0 release body: put a short, plain-text-friendly summary first and `<!-- highlights end -->` after it, because v0.3.0's window
will show the body as plain text, and v0.4.0's will show what comes before the marker.

| Check | Result |
|---|---:|
| `test_release_notes` (new) | 6/6 |
| `test_update_notice` (new: logging, notice, Later, Updates card, highlights, raw HTML as text, nothing fetched, links, update path unchanged) | 8/8 |
| `test_update_gui` (the notes check now expects safe Markdown) | 70/70 |
| `test_app`, `test_dashboard_views` | 30/30, 27/27 |

The notice, the Updates card and the update window with v0.3.0's real notes were rendered with real fonts at 920 × 640 and reviewed.

## M9 — Updater reliability tests: blocked, not run

**Status: not run, and documented as not run (never as passed).** Two approvals are missing, and the plan says to stop this workstream
rather than guess:

1. **An isolated machine (D11).** Destructive update tests may run only in an isolated Windows VM or disposable environment with synthetic
   data, never on the main PC or the second PC's real installation. This PC runs Windows 11 Home (no Windows Sandbox or Hyper-V), and no
   Windows VM exists yet.
2. **A test package.** The real-package scenarios need a built v0.4.0 package, and building one is not yet authorized ("no release build").

**What still holds.** The update path is byte for byte v0.3.0's (checked above). v0.3.0's results for it therefore stand: the automated
failure tests on small synthetic installations (`test_update.py`, `test_update_prepare.py`, `test_update_install.py`,
`test_update_release.py`), and one real update, v0.2.3 to v0.3.0, that succeeded on the second PC as a normal user. They were not rerun
here: the code did not change, and a rerun of failure simulations on the main PC is what D11 rules out.

**Ready to run once a VM and a test build are approved.** `tests/update_e2e.py` already drives five real-package scenarios, one per run,
in the order they must pass; the remaining rows are covered by unit tests today and would need new e2e scenarios.

| UT | Scenario | How |
|---|---|---|
| 1 | Healthy update | `update_e2e.py run healthy` |
| 5 | New version fails to start: rollback | `run failed-start` |
| 6 | Helper killed after the swap: launcher recovery | `run crash-after-swap` |
| 7 | Saved data the old version cannot read | `run damaged-data` |
| 8 | An updated copy updates again | `run chained` |
| 2, 3, 4 | Interrupted and resumed download; damaged download or manifest; untrusted or bad signature | Unit tests today; new e2e scenarios if wanted |
| 9 | Preparing while counting | By hand in the VM, comparing event identities on a reference clip |
| 10 | Smart App Control and Defender on | Each e2e report records the Smart App Control state and any file Windows blocked |

Steps (docs/UPDATER.md, "Checking with a real package"): build a test package; `update_e2e.py make-kit` with a throwaway key, outside
the repository; copy the kit into the VM; run one scenario at a time with the kit's own Python; keep each `report.txt`. Never the
production keys; security software stays on.
