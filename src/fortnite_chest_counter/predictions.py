"""
Predictions (v0.5.0): what a profile's counted chests mean for a pool of treasure rewards. Estimates only, like APPROX: the best number
available, never a record of what dropped. Pure apart from reading a pool file and the profile's own predictions.jsonl, so every rule is
unit-tested without the app.

Three kinds of information stay apart:
  * Estimated: the recorded chests (progression.Snapshot.events: detected chests plus your standing +1/-1; Reset, Edit counts, chests seen
    while spectating and `simulate` runs are never in it) and the pool's published odds. Everything on the page.
  * Reported: your own "Mark obtained" (source "manual"), with its time. Never inferred from a percentage.
  * Detected: future treasure recognition, the same row with source "detected". Not built.

Per reward:
  * chance in this cycle: 1 - (1 - p)^n over the chests of the current cycle;
  * statistically expected: chests x p over the whole pool so far (for a weekly reward: as if each week offered one);
  * reported obtained.
Cycles. A repeatable reward (Gizmo) starts a new cycle by itself each time it reaches CYCLE_MILESTONE: a completed cycle, never an
obtained reward. A weekly reward's cycle is its week, so the Sunday rotation starts a new one and nothing carries over. A pool reward
(Pirate Shop Access) has one cycle for the whole pool. "Start new cycle" restarts a cycle by hand; "Mark obtained" stops a unique reward's
chance until a later restart or rotation. Both are rows, and Undo is a row too: nothing is ever deleted, and automatic cycles are worked
out from the chests, never stored, so a corrected history recalculates everything.

The odds are the same for every player and every chest (Epic), so a past drought never makes the next chest luckier: forecasts and the
What If? roll start from now.

Treasure Hours. A pool lists the verified ones (times and a multiplier per reward). A chest opened inside one counts at its boosted odds
for that reward, so the chance is 1 - prod(1 - p_i), worked with "normal-odds chests": n chests at p*m are worth n*log(1-p*m)/log(1-p)
chests at p. Nothing is boosted that the pool does not list, and forecasts use the normal odds (an event lasts hours, not the whole hunt).
What If? can try any multiplier, labelled hypothetical.

Chests you add with Edit counts. The history only has chests the app counted. When you raise APPROX with Edit counts (chests opened
before you used the counter, say), the dialog can add the difference to Predictions as an ADJUST row here: never in the history, so
Analytics, chests per hour and per minute, matches and pace never see it, and no chest is ever invented at a moment in time. Added
chests count at normal odds at the start of their period: "season" (the week is not known: season rewards only) or one reward week (that
week's weekly rewards and the season's). A restart later in the period leaves them out, like any chest before it. A lower count takes
back from what you added, never below zero, and Predictions never use more chests this season than the new total (reconcile), so editing
again after more chests, or after a Reset, never counts the same chests twice. Reset changes nothing here.

Team scenarios (Solo, Duo, Trio, Squad) are a view, never saved: your actual position in each reward's own period (its week, or the
season), in normal-odds chests, times team_factor, as if teammates had opened 80% as many chests as you all along. The chance, the bar,
the expected number, a Gizmo's hypothetical cycles and the chests still needed all come from that modeled position; the actual ones are
kept beside them, and Solo is exactly the actual view. A reported reward is never modeled.

Seasons and periods. Every pool file in pools/ is a season; its periods are its weeks (start, rotations, end), named by a stable id: the
UTC date the period starts. Rows store the pool id and the period id, so a later pool never takes another season's chests.

Assigning added chests to weeks (ALLOCATE): optional. It moves chests you already added between "week not known" and the reward weeks
that had begun by then; it never adds or removes a chest, and what is not assigned stays for season rewards only. The rows are folded
in time order, so later Edit counts rows add on top of an allocation, and Undo of an allocation brings back the split before it.
"""

import json
import math
import random
import uuid
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fortnite_chest_counter import match_history as H

