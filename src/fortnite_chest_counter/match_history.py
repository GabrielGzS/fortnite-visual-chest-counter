"""
Match history (v0.3.0, M5, M6): the durable evidence later statistics are calculated from. Written only when [match] mode = "on".

    state/history/<profile id>/matches.jsonl    runs, heartbeats, state changes, matches, counter changes, gaps, corrections
    state/history/<profile id>/chests.jsonl     counted chests and later chest-type changes

Both files are append-only, one JSON row per line. Rows hold what was observed and never a calculated average, so any statistic can be
recalculated when its formula improves. History never feeds the totals: profile totals stay authoritative, and no repair changes them.

Every row has "kind", "schema" and "id". The id is assigned once, so a row retried after an uncertain write is recognised as the same row.
A row from a newer schema is skipped with a notice and never rewritten. A damaged line is skipped.

    what             identified by
    a run            run_id: one counting session, from start to stop
    a match          run_id + match_number
    a counted chest  run_id + counter_epoch + event_id

The epoch is what makes a chest's identity safe. A Reset restarts event ids during a run, so E0001 can really be two chests; each counter
restart starts a new epoch. Identity does not use source time at all, so a jump in the video cannot confuse it. Time is only data.

Times come in two kinds, and neither stands in for the other: "t" is seconds of source time within the run, and "at" is the wall clock.
For a livestream the two drift apart while it buffers.

Totals are saved first and history second, so an interrupted write can only leave history behind the totals, never ahead:
  * a failed write is kept and retried in order with the next one, so a short lock loses nothing;
  * rows really lost become a "gap" row, and so does any difference found at the next start;
  * a match left open by a crash is closed as interrupted using only the time a heartbeat had reported. The rest is uncertain.

Nothing here may reach the counter: every writer call contains its own errors and warns once. KeyboardInterrupt is left alone.
"""

import functools
import json
from bisect import bisect_right
import os
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

SCHEMA = 1
MATCHES, CHESTS = "matches.jsonl", "chests.jsonl"
MAX_WAITING = 20000                        # rows held while the disk refuses them, roughly 6 MB; far more than a long session writes
INTERRUPTED, WRITE_FAILED, TOTALS_LOWERED = "interrupted", "write_failed", "totals_lowered"

MATCH_FIELDS = ("match_number", "completion", "english_confirmed", "ended_by", "observed_from_start", "opened_t", "played_from_t", "ended_t", "closed_t",
                "observed_seconds", "active_seconds", "spectating_seconds", "uncertain_seconds", "complete_duration_seconds", "start_confidence",
                "end_confidence", "discontinuity", "english_chests", "portuguese_chests", "reasons", "evidence")
SNAPSHOT_FIELDS = ("match_number", "opened_t", "played_from_t", "observed_seconds", "active_seconds", "spectating_seconds", "uncertain_seconds", "english_confirmed")
RUN_KINDS = frozenset({"run_start", "run_end"})
MATCH_KINDS = RUN_KINDS | {"match_opened", "match_closed", "correction", "gap"}     # enough to list matches, without the bulk
CORRECTION_KINDS = frozenset({"chest_correction", "chest_correction_undone", "chest_correction_reason"})
# Why a chest count was corrected. Only "missed" and "false_positive" are claims about the detector: Fortnite can count a chest with nothing
# on screen to detect, so "not_visible" is no failure, and "manual" means the reason is not known. "broken_chest" (M9H) is a chest Fortnite
# counted when a chest was broken rather than opened: no failure either, and kept apart so broken chests can be counted. Stored as these ids.
MISSED, NOT_VISIBLE, FALSE_POSITIVE, MANUAL, BROKEN_CHEST = "missed", "not_visible", "false_positive", "manual", "broken_chest"


def _now():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def new_run_id():
    return f"{datetime.now():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"


def chest_language(popup_template):
    prefix = str(popup_template or "").split(":")[0]
    return prefix if prefix in ("en", "pt") else "unknown"


def _encode(row):
    text = json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    return text.encode("utf-8") + b"\n"


