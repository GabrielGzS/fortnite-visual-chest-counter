# M8 validation record

Date: 2026-11-11. Branch: `dev/v0.3.0`, on top of `d49483a`. Two separate commits, so either can be reviewed or
reverted alone: M8A restructures the Dashboard and M8B adds Analytics. `counter.py`, `settings.py`, the tracker,
recognition, profiles, OBS and the updater are byte-identical to M7.

## M8A: Dashboard views

The Dashboard now answers one question at a time, through a row of tabs under the page title.

| View | Holds |
|---|---|
| Overview | Profile, CERTAIN and APPROX, chest types, one-line match status, what viewers see, OBS status, video source, start and stop, session metrics, Analyse a recording |
| Game | Match status, active / seen / unclear time, start seen, language, Live preview |
| Console | Activity log, detail level, Clear, Logs folder, Diagnostic recording, Mark moment |

The status pill, error banner and update notice stay above the tabs on every view, so a failure cannot hide on a
view that is not open. The log is out of sight on the other views, so the Console tab shows how many warnings are
unread, for example "Console (2)".

Every control is kept, with one exception: the "Activity" on/off toggle is gone, because the Console tab replaces it.
The Live preview toggle stays, and the preview now runs only while the Game view is open, which saves CPU. Settings
remains the home for configuration. Swiping and movable cards were not built.

## M8B: Analytics

`match_analytics.py` is a pure module with no GUI. The page is one more main page, between Dashboard and Overlay. It
reads history on a background thread and is read-only.

| Figure | Definition |
|---|---|
| Matches | Complete, partial and unconfirmed, always shown apart |
| Observed match time | Complete and partial matches, on screen |
| Confirmed play | Active time in complete matches only |
| Time counting | Session time, in or out of matches. "At least" when a session was cut short |
| CERTAIN / APPROX chests | Every chest in history. APPROX includes CERTAIN and is never added to it |
| Per complete match | Credited chests, over complete matches |
| Complete-match rate | Credited chests over active minutes, complete matches only. The comparable figure |
| Observed rate | The same, with partial matches included, shown apart and labelled not comparable. Needs at least 5 minutes of play |

Rules: unknown shows as a dash and zero means a real zero. Unconfirmed matches stay out of every statistic. A match
whose history lost chests is left out of both rates, and its row shows counts such as "3+". Rates are total over
total, not an average of per-match rates. Only chests during active play are credited. An ending is shown only as it
was observed. A note lists anything a reader should know, such as gaps or damaged rows.

**Not built, a decision for review:** the approved plan offered a "Not a match" correction on each recent match, but
the M8 brief says the page is read-only. The page has no button. Storage and the statistics already honour such
corrections, so adding it later is small.

`attribute()` in `match_history.py` now finds a chest's match by binary search, because the earlier scan would have
been far too slow on a very large run.

## Results

| Check | Result |
|---|---:|
| M8B analytics suite (`tests/test_match_analytics.py`) | 52/52 pass |
| M8B targeted mutations (`research/match_analytics_mutations.py`) | 43/43 caught |
| M8A views suite (`tests/test_dashboard_views.py`) | 27/27 pass |
| M8A targeted mutations (`research/dashboard_mutations.py`) | 25/25 caught |
| M7 UI suite and mutations | 50/50, 41/41 |
| M6 recording suite and mutations | 50/50, 37/37 |
| M5 history suite and mutations | 98/98, 57/57 |
| M4 tracker suite and mutations | 63/63, 35/35 |
| M2 lifecycle and audit | 78/78, 26/26 |
| M3 scorecard and mutations | 38/38, 11/11 |
| M1 cues | 25/25 |
| Basics, profiles, types, stream, release, update window, app | 6, 10/10, 9/9, 8/8, 77/77, 70/70, 30/30 |
| OBS | 17/18, the known intermittent `test_wrong_password_and_kick_are_not_retried` (see M6) |

The expected values in the worked example were calculated by hand, not by the code under test. It covers complete,
partial and unconfirmed matches, a chest after the ending and one outside any match.

Existing tests changed: M7's page count is now 5, M5's list of modules allowed to use history gained
`match_analytics.py`, its standard-library list gained `bisect`, and three older sabotage cases were re-aimed at the
moved code.

Surviving mutations were followed up: one exposed a test whose two results were in the order that hid the bug, now
reversed so the older, slower read finishes last.

**Real data.** The real worker ran 60 s on each reference clip in `on` mode, and its real history was shown on the
real page.

| Clip | Matches | Observed | Chests | Rates |
|---|---|---|---|---|
| English | 1 partial | 59 s | 2 / 2 | Both dashes: no complete match, under 5 minutes of play |
| Portuguese | 1 unconfirmed | Dash; 59 s kept apart as unconfirmed | 0 / 3 | Both dashes |

**Large history.** 5,000 matches, 40,000 chests and 30,000 state changes load in 356 ms, or 392 ms with a heartbeat
every minute (38 MB). It runs off the window's thread, and a test confirms a slow read leaves the window responsive.

**Layout.** At the default size, every Dashboard view and the Analytics page fit without scrolling, with real fonts.
The minimum window scrolls vertically and never sideways. Screenshots were reviewed; they are in
`analysis_output/m8/screens/`, which is git-ignored.

Because no counting code changed in M8, M7's off / shadow / on real-video comparison still applies and was not
repeated. The frozen detector check passes against `032df3b`. The window's own `--self-test` passes unpackaged.

## Limits retained

- No person has used the new Dashboard or Analytics by hand yet.
- A real livestream, OBS camera or capture card has not been run with tracking on.
- No real footage has produced a complete match, so the complete-match figures have only been exercised on constructed
  data, and on real footage they correctly show dashes.
- The edited English video deliberately keeps its missed second match. Annotations remain provisional.
- A real reboot is not credited as play, which is the conservative M2 behaviour.
- README and in-app help still describe the old Dashboard layout, and the release build does not ship the match
  templates. Both belong to M9.
- The intermittent OBS test should be fixed before release.

Nothing was pushed, merged, tagged or published. Stop for review before M9.
