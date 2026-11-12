# v0.4.1 validation

Results of each v0.4.1 milestone, in order. Plan and decisions: [V0_4_1_PLAN.md](V0_4_1_PLAN.md). Tests run with the project's virtual
environment (`.venv\Scripts\python.exe tests\<file>.py`); research scripts with `PYTHONPATH=src`.

## M0 — Baseline and reproducible failures

### Evidence added

| File | What it holds |
|---|---|
| `tests/cases/user_20261112.json` | Ground truth for `samples/video tests/2026-11-12 12-52-32.mp4` (SHA-256 recorded): 20 chests (18 new pop-ups, 2 chest lines added to CROWN BONUS pop-ups), 10 verified non-chest pop-ups, every screen from the reboot to the lobby, both matches with their boundaries and true active time, and what v0.4.0 did with each |
| `tests/cases/cases.json` | Six cases from that recording, with a `v041_gap` that pins v0.4.0's result exactly: the duplicate, the four misses, and 0 CERTAIN |
| `tests/fixtures/popups/user_*.npz` | Their pop-up box masks (530 KB in all) |
| `tests/test_cases.py` | `test_v041_gaps_reproduce_exactly_until_fixed`: fails on purpose when a gap changes, so each fix removes its gap entry and the case must then pass like every other |
| `tests/fixtures/match/user_20261112_observations.json.gz` | Every Observation the real pipeline fed the match state machine on the recording, with the live-only fields (green health bar, HUD in view, chest times) the replay cache does not keep |
| `tests/test_user_recording.py` | Replays them: v0.4.0's two records exactly; the Complete and active-time gaps pinned against the truth |
| `research/pipeline_baseline.py` | The real `simulate` pipeline in a temporary folder of its own, recording chest events, match observations, detector time per frame and process CPU |
| `research/regress.py` | Clip `user1112`, scored against its labels (found, duplicates, false, CERTAIN may not get worse) |
| `research/cases.py` | Cases can be windows of a plain recording (`"video"`); `fixtures --case` writes only the named cases |
| `tests/baselines/{en,ps5,user1112}_v0.4.0.json` | v0.4.0 event snapshots |

### Baseline results

| Check | Result |
|---|---|
| `regress.py snapshot --tag v0.4.0 --clips en ps5` | en 6 events (6 CERTAIN), PS5 24 events (11 CERTAIN, 15 APPROX); **byte-identical to `*_v0.3.0-base.json`**, which also settles M9H's open "en/PS5 must stay byte-identical" check |
| `user1112` (the recording, full pipeline) | 17 events, 0 CERTAIN, 17 APPROX; against the labels: 16 of 20 found, 1 duplicate, 0 false |
| Cases on full frames (`research/cases.py run`, the six new cases) | 6 of 10 found, 4 missed, 1 duplicate, 0 false, 0 CERTAIN: exactly the pinned gaps. Found on the way: both RARE CHEST pop-ups are typed "unknown" |
| `tests/test_cases.py` | 17/17 (old cases unchanged; the gaps reproduce exactly from the masks) |
| `tests/test_user_recording.py` | 4/4: v0.4.0's records exactly; match 2 Partial though fully observed; active time +132 s (match 1) and +62 s (match 2) over the truth |
| Match records (live pipeline) | match 1: Partial, 0.0-484.0 s, left_or_unknown, 469 s active; match 2: Partial, 489.0-1478.5 s, stopped, 974 s active. Identical to the audit's run |

### Detector time and CPU (v0.4.0, main PC)

`research/pipeline_baseline.py`, one clip after another, none of this work running beside them. **Not an idle PC:** the packaged v0.4.0 app was
analysing a live desktop capture (15 fps) on the same PC throughout, so these are working figures under that load; before/after
comparisons use alternating pairs, and the gate re-measures on an idle PC. Detector time is `ChestEstimator.process_frame` alone (the FFmpeg decoder runs in
its own process); CPU is this process's, per second of video.

| Clip | Frames | Mean ms/frame | p50 | p95 | p99 | Max | CPU s per video s |
|---|---:|---:|---:|---:|---:|---:|---:|
| en (whole, 509 s) | 7,630 | 6.2 | 4.4 | 22.9 | 29.0 | 41.6 | 0.42 |
| ps5 (first 600 s) | 9,000 | 6.5 | 2.8 | 22.4 | 31.6 | 43.5 | 0.43 |
| user1112 (whole, 1,479 s) | 22,179 | **15.7** | 12.7 | 39.9 | 61.6 | 72.1 | 0.61 |