def _append_line(path, line):
    """One whole row, on its own line even if the last write was cut off, and on disk before returning."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell():
            stream.seek(-1, os.SEEK_END)
            if stream.read(1) != b"\n":
                line = b"\n" + line
            stream.seek(0, os.SEEK_END)
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())


def _contained(method):
    @functools.wraps(method)
    def call(self, *args, **kwargs):
        if self._ended:
            return None
        try:
            return method(self, *args, **kwargs)
        except Exception as error:
            self._warn_once(f"{type(error).__name__}: {error}")
            return None
    return call


class HistoryWriter:
    """Appends one run to a profile's history. `warn` takes one message for the user."""

    def __init__(self, folder, warn, run_id=None, now=_now):
        self.folder, self.run_id = Path(folder), run_id or new_run_id()
        self._warn, self._now = warn, now
        self._n = 0
        self._waiting = deque()
        self._lost = {"rows": 0, "certain": 0, "approximate": 0}
        self._warned = self._ended = False
        self._epoch = self._restart_epoch = self._last_event = 0
        self._seen = {}                    # (event_id, t to the millisecond) -> the epoch it was recorded in
        self._opened = self._beat = None   # the open match's row and the last checkpoint, for closing it if the tracker cannot

    # ------------------------------------------------------------------ a run
    @_contained
    def start_run(self, source_type, app_version, configured_analysis_fps, languages, certain, approximate, events_logged, heartbeat_seconds=None):
        """Recovers any run that never finished, then opens this one. `configured_analysis_fps` is the setting, not the rate achieved:
        run_end and heartbeats carry the frames really processed."""
        self._recover(certain, approximate)
        self._add(MATCHES, "run_start", source_type=source_type, app_version=app_version, configured_analysis_fps=configured_analysis_fps,
                  languages=list(languages), certain_total=certain, approximate_total=approximate, events_logged=events_logged, heartbeat_seconds=heartbeat_seconds)

    @_contained
    def heartbeat(self, t, frames_processed, frames_dropped, match=None):
        """`match` is the open match's running totals, the only time a crash can later claim was observed."""
        snapshot = {key: match[key] for key in SNAPSHOT_FIELDS} if match is not None else None
        self._add(MATCHES, "heartbeat", t=t, frames_processed=frames_processed, frames_dropped=frames_dropped, match=snapshot)
        self._beat = {"t": t, "match": snapshot}

    @_contained
    def end_run(self, t, stop_reason, frames_processed, frames_dropped, elapsed_seconds, certain, approximate, events_logged):
        if self._opened is not None:                   # the tracker stopped early, so nothing closed this match
            self._close_interrupted(self.run_id, self._opened, self._beat, False)
            self._opened = None
        self._add(MATCHES, "run_end", t=t, stop_reason=stop_reason, frames_processed=frames_processed, frames_dropped=frames_dropped,
                  elapsed_seconds=elapsed_seconds, certain_total=certain, approximate_total=approximate, events_logged=events_logged)
        self._ended = True

    # ------------------------------------------------------------------ what happened in it
    @_contained
    def transition(self, event):
        self._add(MATCHES, "transition", **{key: event[key] for key in ("t", "previous", "state", "reason", "match_number")})

    @_contained
    def match_opened(self, event):
        row = {key: event[key] for key in ("t", "match_number", "observed_from_start", "start_confidence")}
        self._add(MATCHES, "match_opened", **row)
        self._opened = row

    @_contained
    def match_closed(self, record):
        """A finished match_state.MatchRecord, as a dict. `respawns` is left out: it cannot be measured yet, and 0 would read as "no reboots"."""
        row = {key: record[key] for key in MATCH_FIELDS}
        row["evidence"] = sorted(row["evidence"], key=lambda item: (item[0], item[1]))            # M2 gathers these from a set
        self._add(MATCHES, "match_closed", **row)
        if self._opened is not None and self._opened["match_number"] == record["match_number"]:
            self._opened = None

    @_contained
    def chest(self, ev, certain_total, approximate_total):
        """A counted chest, after the totals were saved. -> True if recorded. The same event given twice is recorded once."""
        if not (ev.get("certain_counted") or ev.get("approx_counted")):
            return False
        event_id, t = ev["event_id"], ev["time"]
        key = event_id, round(t, 3)
        if self._seen.get(key, -1) >= self._restart_epoch:
            return False
        number = int(event_id[1:])
        if number <= self._last_event:                 # the counter restarted without anyone saying so
            self._epoch += 1
        self._last_event = number
        self._seen[key] = self._epoch
        self._add(CHESTS, "chest", counter_epoch=self._epoch, event_id=event_id, t=t, certain_counted=bool(ev.get("certain_counted")),
                  approx_counted=bool(ev.get("approx_counted")), chest_type=ev.get("chest_type"), language=chest_language(ev.get("popup_template")),
                  popup_template=ev.get("popup_template"), adjusted_tier=ev.get("adjusted_tier"), detector_source=ev.get("source"),
                  certain_total=certain_total, approximate_total=approximate_total)
        return True

    @_contained
    def chest_type(self, event_id, t, chest_type):
        """The detector read a counted chest's type better afterwards. A new row; the chest row is never rewritten."""
        epoch = self._seen.get((event_id, round(t, 3)))
        if epoch is not None:
            self._add(CHESTS, "chest_type", counter_epoch=epoch, event_id=event_id, chest_type=chest_type)

    @_contained
    def counter_changed(self, action, certain_total, approximate_total):
        """Reset, Edit counts or Set starting count during this run. History keeps its chests; the totals simply move."""
        self._epoch += 1
        self._restart_epoch, self._last_event = self._epoch, 0
        self._add(MATCHES, "counter_change", action=action, counter_epoch=self._epoch, certain_total=certain_total, approximate_total=approximate_total)

    # ------------------------------------------------------------------ writing
    def _add(self, name, kind, **fields):
        self._n += 1
        line = _encode({"kind": kind, "schema": SCHEMA, "id": f"{self.run_id}:{self._n}", "run_id": self.run_id, "at": self._now(), **fields})
        self._flush()
        if len(self._waiting) >= MAX_WAITING:
            self._lost["rows"] += 1
            if kind == "chest":
                self._lost["certain"] += int(fields["certain_counted"])
                self._lost["approximate"] += int(fields["approx_counted"])
            return
        self._waiting.append((name, line))
        self._flush()

    def _flush(self):
        while self._waiting:
            name, line = self._waiting[0]
            try:
                self._append(name, line)
            except OSError as error:
                self._warn_once(str(error))
                return
            self._waiting.popleft()
        if self._lost["rows"]:
            lost, self._lost = self._lost, {"rows": 0, "certain": 0, "approximate": 0}
            self._add(MATCHES, "gap", reason=WRITE_FAILED, match_number=self._opened["match_number"] if self._opened else None, lost_rows=lost["rows"],
                      missing_certain=lost["certain"], missing_approximate=lost["approximate"])

    def _append(self, name, line):
        _append_line(self.folder / name, line)

    def _warn_once(self, detail):
        if self._warned:
            return
        self._warned = True
        try:
            self._warn(f"match history could not be saved ({detail}); counting is not affected")
        except Exception:
            pass

    # ------------------------------------------------------------------ after a crash
    @_contained
    def _recover(self, certain, approximate):
        if all(run["end"] is not None or run["start"] is None for run in read(self.folder, only=RUN_KINDS).runs.values()):
            return                                     # nothing crashed: skip reading all of it, as this runs at every start
        history = read(self.folder)
        started = [run_id for run_id, run in history.runs.items() if run["start"] is not None]
        for run_id in started:
            run = history.runs[run_id]
            if run["end"] is not None:
                continue
            open_matches = [row for row in history.open_matches if row["run_id"] == run_id]
            # Only the newest run can be compared with today's totals. Totals below history were lowered by hand, not lost by history.
            missing = (certain - run["totals"][0], approximate - run["totals"][1]) if run_id == started[-1] else (0, 0)
            lost = any(value > 0 for value in missing)
            for opened in open_matches:
                self._close_interrupted(run_id, opened, run["last_heartbeat"], lost)
            if any(missing) and not any(g["run_id"] == run_id and g["reason"] in (INTERRUPTED, TOTALS_LOWERED) for g in history.gaps):
                self._add(MATCHES, "gap", run_id=run_id, reason=INTERRUPTED if lost else TOTALS_LOWERED, match_number=open_matches[-1]["match_number"] if lost and open_matches else None,
                          lost_rows=None, missing_certain=missing[0], missing_approximate=missing[1])
            beat = run["last_heartbeat"] or {}
            self._add(MATCHES, "run_end", run_id=run_id, interrupted=True, stop_reason=INTERRUPTED, t=beat.get("t"), last_seen_at=beat.get("at", run["start"]["at"]),
                      frames_processed=beat.get("frames_processed"), frames_dropped=beat.get("frames_dropped"), elapsed_seconds=None)

    def _close_interrupted(self, run_id, opened, beat, history_incomplete):
        """Always partial or unconfirmed, whatever had been seen. Time a heartbeat did not report is uncertain, never played."""
        number = opened["match_number"]
        snapshot = beat["match"] if beat is not None and beat.get("match") and beat["match"]["match_number"] == number else None
        opened_t = snapshot["opened_t"] if snapshot else opened["t"]
        closed_t = max(beat["t"] if beat is not None else opened["t"], opened_t)
        span = closed_t - opened_t
        observed = min(snapshot["observed_seconds"], span) if snapshot else 0.0
        active = min(snapshot["active_seconds"], observed) if snapshot else 0.0
        spectating = min(snapshot["spectating_seconds"], observed - active) if snapshot else 0.0
        confirmed = bool(snapshot and snapshot["english_confirmed"])
        self._add(MATCHES, "match_closed", run_id=run_id, match_number=number, completion="partial" if confirmed else "unconfirmed", english_confirmed=confirmed,
                  ended_by=INTERRUPTED, observed_from_start=opened["observed_from_start"], opened_t=opened_t, played_from_t=snapshot["played_from_t"] if snapshot else opened_t,
                  ended_t=None, closed_t=closed_t, observed_seconds=round(observed, 3), active_seconds=round(active, 3), spectating_seconds=round(spectating, 3),
                  uncertain_seconds=round(span - observed, 3), complete_duration_seconds=None, start_confidence=opened["start_confidence"], end_confidence="low",
                  discontinuity=True, english_chests=None, portuguese_chests=None, reasons=["interrupted: no close was written"], evidence=[], interrupted=True,
                  history_incomplete=history_incomplete)


