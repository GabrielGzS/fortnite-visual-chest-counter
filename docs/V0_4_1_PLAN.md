# v0.4.1 — HUD Compatibility & Detection Reliability (plan)

Planning document, 2026-11-12. Base: the v0.4.0 release (tag `v0.4.0`, commit `fa1747d`), branch `dev/v0.4.1`. Evidence: the
v0.4.1 Detection Reliability Audit (claude.ai doc, 2026-11-12) and the maintainer's recording `samples/video tests/2026-11-12 12-52-32.mp4`,
labelled in `tests/cases/user_20261112.json`. Results of each milestone go to [V0_4_1_VALIDATION.md](V0_4_1_VALIDATION.md).

**Status: development authorized 2026-11-12 for M0 and M1; stop at the architecture gate (section 4) before M2.** Each milestone:
implement, test what changed, commit locally, record results, then stop for review where this plan says so. Nothing is pushed, tagged,
signed, built for release or published without explicit approval.

## 1. Goals

1. **HUD compatibility is a feature, not a patch.** The maintainer cannot use the app properly with their own Fortnite HUD: on their footage
   every chest is APPROX, 4 of 20 are missed, 1 is counted twice, and a fully observed match is Partial. Fix the architecture so supported
   HUD configurations work for every player, not one more size added by hand.
2. **Keep CERTAIN meaningful.** No threshold is lowered to raise CERTAIN. A native-size match goes through the same evidence rules as the
   normal-HUD word, and each size is admitted only with measured false-alarm margins.
3. **Correct match boundaries and durations.** Complete/Partial must follow what was observed, and active time must stop when participation
   ends (post-match screens, the waiting island and time after death were counted as play). Duration accuracy is a first-class objective,
   because Analytics' rates depend on it.
4. **Stay cheap.** Ordinary Windows PCs, over OBS and SRT inputs: no unbounded multi-scale search on every frame.

### Not in v0.4.1

- Treasure recognition and predictions (v0.5.0).
- Machine learning, cloud services or new major dependencies, unless experiments show the template approach cannot work (approval needed).
- Any change to the updater, update-manifest format, production Ed25519 signing, release assets, OBS text-output contracts or persistent
  count semantics.
- Lowering detection thresholds globally.

## 2. Baseline (v0.4.0 on the maintainer's recording)

| Measure | v0.4.0 | Target |
|---|---:|---:|
| Real chests | 20 | |
| Found | 16 (80%) | >= 95% on held-out footage |
| Duplicates | 1 (inventory panel hid a pop-up) | 0 |
| Missed | 4 (2 single pop-ups at low margin, 2 chest lines added to CROWN BONUS pop-ups) | |
| CERTAIN | 0 | follows the evidence; no forced value |
| Fully observed matches marked Complete | 0 of 1 | all |
| Active time, match 2 | 974 s detector vs about 912 s true (bus to death) | within a few seconds |

Measured causes (audit): the XP pop-up is drawn 0.95x and HUD text 0.90x of the reference; templates exist only for 1.0x and 0.78x; the
exact glyph match is lost at a 5% size difference; resampling raster templates does not reproduce Fortnite's smaller text; several match
cues fail for position, colour or 1 Hz sampling, not scale. Readying up without the lobby works.

## 3. Rules for every milestone

- **Isolation.** Research and tests never touch real profiles, counts or history: `research/regress.py`, `research/cases.py` and
  `research/pipeline_baseline.py` run in temporary folders with an explicit state file; a size-and-time fingerprint of the user data folders
  is compared before and after each long run.
- **Regression gate for detector changes.** `research/regress.py compare --tag v0.4.0 --clips en ps5 user1112` (the user clip is scored
  against its labels: found, duplicates, false, CERTAIN may not get worse), `tests/test_cases.py` (17 checks; the six v0.4.1 gaps are
  pinned exactly and are removed one by one as fixes land), and the match tests. Reference clips must give identical events unless a
  reviewed change intends otherwise.
- **Performance.** Detector time per frame is measured with `research/pipeline_baseline.py` on the same clips, compared in alternating
  pairs when anything else is running. Budget: at most +2 ms average per frame over v0.4.0; match sampling within its 10 ms budget.
- **Evidence over assumptions.** Rejected experiments are written down, not integrated.

## 4. Milestones

### M0 — Baseline and reproducible failures
Labels for the 20 chests, 10 non-chest pop-ups, both matches, screens and active-time truth (`tests/cases/user_20261112.json`). Six cases
with pinned gaps (`tests/cases/cases.json`, fixtures in `tests/fixtures/popups/`). The recording as a labelled regress clip (`user1112`).
v0.4.0 snapshots for `en`, `ps5`, `user1112` in `tests/baselines/`. Match observations as fed to the state machine, with a test that pins
v0.4.0's two Partial records against the truth. Baseline detector timing and CPU. Full test suites.

