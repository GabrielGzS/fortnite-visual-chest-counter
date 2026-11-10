"""
Measure the match-recognition cues on labelled footage and on ordinary gameplay. Samples frames only: it runs no chest detection.

    python research/match_cues_eval.py --capture "<...>/captures/20261108_233437" [--ffmpeg <exe>] [--write-fixtures]

Exit code 0 only when every signal reaches the threshold on its known screens and stays at or below 0.40 everywhere else, and the combined
checks stay under the time budget. Frames close to a labelled boundary are not judged either way, because those labels are approximate.
"""
import argparse
import gzip
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fortnite_chest_counter import match_cues as M                                 # noqa: E402

WIDTH, HEIGHT = 1280, 720
WRONG_SCREEN_LIMIT, BUDGET_MS = 0.40, 10.0
BOUNDARY_MARGIN = 2.5                                                               # seconds either side of a labelled window that are not judged
NEW, PS5 = "Fortnites-NEW-HD-No-Audio.mp4", "Fortnite-PS5-Pro-HD-No-Audio.mp4"
#              signal: {source: [(from, to) in seconds where the text is on screen]}, labelled by eye from the footage
TRUTH = {"you_placed": {"clip1": [(8.5, 14.5), (16.0, 16.5)], "clip2": [(40.0, 45.5), (46.5, 47.0)]},
         "eliminated_by": {"clip1": [(10.0, 14.5)], "clip2": [(40.0, 45.0)]},
         "connecting": {"clip1": [(18.5, 27.0)], "clip2": [(48.5, 58.0)], "clip3": [(18.0, 21.0)], "case_20261108_030211_seg_00019": [(2.0, 9.0)]},
         "lobby_menu": {"clip1": [(30.5, 60.0)], "clip2": [(0.0, 3.5), (60.5, 63.5), (68.0, 80.0)], "clip3": [(0.0, 15.0)]},
         "matchmaking": {"clip1": [(30.5, 60.0)], "clip2": [(0.0, 8.0), (61.0, 64.5)], "clip3": [(0.0, 14.0)]},
         "waiting_for_players": {"clip3": [(24.0, 33.0)]},
         "bus_launching": {"clip3": [(34.5, 44.0)]},
         "spectating": {"clip1": [(14.0, 14.5), (16.0, 16.5)], "clip2": [(44.0, 45.0), (46.5, 47.0)]},
         "victory_royale": {"new": [(258.0, 261.0), (499.0, 506.0)], "ps5": [(1020.0, 1028.0)]}}
# On screen but hidden behind the Twitch player's controls: neither right nor wrong for this signal.
NOT_JUDGED = {"lobby_menu": {"clip2": [(3.5, 9.5), (63.5, 66.5)]}}
SETS = {"LOBBY": ("connecting", "lobby_menu"), "LOADING": ("waiting_for_players", "lobby_menu"), "PRE_GAME": ("waiting_for_players", "bus_launching", "connecting", "you_placed"),
        "IN_MATCH": ("you_placed", "victory_royale", "connecting", "lobby_menu"), "ELIMINATED": ("connecting", "lobby_menu", "you_placed", "spectating"), "UNKNOWN (everything)": tuple(M.SIGNALS)}


