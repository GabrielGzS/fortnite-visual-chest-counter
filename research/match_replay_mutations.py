"""Small, reproducible sabotage checks for M3's important validation guarantees.

Mutates private in-memory module copies, never repository files or M2. Each
mutation must be rejected by a named existing test. Run after test_match_replay.py.
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_match_replay as T


MUTATIONS = [
    ("C", "if abs(r[\"observed_seconds\"] + r[\"uncertain_seconds\"] - span) > tolerance:", "if False:", "test_record_invariants_detect_each_impossible_time_total"),
    ("C", "if r[\"active_seconds\"] + r[\"spectating_seconds\"] > r[\"observed_seconds\"] + tolerance:", "if False:", "test_record_invariants_detect_each_impossible_time_total"),
    ("C", "if not (r[\"observed_from_start\"] and r[\"english_confirmed\"] and not r[\"discontinuity\"] and r[\"ended_by\"] in ENDINGS):", "if False:", "test_complete_match_needs_its_start_language_continuity_and_end"),
    ("C", "pairs = align(truth[\"matches\"], records, lambda a, b: overlap(a, b) or None)", "pairs = [(0, j) for j in range(len(records))]", "test_duplicate_prediction_cannot_satisfy_the_same_truth_twice"),
    ("C", "issues[\"false_endings\"].append", "[].append", "test_wrong_truth_fails_without_changing_predictions"),
    ("C", "issues[\"classification_errors\"].append", "[].append", "test_matching_does_not_hide_wrong_classifications"),
    ("C", "issues[\"boundary_errors\"].append", "[].append", "test_boundary_errors_are_signed_and_do_not_reclassify_the_match"),
    ("C", "if not human_reviewed and not allow_provisional:", "if False:", "test_provisional_annotations_never_become_human_validated"),
    ("R", "for language in (\"en\", \"pt\", \"unknown\")", "for language in (\"en\", \"pt\")", "test_portuguese_chest_evidence_preserves_unknowns_and_approx_only_events"),
    ("R", "\"approx\": sum(e[\"approx_counted\"]", "\"approx\": sum(e[\"certain_counted\"]", "test_portuguese_chest_evidence_preserves_unknowns_and_approx_only_events"),
    ("R", "fps = 2 if path.suffix.lower() == \".ffconcat\" else 1", "fps = 1", "test_extraction_keeps_M1_sampling_phase_and_picture_reference"),
]


def main():
    caught = 0
    for number, (name, old, new, test_name) in enumerate(MUTATIONS, 1):
        original = getattr(T, name)
        source = Path(original.__file__).read_text(encoding="utf-8")
        if old not in source:
            raise RuntimeError(f"mutation {number} no longer applies; review this check")
        mutant = types.ModuleType(original.__name__ + "_mutated")
        mutant.__file__ = original.__file__
        exec(compile(source.replace(old, new), original.__file__, "exec"), mutant.__dict__)
        try:
            with patch.object(T, name, mutant):
                if name == "C":
                    with patch.object(T.R, "C", mutant):
                        getattr(T, test_name)()
                else:
                    getattr(T, test_name)()
        except AssertionError:
            caught += 1
            print(f"caught {number:02d}: {test_name}")
        else:
            print(f"SURVIVED {number:02d}: {test_name}")
    print(f"{caught}/{len(MUTATIONS)} scorecard mutations caught")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
