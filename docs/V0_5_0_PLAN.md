# v0.5.0 — Treasure Recognition & Predictions (roadmap)

Planning document, written 2026-11-12 while v0.4.0 planning began. **This is a roadmap, not implementation authorization.** Nothing here
is built until v0.4.0 has shipped and a v0.5.0 investigation and design have been approved, the same way v0.3.0 and v0.4.0 started.

Purpose: keep the v0.5.0 vision from getting lost, and make sure v0.4.0 records the data v0.5.0 will need.

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
- Claims about Fortnite's real drop rates.
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
