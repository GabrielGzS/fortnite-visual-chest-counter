# M3 validation record

Date: 2026-11-10. Branch: `dev/v0.3.0`. This document records M3 evidence, not a
replacement for the private ten-milestone plan (the export has not been supplied).

## Before M2 corrections

M2 source: `d6913106240625c2876fb0a790d89cf39840744c`, unchanged throughout the
initial replay and defect demonstration.

Original capture located and read at:

```text
C:/Users/gzgab/Downloads/Fortnite-Visual-Chest-Counter/Fortnite-Visual-Chest-Counter-v0.2.2/captures/20261108_233437
```

The three playlists and segments exist, with 0 dropped recorded frames. The
capture contains marks but no filled-in truth judgments. Match truth supplied
with M3 is consequently marked **provisional**, not human-approved.

All five recordings were decoded through M1 and M2, using the frozen M0 chest
event lists rather than running the chest detector again. FFmpeg SHA-256:
`7A1CC6F3E55089F5C0575F14F8BD608CAD4F2CCEF813C9536F876F5B481C83F0`.

| Source | Cue samples | Matches original M1 fixture after its documented rounding | Matches frozen M2 outcome |
|---|---:|---|---|
| clip1 | 60 | exact | exact |
| clip2 | 80 | exact | exact |
| clip3 | 60 | exact | exact |
| English (`new`) | 509 | exact | exact |
| Portuguese (`ps5`) | 1029 | exact | exact |

The 1,738 samples reproduce the stored scores, health evidence, black/frozen flags
and timestamps, not just the number of matches. The M2 behavior reference is
archived in `tests/fixtures/match/m2_reference.json` and remains separate from
independent truth.

Against provisional visual annotations, clip1, clip2, clip3 and ps5 pass. The
English edited recording fails with an extra UNKNOWN transition and four boundary
errors. Its visible edit into the second match is around 262 s; M2 closes/opens
ownership at 302 s and announces IN_MATCH at 303 s. This is 38-39 seconds outside
the annotated ownership windows and 36 seconds outside the allowed transition
window. The truth is not moved to match the timer.

Initial focused results:

- M3 scorecard: **37/37 pass**; includes a real CLI subprocess with deliberately
  incorrect truth returning exit 1 and preserving fake profile state.
- M3 targeted mutations: **11/11 caught**, using a committed, reproducible
  in-memory runner. This is distinct from the earlier developer's unarchived
  51-mutation claim.
- Permanent M2 audit regressions: **3/16 pass, 13 fail** before corrections.
  No skips, expected failures or modified thresholds. Additional time tests expose
  missing stop-tail accounting, counting the last black interval as active, and
  black countdown time becoming active time.

Local, git-ignored evidence:

```text
analysis_output/m3/decoded-cues.json.gz
analysis_output/m3/before-fixes.json
analysis_output/m3/baseline-reproduction.json
analysis_output/m3/test_match_replay-before.txt
analysis_output/m3/match_replay_mutations-before.txt
analysis_output/m3/test_match_state_defects-before.txt
```

Review contact sheets are also under that directory. They are selected frames,
not a claim that every moment of each video has been reviewed by a human.

## After the approved M2 corrections

M3 was committed locally as `b990db5` before changing M2. The user then approved
the four conservative corrections and the associated recall tradeoff. The interrupted
working tree was recovered intact; no video decoding or full chest-detector
regression was repeated while finishing this verification.

The countdown blackout fix was present at recovery and is now verified. A long
break after the last countdown cannot date active play from before the blackout.
The regression asserts `played_from_t == 28` and exactly six active seconds;
its previous upper bound was strengthened, not relaxed. A separate control ensures
uncertainty before a fresh countdown is not subtracted from later play.

| Focused check | Final result |
|---|---:|
| M2 lifecycle suite | 78/78 pass |
| Permanent audit regressions | 26/26 pass |
| M3 replay scorecard suite | 38/38 pass |
| M1 cue suite | 25/25 pass |
| Targeted M3 mutations | 11/11 caught |

The 167 test functions include a 60-case matrix of timeout/stop/black-picture
combinations, independent time invariants, language breaks and fresh-evidence
controls, spectator HUD recovery, and long post-victory celebrations. The original
13 failing checks now pass. Seven existing M2 tests whose expectations required
unsafe heuristics were replaced with conservative assertions, preserving checks
for genuine observed boundaries and stronger active-time/ending guarantees.
No skipped or expected-failure tests were introduced.

The initial resumed scorecard run stalled during execution; a live-output run
and a diagnostic run both completed 38/38 without code or assertion changes.
The remaining cue/mutation checks and cached scorecard also completed successfully.

The scorecard replay used the existing `decoded-cues.json.gz`, with exactly the
same provisional annotations and frozen chest events as before corrections:

| Source | Post-fix outcome against provisional truth |
|---|---|
| clip1 | Pass; one partial placed match, same transitions |
| clip2 | Pass; one partial placed match after rewind, same transitions |
| clip3 | Pass; one partial match with the observed start, same transitions |
| Portuguese (`ps5`) | Pass; one unconfirmed win, no English confirmation |
| English (`new`) | Fail; one partial first win, second edited match missed |

The English result has **one missed match, one missed ending, two missed
transitions and one boundary error**. The first record remains open until 509 s
because M1 supplies no recognized boundary at the editorial cut; this is 246 s
outside the first record's annotated closing window. Both real victories remain
in truth. The tool correctly returns **exit 1**; a known miss is not promoted to a
successful recognition result. Annotation status remains **provisional**, pending
independent human review.

Across the five cached sources, there are **zero duplicate/extra match records,
zero false endings, zero time-invariant errors, and zero complete matches**.
The four other sources retain the archived M2 transition/ending/classification
outcomes. The old two-win behavior remains archived in `m2_reference.json`.

Post-fix report and console output:

```text
analysis_output/m3/after-fixes.json
analysis_output/m3/cached-replay-after.txt
```

Git comparisons confirm frozen detection code, estimator and chest templates are
identical to v0.2.3. No existing application source file changed from v0.2.3; the
only source additions are the isolated M1/M2 modules and match templates. M1/M2
tests verify that live application code still imports neither recognition module.
M3 research code, truth and reference fixtures are unchanged from `b990db5`.

M2 corrections are committed separately from M3. Stop for review before M4.

## Limits retained

- No recording here covers a verified complete match from pre-game to ending.
- Reboot/respawn behavior lacks real own-player identity evidence.
- M1 does not recognize editorial cuts or every English UI element.
- Clip1 and clip2 show the same real match twice; cross-source records must not
  be summed into unique-match statistics.
- Cached chest delivery uses the explicit three-second M2 assumption unless an
  `available_t` was recorded. Production chest attribution remains out of scope.
- Four APPROX-only Portuguese-video events have unknown language. Raw evidence
  keeps them; M2's Portuguese chest count alone does not represent all chests.
- No long chest-detector regression, live integration, release, push or publication
  is part of this milestone.
