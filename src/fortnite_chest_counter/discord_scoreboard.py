"""Publish and read the shared Discord leaderboard message."""

from dataclasses import asdict, dataclass, field
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener
from urllib.parse import urlsplit
from uuid import uuid4

from fortnite_chest_counter import discord_group
from fortnite_chest_counter.discord_summary import _NoRedirects, valid_id


_MARKER = "Fortnite Visual Chest Counter | Shared leaderboard v1"
_LINK = re.compile(r"https://discord\.com/channels/\d+/\d+/([1-9][0-9]{14,21})/?")
_TEAM_TEXT = re.compile(
    r"Team matches: ([0-9,]+)"
    r"(?:\nLatest received team match: ([0-9,]+) chests · ([0-9,]+) submitted players"
    r"\nEstimated Pirate Token chance from submitted chests: "
    r"(?:(\d{1,3}\.\d{6}%)(?: \(about 1 in ([0-9,]+)\))?|about 1 in ([0-9,]+)|zero))?"
)
MODES = ("Solo", "Duo", "Trio", "Squad")
BOOSTS = (1.0, 1.5, 2.0)
_GROUP_SETTINGS = re.compile(r"Group settings: (Solo|Duo|Trio|Squad) · ×(1|1\.5|2)")
_DATA_TITLE = "Group sync data"
_SESSION_ATTACHMENT = "fcc-sessions.json"
_MAX_SESSION_BYTES = 4 * 1024 * 1024
_MAX_RANKS = 10
_TYPE_KEYS = {label: key for key, label in discord_group.GROUP_TYPE_LABELS.items()}


class BoardNotFound(ValueError):
    pass


@dataclass(frozen=True)
class Row:
    name: str
    total: int
    matches: int | None = None
    certain: int | None = None
    estimated: int | None = None
    chest_types: dict[str, int] = field(default_factory=dict)


def message_id(value):
    value = value.strip()
    link = _LINK.fullmatch(value)
    if link:
        return link[1]
    if value and not valid_id(value):
        raise ValueError("Enter a Discord message link or message ID.")
    return value


def rows(players):
    return tuple(Row(p.name, p.total, p.matches, p.certain,
                     p.confirmed_total - p.certain if p.certain is not None else None, p.chest_types)
                 for p in players[:_MAX_RANKS])


def _field(index, row):
    lines = [f"Total: {row.total:,}"]
    if row.matches is not None:
        lines.append(f"Matches: {row.matches:,}")
    if row.certain is not None:
        lines.append(f"Certain: {row.certain:,}")
    if row.estimated is not None:
        lines.append(f"Estimated: {row.estimated:,}")
    lines.extend(f"{discord_group.GROUP_TYPE_LABELS[kind]}: {count:,}"
                 for kind, count in row.chest_types.items() if kind in discord_group.GROUP_TYPE_LABELS and count)
    return {"name": f"{index}. {row.name}", "value": "\n".join(lines), "inline": False}


def _request(webhook, suffix, method, payload=None, *, attachment=None):
    discord_group.check_webhook_cooldown(webhook)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    content_type = "application/json"
    if attachment is not None:
        boundary = "fcc-" + uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
                "Content-Type: application/json\r\n\r\n").encode("ascii") + body + b"\r\n"
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; "
                 f"filename=\"{_SESSION_ATTACHMENT}\"\r\nContent-Type: application/json\r\n\r\n").encode("ascii")
        body += attachment + f"\r\n--{boundary}--\r\n".encode("ascii")
        content_type = f"multipart/form-data; boundary={boundary}"
    request = Request(webhook.url + suffix, data=body, method=method,
                      headers={"Content-Type": content_type, "User-Agent": "FortniteVisualChestCounter"})
    try:
        with build_opener(_NoRedirects()).open(request, timeout=8) as response:
            discord_group.webhook_response(webhook, response)
            if response.status == 204:
                return None
            return json.load(response)
    except HTTPError as error:
        if error.code == 429:
            raise discord_group.webhook_rate_limited(webhook, error) from None
        if error.code == 404:
            raise BoardNotFound("Discord could not find this leaderboard message for the saved webhook.") from None
        raise ValueError(f"Discord returned HTTP {error.code} for the shared leaderboard.") from None
    except (OSError, URLError, ValueError):
        raise ValueError("Discord did not return a shared leaderboard response.") from None


