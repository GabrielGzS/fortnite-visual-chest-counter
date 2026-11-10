# Match recognition replay scorecard (M3)

`research/match_replay.py` samples recorded pictures, runs the existing M1 cue
reader, feeds M2, and compares the result with separately authored match truth.
It is research-only: no live worker, GUI, OBS, profiles, history storage, or chest
detector is run or changed. Use Python from the project's existing environment.

## Fast replay of the five stored timelines

PowerShell, from the repository root:

```powershell
.venv/Scripts/python.exe -B research/match_replay.py `
  --timelines tests/fixtures/match/timelines.json.gz `
  --truth tests/fixtures/match/footage_truth.provisional.json --allow-provisional `
  --chests new=tests/baselines/en_v0.3.0-base.json `
  --chests ps5=tests/baselines/ps5_v0.3.0-base.json `
  --out analysis_output/m3/cached-scorecard.json
```

This is expected to report recognition inaccuracies and return **1**, not a
blanket success. The annotations retain the second real English match and its
visible edit around 262 s, independently of what M2 predicts.

`tests/fixtures/match/m2_reference.json` separately archives the previous M2
behavior at `d691310`. A behavior reference is not ground truth. The original
cue fixture is not rewritten, and has no full decoding provenance; the report
identifies it as `legacy_fixture`.

## Replay the actual recordings once, then reuse the evidence

```powershell
$capture = 'C:/Users/gzgab/Downloads/Fortnite-Visual-Chest-Counter/Fortnite-Visual-Chest-Counter-v0.2.2/captures/20261108_233437'
$ffmpeg = 'build_out/v0.2.3/Fortnite-Visual-Chest-Counter-v0.2.3/runtime/ffmpeg/ffmpeg.exe'
.venv/Scripts/python.exe -B research/match_replay.py `
  --capture $capture `
  --video 'new=samples/video tests/Fortnites-NEW-HD-No-Audio.mp4' `
  --video 'ps5=samples/video tests/Fortnite-PS5-Pro-HD-No-Audio.mp4' `
  --ffmpeg $ffmpeg `
  --truth tests/fixtures/match/footage_truth.provisional.json --allow-provisional `
  --chests new=tests/baselines/en_v0.3.0-base.json `
  --chests ps5=tests/baselines/ps5_v0.3.0-base.json `
  --write-timelines analysis_output/m3/decoded-cues.json.gz `
  --out analysis_output/m3/decoded-scorecard.json
```

Use `--timelines analysis_output/m3/decoded-cues.json.gz` afterwards. A new cache
records input/segment hashes, M1/visual/template hashes, dependency versions,
FFmpeg hash, sampling cadence and capture offsets. Cached mode replays those
recorded observations; it does not silently claim to have validated today's
video or reader. The report identifies the current M2 source hash separately.

Only one sample per second enters M2. To reproduce M1's original source-picture
selection, `.ffconcat` clips are decoded at 2 fps and every even sample is used;
standalone reference videos are decoded at 1 fps. Changing this sampling phase
can change scores. Chest detection at 15 fps is deliberately not repeated.

Each capture clip is an independent source (`clip1`, `clip2`, ...), with time
starting at zero. Gaps between retained clips never imply continuous observation.
The capture metadata is used only for clip/time integrity, not saved detector
settings or profiles. Captures with dropped frames, clock reversals, or live-time
gaps above M2's limit are rejected rather than compressed into seemingly continuous
video. Split/review those inputs explicitly. General nested/remote FFmpeg playlists
are not supported; the capture-generated local-file format is supported.

Clip1 and clip2 contain the same real match due to a stream rewind. The tool does
not sum source records into a global unique-match count. Within a source, duplicate
predictions and overlapping ownership intervals are checked. Inferring the identity
of a match across separate clips or edited repetitions is outside M3.

## Independent annotations

Truth is JSON with `schema: "match-truth-v1"` and a `sources` object. See the
committed provisional file for the full example. Source IDs must match exactly;
`--source clip1` explicitly selects a subset. Omitted sources never silently pass.

Every source supplies:

- `review`: `status` (`human_reviewed` or `provisional`), `reviewer`, and `basis`.
- `matches`: ordered records, each with a unique `id` and a positive-length
  `anchor: [from, to]` inside its visible portion. Anchors cannot overlap.
