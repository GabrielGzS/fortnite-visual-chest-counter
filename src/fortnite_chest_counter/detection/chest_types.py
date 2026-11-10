"""
Chest type from the pop-up line (v0.2.2, docs/reference/INVESTIGATION_2026-11-08.md): "CHEST", "RARE CHEST" or "SPRITE CHEST".

Classification never creates or removes a count: it only labels a chest the counter already counted. What is read:

  * the word LEFT of the line's CHEST word. Nothing there -> a normal chest.
  * its LENGTH, relative to the CHEST word (so it works at any HUD size): RARE 0.77-0.89, SPRITE 1.04-1.18 on the
    labelled footage, nothing (normal chest) 0.00-0.04. A shorter template can match the tail of a longer word, so length
    decides and the word confirms it: the EXACT match of the length-matching word >= WORD_MIN and >= WORD_MARGIN above
    the other word (real words: 0.67-0.94 median, the other word 0.22-0.39; random ink of the same length: <= 0.41 - a
    blurred match was rejected: random ink reached 0.65 against it).
  * anything else (another word, background ink, a length in between) -> "unknown". An uncertain line is never called
    a normal chest just because RARE / SPRITE was not recognised.

The type of a counted chest is the majority of its line's per-frame readings while the pop-up stays on screen (votes),
so a type can become known after the chest was counted - that changes the label, never the count.

To add a type: cut its word as a template (prefix templates below, one per HUD size), give its length range in TYPES.
Templates: chest/en/rare*.npy and sprite*.npy, cut from the English reference clip (RARE, normal size), Replays'
stream (SPRITE, normal size) and Thiefs' stream (both, small size).
"""

from collections import Counter

import numpy as np

from fortnite_chest_counter import paths
from fortnite_chest_counter.detection import popup_lines, visual as V

NORMAL, RARE, SPRITE, UNKNOWN = "chest", "rare", "sprite", "unknown"
KNOWN = (NORMAL, RARE, SPRITE)                      # display order; UNKNOWN is always kept separately
LABELS = {NORMAL: "Chest", RARE: "Rare chest", SPRITE: "Sprite chest", UNKNOWN: "Unknown type"}
# type -> (prefix length range relative to the CHEST word, template file per HUD size)
TYPES = {RARE: ((0.70, 0.95), {"normal": "chest/en/rare.npy", "small": "chest/en/rare_small.npy"}),
         SPRITE: ((0.98, 1.28), {"normal": "chest/en/sprite.npy", "small": "chest/en/sprite_small.npy"})}
EMPTY_MAX = 0.25                 # prefix length below this = no prefix word = a normal chest
WORD_MIN = 0.50                  # exact match of the length-matching word...
WORD_MARGIN = 0.15               # ...and its lead over the other word
VOTES_MIN = 3                    # per-frame readings needed before a line's type is decided...
MAJORITY = 0.6                   # ...and the share the winning type needs
SIGMA = 0.6


def load_prefixes(size):
    """{type: binary word template} for "normal" or "small" HUD size."""
    return {kind: np.load(paths.TEMPLATES_DIR / files[size]).astype(np.float32) for kind, (_, files) in TYPES.items()}


def load_french_suffixes():
    # RARE has the same letters in both languages. The sprite suffix is from the XP line COFFRE À ESPRIT.
    return {RARE: load_prefixes("normal")[RARE],
            SPRITE: np.load(paths.TEMPLATES_DIR / "chest/fr/esprit.npy").astype(np.float32)}


def classify_french_line(mask, y, x, th, tw, suffixes):
    """Read the qualifier to the right of COFFRE on the same XP line."""
    end = x + tw
    if x < 4 or y < 2 or y + th + 2 > mask.shape[0] or end + tw > mask.shape[1]:
        return UNKNOWN
    left = prefix_length(mask, y, x, th, tw)
    if left >= EMPTY_MAX:
        return UNKNOWN
    # Leave room for the gap, and for the short word À in COFFRE À ESPRITS.
    region = mask[y - 2:y + th + 2, end + 1:end + int(1.8 * tw)]
    scores = {}
    for kind, template in suffixes.items():
        if region.shape[0] < template.shape[0] or region.shape[1] < template.shape[1]:
            continue
        score, _, offset = V.best_template_correlation(region, template)
        if offset <= (tw * 0.65 if kind == SPRITE else tw * 0.35):
            scores[kind] = score
    for kind, score in scores.items():
        other = max((v for k, v in scores.items() if k != kind), default=0.0)
        if score >= WORD_MIN and score - other >= WORD_MARGIN:
            return kind
    # A qualifier we cannot read must not silently become a normal chest.
    return NORMAL if not region[:, 2:tw].any() else UNKNOWN


def french_sprite_score(mask, y, x, th, tw, template):
    end = x + tw
    region = mask[max(0, y - 3):y + th + 5, max(0, end - 1):end + int(1.8 * tw)]
    if region.shape[0] < template.shape[0] or region.shape[1] < template.shape[1]:
        return 0.0
    score, _, offset = V.best_template_correlation(region, template)
    return score if offset <= tw * 0.4 else 0.0