UTC = timezone.utc
POOLS_DIR = Path(__file__).resolve().parent / "pools"
DEFAULT_POOL = POOLS_DIR / "ch7_treasure_hunters.json"
ACTIONS_FILE = "predictions.jsonl"
POOL_FORMAT = 1
REPEATABLE, WEEKLY, POOL = "repeatable", "weekly", "pool"
KINDS = (REPEATABLE, WEEKLY, POOL)
CYCLE_MILESTONE = 0.90                     # a repeatable reward's automatic cycle, and the bar's target
MILESTONES = (0.50, 0.90)
TEAMS = (("Solo", 1), ("Duo", 2), ("Trio", 3), ("Squad", 4))
TEAMMATE_SHARE = 0.8                       # a teammate is assumed to open 80% as many chests as you: a safe average, never detected
RESTART, OBTAINED, UNDO, ADJUST, ALLOCATE = ("prediction_restart", "prediction_obtained", "prediction_undo", "prediction_chests",
                                             "prediction_allocation")
ACTION_KINDS = (RESTART, OBTAINED, UNDO, ADJUST, ALLOCATE)
SEASON, WEEK = "season", "week"            # an ADJUST row's period
MANUAL = "manual"
MULTIPLIERS = (1.0, 1.5, 2.0, 7.5, 10.0)   # What If? choices; Epic announced 1.5x-10x for some rewards
RATE_PERIODS = (("last7", "last 7 days"), ("all", "all your history"))


class PoolError(ValueError):
    pass


# ------------------------------------------------------------------ the maths
def chance(n, p):
    """The chance of at least one drop in n chests of chance p each. Exact for tiny p (expm1 / log1p)."""
    return 0.0 if n <= 0 else -math.expm1(n * math.log1p(-p))


def more_to(milestone, p, have=0.0):
    """Chests still needed at chance p, from `have` normal-odds chests, to reach `milestone`. 0 when reached."""
    if chance(have, p) >= milestone:
        return 0
    k = max(1, math.ceil(math.log1p(-milestone) / math.log1p(-p) - have))
    while k > 1 and chance(have + k - 1, p) >= milestone:
        k -= 1
    while chance(have + k, p) < milestone:
        k += 1
    return k


def chests_to(milestone, p):
    """The fewest chests whose chance reaches `milestone` (0 < milestone < 1). There is no chest count for 100%."""
    n = max(1, math.ceil(math.log1p(-milestone) / math.log1p(-p)))
    while n > 1 and chance(n - 1, p) >= milestone:          # guard against rounding either way
        n -= 1
    while chance(n, p) < milestone:
        n += 1
    return n


def percent(x):
    """A chance for display: never "100%" (a random drop is never certain) and never "0%" for a real chance."""
    if x <= 0:
        return "0%"
    if x < 0.0001:
        return "<0.01%"
    if x >= 0.9999:
        return ">99.99%"
    if x < 0.10 or x >= 0.99:
        return f"{100 * x:.2f}%"
    return f"{100 * x:.1f}%"


def team_factor(team):
    """How many of your chests a team opens in the same time: you, plus each teammate at TEAMMATE_SHARE (Duo 1.8, Trio 2.6, Squad 3.4)."""
    return 1.0 + TEAMMATE_SHARE * (max(int(team), 1) - 1)


def hours(chests, rate, team=1):
    """Hours of real life for `chests` at your `rate` chests per hour, with `team` players opening chests. None without a rate."""
    return None if not rate or rate <= 0 else chests / (rate * team_factor(team))


def short_hours(h):
    """Hours for a large number on a card: "27 min", "1.5 h", "715 h", "33,312 h"."""
    if h is None:
        return None
    if h < 1:
        return f"{max(1, round(h * 60))} min"
    return f"{h:.1f} h" if h < 100 else f"{round(h):,} h"


CURVE_TOP = 0.9999                         # the probability curve runs from 0 to the chests for 99.99%


def curve(p, points=240, top=CURVE_TOP):
    """[(chests, chance)] from 0 to the chests for `top`, evenly spaced, and that last chest count: what the probability curve draws."""
    end = chests_to(top, p)
    return [(end * i / points, chance(end * i / points, p)) for i in range(points + 1)], end


def duration(h):
    if h is None:
        return None
    if h < 1:
        return f"{max(1, round(h * 60))} min"
    if h < 100:
        return f"{h:.1f} h"
    text = f"{round(h):,} h"
    return text + (f" (about {round(h / 24):,} days nonstop)" if h >= 1000 else "")


# ------------------------------------------------------------------ pools
@dataclass(frozen=True)
class Reward:
    id: str
    name: str
    odds: int                              # 1 in `odds` per chest
    kind: str

    @property
    def p(self):
        return 1.0 / self.odds


