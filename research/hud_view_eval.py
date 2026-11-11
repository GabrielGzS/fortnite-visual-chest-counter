"""
Can the fixed parts of the game's HUD tell gameplay from something else on screen? Samples one frame per second; runs no chest detection.

    python research/hud_view_eval.py --capture "<...>/captures/20261108_233437" --small-capture <a copy of captures/20261111_071106> [--ffmpeg <exe>] [--write-templates] [--write-fixtures]

Templates are the average edges of many seconds of play, so terrain, numbers and icons blur away and only the fixed shapes remain: one source per HUD
size (normal: the NEW video; small: the PS5 video). Everything else is held out: another creator at each size, and the browser pages.
Exit code 0 only when held-out play is seen, the browser pages are not, and no stretch of play goes unseen for GAME_OUT_OF_VIEW seconds.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fortnite_chest_counter import match_cues as M                                 # noqa: E402
from fortnite_chest_counter import match_state as S                                # noqa: E402

BUILT_FROM = {"stats": "new", "compass": "new", "stats_small": "ps5", "compass_small": "ps5"}
NEW, PS5 = "Fortnites-NEW-HD-No-Audio.mp4", "Fortnite-PS5-Pro-HD-No-Audio.mp4"
BROWSER = {"small": range(4, 20), "case_20261108_054841_seg_00000": range(10), "case_20261108_054841_seg_00001": range(10)}     # labelled by eye
BUDGET_MS = 5.0


def sources(capture, small_capture):
    samples = ROOT / "samples" / "video tests"
    for number in (1, 2, 3):
        yield f"clip{number}", ["-f", "concat", "-safe", "0", "-i", str(Path(capture) / "video" / f"clip_{number:03d}.ffconcat")]
    yield "small", ["-f", "concat", "-safe", "0", "-i", str(Path(small_capture) / "video" / "clip_small.ffconcat")]
    yield "new", ["-i", str(samples / NEW)]
    yield "ps5", ["-i", str(samples / PS5)]
    for segment in sorted((ROOT / "samples" / "cases").glob("*/video/seg_*.mkv")):
        yield f"case_{segment.parent.parent.name}_{segment.stem}", ["-i", str(segment)]


def frames(ffmpeg, inputs):
    process = subprocess.Popen([ffmpeg, "-v", "error", "-nostdin", "-threads", "4", *inputs, "-vf", "fps=1,scale=1280:720", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, bufsize=10 ** 7)
    size = 1280 * 720 * 3
    while len(raw := process.stdout.read(size)) == size:
        yield np.frombuffer(raw, np.uint8).reshape(720, 1280, 3)
    process.wait()


def write_templates(ffmpeg, all_sources):
    """Average each cue's edges over the source it is built from, during play, and keep the pixels that are an edge in most frames."""
    M.HUD_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    reader = M.CueReader()
    for source in sorted(set(BUILT_FROM.values())):
        cues = [cue for cue in M.HUD_CUES if BUILT_FROM[cue.name] == source]
        sums, count, machine, previous, t = {cue.name: 0.0 for cue in cues}, 0, S.MatchStateMachine(), None, 0
        for frame in frames(ffmpeg, all_sources[source]):
            picture, health = M.picture_evidence(frame, previous), M.health_bar_pixels(frame)
            previous = picture.sample
            machine.update(S.Observation(float(t), reader.read(frame), health, bool(picture.black), bool(picture.frozen), ()))
            t += 1
            if machine.state == S.IN_MATCH and health >= S.HEALTH_BAR_MIN_PIXELS:
                count += 1
                for cue in cues:
                    sums[cue.name] = sums[cue.name] + M.hud_edges(frame, cue.box, 0)
        for cue in cues:
            share = sums[cue.name] / count
            template = (share >= max(0.30, np.percentile(share, 85))).astype(np.float32)
            np.save(M.HUD_TEMPLATE_DIR / f"{cue.name}.npy", template)
            print(f"wrote {cue.name}: {template.shape}, {int(template.sum())} pixels, from {count} seconds of {source}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capture", required=True)
    parser.add_argument("--small-capture", required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--write-templates", action="store_true")
    parser.add_argument("--write-fixtures", action="store_true")
    arguments = parser.parse_args()
    all_sources = dict(sources(arguments.capture, arguments.small_capture))
    if arguments.write_templates:
        write_templates(arguments.ffmpeg, all_sources)

    reader, rows, cost = M.CueReader(), [], []
    for source, inputs in all_sources.items():
        machine, previous, t = S.MatchStateMachine(), None, 0
        for frame in frames(arguments.ffmpeg, inputs):
            frame.flags.writeable = False
            begin = time.perf_counter()
            seen = reader.hud_in_view(frame)
            cost.append(1000 * (time.perf_counter() - begin))
            scores, health, picture = reader.read(frame), M.health_bar_pixels(frame), M.picture_evidence(frame, previous)
            previous = picture.sample
            machine.update(S.Observation(float(t), scores, health, bool(picture.black), bool(picture.frozen), ()))
            masks = {cue.name: M.hud_edges(frame, cue.box, M.HUD_SEARCH) for cue in M.HUD_CUES}
            rows.append({"source": source, "t": t, "state": machine.state, "health": health, "seen": seen, "text": any(v >= S.SCORE_THRESHOLD for v in scores.values()),
                         "scores": {name: reader.hud_score(name, mask) for name, mask in masks.items()}, "masks": masks})
            t += 1

    def kind(row):
        if row["t"] in BROWSER.get(row["source"], ()):
            return "browser page"
        if row["state"] == S.PRE_GAME:
            return "waiting island"
        if row["state"] == S.IN_MATCH and row["health"] >= S.HEALTH_BAR_MIN_PIXELS:
            return "playing"
        return {S.LOBBY: "lobby", S.LOADING: "loading", S.ELIMINATED: "end or spectating", S.IN_MATCH: "in match, no health bar"}.get(row["state"], "other")

    held_out = [row for row in rows if row["source"] not in ("new", "ps5")]
    print(f"\n{len(rows)} samples, {len(held_out)} held out from the templates\n{'held out':26}{'n':>6}{'HUD seen':>10}")
    groups = {}
    for row in held_out:
        groups.setdefault(kind(row), []).append(row)
    for name in sorted(groups):
        print(f"{name:26}{len(groups[name]):6d}{sum(r['seen'] for r in groups[name]):10d}")

    longest, in_match = 0, 0
    by_source = {}
    for row in rows:
        by_source.setdefault(row["source"], []).append(row)
    for items in by_source.values():
        run = 0
        for row in items:
            in_match += row["state"] == S.IN_MATCH
            unseen = row["state"] == S.IN_MATCH and row["health"] < S.HEALTH_BAR_MIN_PIXELS and not row["seen"] and not row["text"]
            run = run + 1 if unseen else 0
            longest = max(longest, run)
    p99 = float(np.percentile(cost, 99))
    playing, browser = groups["playing"], groups["browser page"]
    ok = all(r["seen"] for r in playing) and not any(r["seen"] for r in browser) and longest < S.GAME_OUT_OF_VIEW and p99 < BUDGET_MS
    print(f"\nlongest stretch of a match with nothing in view: {longest} s, over {in_match} s in matches (limit {S.GAME_OUT_OF_VIEW:.0f} s)")
    print(f"cost per sample: median {np.median(cost):.2f} ms, p99 {p99:.2f} ms (budget {BUDGET_MS:.0f} ms), once a second")
    if arguments.write_fixtures:
        chosen = [r for name in ("playing", "waiting island") for r in groups[name][::max(1, len(groups[name]) // 40)]] + browser
        path = ROOT / "tests" / "fixtures" / "match" / "hud_masks.npz"
        np.savez_compressed(path, cues=np.array([cue.name for cue in M.HUD_CUES]), kinds=np.array([kind(r) for r in chosen]), where=np.array([f"{r['source']}@{r['t']}" for r in chosen]),
                            **{cue.name: np.stack([np.packbits(r["masks"][cue.name].ravel()) for r in chosen]) for cue in M.HUD_CUES})
        print(f"wrote {path}: {len(chosen)} samples, {path.stat().st_size // 1024} KiB")
    print("\nRESULT:", "ACCEPTED" if ok else "NOT ACCEPTED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
