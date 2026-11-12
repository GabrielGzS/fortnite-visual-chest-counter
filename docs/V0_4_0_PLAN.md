# v0.4.0 — Analytics Expansion & Reliability (plan)

Planning document, 2026-11-12. Base: the v0.3.0 release (tag `v0.3.0`, commit `9eca405`), branch `dev/v0.4.0`. Future work after this
release: [V0_5_0_PLAN.md](V0_5_0_PLAN.md).

**Status: approved 2026-11-12, implementation authorized from M1.** Decisions are settled in section 9. Milestones run one at a time:
implement, test what changed, commit locally, record results in `docs/V0_4_0_VALIDATION.md`, then continue while acceptance criteria pass,
stopping on a genuine blocker, data-loss risk, security regression or contradiction. Nothing is pushed, tagged, signed, built for release
or published without explicit approval.

**Naming (2026-11-12):** the tab planned as "Records" is called **Personal Bests** in the app, so it cannot be mistaken for History.
Internal identifiers may keep `records`.

## 1. Goals

1. **Measure real progress.** Chests per real-life hour, per day and per week, next to the existing chests per minute of play, plus
   personal records. Three questions, three numbers:

   | | Measures | Question it answers |
   |---|---|---|
   | per active minute | Efficiency | How fast do I loot while playing? |
   | per hour | Productivity | How fast do I progress during a gaming session, breaks and queues included? |
   | per day, per week | Consistency, sustainability | How much do I really get done, days off included? |

2. **Fix the UX problems found while using v0.3.0**, and make the updater easier to notice and read.
3. **Test the updater's failure paths** that v0.3.0 shipped without proving.

### Not in v0.4.0

- New chest-detection work. The detector stays frozen unless a critical regression appears. v0.3.0's open detection issues (lobby
  menu with the TREASURE tab, 720p small-HUD start text, stacked pop-ups at 720p, switching away from the game mid-match) stay
  documented and deferred.
- No change to CERTAIN/APPROX meaning, the overlay files, or profiles.
- No change to the update install path: download, staging, archive rules, signature checks, install, helper and rollback code stay as
  shipped. Only the update window and notifications change (section 7).
- Treasure recognition and predictions: v0.5.0.

## 2. Architecture audit: what v0.3.0 already records

### 2.1 Where the data lives