@dataclass(frozen=True)
class Pool:
    id: str
    revision: int
    name: str
    start: datetime
    end: datetime
    end_estimated: bool
    rotations: tuple                       # the weekly rotations inside the pool
    rewards: tuple
    about: tuple
    sources: tuple
    treasure_hours: tuple = ()             # verified boosts only: (start, end, {reward id: multiplier})

    def weeks(self):
        bounds = (self.start, *self.rotations, self.end)
        return list(zip(bounds, bounds[1:]))

    def week_of(self, when):
        """The index of the week `when` falls in (a rotation begins its week); before the start the first, from the end on the last."""
        return bisect_right(self.rotations, when)

    def period_id(self, index):
        """A period's stable name: the UTC date it starts."""
        return self.weeks()[index][0].date().isoformat()

    def period_index(self, period):
        """The index of a period id, a period index, or a digit string (rows written before v0.5.0 RC4); None if unknown."""
        if isinstance(period, int):
            return period if 0 <= period < len(self.weeks()) else None
        if isinstance(period, str) and period.isdigit():
            return self.period_index(int(period))
        ids = [self.period_id(i) for i in range(len(self.weeks()))]
        return ids.index(period) if period in ids else None


def _when(text, what):
    try:
        moment = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        raise PoolError(f"{what}: not a date and time ({text!r})") from None
    if moment.tzinfo is None:
        raise PoolError(f"{what}: needs its UTC offset ({text!r})")
    return moment.astimezone(UTC)


def parse_pool(data):
    if not isinstance(data, dict) or data.get("format") != POOL_FORMAT:
        raise PoolError(f"not a reward pool of format {POOL_FORMAT}")
    if not isinstance(data.get("id"), str) or not data["id"] or not isinstance(data.get("name"), str):
        raise PoolError("a pool needs an id and a name")
    start, end = _when(data.get("start"), "start"), _when(data.get("end"), "end")
    rotations = tuple(_when(text, "rotation") for text in data.get("rotations", []))
    if not start < end or list(rotations) != sorted(set(rotations)) or any(not start < r < end for r in rotations):
        raise PoolError("start, rotations and end must be in order, the rotations inside the pool")
    rewards, seen = [], set()
    for item in data.get("rewards", []):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item["id"] in seen or not isinstance(item.get("name"), str):
            raise PoolError(f"a reward needs a unique id and a name: {item!r}")
        if type(item.get("odds")) is not int or item["odds"] < 2 or item.get("kind") not in KINDS:
            raise PoolError(f"{item['id']}: odds must be a whole number of at least 2, kind one of {list(KINDS)}")
        seen.add(item["id"])
        rewards.append(Reward(item["id"], item["name"], item["odds"], item["kind"]))
    if not rewards:
        raise PoolError("a pool needs at least one reward")
    odds = {r.id: r.p for r in rewards}
    hours_list = []
    for item in data.get("treasure_hours", []):
        if not isinstance(item, dict) or not isinstance(item.get("multipliers"), dict):
            raise PoolError(f"a Treasure Hour needs a start, an end and multipliers: {item!r}")
        a, b = _when(item.get("start"), "Treasure Hour start"), _when(item.get("end"), "Treasure Hour end")
        boosts = item["multipliers"]
        if not a < b or any(rid not in odds or type(m) not in (int, float) or not 1 <= m or m * odds[rid] >= 1 for rid, m in boosts.items()):
            raise PoolError(f"a Treasure Hour needs start < end and a multiplier of at least 1 per known reward: {item!r}")
        hours_list.append((a, b, {rid: float(m) for rid, m in boosts.items()}))
    hours_list.sort(key=lambda h: h[0])
    if any(x[1] > y[0] for x, y in zip(hours_list, hours_list[1:])):
        raise PoolError("Treasure Hours must not overlap")
    return Pool(data["id"], int(data.get("revision", 1)), data["name"], start, end, bool(data.get("end_estimated")), rotations, tuple(rewards),
                tuple(data.get("about", [])), tuple(data.get("sources", [])), tuple(hours_list))


def load_pools(folder=POOLS_DIR):
    """Every installed pool, by start. A broken file is skipped and reported, never guessed at. -> ([Pool], [(file name, error)])."""
    pools, errors = [], []
    for path in sorted(Path(folder).glob("*.json")):
        try:
            pools.append(load_pool(path))
        except PoolError as error:
            errors.append((path.name, str(error)))
    return sorted(pools, key=lambda pool: pool.start), errors