def prefix_length(mask, y, x, th, tw):
    """Width of the word directly left of the CHEST word at (y, x), as a share of the CHEST word's width."""
    region = mask[max(0, y - 1):y + th + 1, max(0, x - int(1.7 * tw)):max(0, x - 1)]
    if region.size == 0:
        return 0.0
    cols = region.sum(0) > 0
    gap_max = max(2, int(round(0.12 * tw)))
    i = len(cols) - 1
    while i >= 0 and not cols[i] and len(cols) - 1 - i < 4:      # the 1-2 px space before CHEST
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
    return 0.0 if left is None else (start - left + 1) / tw


def classify_line(mask, y, x, th, tw, prefixes):
    """One frame's reading of one chest line -> (type, evidence dict)."""
    length = prefix_length(mask, y, x, th, tw)
    if length < EMPTY_MAX:
        return NORMAL, {"prefix_length": round(length, 2)}
    region = mask[max(0, y - 3):y + th + 3, max(0, x - int(1.7 * tw)):max(0, x - 1)]
    scores = {k: (V.best_template_correlation(region, tpl)[0]
                  if region.shape[0] >= tpl.shape[0] and region.shape[1] >= tpl.shape[1] else 0.0)
              for k, tpl in prefixes.items()}
    for kind, ((lo, hi), _) in TYPES.items():
        if lo <= length <= hi:
            other = max((v for k, v in scores.items() if k != kind), default=0.0)
            evidence = {"prefix_length": round(length, 2), "word_score": round(scores[kind], 2), "other": round(other, 2)}
            if scores[kind] >= WORD_MIN and scores[kind] - other >= WORD_MARGIN:
                return kind, evidence
            return UNKNOWN, evidence
    return UNKNOWN, {"prefix_length": round(length, 2)}


def decide(votes):
    """Per-frame readings (a Counter) -> (type, confidence 0-1). UNKNOWN until enough readings agree."""
    total = sum(votes.values())
    if total < VOTES_MIN:
        return UNKNOWN, 0.0
    kind, n = max(votes.items(), key=lambda kv: kv[1])
    share = n / total
    return (kind, round(share, 2)) if kind != UNKNOWN and share >= MAJORITY else (UNKNOWN, round(share, 2))


class FrenchQualifiedPopups:
    """Stable quantities of rare and sprite chests in one visible French XP group."""

    def __init__(self):
        folder = paths.TEMPLATES_DIR / "chest/fr"
        self.templates = [(kind, quantity, V.blur_template(np.load(folder / f"stack_{name}.npy"), SIGMA))
                          for kind, quantity, name in ((RARE, 1, "rare"), (RARE, 2, "x2"),
                                                      (SPRITE, 1, "sprite"))]
        self.exp = np.load(folder / "stack_exp.npy")
        self.last_seen = None
        self.rows = []
        self.totals = Counter()
        self.candidate = None
        self.frames = 0

    def observe(self, t, roi):
        if self.last_seen is not None and t - self.last_seen > 0.55:
            self.rows = []
            self.totals.clear()
            self.candidate = None
            self.frames = 0
        # The qualifiers and multiplier appear on the right side of the XP notification.
        bright = roi[33:124, 125:225].min(axis=2)
        peaks = []
        for level in (155, 178):
            mask = (bright > level).astype(np.float32)
            if mask.sum() < 50:
                continue
            for kind, quantity, template in self.templates:
                for score, y, x in popup_lines.correlation_peaks(mask, template, 0.76):
                    if 5 <= x <= 45:
                        peaks.append((score, y + 36, x + 139, kind, quantity))
        rows = []
        for row in sorted(peaks, reverse=True):
            if all(abs(row[1] - other[1]) >= 6 for other in rows):
                rows.append(row)
        if not rows:
            return []
        if not self.totals:
            top = min(row[1] for row in rows) - 3
            # Require the XP heading above a new group before owning the individual lines.
            exp = roi[max(0, top - 23):top - 1, 157:207]
            if exp.shape[0] < self.exp.shape[0] or max(
                    V.best_template_correlation((exp.min(axis=2) > level).astype(np.float32), self.exp)[0]
                    for level in (135, 155)) < 0.60:
                return []
        self.last_seen = t
        counts = Counter()
        for _, _, _, kind, quantity in rows:
            counts[kind] += quantity
        self.frames = self.frames + 1 if counts == self.candidate else 1
        self.candidate = counts
        if self.frames < VOTES_MIN:
            return []
        self.rows = rows
        added = []
        for kind, quantity in counts.items():
            delta = quantity - self.totals[kind]
            if delta > 0:
                row = next(row for row in rows if row[3] == kind)
                added.extend([row] * delta)
                self.totals[kind] = quantity
        return added

    def owns(self, y, x):
        # The short-word reader can lock onto the qualifier to the right of COFFRE.
        return any(abs(row_y - y) <= 8 and -23 <= x - row_x <= 34 for _, row_y, row_x, _, _ in self.rows)