def attribute(history):
    """Each chest with the match it belongs to, worked out from its own time, so correcting a match never rewrites a chest. -> new dicts with
    match_number (None outside every match), spectating (after the player was out), and credited (during this player's active play)."""
    by_run, out_at = {}, {}
    for match in sorted(history.matches, key=lambda m: m["opened_t"]):
        by_run.setdefault(match["run_id"], []).append(match)
    starts = {run_id: [m["opened_t"] for m in matches] for run_id, matches in by_run.items()}
    for row in history.transitions:
        if row["state"] == "ELIMINATED" and row["match_number"] is not None:
            out_at.setdefault((row["run_id"], row["match_number"]), row["t"])
    result = []
    for chest in history.chests:
        t, run_id = chest["t"], chest["run_id"]
        index = bisect_right(starts.get(run_id, ()), t) - 1                # matches in a run never overlap: only the latest to open can hold it
        match = by_run[run_id][index] if index >= 0 and t < by_run[run_id][index]["closed_t"] else None
        if match is None:
            result.append({**chest, "match_number": None, "spectating": False, "credited": False})
            continue
        moments = [m for m in (out_at.get((chest["run_id"], match["match_number"])), match.get("ended_t")) if m is not None]
        spectating = bool(moments) and t >= min(moments)
        result.append({**chest, "match_number": match["match_number"], "spectating": spectating,
                       "credited": match["played_from_t"] <= t and not spectating and not match["not_a_match"]})
    return result


