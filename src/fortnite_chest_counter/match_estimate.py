"""
The end-of-match chest estimate (optional, off by default; Dashboard > Game): when a match ends, add an estimated number of broken
chests to APPROX.

Fortnite counts a chest that is broken instead of opened, but a broken chest shows no pop-up, so the detector cannot see it. In the
maintainer's v0.5.1 history the "Broken chest" +1s made in the Game view came to about 20 % of the chests detected in the same match
(33 complete matches, 315 of 1,538; single matches anywhere from 2 % to 51 %). This adds that share at the end of each match - an
estimate, never evidence:

    base      = the chests the detector counted in the match (APPROX) - your -1s for that match
    target    = base x percent / 100, rounded half up
    estimate  = target - your "Broken chest" +1s for that match, never below 0: chests you added yourself are not added twice

The base never contains a correction or an earlier estimate, so nothing compounds. A match qualifies when it is confirmed as a match
(English) and either COMPLETE, or PARTIAL with your own ending seen on screen (Placed or Victory): the share applies to the chests that
were detected, so a short gap in the video does not stop it (v0.6.0). Never a match cut off by Stop, lost, ended without your ending being
seen, or not confirmed as a match. "Partial" itself does not change: only who gets an estimate. It is
applied once its late chests are in (10 s of video after the close - the tracker's settling time -, the next match opening, or
counting stopping), exactly once: its id is made from the run and the match number, and the counter refuses a second one from memory and from
the history. CERTAIN never changes. The record is kept apart from your +1s (a "chest_estimate" row of the match history), so the
Overview, Analytics and the history show detected chests, your corrections and estimated chests separately, and Undo takes an estimate
back like a +1. Pure functions only: the counter applies the estimate.
"""

DEFAULT_PERCENT = 20
MIN_PERCENT, MAX_PERCENT = 1, 100
COMPLETE, PARTIAL = "complete", "partial"
PLAYER_ENDINGS = ("placed", "victory")      # match_state.PLACED / VICTORY: your own ending, seen on screen


def estimate_id(run_id, match_number):
    """The one id an estimate for this match can ever have: a second request for it is the same estimate, not another one."""
    return f"estimate:{run_id}:{match_number}"


def eligible(match):
    """English confirmed, and complete - or partial (a gap in the video, say) with your Placed / Victory seen. Never one cut off by Stop,
    lost, ended unseen, or unconfirmed."""
    if not match or match.get("english_confirmed") is not True:
        return False
    return match.get("completion") == COMPLETE or (match.get("completion") == PARTIAL and match.get("ended_by") in PLAYER_ENDINGS)


def valid_percent(value):
    return type(value) is int and MIN_PERCENT <= value <= MAX_PERCENT


def amount(detected, removed, broken_logged, percent):
    """-> (base, target, estimate) in whole chests, as the module docstring says. Rounded half up: 20 % of 3 is 1, of 2 is 0."""
    base = max(0, int(detected) - int(removed))
    target = (2 * base * int(percent) + 100) // 200
    return base, target, max(0, target - int(broken_logged))


def describe(result):
    """One plain sentence about an applied (or empty) estimate, for the console and the app's Activity log."""
    number, percent, base, broken = result.get("match_number"), result.get("percent"), result.get("base"), result.get("broken_logged") or 0
    why = f"{percent} % of {base} detected" + (f", minus your {broken} Broken chest +1s" if broken else "")
    if result.get("delta"):
        return f"Match {number}: +{result['delta']} estimated broken chests ({why})."
    return f"Match {number}: no estimated chests to add ({why})."
