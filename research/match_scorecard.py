"""Pure, offline comparison of match predictions with independently authored truth.

Times are seconds within ONE continuous recording/clip, not wall-clock time.
Truth uses inclusive boundary windows; match ownership uses half-open intervals.
No prediction is allowed to satisfy two truth matches or two truth transitions.
"""

import math


STATES = {"UNKNOWN", "LOBBY", "LOADING", "PRE_GAME", "IN_MATCH", "ELIMINATED"}
COMPLETIONS = {"complete", "partial", "unconfirmed"}
ENDINGS = {"placed", "victory"}
BOUNDARIES = ("opened_t", "played_from_t", "ended_t", "closed_t")
COUNTS = ("missed_matches", "extra_matches", "duplicate_matches", "missed_transitions",
          "extra_transitions", "incorrect_transitions", "false_endings", "missed_endings",
          "classification_errors", "boundary_errors", "invariant_errors", "unreviewed_sources")


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def window(value, label):
    if not isinstance(value, list) or len(value) != 2 or not all(number(v) for v in value) or value[0] > value[1]:
        raise ValueError(f"{label}: expected a finite [earliest, latest] window")
    return value


def keys(value, allowed, required, label):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ValueError(f"{label}: invalid keys (allowed: {', '.join(sorted(allowed))}; required: {', '.join(sorted(required))})")


def validate_truth(truth):
    """Reject malformed annotations instead of silently skipping unknown fields."""
    keys(truth, {"schema", "about", "sources"}, {"schema", "sources"}, "truth")
    if truth["schema"] != "match-truth-v1" or not isinstance(truth["sources"], dict) or not truth["sources"]:
        raise ValueError("expected match-truth-v1 with at least one source")
    for name, source in truth["sources"].items():
        if not isinstance(name, str) or not name:
            raise ValueError("truth source IDs must be nonempty strings")
        keys(source, {"review", "notes", "matches", "transitions", "unscored_transitions", "association_seconds"},
             {"review", "matches", "transitions"}, name)
        review = source["review"]
        keys(review, {"status", "reviewer", "basis"}, {"status", "reviewer", "basis"}, f"{name}.review")
        if review["status"] not in {"human_reviewed", "provisional"} or not all(isinstance(review[k], str) and review[k].strip() for k in ("reviewer", "basis")):
            raise ValueError(f"{name}: review needs a status, named reviewer and basis")
        distance = source.get("association_seconds", 30.0)
        if not number(distance) or distance <= 0:
            raise ValueError(f"{name}: association_seconds must be positive")
        if not isinstance(source["matches"], list) or not isinstance(source["transitions"], list):
            raise ValueError(f"{name}: matches and transitions must be lists (empty lists explicitly mean none)")
        ids, last_anchor = set(), float("-inf")
        for match in source["matches"]:
            keys(match, {"id", "anchor", "notes", "completion", "observed_from_start", "english_confirmed", "ended_by", *BOUNDARIES},
                 {"id", "anchor"}, f"{name}.match")
            if not isinstance(match["id"], str) or not match["id"] or match["id"] in ids:
                raise ValueError(f"{name}: match IDs must be nonempty and unique")
            ids.add(match["id"])
            a, b = window(match["anchor"], f"{name}.{match['id']}.anchor")
            if a < last_anchor or a == b:
                raise ValueError(f"{name}: match anchors must be nonoverlapping, positive-length and ordered")
            last_anchor = b
            for field in BOUNDARIES:
                if field in match and match[field] is not None:
                    window(match[field], f"{name}.{field}")
            if "completion" in match and match["completion"] not in COMPLETIONS:
                raise ValueError(f"{name}: invalid completion")
            for field in ("observed_from_start", "english_confirmed"):
                if field in match and not isinstance(match[field], bool):
                    raise ValueError(f"{name}: {field} must be boolean")
            if "ended_by" in match and match["ended_by"] not in ENDINGS | {None}:
                raise ValueError(f"{name}: ended_by is placed, victory, or null (no observed ending)")
        last_transition = float("-inf")
        for event in source["transitions"]:
            keys(event, {"state", "time", "notes"}, {"state", "time"}, f"{name}.transition")
            a, b = window(event["time"], f"{name}.transition.time")
            if event["state"] not in STATES or a < last_transition:
                raise ValueError(f"{name}: transitions must name known states and be ordered")
            last_transition = a
        ignored = source.get("unscored_transitions", [])
        if not isinstance(ignored, list):
            raise ValueError(f"{name}: unscored_transitions must be a list")
        for item in ignored:
            keys(item, {"time", "reason"}, {"time", "reason"}, f"{name}.unscored_transitions")
            window(item["time"], f"{name}.unscored_transitions.time")
            if not isinstance(item["reason"], str) or not item["reason"].strip():
                raise ValueError(f"{name}: an unscored interval needs a reason")
        for event in source["transitions"]:
            if any(max(event["time"][0], item["time"][0]) <= min(event["time"][1], item["time"][1]) for item in ignored):
                raise ValueError(f"{name}: expected transition overlaps an unscored interval")
    return truth


