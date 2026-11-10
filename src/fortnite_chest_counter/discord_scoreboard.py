"""Publish and read the shared Discord leaderboard message."""

from dataclasses import dataclass, field
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

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


def _request(webhook, suffix, method, payload=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(webhook.url + suffix, data=body, method=method,
                      headers={"Content-Type": "application/json", "User-Agent": "FortniteVisualChestCounter"})
    try:
        with build_opener(_NoRedirects()).open(request, timeout=8) as response:
            if response.status == 204:
                return None
            return json.load(response)
    except HTTPError as error:
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


def fetch(webhook, ident, *, with_team=False, with_settings=False):
    if not valid_id(ident):
        raise ValueError("Enter a valid leaderboard message ID.")
    return _decode(webhook, _request(webhook, f"/messages/{ident}", "GET"), with_team=with_team,
                   with_settings=with_settings)


def delete(webhook, ident):
    """Delete only the leaderboard for the configured webhook."""
    try:
        fetch(webhook, ident)
        _request(webhook, f"/messages/{ident}", "DELETE")
    except BoardNotFound:
        pass


def publish(webhook, ident, ranking, team=None, *, settings=None):
    if ident:
        # Do not overwrite a normal contribution or other webhook message.
        fetch(webhook, ident)
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
    suffix, method = (f"/messages/{ident}", "PATCH") if ident else ("?wait=true", "POST")
    message = _request(webhook, suffix, method, {"embeds": [embed], "allowed_mentions": {"parse": []}})
    try:
        channel, message_id = message["channel_id"], message["id"]
        guild = message.get("guild_id")
        if not valid_id(channel) or not valid_id(message_id) or (guild is not None and not valid_id(guild)):
            raise ValueError
        return message_id, f"https://discord.com/channels/{guild or '@me'}/{channel}/{message_id}" if guild else message_id
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ValueError("Discord did not return the leaderboard message ID.") from None
