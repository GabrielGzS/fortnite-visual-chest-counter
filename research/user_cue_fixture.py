"""
Write tests/fixtures/match/user_20261112_cues.npz (v0.4.1): the cue boxes of the match signals added for the maintainer's recording, at
labelled moments of samples/video tests/2026-11-12 12-52-32.mp4, as true/false ink masks only (like frames.npz).

    python research/user_cue_fixture.py

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


if __name__ == "__main__":
    main()