def active_pool(pools, now):
    """The pool running now; otherwise the latest that has begun; otherwise the first. None without pools."""
    now = now.astimezone(UTC)
    running = [pool for pool in pools if pool.start <= now < pool.end]
    begun = [pool for pool in pools if pool.start <= now]
    if running:
        return running[-1]
    if begun:
        return begun[-1]
    return pools[0] if pools else None


def pool_at(pools, when):
    """(pool, period index) that `when` falls in, or (None, None): a date no installed pool covers is never guessed at."""
    when = when.astimezone(UTC)
    for pool in pools:
        if pool.start <= when < pool.end:
            return pool, pool.week_of(when)
    return None, None


def load_pool(path=DEFAULT_POOL):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PoolError(f"the reward pool could not be read ({type(error).__name__})") from None
    return parse_pool(data)


# ------------------------------------------------------------------ recorded chests
class ChestLog:
    """Recorded chests by time, from (at, delta) events as progression.Snapshot.events gives them."""

    def __init__(self, events):
        pairs = sorted((event.at.astimezone(UTC), event.delta) for event in events)
        self._times = [at for at, _ in pairs]
        self._sums = [0]
        for _, delta in pairs:
            self._sums.append(self._sums[-1] + delta)

    def count(self, start, end):
        """Recorded chests with start <= at < end; never below zero (a -1 for a chest from before the window)."""
        if end <= start:
            return 0
        return max(self._sums[bisect_left(self._times, end)] - self._sums[bisect_left(self._times, start)], 0)

    @property
    def first(self):
        return self._times[0] if self._times else None

    def _boosted(self, start, end, reward, treasure_hours):
        """[(chests, multiplier)] of the Treasure Hours inside start..end that boost this reward."""
        out = []
        for a, b, boosts in treasure_hours:
            m = boosts.get(reward.id, 1.0)
            if m > 1.0:
                n = self.count(max(start, a), min(end, b))
                if n:
                    out.append((n, m))
        return out

    def effective(self, start, end, reward, treasure_hours=()):
        """The chests of start..end as normal-odds chests for this reward: a boosted chest is worth more than one."""
        n = float(self.count(start, end))
        base = math.log1p(-reward.p)
        for boosted, m in self._boosted(start, end, reward, treasure_hours):
            n += boosted * (math.log1p(-reward.p * m) / base - 1.0)
        return n

    def expected(self, start, end, reward, treasure_hours=()):
        """Expected drops in start..end: the sum of each chest's own chance."""
        return self.count(start, end) * reward.p + sum(n * reward.p * (m - 1.0) for n, m in self._boosted(start, end, reward, treasure_hours))

    def boosted_count(self, start, end, reward, treasure_hours=()):
        return sum(n for n, _ in self._boosted(start, end, reward, treasure_hours))


# ------------------------------------------------------------------ your actions
@dataclass(frozen=True)
class Action:
    id: str
    kind: str
    at: datetime
    pool: str
    reward: str
    undoes: object = None
    source: str = MANUAL
    delta: int = 0                         # ADJUST: chests added (or taken back)
    scope: object = None                   # ADJUST: SEASON or WEEK
    week: object = None                    # ADJUST with WEEK: the 0-based reward week
    weeks: object = None                   # ALLOCATE: {period id or index: chests} of the chests you added
    period: object = None                  # ADJUST with WEEK: the period's stable id (RC4 on); `week` is kept for older rows


def read_actions(folder):
    """-> ([Action], lines that could not be read). A missing file is no actions. Reading never writes."""
    try:
        data = (Path(folder) / ACTIONS_FILE).read_bytes()
    except FileNotFoundError:
        return [], 0
    actions, seen, bad = [], set(), 0
    for line in data.split(b"\n"):
        if not line.strip():
            continue
        row = H._parse(line)
        try:
            if row is None or row["schema"] > H.SCHEMA or row["kind"] not in ACTION_KINDS:
                raise ValueError
            if row["id"] in seen:
                continue
            at = datetime.fromisoformat(row["at"])
            if at.tzinfo is None or not isinstance(row.get("pool"), str) or not isinstance(row.get("reward"), str):
                raise ValueError
            if row["kind"] == UNDO and not isinstance(row.get("undoes"), str):
                raise ValueError
            if row["kind"] == ADJUST and (type(row.get("delta")) is not int or row.get("scope") not in (SEASON, WEEK)
                                          or (row["scope"] == WEEK and not ((type(row.get("week")) is int and row["week"] >= 0)
                                                                           or isinstance(row.get("period"), str)))):
                raise ValueError
            allocation = None
            if row["kind"] == ALLOCATE:
                raw = row.get("weeks")
                if not isinstance(raw, dict) or any(not isinstance(k, str) or type(v) is not int or v < 0 for k, v in raw.items()):
                    raise ValueError
                allocation = dict(raw)
        except (KeyError, TypeError, ValueError):
            bad += 1
            continue
        seen.add(row["id"])
        actions.append(Action(row["id"], row["kind"], at.astimezone(UTC), row["pool"], row["reward"], row.get("undoes"), str(row.get("source", MANUAL)),
                              row.get("delta", 0), row.get("scope"), row.get("week"), allocation, row.get("period")))
    return actions, bad


