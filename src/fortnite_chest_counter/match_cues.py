"""
What is on screen, as individual scores (v0.3.0, English). Evidence only: this module never decides that a match started or ended.

The game's fixed interface text is found the same way as the chest word: a small bitmap of the word is slid over a small box of the
1280x720 frame the detector already has (visual.best_template_correlation). Every score is 0 to 1, one per signal, for example
{"you_placed": 0.99, "connecting": 0.04, "lobby_menu": 0.02}. A later stage turns those into states and needs to know nothing about images.

Nothing here writes to the frame, keeps it, or touches chest detection, counting, saved data, OBS output or the app window.

    signals             what each one means                                how sure the evidence is
    you_placed          "YOU PLACED #N": eliminated, placement shown       one match end, recorded twice
    eliminated_by       "ELIMINATED BY": killed by another player          one match end, recorded twice
    connecting          "CONNECTING...": loading                           three artworks, two sessions; on the white
                                                                           return-to-lobby splash, its grey shadow (one splash)
    lobby_menu          the menu bar: at least two of three words          one lobby, two tabs
    matchmaking         "CANCEL": in the matchmaking queue                 one lobby
    waiting_for_players the pre-game island countdown                      one match start, and one on a smaller HUD
    bus_launching       "... LAUNCHING IN": the bus is about to leave      one match start, and one on a smaller HUD
    spectating          "SPECTATING:": watching another player             one match end, recorded twice
    victory_royale      PROVISIONAL, see below                             three wins, two banner sizes
    ready_overlay       READY: "PARTY TO READY UP..." / "NEXT MATCH" after  two overlays of one session (v0.4.1)
                        a match: the player readied up straight from it

victory_royale is a template of the word ROYALE at the two banner sizes seen so far. A second English win from the same creator scored
0.93 to 0.97 against the template cut from the first. A template from the English win found the Portuguese win (and the reverse, 0.83
to 0.86) only after being resized by about 1.27 times, so a third size may score low. ROYALE is the same word in Portuguese, so this
signal alone must not be taken as evidence of an English game.

Supporting evidence, never a match ending on its own: `picture_evidence` (black or frozen picture), `health_bar_pixels` (loading
artwork can imitate a health bar), and `CueReader.hud_in_view` (the fixed parts of the HUD: is the game still on screen at all?). The HUD is
also there on the waiting island, so it says nothing about whether a match has started or ended.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from fortnite_chest_counter import paths
from fortnite_chest_counter.detection.visual import NORMALIZED_HEIGHT, NORMALIZED_WIDTH, best_template_correlation

TEMPLATE_DIR = paths.TEMPLATES_DIR / "match" / "en"
SCORE_THRESHOLD = 0.70                     # a score at or above this means the text is there
WHITE, DARK, SHADOW = "white", "dark", "shadow"
WHITE_LEVEL, DARK_LEVEL = 200, 90          # white text: every channel at least this; dark text: every channel at most this
# The shadow of white text on a near-white picture (v0.4.1): the white CONNECTING... on the return-to-lobby splash cannot be told from its
# background, but its grey shadow can. Shadow ink is anything under near-white, so on ordinary frames the box is almost all "ink" and
# MAX_BOX_INK makes it score 0; only a near-white box can match.
SHADOW_LEVEL = 215
SHADOW_MAX_INK = 0.25                      # shadow text is a thin outline on a near-white field: the splash box is 6% shadow ink, ordinary frames 30-100%
MIN_INK_SHARE = 0.45                       # with under this share of a word's ink in the box, the correlation cannot reach 0.70 (see _score)
MAX_BOX_INK = 0.70                         # a box this full of "ink" is bright sky or snow, not text: its correlation is meaningless (0.49 was seen)

BLACK_LUMA = 12.0                          # mean brightness below this is "no picture"
FROZEN_CHANGE = 0.05                       # mean change per channel between samples, on a 0-255 scale, below this is "frozen"
HEALTH_BAR_MIN_PIXELS = 30                 # a solid bar: the fourth longest row of bar-coloured pixels is at least this long
_SAMPLE_STEP = 16                          # every 16th pixel each way: 80 x 45 is enough to tell a picture changed
HUD_TEMPLATE_DIR = paths.TEMPLATES_DIR / "match" / "hud"
HUD_EDGE = 28.0                            # a brightness step this big between neighbouring pixels is an edge
HUD_SEARCH = 6                             # how far a HUD shape may sit from where it was measured


@dataclass(frozen=True)
class Cue:
    name: str
    box: tuple                             # x0, y0, x1, y1 in the 1280x720 frame: the word's position plus room for it to move
    ink: str = WHITE


CUES = (Cue("you_placed_screen", (514, 86, 707, 140)), Cue("you_placed_bar", (536, 6, 700, 56)),
        Cue("eliminated_by", (488, 566, 720, 614)), Cue("connecting", (36, 632, 220, 679)),
        Cue("connecting_shadow", (36, 632, 230, 679), SHADOW),
        # The READY overlay after a match (v0.4.1, the maintainer's ready-up): its two right-hand lines, at the same place in both overlays seen.
        Cue("ready_party", (978, 600, 1270, 646)), Cue("ready_finding", (946, 584, 1130, 630)),
        # Fortnite HUD Scale 75% (v0.4.1): the same texts as the game draws them there, cut from the maintainer's recording (2560x1440 through
        # OBS 1280x720), in the boxes of their normal-size versions. Read only for a profile with that HUD (HUD_SCALE_CUES).
        Cue("waiting_for_players_75", (552, 80, 752, 120)), Cue("bus_launching_75", (600, 58, 800, 94)),
        Cue("you_placed_screen_75", (514, 86, 707, 140)), Cue("you_placed_bar_75", (536, 6, 700, 56)), Cue("victory_75", (550, 121, 754, 188)),
        Cue("menu_locker", (304, 27, 414, 66)), Cue("menu_quests", (479, 27, 586, 66)), Cue("menu_career", (665, 27, 775, 66)),
        Cue("matchmaking_cancel", (101, 586, 246, 632), DARK), Cue("waiting_for_players", (552, 80, 752, 120)),
        Cue("bus_launching", (600, 58, 800, 94)),          # wider: the sentence is centred, and the bus's name changes each season
        Cue("spectating", (1012, 0, 1157, 36)), Cue("victory_large", (550, 121, 754, 188)), Cue("victory_small", (561, 94, 736, 152)),
        # The same two sentences on a HUD drawn about 0.78x: at that size the normal templates score under 0.3, so the game's start is missed.
        Cue("waiting_for_players_small", (570, 78, 735, 104)), Cue("bus_launching_small", (600, 58, 800, 84)))
_CUE = {cue.name: cue for cue in CUES}



@dataclass(frozen=True)
class HudCue:
    name: str
    box: tuple                             # x0, y0, x1, y1: where the shape was measured, in the 1280x720 frame
    line: float                            # at or above this the shape is there. research/hud_view_eval.py: play was above and browser pages below at 0.8x to 1.25x of it


# The stat icons beside the minimap and the compass arrow, at the two HUD sizes seen. These never change shape, unlike what is drawn inside the minimap,
# the compass numbers or the hotbar's items. Measured and left out: the minimap's frame (browser pages came too close) and the hotbar (it moves with the selected slot).
HUD_CUES = (HudCue("stats", (1095, 20, 1119, 60), 0.40), HudCue("stats_small", (1135, 20, 1154, 52), 0.40),
            HudCue("compass", (630, 16, 650, 28), 0.35), HudCue("compass_small", (630, 16, 650, 28), 0.35))
_HUD_CUE = {cue.name: cue for cue in HUD_CUES}

_MENU = ("menu_locker", "menu_quests", "menu_career")
# signal -> the templates behind it. The highest score wins, except the menu bar, where two of the three words must agree.
SIGNALS = {"you_placed": ("you_placed_screen", "you_placed_bar", "you_placed_screen_75", "you_placed_bar_75"), "eliminated_by": ("eliminated_by",), "connecting": ("connecting", "connecting_shadow"),
           "lobby_menu": _MENU, "matchmaking": ("matchmaking_cancel",), "waiting_for_players": ("waiting_for_players", "waiting_for_players_small", "waiting_for_players_75"),
           "bus_launching": ("bus_launching", "bus_launching_small", "bus_launching_75"), "spectating": ("spectating",), "victory_royale": ("victory_large", "victory_small", "victory_75"),
           "ready_overlay": ("ready_party", "ready_finding")}
PROVISIONAL_SIGNALS = frozenset({"victory_royale"})          # too few examples to rely on by itself
# Templates of one Fortnite HUD Scale, read only when the profile has that HUD ([detector] hud). Every other template is always read.
HUD_SCALE_CUES = {"75": frozenset({"waiting_for_players_75", "bus_launching_75", "you_placed_screen_75", "you_placed_bar_75", "victory_75"})}
NOT_ENGLISH_SPECIFIC = frozenset({"victory_royale"})         # the same word appears in the Portuguese game


def _ink_mask(region, ink):
    if ink == SHADOW:
        return region.max(axis=2) <= SHADOW_LEVEL
    return region.min(axis=2) >= WHITE_LEVEL if ink == WHITE else region.max(axis=2) <= DARK_LEVEL


def _check_frame(frame):
    if frame.shape != (NORMALIZED_HEIGHT, NORMALIZED_WIDTH, 3):
        raise ValueError(f"expected a {NORMALIZED_WIDTH}x{NORMALIZED_HEIGHT} RGB frame, got shape {frame.shape}")


class CueReader:
    """Loads the word templates once. `read` can then be called for each frame; it keeps nothing between calls."""

    def __init__(self, folder=None, hud="standard"):
        """hud: the profile's Fortnite HUD Scale ([detector] hud). Its own templates are read too; an unknown value reads the standard ones."""
        folder = Path(folder) if folder is not None else TEMPLATE_DIR
        skip = set().union(*HUD_SCALE_CUES.values()) - HUD_SCALE_CUES.get(hud, frozenset())
        self._templates = {cue.name: np.load(folder / f"{cue.name}.npy").astype(np.float32) for cue in CUES if cue.name not in skip}
        self._ink = {name: float(template.sum()) for name, template in self._templates.items()}
        self._hud = {cue.name: np.load(HUD_TEMPLATE_DIR / f"{cue.name}.npy").astype(np.float32) for cue in HUD_CUES}
        self._hud_edges = {name: float(template.sum()) for name, template in self._hud.items()}

    def _score(self, frame, name):
        """One template's best score in its box. A window holding k of the n ink pixels correlates at most sqrt(k/n), so when the
        whole box has under 45% of the word's ink the word cannot reach the threshold and the comparison is skipped. A box almost
        entirely full of ink has no readable word in it either."""
        cue = _CUE[name]
        x0, y0, x1, y1 = cue.box
        mask = _ink_mask(frame[y0:y1, x0:x1], cue.ink)
        ink = int(mask.sum())
        if ink < MIN_INK_SHARE * self._ink[name] or ink > (SHADOW_MAX_INK if cue.ink == SHADOW else MAX_BOX_INK) * mask.size:
            return 0.0
        return float(np.clip(best_template_correlation(mask.astype(np.float32), self._templates[name])[0], 0.0, 1.0))

    def template_scores(self, frame, names=None):
        """{template name: score}, for debugging and research."""
        _check_frame(frame)
        return {name: self._score(frame, name) for name in (names if names is not None else self._templates)}

    def read(self, frame, signals=None):
        """{signal: score, 0 to 1} for every signal, or only the ones named. Never writes to `frame`."""
        _check_frame(frame)
        out = {}
        for signal in (signals if signals is not None else SIGNALS):
            scores = [self._score(frame, name) for name in SIGNALS[signal] if name in self._templates]
            out[signal] = sorted(scores)[-2] if signal == "lobby_menu" else max(scores)
        return out

    def hud_score(self, name, mask):
        """How well a box of edges (see `hud_edges`) matches one HUD shape, 0 to 1."""
        if not mask.any():
            return 0.0
        score = float(best_template_correlation(mask.astype(np.float32), self._hud[name])[0])
        return float(np.clip(score, 0.0, 1.0)) if np.isfinite(score) else 0.0

    def hud_in_view(self, frame):
        """Is any fixed part of the HUD on screen? Evidence that the game is being shown, never that a match started or ended. Never writes to `frame`."""
        _check_frame(frame)
        masks = {}                                         # the two compass sizes share one box
        for cue in HUD_CUES:
            if cue.box not in masks:
                masks[cue.box] = hud_edges(frame, cue.box, HUD_SEARCH)
            if self._hud_seen(cue, masks[cue.box]):
                return True
        return False

    def _hud_seen(self, cue, mask):
        """A window holding k of the shape's n edge pixels correlates at most sqrt(k/n), so a box with fewer than line^2 * n edges cannot
        reach the line and is not compared: the answer is the same, only cheaper."""
        if mask.sum() < cue.line ** 2 * self._hud_edges[cue.name]:
            return False
        return self.hud_score(cue.name, mask) >= cue.line


