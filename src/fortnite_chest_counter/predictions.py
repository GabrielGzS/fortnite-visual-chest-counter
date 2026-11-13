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
RESTART, OBTAINED, UNDO = "prediction_restart", "prediction_obtained", "prediction_undo"
ACTION_KINDS = (RESTART, OBTAINED, UNDO)
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


def hours(chests, rate, team=1):
    """Hours of real life for `chests` at `rate` chests per hour per player, with `team` players opening chests. None without a rate."""
    return None if not rate or rate <= 0 else chests / (rate * team)


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
        except (KeyError, TypeError, ValueError):
            bad += 1
            continue
        seen.add(row["id"])
        actions.append(Action(row["id"], row["kind"], at.astimezone(UTC), row["pool"], row["reward"], row.get("undoes"), str(row.get("source", MANUAL))))
    return actions, bad


def append_action(folder, kind, pool, reward, undoes=None, chests=None, at=None):
    """One row in the profile's predictions.jsonl, on disk before returning. -> its id."""
    if kind not in ACTION_KINDS:
        raise ValueError(kind)
    row_id = f"prediction:{uuid.uuid4().hex}"
    row = {"kind": kind, "schema": H.SCHEMA, "id": row_id, "at": (at or datetime.now(UTC)).astimezone().isoformat(timespec="milliseconds"),
           "pool": pool, "reward": reward, "source": MANUAL}
    if undoes is not None:
        row["undoes"] = undoes
    if chests is not None:
        row["chests"] = chests                                # for reading the file by eye; the numbers are always recalculated
    H._append_line(Path(folder) / ACTIONS_FILE, H._encode(row))
    return row_id


def effective(actions):
    """The actions that stand: every one not undone. An undo is final."""
    undone = {a.undoes for a in actions if a.kind == UNDO}
    return [a for a in actions if a.kind != UNDO and a.id not in undone]


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
    pool_chests: int
    expected: float
    obtained: object                       # the standing "Mark obtained" in this frame, or None
    obtained_chance: object                # the chance in its cycle when it was reported
    frozen: bool                           # obtained, and no new cycle since
    last_action: object                    # the latest standing action in this frame, for Undo


def reward_state(pool, reward, log, actions, now):
    now = now.astimezone(UTC)
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
    n, e = log.count(cycle_start, stop), log.effective(cycle_start, stop, reward, hours_)
    boosted = log.boosted_count(cycle_start, stop, reward, hours_)
    milestone = chests_to(CYCLE_MILESTONE, reward.p)
    completed = 0
    if reward.kind == REPEATABLE:
        bounds = [start, *restarts, end]
        completed = sum(int(log.effective(a, b, reward, hours_) // milestone) for a, b in zip(bounds, bounds[1:]))
        e %= milestone
        n = int(e)
    report_chance = None
    if report is not None:
        began = max([start, *(t for t in restarts if t <= report.at)])
        report_chance = chance(log.effective(began, report.at, reward, hours_), reward.p)
    in_pool = (pool.start, min(now, pool.end))
    remaining = None if frozen else {m: more_to(m, reward.p, e) for m in MILESTONES}
    return RewardState(reward, (start, finish), week, len(weeks), now >= pool.start, now >= finish, cycle_start, n, e, boosted, chance(e, reward.p),
                       milestone, remaining, completed, log.count(*in_pool), log.expected(*in_pool, reward, hours_), report, report_chance, frozen,
                       mine[-1] if mine else None)


def progress(pool, log, actions, now):
    live = effective(actions)
    return [reward_state(pool, reward, log, live, now) for reward in pool.rewards]


# ------------------------------------------------------------------ what it means (fixed wording, never generated)
def insight(state):
    """One sentence on how unusual this is. Without a report it is conditional: the app does not know what dropped."""
    if state.obtained is not None:
        q = state.obtained_chance
        if q < 0.25:
            return f"Lucky find: only {percent(q)} of players find it this early."
        if q <= 0.75:
            return f"Right around the typical point: about {percent(q)} of players have found it by then."
        return f"A long hunt that paid off: {percent(1 - q)} of players would still have been waiting."
    c = state.chance
    if state.reward.kind == REPEATABLE:
        return f"In this cycle, {percent(c)} of players would have found at least one by now."
    waiting = 1 - c
    if c < 0.25:
        return f"Still early: {percent(waiting)} of players would still be waiting."
    if c < 0.60:
        return f"Perfectly normal: {percent(waiting)} of players would still be waiting."
    if c < 0.80:
        return f"Behind the average, but common: {percent(waiting)} of players would still be waiting."
    if c < 0.90:
        return f"Uncommon territory: only {percent(waiting)} of players would still be waiting."
    if c < 0.99:
        return (f"Unlucky, if you are still waiting: about 1 in {round(1 / waiting)} players would be too. Long droughts happen even when "
                "every chest has the same chance.")
    return "Terrible luck, if you are still waiting: fewer than 1 in 100 players would be. Rare, but statistically possible."


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
    return Roll(n, rng.randrange(team), team, hours(n, rate, team), chance(n - 1, p), 1 - chance(n, p))


def roll_verdict(result):
    if result.earlier < 0.5:
        return f"Luckier than {percent(result.later)} of first drops."
    return f"Unluckier than {percent(result.earlier)} of first drops."


def finder_name(result):
    return "You" if result.finder == 0 else f"Teammate {result.finder}"


# ------------------------------------------------------------------ one read for the page
@dataclass(frozen=True)
class View:
    pool: Pool
    states: list
    rate: object
    rate_period: object
    season_chests: int
    first_chest: object                    # the first recorded chest in the pool, or None
    now: datetime
    bad_lines: int


def load_view(folder, pool, now=None, counting_now=False):
    """Everything the page shows for one profile, from one read of its history. Slow on a huge history: the app calls it off its window."""
    from fortnite_chest_counter import progression as P
    now = (now or datetime.now(UTC)).astimezone(UTC)
    snapshot = P.load(folder, now=now, counting_now=counting_now)
    log = ChestLog(snapshot.events)
    actions, bad = read_actions(folder)
    rate, period = pace(snapshot)
    inside = [e.at for e in snapshot.events if pool.start <= e.at < min(now, pool.end)]
    return View(pool, progress(pool, log, actions, now), rate, period, log.count(pool.start, min(now, pool.end)), min(inside) if inside else None, now, bad)
