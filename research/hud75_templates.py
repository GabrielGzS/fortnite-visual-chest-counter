"""
Build and evaluate the native templates of the HUD 75% configuration (v0.4.1 hotfix) from the maintainer's recording.

    python research/hud75_templates.py            # evaluate only
    python research/hud75_templates.py --write    # also write the templates into src/.../templates

The maintainer's configuration: Fortnite HUD Scale 75%, game 2560x1440, OBS canvas 1920x1080, output 1280x720 bicubic 30 fps, SRT NVENC
CBR 4 Mbps (tests/cases/user_20261112.json; the recording has the stream's own settings). Templates are cut where the game drew them,
never resized.

CHEST: a consensus of several pop-ups (each pop-up's settled frame, aligned on a locator cut, averaged, kept where at least half agree),
because one cut is a weak template (M1a: 65-82% of held-out pop-ups over the trigger). Overfitting is measured two ways: a consensus of
match 1's pop-ups scored on match 2's (a different match of the same recording), and leave-one-out over all new pop-ups. RARE: the word
left of CHEST on the two rare pop-ups (one tests the other). Match text: one cut each (one island, one death screen, one Victory; the recap
bar is shown twice, so it is held out on the second). False alarms: every non-chest frame of the three videos and the case fixtures.

LIMIT: all of it comes from one recording of one player. It is not independent validation; the maintainer's live test is.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
from fortnite_chest_counter import match_cues as M  # noqa: E402
from fortnite_chest_counter import paths  # noqa: E402
from fortnite_chest_counter.detection import chest_types as CT  # noqa: E402
from fortnite_chest_counter.detection import visual as V  # noqa: E402
from fortnite_chest_counter.detection.audio import GROUND_TRUTH_FILE, load_ground_truth  # noqa: E402

USER = ROOT / "samples/video tests/2026-11-12 12-52-32.mp4"
EN = ROOT / "samples/video tests/Fortnites-NEW-HD-No-Audio.mp4"
PS5 = ROOT / "samples/video tests/Fortnite-PS5-Pro-HD-No-Audio.mp4"
LABELS = json.loads((ROOT / "tests/cases/user_20261112.json").read_text(encoding="utf-8"))
CASES = json.loads((ROOT / "tests/cases/cases.json").read_text(encoding="utf-8"))["cases"]
SIGMA = 0.6
MATCH1_END = 480.0
CHEST_OUT = paths.TEMPLATES_DIR / "chest/en/hud75"
# match text at 75%: name -> (cut time, cut box, the box the cue searches, the windows it is on screen in the recording)
CUES75 = {"waiting_for_players_75": (500.0, (578, 90, 726, 105), M._CUE["waiting_for_players"].box, [(488, 509)]),
          "bus_launching_75": (512.0, (664, 67, 745, 80), M._CUE["bus_launching"].box, [(510, 519)]),
          "you_placed_screen_75": (1433.0, (543, 91, 677, 122), M._CUE["you_placed_screen"].box, [(1432.3, 1435.0)]),
          "you_placed_bar_75": (1436.5, (555, 15, 655, 42), M._CUE["you_placed_bar"].box, [(1435.5, 1438.0), (1459.5, 1460.6)]),
          "victory_75": (366.0, (585, 125, 705, 172), M._CUE["victory_large"].box, [(362, 374)])}


def frame_at(video, t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1", "-vf", "scale=1280:720",
                          "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(720, 1280, 3)


def roi_masks(video, start=None, dur=None, fps=15):
    x0, y0, w, h = V.ROI_X, V.ROI_Y, V.ROI_W, V.ROI_H
    cmd = ["ffmpeg", "-v", "error"] + (["-ss", f"{start:.3f}"] if start is not None else []) + ["-i", str(video)]
    cmd += (["-t", f"{dur:.3f}"] if dur else []) + ["-vf", f"scale=1280:720,fps={fps},crop={w}:{h}:{x0}:{y0}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10 ** 8)
    i = 0
    while True:
        raw = p.stdout.read(w * h * 3)
        if len(raw) < w * h * 3:
            break
        yield (start or 0.0) + i / fps, V.lavender_mask(np.frombuffer(raw, np.uint8).reshape(h, w, 3))
        i += 1


def score(mask, tpl, tpl_b, search=3):
    if mask.sum() < 20:
        return 0.0, 0.0
    e, y, x = V.best_template_correlation(mask, tpl)
    th, tw = tpl.shape
    crop = mask[max(0, y - search):y + th + search, max(0, x - search):x + tw + search]
    ph, pw = max(0, tpl_b.shape[0] - crop.shape[0]), max(0, tpl_b.shape[1] - crop.shape[1])
    crop = np.pad(crop, ((0, ph), (0, pw))) if ph or pw else crop
    return float(e), float(V.robust_correlation(crop, tpl_b, SIGMA))


def trim(m):
    ys, xs = np.nonzero(m)
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def locator():
    """One pop-up's word (1094 s), found with the normal template's blurred match: only used to align the others."""
    x0, y0 = V.ROI_X, V.ROI_Y
    m = V.lavender_mask(frame_at(USER, 1094.0)[y0:y0 + V.ROI_H, x0:x0 + V.ROI_W])
    ref_b = V.blur_template(np.load(paths.TEMPLATES_DIR / "chest/en/chest.npy").astype(np.float32), SIGMA)
    _, y, x = V.robust_correlation_at(m, ref_b, SIGMA)
    return trim(m[y:y + 11, x:x + 31]).astype(np.float32)


def settled_crop(t, loc):
    """The pop-up's best frame in [t, t+1.6] s against the locator, cropped 1 px around the locator's place."""
    best = (-1.0, None)
    for _, m in roi_masks(USER, t, 1.6):
        if m.sum() < 20:
            continue
        s, y, x = V.best_template_correlation(m, loc)
        if s > best[0]:
            th, tw = loc.shape
            best = (s, np.pad(m, 2)[y + 1:y + th + 3, x + 1:x + tw + 3])
    return best[1]


def consensus(crops):
    return trim(np.mean(np.stack(crops), axis=0) >= 0.5).astype(np.float32)


def chest_scores(tpl, times):
    tb = V.blur_template(tpl, SIGMA)
    out = []
    for t in times:
        e = b = 0.0
        for _, m in roi_masks(USER, t - 0.2, 1.8):
            se, sb = score(m, tpl, tb, search=8)
            e, b = max(e, se), max(b, sb)
        out.append((t, e, b))
    return out


def certain_proxy(e, b):
    """Today's rules on a pop-up's best exact and blurred scores: fires at 0.75; CERTAIN >= 0.90, HIGH >= 0.85 (CERTAIN by default),
    MEDIUM promoted to HIGH at blurred >= 0.88. Supporting clues (sprite tag) are ignored, so this can only under-count CERTAIN."""
    if e < 0.75:
        return "not fired (fallback channel: APPROX)"
    return "CERTAIN" if e >= 0.85 or b >= 0.88 else "APPROX (MEDIUM)"


def describe(rows, tag):
    ex = np.array([r[1] for r in rows])
    bl = np.array([r[2] for r in rows])
    certain = sum(certain_proxy(r[1], r[2]) == "CERTAIN" for r in rows)
    print(f"  {tag}: {len(rows)} pop-ups, exact {ex.min():.2f}-{ex.max():.2f} (median {np.median(ex):.2f}), >= 0.75 on {int((ex >= 0.75).sum())}, "
          f"blurred median {np.median(bl):.2f}; CERTAIN by today's rules on {certain} of {len(rows)}")
    return certain


def non_chest_max(tpl):
    tb = V.blur_template(tpl, SIGMA)
    near_user = [c["t"] for c in LABELS["chests"]]
    near_en = [float(t) for t in load_ground_truth(GROUND_TRUTH_FILE)]
    out = {}
    for name, video, near in (("maintainer", USER, near_user), ("reference en", EN, near_en), ("PS5 Portuguese", PS5, [])):
        top = [0.0, 0.0]
        for t, m in roi_masks(video, fps=7.5):
            if m.sum() < 40 or any(c - 1.0 <= t <= c + 3.0 for c in near):
                continue
            e, b = score(m, tpl, tb, search=8)
            top = [max(top[0], e), max(top[1], b)]
        out[name] = top
    for case in ("replays_six_chests", "replays_vault_five_chests", "replays_stack_x2_x3", "thiefs_1080p_small_hud", "thiefs_720p_stream_chests"):
        d = np.load(ROOT / "tests/fixtures/popups" / f"{case}.npz")
        h, w = (int(v) for v in d["shape"])
        truth = [r["t"] for r in CASES[case]["truth"]]
        top = [0.0, 0.0]
        for t, packed in zip(d["times"], d["masks"]):
            if any(c - 1.0 <= t <= c + 3.0 for c in truth):
                continue
            m = np.unpackbits(packed)[:h * w].reshape(h, w).astype(np.float32)
            e, b = score(m, tpl, tb, search=8)
            top = [max(top[0], e), max(top[1], b)]
        out[case] = top
    return out


def rare_prefix(t, chest):
    """The word left of the CHEST word on the pop-up's best frame (chest_types' own region)."""
    th, tw = chest.shape
    best = (-1.0, None)
    for _, m in roi_masks(USER, t, 1.6):
        if m.sum() < 20:
            continue
        s, y, x = V.best_template_correlation(m, chest)
        if s > best[0]:
            region = m[max(0, y - 1):y + th + 1, max(0, x - int(1.7 * tw)):max(0, x - 1)]
            cols = region.sum(0) > 0
            # chest_types.prefix_length's own rule: skip the space before CHEST, then the word reaches left until a gap wider than a letter space
            gap_max, i = max(2, int(round(0.12 * tw))), len(cols) - 1
            while i >= 0 and not cols[i] and len(cols) - 1 - i < 4:
                i -= 1
            start, left, gap = i, None, 0
            while i >= 0:
                if cols[i]:
                    left, gap = i, 0
                else:
                    gap += 1
                    if gap > gap_max:
                        break
                i -= 1
            # only a frame where the word has RARE's own width (chest_types: 0.70-0.95 of CHEST): early frames carry the opening streak
            if left is not None and 0.70 * tw <= start - left + 1 <= 0.95 * tw:
                best = (s, trim(region[:, left:start + 1]))
    return best[1].astype(np.float32)


def type_votes(t, chest, prefixes):
    th, tw = chest.shape
    votes = {}
    for _, m in roi_masks(USER, t, 1.6):
        if m.sum() < 20:
            continue
        s, y, x = V.best_template_correlation(m, chest)
        if s < 0.6:
            continue
        kind, _ = CT.classify_line(m, y, x, th, tw, prefixes)
        votes[kind] = votes.get(kind, 0) + 1
    return votes


def cue_eval(templates):
    on = {k: 0.0 for k in templates}
    held = {}
    off = {k: {"maintainer": 0.0, "reference en": 0.0, "PS5": 0.0} for k in templates}
    true_victory = {"reference en": [(255, 265), (500, 507)], "PS5": [(1015, 1030)]}
    for label, video in (("maintainer", USER), ("reference en", EN), ("PS5", PS5)):
        p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "scale=1280:720,fps=1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                             stdout=subprocess.PIPE, bufsize=10 ** 8)
        i = 0
        while True:
            raw = p.stdout.read(1280 * 720 * 3)
            if len(raw) < 1280 * 720 * 3:
                break
            t, f = float(i), np.frombuffer(raw, np.uint8).reshape(720, 1280, 3)
            i += 1
            for name, (tpl, box, windows) in templates.items():
                x0, y0, x1, y1 = box
                mk = M._ink_mask(f[y0:y1, x0:x1], M.WHITE)
                k = mk.sum()
                s = 0.0 if k < 0.45 * tpl.sum() or k > M.MAX_BOX_INK * mk.size else float(np.clip(V.best_template_correlation(mk.astype(np.float32), tpl)[0], 0, 1))
                if label == "maintainer" and any(a - 0.5 <= t <= b + 0.5 for a, b in windows):
                    on[name] = max(on[name], s)
                    if name == "you_placed_bar_75" and t >= 1459:
                        held[name] = max(held.get(name, 0.0), s)
                elif label == "maintainer" and any(a - 3 <= t <= b + 3 for a, b in windows):
                    continue
                elif name == "victory_75" and any(a <= t <= b for a, b in true_victory.get(label, [])):
                    continue
                else:
                    off[name][label] = max(off[name][label], s)
    return on, held, off


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    loc = locator()
    new = [c["t"] for c in LABELS["chests"] if c["what"] == "new_popup"]
    crops = {t: settled_crop(t, loc) for t in new}
    m1 = [t for t in new if t < MATCH1_END]
    m2 = [t for t in new if t >= MATCH1_END]
    print(f"locator {loc.shape[1]}x{loc.shape[0]}; {len(new)} new pop-ups: match 1 {len(m1)}, match 2 {len(m2)}")

    print("\nCHEST word at 75%")
    tpl_m1 = consensus([crops[t] for t in m1])
    print(f"  consensus of match 1 ({tpl_m1.shape[1]}x{tpl_m1.shape[0]}), held out on match 2:")
    describe(chest_scores(tpl_m1, m2), "match 2")
    loo = []
    for t in new:
        tpl = consensus([crops[u] for u in new if u != t])
        loo += chest_scores(tpl, [t])
    print("  leave-one-out over every new pop-up (each scored by a consensus of the others):")
    describe(loo, "all")
    print("    per pop-up: " + ", ".join(f"{t:.0f}:{e:.2f}/{b:.2f}" for t, e, b in loo))
    tpl_all = consensus([crops[t] for t in new])
    lines = [c["t"] for c in LABELS["chests"] if c["what"] == "new_line"]
    print("  chest lines added to CROWN BONUS pop-ups (consensus of all): " + ", ".join(f"{t:.1f}: {e:.2f}/{b:.2f}" for t, e, b in chest_scores(tpl_all, lines)))
    fp = non_chest_max(tpl_all)
    print("  highest on non-chest frames (exact / blurred): " + "; ".join(f"{k} {v[0]:.2f}/{v[1]:.2f}" for k, v in fp.items()))

    print("\nRARE word at 75% (types never change counts)")
    from collections import Counter
    rares = [c["t"] for c in LABELS["chests"] if c["type"] == "rare" and c["what"] == "new_popup"]
    words = {t: rare_prefix(t, tpl_all) for t in rares}
    sprite = np.load(paths.TEMPLATES_DIR / "chest/en/sprite.npy").astype(np.float32)
    for t, w in words.items():
        other = [u for u in rares if u != t][0]
        votes = type_votes(other, tpl_all, {CT.RARE: w, CT.SPRITE: sprite})
        print(f"  cut from {t:.1f} ({w.shape[1]}x{w.shape[0]}) -> the other rare pop-up ({other:.1f}): {votes} -> {CT.decide(Counter(votes))}")
    ra, rb = (words[t] for t in rares)                 # the two cuts aligned (shift 0-2 px) and kept where both agree on average
    h, w = max(ra.shape[0], rb.shape[0]) + 2, max(ra.shape[1], rb.shape[1]) + 2
    best = (-2.0, None)
    for dy in range(3):
        for dx in range(3):
            pa, pb = np.zeros((h, w)), np.zeros((h, w))
            pa[1:1 + ra.shape[0], 1:1 + ra.shape[1]] = ra
            pb[dy:dy + rb.shape[0], dx:dx + rb.shape[1]] = rb
            c = float(np.corrcoef(pa.ravel(), pb.ravel())[0, 1])
            if c > best[0]:
                best = (c, (pa + pb) / 2)
    rare = trim(best[1] >= 0.5).astype(np.float32)
    print(f"  consensus of both ({rare.shape[1]}x{rare.shape[0]}, cuts agree at {best[0]:.2f}): " + ", ".join(
        f"{t:.1f} -> {CT.decide(Counter(type_votes(t, tpl_all, {CT.RARE: rare, CT.SPRITE: sprite})))}" for t in rares + [1223.7]))
    normals = [c["t"] for c in LABELS["chests"] if c["type"] == "chest" and c["what"] == "new_popup"]
    print("  plain CHEST pop-ups with that RARE word: " + ", ".join(
        f"{t:.0f}: {CT.decide(Counter(type_votes(t, tpl_all, {CT.RARE: rare, CT.SPRITE: sprite})))[0]}" for t in normals))

    print("\nMatch text at 75% (score while on screen | highest elsewhere: maintainer / reference / PS5)")
    cues = {}
    for name, (t, box, search, windows) in CUES75.items():
        x0, y0, x1, y1 = box
        cues[name] = (trim(M._ink_mask(frame_at(USER, t)[y0:y1, x0:x1], M.WHITE)), search, windows)
    on, held, off = cue_eval({k: (v[0].astype(np.float32), v[1], v[2]) for k, v in cues.items()})
    for name in cues:
        o = off[name]
        extra = f" (held out on the second recap: {held[name]:.2f})" if name in held else ""
        print(f"  {name:22s} {cues[name][0].shape[1]:3d}x{cues[name][0].shape[0]:2d}  {on[name]:.2f}{extra} | {o['maintainer']:.2f} / {o['reference en']:.2f} / {o['PS5']:.2f}")

    if a.write:
        CHEST_OUT.mkdir(parents=True, exist_ok=True)
        np.save(CHEST_OUT / "chest.npy", tpl_all.astype(np.float32))
        np.save(CHEST_OUT / "rare.npy", rare.astype(np.float32))
        for name, (tpl, _, _) in cues.items():
            np.save(M.TEMPLATE_DIR / f"{name}.npy", tpl.astype(bool))
        print("\nwritten:", CHEST_OUT / "chest.npy", CHEST_OUT / "rare.npy", *(M.TEMPLATE_DIR / f"{n}.npy" for n in cues))


if __name__ == "__main__":
    main()