def boundary_error(actual, expected):
    """Signed seconds outside the accepted window; None denotes a missing boundary."""
    if actual is None:
        return None
    return actual - min(max(actual, expected[0]), expected[1])


def align(expected, actual, affinity):
    """Order-preserving one-to-one association, maximizing matches, then affinity.

    Classifications do not affect match association. A wrong classification must
    be scored as wrong, not avoided by finding a more convenient truth record.
    """
    table = [[(0, 0.0, ()) for _ in range(len(actual) + 1)] for _ in range(len(expected) + 1)]
    for i, truth in enumerate(expected, 1):
        for j, prediction in enumerate(actual, 1):
            options = [table[i - 1][j], table[i][j - 1]]
            score = affinity(truth, prediction)
            if score is not None:
                n, total, pairs = table[i - 1][j - 1]
                options.append((n + 1, total + score, pairs + ((i - 1, j - 1),)))
            table[i][j] = max(options, key=lambda item: (item[0], item[1]))
    return list(table[-1][-1][2])


def overlap(match, prediction):
    a, b = match["anchor"]
    return max(0.0, min(b, prediction["closed_t"]) - max(a, prediction["opened_t"]))


def record_errors(records, tolerance=0.005):
    """Checks independent of expected outcomes, including roundoff at M2's 1 ms precision."""
    errors, numbers = [], set()
    for index, r in enumerate(records):
        def bad(message):
            errors.append({"record_index": index, "match_number": r.get("match_number"), "message": message})
        if r["match_number"] in numbers:
            bad("duplicate match number")
        numbers.add(r["match_number"])
        fields = ("opened_t", "played_from_t", "closed_t", "observed_seconds", "active_seconds", "spectating_seconds", "uncertain_seconds")
        if not all(number(r.get(k)) for k in fields):
            bad("nonfinite or missing time")
            continue
        span = r["closed_t"] - r["opened_t"]
        if not r["opened_t"] <= r["played_from_t"] <= r["closed_t"]:
            bad("boundaries out of order")
        if any(r[k] < -tolerance for k in fields[3:]):
            bad("negative duration")
        if abs(r["observed_seconds"] + r["uncertain_seconds"] - span) > tolerance:
            bad("observed + uncertain does not equal closed - opened")
        if r["active_seconds"] + r["spectating_seconds"] > r["observed_seconds"] + tolerance:
            bad("active + spectating exceeds observed")
        ended, duration = r.get("ended_t"), r.get("complete_duration_seconds")
        if ended is not None and (not number(ended) or not r["played_from_t"] <= ended <= r["closed_t"]):
            bad("ending outside match interval")
        if r["completion"] not in COMPLETIONS:
            bad("unknown completion classification")
        elif r["completion"] == "complete":
            if not (r["observed_from_start"] and r["english_confirmed"] and not r["discontinuity"] and r["ended_by"] in ENDINGS):
                bad("complete match lacks required start, language, continuity or ending")
            if not number(duration) or not number(ended) or abs(duration - (ended - r["played_from_t"])) > tolerance:
                bad("invalid complete duration")
        elif duration is not None:
            bad("incomplete match claims a complete duration")
        for previous in records[:index]:
            if max(previous["opened_t"], r["opened_t"]) < min(previous["closed_t"], r["closed_t"]) - tolerance:
                bad(f"overlaps match {previous['match_number']}")
    return errors