def append_action(folder, kind, pool, reward, undoes=None, chests=None, at=None, delta=None, scope=None, week=None, weeks=None, period=None):
    """One row in the profile's predictions.jsonl, on disk before returning. -> its id."""
    in_week = type(week) is int or isinstance(period, str)
    if kind not in ACTION_KINDS or (kind == ADJUST and (type(delta) is not int or scope not in (SEASON, WEEK) or (scope == WEEK) != in_week)):
        raise ValueError(kind)
    if kind == ALLOCATE and (not isinstance(weeks, dict) or any(not ((type(w) is int and w >= 0) or isinstance(w, str)) or type(n) is not int or n < 0
                                                                for w, n in weeks.items())):
        raise ValueError(kind)
    row_id = f"prediction:{uuid.uuid4().hex}"
    row = {"kind": kind, "schema": H.SCHEMA, "id": row_id, "at": (at or datetime.now(UTC)).astimezone().isoformat(timespec="milliseconds"),
           "pool": pool, "reward": reward, "source": MANUAL}
    if undoes is not None:
        row["undoes"] = undoes
    if chests is not None:
        row["chests"] = chests                                # for reading the file by eye; the numbers are always recalculated
    if kind == ADJUST:
        row.update(delta=delta, scope=scope)
        if scope == WEEK:
            row.update({k: v for k, v in (("week", week), ("period", period)) if v is not None})
    if kind == ALLOCATE:
        row["weeks"] = {str(w): n for w, n in sorted(weeks.items()) if n}
    H._append_line(Path(folder) / ACTIONS_FILE, H._encode(row))
    return row_id


def effective(actions):
    """The actions that stand: every one not undone. An undo is final."""
    undone = {a.undoes for a in actions if a.kind == UNDO}
    return [a for a in actions if a.kind != UNDO and a.id not in undone]


@dataclass(frozen=True)
class Added:
    season: int                            # season rewards: every chest you added this season
    weeks: dict                            # {week: chests added for that reward week}
    unknown_week: int                      # added with the week unknown (counted for season rewards only)
    last: object                           # the latest standing ADJUST row, for Undo


def added(pool, actions, now):
    """Chests you added with Edit counts, from the standing ADJUST and ALLOCATE rows of this pool, folded in time order. No period ever goes
    below zero; an allocation only moves chests already added, to weeks that had begun when it was made."""
    rows = sorted((a for a in actions if a.kind in (ADJUST, ALLOCATE) and a.pool == pool.id and a.at <= now), key=lambda a: a.at)
    bounds = pool.weeks()
    unknown, weeks = 0, {}
    for a in rows:
        if a.kind == ADJUST and a.scope == SEASON:
            unknown = max(unknown + a.delta, 0)
        elif a.kind == ADJUST:
            w = pool.period_index(a.period) if a.period is not None else pool.period_index(a.week)
            if w is not None:
                weeks[w] = max(weeks.get(w, 0) + a.delta, 0)
        else:
            left, weeks = unknown + sum(weeks.values()), {}
            wanted = {}
            for key, n in a.weeks.items():
                w = pool.period_index(key)
                if w is not None and bounds[w][0] <= a.at:
                    wanted[w] = wanted.get(w, 0) + n
            for w in sorted(wanted):
                n = min(wanted[w], left)
                if n:
                    weeks[w], left = n, left - n
            unknown = left
    weeks = {w: n for w, n in weeks.items() if n > 0}
    return Added(unknown + sum(weeks.values()), weeks, unknown, rows[-1] if rows else None)


