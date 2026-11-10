# M5 validation record

Date: 2026-11-11. Branch: `dev/v0.3.0`, on top of `63418e4`. M5 adds the storage for match history and tests it
on its own. Nothing in the program uses it yet: connecting it to counting is M6. It implements no statistics, no
reward calculations and no user-facing feature.

## What was added

`src/fortnite_chest_counter/match_history.py` writes and reads two append-only files per profile:

```text
state/history/<profile id>/matches.jsonl   run_start, run_end, heartbeat, transition, match_opened,
                                           match_closed, counter_change, gap, correction
state/history/<profile id>/chests.jsonl    chest, chest_type
```

`profiles.py` gained `history_folder`, and `delete` now moves a profile's history to
`state/history/deleted/<id>-<stamp>/`.

Every row has `kind`, `schema` (1) and `id`. Rows hold observations, never averages, so any statistic can be
recalculated when its formula improves.

| Identity | Key |
|---|---|
| A run | `run_id`, new for every counting session |
| A match | `run_id` + `match_number` |
| A counted chest | `run_id` + `counter_epoch` + `event_id` |
| Any row, across retries | `id`, assigned once |

| Evidence kept for later statistics | Where |
|---|---|
| Session start and end, wall clock | `run_start.at`, `run_end.at`, or `last_seen_at` after a crash |
| Source, app version, languages | `run_start` |
| Configured analysis fps | `run_start.configured_analysis_fps` |
| Frames really processed and dropped, elapsed time | `run_end` and heartbeats |
| Observed, active, spectating, uncertain and complete-duration time | `match_closed`, kept separate |
| Complete, partial, unconfirmed, and confidence at each boundary | `match_closed` |
| Lobby, loading and pre-game time | `transition` rows |
| Chest time, CERTAIN and APPROX flags, type, language, tier | `chest` |

Which match a chest belongs to is not stored. It is worked out on reading from the chest's own time, so
correcting a match never rewrites a chest row. `respawns` is left out: it cannot be measured yet, and a stored 0
would read as "no reboots".

## Decisions that differ from the approved plan

1. **Chest identity uses a counter epoch, not a timestamp.** The plan's key of `run_id` + `event_id` loses data:
   a Reset during a run restarts event ids, confirmed against the real `CounterSession`. A timestamp would also
   have fixed that, but it would tie identity to source time, which can repeat. Each counter restart starts a new
   epoch, whether announced or noticed from the numbering, so identity does not use time at all.
2. **Failed writes are retried first.** The plan writes a gap row after a failed write. Here the row is kept and
   retried in order with the next write, so a short file lock loses nothing, and a gap row appears only for rows
   really lost.
3. **A recovered match without English evidence stays `unconfirmed`**, not `partial`, which keeps M2's rule that
   unconfirmed matches stay out of statistics.
4. **Totals found below history after a crash are recorded as `totals_lowered`**, without marking any match
   incomplete. The user lowered them; history lost nothing.
5. **The 100 ms target is measured on listing matches**, because M5 implements no summary.

## Results

| Check | Result |
|---|---:|
| M5 history suite (`tests/test_match_history.py`) | 98/98 pass |
| M5 targeted mutations (`research/match_history_mutations.py`) | 56/56 caught |
| M4 tracker suite and mutations | 63/63, 34/34 |
| M2 lifecycle and audit | 78/78, 26/26 |
| M3 scorecard and mutations | 38/38, 11/11 |
| M1 cues | 25/25 |
| Basics, profiles, release | 6, 10/10, 77/77 |

No video was decoded, and `test_app`, `test_types`, `test_obs` and `test_stream` were not re-run: `counter.py`,
`settings.py` and the detector did not change. The M1 to M4 and existing suites ran before the final edits to
`match_history.py`, which none of them import.

Three mutations survived at first. Two were aimed at a test that could not see them and were retargeted. One
exposed that nothing proved finished runs are skipped during recovery, which is now tested directly.

### Verification requested before approval

| Requirement | Evidence |
|---|---|
| Reset never suppresses a distinct chest | A real `CounterSession` Reset producing two `E0001` chests keeps both; announced and unannounced restarts |
| Repeated delivery is idempotent | Same event twice, including after a Reset; repeated rows; same chest under a new row id; retry after an uncertain write |
| A crash or truncation cannot invent time | The last heartbeat cut at every byte and recovered; no heartbeat means zero observed time; impossible heartbeat totals are clamped; every record passes the M3 time invariants; an interrupted match is never complete |
| Completed runs are not recovered or modified | A clean run followed by a crashed one: its bytes are untouched and it keeps exactly one `run_end`; a second recovery changes nothing |
| Profile deletion is safe | History moves and is never erased; a locked history stops the delete with nothing changed; a failed counter move puts the history back; a new profile reusing the id starts empty |
| Totals stay authoritative | The module imports only the standard library, nothing in the program imports it, and recovery leaves the real counter file byte-identical |
| Large files load reasonably | Measured below |
| Epoch across a restart | The epoch restarts at 0 in a new process, which is safe because `run_id` is always new. Same event id, epoch and source time across a restart stay two chests. 5,000 generated run ids do not repeat. Recovery rows use the recovering writer's id space |

### Large history

Synthetic: 5,000 matches of 20 minutes, about 1,700 hours of play, with 6 transitions and 8 chests per match.

| Heartbeat every | File sizes | List matches | Read everything | Normal start | Start after a crash |
|---|---|---:|---:|---:|---:|
| 60 s | 46.5 + 14.2 MB | 114 ms | 672 ms | 107 ms | 1,457 ms |
| 5 min | 17.9 + 14.2 MB | 81 ms | 372 ms | 65 ms | 790 ms |

At one heartbeat a minute, listing misses the 100 ms target slightly, and heartbeats make up most of the file.
The repository test pins the five-minute case. Appending one row takes about 6 ms including the disk flush.

## For M6

- Choose the heartbeat interval. Five minutes keeps files small, and a crash then moves up to five minutes of
  play into uncertain time; it never invents any.
- Heartbeats need the open match's running totals, which requires a small read-only accessor on `match_state.py`.
- `counter_changed` must be called whenever the counter file is adopted. `sync_external_changes` returns False
  when the counts are unchanged, even though a Reset can still have restarted the event ids.
- Decide what an explicit `--state` file does, since it has no profile folder.
- Reading everything can take over half a second on a huge history, so M8 should not do it on the window's thread.

The real updater and build checks remain at M9. Statically, `state/` is user-owned in the updater and the build
audit rejects `.jsonl` files.

Nothing was pushed, merged, tagged or published. Stop for review before M6.