### M1 — HUD calibration research
**M1a (existing footage, now):** cross-score native templates from every available size (1.0x reference, 0.78x Thiefs at 720p and 1080p,
0.95x maintainer) on every footage family; measure how far a native template can be from the true size before exact and blurred matches
fail; test whether synthesis from a master works for small offsets (it failed at 0.8x); separate the effect of source resolution from HUD
scale; positions of each element family; cost per template.
**M1b (calibration footage, needs recordings):** the same measurements across the HUD Scale slider from one game, to learn how many
genuinely distinct template variants exist per element family. Protocol in V0_4_1_VALIDATION.md.

### Architecture review gate (stop)
Present: the calibration model; which slider values share templates; which need native variants; how the variant is chosen (setting,
Auto evidence, fallback); compatibility for existing users and profiles; CPU and memory cost; held-out evidence. No production
implementation of the profile system before approval.

### M2 — HUD Scale profile system
Per-profile HUD configuration (GUI and config), unknown configurations fall back to today's channels, calibration logged for diagnostics,
shadow mode first.

### M3 — Scale-aware chest and match recognition
Chest word and chest types, stacked lines where supported, countdown, YOU PLACED, Victory, HUD-in-view, supporting cues where calibration
exists; today's tier rules at every supported size. Full regression after.

### M4 — Targeted correctness fixes
Same-pop-up rule for every pop-up channel; chest lines added to non-chest pop-ups; short end screens (ELIMINATED BY: faster sampling vs
event-specific rules); SPECTATING and the lobby bar at varying positions; grey CONNECTING; the READY / FINDING NEXT MATCH overlay as
"participation over"; correct console wording.

### M5 — Validation and release candidate
Reference videos, the maintainer's recording, held-out footage at every supported configuration, English and Portuguese, match
completeness and active time, 15 fps throughput, match budget, automated and mutation tests, a real SRT test, persistence/OBS/Analytics
unchanged except where corrected detection legitimately changes results. No release preparation, signing or publication without approval.

**README HUD compatibility matrix (M5).** A dedicated section of the project README.md (the repository page people hand to their AI
assistant; not the release notes or the quick start): one structured table, a row per tested combination of HUD Scale, game resolution and
the resolution the app receives, with chest detection, CERTAIN, chest types and match tracking, each **Verified** (end-to-end tested on
held-out footage), **Partial** or **Untested**, plus known limits and what diagnostics to collect when recognition fails. It also says
that the HUD Scale percentage and the detector's measured sizes are different things. Only end-to-end tested combinations are Verified;
untested slider values are never advertised as compatible.

**Compatibility contracts.** Every Verified row becomes a permanent regression gate, like the English, PS5, Replays and Thiefs footage
today: no later change (v0.4.2, v0.5.0) may break it without that showing in the cases and the full-video regression.

## 5. Acceptance goals (targets, not guarantees)

| Goal | Target |
|---|---|
| Recall on independently labelled footage at supported HUD configurations | >= 95% |
| False positives and duplicates in validation cases | 0 |
| Fully observed matches classified Complete when their evidence is visible | all |
| Reference videos | no unintended change |
| Detector time | at most +2 ms per frame on average over v0.4.0 |

## 6. Decisions

| Date | Decision |
|---|---|
| 2026-11-12 | v0.4.1 opened from tag v0.4.0; M0 and M1 authorized; architecture gate before M2 (maintainer, after the audit). |
| 2026-11-12 | Do not commit to a full per-slider-value template bank before M1 shows how many variants are genuinely distinct. |
| 2026-11-12 | The 720p recording stays a permanent regression fixture; calibration footage is recorded at 1080p60, CQP 18, from the main PC. |
| 2026-11-12 | Self-service HUD calibration is a high-priority backlog item (section 7.1); v0.4.1's HUD profile must be able to take validated user templates later. |
| 2026-11-12 | Spectator recognition and adaptive processing are a research proposal (section 7.2), not a state-machine rewrite; investigate during v0.4.1 if time allows. |

