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
