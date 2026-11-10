"""Durable shared Group contributions sent through a single Discord webhook."""

from collections import Counter
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import sqlite3
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener
from uuid import uuid4

from fortnite_chest_counter import paths
from fortnite_chest_counter.detection.chest_types import LABELS
from fortnite_chest_counter.discord_summary import _NoRedirects
from fortnite_chest_counter.obs import credentials


_TARGET = "Fortnite Visual Chest Counter/Group Webhook"
_WEBHOOK = re.compile(r"https://discord\.com/api/(?:v10/)?webhooks/([1-9][0-9]{14,21})/([\w.-]{16,300})", re.ASCII)
_EVENT_ID = re.compile(r"[a-f0-9]{32}")
_PREFIX = "||FCC1 "
_FLUSH_LOCK = threading.Lock()
GROUP_TYPE_LABELS = {**LABELS, "unclassified": "Not classified"}
_SCHEMA = """
CREATE TABLE IF NOT EXISTS contributions (
    webhook TEXT NOT NULL, event TEXT NOT NULL, player TEXT NOT NULL, name TEXT NOT NULL, count INTEGER NOT NULL,
    PRIMARY KEY(webhook, event)
);
CREATE TABLE IF NOT EXISTS corrections (
    webhook TEXT NOT NULL, player TEXT NOT NULL, amount INTEGER NOT NULL, reset_row INTEGER NOT NULL,
    PRIMARY KEY(webhook, player)
);
CREATE TABLE IF NOT EXISTS cursors (
    webhook TEXT NOT NULL, channel TEXT NOT NULL, message TEXT NOT NULL, PRIMARY KEY(webhook, channel)
);
CREATE TABLE IF NOT EXISTS outbox (
    webhook TEXT NOT NULL, snapshot TEXT NOT NULL, event TEXT NOT NULL, name TEXT NOT NULL,
    count INTEGER NOT NULL, sent INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(webhook, snapshot)
);
CREATE TABLE IF NOT EXISTS event_details (
    webhook TEXT NOT NULL, event TEXT NOT NULL, certain INTEGER, chest_types TEXT NOT NULL,
    PRIMARY KEY(webhook, event)
);
"""


@dataclass(frozen=True)
class Webhook:
    id: str
    token: str = field(repr=False)

    @property
    def url(self):
        return f"https://discord.com/api/v10/webhooks/{self.id}/{self.token}"


def _parse_webhook(url):
    match = _WEBHOOK.fullmatch(url.strip())
    if not match:
        raise ValueError("Paste a valid Discord webhook URL.")
    return Webhook(*match.groups())


def load_webhook():
    url = credentials.load_password(_TARGET)
    return _parse_webhook(url) if url else None


def save_webhook(url):
    webhook = _parse_webhook(url)
    credentials.save_password(webhook.url, _TARGET, description="Shared Discord Group webhook")
    return webhook


def forget_webhook():
    credentials.forget_password(_TARGET)


def validate_player(player):
    player = " ".join(player.split())
    if not player or len(player) > 80 or not all(char.isprintable() for char in player):
        raise ValueError("Enter a Group player name of 1 to 80 characters.")
    return player


@dataclass(frozen=True)
class Player:
    name: str
    total: int
    certain: int | None = None
    chest_types: dict[str, int] = field(default_factory=dict)
    recorded: int = 0
    adjustment: int = 0
    confirmed_total: int = 0
    matches: int = 0


def _combine(name, players, adjustment=0):
    kinds = Counter()
    recorded = confirmed_total = certain = matches = 0
    has_details = False
    for player in players:
        recorded += player.recorded
        confirmed_total += player.confirmed_total
        certain += player.certain or 0
        has_details |= player.certain is not None
        matches += player.matches
        kinds.update(player.chest_types)
        adjustment += player.adjustment
    return Player(name, recorded + adjustment, certain if has_details else None, dict(kinds),
                  recorded, adjustment, confirmed_total, matches)