def append_chest_correction(folder, correction_id, run_id, delta, reason, counter_token, certain, approximate, detector_approximate, match_number=None):
    """A +1 or -1 the user made to the total, after the total was saved. Raises OSError if it cannot be saved.
    `match_number`: the match of this run it was made for (the Game view's buttons), or None for one made to the total alone (Overview)."""
    row = {"kind": "chest_correction", "schema": SCHEMA, "id": correction_id, "run_id": run_id, "at": _now(), "delta": delta, "reason": reason, "counter_token": counter_token,
           "certain_total": certain, "approximate_total": approximate, "detector_approximate": detector_approximate}
    if match_number is not None:
        row["match_number"] = match_number
    _append_line(Path(folder) / CHESTS, _encode(row))


def corrections_by_match(corrections):
    """{(run_id, match_number): [added, removed, broken chests among the added]} of the corrections still standing that were made for a match."""
    out = {}
    for c in corrections:
        number = c.get("match_number")
        if not c["undone"] and isinstance(number, int) and not isinstance(number, bool):
            tally = out.setdefault((c.get("run_id"), number), [0, 0, 0])
            tally[0 if c["delta"] > 0 else 1] += 1
            tally[2] += c["delta"] > 0 and c.get("reason") == BROKEN_CHEST
    return out


