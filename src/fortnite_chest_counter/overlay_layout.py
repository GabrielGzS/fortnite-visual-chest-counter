"""Render the shared on-screen and OBS sections from one validated context."""

import math

from fortnite_chest_counter import settings
from fortnite_chest_counter.detection import chest_types


RATE = 137_500
SCOPES = ("personal", "team", "cumulative")


def _count(value, default=0):
    return value if type(value) is int and 0 <= value <= 9_000_000_000_000_000 else default


def _boost(value):
    return float(value) if type(value) in (int, float) and value in (1, 1.5, 2) else 1.0


def _summary(value):
    if not isinstance(value, dict):
        return None
    total = _count(value.get("total"))
    certain = min(_count(value.get("certain")), total)
    boost = _boost(value.get("boost"))
    log_no_drop = value.get("log_no_drop")
    if type(log_no_drop) not in (int, float) or not math.isfinite(log_no_drop) or log_no_drop > 0:
        log_no_drop = total * math.log1p(-boost / RATE)
    return {
        "certain": certain, "total": total, "log_no_drop": float(log_no_drop), "boost": boost,
        "matches": _count(value.get("matches")), "players": _count(value.get("players")),
        "names": value.get("names") if isinstance(value.get("names"), str) else "",
        "types": value.get("types") if isinstance(value.get("types"), str) else "",
    }


def _personal(state, *, boost=1.0, active=False):
    state = state if isinstance(state, dict) else {}
    total = max(_count(state.get("approximate")), _count(state.get("certain")))
    return {"certain": _count(state.get("certain")), "total": total,
            "log_no_drop": total * math.log1p(-boost / RATE), "boost": boost,
            "matches": int(bool(total or active)), "players": 1, "names": "", "types": ""}


def valid_context(value):
    return (isinstance(value, dict) and type(value.get("version")) is int and value["version"] == 1
            and isinstance(value.get("state"), dict) and isinstance(value.get("personal"), dict)
            and type(value["state"].get("certain")) is int and value["state"]["certain"] >= 0
            and type(value["state"].get("approximate")) is int
            and value["state"]["approximate"] >= value["state"]["certain"]
            and "session_started_at" in value["state"]
            and (value["state"]["session_started_at"] is None
                 or isinstance(value["state"]["session_started_at"], str)))


def reconcile_context(context, state):
    """Advance a GUI snapshot to worker counts without adding the same current match twice."""
    if not isinstance(state, dict):
        state = {}
    if not valid_context(context):
        personal = _personal(state)
        return {"version": 1, "state": dict(state), "personal": personal, "team": None,
                "cumulative": dict(personal), "current_saved": False, "active": False}
    personal = _summary(context["personal"])
    team = _summary(context.get("team"))
    cumulative = _summary(context.get("cumulative")) or dict(personal)
    old = context["state"]
    total = max(_count(state.get("approximate")), _count(state.get("certain")))
    certain = _count(state.get("certain"))
    same_match = old.get("session_started_at") == state.get("session_started_at")
    rate = (personal["log_no_drop"] / personal["total"] if personal["total"] > 0
            else math.log1p(-personal["boost"] / RATE))
    if same_match:
        total_delta = total - old["approximate"]
        certain_delta = certain - old["certain"]
        for summary in (personal, team, cumulative):
            if summary is None:
                continue
            summary["total"] = max(0, summary["total"] + total_delta)
            summary["certain"] = min(summary["total"], max(0, summary["certain"] + certain_delta))
            summary["log_no_drop"] = min(0.0, summary["log_no_drop"] + total_delta * rate)
        previous_matches = personal["matches"]
        personal["matches"] = max(previous_matches, int(total > 0 or context.get("active") is True))
        cumulative["matches"] += personal["matches"] - previous_matches
    else:
        # A saved previous match already belongs to the cumulative result. An unsaved
        # current contribution must be removed before incorporating the new counter.
        if context.get("current_saved") is not True:
            cumulative["total"] = max(0, cumulative["total"] - personal["total"])
            cumulative["certain"] = max(0, cumulative["certain"] - personal["certain"])
            cumulative["log_no_drop"] = min(0.0, cumulative["log_no_drop"] - personal["log_no_drop"])
            cumulative["matches"] = max(0, cumulative["matches"] - personal["matches"])
        personal = _personal(state, boost=personal["boost"], active=context.get("active") is True)
        cumulative["total"] += personal["total"]
        cumulative["certain"] = min(cumulative["total"], cumulative["certain"] + personal["certain"])
        cumulative["log_no_drop"] += personal["log_no_drop"]
        cumulative["matches"] += personal["matches"]
        team = None
    return {**context, "version": 1, "state": dict(state), "personal": personal, "team": team,
            "cumulative": cumulative, "current_saved": context.get("current_saved") is True and same_match,
            "active": context.get("active") is True}


