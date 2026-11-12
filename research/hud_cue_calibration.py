"""
HUD calibration research for match text (v0.4.1 M1): native templates at the maintainer's HUD size (0.90x) for the countdown and YOU PLACED.

    python research/hud_cue_calibration.py

Cuts WAITING FOR PLAYERS, LAUNCHING IN and YOU PLACED at the size the maintainer's game draws them (one frame each of
samples/video tests/2026-11-12 12-52-32.mp4), then samples every video once per second and reports, for these and the production
templates (1.0x and, for the countdown, 0.78x): the best score while the text is on screen, and the highest score on any other sample.
Matching is match_cues' own (white ink mask in a box, binary NCC), in a search box wide enough for every size.

LIMIT: the recording has ONE waiting island and ONE death screen, so the native scores while the text is on screen are within the session
the template came from (other frames, other backgrounds, but not held-out footage). False alarms are measured on everything else.
"""

import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fortnite_chest_counter import match_cues as M  # noqa: E402
from fortnite_chest_counter.detection.visual import best_template_correlation  # noqa: E402

USER = ROOT / "samples/video tests/2026-11-12 12-52-32.mp4"
OTHERS = {"reference 1.00": ROOT / "samples/video tests/Fortnites-NEW-HD-No-Audio.mp4",
          "PS5 Portuguese": ROOT / "samples/video tests/Fortnite-PS5-Pro-HD-No-Audio.mp4"}
# signal: (cut time, cut box at the maintainer's size, search box for every size, production templates, windows on screen in USER)
CUES = {"waiting_for_players": (500.0, (578, 90, 726, 105), (540, 70, 760, 125), ("waiting_for_players", "waiting_for_players_small"), [(488, 509)]),
        "bus_launching": (512.0, (664, 67, 745, 80), (590, 52, 810, 98), ("bus_launching", "bus_launching_small"), [(510, 519)]),
        "you_placed": (1433.0, (543, 91, 677, 122), (500, 70, 720, 145), ("you_placed_screen",), [(1432.3, 1435.0)])}


def frames(video, fps=1.0):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"scale=1280:720,fps={fps}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                         stdout=subprocess.PIPE, bufsize=10 ** 8)
    n, i = 1280 * 720 * 3, 0
    while True:
        raw = p.stdout.read(n)
        if len(raw) < n:
            break
        yield i / fps, np.frombuffer(raw, np.uint8).reshape(720, 1280, 3)
        i += 1


def frame_at(t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(USER), "-frames:v", "1", "-vf", "scale=1280:720",
                          "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(720, 1280, 3)


def cut(t, box):
    x0, y0, x1, y1 = box
    m = M._ink_mask(frame_at(t)[y0:y1, x0:x1], M.WHITE)
    ys, xs = np.nonzero(m)
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)


def score(frame, box, tpl):
    x0, y0, x1, y1 = box
    m = M._ink_mask(frame[y0:y1, x0:x1], M.WHITE)
    k = m.sum()
    if k < 0.45 * tpl.sum() or k > M.MAX_BOX_INK * m.size:
        return 0.0
    return float(np.clip(best_template_correlation(m.astype(np.float32), tpl)[0], 0, 1))


def main():
    T = {}
    for sig, (t, box, search, prod, _) in CUES.items():
        T[(sig, "native 0.90 (maintainer)")] = (cut(t, box), search)
        for name in prod:
            T[(sig, f"production {name}")] = (np.load(M.TEMPLATE_DIR / f"{name}.npy").astype(np.float32), search)
    for (sig, name), (tpl, _) in T.items():
        print(f"{sig:20s} {name:42s} {tpl.shape[1]}x{tpl.shape[0]}")
    on = {k: 0.0 for k in T}
    off = {k: {"maintainer": 0.0, **{o: 0.0 for o in OTHERS}} for k in T}
    for label, video in [("maintainer", USER), *OTHERS.items()]:
        for t, f in frames(video):
            for key, (tpl, search) in T.items():
                s = score(f, search, tpl)
                windows = CUES[key[0]][4] if label == "maintainer" else []
                if any(a - 0.5 <= t <= b + 0.5 for a, b in windows):
                    on[key] = max(on[key], s)
                elif not (label == "maintainer" and any(a - 3 <= t <= b + 3 for a, b in windows)):
                    off[key][label] = max(off[key][label], s)
    print("\nscore while on screen (maintainer, 0.90x HUD) | highest elsewhere: maintainer / reference / PS5   (a signal needs 0.70)")
    for key in T:
        o = off[key]
        print(f"  {key[0]:20s} {key[1]:42s} {on[key]:.2f} | {o['maintainer']:.2f} / {o['reference 1.00']:.2f} / {o['PS5 Portuguese']:.2f}")


if __name__ == "__main__":
    main()