def append_correction_undone(folder, undo_id, run_id, undoes, certain, approximate):
    """Undoing keeps the original row and adds this one, so the history of what was corrected is never lost."""
    _append_line(Path(folder) / CHESTS, _encode({"kind": "chest_correction_undone", "schema": SCHEMA, "id": undo_id, "run_id": run_id, "at": _now(), "undoes": undoes, "certain_total": certain, "approximate_total": approximate}))


def set_correction_reason(folder, correction_id, reason):
    """Say why after the fact. A new row: the latest wins, and no total changes."""
    _append_line(Path(folder) / CHESTS, _encode({"kind": "chest_correction_reason", "schema": SCHEMA, "id": f"reason:{uuid.uuid4().hex}", "at": _now(), "corrects": correction_id, "reason": reason}))


def _merge_corrections(rows):
    merged = {}
    for row in rows:
        if row["kind"] == "chest_correction" and row.get("delta") in (1, -1):
            merged.setdefault(row["id"], {**row, "undone": False})
    for row in rows:
        if row["kind"] == "chest_correction_undone" and row.get("undoes") in merged:
            merged[row["undoes"]]["undone"] = True
        elif row["kind"] == "chest_correction_reason" and row.get("corrects") in merged:
            merged[row["corrects"]]["reason"] = row.get("reason")
    return list(merged.values())


def read_chest_corrections(folder):
    """Every correction ever made in this profile, oldest first, with its latest reason and whether it was undone."""
    return _merge_corrections(list(_rows(Path(folder) / CHESTS, CORRECTION_KINDS, History())))


def correction_totals(corrections, counter_token=None):
    """What still stands. Given a token, only this life of the counter: a Reset or Edit counts replaces the total, and with it earlier corrections."""
    standing = [c for c in corrections if not c["undone"] and (counter_token is None or c.get("counter_token") == counter_token)]
    reasons = [c.get("reason") for c in standing]
    return {"net": sum(c["delta"] for c in standing), "added": sum(c["delta"] == 1 for c in standing), "removed": sum(c["delta"] == -1 for c in standing), "standing": standing,
            "reversed": sum(c["undone"] for c in corrections), "detector_misses": reasons.count(MISSED), "detector_false_positives": reasons.count(FALSE_POSITIVE),
            "not_visible": reasons.count(NOT_VISIBLE), "broken_chests": reasons.count(BROKEN_CHEST),
            "unknown": len(reasons) - reasons.count(MISSED) - reasons.count(FALSE_POSITIVE) - reasons.count(NOT_VISIBLE) - reasons.count(BROKEN_CHEST)}


def correct_match(folder, run_id, match_number, not_a_match=True):
    """Mark a match as "Not a match", or undo it. A new row: the latest wins, and no chest row or total changes. Raises OSError if it cannot be saved."""
    _append_line(Path(folder) / MATCHES, _encode({"kind": "correction", "schema": SCHEMA, "id": f"correction:{uuid.uuid4().hex}", "run_id": run_id, "at": _now(),
                                                  "match_number": match_number, "not_a_match": bool(not_a_match)}))


# ---------------------------------------------------------------------- reading

