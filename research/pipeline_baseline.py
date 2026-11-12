"""
The real pipeline on one recording, with the evidence regress.py does not keep (v0.4.1 M0).

    python research/pipeline_baseline.py VIDEO OUT_DIR [--match-mode on] [--until SECONDS] [--set NAME=VALUE ...]

Runs `simulate` (every frame at 15 fps through the real ChestEstimator and, with match tracking on, the real MatchTracker) in a fresh
process, in a temporary folder of its own: an explicit --state, --obs-dir and --log-dir, so no profile, history, count or OBS file of the
user's is read or written. It refuses to run where a config.toml would be picked up. Writes to OUT_DIR:

    events.json          the chest events in research/regress.py's snapshot format
    observations.json.gz every Observation the match state machine received (exactly what live tracking would feed it)
    matches.json         the match_state lines of the session log (records, transitions, summary)
    timing.json          detector time per frame (mean, percentiles, max), process CPU and wall time, frames processed

Times are measured in this process only: the FFmpeg decoder runs in its own process and is not included.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS = ("time", "source", "popup_score", "popup_template", "base_tier", "adjusted_tier", "shooting_negative", "ammo_steps",
        "interaction_score", "sprite_present", "certain_counted", "approx_counted")

CHILD = r'''
import ast, gzip, json, sys, time
from dataclasses import asdict
import numpy as np
import fortnite_chest_counter.estimator as E
import fortnite_chest_counter.match_state as S
argv, out, sets = json.loads(sys.argv[1]), sys.argv[2], json.loads(sys.argv[3])
for k, v in sets:
    setattr(E, k, ast.literal_eval(v))
observations, frame_ms = [], []
_update, _frame = S.MatchStateMachine.update, E.ChestEstimator.process_frame

def update(self, observation):
    d = asdict(observation)
    d["scores"] = {k: round(float(v), 4) for k, v in d["scores"].items() if v}
    d["chests"] = list(d["chests"])
    observations.append(d)
    return _update(self, observation)

def process_frame(self, t, frame):
    a = time.perf_counter()
    try:
        return _frame(self, t, frame)
    finally:
        frame_ms.append(1000 * (time.perf_counter() - a))

S.MatchStateMachine.update, E.ChestEstimator.process_frame = update, process_frame
from fortnite_chest_counter.counter import main
cpu0, wall0 = time.process_time(), time.perf_counter()
code = main(argv)
cpu, wall = time.process_time() - cpu0, time.perf_counter() - wall0
with gzip.open(out + "/observations.json.gz", "wt", encoding="utf-8") as f:
    json.dump(observations, f, separators=(",", ":"))
ms = np.array(frame_ms)
json.dump({"frames": len(ms), "detector_ms": {"mean": round(float(ms.mean()), 3), "p50": round(float(np.percentile(ms, 50)), 3),
           "p95": round(float(np.percentile(ms, 95)), 3), "p99": round(float(np.percentile(ms, 99)), 3), "max": round(float(ms.max()), 3)},
           "process_cpu_s": round(cpu, 2), "wall_s": round(wall, 2), "exit": code},
          open(out + "/timing.json", "w", encoding="utf-8"), indent=1)
sys.exit(code)
'''


def run(video, out_dir, match_mode="on", sets=(), until=None):
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if (Path.cwd() / "config.toml").exists():
        raise SystemExit("a config.toml in the current folder would be used by simulate; run from a folder without one")
    with tempfile.TemporaryDirectory(prefix="fcc_baseline_") as tmp:
        tmp = Path(tmp)
        argv = ["simulate", "--video", str(Path(video).resolve()), "--reset", "--no-evaluate", "--state", str(tmp / "state" / "s.json"),
                "--obs-dir", str(tmp / "obs"), "--log-dir", str(tmp / "logs")]
        argv += ["--match-mode", match_mode] if match_mode else []
        argv += ["--until", str(until)] if until is not None else []
        env_path = str(ROOT / "src")
        subprocess.run([sys.executable, "-B", "-c", CHILD, json.dumps(argv), str(out_dir), json.dumps([s.split("=", 1) for s in sets])],
                       check=True, stdout=subprocess.DEVNULL, env={**__import__("os").environ, "PYTHONPATH": env_path})
        rows = [json.loads(line) for log in (tmp / "logs").glob("*.jsonl") for line in log.open(encoding="utf-8") if line.strip()]
    events = []
    for e in rows:
        if "time" in e and e.get("source") != "manual":
            r = {k: e.get(k) for k in KEYS}
            r["chest_object"] = e.get("chest_object_gold") is not None
            events.append(r)
    (out_dir / "events.json").write_text(json.dumps(events, indent=1) + "\n", encoding="utf-8", newline="\n")
    matches = [{k: v for k, v in e.items() if k != "logged_at"} for e in rows if e.get("event") == "match_state"]
    (out_dir / "matches.json").write_text(json.dumps(matches, indent=1) + "\n", encoding="utf-8", newline="\n")
    return events, matches, json.loads((out_dir / "timing.json").read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--match-mode", default="on")
    ap.add_argument("--until", type=float, help="stop at this video time (seconds)")
    ap.add_argument("--set", dest="sets", action="append", default=[])
    a = ap.parse_args()
    events, matches, timing = run(a.video, a.out, a.match_mode, a.sets, a.until)
    print(f"{len(events)} events, CERTAIN {sum(e['certain_counted'] for e in events)}, APPROX {sum(e['approx_counted'] for e in events)}")
    for m in matches:
        if m.get("kind") == "record":
            print(f"match {m['match_number']}: {m['completion']}, opened {m['opened_t']}, closed {m['closed_t']}, ended by {m['ended_by']}, "
                  f"active {m['active_seconds']} s")
    print("timing:", json.dumps(timing))


if __name__ == "__main__":
    main()
