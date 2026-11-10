# M2 corrections approved during M3

Status: approved by the user on 2026-11-10 and implemented. Base:
`d6913106240625c2876fb0a790d89cf39840744c`. M3 tooling is committed separately as
`b990db5`; the corrections follow it in a separate local commit.

The accepted handoff asks for failing permanent tests before fixes and for approved
corrections afterwards. The first 13 permanent regression checks reported
**3 passed, 10 failed** against the unchanged implementation. Before any M2 code
change, the expanded 16-check suite reported **3 passed, 13 failed**. After the
fixes and additional controls, **26/26 pass**, including a 60-case interval matrix.
These are ordinary assertions, with no skips or expected-failure decorators.

The user's approval explicitly covered all four conservative corrections, the
known missed edited match, and replacing tests that required the unsafe behavior
while preserving or strengthening coverage. No recognition threshold was weakened.

## 1. Invalidate pending English confirmation on a break

Keep the continuous CONNECTING -> gameplay language handoff, but track whether
that evidence is still continuous. Invalidate it on a missing-sample gap greater
than `MAX_SAMPLE_GAP`, a black/frozen interval reaching `NO_PICTURE_BREAK`, and a
rewind. A fresh, confirmed CONNECTING signal can establish it again. Pending
pre-game language evidence is also invalidated on a break; fresh countdown text
may establish it again without repairing the lost start. Lobby-only language
inheritance was not added.

Reproductions: loading -> 20 missing seconds -> health bar; loading -> eight
black/frozen samples -> health bar. All previously produced English-confirmed
records without fresh English evidence. They now remain unconfirmed. Continuous,
short-interruption and fresh-confirmation controls pass.

## 2. Stop treating a returning health bar as proof of respawn

Remove the automatic ELIMINATED -> IN_MATCH transition based solely on health
pixels and disappearing end/spectating text. The current evidence cannot identify
whose HUD is visible. Keep active time stopped after elimination. If gameplay
becomes ambiguous before any confirmed ending, retain an explicit reason and
prevent a later record from claiming complete observation of the player's match.

This deliberately undercounts real reboots until positive own-player evidence is
available. Existing tests that call HUD-only recovery a reboot must be replaced
with assertions for this approved conservative behavior; they cannot keep their
old expected transitions and also satisfy the new requirement. Unrelated lifecycle
and language assertions remain in force.

## 3. Use the actual closure decision time consistently

`closed_t` will mean when the tracker closes the record, separately from
`ended_t` (the observed placement/victory time). In the three timeout paths,
close at the current observation time rather than backdating closure after
already accumulating the intervening time. Missing-picture/sample intervals
remain uncertain; usable-picture time retains the existing state-based categories.

This is a small change to the closure calls, not a new duration estimate. Complete
duration continues to use observed play/end boundaries only. Partial/unconfirmed
matches still have no complete duration. Enforce these invariants on all records:

- observed + uncertain = closed - opened, within 0.005 s rounding tolerance;
- active + spectating <= observed;
- durations are nonnegative and boundaries ordered;
- adjacent record intervals never overlap.

The failing reproductions previously reported 216 accounted seconds in a 95-second
record, 155 observed seconds in a 95-second record, and inconsistent post-elimination
timeouts. A consistent `closed_t` includes the delay until the tracker decides
the source is lost; it must not be interpreted as a visually observed match ending.

The expanded tests exposed three related accounting cases, corrected within this
same scope: a missing stop tail is uncertain rather than omitted; stopping on a
black/frozen picture adds no active time; and missing time after a countdown is
excluded from active play. If a long break hides departure and no later countdown
was seen, `played_from_t` is the first usable observation after the break. Earlier
departure is not estimated. Uncertainty before a fresh countdown is not subtracted
from later observed play. The blackout regression now asserts an exact six active
seconds starting at 28 s, rather than relaxing its original six-second bound.

## 4. Remove the timer-only post-victory new-match fallback

Elapsed time plus a health bar is compatible with a victory celebration. It must
not manufacture another match. Retain the finished match until a normal observed
boundary (loading/menu/countdown), a loss of source, or stopping closes it. A real
new countdown can still open a separate record.

**Known recall tradeoff:** the English reference contains an editorial cut from
the first win into another match around 262 s, without the loading/countdown cues
M1 recognizes. The old fallback opens the second record at 303 s. Removing it will
miss that second match with the current cue set. The independent scorecard does
continue reporting this miss; its truth was not changed to make the fix pass.
The old two-record regression expectation was replaced transparently, while
keeping both observed victories in the independent annotations and the old behavior
in the frozen reference file. See `M3_VALIDATION.md` for exact remaining errors.

Detecting edited cuts, recognizing the player after a reboot, or introducing a
separate candidate-match API would require additional design/evidence and is not
part of these narrow corrections.

## Scope and verification

Changes are limited to `match_state.py`, its tests, and documentation. M1,
frozen chest detection, profile state, OBS, the GUI and live counting remain
outside this work. Keep M3 tooling and M2 fixes in separate local commits.

Verified the new regressions, remaining M2 contracts, M1 tests, cached real timelines,
and independent scorecard outcomes. The changed English result and retained
limitations are recorded in `M3_VALIDATION.md`. Truth windows, frozen reference
data, M1 cues and chest detector thresholds remain unchanged.
