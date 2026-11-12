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