def _decode_team(description):
    lines = description.split("\n\n", 1)
    if len(lines) == 1:
        return None
    match = _TEAM_TEXT.fullmatch(lines[1])
    if match is None:
        raise ValueError
    matches_text, chests_text, players_text, chance, current_odds, legacy_odds = match.groups()
    matches, chests, players, one_in = (int(n.replace(",", "")) if n else None
                                        for n in (matches_text, chests_text, players_text, current_odds or legacy_odds))
    if (not matches and any(n is not None for n in (chests, players, one_in))
            or matches and (not players or chests is None or bool(chests) != bool(one_in))
            or chance is not None and (float(chance[:-1]) > 100 or bool(float(chance[:-1])) != bool(chests))):
        raise ValueError
    return discord_group.TeamSummary(matches, players or 0, chests or 0, one_in, chance)


def _decode(webhook, message, *, with_team=False, with_settings=False):
    try:
        embed, = message["embeds"]
        if message["webhook_id"] != webhook.id or embed["footer"]["text"] != _MARKER:
            raise ValueError
        fields = embed.get("fields", [])
        if not isinstance(fields, list) or len(fields) > _MAX_RANKS:
            raise ValueError
        result = []
        for index, item in enumerate(fields, 1):
            prefix = f"{index}. "
            if not item["name"].startswith(prefix):
                raise ValueError
            name = discord_group.validate_player(item["name"][len(prefix):])
            parts = dict(line.split(": ", 1) for line in item["value"].splitlines())
            counts = {key: int(value.replace(",", "")) for key, value in parts.items()}
            if any(n < 0 for n in counts.values()):
                raise ValueError
            total, matches = counts.pop("Total"), counts.pop("Matches", None)
            certain, estimated = counts.pop("Certain", None), counts.pop("Estimated", None)
            types = {_TYPE_KEYS[label]: count for label, count in counts.items()}
            result.append(Row(name, total, matches, certain, estimated, types))
        ranking = tuple(result)
        if with_team or with_settings:
            description = embed.get("description", "")
            team = _decode_team(description)
            if with_settings:
                heading = description.split("\n\n", 1)[0]
                match = _GROUP_SETTINGS.fullmatch(heading.rsplit("\n", 1)[-1])
                settings = (match[1], float(match[2])) if match else None
                return ranking, team, settings
            return ranking, team
        return ranking
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ValueError("This message is not a valid leaderboard for the saved webhook.") from None


