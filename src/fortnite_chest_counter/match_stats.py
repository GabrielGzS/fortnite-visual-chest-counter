"""Compose personal and team match totals without counting the same session twice."""

from dataclasses import dataclass
import math


RATE = 137_500


@dataclass(frozen=True)
class Summary:
    certain: int = 0
    total: int = 0
    log_no_drop: float = 0.0
    players: tuple[str, ...] = ()
    matches: int = 0

    @property
    def chance(self):
        return f"{-math.expm1(self.log_no_drop) * 100 if self.log_no_drop else 0:.6f}%"

    def __add__(self, other):
        return Summary(self.certain + other.certain, self.total + other.total,
                       self.log_no_drop + other.log_no_drop, matches=self.matches + other.matches)


def personal(certain, total, boost):
    return Summary(certain, total, total * math.log1p(-boost / RATE), matches=1)


def team(session, player, *, current=None):
    if session is None:
        return None
    members = {member.name.casefold(): member for member in session.players}
    own = player.casefold()
    if not own or (own not in members and current is None):
        return None
    names = {key: member.name for key, member in members.items()}
    if current is not None:
        names[own] = player
    if len(names) < 2:
        return None
    result = Summary()
    for key, member in members.items():
        if key != own or current is None:
            result += personal(member.certain, member.total, member.boost)
    if current is not None:
        result += personal(*current)
    return Summary(result.certain, result.total, result.log_no_drop, tuple(names.values()), 1)


def saved_team(match, sessions, webhook_id):
    if not match.session_fingerprint or not match.group_webhook_id or match.group_webhook_id != webhook_id:
        return None
    return team(sessions.get(match.session_fingerprint), match.player,
                current=(match.certain, match.total, match.boost))


def cumulative(matches, sessions, webhook_id, *, snapshot="", certain=0, total=0, boost=1.0,
               fingerprint="", player="", sharing=False, active=False):
    result = Summary()
    seen = set()
    snapshots = set()
    for match in matches:
        snapshots.add(match.snapshot)
        linked = saved_team(match, sessions, webhook_id)
        key = (match.group_webhook_id, match.session_fingerprint)
        if linked is not None:
            if key not in seen:
                result += linked
                seen.add(key)
        else:
            result += personal(match.certain, match.total, match.boost)
    if snapshot and snapshot not in snapshots and (total > 0 or active):
        linked = team(sessions.get(fingerprint), player, current=(certain, total, boost)) if sharing and fingerprint else None
        key = (webhook_id, fingerprint)
        if linked is not None:
            if key not in seen:
                result += linked
        else:
            result += personal(certain, total, boost)
    return result
