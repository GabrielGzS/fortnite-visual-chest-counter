# v0.5.0 — Treasure Recognition & Predictions (roadmap)

Planning document, written 2026-11-12 while v0.4.0 planning began. **This is a roadmap, not implementation authorization.** Nothing here
is built until v0.4.0 has shipped and a v0.5.0 investigation and design have been approved, the same way v0.3.0 and v0.4.0 started.

Purpose: keep the v0.5.0 vision from getting lost, and make sure v0.4.0 records the data v0.5.0 will need.

**Revised 2026-11-13 (after v0.4.1 shipped): v0.5.0 is the Predictions MVP without treasure recognition.** Recognition is expensive
(no footage, templates per season and HUD scale), so it is deferred. The MVP turns the chest history every profile already keeps into
statistical forecasts for a reward pool. Section 0 is the design and the read-only architecture audit behind it; sections 1-10 below are
the original roadmap, kept for the recognition work that comes later. Approved by the maintainer on 2026-11-13 and built (section 0.11).

## 0. Predictions MVP (design, 2026-11-13)

### 0.1 What it is, and what it is not

A **statistical estimator**, like APPROX: the best number available, not an observation. It uses the APPROX side of the history (detected
chests plus the player's standing +1/−1), the reward odds of a pool preset, and the profile's real chest rate. It never claims a reward
dropped. Three kinds of information stay apart from day one, so recognition can be added later without rebuilding anything:

| Kind | Source | In the MVP |
|---|---|---|
| **Estimated** | chest history × published odds | everything on the page |
| **Reported** | the player presses "Mark obtained" | stored as an event with time, profile, pool, reward, chest count, `source: "manual"` |
| **Detected** | future treasure recognition | not built; same event shape with `source: "detected"`, which then takes precedence |

### 0.2 Three independent numbers per reward

| Number | Meaning | Resets |
|---|---|---|
| **Chance in this cycle** | 1 − (1 − p)^n over the chests of the current cycle | per the reward's cycle rule (0.3) |
| **Statistically expected** | n_total × p over every chest in the pool's period: "how many cars you could have pulled" | never within the pool |
| **Reported obtained** | the player's own reports | only by Undo |

The second number answers the "how many cars could I have gotten" idea for **every** reward without making weekly rewards cycle on their
own. Completed cycles are shown beside it and are never called obtained rewards.

### 0.3 Cycle rules (set by the preset, not per card)

| Reward kind | Default rule | Cycle restarts when |
|---|---|---|
| Repeatable (Gizmo) | **automatic** at the cycle milestone (90%: 292 chests at 1 in 127) | the milestone is reached; counted as one completed cycle |
| Weekly (car, pickaxe/back bling, jam track, loading screen) | **no automatic cycle** | the weekly rotation (a new reward: nothing carries over), or the player presses **Start new cycle** (for example to help friends) |
| One per pool (Pirate Shop Access, gold outfit if per pool) | **no cycle** | the pool ends, or the player presses Start new cycle |

**Mark obtained** stops a weekly or one-per-pool reward's chance from rising until its next rotation; **Undo** restores it exactly.
**Start new cycle** and **Mark obtained** are separate buttons: one is a statistical restart, the other a report. A "count my cycles
automatically" switch for weekly rewards can come later if players ask; the expected number already covers the hypothetical.

Automatic cycles are **derived, not stored**: completed = floor(chests since the cycle start / milestone chests). Only player actions are
stored, so a corrected or re-read history recalculates everything (the v0.3.0 principle).

### 0.4 The maths (pure, deterministic)

- Chance after n chests: 1 − (1 − p)^n, computed as −expm1(n · log1p(−p)) so 1 in 1,562,500 stays exact.
- Chests to a milestone m: ceil(log(1 − m) / log1p(−p)). 1 in 127: 50% at 88, 90% at 292. Never 100%: no "guaranteed by".
- Chance over the next k chests: the same formula on k alone. Past failures never make the next chest luckier, and the page says so.
- Hours to a milestone: remaining chests ÷ (chest rate × team scenario). Already reached: "Milestone reached", never "expected now".
- Later, Treasure Hours: each chest carries its own p, so the chance becomes 1 − Π(1 − p_i). The store keeps chest times, so this
  can be added without changing the data.

### 0.5 Rate and team scenarios

- **Rate:** real-life chests per hour from v0.4.0 (`progression.Snapshot.progress`): session time, breaks and queues included, which is
  what "hours of my life" means. Default period: last 7 days, falling back to all time; "Not enough counting yet" under 30 minutes of
  session time (the existing `MIN_HOURLY_SECONDS`), with an optional manual rate.
- **Solo / Duo / Trio / Squad:** a selector that multiplies the future rate by 1 + 0.8(N-1): each teammate opens 80% as many chests as
  you (maintainer, 2026-11-13: a safe average; never detected). Duo 1.8x, Trio 2.6x, Squad 3.4x. It changes only the forecast and the
  What If? time and finder, never the chance so far, and is labelled a scenario: sharing within a team is a community belief, not
  confirmed by Epic.

### 0.6 What the audit found (read-only, 2026-11-13)

| Need | Existing piece | Consequence |
|---|---|---|
| Chests per profile, each with its own time | `state/history/<profile id>/chests.jsonl` (`profiles.history_folder`), kept with match tracking on or off since v0.4.0 | no second counter: chests in any window are counted from history |
| The right count (APPROX, corrections, no Reset/Edit) | `progression.Snapshot` events: detected + standing +1/−1; Reset, Edit counts and starting counts are not chests | reuse as is; Reset on the Dashboard cannot erase predictions |
| Not someone else's chests | `progression` leaves out chests seen while spectating, and `timeline.LEFT_OUT_SOURCES` (`simulate`) | the same rules apply to predictions |
| Where to start for an existing profile | every chest since v0.3.0 has `at` | "count from the season's start" is exact where history covers it, else "from now" |
| Live updates | the window gets an `event` message per counted chest (`set_counts`) | the page adds live chests on top of the last history read, re-read off-thread like Analytics (`records.load` takes ~2 s on a heavy year) |
| Per-profile state | profiles keep their own counter, source, HUD; Analytics follows the active profile | predictions follow the active profile; switching re-reads |
| Storage safety | an unknown kind in `chests.jsonl` reads as damaged; `state/*.json` files are treated as counter files by the updater's helper | player actions go in a new append-only `state/history/<profile id>/predictions.jsonl`, ignored by older versions (rollback-safe) |
| Shipping data | templates ship from an explicit list (`build_release.TEMPLATE_FILES`; v0.4.1 almost missed one) | the pool preset file must be added to that packaging list, with a `test_release` check |

### 0.7 Pool presets

A JSON file in the package, one per pool, with an id, a display name, start and end dates, the weekly rotation time, each reward's id,
name, odds (1 in N), kind (repeatable / weekly / one per pool), its cycle rule, and the source (URL and the date it was read) with a
revision number. The first preset is Chapter 7 Season 5's Treasure Hunters pool with Epic's published normal odds (Gizmo 1 in 127,
loading screen 272, jam track 391, pickaxe or back bling 568, vehicle and decal 7,813, Pirate Shop Access 137,500, gold outfit
1,562,500), **read again from Epic's support page when the preset is written**: the figures above came to us second-hand. Treasure Hour
multipliers are recorded in the preset but not applied in the MVP. Weekly rewards get a separate cycle per week, derived from the
rotation time: a new week never inherits last week's chance.

### 0.8 The page

A **Predictions** page in the sidebar, next to Analytics: profile and pool on top, the chest count used and the rate, the team selector
and the milestone choice (50% / 90%). One card per reward, rarest last by default:

- the chance in this cycle, large, with the odds under it;
- a bar toward the selected milestone, **measured in chests** and labelled as such (a raw-probability bar barely moves for rare rewards);
- chests and hours to 50% and 90%, or "Milestone reached";
- statistically expected, completed cycles, reported obtained (with date);
- **Start new cycle** and **Mark obtained** / **Undo**.

Every number says "estimate" once at the top: based on counted chests (which can miss some) and published odds, never a record of what
dropped. Nothing here changes CERTAIN, APPROX, history, Analytics or the OBS files.

### 0.9 Scope, acceptance and testing budget

**In:** the page, one pool preset, per-profile tracking, chance / expected / cycles, automatic Gizmo cycles, manual cycles, Mark obtained
and Undo, 50% and 90% forecasts, team scenarios, start from the season or from now, live updates.
**Out:** treasure recognition, Treasure Hour boosts applied to the maths, custom pools, OBS output for predictions, automatic pool
downloads.

| Acceptance target | Verification |
|---|---|
| Correct maths, including extreme odds | unit tests with fixed values (88 / 292, 1 in 1,562,500) |
| Cycles, rotation, Mark obtained, Undo, restart | unit tests on synthetic chest histories and action logs |
| Per-profile separation and persistence | two profiles, switch, restart the app (focused integration test) |
| Live updates while counting | synthetic `event` messages update the cards |
| Existing behaviour unchanged | the existing count, history and Analytics suites; no detector change, so **no video runs** |
| Ships correctly | one package build and check, the preset in the zip |

**Budget:** unit and focused integration tests while building; one consolidated run of the existing suites at the end; one package
check. **Stop when** every target passes and the page is usable. Presentation polish and anything listed as Out go to later versions.

### 0.10 Milestones (each one commit, focused tests)

| Step | Content |
|---|---|
| P1 | `predictions.py`: pure engine (maths, cycles, rotation, expected, forecasts) and the preset format, with tests |
| P2 | Storage: `predictions.jsonl` actions, reading chests from history with the existing rules, season-start versus from-now; tests incl. rollback safety |
| P3 | The Predictions page, live updates, team and milestone selectors, buttons; GUI tests offscreen |
| P4 | Packaging (preset in `TEMPLATE_FILES`-style list), docs, README, release notes; one package check; RC |

### 0.11 Decisions (maintainer, 2026-11-13) and what was built

| Question / addition | Decision |
|---|---|
| Weekly rotation | Sundays 9 AM America/New_York (14:00 UTC in November 2026), as explicit UTC times in the preset, never assumed to go on forever |
| Eligible chests | every chest the counter counts (normal, rare, sprite) is one attempt; the page says so |
| Gold outfit, Pirate Shop Access | the gold outfit is weekly (Epic's table: "Weekly Gold Outfit"); Pirate Shop Access is once per season |
| Start | from the season's start, from history; Start new cycle counts from the moment it is pressed (a timestamp, never a copied number) |
| Two tabs | **My Progress** (this profile, saved actions) and **What If?** (never saved), one engine |
| Luck wording | fixed sentences from the chance (still early, perfectly normal, behind the average, uncommon, unlucky, terrible luck); without a report they are conditional ("if you are still waiting"); after Mark obtained they say how early or late it came. No claim about fairness of the game |
| What If? | Roll a prediction: a geometric first-drop draw (not a number between 1 and the odds), the finder drawn among the team, hours at the player's pace, how lucky the roll was |
| Treasure Hours | the preset lists verified windows (start, end, multiplier per reward); a chest inside one counts at its boosted odds by its own time (1 − Π(1 − pᵢ)); none listed yet. What If? offers 1.5× to 10× as hypotheticals for the whole hunt. Forecasts stay at normal odds |

RC3 (maintainer's review of RC2): the team choice changes every card's time rows at once (never the chance or the chests needed);
**Assign to weeks...** (ALLOCATE rows: moves added chests between "week not known" and weeks that had begun, never adds or removes any);
a **Probability curve** per reward (`charts.ProbabilityCurve`, QPainter, no new dependency).

RC4 (maintainer's review of RC3): the team selector is a **scenario model**, not a speed control: every card is recalculated from your
actual position in its own period times the team factor (chance, bar, expected, Gizmo's hypothetical cycles, chests and time needed),
with your own figures beside it; never saved, a reported reward never modeled, Solo is the actual view. **Seasons and periods** are
generic: every file in `pools/` is a season, its periods are named by their start date (stable ids in the rows; RC3's indexes still
read); Edit counts asks optionally for the season (the running one by default) and the period (not known, current, previous, a listed
week, or a date resolved among installed seasons only). **Manage weeks...** is a visible button on My Progress.

Built on `dev/v0.5.0`: `predictions.py` (engine, pool, actions), `pools/ch7_treasure_hunters.json`, the Predictions page in `gui/app.py`,
`tests/test_predictions.py` (21) and `tests/test_predictions_ui.py` (7). The preset ships with the package automatically (the build copies
the whole package folder except templates).

## 1. The goal

v0.3.0 knows which match a chest belongs to. v0.4.0 measures real progress (per hour, per day, per week) and personal bests. v0.5.0 adds
the last major source of information on screen, **treasure rewards**, and turns the accumulated history into **predictions**: how many
more chests, hours and days until a goal the player sets.

With chest counts, treasures, real-life time and daily history linked together, the app can answer the question players actually ask:
*"At my real pace, when will I get there?"*

## 2. What v0.5.0 depends on from v0.4.0

| v0.5.0 needs | Provided by v0.4.0 (see [V0_4_0_PLAN.md](V0_4_0_PLAN.md)) |
|---|---|
| Every chest with a wall-clock time and a stable identity | Already in v0.3.0 history (`chests.jsonl`, `run_id + counter_epoch + event_id`, `at`). v0.4.0 keeps it even with match tracking off (decision D7) |
| Real-life rate per hour, honest about gaps | Sessions and time counting (M1, M2) |
| Daily and weekly history that separates "no chests" from "not counting" | Day and week coverage (M2) |
| Detected vs adjusted totals, and why each manual chest was added | v0.3.0 correction reasons, v0.4.0 chest-source statistics (M10) |
| Per-match attribution | v0.3.0 `match_history.attribute` |
| A tabbed Analytics page with room for a new tab | v0.4.0 M4 |
| A charting approach that adds nothing to the package | v0.4.0 M5 (drawn with QPainter; QtCharts is not shipped) |

If v0.4.0's daily coverage turns out unreliable, predictions in days must wait: a forecast built on days that look like zero but were
really "not counting" would be badly wrong.

## 3. Treasure recognition

### What is known today

- The idea is ROADMAP item C: the **"YOU FOUND ..."** notification and similar reward cues, as their own events, de-duplicated across
  frames and linked to the chest they came from when the footage shows it.
- **No labelled footage of it exists in the project yet**: no case in `tests/cases/`, no capture, no template. Its position, duration,
  animation, size at other HUD scales and wording in other languages are all unmeasured.
- The lobby has a **TREASURE** tab (found during v0.3.0 M9H because it moves the menu bar words). It may relate to the same reward
  system. Reading the lobby is a different feature and is not assumed here.

### What it should detect (to be confirmed by footage)

| Field | Notes |
|---|---|
| Treasure type | Only types with a template. Anything else is "unrecognised treasure", never guessed |
| Quantity | Only if the number is legible; otherwise unknown, never 1 by default |
| Time | Source time `t` and wall clock `at`, as for chests |
| Match | By the treasure's own time, with the same rule chests use (`attribute`) |
| Related chest | Only when one chest event is clearly the cause (see below); otherwise none |
| Confidence | Two tiers at most, mirroring CERTAIN/APPROX; never mixed into chest counts |

### How it would probably be built (subject to the investigation)

- The proven v0.3.0 approach first: fixed-position text masks scored with template correlation (`match_cues.py` style), English
  first, native-size templates per HUD scale (v0.3.0 M9G showed these beat multi-scale search: 0.92+ vs 0.82–0.86 and 31× cheaper).
- Quantities: digit templates in a fixed box, the way `popup_lines.py` tracks digit changes, before any OCR library is considered.
- Cost: chest detection already uses most of the ~10 ms per-frame budget, and match tracking samples once a second. A short
  notification may need checking on every frame for a few seconds after each chest event, rather than all the time. Measure inside
  the full pipeline before deciding, and judge it by end-to-end results (sustained frame rate, dropped frames), not micro-benchmarks.
- One notification = one event, de-duplicated across frames and across a brief hide (the full-screen map), as v0.3.0 does for
  pop-ups.

### Linking a treasure to a chest

- Rule of thumb to be measured: a treasure seen within a short window after exactly one counted chest belongs to that chest.
- Two chests in the window, a broken chest (no pop-up), or a treasure from something that is not a chest: **unattributed**.
  Unattributed treasures still count in per-match, per-hour and per-day statistics; they are only left out of "per chest" yield.
- Never rewrite a chest row. The link is its own row, so a better rule later can recalculate everything (v0.3.0 principle:
  history keeps observations, statistics are recalculated).

### Storage

- A new append-only file, for example `state/history/<profile>/treasures.jsonl`, rather than new kinds in `chests.jsonl`.
  Reason: v0.4.0's (and v0.3.0's) reader counts an unknown kind in `chests.jsonl` as a damaged row, so a rollback would show
  warnings. A separate file is ignored by older versions entirely.
- Same row contract as today: `kind`, `schema`, `id`, `run_id`, `at`.
- Not in `state/*.json` (the updater's helper treats every such file as a counter file).

## 4. Treasure analytics

| Metric | Denominator | Notes |
|---|---|---|
| Treasures found | — | Total and by type |
| Treasures per chest | Attributed chests | Only from attributed treasures, so it is a true per-chest yield |
| Treasures per match | Complete matches | Same eligibility as chests per match |
| Treasures per active minute | Active play | v0.3.0 definition of active play |
| Treasures per real-life hour, day, week | v0.4.0 session time, calendar days and weeks | Same coverage rules as chests |
| Yield by type | Attributed chests | With sample size shown |

**Observed frequencies are not drop odds.** "1 in 14 chests gave X" is what this player saw, with this detector, in this sample. The
page must say so, show the sample size, and show a range (for example a 90% interval) rather than one exact rate. Detection
completeness matters too: if the detector misses some notifications, the observed yield is too low, and that must be stated until it is
measured.

## 5. The Prediction page

### Goals the player sets

| Goal type | Example | Model |
|---|---|---|
| Fixed chest count | "Open 500 chests" | Deterministic: remaining chests ÷ rate |
| Fixed treasure count | "Find 10 of X" | Random: needs the observed yield and its uncertainty |
| First occurrence | "Get my first X" | Random: geometric-style waiting time |
| By a date | "How many chests by Sunday?" | Rate × remaining time, as a range |

The reward model must be **chosen explicitly** by the player (or by a preset we document), never inferred silently.

### What it shows

- **Chests still needed**: exact for a fixed count; for a random reward, a range (for example 50%, 90%, 95%, 99%). A random drop never
  reaches 100%, so there is no "guaranteed by" number.
- **Hours still needed**: chests ÷ real-life chests per hour (v0.4.0 session rate), not the per-minute gameplay rate, which would be
  far too optimistic.
- **Days still needed**: from chests per **calendar** day over a stated period (for example the last 14 days), with "if you keep
  playing like your average played day" as a clearly labelled alternative. Using only played days would exaggerate the pace.
- **Pace check**: "on track / behind" against a deadline, if the player sets one.
- **How sure**: sample size, period used, and a plain sentence when the data is too thin ("Play a few more days for a forecast").

### Uncertainty

- Rates: use the spread between days, not only the average (a 500-chest day followed by three zeros is not "125 a day, reliably").
- Random rewards: estimate the yield with its uncertainty (for example a Beta posterior on per-chest yield) and turn that into a
  distribution of chests needed; quote percentiles.
- Show the inputs: "based on 9 days, 1,240 chests, 18 X found".

## 6. Data requirements (check during v0.4.0)

- Every counted chest keeps `at` with its UTC offset (true since v0.3.0).
- Days with no counting are distinguishable from days with counting and no chests (v0.4.0 M2).
- Manual chests keep their reasons, so broken chests (which show no pop-up and may give no visible treasure) can be modelled apart.
- History is append-only and never migrated in place, so v0.5.0 can recalculate everything from v0.3.0 onward.

## 7. Technical challenges

1. **Evidence first.** No footage yet. Collect lobby-to-lobby sessions with treasures, at 1080p and the small HUD, and keep short
   verified clips as permanent cases (`tests/cases/`, `research/cases.py`).
2. **Season changes.** Treasure names, icons and the notification design can change every season; templates need a maintenance
   path, and an unknown design must degrade to "unrecognised", never to a wrong type.
3. **Languages and HUD scales.** English first, as for match tracking. Portuguese chest detection stays as is.
4. **Overlap with the chest pop-up.** The notification may appear near or over the chest pop-up region. Chest counting must stay
   event-identical (`research/regress.py`) whatever treasure detection does.
5. **Livestream compression.** Small text blurs at 720p (v0.3.0 M9H). Expect lower recall on streams; report it per source type.
6. **Time budget.** See section 3.
7. **Fair play.** Video only, as always: no game memory, files, network or Fortnite API.

## 8. Decisions deferred to the v0.5.0 investigation

- Which treasures exist this season, and which are worth recognising first.
- Whether quantities are legible enough to read.
- The chest-link window, measured on footage.
- Whether treasure counts belong in the OBS overlay (probably an optional separate file, never a change to `chest_counter.txt`).
- Which reward models ship as presets, and how a player defines a custom one.
- Whether predictions appear on the Dashboard or only on their own page.
- Whether treasure events need their own confidence tiers or reuse CERTAIN/APPROX wording.

## 9. Not in v0.5.0

- Reading the lobby's TREASURE tab or any account progress (not video of play, and a different feature).
- Claims about Fortnite's real drop rates. *(2026-11-13: the Predictions MVP uses Epic's own published odds, cited in the preset with
  their source and date; the app still makes no claim of its own about drop rates.)*
- Automatic correction factors (for example "add 15% for broken chests") without measured evidence.
- Other languages beyond English for treasure text.

## 10. Milestone sketch (not authorized)

| Step | Content |
|---|---|
| T0 | Investigation: collect and label footage, measure candidate cues, cost and recall; report before any design |
| T1 | Treasure cue scoring (pure module + tests), like v0.3.0 M1 |
| T2 | Treasure events and storage (`treasures.jsonl`), chest link rule, shadow mode first |
| T3 | Treasure analytics in the existing Analytics tabs |
| T4 | Prediction engine (pure, tested with synthetic histories, deterministic and random models) |
| T5 | Prediction page and goal setting |
| T6 | Validation, RC, hands-on acceptance, release |
