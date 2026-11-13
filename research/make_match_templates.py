"""
Cut the v0.3.0 match-recognition word templates from labelled footage, so they can be rebuilt and checked. Needs footage that is not in Git.

    python research/make_match_templates.py --capture "<...>/captures/20261108_233437" --small-capture "<...>/captures/20261111_071106" [--ffmpeg <exe>]

Each template is the word's ink (white or dark text) as a small true/false bitmap, trimmed to the word. No other picture content is kept.
Footage held back for independent validation must never be used here.
"""
import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fortnite_chest_counter import match_cues as M                                 # noqa: E402

SAMPLES = ROOT / "samples" / "video tests"
ENGLISH_WIN, PORTUGUESE_WIN = SAMPLES / "Fortnites-NEW-HD-No-Audio.mp4", SAMPLES / "Fortnite-PS5-Pro-HD-No-Audio.mp4"
MAINTAINER = SAMPLES / "2026-11-12 12-52-32.mp4"      # v0.4.1: the maintainer's own recording (tests/cases/user_20261112.json)
#          template               footage  seconds  box of the word in 1280x720 pixels
SOURCES = {"you_placed_screen": (1, 9, (538, 98, 683, 128)), "you_placed_bar": (1, 17, (560, 18, 676, 44)), "eliminated_by": (1, 11, (512, 578, 696, 602)),
           "connecting": (1, 22, (60, 644, 196, 667)), "menu_locker": (1, 36, (328, 39, 390, 54)), "menu_quests": (1, 36, (503, 39, 562, 54)),
           "menu_career": (1, 36, (689, 39, 751, 54)), "matchmaking_cancel": (1, 36, (125, 598, 222, 620)), "waiting_for_players": (3, 24, (576, 92, 728, 108)),
           "bus_launching": (3, 38, (670, 68, 752, 84)), "spectating": (1, 17, (1036, 8, 1133, 24)),
           "victory_large": (ENGLISH_WIN, 260, (574, 135, 730, 174)), "victory_small": (PORTUGUESE_WIN, 1024, (585, 108, 712, 138)),
           "waiting_for_players_small": ("seg_00169.mkv", 7.4, (592, 85, 712, 97)), "bus_launching_small": ("seg_00170.mkv", 5.4, (660, 67, 730, 77)),
           # v0.4.1: the grey shadow of CONNECTING on the white return-to-lobby splash, and the READY overlay's two lines
           "connecting_shadow": (MAINTAINER, 1464.5, (55, 640, 225, 670)), "ready_party": (MAINTAINER, 1446, (980, 605, 1265, 640)),
           "ready_finding": (MAINTAINER, 440, (940, 588, 1140, 630)),
           # v0.4.1: Fortnite HUD Scale 75% (the maintainer's game; research/hud75_templates.py evaluates them)
           "waiting_for_players_75": (MAINTAINER, 500.0, (578, 90, 726, 105)), "bus_launching_75": (MAINTAINER, 512.0, (664, 67, 745, 80)),
           "you_placed_screen_75": (MAINTAINER, 1433.0, (543, 91, 677, 122)), "you_placed_bar_75": (MAINTAINER, 1436.5, (555, 15, 655, 42)),
           "victory_75": (MAINTAINER, 366.0, (585, 125, 705, 172))}


def read_frame(ffmpeg, capture, source, seconds, small_capture=None):
    if isinstance(source, str):                                                     # a segment of the capture with the smaller HUD
        source = Path(small_capture) / "video" / source
    if isinstance(source, int):
        inputs = ["-f", "concat", "-safe", "0", "-i", str(Path(capture) / "video" / f"clip_{source:03d}.ffconcat")]
    else:
        inputs = ["-i", str(source)]
    command = [ffmpeg, "-v", "error", "-nostdin", "-threads", "1", "-ss", str(seconds), *inputs, "-frames:v", "1", "-vf", "scale=1280:720", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    return np.frombuffer(subprocess.run(command, capture_output=True, check=True).stdout, np.uint8).reshape(720, 1280, 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capture", required=True, help="the labelled capture folder")
    parser.add_argument("--small-capture", required=True, help="the capture with the smaller HUD")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--out", default=str(M.TEMPLATE_DIR))
    arguments = parser.parse_args()
    out = Path(arguments.out)
    out.mkdir(parents=True, exist_ok=True)
    inks = {cue.name: cue.ink for cue in M.CUES}
    if set(SOURCES) != set(inks):
        raise SystemExit(f"SOURCES and match_cues.CUES disagree: {sorted(set(SOURCES) ^ set(inks))}")
    for name, (source, seconds, (x0, y0, x1, y1)) in SOURCES.items():
        word = M._ink_mask(read_frame(arguments.ffmpeg, arguments.capture, source, seconds, arguments.small_capture)[y0:y1, x0:x1], inks[name])
        ys, xs = np.nonzero(word)
        trimmed = word[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        np.save(out / f"{name}.npy", trimmed)
        print(f"{name:22} {trimmed.shape[1]:4d} x {trimmed.shape[0]:3d} px, ink {trimmed.mean():.2f}, word at x {x0 + xs.min()}-{x0 + xs.max()}, y {y0 + ys.min()}-{y0 + ys.max()}")


if __name__ == "__main__":
    main()