The maintainer's footage costs 2.5 times the references. Cause, from the audit's instrumented replay of 1200-1230 s: the purple storm
passes the 60 px lavender prefilter on most frames (87% there), and each such frame runs the multi-scale blurred search (13 ms) and the
small-HUD search, because the scale never locks (the pop-ups' blurred 0.80-0.86 rarely reaches the 0.84 vote). A selected native template
would replace that search, so v0.4.1 should lower this cost, not add to it. Under load (three runs in parallel) the same clip measured
19.7 ms, so comparisons use alternating pairs.

Reproducibility: the clean run's chest events are byte-identical to `tests/baselines/user1112_v0.4.0.json`, and en's are identical to the
regress snapshot made by `research/regress.py`.

### Isolation

Size and modification time of the 83 files in the repository's `state/`, `logs/`, `obs_output/` and every installed version's `state/` and
`logs/` under Downloads, taken before the first run and after the last. 79 unchanged. The 4 that changed (a session log, the Replays
profile and its chest and match history in the installed v0.4.0) belong to the packaged app's own live session: desktop capture on profile
"Replays" started at 22:39:59, before the first fingerprint, ending with a manual +1 correction at 23:59:01. Nothing in this work writes
there: every run used its own temporary folder.

### Test suites

All 33 suites pass, 1,433 checks (v0.4.0: 32 suites, 1,428), run one after another (the packaged app's live session was running). New: `test_user_recording`
(4) and `test_v041_gaps_reproduce_exactly_until_fixed` in `test_cases` (17). `test_obs`'s known flaky check passed this time.

## M1 — HUD calibration research

### M1a — existing footage (`research/hud_calibration.py`, `research/hud_cue_calibration.py`)

Every native CHEST template we have, on every labelled footage family. Cells: exact median, share of chests with exact >= 0.75 (the
trigger), blurred median, share with blurred >= 0.88 (the CERTAIN promotion line). A template is never scored on the pop-up it was cut from.

| Footage (pop-up size, source) | 1.00 reference | 0.95 maintainer | 0.78 Thiefs | synthetic 0.95 (shrunk 1.00) |
|---|---|---|---|---|
| reference 1.00, 720p x264 (6 chests) | **0.87, 100%, 0.96, 100%** | 0.60, 0%, 0.85, 0% | 0.38, 0%, 0.72, 0% | 0.55, 0%, 0.71, 0% |
| Replays 1.00, stream captures (7) | **0.76, 71%, 0.90, 71%** | 0.56, 0%, 0.82, 0% | 0.34, 0%, 0.65, 0% | 0.61, 0%, 0.74, 0% |
| Thiefs 0.78, OBS camera (2) | 0.31, 0%, 0.42, 0% | 0.34, 0%, 0.59, 0% | **0.95, 100%, 0.99, 100%** | 0.31, 0%, 0.53, 0% |
| Thiefs 0.78, 1080p browser (3) | 0.29, 0%, 0.41, 0% | 0.30, 0%, 0.46, 0% | **0.88, 100%, 0.96, 100%** | 0.31, 0%, 0.48, 0% |
| Thiefs 0.78, 720p stream (3) | 0.29, 0%, 0.42, 0% | 0.29, 0%, 0.55, 0% | **0.72, 0%, 0.92, 100%** | 0.31, 0%, 0.49, 0% |
| maintainer 0.95, 720p NVENC (18) | 0.53, 0%, 0.83, 0% | **0.80, 82%, 0.94, 94%** | 0.36, 0%, 0.65, 0% | 0.49, 0%, 0.77, 0% |

Highest score on any non-chest frame (exact / blurred):

| Non-chest footage | 1.00 reference | 0.95 maintainer | 0.78 Thiefs | synthetic 0.95 |
|---|---|---|---|---|
| reference video, away from its chests | 0.65 / 0.80 | 0.48 / 0.78 | 0.45 / 0.76 | 0.49 / 0.73 |
| PS5, Portuguese combat text, every frame | 0.35 / 0.62 | 0.45 / 0.77 | 0.59 / 0.84 | 0.38 / 0.72 |
| maintainer recording, away from its chests | 0.52 / 0.74 | 0.59 / 0.81 | 0.48 / 0.82 | 0.53 / 0.76 |

Match text at the maintainer's size (one waiting island and one death screen exist, so "on screen" is within the session the template was
cut from; "elsewhere" is every other sample of the three videos):

| Signal | Native 0.90 (cut) | Production 1.0 | Production 0.78 | Native: highest elsewhere |
|---|---:|---:|---:|---:|
| WAITING FOR PLAYERS | 0.99 | 0.29 | 0.30 | 0.22 |
| LAUNCHING IN | 1.00 | 0.23 | 0.26 | 0.27 |
| YOU PLACED | 0.98 | 0.25 | - | 0.49 |

Exact match over the whole pop-up box: 2.0 ms per template on the main PC.

**What this establishes**

1. **A native template does not carry across a 5% size step** at the detector's 1280x720 working size, where the word is 7 px high.
   0.95 on 1.00 footage and 1.00 on 0.95 footage both stay under the exact trigger on every chest. Match text 10% off scores like text
   20% off (0.23-0.30).
2. **Blurred matching tolerates about 5%** (0.81-0.85): over the 0.80 APPROX trigger, under the 0.88 CERTAIN line, and with margins of
   0.01-0.05. That thin margin is the maintainer's 3 low-margin misses.
3. **Synthesis is rejected at every offset tested.** Shrinking the 1.00 word by 5% scores worse on real 0.95 pop-ups (0.49) than the
   unchanged 1.00 word (0.53); at 0.8x it failed on 2026-11-12.
4. **The source moves exact scores by 0.1-0.2 at the same size** (Thiefs' 0.78 word: 0.95 on its own OBS source, 0.88 on a 1080p browser,
   0.72 on a 720p stream; the 1.00 word: 0.87 on the reference, 0.76 on Replays' stream captures). Blurred scores stay at 0.90-0.99. Native
   templates therefore need validating per source quality, and CERTAIN at a given size depends on the input.
5. **Element families scale differently:** the maintainer's pop-up is 0.95x and HUD text 0.90x; Thiefs' are about 0.80x and 0.78x. A
   single "HUD scale" number cannot select every template.
6. **One pop-up is a weak template source:** the two cuts from the maintainer's footage reach the trigger on 82% and 65% of the other
   pop-ups. Templates should be built from several confirmed pop-ups.
7. **False alarms stay low at native size:** the maintainer's template never passes 0.59 exact on any non-chest frame of the three videos.
8. **Cost forbids scanning a bank:** 2 ms per template per frame, so the size must be selected (setting or locked evidence), never
   searched over every frame.

### What M1a cannot answer

How many distinct rendered sizes Fortnite's HUD Scale slider produces for each element family, and how the slider value maps to the pop-up
and text sizes. The three sizes above come from three different players and sources, so they say nothing about slider steps. That needs
the calibration footage below (M1b).

### Candidate architectures for the gate (to be decided on M1b's evidence)

| Option | How a player's size gets native templates | Maintenance | Main risk |
|---|---|---|---|
| A. Template bank | the maintainer records every supported slider value once | grows with every value and every Fortnite font change | values nobody recorded fall back to APPROX |
| B. In-app calibration | the app cuts templates from 3-6 chests the player confirms, validated before use (must match the other confirmed pop-ups and stay low on the session's non-chest frames) | none per size | a bad cut; needs strict validation and a way back |
| C. Hybrid | a bank for the common values (100% and the most used), calibration for the rest | small | both of the above, smaller |

M1b's footage answers which is needed: if several slider values render the same word, a small bank (A or C) is enough; if every value
differs, B avoids an ever-growing bank. The single cuts above (65-82% of held-out pop-ups over the trigger, no false alarms) are the first
evidence that B can work; templates built from several pop-ups have to be measured.

### M1b calibration recording protocol

**Before recording, tell me three facts** (a screenshot of the setting is enough): your Fortnite **HUD Scale** value, the slider's lowest
and highest value, and its step (what one click or arrow press changes). The plan below assumes 5% steps; it shrinks if the slider is coarser.

**OBS (main PC, not the SRT feed):** record the game at its own resolution, 1920x1080, 60 fps, NVENC **CQP 18**, no output rescaling,
MKV (remux to MP4 afterwards). Expected size: about 3-6 GB per 15 minutes. Keep overlays (the counter's own text included) away from the
centre-right of the screen and the top centre.

**Label every change on camera:** after changing HUD Scale, keep the settings page with the value visible for 2 seconds, then return to
the game. The recording then documents itself; no notes needed.

**Values:** your normal value, 100%, and every step between them, plus the two steps below yours (for example 80, 85, 90, 95, 100 if you
play at 90). One step above 100 if the slider has it.

**Per value (one recording can cover several values; change HUD Scale between chests):**
1. **Six separate chests**, waiting until the previous pop-up is gone (about 3 s) before opening the next. A rare chest if one is
   near. If it happens naturally, open one while another XP line is still on screen (a stacked pop-up).
2. Nothing else needed for chests: three are used to cut templates, the other three are held out to test them.

**Match text (start a match at the value; the countdown and the end cannot be changed mid-match):**
- Your normal value: **two full matches**, waiting island to the end screen, one ending with READY (ready up) and one with RETURN TO
  LOBBY.
- 100% and your lowest recorded value: **one full match each** (waiting island, bus countdown, and the end screen, whatever it is).

**Held back for acceptance (record, do not send yet):** one more session at your normal value on another day, and 10 minutes of the same
game received on PC B over SRT, captured by the app's capture tool in lossless mode.

**Total:** 4 full matches plus about 36 chests, roughly 60-90 minutes of play, about 15-30 GB of footage. Keep the files in
`samples/video tests/` (not in Git); I will cut only short labelled windows into cases, as with the existing ones.
