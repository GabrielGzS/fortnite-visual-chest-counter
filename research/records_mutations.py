"""Small, reproducible sabotage checks for v0.4.0 M3: Personal Bests eligibility and evidence.

Mutates private in-memory module copies, never repository files. Each mutation must be rejected by a named test in tests/test_records.py.
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_records as TR

MUTATIONS = [
    ("    complete = [m for m in matches if m.quality == A.COMPLETE]", "    complete = list(matches)", "test_the_best_match_is_complete_even_when_a_partial_one_had_more"),
    ("(m.active_seconds or 0) >= MIN_RATE_ACTIVE_SECONDS", "(m.active_seconds or 0) >= 60", "test_the_best_rate_needs_five_minutes_of_play"),
    ("if m.quality in (A.COMPLETE, A.PARTIAL) and m.broken_chests > 0]", "if m.quality == A.COMPLETE and m.broken_chests > 0]", "test_most_broken_chests_counts_partial_matches_as_reported"),
    ("(value(item) == value(best) and when(item) < when(best))", "(value(item) == value(best) and when(item) > when(best))", "test_a_tie_goes_to_the_first"),
    ("    if hour is not None and hour.totals.recorded > 0:", "    if hour is not None:", "test_nothing_yet_means_no_bests"),
    ("r.session.span_seconds >= MIN_SESSION_RATE_SECONDS", "r.session.span_seconds > 0", "test_a_session_under_an_hour_has_no_pace_best_and_no_best_hour"),
    ("bool(match.chests_may_be_missing or match.interrupted)", "bool(match.interrupted)", "test_a_match_cut_short_is_marked"),
    ("_match_best(\"match_chests\", best, best.approx, best.certain)", "_match_best(\"match_chests\", best, best.approx - best.manual_added + best.manual_removed, best.certain)",
     "test_undoing_a_correction_changes_the_best"),
]


def main():
    caught = 0
    original = TR.R
    source = Path(original.__file__).read_text(encoding="utf-8")
    for number, (old, new, test_name) in enumerate(MUTATIONS, 1):
        if old not in source:
            raise RuntimeError(f"mutation {number} no longer applies; review this check")
        mutant = types.ModuleType(original.__name__ + "_mutated")
        mutant.__file__, mutant.__package__ = original.__file__, original.__package__
        sys.modules[mutant.__name__] = mutant
        exec(compile(source.replace(old, new, 1), original.__file__, "exec"), mutant.__dict__)
        try:
            with patch.object(TR, "R", mutant):
                getattr(TR, test_name)()
        except (AssertionError, RuntimeError, ZeroDivisionError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
            caught += 1
            print(f"caught {number:02d}: {test_name} ({type(error).__name__})", flush=True)
        else:
            print(f"SURVIVED {number:02d}: {test_name}", flush=True)
    print(f"{caught}/{len(MUTATIONS)} personal best mutations caught")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