def _encode_sessions(sessions):
    sessions = discord_group.validate_sessions(sessions)
    raw = json.dumps({"format": 1, "sessions": [asdict(session) for session in sessions]},
                     ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > _MAX_SESSION_BYTES:
        raise ValueError("Shared session history exceeds the supported 4 MB snapshot size.")
    return raw


def _session_rows(values):
    if not isinstance(values, list):
        raise ValueError("Invalid shared sessions.")
    sessions = tuple(discord_group.TeamSession(
        row["fingerprint"], tuple(discord_group.SessionPlayer(**player) for player in row["players"]))
        for row in values)
    return discord_group.validate_sessions(sessions)


def _read_snapshot(raw):
    if len(raw) > _MAX_SESSION_BYTES:
        raise ValueError("Shared session history exceeds the supported snapshot size.")
    try:
        document = json.loads(raw)
        if not isinstance(document, dict) or type(document["format"]) is not int or document["format"] not in (1, 2):
            raise ValueError
        return document
    except (KeyError, TypeError, ValueError, RecursionError):
        raise ValueError("Discord did not return valid shared session history.") from None


def _validate_count(value, *, optional=False):
    if optional and value is None:
        return
    if type(value) is not int or not 0 <= value <= 9_000_000_000_000_000:
        raise ValueError("Invalid shared count.")


def _snapshot_ranking(values):
    if not isinstance(values, list) or len(values) > _MAX_RANKS:
        raise ValueError("Invalid shared ranking.")
    result = []
    names = set()
    for value in values:
        if not isinstance(value, dict) or set(value) != set(Row.__dataclass_fields__):
            raise ValueError("Invalid shared player fields.")
        row = Row(**value)
        if not isinstance(row.name, str) or discord_group.validate_player(row.name) != row.name or row.name.casefold() in names:
            raise ValueError("Invalid shared player name.")
        names.add(row.name.casefold())
        _validate_count(row.total)
        for count in (row.matches, row.certain, row.estimated):
            _validate_count(count, optional=True)
        if not isinstance(row.chest_types, dict) or any(key not in _TYPE_KEYS.values() for key in row.chest_types):
            raise ValueError("Invalid shared chest types.")
        for count in row.chest_types.values():
            _validate_count(count)
        result.append(row)
    return tuple(result)


def _snapshot_team(values):
    if values is None:
        return None
    if not isinstance(values, dict) or set(values) != set(discord_group.TeamSummary.__dataclass_fields__):
        raise ValueError("Invalid team summary.")
    team = discord_group.TeamSummary(**values)
    for count in (team.matches, team.players, team.chests):
        _validate_count(count)
    _validate_count(team.one_in, optional=True)
    if team.one_in == 0:
        raise ValueError("Invalid team odds.")
    if team.chance_percent is not None and (
            not isinstance(team.chance_percent, str) or not re.fullmatch(r"\d{1,3}\.\d{6}%", team.chance_percent)
            or float(team.chance_percent[:-1]) > 100):
        raise ValueError("Invalid team probability.")
    if not team.matches and (team.players or team.chests or team.one_in is not None or
                             team.chance_percent not in (None, "0.000000%")):
        raise ValueError("Invalid empty team summary.")
    # Reuse the public summary's consistency checks for populated summaries.
    return _decode_team("Snapshot\n\n" + team.text()) if team.matches else team


def _snapshot_settings(values):
    if values is None:
        return None
    if (not isinstance(values, (list, tuple)) or len(values) != 2 or values[0] not in MODES
            or type(values[1]) not in (int, float) or values[1] not in BOOSTS):
        raise ValueError("Invalid group match settings.")
    return tuple(values)


def _decode_data_snapshot(raw):
    try:
        document = _read_snapshot(raw)
        if document["format"] != 2 or set(document) != {"format", "ranking", "team", "settings", "sessions"}:
            raise ValueError
        return (_snapshot_ranking(document["ranking"]), _snapshot_team(document["team"]),
                _snapshot_settings(document["settings"]), _session_rows(document["sessions"]))
    except (KeyError, AttributeError, TypeError, ValueError, RecursionError):
        raise ValueError("Discord did not return valid Group sync data.") from None


def _encode_data_snapshot(ranking, team, settings, sessions):
    raw = json.dumps({"format": 2, "ranking": [asdict(row) for row in ranking],
                      "team": asdict(team) if team is not None else None, "settings": settings,
                      "sessions": [asdict(session) for session in discord_group.validate_sessions(sessions)]},
                     ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    _decode_data_snapshot(raw)
    return raw


def _decode_sessions(raw):
    document = _read_snapshot(raw)
    if document["format"] == 2:
        return _decode_data_snapshot(raw)[3]
    try:
        return _session_rows(document["sessions"])
    except (KeyError, AttributeError, TypeError, ValueError, RecursionError):
        raise ValueError("Discord did not return valid shared session history.") from None


def _fetch_attachment(message):
    attachments = message.get("attachments", ())
    if not isinstance(attachments, (tuple, list)) or any(not isinstance(item, dict) for item in attachments):
        raise ValueError("Discord did not return valid leaderboard attachments.")
    attachments = [item for item in attachments if item.get("filename") == _SESSION_ATTACHMENT]
    if not attachments:
        return None
    if len(attachments) != 1:
        raise ValueError("The leaderboard contains multiple session snapshots.")
    attachment, = attachments
    try:
        location = urlsplit(attachment["url"])
        size = attachment["size"]
        if (location.scheme != "https" or location.hostname != "cdn.discordapp.com"
                or location.port not in (None, 443) or location.username is not None or location.password is not None
                or not location.path.startswith("/attachments/") or not location.path.endswith("/" + _SESSION_ATTACHMENT)
                or type(size) is not int or not 0 <= size <= _MAX_SESSION_BYTES):
            raise ValueError
        request = Request(attachment["url"], headers={"User-Agent": "FortniteVisualChestCounter"})
        with build_opener(_NoRedirects()).open(request, timeout=8) as response:
            raw = response.read(_MAX_SESSION_BYTES + 1)
        return raw
    except (KeyError, AttributeError, TypeError, ValueError, OSError, URLError):
        raise ValueError("Could not read the shared session snapshot from Discord.") from None


def _fetch_sessions(message):
    raw = _fetch_attachment(message)
    return _decode_sessions(raw) if raw is not None else ()


def fetch(webhook, ident, *, with_team=False, with_settings=False, with_sessions=False):
    if not valid_id(ident):
        raise ValueError("Enter a valid leaderboard message ID.")
    message = _request(webhook, f"/messages/{ident}", "GET")
    decoded = _decode(webhook, message, with_team=with_team, with_settings=with_settings or with_sessions)
    if message["embeds"][0].get("title") == _DATA_TITLE:
        raw = _fetch_attachment(message)
        if raw is None:
            raise ValueError("Group sync data is missing its snapshot attachment.")
        snapshot = _decode_data_snapshot(raw)
        if with_sessions:
            return snapshot
        if with_settings:
            return snapshot[:3]
        return snapshot[:2] if with_team else snapshot[0]
    if with_sessions:
        return (*decoded, _fetch_sessions(message))
    return decoded


def delete(webhook, ident):
    """Delete only the leaderboard for the configured webhook."""
    try:
        fetch(webhook, ident)
        _request(webhook, f"/messages/{ident}", "DELETE")
    except BoardNotFound:
        pass


def make_embed(ranking, team=None, *, settings=None):
    embed = {"title": "🏆 Shared chest leaderboard", "color": 0xE9A954,
             "description": "Top 10 players" if ranking else "No matches shared yet.",
             "fields": [_field(i, row) for i, row in enumerate(ranking, 1)],
             "footer": {"text": _MARKER}}
    if settings is not None:
        mode, boost = settings
        if mode not in MODES or boost not in BOOSTS:
            raise ValueError("Invalid group match settings.")
        embed["description"] += f"\nGroup settings: {mode} · ×{boost:g}"
    if team is not None:
        embed["description"] += "\n\n" + team.text()
    return embed


def type_breakdown(chest_types):
    return " · ".join(f"{label} {chest_types[key]:,}"
                      for key, label in discord_group.GROUP_TYPE_LABELS.items() if chest_types.get(key))


def make_public_embed(players, team=None, *, settings=None):
    """Readable bot output, separate from the webhook payload read by clients."""
    players = players[:_MAX_RANKS]
    embed = make_embed((), settings=settings)
    embed["description"] = "Player totals across shared results." if players else "No matches shared yet."
    if settings is not None:
        mode, boost = settings
        embed["footer"]["text"] = f"Current group settings · {mode} ×{boost:g}"
    for index, player in enumerate(players, 1):
        results = "result" if player.matches == 1 else "results"
        value = (f"**{player.total:,}** chests · {player.matches:,} {results} · "
                 f"Pirate Token chance · **{player.token_chance}**")
        embed["fields"].append({"name": f"{index}. {player.name}", "value": value, "inline": False})
    if team is not None and team.matches:
        players_received = "player" if team.players == 1 else "players"
        chance = team.chance_percent or (f"about 1 in {team.one_in:,}" if team.one_in else "0%")
        value = (f"**{team.chests:,}** chests · Results received from {team.players:,} {players_received}\n"
                 f"Estimated Pirate Token chance · **{chance}**\n"
                 f"Matches synced in total · {team.matches:,}")
        embed["fields"].append({"name": "Latest synchronized match", "value": value, "inline": False})
    return embed


def publish(webhook, ident, ranking, team=None, *, settings=None, sessions=None, data_only=False):
    if ident:
        _decode(webhook, _request(webhook, f"/messages/{ident}", "GET"))
    embed = make_embed(ranking, team, settings=settings)
    if data_only:
        embed.update(title=_DATA_TITLE, description="Synchronizes the apps in this group. The public leaderboard "
                     "is published by the bot in the selected channel.", fields=[])
    suffix, method = (f"/messages/{ident}", "PATCH") if ident else ("?wait=true", "POST")
    payload = {"embeds": [embed], "allowed_mentions": {"parse": []}}
    if not ident:
        payload.update(discord_group.webhook_identity())
    if sessions is not None or data_only:
        payload["attachments"] = [{"id": 0, "filename": _SESSION_ATTACHMENT}]
        attachment = (_encode_data_snapshot(ranking, team, settings, sessions or ()) if data_only
                      else _encode_sessions(sessions))
        message = _request(webhook, suffix, method, payload, attachment=attachment)
    else:
        message = _request(webhook, suffix, method, payload)
    try:
        channel, message_id = message["channel_id"], message["id"]
        guild = message.get("guild_id")
        if not valid_id(channel) or not valid_id(message_id) or (guild is not None and not valid_id(guild)):
            raise ValueError
        return message_id, f"https://discord.com/channels/{guild or '@me'}/{channel}/{message_id}" if guild else message_id
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ValueError("Discord did not return the leaderboard message ID.") from None
