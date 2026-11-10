"""Opt-in Discord bot delivery for saved match summaries."""

from dataclasses import asdict, dataclass
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fortnite_chest_counter.obs import credentials


_TARGET = "Fortnite Visual Chest Counter/Discord Bot"


@dataclass(frozen=True)
class BotSettings:
    channel: str
    token: str


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


def _validate(values):
    if not isinstance(values.channel, str) or not re.fullmatch(r"[1-9][0-9]{14,21}", values.channel):
        raise ValueError("Enter a valid Discord channel ID.")
    if not isinstance(values.token, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{8,300}", values.token):
        raise ValueError("Enter a Discord bot token.")


def save(values):
    _validate(values)
    credentials.save_password(json.dumps(asdict(values)), _TARGET, description="Discord bot configuration")


def forget():
    credentials.forget_password(_TARGET)


def send(values, content):
    _validate(values)
    body = json.dumps({"content": content, "allowed_mentions": {"parse": []}}).encode("utf-8")
    request = Request(f"https://discord.com/api/v10/channels/{values.channel}/messages", data=body,
                      headers={"Authorization": f"Bot {values.token}", "Content-Type": "application/json",
                               "User-Agent": "FortniteVisualChestCounter"})
    try:
        with build_opener(_NoRedirects()).open(request, timeout=12):
            pass
    except HTTPError as error:
        messages = {401: "Discord rejected the bot token.", 403: "The bot cannot send messages in this channel.",
                    404: "Discord could not find the channel.", 429: "Discord is rate limiting requests. Try again later."}
        raise ValueError(messages.get(error.code, f"Discord returned HTTP {error.code}.")) from None
    except (OSError, URLError):
        raise ValueError("Discord did not confirm delivery. Check the channel before retrying.") from None
