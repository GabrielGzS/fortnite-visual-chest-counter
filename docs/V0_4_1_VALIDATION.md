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
   single "HUD scale" number cannot select every template. *Revised 2026-11-13:* the two sizes are relative to templates from different
   streamers (match text: Replays, 82%; chest word: a streamer at about 79%). With the confirmed 75% both fit one rule, size proportional
   to the slider (M1b section below). That is a hypothesis for M1b, not yet a finding.
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

### M1b — confirmed settings and the refined calibration experiment (2026-11-13)

**Confirmed facts**

| | Value | Source |
|---|---|---|
| Maintainer's Fortnite HUD Scale | **75%** | read in Fortnite (Game UI, HUD Options), and `HUDScale = 0.75` in `%LOCALAPPDATA%\FortniteGame\Saved\Config\ClientSettings.Sav` |
| Maintainer's game resolution | 2560x1440, resolution quality 100%, no dynamic resolution | `GameUserSettings.ini` |
| The audit recording | 1280x720, 30 fps, NVENC 4 Mbps: the 1440p game through a 1080p canvas | the file itself, the OBS profile |
| Replays' HUD Scale | **82%** | the maintainer |
| Thiefs' HUD Scale | unknown (predicted about 64%, below) | |

**Can the app read the HUD Scale itself?** Yes, on the gaming PC: `GameUserSettings.ini` does not hold it, but the binary
`Config\ClientSettings.Sav` (Unreal save format) has a `HUDScale` float property, 0.75 here, read without opening anything for writing. It
is undocumented and may change, so it can only ever suggest a value (M2's Auto). The maintainer's app runs on PC B, which cannot see the
gaming PC's files, so two-PC setups still need the value entered.

**A model the numbers fit (hypothesis for M1b to test).** The countdown templates were cut from Replays' stream (82%). The maintainer's
countdown measured 0.90-0.91x of them, and 75/82 = 0.915. If every element scales with the slider, the chest template's source streamer
(Fortnites-NEW) played at about 75/0.95 = 79%; Replays' pop-ups are then 4% larger than the chest template, which fits their borderline exact
scores (0.73-0.78). Thiefs' countdown (0.78x) and pop-up (0.80x) both put Thiefs at about 64%. If it holds, rendered size is simply
proportional to the slider for every element family, and the open question becomes how finely templates must be spaced, and whether one
high-resolution master can produce them. Shrinking a 720p raster failed (M1a), but the maintainer's real pipeline downscales a 1440p render
to 720p, which a 1440p master reproduces far more closely; that is the key test.

**What M1b must separate:** the HUD slider, the capture downscaling (OBS's scaler from 1440p, or the app's FFmpeg scaler from a 1080p/1440p
input), and the stream encoding. So the same play is recorded twice at once: the game at full 1440p locally, and the 720p SRT feed exactly
as the app on PC B receives it.

### The maintainer's capture pipeline (OBS profile, read 2026-11-13)

| OBS setting | Value |
|---|---|
| Canvas (base) | 1920x1080 |
| Output (scaled) | 1280x720, bicubic |
| Frame rate | 30 fps |
| Stream encoder (the SRT feed to PC B) | NVENC H.264, CBR 4,000 kbps, no extra rescale |
| Recording | NVENC, no rescale (so 720p), about 4 Mbps in the audit file |

So the game reaches PC B through two downscales: 2560x1440 to the 1920x1080 canvas (scene scaling), then to 1280x720 (bicubic). The audit
recording has the same output, frame rate, encoder and bitrate as the SRT feed, so its measurements describe the live counter, apart from
network loss. The SRT feed carries about 0.145 bits per pixel (4 Mbps / 1280x720 / 30 fps), about three times Twitch's 1080p60 at 6 Mbps
(0.048): 720p at this quality is a mainstream input, not an edge case. The edge case seen in M9H was a heavily compressed YouTube 720p
stream. Re-encoding the reference at these exact settings changed its scores very little (M1a); the size mismatch is what broke matching.

HUD Scale slider: **25% to 125%** (the maintainer); step not yet confirmed.

### M1b recording checklist (replaces the earlier protocol)

**Do not change** Settings > Video (canvas, output, 30 fps, bicubic): those settings make the pixels PC B receives, and changing them
would change what is being measured.

**Setup for every session:**
- Stream to PC B over SRT as usual. On PC B, record that input with the app's capture tool in **lossless** mode: the exact pixels the
  counter sees.
- Local OBS recording of the canvas: Settings > Output > Recording: Rescale Output **1920x1080** (OBS cannot record beyond its canvas),
  NVENC, rate control **CQP 18**, MKV (remux to MP4 afterwards). About 2-4 GB per 10 minutes. This sharper copy of the same moments is
  for research only: it lets M1b separate the HUD slider from the downscaling.
- Keep overlays away from the centre-right of the screen and the top centre. When you change HUD Scale, keep the settings page with the
  value on screen for 2 seconds.

**Pilot first (about 5 minutes, at 75%).** Start a match and record from the waiting island: the countdown, the bus, landing, and 4-6
chests. Afterwards, check OBS's stats for dropped or lagged frames (encoding two streams at once), and send me both files. I check that
they line up in time, have the expected resolutions, and that native 75% templates cut from the PC B capture work on the rest of it.
Only then the three sessions below.

**Session A: template source, 75% (one match).** The waiting island with its countdown and the bus launch; at least 6 separate chests
(wait until the previous pop-up is gone), a rare chest if one is near, one opened while another XP line is on screen if it happens
naturally; the end screen, whatever it is; ready up from it (READY overlay).

**Session B: held-out validation, 75% (another match, another time).** The same contents, but end with RETURN TO LOBBY. Nothing is cut
from it; it only judges what A produced.

**Session C: the slider sweep (one match).** On the waiting island, step HUD Scale through 25, 50, 65, 70, 75, 80, 82, 85, 90, 100 and 125
(5 seconds of countdown at each, shown on camera). In the match, open 2 chests each at 65, 75, 82 and 100 (70 and 80 too if chests are
easy to find); if the slider moves in 1% steps, also 2 chests each at 74 and 76.

**Not needed:** Thiefs' value (the 64% estimate stays a prediction), other players, Creative, Portuguese. **Total after the pilot:** 3
matches, roughly 35-45 minutes of play, 10-15 GB of local recordings plus the PC B captures. Everything stays in `samples/video tests/`
(not in Git); only short labelled windows become cases.

## M4 (first batch) — HUD-independent fixes

Approved 2026-11-13 ahead of the architecture gate, one validated commit each. None of them changes a threshold that decides CERTAIN, and
none depends on the HUD size.

| Commit | Fix | Evidence | Result |
|---|---|---|---|
| A `d18b4c3` | A pop-up covered for a moment counts once, on every English channel (`estimator.PopupMemory`: where the word was last seen; same word, same place, within 2 s of the onset) | Real: the maintainer's inventory duplicate. Synthetic: real case fixtures with the pop-up box blanked 0.4 / 0.75 / 1.0 s (`research/occlusion_check.py`) | duplicates 11 / 10 / 9 -> 1 / 1 / 1; found 32 / 32 / 27 -> 34 / 35 / 33 of 37; uncovered footage identical |
| B `55a6522` | The console and event reason say what was measured: a blurred match at x1.0 is "near-normal pop-up, shape not exact", not "drawn larger" | every chest on the maintainer's footage was described as larger, the opposite of the truth | same line length as the other scaled lines |
| C `7278771` | One strong sample (>= 0.85) confirms ELIMINATED BY while a match is in play | on screen 0.86-0.99 in every recording; elsewhere at most 0.17 over ~4,000 samples; the maintainer's was readable for 1.4 s | play stops at the death screen |
| D `aecd1ac` | Grey CONNECTING on the white return-to-lobby splash (a shadow-ink template) and the READY overlay ("PARTY TO READY UP...", "NEXT MATCH") as "the player's part is over" | splash 0.97-1.00, elsewhere <= 0.20 over 6,022 samples (one splash: within the session); READY lines cut from different matches, each held out on the other (0.88-1.00), elsewhere <= 0.14 over 5,782 samples | match 2 closes at 1465 s instead of when the video stopped; the overlay is no longer play |

**The maintainer's recording, end to end** (`tests/test_user_recording.py`, observations regenerated from the real pipeline):

| | v0.4.0 | Now | True |
|---|---:|---:|---:|
| Chests found / duplicates / false | 16 / 1 / 0 of 20 | 16 / 0 / 0 | 20 |
| Match 1 active play | 469 s | 377 s | 337 s (rebooted at 24 s, Victory at 361 s) |
| Match 2 active play | 974 s | 945 s | 912 s (bus at 520 s, death at 1432 s) |
| Match 2 closed | 1478.5 s, video stopped | 1465 s, grey CONNECTING | lobby at ~1466 s |
| Fully observed matches Complete | 0 of 1 | 0 of 1 | 1 |

What remains is HUD-dependent and waits for the gate: the 0.90x countdown (the island is still counted as play and match 2 cannot be
Complete), YOU PLACED and Victory at the maintainer's size, CERTAIN, the 3 low-margin and stacked misses, and RARE typing.

**Regression:** `regress.py compare --tag v0.4.0`: en and PS5 identical decisions; user1112 found 16 -> 16, duplicates 1 -> 0, false 0,
CERTAIN 0 -> 0 (regress now judges a fully labelled clip by its scorecard: a removed duplicate is not a lost chest). Cases 19/19.
Match suites: match_state 123, defects 26, replay 39, tracker 68, live 88, recording 50, cues 36, user recording 4. The tracker's HUD-check
budget test failed once and passed on four reruns: a wall-clock check, with the packaged app capturing live on the same PC. Mutations: match state 36/36, tracker 43/43, live match 59/59, replay 14/14, recording 37/37 caught.

**Full suite after the batch (on `aecd1ac`):** 33 of 33 suites run, 1,441 of 1,442 checks pass. The one failure,
`test_analytics_ui` `test_days_and_weeks_tell_counted_from_not_counted`, is pre-existing and depends on the clock: on untouched v0.4.0
(`fa1747d`) at the same time (Friday 01:42) it fails too, together with `test_personal_bests_show_their_evidence_or_what_they_need`;
both passed during M0 the previous evening. Analytics is not touched by v0.4.1; the test needs a fixed clock (reported, not fixed here).
That runner also exits 0 on a failed check, so only its summary line shows it.

**Packaging caught:** the release copies templates from an explicit list (`packaging/build_release.py` TEMPLATE_FILES), so the new
templates would have been left out of the package and match tracking would have stopped there. They are added, and
`test_every_template_ships_in_the_release` now guards every cue.

**Occlusion limits (documented, not fixed):** a line change hidden by the overlay (a non-chest line pushing the word up one line, or an X2
appearing just as the pop-up returns) can still give one duplicate or one missed step. Carrying the tracker's state across the gap would
fix it; not attempted in this batch.

**RARE typing (investigated, HUD-dependent):** the scale-free length test reads RARE on the maintainer's pop-ups (0.78-0.81 of the CHEST
word), but the exact 1.0x RARE template confirms at 0.22-0.36 against its 0.50 line. A blurred confirmation was rejected in v0.2.2 (random
ink 0.65) and the line is not lowered, so RARE typing comes with the native templates (M3). Types never change counts.