@dataclass(frozen=True)
class PictureEvidence:
    mean_luma: float
    change: object                         # mean change from the previous sample, or None when there is no previous sample
    black: bool
    frozen: bool
    sample: np.ndarray                     # pass this back as `previous` for the next frame


def picture_evidence(frame, previous=None):
    """Is there a live picture at all? Supporting evidence for whether other signals can be trusted, never a match ending by itself."""
    _check_frame(frame)
    sample = frame[::_SAMPLE_STEP, ::_SAMPLE_STEP].copy()
    luma = float(sample.mean())
    change = None if previous is None else float(np.abs(sample.astype(np.int16) - previous.astype(np.int16)).mean())
    return PictureEvidence(luma, change, luma < BLACK_LUMA, change is not None and change < FROZEN_CHANGE, sample)


def hud_edges(frame, box, pad):
    """Where brightness jumps inside `box`, widened by `pad` on every side, as True/False. Edges survive any background, which colours do not."""
    x0, y0, x1, y1 = box
    gray = frame[y0 - pad:y1 + pad + 1, x0 - pad:x1 + pad + 1].astype(np.float32).mean(axis=2)
    return np.abs(gray[:-1, 1:] - gray[:-1, :-1]) + np.abs(gray[1:, :-1] - gray[:-1, :-1]) >= HUD_EDGE


def health_bar_pixels(frame):
    """The fourth longest row of health- or shield-coloured pixels at the bottom left. Supporting evidence only: loading art can imitate it."""
    _check_frame(frame)
    roi = frame[610:716, 0:420].astype(np.int16)
    red, green, blue = roi[..., 0], roi[..., 1], roi[..., 2]
    rows = (((green > 165) & (green - red > 45) & (blue < 130)) | ((blue > 165) & (red < 110) & (green > 110))).sum(axis=1)
    return int(np.partition(rows, -4)[-4])


def health_bar_green_pixels(frame):
    """The same measure for the green health bar alone. The lobby's blue PARTY CHANNEL tiles sit where a small HUD draws the bar and pass
    the shield colour test, but have no green: in the M9H footage every one of 67 menu samples with a "bar" was blue only, while 123 of
    126 in play had the green bar (the other 3 were a thin shield bar at low health)."""
    _check_frame(frame)
    roi = frame[610:716, 0:420].astype(np.int16)
    red, green, blue = roi[..., 0], roi[..., 1], roi[..., 2]
    rows = ((green > 165) & (green - red > 45) & (blue < 130)).sum(axis=1)
    return int(np.partition(rows, -4)[-4])
