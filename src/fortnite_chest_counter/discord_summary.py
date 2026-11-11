"""Opt-in Discord bot delivery for saved match summaries."""

from dataclasses import asdict, dataclass, field
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fortnite_chest_counter.detection.chest_types import LABELS
from fortnite_chest_counter.obs import credentials


_TARGET = "Fortnite Visual Chest Counter/Discord Bot"


@dataclass(frozen=True)
class BotSettings:
    channel: str
    token: str = field(repr=False)
    application_id: str = ""


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def load():
    raw = credentials.load_password(_TARGET)
    if not raw:
        return None
    try:
        values = BotSettings(**json.loads(raw))
        _validate(values)
        return values
    except (TypeError, ValueError) as error:
        raise ValueError("The saved Discord settings are invalid. Save the setup again.") from error


def valid_id(value):
    return isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{14,21}", value) is not None


def _validate(values):
    if values.channel and not valid_id(values.channel):
        raise ValueError("Enter a valid Discord channel ID.")
    if not isinstance(values.token, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{8,300}", values.token):
        raise ValueError("Enter a Discord bot token.")
    if values.application_id != "" and not valid_id(values.application_id):
        raise ValueError("Enter a valid Discord Application ID.")


def save(values):
    _validate(values)
    credentials.save_password(json.dumps(asdict(values)), _TARGET, description="Discord bot configuration")


def forget():
    credentials.forget_password(_TARGET)


def send(values, content):
    """Send a match report, or a plain-text message for existing callers."""
    _validate(values)
    if not valid_id(values.channel):
        raise ValueError("The bot has not resolved the Group webhook channel.")
    if isinstance(content, str):
        return _send(values, {"content": content})
    embed = {
        "title": "Fortnite match report",
        "description": f"{content.mode} · {content.finished_at}"[:4096],
        "color": 0x5865F2,
        "fields": [
            {"name": "Total chests", "value": f"{content.total:,}", "inline": False},
            {"name": "Certain", "value": f"{content.certain:,}", "inline": True},
            {"name": "Estimated", "value": f"{content.estimated:,}", "inline": True},
            {"name": "Estimated Pirate Token chance", "value": content.token_chance[:1024] or "Unavailable",
             "inline": False},
        ],
    }
    if getattr(content, "player", ""):
        embed["author"] = {"name": content.player[:256]}
    chest_types = getattr(content, "chest_types", {})
    fallback = content.summary()
    if chest_types:
        labels = {**LABELS, "unclassified": "Not classified"}
        breakdown = "\n".join(f"{label}: {chest_types[key]:,}" for key, label in labels.items() if key in chest_types)
        if breakdown:
            embed["fields"].append({"name": "Chest types", "value": breakdown, "inline": False})
            fallback += f"\n{breakdown}"
    try:
        _send(values, {"embeds": [embed]}, allow_embed_fallback=True)
    except _EmbedForbidden:
        _send(values, {"content": fallback[:2000]})


class _EmbedForbidden(Exception):
    pass


def _send(values, payload, *, allow_embed_fallback=False):
    body = json.dumps({**payload, "allowed_mentions": {"parse": []}}).encode("utf-8")
    request = Request(f"https://discord.com/api/v10/channels/{values.channel}/messages", data=body,
                      headers={"Authorization": f"Bot {values.token}", "Content-Type": "application/json",
                               "User-Agent": "FortniteVisualChestCounter"})
    try:
        with build_opener(_NoRedirects()).open(request, timeout=12):
            pass
    except HTTPError as error:
        if allow_embed_fallback and error.code == 403:
            # A rejected request cannot have posted a duplicate. Discord uses
            # the same missing-permission response for Embed Links and Send Messages.
            raise _EmbedForbidden from None
        messages = {401: "Discord rejected the bot token.", 403: "The bot cannot send messages in this channel.",
                    404: "Discord could not find the channel.", 429: "Discord is rate limiting requests. Try again later."}
        raise ValueError(messages.get(error.code, f"Discord returned HTTP {error.code}.")) from None
    except (OSError, URLError):
        raise ValueError("Discord did not confirm delivery. Check the channel before retrying.") from None
