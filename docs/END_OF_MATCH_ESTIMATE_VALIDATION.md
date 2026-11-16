# End-of-match chest estimate (validation notes)

Branch `dev/remote-sharing`, on top of Milestone A. Part of the next release; not released on its own. Plan and evidence: the
"End-of-match estimate" tab of the planning doc.

## Why

A broken chest shows no pop-up, so the detector cannot see it. In the maintainer's v0.5.1 history (read-only), the "Broken chest" +1s
made in the Game view came to 315 of 1,538 detected chests over 33 complete matches: 20.5 % pooled, median 19 %, single matches 2-51 %.

## What it does

- Dashboard > Game: **Add estimated broken chests when a match ends** + a percentage (1-100, default 20 %), **off by default**. Saved at
  once in `[chest_estimate]` of config.toml and sent to a running counter (`estimate {json}` on the worker's stdin).
- When a **complete** match (English confirmed, start and end seen, no gap) has settled - 10 s of video after its close, the next match
  opening, or counting stopping, whichever first; the stop case is decided before the tracker closes the match Stop cuts off - the worker
  adds `round_half_up((detected APPROX - your -1s) x percent / 100) - your Broken chest +1s` (never below 0) to APPROX. CERTAIN and the
  chest types never change. Live counting only (not "Analyse a recording").
- Exactly once per match: id `estimate:<run id>:<match number>`, checked against the run's memory and the history. A settled match is
  offered once, so turning the feature on later never reaches back. A restart is a new run.
- Stored as its own row kind, `chest_estimate`, in **matches.jsonl** (older versions skip unknown kinds there silently; in chests.jsonl
  v0.5.1 would count them as damaged lines). Read together with the corrections, flagged `estimate`: Undo takes it back like a +1 (refused
  across a Reset/Edit counts, and below CERTAIN), the Overview line shows Detector / Manual / Estimated / Total, and per-match +1 tallies
  (`corrections_by_match`) never include it.
- Analytics: in the match's APPROX ("(+n est.)"), in rates only with "Count my +1s" ticked, a summary note, never a Personal Best.

## Tests

| Suite | Result |
| --- | --- |
| `tests/test_match_estimate.py` (new): arithmetic and rounding table, eligibility, 100 -> +20 and 150 -> +30, APPROX only, OBS text, exactly once (repeat, fresh session, new run), top-up, -1s, nothing-to-add, Undo (and below CERTAIN), Reset/Edit counts, old-reader invisibility, settling (late chest in, once, final, next match), the live-loop helpers and control channel, config validation, Analytics, the Dashboard setting/preview/applied/undo, the real live loop with it on, stop order | 26/26 |
| Existing suites, every one except `test_cases` (detector untouched): 36 more, among them `test_app` 30/30, `test_corrections` 82/82, `test_match_history` 98/98, `test_match_analytics` 61/61, `test_match_tracker` 68/68, `test_match_ui` 50/50 | all pass |

Architecture rules kept: only the counter applies it; `match_tracker` imports nothing new; no module outside the allowed list names the
history or tracker modules (two such tests caught early drafts).

Mutation check (12 hand-made mutations: rounding, top-up, eligibility, dedupe, tallies, settling once/wait, rates, row file, setting
ignored, undo bookkeeping, CERTAIN): 12/12 caught.

## Known limitations

- The percentage is an average: single matches range widely (2-51 % in the evidence).
- A match cut off by Stop, a video gap, or not confirmed as a match gets no estimate (by design).
- At the smallest window size (920 x 640) the Game view now scrolls about 130 px to reach Fix this match and the estimate row.
- A crash in the milliseconds between saving the counter file and appending the history row leaves the estimate in APPROX without its
  row (never duplicated) - the same window corrections have.
