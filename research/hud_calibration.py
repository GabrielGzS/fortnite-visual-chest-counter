"""
HUD calibration research (v0.4.1 M1): how far does a native CHEST template carry across HUD sizes, sources and resolutions?

    python research/hud_calibration.py [--json OUT]

Every native template we have (cut at the size the game drew it) is scored on every labelled footage family we have:

    template          cut from
    1.00 reference    templates/chest/en/chest.npy (Fortnites-NEW-HD, normal HUD)
    0.78 Thiefs       templates/chest/en/chest_small.npy (Thiefs' stream, small HUD)
    0.95 maintainer A / B   the maintainer's recording at 1094.0 s / 1151.1 s (pop-up 0.95x)
    synthetic 0.95    the 1.00 reference word, its RGB shrunk to 0.95 (visual.resize_box) and masked: does synthesis work for SMALL offsets?

    footage family                      chests                         non-chests
    reference 1.00 (720p, x264)         Fortnites-NEW-HD, 6 labelled    the rest of that video, and the Portuguese PS5 video
    Replays 1.00 (cases)                replays_six_chests, replays_vault_five_chests fixtures (new pop-ups)
    Thiefs 0.78 at 3 sources            thiefs_small_hud (OBS virtual camera), thiefs_1080p_small_hud, thiefs_720p_stream_chests
    maintainer 0.95 (720p NVENC)        tests/cases/user_20261112.json, 18 new pop-ups + 2 lines   the rest of the recording

Per pair: the exact (binary NCC) and blurred (sigma 0.6) scores of each real chest's best frame in [t - 0.2, t + 1.5] s, and the highest
score on any non-chest frame. A template is never scored on the pop-up it was cut from (leave-one-out). Also the cost of one exact match
over the pop-up box. Needs samples/ (not in Git) for the videos; the case fixtures are in the repository.
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
from fortnite_chest_counter import paths  # noqa: E402
from fortnite_chest_counter.detection import visual as V  # noqa: E402
from fortnite_chest_counter.detection.audio import GROUND_TRUTH_FILE, load_ground_truth  # noqa: E402

SIGMA = 0.6
FPS_WINDOWS, FPS_SCAN = 15, 7.5
BOX = (V.ROI_X, V.ROI_Y, V.ROI_X + V.ROI_W, V.ROI_Y + V.ROI_H)      # the production pop-up box
USER = ROOT / "samples/video tests/2026-11-12 12-52-32.mp4"
EN = ROOT / "samples/video tests/Fortnites-NEW-HD-No-Audio.mp4"
PS5 = ROOT / "samples/video tests/Fortnite-PS5-Pro-HD-No-Audio.mp4"
LABELS = json.loads((ROOT / "tests/cases/user_20261112.json").read_text(encoding="utf-8"))
CASES = json.loads((ROOT / "tests/cases/cases.json").read_text(encoding="utf-8"))["cases"]


def frame_at(video, t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1", "-vf", "scale=1280:720",
                          "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(720, 1280, 3)


def roi_frames(video, start=None, dur=None, fps=FPS_WINDOWS):
    x0, y0, x1, y1 = BOX
    cmd = ["ffmpeg", "-v", "error"] + (["-ss", f"{start:.3f}"] if start is not None else []) + ["-i", str(video)]
    cmd += (["-t", f"{dur:.3f}"] if dur is not None else []) + ["-vf", f"scale=1280:720,fps={fps},crop={x1 - x0}:{y1 - y0}:{x0}:{y0}",
                                                                 "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10 ** 8)
    n, i = (x1 - x0) * (y1 - y0) * 3, 0
    while True:
        raw = p.stdout.read(n)
        if len(raw) < n:
            break
        yield (start or 0.0) + i / fps, V.lavender_mask(np.frombuffer(raw, np.uint8).reshape(y1 - y0, x1 - x0, 3))
        i += 1


def fixture_frames(name):
    d = np.load(ROOT / "tests/fixtures/popups" / f"{name}.npz")
    h, w = (int(v) for v in d["shape"])
    for t, packed in zip(d["times"], d["masks"]):
        yield float(t), np.unpackbits(packed)[:h * w].reshape(h, w).astype(np.float32)


def cut_word(mask_full, approx_tl, size=(31, 11)):
    """The lit pixels of the word whose blurred 1.00 window starts at approx_tl (y, x) in the pop-up box mask."""
    y, x = approx_tl
    win = mask_full[y:y + size[1], x:x + size[0]]
    ys, xs = np.nonzero(win)
    return win[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)


def native_user_template(t):
    x0, y0, x1, y1 = BOX
    m = V.lavender_mask(frame_at(USER, t)[y0:y1, x0:x1])
    ref_b = V.blur_template(np.load(paths.TEMPLATES_DIR / "chest/en/chest.npy").astype(np.float32), SIGMA)
    _, y, x = V.robust_correlation_at(m, ref_b, SIGMA)
    return cut_word(m, (y, x))


def synthetic(s):
    """The reference word's RGB (Fortnites-NEW-HD 51.8 s, box 885,229-912,236 + 6 px) shrunk by s, masked, cropped to the word."""
    f = frame_at(EN, 51.8)
    pad, (bx0, by0, bx1, by1) = 6, (885, 229, 912, 236)
    patch = f[by0 - pad:by1 + pad, bx0 - pad:bx1 + pad]
    h, w = patch.shape[:2]
    small = V.resize_box(patch, round(w * s), round(h * s))
    m = V.lavender_mask(small)[int(pad * s):int(np.ceil((pad + 7) * s)), int(pad * s):int(np.ceil((pad + 27) * s))]
    ys, xs = np.nonzero(m)
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)