def frames(ffmpeg, inputs, fps):
    command = [ffmpeg, "-v", "error", "-nostdin", "-threads", "1", *inputs, "-vf", f"fps={fps},scale={WIDTH}:{HEIGHT}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, bufsize=10 ** 7)
    index, size = 0, WIDTH * HEIGHT * 3
    while len(raw := process.stdout.read(size)) == size:
        yield index / fps, np.frombuffer(raw, np.uint8).reshape(HEIGHT, WIDTH, 3)
        index += 1
    process.wait()


def sources(capture):
    samples = ROOT / "samples" / "video tests"
    for number in (1, 2, 3):
        yield f"clip{number}", ["-f", "concat", "-safe", "0", "-i", str(Path(capture) / "video" / f"clip_{number:03d}.ffconcat")], 2
    yield "ps5", ["-i", str(samples / PS5)], 1
    yield "new", ["-i", str(samples / NEW)], 1
    for segment in sorted((ROOT / "samples" / "cases").glob("*/video/seg_*.mkv")):
        yield f"case_{segment.parent.parent.name}_{segment.stem}", ["-i", str(segment)], 1


def verdict(signal, source, t):
    """True: the text is on screen. False: it is not. None: too close to a labelled edge to say."""
    if any(start <= t <= end for start, end in NOT_JUDGED.get(signal, {}).get(source, [])):
        return None
    windows = TRUTH[signal].get(source, [])
    if any(start <= t <= end for start, end in windows):
        return True
    return None if any(start - BOUNDARY_MARGIN <= t <= end + BOUNDARY_MARGIN for start, end in windows) else False


def bits_of(frame):
    return np.packbits(np.concatenate([M._ink_mask(frame[c.box[1]:c.box[3], c.box[0]:c.box[2]], c.ink).ravel() for c in M.CUES]))


def write_fixtures(rows, bits, path):
    """A small, committable sample: for each signal some true screens and its hardest wrong screens, plus spread-out ordinary frames."""
    chosen = set()
    for signal in M.SIGNALS:
        positives = [i for i, row in enumerate(rows) if verdict(signal, row["source"], row["t"]) is True]
        chosen.update(positives[:: max(1, len(positives) // 3)][:4])
        negatives = sorted((i for i, row in enumerate(rows) if verdict(signal, row["source"], row["t"]) is False), key=lambda i: -rows[i][signal])
        chosen.update(negatives[:3])
    others = [i for i, row in enumerate(rows) if not row["source"].startswith("clip")]
    chosen.update(others[:: max(1, len(others) // 24)])
    order = sorted(chosen)
    signals = list(M.SIGNALS)
    truth = [[verdict(s, rows[i]["source"], rows[i]["t"]) for s in signals] for i in order]
    np.savez_compressed(path, cues=np.array([c.name for c in M.CUES]), signals=np.array(signals), masks=np.stack([bits[i] for i in order]),
                        scores=np.array([[rows[i][s] for s in signals] for i in order], dtype=np.float64),
                        expected=np.array([[-1 if v is None else int(v) for v in row] for row in truth], dtype=np.int8),
                        where=np.array([f"{rows[i]['source']}@{rows[i]['t']:.1f}" for i in order]))
    print(f"\nwrote {path}: {len(order)} frames, {path.stat().st_size // 1024} KiB")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capture", required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--write-fixtures", action="store_true")
    parser.add_argument("--write-timelines", action="store_true", help="save one-sample-per-second cue timelines for tests/test_match_state.py")
    arguments = parser.parse_args()
    timelines = {}
    reader = M.CueReader()
    rows, bits, whole_ms, set_ms = [], [], [], {name: [] for name in SETS}
    changes, still, started = {}, [], time.monotonic()
    for source, inputs, fps in sources(arguments.capture):
        previous, step = None, 0
        for t, frame in frames(arguments.ffmpeg, inputs, fps):
            frame.flags.writeable = False
            begin = time.perf_counter()
            scores = reader.read(frame)
            evidence = M.picture_evidence(frame, previous)
            health = M.health_bar_pixels(frame)
            whole_ms.append(1000 * (time.perf_counter() - begin))
            for name, signals in SETS.items():
                begin = time.perf_counter()
                reader.read(frame, signals)
                M.picture_evidence(frame, previous)
                M.health_bar_pixels(frame)
                set_ms[name].append(1000 * (time.perf_counter() - begin))
            if step % fps == 0:                                                      # one sample per second, as the tracker will
                if evidence.change is not None:
                    changes.setdefault(source.split("_")[0], []).append(evidence.change)
                    if evidence.change < 1.0:
                        still.append((source, t, round(evidence.change, 3), round(evidence.mean_luma, 1)))
                previous = evidence.sample
                if source in ("clip1", "clip2", "clip3", "ps5", "new"):
                    timelines.setdefault(source, []).append([round(t, 1), {k: round(v, 3) for k, v in scores.items() if v >= 0.05}, health, int(evidence.black), int(evidence.frozen)])
            step += 1
            fill = {signal: max(float(M._ink_mask(frame[M._CUE[n].box[1]:M._CUE[n].box[3], M._CUE[n].box[0]:M._CUE[n].box[2]], M._CUE[n].ink).mean()) for n in M.SIGNALS[signal]) for signal in M.SIGNALS}
            rows.append({"source": source, "t": t, **scores, "mean_luma": evidence.mean_luma, "health": health, "fill": fill})
            bits.append(bits_of(frame))
    print(f"scored {len(rows)} frames in {time.monotonic() - started:.0f} s; {sum(r['source'].startswith('clip') for r in rows)} from the labelled clips\n")

    ok = True
    print(f"{'signal':21}{'true frames':>12}{'lowest':>8}{'median':>8}{'wrong frames':>14}{'highest':>9}{'>=0.70':>8}{'>0.40':>7}")
    for signal in M.SIGNALS:
        true = [r for r in rows if verdict(signal, r["source"], r["t"]) is True]
        wrong = [r for r in rows if verdict(signal, r["source"], r["t"]) is False]
        low, top = min(r[signal] for r in true), max(r[signal] for r in wrong)
        passed = low >= M.SCORE_THRESHOLD and top <= WRONG_SCREEN_LIMIT
        ok &= passed
        print(f"{signal:21}{len(true):12d}{low:8.2f}{np.median([r[signal] for r in true]):8.2f}{len(wrong):14d}{top:9.2f}{sum(r[signal] >= M.SCORE_THRESHOLD for r in wrong):8d}{sum(r[signal] > WRONG_SCREEN_LIMIT for r in wrong):7d}  {'pass' if passed else 'FAIL'}")
        for r in [r for r in true if r[signal] < M.SCORE_THRESHOLD][:8]:
            print(f"     below threshold: {r['source']} @ {r['t']:.1f} s = {r[signal]:.2f}")
        for r in sorted([r for r in wrong if r[signal] > WRONG_SCREEN_LIMIT], key=lambda r: -r[signal])[:8]:
            print(f"     wrong screen:    {r['source']} @ {r['t']:.1f} s = {r[signal]:.2f}")

    print(f"\nhow full of ink a search box gets on true screens (rejected above {M.MAX_BOX_INK:.2f}):")
    print("   " + ", ".join(f"{signal} {max(r['fill'][signal] for r in rows if verdict(signal, r['source'], r['t']) is True):.2f}" for signal in M.SIGNALS))
    print(f"\nCOST, milliseconds per frame (signals + picture check + health bar), {len(whole_ms)} real frames")
    print(f"{'set of checks':24}{'median':>9}{'p99':>9}{'max':>9}")
    for name in SETS:
        print(f"{name:24}{np.median(set_ms[name]):9.2f}{np.percentile(set_ms[name], 99):9.2f}{max(set_ms[name]):9.2f}")
    p99 = float(np.percentile(whole_ms, 99))
    ok &= p99 < BUDGET_MS
    print(f"{'all, first pass':24}{np.median(whole_ms):9.2f}{p99:9.2f}{max(whole_ms):9.2f}   budget {BUDGET_MS:.0f} ms at p99: {'pass' if p99 < BUDGET_MS else 'FAIL'}")

    print("\nPICTURE CHECKS")
    print(f"black frames (mean brightness below {M.BLACK_LUMA:.0f}): {sum(r['mean_luma'] < M.BLACK_LUMA for r in rows)}")
    for source, values in changes.items():
        print(f"change between samples one second apart, {source:6}: lowest {min(values):7.3f}, median {np.median(values):7.2f}, below frozen limit {sum(v < M.FROZEN_CHANGE for v in values)} of {len(values)}")
    print("samples that barely changed (source, time, change, brightness):", still)
    print("\nHEALTH BAR (supporting only): frames with a bar, by source group")
    for group in ("clip", "ps5", "new", "case"):
        chosen = [r for r in rows if r["source"].startswith(group)]
        print(f"   {group:6} {sum(r['health'] >= M.HEALTH_BAR_MIN_PIXELS for r in chosen)} of {len(chosen)}")

    if arguments.write_fixtures:
        folder = ROOT / "tests" / "fixtures" / "match"
        folder.mkdir(parents=True, exist_ok=True)
        write_fixtures(rows, bits, folder / "frames.npz")
    if arguments.write_timelines:
        path = ROOT / "tests" / "fixtures" / "match" / "timelines.json.gz"
        with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as out:
            out.write(json.dumps(timelines, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        print(f"\nwrote {path}: {sum(len(v) for v in timelines.values())} samples, {path.stat().st_size // 1024} KiB")
    print("\nRESULT:", "ACCEPTED" if ok else "NOT ACCEPTED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
