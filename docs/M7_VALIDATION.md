# M7 validation record

Date: 2026-11-11. Branch: `dev/v0.3.0`, on top of `f998ff4`. M7 makes match tracking reachable from the desktop app:
a read-only status line on the Dashboard and a card in Settings. It adds no analytics and no packaging.

## What was added

**Dashboard.** One line, "Match (experimental):", under Chest types. It appears only while counting with tracking on.

| What the worker reports | What the line says |
|---|---|
| Lobby, loading, pre-game | In the lobby / Loading / Waiting for the match to start |
| Unknown | Not sure yet |
| In a match, seen from its start | In match, 12:34 |
| Joined partway | In match, 12:34 seen · partial: joined after the start |
| A break in the video | In match, 12:34 seen · partial: part of it was not seen |
| No English evidence (Portuguese, or English not seen yet) | Possibly in a match, 12:34 seen · not confirmed yet (no English game text seen) |
| Out, no ending seen | Spectating or out of the match |
| Ending seen | Match over, plus the same partial or unconfirmed note. Never "complete" |
| Black or frozen picture | The state, plus "no picture right now" |
| No message for 5 s | No video right now |
| Tracker failed / could not start | Stopped for this session after an error / Not available for this session, each saying counting is not affected |

An unknown time shows no time at all, never a made-up 00:00. Anything unrecognised reads "Not sure yet".

**Settings.** A "Match tracking (experimental)" card: a checkbox mapping to `[match] mode` (`on` or `off`) and a
"Save progress every" selector of 30 seconds, 1 minute (recommended), 5 minutes or 10 minutes. Tracking stays off by
default. Changes apply to the next counting session, as the page already says. `shadow` is not offered; a `shadow`
value in `config.toml` is left alone unless the user ticks the box.

**Worker.** In `on` mode only, it sends a `match` message once per second of video. Shadow sends none, so M4's
guarantee that shadow makes no difference to the app still holds. If telling the app fails, only the status line
stops; recording carries on.

`match_state.snapshot()` gained three read-only fields the line needs.

## Results

| Check | Result |
|---|---:|
| M7 UI suite (`tests/test_match_ui.py`) | 50/50 pass |
| M7 targeted mutations (`research/match_ui_mutations.py`) | 41/41 caught |
| M6 recording suite and mutations | 50/50, 37/37 |
| M5 history suite and mutations | 98/98, 57/57 |
| M4 tracker suite and mutations | 63/63, 35/35 |
| M2 lifecycle and audit | 78/78, 26/26 |
| M3 scorecard and mutations | 38/38, 11/11 |
| M1 cues | 25/25 |
| Basics, profiles, types, OBS, stream, release, update window, app | 6, 10/10, 9/9, 18/18, 8/8, 77/77, 70/70, 30/30 |

The final wording change to one status message came after the full run; the M7 suite and its mutations were re-run
after it. `test_obs` passed this time, but its known intermittent failure remains (see M6).

Two lines of `tests/test_match_recording.py` changed: its app comparison now ignores the `match` messages added on
purpose, and a snapshot check allows the three new fields.

Two mutations survived at first. One removed a redundant `hide()`, which `set_mode` also does, and was dropped. The
other was applied to the wrong copy of a module, and was corrected.

**Real video, first 100 s.** Pinned M0 FFmpeg. Events, OBS files and saved counts were identical across `off`, `shadow`
and `on`, events starting in the first 90 s match the frozen M0 baseline, and history matched the totals.

**Real worker through the real window.** The real `live --gui` worker ran 40 s on each reference clip in `on` mode, and
its recorded messages then drove the real window, rendered hidden with real fonts.

| Clip | Line over time | Final counts |
|---|---|---|
| English | Not sure yet → Possibly in a match → In match, partial: joined after the start (38 s, when the first English chest arrived) | 1 / 1 |
| Portuguese | Not sure yet → Possibly in a match, not confirmed yet | 0 / 3 |

After the worker exited the line was hidden and empty. Screenshots of the Dashboard and Settings were reviewed. The
window's own `--self-test` passes unpackaged. The packaged self-test belongs to M9. The frozen detector check passes
against `032df3b`. Local, git-ignored evidence is under `analysis_output/m7/`.

## Known issues kept

- Full lobby-to-lobby accuracy is unverified on real footage. No complete match has come from real footage yet.
- A real livestream, OBS camera or capture card has not been run with tracking on.
- No person has used the Dashboard and Settings by hand yet; that is the remaining acceptance step.
- The edited English recording deliberately keeps its missed second match. Cached replay stays 4/5.
- Annotations remain provisional.
- `test_wrong_password_and_kick_are_not_retried` in `test_obs` is intermittently flaky, also on v0.2.3.
- `packaging/build_release.py` does not ship `templates/match/` yet. This must be fixed before v0.3.0 is published
  (M9). Until then a packaged build shows "Not available for this session".

Nothing was pushed, merged, tagged or published. Stop for review before M8.