class GroupStore:
    def __init__(self, webhook_id, path=None):
        self.webhook_id = webhook_id
        self.path = Path(path) if path is not None else paths.APP_DIR / "state" / "discord-group.sqlite3"

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript(_SCHEMA)
            with db:
                yield db

    def _players(self, db):
        rows = db.execute("""
            SELECT m.player, m.name, m.count, d.certain, d.chest_types,
                   COALESCE(c.amount, 0), m.rowid > COALESCE(c.reset_row, 0)
            FROM contributions AS m
            LEFT JOIN corrections AS c ON c.webhook = m.webhook AND c.player = m.player
            LEFT JOIN event_details AS d ON d.webhook = m.webhook AND d.event = m.event
            WHERE m.webhook = ?
            ORDER BY m.rowid
        """, (self.webhook_id,))
        groups = {}
        identities = {}
        for key, name, count, certain, chest_types, amount, included in rows:
            identities[key] = name, amount
            if included:
                groups.setdefault(key, []).append(Player(name, count, certain, json.loads(chest_types or "{}"),
                                                          count, confirmed_total=count if certain is not None else 0,
                                                          matches=1))
        return {key: _combine(name, groups.get(key, ()), amount) for key, (name, amount) in identities.items()}

    def leaderboard(self):
        with self.connection() as db:
            return sorted(self._players(db).values(), key=lambda player: (-player.total, player.name.casefold()))

    def count(self, name):
        player = self.stats(name)
        return player.name, player.total

    def stats(self, name=None):
        with self.connection() as db:
            if name is None:
                return _combine("Everyone", self._players(db).values())
            return self._player(db, name)

    def _player(self, db, name):
        player = self._players(db).get(name.strip().casefold())
        if player is None:
            raise ValueError("Player not found in shared Group matches.")
        return player

    def adjust(self, name, amount):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            player = self._player(db, name)
            key = player.name.casefold()
            if amount is None:
                reset_row, = db.execute(
                    "SELECT MAX(rowid) FROM contributions WHERE webhook=? AND player=?", (self.webhook_id, key)
                ).fetchone()
                db.execute("INSERT OR REPLACE INTO corrections VALUES (?, ?, 0, ?)", (self.webhook_id, key, reset_row))
                return player.name, 0
            if player.total + amount < 0:
                raise ValueError("A player's total cannot be negative.")
            db.execute("""
                INSERT INTO corrections VALUES (?, ?, ?, 0)
                ON CONFLICT(webhook, player) DO UPDATE SET amount = amount + excluded.amount
            """, (self.webhook_id, key, amount))
            return player.name, player.total + amount

    def cursor(self, channel):
        with self.connection() as db:
            row = db.execute("SELECT message FROM cursors WHERE webhook=? AND channel=?",
                             (self.webhook_id, str(channel))).fetchone()
            return int(row[0]) if row else 0

    def advance_cursor(self, channel, message):
        with self.connection() as db:
            db.execute("""INSERT INTO cursors VALUES (?, ?, ?)
                          ON CONFLICT(webhook, channel) DO UPDATE SET message = excluded.message
                          WHERE length(excluded.message) > length(cursors.message)
                             OR (length(excluded.message) = length(cursors.message)
                                 AND excluded.message > cursors.message)""",
                       (self.webhook_id, str(channel), str(message)))

    def ingest(self, message):
        if str(message.webhook_id) != self.webhook_id:
            return False
        contribution = _parse_event(message.content)
        channel = str(message.channel.id)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute("SELECT message FROM cursors WHERE webhook=? AND channel=?",
                                (self.webhook_id, channel)).fetchone()
            if cursor and int(cursor[0]) >= message.id:
                return False
            inserted = False
            if contribution:
                event, name, count, certain, chest_types = contribution
                result = db.execute("INSERT OR IGNORE INTO contributions VALUES (?, ?, ?, ?, ?)",
                                    (self.webhook_id, event, name.casefold(), name, count))
                inserted = bool(result.rowcount)
                if inserted:
                    db.execute("INSERT OR REPLACE INTO event_details VALUES (?, ?, ?, ?)",
                               (self.webhook_id, event, certain, json.dumps(chest_types)))
            db.execute("INSERT OR REPLACE INTO cursors VALUES (?, ?, ?)",
                       (self.webhook_id, channel, str(message.id)))
            return inserted

    def queue(self, match, player):
        if not 0 <= match.total <= 1_000_000_000:
            raise ValueError("A Group contribution must contain 0 to 1,000,000,000 chests.")
        event = uuid4().hex
        certain, chest_types = _validate_breakdown(match.total, getattr(match, "certain", None),
                                                  getattr(match, "chest_types", {}))
        with self.connection() as db:
            result = db.execute("INSERT OR IGNORE INTO outbox VALUES (?, ?, ?, ?, ?, 0)",
                                (self.webhook_id, match.snapshot, event, validate_player(player), match.total))
            if result.rowcount:
                db.execute("INSERT INTO event_details VALUES (?, ?, ?, ?)",
                           (self.webhook_id, event, certain, json.dumps(chest_types)))
            return bool(result.rowcount)

    def flush(self, webhook):
        with _FLUSH_LOCK, self.connection() as db:
            rows = db.execute("""
                SELECT o.event, o.name, o.count, d.certain, d.chest_types
                FROM outbox AS o LEFT JOIN event_details AS d ON d.webhook = o.webhook AND d.event = o.event
                WHERE o.webhook=? AND o.sent=0 ORDER BY o.rowid
            """, (self.webhook_id,)).fetchall()
            for event, name, count, certain, chest_types in rows:
                _publish(webhook, event, name, count, certain, json.loads(chest_types or "{}"))
                db.execute("UPDATE outbox SET sent=1 WHERE webhook=? AND event=?", (self.webhook_id, event))
                db.commit()
            return len(rows)


