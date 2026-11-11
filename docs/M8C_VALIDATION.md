# M8C validation record

Date: 2026-11-11. Branch: `dev/v0.3.0`, on top of `4686e57`. Adds two manual corrections: a chest count of +1 or -1,
and Not a match / Restore on a recorded match. No prediction or detector scoring is built.

## Audit of the existing counter

Before changing anything that affects the official totals:

- `CounterSession.save` and `write_obs` are the only path that changes totals, and Reset, Edit counts and `adjust` all
  end there. Corrections use that path, so there is no second source of truth.
- The chest-type line already holds everything the detector did not classify, including manual changes, as "not
  classified". The numbers still add up with no new field.
- **A real risk:** Edit counts writes the counter file from the app while the worker may be running. That is safe for
  setting an absolute number. A relative +1 could lose a chest if both write at once. So while counting, corrections go
  to the worker through the same stdin channel as Mark, and only the worker writes. When not counting, the app applies
  them directly.
- Reset restarts event ids. Corrections do not touch `events_logged`, so they cannot collide with chest identities.

## What was added

**Chest corrections.** Two buttons on the Overview, -1 and +1, take effect at once using the reason last chosen. A line
then appears: `Detector 231 · Manual +2 · Total 233`, with an optional "Why?" and Undo.

- APPROX only. A chest the user adds was not confirmed by the detector, so it never becomes CERTAIN.
- A -1 that would put APPROX below CERTAIN is refused and the button is disabled. Correcting a wrong CERTAIN chest
  stays with Edit counts, because the correction does not know which event was wrong.
- Undo adds a row and leaves the original. A correction made before a Reset or Edit counts can no longer be undone,
  because the total it changed has been replaced. `counter_token` (the counter's start time plus a `counter_life`
  number that Reset and Edit counts raise) identifies this.

| Reason | Meaning | A claim about the detector? |
|---|---|---|
| `manual` (default) | Not sure, or a balance fix | No |
| `not_visible` | Fortnite counted it with nothing on screen, such as a broken chest | No |
| `missed` | A visible chest the counter missed | Yes |
| `false_positive` | Counted something that was not a chest | Yes |

Each correction is kept in `chests.jsonl` with its identity, time, run (when counting with tracking on), delta, latest
reason, totals after it and the detector count at that moment. They are recorded whether or not match tracking is on.
Analytics does not include them, and says so.

**Match corrections.** Each recent match on Analytics offers Not a match, then Restore. Each is a new row: nothing is
deleted, the chest rows and totals are untouched, and the match stays listed so it can be restored.

## Results

| Check | Result |
|---|---:|
| M8C corrections suite (`tests/test_corrections.py`) | 68/68 pass |
| M8C targeted mutations (`research/corrections_mutations.py`) | 47/47 caught |
| M8B analytics suite and mutations | 52/52, 43/43 |
| M8A views suite and mutations | 27/27, 25/25 |
| M7 UI suite and mutations | 50/50, 41/41 |
| M6 recording suite and mutations | 50/50, 37/37 |
| M5 history suite and mutations | 98/98, 57/57 |
| M4 tracker suite and mutations | 63/63, 35/35 |
| M2 lifecycle and audit | 78/78, 26/26 |
| M3 scorecard and mutations | 38/38, 11/11 |
| M1 cues | 25/25 |
| Basics, profiles, types, OBS, stream, release, update window, app | 6, 10/10, 9/9, 18/18, 8/8, 77/77, 70/70, 30/30 |

The full run came before two final display fixes to the Analytics table. The corrections, analytics, Dashboard and
update-window suites, their mutations and the self-test were re-run after them. `test_obs` passed this run, but its known
intermittent failure remains.

One mutation makes every +1 count as a detector miss; it is caught. A separate test proves `not_visible` never does.

**Live soak on real video.** The real `--gui` worker counted 80 s of the English clip in `on` mode while receiving one
correction every 2 seconds, right through the chests, then an undo.

| Sent | Applied | Chests detected | Final APPROX | Expected | CERTAIN | Gaps |
|---|---|---|---|---|---|---|
| 30 + 1 undo | 31 | 5 | 34 | 5 + 30 - 1 = 34 | 5, unchanged | None |

The OBS file showed 34, history held all 5 chests, and the 29 standing corrections were all `not_visible` with 0 detector
misses.

**Real video, first 100 s.** `counter.py` changed in this milestone, so the comparison was repeated. Events, OBS files and
saved counts were identical across `off`, `shadow` and `on`, and match the frozen M0 baseline.

The visual review found two Analytics table bugs that tests could not: "Counting stopped" was cut off, and a replaced
button stayed drawn in the corner. Both are fixed and now have tests. Screenshots are in `analysis_output/m8c/screens/`,
which is git-ignored.

Existing tests changed: M5's allowed-modules list gained `app.py`, M8B's Not a match test now expects the excluded
match to stay listed, and the Dashboard inventory gained the new controls.

## Limits

- No person has used this by hand yet, and no real livestream or OBS camera has been run with it.
- While counting, a correction applies on the next frame. If no video is arriving it waits, and is applied at the latest
  when counting stops.
- If the app dies between saving the total and writing the correction row, the total is right but the "Detector" line is
  off by that one correction.
- A correction made after a crash and before the next start reads as a difference at recovery, like Edit counts, and
  is recorded as a gap.
- Reason data is stored for future accuracy estimates. None are calculated.

Nothing was pushed, merged, tagged or published. Stop for review before M9.