def score(mask, tpl, tpl_b):
    if mask.sum() < 20:
        return 0.0, 0.0
    e, y, x = V.best_template_correlation(mask, tpl)
    th, tw = tpl.shape
    crop = mask[max(0, y - 3):y + th + 3, max(0, x - 3):x + tw + 3]
    ph, pw = max(0, tpl_b.shape[0] - crop.shape[0]), max(0, tpl_b.shape[1] - crop.shape[1])
    if ph or pw:
        crop = np.pad(crop, ((0, ph), (0, pw)))
    return float(e), float(V.robust_correlation(crop, tpl_b, SIGMA))


def best_over(frames, T, B):
    best = {n: (0.0, 0.0) for n in T}
    for _, m in frames:
        for n in T:
            e, b = score(m, T[n], B[n])
            best[n] = (max(best[n][0], e), max(best[n][1], b))
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json")
    a = ap.parse_args()
    T = {"1.00 reference": np.load(paths.TEMPLATES_DIR / "chest/en/chest.npy").astype(np.float32),
         "0.78 Thiefs": np.load(paths.TEMPLATES_DIR / "chest/en/chest_small.npy").astype(np.float32),
         "0.95 maintainer A": native_user_template(1094.0), "0.95 maintainer B": native_user_template(1151.1),
         "synthetic 0.95": synthetic(0.95)}
    source = {"0.95 maintainer A": 1093.47, "0.95 maintainer B": 1150.60}
    B = {n: V.blur_template(t, SIGMA) for n, t in T.items()}
    for n, t in T.items():
        print(f"template {n:18s} {t.shape[1]}x{t.shape[0]} px, {int(t.sum())} lit")

    # chests per family: name -> list of (label, {template: (exact, blurred)})
    chests = {"reference 1.00 (720p x264)": [], "Replays 1.00 (stream captures)": [], "Thiefs 0.78 OBS camera": [],
              "Thiefs 0.78 1080p browser": [], "Thiefs 0.78 720p stream": [], "maintainer 0.95 (720p NVENC)": []}
    for t in load_ground_truth(GROUND_TRUTH_FILE):
        chests["reference 1.00 (720p x264)"].append((float(t), best_over(roi_frames(EN, t - 0.2, 1.7), T, B)))
    for fam, names in (("Replays 1.00 (stream captures)", ["replays_six_chests", "replays_vault_five_chests"]),
                       ("Thiefs 0.78 OBS camera", ["thiefs_small_hud"]), ("Thiefs 0.78 1080p browser", ["thiefs_1080p_small_hud"]),
                       ("Thiefs 0.78 720p stream", ["thiefs_720p_stream_chests"])):
        for name in names:
            frames = list(fixture_frames(name))
            for row in CASES[name]["truth"]:
                if row["what"] == "new_popup":
                    chests[fam].append((row["t"], best_over([f for f in frames if row["t"] - 0.2 <= f[0] <= row["t"] + 1.5], T, B)))
    for c in LABELS["chests"]:
        chests["maintainer 0.95 (720p NVENC)"].append((c["t"], best_over(roi_frames(USER, c["t"] - 0.2, 1.7), T, B), c["what"]))

    # non-chests: every frame away from a chest, on the three videos
    nonchest = {}
    for fam, video, near in (("reference 1.00 video, non-chest frames", EN, [float(t) for t in load_ground_truth(GROUND_TRUTH_FILE)]),
                             ("PS5 Portuguese (combat text), all frames", PS5, []),
                             ("maintainer recording, non-chest frames", USER, [c["t"] for c in LABELS["chests"]])):
        top = {n: [0.0, 0.0] for n in T}
        for t, m in roi_frames(video, fps=FPS_SCAN):
            if any(c - 1.0 <= t <= c + 3.0 for c in near) or m.sum() < 40:
                continue
            for n in T:
                e, b = score(m, T[n], B[n])
                top[n] = [max(top[n][0], e), max(top[n][1], b)]
        nonchest[fam] = top

    report = {"templates": {n: list(t.shape) for n, t in T.items()}, "families": {}, "non_chest_max": nonchest}
    print("\nReal chests (new pop-ups unless noted): exact min / median / max | share exact >= 0.75 | blurred median | share blurred >= 0.88")
    for fam, rows in chests.items():
        print(f"\n{fam}: {len(rows)} chests")
        report["families"][fam] = {}
        for n in T:
            use = [r for r in rows if not (n in source and abs(r[0] - source[n]) < 0.5)]
            if fam.startswith("maintainer"):
                use = [r for r in use if r[2] == "new_popup"]
            ex = np.array([r[1][n][0] for r in use])
            bl = np.array([r[1][n][1] for r in use])
            stats = {"n": len(use), "exact_min": round(float(ex.min()), 3), "exact_median": round(float(np.median(ex)), 3),
                     "exact_max": round(float(ex.max()), 3), "share_exact_075": round(float((ex >= 0.75).mean()), 2),
                     "blur_median": round(float(np.median(bl)), 3), "blur_min": round(float(bl.min()), 3),
                     "share_blur_088": round(float((bl >= 0.88).mean()), 2)}
            report["families"][fam][n] = stats
            print(f"  {n:18s} {stats['exact_min']:.2f} / {stats['exact_median']:.2f} / {stats['exact_max']:.2f} | {stats['share_exact_075']:4.0%}"
                  f" | {stats['blur_median']:.2f} (min {stats['blur_min']:.2f}) | {stats['share_blur_088']:4.0%}")
        if fam.startswith("maintainer"):
            lines = [r for r in rows if r[2] == "new_line"]
            for t, s, _ in lines:
                print(f"  chest line at {t:.1f} s: " + ", ".join(f"{n} {s[n][0]:.2f}/{s[n][1]:.2f}" for n in T))
    print("\nHighest score on non-chest frames (exact / blurred)")
    for fam, top in nonchest.items():
        print(f"  {fam}: " + "; ".join(f"{n} {v[0]:.2f}/{v[1]:.2f}" for n, v in top.items()))

    m = next(f for _, f in roi_frames(USER, 1094.0, 0.1))
    cost = {}
    for n in ("1.00 reference", "0.95 maintainer A"):
        a0 = time.perf_counter()
        for _ in range(200):
            V.best_template_correlation(m, T[n])
        cost[n] = round(1000 * (time.perf_counter() - a0) / 200, 3)
    report["exact_match_ms_per_template_full_box"] = cost
    print("\nExact match over the whole pop-up box, ms per template:", cost)
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
