"""
M4: proves on real video that shadow mode changes nothing. Runs the first 100 s of each reference clip with tracking off and in shadow.

    python research/match_shadow_check.py [--clips en ps5] [--out analysis_output/m4/shadow-check.json]

Checks, per clip: off and shadow give byte-identical events, OBS files and saved counts, and both match the frozen M0 baseline for every
event that began before the last 10 s of the window (the window's early flush can legitimately end a later event differently).
FFmpeg must be the exact build in tests/baselines/v0.3.0-base.txt, first on PATH. One clip at a time. Exit code 1 if anything differs.
"""

import argparse
import glob
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research"))

import regress as G

FFMPEG_SHA256 = "7A1CC6F3E55089F5C0575F14F8BD608CAD4F2CCEF813C9536F876F5B481C83F0"
WINDOW, MARGIN = 100, 10
CLOCK_FIELDS = ("updated_at", "session_started_at", "types_since")


def session(tmp):
    tmp = Path(tmp)
    state = json.loads((tmp / "s.json").read_text(encoding="utf-8"))
    log = [json.loads(line) for line in open(glob.glob(str(tmp / "l" / "*.jsonl"))[0], encoding="utf-8") if line.strip()]
    return ({f.name: f.read_bytes() for f in sorted((tmp / "o").iterdir())}, {k: v for k, v in state.items() if k not in CLOCK_FIELDS},
            [row for row in log if row.get("event") == "match_state"])


def check(clip):
    video = ROOT / G.CLIPS[clip][1]
    with tempfile.TemporaryDirectory() as off_dir, tempfile.TemporaryDirectory() as shadow_dir:
        off = G.run_clip(video, off_dir, until=WINDOW)
        shadow = G.run_clip(video, shadow_dir, match_mode="shadow", until=WINDOW)
        off_obs, off_state, off_lines = session(off_dir)
        shadow_obs, shadow_state, shadow_lines = session(shadow_dir)
    frozen = json.loads((ROOT / "tests" / "baselines" / f"{clip}_v0.3.0-base.json").read_text(encoding="utf-8"))
    compared = [e for e in frozen if e["time"] < WINDOW - MARGIN]
    summary = next((row for row in shadow_lines if row["kind"] == "summary"), None)
    checks = {"events_identical": off == shadow, "obs_identical": off_obs == shadow_obs, "state_identical": off_state == shadow_state,
              "off_wrote_no_match_lines": off_lines == [], "shadow_wrote_a_summary": summary is not None,
              "tracker_did_not_fail": summary is not None and not summary["match_failed"],
              "matches_m0": [e for e in shadow if e["time"] < WINDOW - MARGIN] == compared}
    return {"clip": clip, "window_seconds": WINDOW, "events": len(shadow), "m0_events_compared": len(compared),
            "certain": shadow_state["certain"], "approximate": shadow_state["approximate"], "checks": checks, "summary": summary,
            "transitions": [(row["t"], row["state"], row["reason"]) for row in shadow_lines if row["kind"] == "transition"],
            "records": [row for row in shadow_lines if row["kind"] == "record"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clips", nargs="+", default=["en", "ps5"])
    parser.add_argument("--out", type=Path, help="also write the results as JSON")
    args = parser.parse_args()
    ffmpeg = shutil.which("ffmpeg")
    digest = hashlib.sha256(Path(ffmpeg).read_bytes()).hexdigest().upper() if ffmpeg else None
    if digest != FFMPEG_SHA256:
        print(f"ERROR: FFmpeg on PATH is not the M0 build: {ffmpeg} ({digest})", file=sys.stderr)
        return 2
    results, passed = [], True
    for clip in args.clips:
        print(f"{clip}: first {WINDOW} s, off then shadow ...", flush=True)
        result = check(clip)
        results.append(result)
        passed &= all(result["checks"].values())
        for name, ok in result["checks"].items():
            print(f"  {'ok  ' if ok else 'FAIL'}  {name}")
        print(f"  {result['events']} events, {result['m0_events_compared']} compared with M0, CERTAIN {result['certain']}, APPROX {result['approximate']}")
        print(f"  tracker: {result['summary']}")
        print(f"  transitions: {result['transitions']}", flush=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
