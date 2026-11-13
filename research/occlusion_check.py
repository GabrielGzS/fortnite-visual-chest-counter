"""
Pop-ups covered for a moment (v0.4.1 M4): does the detector count them once, and keep counting chests added to them?

    python research/occlusion_check.py [--case NAME ...]

Replays real case fixtures (tests/fixtures/popups) through the real ChestEstimator, with the pop-up box blanked for 0.4, 0.75 or 1.0 s
starting 0.5 s after every labelled new pop-up, the way an inventory panel or the map covers it (the maintainer's recording: 0.75 s;
Thiefs' map flash: 0.6 s). Reports found / missed / duplicates / false against the case truth, per hidden time.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
import test_cases as T  # noqa: E402
from fortnite_chest_counter import estimator as E  # noqa: E402
from fortnite_chest_counter import settings  # noqa: E402
from fortnite_chest_counter.detection import visual as V  # noqa: E402

CASES = ["replays_six_chests", "replays_vault_five_chests", "replays_stack_x2_x3", "replays_new_chest_line", "thiefs_small_hud",
         "thiefs_1080p_small_hud", "thiefs_720p_stream_chests", "user_plain_popups_approx_only", "user_two_rares_then_rare_line"]
HIDDEN = (0.4, 0.75, 1.0)


def run(case, hide):
    truth = [r["t"] for r in T.CASES[case]["truth"] if r["what"] == "new_popup"]
    E.configure(settings.DEFAULTS["detector"])
    est, events = E.ChestEstimator(), []
    for t, frame in T.frames(case):
        if hide and any(c + 0.5 <= t <= c + 0.5 + hide for c in truth):
            frame = frame.copy()
            frame[V.ROI_Y:V.ROI_Y + V.ROI_H, V.ROI_X:V.ROI_X + V.ROI_W] = np.array([40, 36, 60], np.uint8)
        events += est.process_frame(t, frame)
    events += est.flush()
    return T.score(case, [e for e in events if e["approx_counted"]])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", action="append")
    a = ap.parse_args()
    total = {h: [0, 0, 0, 0] for h in (0,) + HIDDEN}
    print(f"{'case':34s} " + "  ".join(f"{'not hidden' if h == 0 else f'hidden {h} s':>13s}" for h in (0,) + HIDDEN))
    for case in a.case or CASES:
        row = []
        for h in (0,) + HIDDEN:
            r = run(case, h)
            total[h] = [x + y for x, y in zip(total[h], r)]
            row.append(f"{r[0]}/{r[0] + r[1]} d{r[2]} f{r[3]}")
        print(f"{case:34s} " + "  ".join(f"{c:>13s}" for c in row))
    print(f"{'TOTAL found/real, duplicates, false':34s} " + "  ".join(f"{f'{v[0]}/{v[0] + v[1]} d{v[2]} f{v[3]}':>13s}" for v in total.values()))


if __name__ == "__main__":
    main()