| Data | File | Timestamps | Written when |
|---|---|---|---|
| Totals per profile (CERTAIN, APPROX, types, last chest) | `state/chest_state.json`, `state/profiles/<id>.json` | `session_started_at` (start of this counter's life), `updated_at` | Every chest, correction, reset, edit |
| Profiles | `state/profiles.json` | `created_at` | On change |
| Runs: `run_start`, `heartbeat`, `run_end` | `state/history/<id>/matches.jsonl` | `at` (wall clock, local, UTC offset, ms) on every row; `t` (source seconds) on heartbeats and `run_end`; `elapsed_seconds` (monotonic wall) on a clean `run_end` | Start, every `heartbeat_seconds` (default 60) of source time, stop |
| Match rows: `match_opened`, `transition`, `match_closed`, `correction` (Not a match) | same | `at`, `t`, `opened_t`, `played_from_t`, `ended_t`, `closed_t`; seconds observed / active / spectating / uncertain / complete duration | As matches happen |
| Counter changes during a run (Reset, Edit counts, corrections) | same | `at` | As they happen |
| Gaps (history lost rows, or totals changed outside history) | same | `at` | When detected |
| Counted chests | `state/history/<id>/chests.jsonl` | `at` (set when the chest is applied, kept if the write is retried), `t` | Every counted chest, after the totals are saved |
| Manual +1/−1, Undo, later reason | same | `at` when clicked | Every correction, counting or not |
| Session log (diagnostics) | `logs/session_*.jsonl` | `logged_at` | Every event, if logging is on |

A chest's identity is `run_id + counter_epoch + event_id`. Matches are `run_id + match_number`. Both files are append-only, one JSON
row per line, and never rewritten. Analytics already recalculates everything from rows on every refresh (`match_analytics.load`).

### 2.2 The clocks, and what each is good for

| Clock | Where | Good for | Not good for |
|---|---|---|---|
| Source time `t` | chest, heartbeat, match rows | Order and gaps inside one run; match durations | Calendar dates. For a livestream URL it is stream time and drifts from the wall clock by the buffer backlog |
| Wall clock `at` | every row | Calendar days, weeks, rolling hours, session spans | Measuring play inside a match (use `t`) |
| Run elapsed `elapsed_seconds` | clean `run_end` | Time counting, immune to a clock change | Interrupted runs (absent) |
| Calendar time | derived from `at` | "Days with no counting" | Anything before the first recorded row |

For the OBS camera, capture device, Screen and projector inputs, `t` is arrival time since the source opened, so `t` and `at` agree.
Checked on real data: the first chest's `at` was 0.8 s after `run_start.at + t`, the detector's normal finishing delay.

### 2.3 A real session

The maintainer's own v0.3.0 install has one recorded run, read without changing anything:

| | |
|---|---|
| Source, length | Screen input, 72 minutes (03:38–04:50, UTC+1) |
| Chests | 214 detected, plus 46 manual +1s made in the Game view: 39 broken chest, 7 missed |
| Matches | 7 opened, 6 closed, all Complete |
| `run_end` | **Missing.** The run will be closed as interrupted the next time counting starts. Until then, only its heartbeats tell how long it lasted |
| Size | 155 KB for both files, about 130 KB per hour of counting |

Two consequences:

- **Manual chests were about 18% of that session's adjusted total** (46 of 260). Whether per-hour and per-day numbers include your
  +1s changes the answer by that much (decision D3).
- **Runs without a `run_end` are normal**, not an edge case. Every time-based metric must handle them.

### 2.4 Findings

| # | Finding | Effect on v0.4.0 |
|---|---|---|
| F1 | **History is only written when match tracking is on** (`counter._open_history` requires `[match] mode = "on"`). With tracking off, no run, heartbeat or chest row exists | No per-hour or per-day statistics for anyone who turns tracking off. Proposed fix in M1 (D7) |
| F2 | **Nothing before v0.3.0 has timestamps.** Counter files hold totals only. Session logs hold per-chest `logged_at`, but they stay in each old version's folder, include developer and test runs, and are not tied to a profile before v0.2.2 | Analytics starts at the first recorded day; lifetime totals stay on Overview (D8) |
| F3 | Time counting = runs. Clean runs give `run_start.at` and `elapsed_seconds`. An interrupted run ends at its last heartbeat (up to `heartbeat_seconds` short: 60 s by default, up to 10 min if set to 600) | Report interrupted runs as "at least" |
| F4 | **Pitfall:** the `run_end` row written when recovering an interrupted run has `at` = the moment of recovery (the next counting start, possibly days later). Its real end is `last_seen_at` | Using the recovery row's `at` would invent hours or days of counting. Tested explicitly in M1 |
| F5 | Recovery only runs when counting next starts, so Analytics can meet a run with no `run_end` that is not running | Treat it as ending at its last heartbeat; the currently running run counts up to now |
| F6 | Heartbeats come from the match tracker. If the tracker stops after an error, or tracking is off (with F1 fixed), there are none | M1 adds a heartbeat from the live loop when the tracker is not running |
| F7 | During a video stall the live loop gets no frames, so no heartbeats | Harmless: only makes an interrupted run's length a lower bound |
| F8 | Every `at` carries its UTC offset | Elapsed time is exact across daylight-saving changes |
| F9 | Reset, Edit counts and Set starting count are counter changes, not chests. Outside a run they leave no history row at all | Progress = chest rows + correction rows only. A starting count of 150 can never appear as 150 chests on one day |
| F10 | Corrections carry `at`, `delta`, reason, `match_number` (Game view) or none (Overview), and Undo / reason rows. Overview corrections made while not counting have `run_id = null` | Usable for per-day numbers. A correction is dated when clicked, which can be minutes after the chest |
| F11 | `match_history.attribute` marks chests seen after the player was out (spectating a teammate) | They are in the Dashboard total but are not the player's chests (D4) |
| F12 | Analyse a recording never writes history (saving is off). The developer `simulate` command does, with `source_type = "simulate"`, and its wall time is not play time | Leave `simulate` runs out of every time-based metric |
| F13 | Active play = alive on the bus or the map, English-recognised matches only (`match_state`) | Utilization (active ÷ counting) is only meaningful when matches were recognised. If chests were counted outside any match, show it as unknown, never as a low number. Note: the bus counts as play, unlike some definitions of downtime |
| F14 | The updater backs up `state/*.json`, `state/profiles/*.json` and `config.toml`, and treats **every** `state/*.json` as a counter file (`install_helper._user_data_files`, `_readable_by_this_version`). `state/history/` is not backed up | No new file may go in `state/*.json`. History must never be migrated or rewritten in place |
| F15 | v0.3.0's reader skips rows with a newer `schema` (reported as "rows from a newer version"), ignores unknown kinds in `matches.jsonl`, but counts unknown kinds in `chests.jsonl` as **damaged rows** | If v0.4.0 needs new row kinds, they go in `matches.jsonl` or a new file, never in `chests.jsonl` |
| F16 | Analytics reads everything except heartbeats on every refresh. At about 130 KB per hour, two hours a day for a year is about 95 MB | Measure in M1 with a synthetic year; add a rebuildable cache only if the measurement needs one |
| F17 | Profiles are separate histories. Many profiles count someone else's stream, so their "days with no counting" are mostly days nobody watched | Every day and week figure shows how many days were counted |
| F18 | Analytics refreshes only when the page opens, on Refresh, and when counting stops. Refilling the table keeps both scroll positions | Causes UX-06 and UX-07 (section 6) |
| F19 | The Analytics page is a `QScrollArea` (`page_layout`) holding a `QTableWidget` that scrolls on its own | Cause of UX-04 |
| F20 | `#gameStatus` is 15 pt bold, word-wrapped, and the whole sentence, including "partial: joined after the start", is drawn in the APPROX yellow | Cause of UX-05 |
| F21 | An automatic update check never opens anything (`take_open_request` is set only by a manual check); its only sign is the sidebar link. A failed automatic check sets no message and writes no log line | Cause of UX-01; whether PC B's check ran and failed, or succeeded and showed only the link, cannot be told afterwards |
| F22 | Release notes are the GitHub body shown in a `QPlainTextEdit` | Cause of UX-02 and UX-03. **v0.3.0's own code will show v0.4.0's notes**, so they must read well as plain text |
| F23 | QtCharts is not in the packaged runtime | Charts are drawn with `QPainter`: no new dependency, no package growth |

### 2.5 What each metric can rest on

| Metric | Needs | Available | Verdict |
|---|---|---|---|
| Chests per active minute, per complete match, per match | Matches, chests | Since v0.3.0 | Supported (existing) |
| Time counting | Runs, heartbeats | Since v0.3.0, tracking on | Supported; "at least" for interrupted runs |
| Session time | Runs + break rule (D1, D2) | Derived | Supported |
| Chests per hour | Chest `at`, sessions | Since v0.3.0 | Supported |
| Time between matches, share of time playing | Active play, time counting | Recognised English matches only | Supported with an "unknown" state (F13) |
| Current and best rolling hour | Chest `at`, counting coverage | Since v0.3.0 | Supported |
| Today, yesterday, per day, best day | Chest and correction `at` | Since v0.3.0 | Supported |
| This week, per week, best week, last 7 / 30 days | Same | Since v0.3.0 | Supported, with counted-day coverage |
| Average per calendar day vs per counted day | Day coverage | Since the first recorded day | Supported |
| Records | All of the above | Since v0.3.0 | Supported, derived on the fly |
| Broken / missed / false-positive / unknown chests | Correction reasons | Since v0.3.0 | Supported, as reports by the user |
| Anything before v0.3.0, or with tracking off | — | Not recorded | Not possible; never reconstructed |

**Nothing needs a new file format.** M1's changes write the same row kinds v0.3.0 writes, so a rollback to v0.3.0 reads them normally.

## 3. Definitions

These are the definitions the code and the interface will use. The open choices are in section 9.

| Term (in the app) | Definition |
|---|---|
| **Time counting** | Wall-clock time inside runs: from `run_start.at` to the clean end (`elapsed_seconds`), or to the last heartbeat for an interrupted run (marked "at least"). `simulate` runs excluded |
| **Session** | Runs joined while the gap between them is shorter than the break limit (D2, proposed 30 minutes). A session spans from its first start to its last end |
| **Session time** | The session's span. Short pauses when counting was stopped are inside it: they are breaks, which is what "real life" means here |
| **Active play** | v0.3.0's definition, unchanged: alive on the bus or the map, in recognised matches |
| **Between matches** | Time counting minus active play, shown only when the matches in that period were recognised (F13). In the docs: downtime |
| **Recorded chests** | Detected chests plus your standing corrections (D3), dated by their own `at`. Spectated chests per D4. Reset, Edit counts and starting counts never count |
| **Chests per hour** | Recorded chests in sessions ÷ session hours (D1) |
| **Rolling hour** | Recorded chests in any 60-minute window that lies entirely inside time counting. Never a shorter period scaled up |
| **Day** | Local calendar day (D6), using the PC's time zone rules at each moment, so 23- and 25-hour days are handled |
| **Week** | Calendar week starting Monday (D5). **Last 7 days** is separate: today and the 6 days before |
| **Monitored day** | A day with any time counting: an actual observation, even if it found no chests (a **known zero**) |
| **Active day** | A day with recorded chests |
| **Not counted** | A day with no counting and no rows: unobserved, never a zero |
| **Average per monitored day** | Recorded chests on monitored days ÷ monitored days |
| **Average per active day** | Recorded chests ÷ active days |
| **Average per calendar day** | Recorded chests ÷ every day in the period, from the first recorded day, always shown with how many of those days were not counted. The honest number for planning, never presented as continuous observation |

The same three averages exist for weeks. Averages use completed days and weeks; today and this week are shown on their own. A session
that crosses midnight adds its chests to each day by their own times, and is listed once, under the day it started.

**A session's gaps are not observations.** Joining runs across a gap shorter than 30 minutes says only that real time passed, not what
happened in it. Session time, time counting, unobserved gaps and active play are always kept and shown apart.

## 4. Personal Bests (records)

Shown on the **Personal Bests** tab. Derived from history every time, never stored as a number that could drift. Excluding or restoring a match, or undoing a correction,
changes the records at the next refresh.

| Record | Rule | Eligible |
|---|---|---|
| Most chests in a match | APPROX of one match, corrections for that match per D3 | Complete matches (D10) |
| Best chests per minute in a match | APPROX ÷ active minutes | Complete, at least 5 minutes of active play (D10) |
| Best hour | Most recorded chests in a rolling hour | The whole 60 minutes counted |
| Best session | Most recorded chests in a session; also its rate | Rate only for sessions of 60 minutes or more |
| Best day | Most recorded chests on a calendar day | Any counted day |
| Best week | Most recorded chests in a calendar week | Any week with a counted day |
| Longest session | Session time | Any session |
| Most broken chests in a match | Your broken-chest +1s for one match | Complete or Partial; labelled "as you reported" |

Every record shows its value, CERTAIN beside APPROX where it applies, the date and time, the match or session, its duration, how many
of its chests you added by hand, and whether any part was cut short (interrupted run, missing history rows).

## 5. Analytics interface

A tab row like the Dashboard's (same `QButtonGroup` + `QStackedWidget` pattern), so each tab answers one question instead of one long
page of tiles (D9, approved):

| Tab | Answers | Contents |
|---|---|---|
| **Performance** (opens first) | How fast am I progressing? | Period choice (Today, This week, Last 7 days, Last 30 days, All). Two distinct headline numbers: **chests per hour** (real life) and **chests per minute of play**. Session time, time counting, unobserved gaps, active play, between matches. Chest build-up over the selected period as a line chart |
| **Days & weeks** | How consistent am I? | Today, yesterday, this week, last 7 / 30 days; chests per day as bars (not-counted days and known zeros drawn differently from each other and from bars), weeks as bars; averages per monitored, active and calendar day and week; best day and week |
| **Personal Bests** | What are my best results? | Section 4, each with its evidence |
| **History** | What happened? | Recent matches (today's table, with Not a match / Restore), and a sessions list |

The v0.3.0 tiles move to where they belong: match counts and per-match figures into Performance and History, broken chests into the
chest-source section (M10). Values first; the technical detail goes into tooltips. The maintainer reviews the result afterwards (no
separate mock-up round, per the implementation authorization).

**D12:** a small "Today · last hour" line on Overview, computed by the same code as Analytics so the two never disagree (section 9).

## 6. UX issues

Numbering follows the maintainer's list.

| ID | Issue | Cause (from the code) | Fix | Milestone |
|---|---|---|---|---|
| UX-01 | No update notice on startup, and update controls are hidden in Settings | F21: by design only a small sidebar link; automatic check failures are silent | Log every automatic check result as one quiet Console line; a dismissible notice on the Dashboard when a verified update is found ("Version vX is available · What's new · Later"), remembered per version; an **Updates** card in Help & diagnostics (version, last check and result, Check now, open the update window). Never a pop-up dialog, never during counting | M8 |
| UX-02 | Release notes show raw Markdown | F22 | Render a safe subset: headings, lists, bold, tables. Qt's own Markdown reader with raw HTML disabled, no remote images, and links opened only for the project's GitHub pages. Hostile-input tests. Plain text stays as the fallback | M8 |
| UX-03 | Release notes are too long | F22 | Show a short summary first: the release body up to a marker invisible on GitHub (an HTML comment), else its first section, capped; **View on GitHub** for the rest | M8 |
| UX-04 | Scrolling Recent Matches also scrolls the Analytics page | F19: a scrolling table inside a scrolling page; the wheel passes to the page at the table's edge, and touchpad momentum can move both | In the History tab the table fills the space and the tab itself does not scroll, so there is one scroller. Check mouse wheel, precision touchpad and scrollbar dragging | M4 |
| UX-05 | Partial status is huge yellow text in the Game view | F20 | Status in normal text colour at a smaller fixed size, one line; the doubt ("Partial: joined after the start") as a small secondary line or pill in a muted colour, with the explanation as a tooltip. Partial is a normal outcome, not an error. Check every status at 920 × 640 | M7 |
| UX-06 | When a new match is added, Recent Matches keeps its old scroll position, so the new match is hidden and tracking looks broken | F18 | Remember the newest match's identity (`run_id`, `match_number`). Scroll to the top only when a genuinely new match appears. A refresh, a correction, the "Count my +1s" checkbox or an updated existing match keep the position | M4 |
| UX-07 | A match that ends while Analytics is open does not appear until Refresh | F18 | Refresh Analytics when the worker reports a closed match and the page is visible (debounced), relying on UX-06 for the scroll | M4 |
| UX-08 | Analytics table scrolls sideways at the minimum window size (v0.3.0 known issue) | Long labels | Shorter cells or wrapping in the History tab; verified at 920 × 640 | M4 |
| UX-09 | Maintainer's testing notes ("bugs here and there") | — | **To be added by the maintainer.** Each one gets a cause and a fix in M7 or the milestone it belongs to | M7 |

Known and left alone unless cheap: a correction made during a video stall applies on the next frame (v0.3.0, Low).

## 7. Updater

**Evidence so far:** one real update, v0.2.3 to v0.3.0, succeeded on the second PC as a normal user would do it: found through
Settings, downloaded, installed, restarted, profile and totals kept. That supports keeping the architecture. It proves the normal path
once; it proves nothing about failures.

**Rules for v0.4.0:**

- No change to download, staging, archive, authenticity, trust, install or helper code. UX-01 to UX-03 change only
  `gui/update_manager.py` presentation and the update window. If a test finds a defect in the install path, stop and report.
- The v0.3.0 to v0.4.0 update will be performed **and displayed** by v0.3.0's code. So the v0.4.0 GitHub release body must open with
  a short summary that reads well as plain text, and the release notes should tell v0.3.0 users to look for the sidebar link or use
  Settings > Check for updates.
- UX-01 to UX-03 take effect from v0.4.0's own next update onwards.

### Reliability tests (M9)

| # | Scenario | Proves |
|---|---|---|
| UT-1 | Healthy update of a real package | Download, staging, swap, health report, commit; counts and OBS text kept |
| UT-2 | Download interrupted, then resumed | `.part` resume; checksum verified |
| UT-3 | Damaged download / damaged manifest | Refused; nothing staged |
| UT-4 | Signature by an untrusted key, or a bad signature | Refused before anything is unpacked |
| UT-5 | New version fails to start | Automatic rollback; old version reopens; counts kept |
| UT-6 | Helper killed after the swap | Launcher recovery restores the old version |
| UT-7 | Saved data the old version cannot read | Restored from backup; the newer file kept aside and reported |
| UT-8 | Chained update (an updated copy updates again) | Its own helper works |
| UT-9 | Preparing an update while counting | Counting keeps its rate; no dropped chests (compare event identities on a reference clip) |
| UT-10 | Smart App Control and Defender on | Helper and new runtime are not blocked; nothing is turned off |

UT-1 and UT-5 to UT-8 are `tests/update_e2e.py`'s existing scenarios. UT-2 to UT-4 have unit coverage on synthetic installations and
need one real-package run each.

Constraints: a throwaway test key, only inside the test kit, never the production keys; synthetic user data; disposable installations;
one scenario per run; security software stays on. A real v0.3.0 install trusts only the production keys, so these tests exercise
**v0.4.0's own updater** (the code that will install v0.4.1 or v0.5.0); the v0.3.0 to v0.4.0 path is the release itself.

**Blocked on an environment decision (D11).** The only real-package attempt on the main PC (v0.2.3 M3) ended in an unexplained
blue screen (0x101), and staging must not be repeated there without isolation. This PC runs Windows 11 Home, so Windows Sandbox and
Hyper-V are not available; VirtualBox or VMware drivers are installed, so a Windows virtual machine may be possible.

## 8. Milestones

Order: data and timing first, then metrics and records, then interface and UX, then the updater. Each milestone: implement, test what
changed, commit locally as `v0.4.0 (dev): Mn ...`, add a section to `docs/V0_4_0_VALIDATION.md`, stop for review.

| # | Milestone | Priority | Depends on |
|---|---|---|---|
| M0 | This plan | — | — |
| M1 | Timing foundation | P0 | M0 approved, D1, D2, D7 |
| M2 | Progress metrics | P0 | M1, D3–D6 |
| M3 | Personal Bests engine (records) | P0 | M2, D10 |
| M4 | Analytics tabs and History table (UX-04, 06, 07, 08) | P1 | M0 (shell); data from M2/M3 shown later |
| M5 | Performance and Days & weeks tabs, charts | P1 | M2, M4 |
| M6 | Personal Bests tab | P1 | M3, M4 |
| M7 | Game view status and the maintainer's UX notes (UX-05, UX-09) | P1 | — (can move earlier) |
| M8 | Updater window and notices (UX-01, 02, 03) | P1 | — |
| M9 | Updater reliability tests | P1 | M8, D11 |
| M10 | Chest-source statistics | P2 | M2 |
| M11 | Release qualification | — | All |

### M1 — Timing foundation

- **Objective:** a pure, tested model of time counting, sessions and day/week coverage, and history that is kept whenever saving is on.
- **Changes:**
  - Open the history writer whenever saving is on, independent of match tracking (D7). Match rows only with tracking on. Settings
    wording updated to match.
  - A heartbeat from the live loop when the tracker is not running or has stopped (F6), same row kind and interval.
  - New pure module (for example `timeline.py`): runs to intervals (F3–F5, F12), sessions (D1, D2), day and week buckets (D5, D6),
    counted-day coverage. One function for the time zone, so tests can inject a daylight-saving zone.
  - A synthetic history generator for tests: several weeks, both daylight-saving changes, sessions across midnight, interrupted and
    recovered runs, a livestream run with backlog, a `simulate` run, corrections while not counting, spectated chests, the waiting
    island, Not a match.
- **Code:** `counter.py` (`_open_history`, live loop), `match_history.py` (only if a helper is needed; no format change), new module,
  `settings.py` / Settings page text, tests.
- **Data:** no new row kinds, no schema change, no rewrite. Test that v0.3.0's reader (from the tag) reads M1-written files with no
  damaged or newer rows.
- **Acceptance:** hand-computed expectations match exactly for every fixture; the recovery row's `at` is never used as an end (F4);
  23- and 25-hour days correct; counting results unchanged (chest events identical on the reference clips); with tracking off, a run
  still produces run, heartbeat and chest rows.
- **Performance:** read time for a synthetic year (about 95 MB) measured on the main PC; target under 1 s for an Analytics refresh. If
  missed, propose (not build) a cache that is rebuildable, deletable and outside `state/*.json`.
- **Risks:** turning on history for tracking-off users is a behaviour change (D7); clock changes (an interval that disagrees with
  `elapsed_seconds` by more than 2 minutes trusts `elapsed_seconds`, flagged).

### M2 — Progress metrics

- **Objective:** every number in section 3, for a chosen period, from history only.
- **Contents:** chests per hour (session and counting), time counting, active play, between matches (with the unknown state),
  today, yesterday, this week, last 7 and 30 days, per day and per week, averages per calendar day and per counted day, current and
  best rolling hour, counted-day coverage, detected vs recorded (D3), spectated chests (D4).
- **Code:** a pure module beside `match_analytics.py`, sharing one history read with it.
- **Acceptance:** fixture expectations exact; no value is invented (unknown is `None`, shown as a dash); a 20-minute session never
  yields a "best hour"; not-counted days never average as zero in "per counted day" and always do in "per calendar day".
- **Tests:** unit tests plus a mutation check (deliberately break each rule and confirm a test fails), the project's usual practice.

### M3 — Personal Bests engine (records)

- **Objective:** section 4, derived on the fly, with evidence.
- **Acceptance:** Not a match, Restore and Undo change records at the next refresh; ineligible matches and sessions never hold a
  record; each record names its source and manual share. Unit and mutation tests.

### M4 — Analytics tabs and History table

- **Objective:** the tab shell, and the History tab with today's table and a sessions list; UX-04, UX-06, UX-07, UX-08.
- **Acceptance:** one scroller at a time with wheel, touchpad and scrollbar; a new match scrolls to the top and nothing else moves
  the scroll; a match closing while the page is open appears; everything fits 920 × 640 with no sideways scroll (extend the existing
  fit test); screenshots of the real rendering reviewed before handover.

### M5 — Performance and Days & weeks tabs

- **Objective:** section 5, with charts drawn by `QPainter` (cumulative line, day and week bars, not-counted markers).
- **Acceptance:** plain numbers first, APPROX before CERTAIN; light and dark contrast checked; fits 920 × 640;
  Analytics stays responsive (reading off the window's thread, as today). D12 if approved.

### M6 — Personal Bests tab

- **Acceptance:** every record shows the evidence in section 4; empty states say what is needed ("needs a 60-minute session").

### M7 — Game view and UX notes

- **Objective:** UX-05 and the maintainer's list (UX-09).
- **Acceptance:** every match status, short and long, on one line at 920 × 640; Partial readable but not alarming; each listed issue
  fixed or explicitly deferred with a reason.

### M8 — Updater window and notices

- **Objective:** UX-01 to UX-03, presentation only.
- **Acceptance:** an automatic check's result is visible in the Console, success or failure; a found update shows a dismissible notice
  and an Updates card in Help; Markdown renders headings, lists, bold and tables; raw HTML, scripts, remote images and non-GitHub links
  are inert (tests with hostile release bodies); the summary is short and the full notes are one click away; install path files
  unchanged (checked by hash against v0.3.0).

### M9 — Updater reliability tests

- **Objective:** UT-1 to UT-10 in the environment chosen in D11.
- **Acceptance:** each scenario's report kept; any failure stops the run and is reported before anything else changes.

### M10 — Chest-source statistics

- **Objective:** reported broken chests, missed chests, false positives and unknown corrections: totals, per match, per hour of
  counting, and their share of the recorded total, per period.
- **Rules:** user reports are labelled as such; only `missed` and `false_positive` are claims about the detector; no correction factor.

### M11 — Release qualification

- README, `packaging/README.html`, an Analytics guide (or `MATCH_TRACKING.md` extended), ROADMAP updated (its v0.4.0 section is now
  this plan), release notes with a plain-text summary first (section 7).
- RC build, a test matrix built from what changed since v0.3.0 (unchanged systems reuse earlier results), detector files byte-identical
  to v0.3.0, packaged smoke test, Defender scan, hands-on acceptance by the maintainer.
- Signing, push, tag and publish each need explicit approval.

## 9. Decisions

**Settled 2026-11-12.** D1–D7, D9 and D11 were approved by the maintainer as recommended, with these clarifications:

- **D1:** real-world elapsed session time, including match transitions, lobby, matchmaking, breaks and downtime. A real-life rate is
  never chests per minute × 60.
- **D2:** joining runs less than 30 minutes apart is a grouping rule, not evidence of play during the gap. Measured time, unobserved
  gaps and active play stay distinct.
- **D3:** progress includes standing +1s and −1s by default, with the manual share shown separately. CERTAIN and the chests-per-minute
  checkbox keep their v0.3.0 meaning.
- **D4:** only chests **reliably** attributed to spectating (in a recognised Complete or Partial match that is not marked Not a match)
  leave progress statistics. Their rows, the detector's evidence and the totals are untouched. Elsewhere, attribution is treated as
  uncertain and the chest counts.
- **D6:** local midnight, with time zones, daylight saving and midnight-crossing sessions handled.
- **D7:** chest history whenever counts are saved; match recognition stays optional.
- **D11:** destructive updater tests only in an isolated Windows VM or disposable environment with synthetic data; never on the main
  PC or the second PC's real installation.
- Unobserved days are never confirmed zeros (section 3).

Left to this plan's recommendation, choosing the conservative option:

- **D8: no import** of pre-v0.3.0 session logs. Analytics says from which day it has data; lifetime totals stay on Overview.
- **D10:** match bests use **Complete** matches only; best chests per minute needs **5 minutes** of active play; the best hour must lie
  inside a fully counted 60 minutes; session rates need a session of at least 60 minutes.
- **D12:** the Overview line is built only if it can be computed by the same code as Analytics, so the two never disagree (including
  D4), and only while it stays cheap (M1 measures the cost of reading history). Otherwise it is deferred and recorded as such.

The original table, kept for reference:

| # | Question | Recommendation | Why |
|---|---|---|---|
| D1 | What is "per hour" divided by? | **Session time** (runs joined across short gaps), with time counting shown as a detail | Closest to "real life, breaks included" even when counting was stopped for a break |
| D2 | Break limit that splits sessions | **30 minutes** | Longer than queues and short breaks, shorter than "done for now" |
| D3 | Do per-hour, per-day and per-week numbers include your +1s? | **Yes**: recorded chests = detected + your standing corrections, like the Dashboard total, with "of which N added by you" beside. Chests per active minute keeps today's checkbox (off by default) | In the real session, +1s were 18% of the total. Fortnite counts broken chests, so leaving them out understates progress |
| D4 | Chests seen while spectating after you were out | **Leave them out** of progress numbers, and say how many were left out | They are someone else's chests |
| D5 | Week starts on | **Monday** (ISO weeks) | Standard; easy to change later |
| D6 | Day starts at | **Midnight** now; an optional "day ends at 4 AM" later if late sessions make days look wrong | Simplest correct default |
| D7 | Keep chest and session history when match tracking is off | **Yes**, whenever saving is on, with clearer Settings wording | Otherwise per-hour and per-day stats silently stop for anyone who turns tracking off |
| D8 | Import pre-v0.3.0 session logs | **No** | Unreliable source (test runs, no profile, scattered folders); lifetime totals stay on Overview |
| D9 | Tabs | **Performance, Days & weeks, Personal Bests, History** | Days and weeks are distinct and central for v0.5.0 forecasts |
| D10 | Record eligibility | **Complete matches** for match records; **5 minutes** of active play for best chests per minute; best hour only over a fully counted 60 minutes | Keeps records meaningful |
| D11 | Where to run the real updater failure tests | **A Windows virtual machine** on the main PC, if you have or want one; otherwise only synthetic tests plus the real release, documented as such | The main PC's blue screen is unexplained, and Windows 11 Home has no Sandbox |
| D12 | "Today · last hour" line on Overview | **Yes, small and optional** | Useful live on stream; the Dashboard stays focused |

## 10. Risks

| Risk | Mitigation |
|---|---|
| Time numbers that look precise but rest on gaps | Coverage shown everywhere; interrupted runs marked "at least"; unknown shown as a dash |
| Recognition misses play (non-English, unrecognised modes), so "between matches" looks too large | Unknown state when chests were counted outside any match (F13) |
| Reading a large history gets slow | Measured in M1; a rebuildable cache only if needed |
| History change breaks a rollback to v0.3.0 | No new kinds or schema; compatibility test against the v0.3.0 reader |
| Turning history on for tracking-off users | D7 decided explicitly; documented in release notes |
| Scope creep from many possible statistics | Section 2.5 is the list; anything else waits for v0.5.0 or later |
| UI crowding at 920 × 640 | Tabs; fit test extended; screenshots reviewed |
| Updater tests destabilise the main PC | D11; no real staging on the main PC without isolation |
| The v0.4.0 notes look bad in v0.3.0's window | Plain-text summary first (section 7) |

## 11. Definition of done for v0.4.0

- Every metric in section 2.5 marked "Supported" is shown, from history only, with its coverage.
- Personal Bests (section 4) with evidence.
- UX-01 to UX-08 fixed, and UX-09's list fixed or explicitly deferred.
- UT scenarios run in the agreed environment, or documented as not run, never as passed.
- Detector and overlay output unchanged; profiles, counts, history and settings from v0.3.0 kept; rollback to v0.3.0 reads v0.4.0's
  history.
- Docs and release notes updated; the maintainer's hands-on acceptance passed.