@dataclass
class History:
    runs: dict = field(default_factory=dict)                  # run_id -> {"start", "end", "last_heartbeat", "totals"}
    matches: list = field(default_factory=list)               # closed matches, with not_a_match and history_incomplete settled
    open_matches: list = field(default_factory=list)          # opened, and not closed (yet)
    chests: list = field(default_factory=list)                # one per chest, with its latest chest_type
    transitions: list = field(default_factory=list)
    counter_changes: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    chest_corrections: list = field(default_factory=list)     # the user's +1 and -1, with their latest reason
    bad_lines: int = 0
    newer_rows: int = 0


def _parse(line):
    try:
        row = json.loads(line)
    except ValueError:
        return None
    return row if isinstance(row, dict) and isinstance(row.get("kind"), str) and isinstance(row.get("id"), str) and type(row.get("schema")) is int and row["schema"] >= 1 else None


def _rows(path, only, history):
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return
    seen = set()
    wanted = None if only is None else {kind.encode() for kind in only}
    for line in data.split(b"\n"):
        if not line:
            continue
        if wanted is not None and line.startswith(b'{"kind":"') and line[9:line.find(b'"', 9)] not in wanted:
            continue
        row = _parse(line)
        if row is None:
            history.bad_lines += 1
        elif row["schema"] > SCHEMA:
            history.newer_rows += 1
        elif row["id"] not in seen:
            seen.add(row["id"])
            yield row


def _run(history, run_id):
    return history.runs.setdefault(run_id, {"start": None, "end": None, "last_heartbeat": None, "totals": (0, 0), "_order": -1})


def _note_totals(run, row):
    """The newest counts this run wrote, in the order its own writer made them."""
    order = int(row["id"].rpartition(":")[2])
    if order > run["_order"]:
        run["_order"], run["totals"] = order, (row["certain_total"], row["approximate_total"])


def read(folder, only=None, warn=None):
    """Everything in a profile's history. `only` limits it to some row kinds, skipping the rest cheaply. Reading never creates or changes a file."""
    folder, history = Path(folder), History()
    opened, closed, corrections, chests = {}, {}, {}, {}
    for row in _rows(folder / MATCHES, only, history):
        try:
            kind, run_id = row["kind"], row["run_id"]
            run = _run(history, run_id)
            if kind == "run_start":
                run["start"] = row
                _note_totals(run, row)
            elif kind == "run_end":
                run["end"] = run["end"] or row
                if "certain_total" in row:
                    _note_totals(run, row)
            elif kind == "heartbeat":
                run["last_heartbeat"] = row
            elif kind == "transition":
                history.transitions.append(row)
            elif kind == "match_opened":
                opened[run_id, row["match_number"]] = row
            elif kind == "match_closed":
                key = run_id, row["match_number"]
                if key not in closed or closed[key].get("interrupted"):
                    closed[key] = row
            elif kind == "counter_change":
                history.counter_changes.append(row)
                _note_totals(run, row)
            elif kind == "gap":
                history.gaps.append(row)
            elif kind == "correction":
                corrections[run_id, row["match_number"]] = row["not_a_match"]
        except (KeyError, TypeError, ValueError, AttributeError):
            history.bad_lines += 1
    correction_rows = []
    for row in _rows(folder / CHESTS, only, history):
        if row["kind"] in CORRECTION_KINDS:
            correction_rows.append(row)
            continue
        try:
            key = row["run_id"], row["counter_epoch"], row["event_id"]
            if row["kind"] == "chest":
                _note_totals(_run(history, row["run_id"]), row)
                chests.setdefault(key, dict(row))
            elif row["kind"] == "chest_type" and key in chests:
                chests[key]["chest_type"] = row["chest_type"]
        except (KeyError, TypeError, ValueError, AttributeError):
            history.bad_lines += 1
    incomplete = {(g["run_id"], g["match_number"]) for g in history.gaps if g.get("match_number") is not None}
    history.matches = [{**row, "not_a_match": corrections.get(key, False), "history_incomplete": bool(row.get("history_incomplete")) or key in incomplete} for key, row in closed.items()]
    history.open_matches = [row for key, row in opened.items() if key not in closed]
    history.chests = list(chests.values())
    history.chest_corrections = _merge_corrections(correction_rows)
    if history.newer_rows and warn is not None:
        warn(f"{history.newer_rows} match history rows were written by a newer version; they were left alone and skipped")
    return history