def compare_source(prediction, truth, allow_provisional=False):
    issues = {key: [] for key in COUNTS}
    records = prediction["records"]
    issues["invariant_errors"] = record_errors(records)
    human_reviewed = truth["review"]["status"] == "human_reviewed"
    if not human_reviewed and not allow_provisional:
        issues["unreviewed_sources"].append({"message": "annotations require human review; --allow-provisional is explicit exploratory scoring only"})
    pairs = align(truth["matches"], records, lambda a, b: overlap(a, b) or None)
    used_truth, used_actual = {i for i, _ in pairs}, {j for _, j in pairs}
    for i, match in enumerate(truth["matches"]):
        if i not in used_truth:
            issues["missed_matches"].append({"truth_id": match["id"]})
            if match.get("ended_by") in ENDINGS:
                issues["missed_endings"].append({"truth_id": match["id"], "expected": match["ended_by"], "message": "match was not found"})
    for j, r in enumerate(records):
        if j not in used_actual:
            duplicated = [truth["matches"][i]["id"] for i in used_truth if overlap(truth["matches"][i], r)]
            kind = "duplicate_matches" if duplicated else "extra_matches"
            issues[kind].append({"match_number": r["match_number"], "truth_ids": duplicated})
            if r["ended_by"] in ENDINGS:
                issues["false_endings"].append({"match_number": r["match_number"], "message": "ending belongs to an unmatched/duplicate record"})
    boundaries = []
    for i, j in pairs:
        match, r = truth["matches"][i], records[j]
        identity = {"truth_id": match["id"], "match_number": r["match_number"]}
        for key in ("completion", "observed_from_start", "english_confirmed"):
            if key in match and match[key] != r[key]:
                issues["classification_errors"].append({**identity, "field": key, "expected": match[key], "actual": r[key]})
        if "ended_by" in match:
            actual_end = r["ended_by"] if r["ended_by"] in ENDINGS else None
            if actual_end != match["ended_by"]:
                if actual_end is not None:
                    issues["false_endings"].append({**identity, "expected": match["ended_by"], "actual": actual_end})
                if match["ended_by"] is not None:
                    issues["missed_endings"].append({**identity, "expected": match["ended_by"], "actual": actual_end})
        for field in BOUNDARIES:
            if field not in match:                 # unobserved/unlabelled is not an estimated timestamp
                continue
            expected, actual = match[field], r[field]
            error = boundary_error(actual, expected) if expected is not None else None
            item = {**identity, "field": field, "expected": expected, "actual": actual, "outside_window_seconds": error}
            boundaries.append(item)
            if (expected is None and actual is not None) or (expected is not None and (actual is None or error != 0)):
                issues["boundary_errors"].append(item)
    ignored = truth.get("unscored_transitions", [])
    excluded = [p for p in prediction["transitions"] if any(w["time"][0] <= p["t"] <= w["time"][1] for w in ignored)]
    transitions = [p for p in prediction["transitions"] if p not in excluded]
    expected = truth["transitions"]
    limit = truth.get("association_seconds", 30.0)

    def affinity(a, b):
        distance = abs(boundary_error(b["t"], a["time"]))
        if distance > limit:
            return None
        return (limit + 1 if a["state"] == b["state"] else 0) - distance

    transition_pairs = align(expected, transitions, affinity)
    used_truth, used_actual = {i for i, _ in transition_pairs}, {j for _, j in transition_pairs}
    issues["missed_transitions"] = [p for i, p in enumerate(expected) if i not in used_truth]
    issues["extra_transitions"] = [p for j, p in enumerate(transitions) if j not in used_actual]
    transition_boundaries = []
    for i, j in transition_pairs:
        a, b = expected[i], transitions[j]
        if a["state"] != b["state"]:
            issues["incorrect_transitions"].append({"expected": a, "actual": b})
        error = boundary_error(b["t"], a["time"])
        item = {"field": "transition", "expected_state": a["state"], "actual_state": b["state"],
                "expected": a["time"], "actual": b["t"], "outside_window_seconds": error}
        transition_boundaries.append(item)
        if error:
            issues["boundary_errors"].append(item)
    counts = {key: len(value) for key, value in issues.items()}
    return {"passed": not any(counts.values()), "human_reviewed": human_reviewed, "review": truth["review"],
            "counts": counts, "issues": issues, "match_pairs": [{"truth_id": truth["matches"][i]["id"], "match_number": records[j]["match_number"]} for i, j in pairs],
            "match_boundaries": boundaries, "transition_boundaries": transition_boundaries,
            "unscored_transition_intervals": ignored, "unscored_predictions": excluded,
            "classifications": {c: sum(r["completion"] == c for r in records) for c in sorted(COMPLETIONS)}}