- `transitions`: ordered `{state, time: [earliest, latest]}` observations.
- Optional `unscored_transitions`: time windows with reasons, such as a hidden
  picture. Excluded predictions and windows stay visible in the report.

A match can specify `opened_t`, `played_from_t`, `ended_t`, and `closed_t` as
accepted windows. **Omit** a field that was not labelled; **null** explicitly
requires the prediction not to claim a known boundary. `opened_t` is first
observation of that occurrence, not necessarily the real match start. A human
reviewer should label visible ownership boundaries, so a tracker that discovers
a cut late receives a measurable error. `closed_t` in M2 is the closure decision
time, distinct from the visual ending; this distinction is exposed by comparison.

Optional `ended_by` is `placed`, `victory`, or null (no ending observed).
Optional classification expectations are `completion`, `english_confirmed` and
`observed_from_start`. English eligibility is distinct from whether a real
Portuguese match occurred. Omitted expectations are not invented by the scorer.

Association is ordered and one-to-one. A prediction must overlap a match's anchor
to represent it. An additional prediction for an already matched anchor is a
duplicate; a prediction elsewhere is extra. Transition association may extend
outside the accepted time window (`association_seconds`, default 30), but this
only permits reporting a delay: it does not make that delay pass. Actual signed
seconds outside the accepted window are retained for every assessed boundary.

The supplied annotations are **provisional**, based on prior cue-window notes and
Codex inspection of selected real frames. No human sign-off or exhaustive review
of full video continuity is claimed. A reviewer must inspect the footage, correct
the annotations if necessary, and record their review before changing the status.
`--allow-provisional` permits exploratory scoring and retains that status in every
report. It never turns provisional truth into a human-reviewed success.

## Chest evidence and timing

`--chests SOURCE=PATH` reads a frozen event list, or chest-event rows from JSONL.
Times must use that source's clip clock; out-of-range events fail. Raw event
fields, independent CERTAIN/APPROX booleans and template-derived language remain
intact. APPROX contains CERTAIN; invalid flags are rejected, not repaired.

For the Portuguese reference, source totals are 11 CERTAIN / 15 APPROX: 11 events
have Portuguese language evidence and four APPROX-only events have unknown
language. M2's `portuguese_chests=11` is therefore not the entire APPROX count.

The old M0 snapshots do not contain decision-delivery timestamps. The replay uses
M2's explicit three-second assumption, configurable with `--chest-delay`; an
event's `available_t` overrides it. Actual event time and assumed delivery time
are kept separately. Evidence arriving after EOF stays in the report. A chest
delivered on a black/frozen picture is flagged, not claimed as usable evidence.

`interval_matches` and `delivery_match` are diagnostic associations, not production
attribution or proof that the original player opened a chest. Spectator evidence
is not promoted into verified own-player statistics. Event storage/attribution
belongs to later milestones.

## Results and failures

The JSON report contains predictions, reasons, per-source completion counts, raw
chest evidence, truth associations and discrepancies. It reports missing/extra/
duplicate matches, missing/extra/wrong transitions, false/missed endings,
classification errors, boundary errors and independent interval invariants.

- Exit 0: every required assertion passed (status still says provisional if used).
- Exit 1: recognition, accounting, or required human-review validation failed.
- Exit 2: invalid/missing input, malformed truth, or decoding error.

Empty decoding, incomplete RGB frames, and FFmpeg failure cannot produce success.
Output files are explicit; do not put research outputs in live user-data folders.

## Focused checks

```powershell
.venv/Scripts/python.exe -B tests/test_match_replay.py
.venv/Scripts/python.exe -B research/match_replay_mutations.py
.venv/Scripts/python.exe -B tests/test_match_state_defects.py
.venv/Scripts/python.exe -B tests/test_match_state.py
.venv/Scripts/python.exe -B tests/test_match_cues.py
```

The scorecard suite includes an actual subprocess invocation with deliberately
incorrect truth and asserts exit 1, a detailed failure report, and untouched fake
profile state. The mutation check sabotages private in-memory copies of M3 only.
The audit suite asserts desired M2 behavior and was demonstrated failing before
corrections; it has no expected-failure marks or weakened assertions.
