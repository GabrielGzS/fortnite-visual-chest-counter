"""
Write tests/fixtures/match/user_20261112_cues.npz (v0.4.1): the cue boxes of the match signals added for the maintainer's recording, at
labelled moments of samples/video tests/2026-11-12 12-52-32.mp4, as true/false ink masks only (like frames.npz).

    python research/user_cue_fixture.py      (also writes user_20261112_cues75.npz: the HUD Scale 75% match text)

Templates covered: connecting_shadow (CONNECTING's grey shadow on the white return-to-lobby splash) and the READY overlay's two lines
(ready_party, ready_finding; their best is the ready_overlay signal). expected: 1 = must reach the threshold, 0 = must stay low.
The READY templates were cut from 1446 s (match 2) and 440 s (match 1), so each is held out on the other match's overlay; the shadow
template has only the one splash (within the session).
"""

import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fortnite_chest_counter import match_cues as M  # noqa: E402

VIDEO = ROOT / "samples/video tests/2026-11-12 12-52-32.mp4"
OUT = ROOT / "tests/fixtures/match/user_20261112_cues.npz"
CUES = ("connecting_shadow", "ready_party", "ready_finding")
CHECKS = ("connecting_shadow", "ready_overlay")
#        seconds, what is on screen, expected connecting_shadow, expected ready_overlay
MOMENTS = [(1463.5, "return-to-lobby splash, grey CONNECTING", 1, 0), (1464.5, "return-to-lobby splash", 1, 0),
           (1465.5, "return-to-lobby splash", 1, 0), (1466.0, "return-to-lobby splash", 1, 0),
           (400.0, "READY, waiting for party (match 1, storm streak across it)", 0, 1), (410.0, "READY, waiting for party (match 1)", 0, 1),
           (1446.0, "READY, waiting for party (match 2)", 0, 1), (1452.0, "READY, waiting for party (match 2)", 0, 1),
           (440.0, "READY, finding next match (match 1)", 0, 1), (460.0, "READY, finding next match (match 1)", 0, 1),
           (1462.0, "READY, finding next match (match 2, under a second)", 0, 1),
           (483.0, "white CONNECTING on dark art (the white template's, not the shadow's)", 0, 0), (381.0, "match recap, PLAY AGAIN", 0, 0), (365.0, "Victory Royale banner", 0, 0),
           (500.0, "waiting island", 0, 0), (530.0, "bus", 0, 0), (700.0, "play", 0, 0), (1000.0, "play, bright water", 0, 0),
           (1300.0, "play", 0, 0), (1433.8, "death screen", 0, 0), (1472.0, "lobby", 0, 0), (60.0, "play, storm", 0, 0)]


def frame_at(t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(VIDEO), "-frames:v", "1", "-vf", "scale=1280:720",
                          "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(720, 1280, 3)


def main():
    masks, scores = [], []
    reader = M.CueReader()
    for t, _, _, _ in MOMENTS:
        f = frame_at(t)
        bits = []
        for name in CUES:
            cue = M._CUE[name]
            x0, y0, x1, y1 = cue.box
            bits.append(M._ink_mask(f[y0:y1, x0:x1], cue.ink).ravel())
        masks.append(np.packbits(np.concatenate(bits)))
        s = reader.template_scores(f, CUES)
        scores.append([s["connecting_shadow"], max(s["ready_party"], s["ready_finding"])])
        print(f"{t:7.1f}  " + "  ".join(f"{k} {v:.2f}" for k, v in zip(CHECKS, scores[-1])))
    np.savez_compressed(OUT, cues=np.array(CUES), checks=np.array(CHECKS), masks=np.array(masks), scores=np.array(scores),
                        expected=np.array([[c, r] for _, _, c, r in MOMENTS], np.int8), where=np.array([w for _, w, _, _ in MOMENTS]),
                        times=np.array([t for t, _, _, _ in MOMENTS]))
    print(f"-> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


# ---- Fortnite HUD Scale 75% (v0.4.1): the match text as the maintainer's game draws it -> tests/fixtures/match/user_20261112_cues75.npz
OUT75 = ROOT / "tests/fixtures/match/user_20261112_cues75.npz"
CUES75 = ("waiting_for_players_75", "bus_launching_75", "you_placed_screen_75", "you_placed_bar_75", "victory_75")
SIGNALS75 = ("waiting_for_players", "bus_launching", "you_placed", "victory_royale")
#          seconds, what is on screen, expected waiting, bus, you_placed, victory (the templates were cut at 500, 512, 1433, 1436.5, 366 s)
MOMENTS75 = [(495.0, "waiting island", 1, 0, 0, 0), (505.0, "waiting island", 1, 0, 0, 0), (512.0, "LAUNCHING IN", 0, 1, 0, 0),
             (516.0, "LAUNCHING IN", 0, 1, 0, 0), (1433.5, "death screen YOU PLACED", 0, 0, 1, 0), (1434.2, "death screen", 0, 0, 1, 0),
             (1436.5, "recap bar YOU PLACED", 0, 0, 1, 0), (1460.0, "recap bar, second time (held out)", 0, 0, 1, 0),
             (365.0, "Victory Royale banner", 0, 0, 0, 1), (370.0, "Victory Royale banner", 0, 0, 0, 1),
             (530.0, "bus, YOU'RE THE CAPTAIN banner", 0, 0, 0, 0), (60.0, "play, storm", 0, 0, 0, 0), (700.0, "play", 0, 0, 0, 0),
             (1000.0, "play, bright water", 0, 0, 0, 0), (1300.0, "play", 0, 0, 0, 0), (483.0, "CONNECTING", 0, 0, 0, 0),
             (381.0, "match recap after the win", 0, 0, 0, 0), (440.0, "READY overlay", 0, 0, 0, 0), (1446.0, "READY overlay", 0, 0, 0, 0),
             (1472.0, "lobby", 0, 0, 0, 0)]


def main75():
    reader = M.CueReader(hud="75")
    boxes = sorted({M._CUE[name].box for name in CUES75})
    masks, scores = [], []
    for t, *_ in MOMENTS75:
        f = frame_at(t)
        masks.append(np.packbits(np.concatenate([M._ink_mask(f[y0:y1, x0:x1], M.WHITE).ravel() for x0, y0, x1, y1 in boxes])))
        s = reader.read(f, SIGNALS75)
        scores.append([s[k] for k in SIGNALS75])
        print(f"{t:7.1f}  " + "  ".join(f"{k} {v:.2f}" for k, v in zip(SIGNALS75, scores[-1])))
    np.savez_compressed(OUT75, boxes=np.array(boxes), signals=np.array(SIGNALS75), masks=np.array(masks), scores=np.array(scores),
                        expected=np.array([m[2:] for m in MOMENTS75], np.int8), where=np.array([m[1] for m in MOMENTS75]),
                        times=np.array([m[0] for m in MOMENTS75]))
    print(f"-> {OUT75} ({OUT75.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
    main75()