def _types_text(state, thousands):
    raw = state.get("types")
    if not isinstance(raw, dict):
        return None
    kinds = []
    classified = 0
    for kind, row in raw.items():
        if not isinstance(row, dict):
            continue
        count = _count(row.get("approx"))
        classified += count
        if count:
            kinds.append(f"{chest_types.LABELS.get(kind, kind)} {settings.format_count(count, thousands)}")
    rest = max(0, _count(state.get("approximate")) - classified)
    if rest:
        kinds.append(f"not classified {settings.format_count(rest, thousands)}")
    return "Chest types · " + (" · ".join(kinds) or "no chests yet")


def render_sections(display, context):
    """Return personal, team and cumulative text using the same templates for every output."""
    context = context if isinstance(context, dict) else {}
    state = context.get("state") if isinstance(context.get("state"), dict) else {}
    personal = _summary(context.get("personal")) or _personal(state)
    summaries = (personal, _summary(context.get("team")), _summary(context.get("cumulative")) or dict(personal))
    thousands = display.get("use_thousands_separator", True)
    hidden = set()
    for flag, token in (("screen_show_token", "chance"), ("screen_show_matches", "matches"),
                        ("screen_show_types", "types")):
        if not display.get(flag, settings.DEFAULTS["display"][flag]):
            hidden.add(token)
    rendered = []
    for scope, summary in zip(SCOPES, summaries):
        if summary is None or not display.get(f"screen_{scope}_enabled", True):
            rendered.append("")
            continue
        values = {name: settings.format_count(summary[name], thousands)
                  for name in ("certain", "total", "matches", "players")}
        values["approx"] = settings.format_count(summary["total"] - summary["certain"], thousands)
        values["chance"] = f"{-math.expm1(summary['log_no_drop']) * 100 if summary['log_no_drop'] else 0:.6f}%"
        values.update(names=summary["names"], types=summary["types"])
        if scope == "personal":
            current_types = _types_text(state, thousands)
            if current_types is not None:
                values["types"] = current_types
        template = display.get(f"screen_{scope}_template", settings.DEFAULTS["display"][f"screen_{scope}_template"])
        template = template if isinstance(template, str) else ""
        lines = []
        for line in template.replace("\\n", "\n").splitlines():
            if any("{" + token + "}" in line for token in hidden) or "{types}" in line and not values["types"]:
                continue
            for key, value in values.items():
                line = line.replace("{" + key + "}", value)
            if line.strip():
                lines.append(line)
        rendered.append("\n".join(lines))
    return tuple(rendered)


def format_text(display, sections):
    """Use the same section titles in plain text output as in the graphical overlay."""
    parts = []
    for scope, text in zip(SCOPES, sections):
        if not text:
            continue
        title = display.get(f"screen_{scope}_title", settings.DEFAULTS["display"][f"screen_{scope}_title"])
        title = title.strip() if isinstance(title, str) else ""
        parts.append(f"{title}\n{text}" if title else text)
    return "\n\n".join(parts)