def _parse_event(content):
    if not content.startswith(_PREFIX) or not content.endswith("||"):
        return None
    try:
        fields = json.loads(content[len(_PREFIX):-2])
        if not isinstance(fields, list) or len(fields) not in (3, 5):
            return None
        event, name, count = fields[:3]
        if (not isinstance(event, str) or not _EVENT_ID.fullmatch(event)
                or type(count) is not int or not 0 <= count <= 1_000_000_000
                or not isinstance(name, str) or validate_player(name) != name):
            return None
        certain, chest_types = _validate_breakdown(count, *(fields[3:] or [None, {}]))
        return event, name, count, certain, chest_types
    except (TypeError, ValueError):
        return None


def _validate_breakdown(count, certain, chest_types):
    if certain is not None and (type(certain) is not int or not 0 <= certain <= count):
        raise ValueError("The certain count must be between zero and the Group contribution total.")
    if (not isinstance(chest_types, dict)
            or any(key not in GROUP_TYPE_LABELS or type(value) is not int or value < 0
                   for key, value in chest_types.items())
            or sum(chest_types.values()) > count):
        raise ValueError("The chest types must be recognized and fit the Group contribution total.")
    return certain, chest_types


def _publish(webhook, event, name, count, certain, chest_types):
    payload = json.dumps([event, name, count, certain, chest_types], ensure_ascii=True,
                         separators=(",", ":")).replace("|", "\\u007c")
    body = json.dumps({
        "content": f"{_PREFIX}{payload}||",
        "embeds": [{"title": "Group chest contribution", "author": {"name": name},
                    "description": f"{count:,} chests", "color": 0x5865F2}],
        "allowed_mentions": {"parse": []},
    }).encode("utf-8")
    request = Request(f"{webhook.url}?wait=true", data=body,
                      headers={"Content-Type": "application/json", "User-Agent": "FortniteVisualChestCounter"})
    try:
        with build_opener(_NoRedirects()).open(request, timeout=12):
            pass
    except HTTPError as error:
        if error.code == 429:
            raise ValueError("Discord is rate limiting Group contributions. The pending reports will retry later.") from None
        raise ValueError(f"Discord rejected the Group webhook request (HTTP {error.code}).") from None
    except (OSError, URLError):
        raise ValueError("Discord did not confirm the Group contribution. It remains pending.") from None


def queue_match(webhook, match, player):
    return GroupStore(webhook.id).queue(match, player)


def flush(webhook):
    store = GroupStore(webhook.id)
    return store.flush(webhook) if store.path.is_file() else 0