## Targeted 75% HUD hotfix (revised authorization, 2026-11-13)

Scope: an opt-in, per-profile **Fortnite HUD Scale 75%** setting with native templates cut from the maintainer's labelled recording;
Standard unchanged and the default. Closed by the maintainer the same day: 19/20 with 0 false is accepted; the CROWN BONUS line miss and
match 1's +27 s are not pursued in v0.4.1; no further benchmarking. **Every 75% figure below comes from the recording the templates were
cut from, so it is not independent validation.** The maintainer's live test is.

| Commit | What |
|---|---|
| `2b4dd5e` | tests: the Analytics checks no longer depend on the time of day (the clock-dependent failure reported above; separate, test-only) |
| `4f52b2d` | 75% CHEST (consensus of 18 pop-ups) and RARE templates; `estimator.HUD`; the native-profile gate on blurred-only pop-ups |
| `a81c250` | 75% countdown, bus, YOU PLACED (screen and bar) and Victory templates, read only for a 75% profile |
| `e94ca82` | `[detector] hud`, a HUD Scale per profile, the Settings card, `--hud` |
| `126f493` | 75% observations fixture; case `user_storm_phase_popup`; `pipeline_baseline.py --hud` and `types.json` |

**Templates** (`research/hud75_templates.py`): CHEST leave-one-out exact 0.71-0.94 (median 0.84), 17 of 18 CERTAIN by today's rules;
a consensus of match 1 scored on match 2's pop-ups 11 of 13. Highest on non-chest frames (the recording, en, PS5, the cases): 0.61 exact /
0.82 blurred. Match text on screen 0.98-1.00, elsewhere <= 0.27 (Victory 0.43 on the reference's own Victory).

**The native-profile gate.** The first full run at 75% found 20/20 with 4 false counts: blurred-only onsets of non-chest pop-ups
(blurred 0.804-0.824, native exact 0.43-0.55). With a native template a pop-up found only by the blurred channel must also reach
blurred 0.85 and native exact 0.60 (stricter than Standard, never looser). That removes the 4 and gives up one real chest: a CHEST
line added to a CROWN BONUS pop-up (0.812 / 0.52), which these scores cannot tell apart. `user_storm_phase_popup` fails without the gate.

**Full pipeline on the recording** (`research/pipeline_baseline.py`, two identical runs):

| | v0.4.0 | v0.4.1 Standard | v0.4.1 75% | True |
|---|---:|---:|---:|---:|
| Found / duplicates / false (of 20) | 16 / 1 / 0 | 16 / 0 / 0 | **19 / 0 / 0** | 20 |
| CERTAIN | 0 | 0 | **18** | |
| Types | RARE unknown | RARE unknown | 16 CHEST, 2 RARE, 1 unknown (RARE line on CROWN BONUS), none wrong | 16 CHEST, 3 RARE |
| Match 1 | Partial, 469 s | Partial, 377 s | Partial, ended by Victory, 364 s | 337 s (reboot wait at 0-24 s) |
| Match 2 | Partial, 974 s | Partial, 945 s | **Complete, YOU PLACED, 913 s** | Complete, 912.3 s |
| Detector ms/frame (mean) | 15.7 | not re-measured | 7.9 (run alone) | |

Match 1's +27 s is the wait for a reboot before the recording's first second of play, which the v0.3.0 rule counts (a design question,
not a detector miss).

**Standard is unchanged:** `regress.py compare --tag v0.4.0 --clips en ps5 user1112`: en and PS5 identical decisions; user1112 16 -> 16
found, duplicates 1 -> 0, false 0, CERTAIN 0. `test_hud_75_changes_nothing_on_the_standard_profile`.

**Checks run** (only what the change touches, per the closing decision): test_cases 21, test_match_cues 39, test_match_tracker 68,
test_user_recording 6, test_profiles 12, test_types 9, test_basics 6, test_app 30, test_analytics_ui 12; packaging below. Not run: the
full 33-suite pass, mutation runs, the occlusion check at 75%, Standard timing (cancelled), the en clip at 75%.

**Known limits of 75%:** made from one recording of one player (2560x1440 through OBS 1280x720, 4 Mbps SRT); other resolutions at 75%
untested; a chest line added to a CROWN BONUS pop-up is missed; a RARE line added to another pop-up stays "unknown"; no SPRITE template at
75% (sprite chests "unknown"); Portuguese at 75% uses the standard BAÚ template; a 75% profile on a different HUD is untested.