def reconcile(old_total, new_total, recorded, added_now, scope=SEASON, week=None):
    """How many chests an Edit counts from `old_total` to `new_total` APPROX adds to Predictions (negative: takes back). The counter already
    holds every chest counted and added so far, so only the difference counts, and:
      * Predictions never use more chests this season than the new total: recorded + added <= new_total. After a Reset, typing the old
        total back in adds nothing, and a counter that also holds earlier seasons is not limited by it;
      * a lower total takes back only from what you added for that period, never below zero: no negative chests."""
    delta = new_total - old_total
    if delta > 0:
        return max(0, min(delta, new_total - recorded - added_now.season))
    if delta < 0:
        have = added_now.unknown_week if scope == SEASON else added_now.weeks.get(week, 0)
        return -min(-delta, have)
    return 0


# ------------------------------------------------------------------ one reward's state
@dataclass(frozen=True)
class RewardState:
    reward: Reward
    window: tuple                          # (start, end) of the frame the cycle lives in: its week, or the pool
    week: object                           # 0-based week for a weekly reward, else None
    weeks: int
    started: bool                          # the pool has begun
    ended: bool                            # its week or the pool is over
    cycle_start: datetime
    cycle_chests: int                      # chests counted in the current cycle (a repeatable reward: in its current automatic cycle)
    cycle_effective: float                 # the same as normal-odds chests (more than cycle_chests when Treasure Hours boosted some)
    boosted: int                           # chests of the current cycle opened in a Treasure Hour that boosts this reward
    chance: float
    milestone_chests: int                  # normal-odds chests for CYCLE_MILESTONE
    remaining: object                      # {milestone: chests still needed at normal odds, 0 when reached}; None while obtained
    completed_cycles: int                  # repeatable only
    pool_chests: int                       # recorded chests in the pool so far
    added: int                             # chests you added that this reward counts (its week, or the season)
    expected: float
    obtained: object                       # the standing "Mark obtained" in this frame, or None
    obtained_chance: object                # the chance in its cycle when it was reported
    frozen: bool                           # obtained, and no new cycle since
    last_action: object                    # the latest standing action in this frame, for Undo
    team: int = 1                          # the scenario these figures are modeled for (1: your actual figures)
    actual_cycle_chests: int = 0           # your actual figures, whatever the scenario
    actual_cycle_effective: float = 0.0
    actual_chance: float = 0.0
    actual_completed: int = 0
    actual_expected: float = 0.0