| 2026-11-13 | M1 split into M1a (existing footage, done) and M1b (calibration footage); the architecture gate stays before M2 (maintainer). |
| 2026-11-13 | HUD-independent fixes approved ahead of the gate, as small separately validated commits: duplicates after an overlay, short end screens, grey CONNECTING, the READY overlay, console wording, and a look at RARE typing. Backlog decisions confirmed. First supported intermediate configuration at the gate: the maintainer's own HUD. |
| 2026-11-13 | RARE typing on the maintainer's footage is HUD-dependent (the scale-free length test reads RARE, 0.78-0.81; the exact 1.0x RARE template confirms at 0.22-0.36 against 0.50), so it moves to M3 with the native templates. Lowering the word threshold or a blurred confirmation stays rejected (random ink reached 0.65, v0.2.2). |
| 2026-11-13 | Confirmed: the maintainer plays at HUD Scale 75%, 2560x1440; Replays at 82%; Thiefs unknown. Ordinary HUD Scale values are the app's compatibility responsibility: a player never has to change a comfortable HUD to use the counter. M1b refined to three matches (75% source, 75% held-out, a slider sweep), each recorded at 1440p and as the 720p SRT feed (V0_4_1_VALIDATION.md). |
| 2026-11-13 | README HUD compatibility matrix (M5 deliverable): see section 4, M5. |

## 7. Backlog and research proposals (not v0.4.1 scope)

Recorded 2026-11-12 at the maintainer's request. Neither is authorized for implementation; both shape v0.4.1's design.

### 7.1 Self-service HUD calibration — high-priority backlog

If every HUD Scale value needs the maintainer to record footage, cut templates and ship an update, support cannot keep up, and players with
other settings stay on APPROX or change their HUD. Possible flow:

1. **Notice** an unsupported HUD: pop-ups keep matching only the fallback (scale-aware / small) channels, never a native template.
2. **Offer guided calibration:** the player opens several chests while the app keeps the candidate pop-up frames.
3. **The player confirms** which ones were chests, so the app never learns from its own false positives.
4. **Validate** the personal template: it must match the other confirmed openings and stay quiet on the session's non-chest frames
   (M1a: single cuts reached the trigger on 65-82% of held-out pop-ups with no false alarm; templates from several pop-ups not yet measured).
5. **Save it per profile**, with reuse, reset and replace.

**Requirement on v0.4.1 now:** the HUD profile must hold templates as data with a provenance (built-in, or validated user calibration) so
user-made templates can be added later without a rewrite.

**Match cues are the harder half.** M1a shows element families scale by different factors (the maintainer's pop-up 0.95x, HUD text
0.90x), so match templates cannot be derived from a chest calibration. They appear once per match (the countdown) or once per ending, so
calibration would have to capture them as they happen (for example "start a match now" for the countdown, a confirmation for an end
screen) and validate each against the session's other frames.

### 7.2 Spectator recognition and adaptive processing — research proposal

The maintainer observes that spectator mode changes the HUD: the compass area gives way to SPECTATING and the player's name. The recording
shows two layouts: spectating a teammate in squads (0-10 s: large SPECTATING / ZSARTH at the top centre, "WAITING TO BE REBOOTED", the
reboot timer) and spectating after death (1438-1458 s: a small right-aligned SPECTATING: CAPALOT2U bar at the top right).

Questions to research:
- Can the app tell apart active play, spectating a teammate, a reboot and return to play, post-match overlays, and loading or uncertain
  states, with corroborated signals and temporal stability?
- **Adaptive processing:** while spectating is firmly established, pause the 15 fps chest search and sample the lightweight match signals
  faster (for example 3-5 per second) to catch a reboot or the match end, keeping total cost at or below normal play.

Constraints:
- A missing compass is never proof of spectating (loading screens, inventories, overlays and hidden HUDs lack it too). Only positive,
  repeated evidence can pause chest detection; on ambiguous evidence it keeps running, and it resumes before a transition could lose a chest.
- **Return to play needs positive evidence of the player's own play** (SPECTATING gone, the own HUD back, PROCESSING REBOOT or the
  redeploy). v0.3.0 keeps a match non-active after an elimination because a health bar alone cannot tell a reboot from spectating, and
  Codex's M2 correction removed the HUD-only recovery on purpose. Explicit spectating evidence would be new information, not that
  heuristic back; the research must show it is reliable before the rule changes. In this recording the rule would have discarded the
  337 s the maintainer played after the reboot.
- **Ownership is a product decision:** a chest a teammate opens while the player spectates should not count as the player's (assumed;
  to confirm), and whether the spectated player's XP pop-ups even appear on screen has not been checked.

## 8. Risks

- One player's footage: every supported configuration needs held-out sessions before it ships.
- Source resolution also changes the raster (720p vs 1080p differed by about 0.1 on the same 0.78x HUD), so a "family" may have to be
  per HUD size and resolution class.
- Fortnite updates can change fonts and layouts; templates are data and may need re-recording.
- Squads screens (teammate spectating, reboots) interact with the v0.3.0 rule that a HUD-only recovery stays non-active.
