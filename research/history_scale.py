"""How long Analytics takes to read a large history (v0.4.0, M1).

Writes a synthetic history shaped like the maintainer's one real v0.3.0 session (per counted hour: about 180 chests, 40 manual corrections with
their counter_change rows, 60 heartbeats, 6 matches with their transitions; about 130 KB), for HOURS_PER_DAY hours a day over DAYS days, then
times each step of a full Analytics refresh. The files go to the folder given (never into state/), and the rows are encoded by the app's own
encoder, so their size and parsing cost are real.

Run:   python research/history_scale.py OUT_FOLDER [DAYS] [HOURS_PER_DAY]
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fortnite_chest_counter import match_analytics as A
from fortnite_chest_counter import match_history as H
from fortnite_chest_counter import timeline as TL

ZONE = timezone(timedelta(hours=1))


def generate(folder, days, hours_per_day):
    folder.mkdir(parents=True, exist_ok=True)
    matches, chests = open(folder / H.MATCHES, "wb"), open(folder / H.CHESTS, "wb")
    start_day = datetime(2026, 11, 12, 19, 0, tzinfo=ZONE) - timedelta(days=days)
    total = 0
    for day in range(days):
        run_id, n = f"day{day:04d}", 0
        start = start_day + timedelta(days=day)

        def row(kind, offset, **fields):
            nonlocal n
            n += 1
            return H._encode({"kind": kind, "schema": 1, "id": f"{run_id}:{n}", "run_id": run_id, "at": (start + timedelta(seconds=offset)).isoformat(timespec="milliseconds"), **fields})

        seconds = int(hours_per_day * 3600)
        matches.write(row("run_start", 0, source_type="desktop", app_version="0.4.0", configured_analysis_fps=15, languages=["en"], certain_total=0,
                          approximate_total=0, events_logged=0, heartbeat_seconds=60))
        for t in range(0, seconds, 60):
            matches.write(row("heartbeat", t, t=float(t), frames_processed=t * 15, frames_dropped=0,
                              match={"match_number": t // 600 + 1, "opened_t": float(t // 600 * 600), "played_from_t": float(t // 600 * 600 + 60),
                                     "observed_seconds": float(t % 600), "active_seconds": float(t % 600), "spectating_seconds": 0.0,
                                     "uncertain_seconds": 0.0, "english_confirmed": True}))
        for number, opened in enumerate(range(0, seconds, 600), 1):
            matches.write(row("match_opened", opened, t=float(opened), match_number=number, observed_from_start=True, start_confidence="high"))
            for k, state in enumerate(("WAITING", "BUS", "IN_MATCH", "ELIMINATED")):
                matches.write(row("transition", opened + 20 * k, t=float(opened + 20 * k), previous="UNKNOWN", state=state, reason="cue", match_number=number))
            matches.write(row("match_closed", opened + 590, match_number=number, completion="complete", english_confirmed=True, ended_by="placed",
                              observed_from_start=True, opened_t=float(opened), played_from_t=float(opened + 60), ended_t=float(opened + 580),
                              closed_t=float(opened + 590), observed_seconds=590.0, active_seconds=520.0, spectating_seconds=10.0, uncertain_seconds=0.0,
                              complete_duration_seconds=520.0, start_confidence="high", end_confidence="high", discontinuity=False, english_chests=30,
                              portuguese_chests=0, reasons=["you_placed_seen"], evidence=[["you_placed", 0.93]]))
        for k in range(int(hours_per_day * 180)):
            t = 20.0 * k
            chests.write(row("chest", t, counter_epoch=0, event_id=f"E{k + 1:04d}", t=t, certain_counted=k % 3 == 0, approx_counted=True, chest_type="chest",
                             language="en", popup_template="en:CHEST", adjusted_tier="HIGH", detector_source="visual", certain_total=k // 3, approximate_total=k + 1))
        for k in range(int(hours_per_day * 40)):
            t = 90.0 * k
            chests.write(row("chest_correction", t, delta=1, reason="broken_chest", counter_token="x", certain_total=0, approximate_total=0, detector_approximate=0, match_number=int(t // 600) + 1))
            matches.write(row("counter_change", t, action="correction", counter_epoch=k + 1, certain_total=0, approximate_total=0))
        matches.write(row("run_end", seconds, t=float(seconds), stop_reason="stopped", frames_processed=seconds * 15, frames_dropped=0, elapsed_seconds=float(seconds),
                          certain_total=0, approximate_total=0, events_logged=0))
        total += 1
    matches.close()
    chests.close()
    return sum(f.stat().st_size for f in (folder / H.MATCHES, folder / H.CHESTS))


def timed(label, fn):
    begin = time.perf_counter()
    value = fn()
    print(f"  {label:<38} {time.perf_counter() - begin:6.2f} s")
    return value


def main(argv):
    out = Path(argv[0])
    days = int(argv[1]) if len(argv) > 1 else 365
    hours = float(argv[2]) if len(argv) > 2 else 2.0
    size = generate(out, days, hours)
    print(f"{days} days x {hours} h: {size / 1e6:.1f} MB")
    history = timed("read (everything but heartbeats)", lambda: H.read(out, only=A.READ_KINDS))
    print(f"    {len(history.chests):,} chests, {len(history.matches):,} matches, {len(history.chest_corrections):,} corrections")
    timed("match statistics (summarize)", lambda: A.summarize(history))
    runs = timed("runs and sessions", lambda: TL.sessions(TL.runs(history)))
    timed("time counting by day", lambda: TL.counted_by_day([run for session in runs for run in session.runs]))
    timed("last heartbeat of one run", lambda: H.last_heartbeats(out, ["day0000"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