def reward_state(pool, reward, log, actions, now, extra=None, team=1):
    now = now.astimezone(UTC)
    factor = team_factor(team)
    extra = extra or added(pool, actions, now)
    hours_ = pool.treasure_hours
    weeks = pool.weeks()
    if reward.kind == WEEKLY:
        week = pool.week_of(now)
        start, finish = weeks[week]
    else:
        week, (start, finish) = None, (pool.start, pool.end)
    end = min(now, finish)
    mine = sorted((a for a in actions if a.pool == pool.id and a.reward == reward.id and start <= a.at < finish and a.at <= now), key=lambda a: a.at)
    restarts = [a.at for a in mine if a.kind == RESTART]
    obtained = [a for a in mine if a.kind == OBTAINED and reward.kind != REPEATABLE]
    report = obtained[-1] if obtained else None
    cycle_start = max([start, *restarts])
    frozen = report is not None and report.at >= cycle_start
    stop = report.at if frozen else end
    mine_added = extra.weeks.get(week, 0) if reward.kind == WEEKLY else extra.season
    head = mine_added if cycle_start == start else 0        # added chests sit at the start of their period, at normal odds
    n, e = log.count(cycle_start, stop) + head, log.effective(cycle_start, stop, reward, hours_) + head
    boosted = log.boosted_count(cycle_start, stop, reward, hours_)
    milestone = chests_to(CYCLE_MILESTONE, reward.p)
    scale = 1.0 if frozen else factor                       # a reported reward is never modeled
    completed = actual_completed = 0
    if reward.kind == REPEATABLE:
        bounds = [start, *restarts, end]
        segments = [log.effective(a, b, reward, hours_) + (mine_added if a == start else 0) for a, b in zip(bounds, bounds[1:])]
        actual_completed = sum(int(seg // milestone) for seg in segments)
        completed = sum(int(seg * scale // milestone) for seg in segments)
        actual_e = (segments[-1] if segments else 0.0) % milestone
        e = (segments[-1] if segments else 0.0) * scale % milestone
        actual_n, n = int(actual_e), int(e)
    else:
        actual_e, actual_n = e, n
        e, n = e * scale, round(n * scale)
    report_chance = None
    if report is not None:
        began = max([start, *(t for t in restarts if t <= report.at)])
        report_chance = chance(log.effective(began, report.at, reward, hours_) + (mine_added if began == start else 0), reward.p)
    in_pool = (pool.start, min(now, pool.end))
    remaining = None if frozen else {m: more_to(m, reward.p, e) for m in MILESTONES}      # from the modeled position, in team chests
    actual_expected = log.expected(*in_pool, reward, hours_) + extra.season * reward.p
    return RewardState(reward, (start, finish), week, len(weeks), now >= pool.start, now >= finish, cycle_start, n, e, boosted, chance(e, reward.p),
                       milestone, remaining, completed, log.count(*in_pool), mine_added, actual_expected * factor, report, report_chance, frozen,
                       mine[-1] if mine else None, team, actual_n, actual_e, chance(actual_e, reward.p), actual_completed, actual_expected)


def progress(pool, log, actions, now, team=1):
    """Every reward's state, modeled for `team` (1: your actual figures). Cheap: the page calls it again when the team changes."""
    live = effective(actions)
    extra = added(pool, live, now.astimezone(UTC))
    return [reward_state(pool, reward, log, live, now, extra, team) for reward in pool.rewards]


# ------------------------------------------------------------------ what it means (fixed wording, never generated)
EARLY, TYPICAL, BEHIND, UNCOMMON, UNLUCKY, TERRIBLE, LUCKY, VERY_LUCKY, LATE, CYCLE = (
    "early", "typical", "behind", "uncommon", "unlucky", "terrible", "lucky", "very_lucky", "late", "cycle")


@dataclass(frozen=True)
class Insight:
    level: str                             # one of the levels above: the page colours it
    heading: str
    text: str


def insight(state):
    """How unusual this is, in fixed words. Without a report it is conditional ("if you are still waiting"): the app does not know what
    dropped, so it never calls anyone unlucky as a fact. After a report, how early or late it came."""
    if state.obtained is not None:
        q = state.obtained_chance
        if q < 0.05:
            return Insight(VERY_LUCKY, "Incredibly lucky!", f"Only {percent(q)} of players find it this early.")
        if q < 0.25:
            return Insight(LUCKY, "Lucky find!", f"Only {percent(q)} of players find it this early.")
        if q <= 0.75:
            return Insight(TYPICAL, "Typical luck", f"About {percent(q)} of players have found it by then.")
        return Insight(LATE, "A long hunt that paid off", f"{percent(1 - q)} of players would still have been waiting.")
    c = state.chance
    if state.reward.kind == REPEATABLE:
        return Insight(CYCLE, "This cycle", f"{percent(c)} of players would have found at least one by now.")
    waiting = 1 - c
    if c < 0.25:
        return Insight(EARLY, "Still early", f"{percent(waiting)} of players would still be waiting.")
    if c < 0.60:
        return Insight(TYPICAL, "Perfectly normal", f"About {percent(waiting)} of players would still be waiting.")
    if c < 0.80:
        return Insight(BEHIND, "Behind the average, but common", f"{percent(waiting)} of players would still be waiting.")
    if c < 0.90:
        return Insight(UNCOMMON, "Uncommon territory", f"Only {percent(waiting)} of players would still be waiting.")
    if c < 0.99:
        return Insight(UNLUCKY, "Unlucky streak, if you are still waiting",
                       f"About 1 in {round(1 / waiting)} players would be too. Long droughts happen even when every chest has the same chance.")
    return Insight(TERRIBLE, "Terrible luck, if you are still waiting", "Fewer than 1 in 100 players would be. Rare, but statistically possible.")


# ------------------------------------------------------------------ pace
def pace(snapshot):
    """(chests per hour of real life, the period it comes from) or (None, None): v0.4.0's rate, breaks and queues included."""
    for key, text in RATE_PERIODS:
        rate = snapshot.progress(key).per_hour
        if rate:
            return rate, text
    return None, None


# ------------------------------------------------------------------ What If?
@dataclass(frozen=True)
class Roll:
    chests: int                            # the team's chests until the first drop, that chest included
    finder: int                            # 0 = you, 1.. = a teammate
    team: int
    hours: object
    earlier: float                         # the share of first drops that come sooner than this one
    later: float                           # the share that come later


def roll(reward, team=1, rate=None, rng=None, multiplier=1.0):
    """One random first drop from now: a geometric draw (each chest independent, chance p x multiplier), not a number picked between 1 and
    the odds. A multiplier is a what-if: the whole hunt at those odds."""
    rng = rng or random.Random()
    p = min(reward.p * multiplier, 0.5)
    u = 1.0 - rng.random()                                  # (0, 1]
    n = max(1, math.ceil(math.log(u) / math.log1p(-p)))
    share = rng.random() * team_factor(team)                # whose chest it was: you 1, each teammate TEAMMATE_SHARE
    finder = 0 if share < 1.0 else min(1 + int((share - 1.0) / TEAMMATE_SHARE), team - 1)
    return Roll(n, finder, team, hours(n, rate, team), chance(n - 1, p), 1 - chance(n, p))


def roll_verdict(result):
    took = f"This time it took {result.chests:,} chests"
    if result.later >= 0.9:
        return Insight(VERY_LUCKY, "Incredibly lucky!", f"{took}: luckier than {percent(result.later)} of first drops.")
    if result.later >= 0.6:
        return Insight(LUCKY, "Lucky!", f"{took}: luckier than {percent(result.later)} of first drops.")
    if result.earlier >= 0.9:
        return Insight(TERRIBLE, "Terrible luck!", f"{took}. {percent(result.earlier)} of first drops happen sooner.")
    if result.earlier >= 0.6:
        return Insight(UNLUCKY, "Unlucky", f"{took}. {percent(result.earlier)} of first drops happen sooner.")
    return Insight(TYPICAL, "Pretty average luck", f"{took}. About {percent(result.earlier)} of first drops happen sooner.")


def finder_name(result):
    return "You" if result.finder == 0 else f"Teammate {result.finder}"


# ------------------------------------------------------------------ one read for the page
@dataclass(frozen=True)
class View:
    pool: Pool
    states: list
    rate: object
    rate_period: object
    season_chests: int                     # recorded chests in the pool so far
    added: object                          # Added: chests you added with Edit counts
    first_chest: object                    # the first recorded chest in the pool, or None
    week: int                              # the current reward week (0-based)
    week_chests: int                       # chests this week's rewards use: recorded this week + added for this week
    week_recorded: tuple                   # recorded chests in each reward week so far
    now: datetime
    bad_lines: int
    log: object = None                     # the recorded chests and every action read, so a team scenario needs no new read
    actions: tuple = ()


def load_view(folder, pool, now=None, counting_now=False):
    """Everything the page shows for one profile, from one read of its history. Slow on a huge history: the app calls it off its window."""
    from fortnite_chest_counter import progression as P
    now = (now or datetime.now(UTC)).astimezone(UTC)
    snapshot = P.load(folder, now=now, counting_now=counting_now)
    log = ChestLog(snapshot.events)
    actions, bad = read_actions(folder)
    rate, period = pace(snapshot)
    inside = [e.at for e in snapshot.events if pool.start <= e.at < min(now, pool.end)]
    extra = added(pool, effective(actions), now)
    week = pool.week_of(now)
    week_start, week_end = pool.weeks()[week]
    per_week = tuple(log.count(a, min(now, b)) for a, b in pool.weeks())
    return View(pool, progress(pool, log, actions, now), rate, period, log.count(pool.start, min(now, pool.end)), extra,
                min(inside) if inside else None, week, log.count(week_start, min(now, week_end)) + extra.weeks.get(week, 0), per_week, now, bad,
                log, tuple(actions))


def edit_summary(folder, pools, now=None):
    """What the Edit counts dialog needs for every installed pool, from one read: {pool id: {"recorded", "added", "week"}}. "week" is the
    period running now, or None when the pool is not running."""
    from fortnite_chest_counter import progression as P
    now = (now or datetime.now(UTC)).astimezone(UTC)
    log = ChestLog(P.load(folder, now=now).events)
    live = effective(read_actions(folder)[0])
    return {pool.id: {"recorded": log.count(pool.start, min(now, pool.end)), "added": added(pool, live, now),
                      "week": pool.week_of(now) if pool.start <= now < pool.end else None} for pool in pools}
