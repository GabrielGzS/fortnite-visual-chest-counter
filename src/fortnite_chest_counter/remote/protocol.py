"""
Remote Sharing protocol v1, the publisher's side: pure rules, no network, no files written.

The relay is whatever compatible server the user runs (the protocol is documented with the reference relay). Nothing
here names a host or a hosting company: the relay address is always the user's own.

    publisher -> relay   snapshot (full counts, rising rev), links (the channel's active viewer links), ping
    relay -> publisher   hello (protocol, stored rev, viewers, active link ids), ack, viewers, error

TLS: wss:// only (ws:// only for this PC, for testing). Certificates and host names are always checked, against the
Mozilla root list bundled with the app (certifi). Windows' own certificate store is deliberately not used: some PCs keep
an expired copy of a root's cross-signature there that makes Python reject valid certificates. Company-installed
private certificate authorities are therefore not trusted (a documented limitation).
"""

import base64
import hashlib
import hmac
import json
import re
import secrets
import ssl
from pathlib import Path
from urllib.parse import urlsplit

PROTOCOL = "fcc.v1"
USER_AGENT = "FortniteVisualChestCounter-RemoteSharing/1"
CHANNEL_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
LINK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,32}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
MAX_LINKS = 16                       # active viewer links per channel (the relay's limit)
MAX_LABEL = 40
MAX_LINES, MAX_LINE = 4, 120         # the overlay text sent along: far below the relay's 4,096-character message limit


def relay_url_problem(url):
    """None if `url` is a usable relay address, else a short reason. An empty url is not a problem (sharing is off)."""
    if not url:
        return None
    if not isinstance(url, str) or any(c.isspace() for c in url):
        return "must be a wss:// address without spaces"
    parts = urlsplit(url)
    if parts.scheme not in ("ws", "wss") or not parts.hostname:
        return "must start with wss://"
    if parts.scheme == "ws" and parts.hostname not in LOCAL_HOSTS:
        return "must use wss:// (ws:// is only allowed for this PC)"
    if parts.query or parts.fragment or parts.username or parts.password:
        return "must be just the relay address, e.g. wss://your-relay.example"
    try:
        parts.port
    except ValueError:
        return "has a bad port number"
    return None


def endpoint(url, role, channel):
    """-> (host, port, path, secure) for wss://<relay>/v1/<role>/<channel>."""
    parts = urlsplit(url)
    secure = parts.scheme == "wss"
    base = parts.path.rstrip("/")
    return parts.hostname, parts.port or (443 if secure else 80), f"{base}/v1/{role}/{channel}", secure


def overlay_url(url, channel, link_id, token, options="show=both"):
    """The overlay page address for one viewer link (the credential stays in the #fragment, never sent to a server)."""
    parts = urlsplit(url)
    scheme = "https" if parts.scheme == "wss" else "http"
    base = parts.path.rstrip("/")
    return f"{scheme}://{parts.netloc}{base}/o/#{channel}.{link_id}.{token}" + (f"&{options}" if options else "")


def tls_context():
    """Certificate and host-name checks always on; trust = the bundled Mozilla list (certifi), or Python's default
    store only if certifi is missing (a source install without it). Verification is never switched off."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def new_channel_id():
    return secrets.token_urlsafe(18)


def new_link_id():
    return secrets.token_urlsafe(6)


def new_secret():
    return secrets.token_urlsafe(32)


def link_token(link_secret, channel, link_id):
    """A viewer link's token, derived from the profile's link secret: the app can show a link again without storing it."""
    digest = hmac.new(link_secret.encode("ascii"), f"{channel}.{link_id}".encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def sha256_hex(text):
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def setup_code(publisher_key):
    """What the relay stores: the key's SHA-256, never the key."""
    return sha256_hex(publisher_key)


def next_rev(last_sent, relay_rev, now_ms):
    """rev = max(unix ms, last sent + 1, the relay's stored rev + 1): always newer, even after a clock jump or a Reset."""
    return max(int(now_ms), int(last_sent) + 1, int(relay_rev) + 1)


def read_counts(path):
    """(certain, approx, updated_at) from a counter file - READ ONLY, never repairs or moves it (the counter does that).
    A missing file is (0, 0, None): a profile that never counted. None if the file cannot be read or is not valid."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 0, 0, None
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    certain, approx = raw.get("certain"), raw.get("approximate")
    if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in (certain, approx)):
        return None
    updated = raw.get("updated_at") if isinstance(raw.get("updated_at"), str) else None
    return certain, max(approx, certain), updated


def read_overlay_lines(path):
    """The overlay text exactly as local OBS reads it (obs_output/chest_counter.txt), as lines - READ ONLY. None if missing."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    lines = text.splitlines()
    return [line[:MAX_LINE] for line in lines[:MAX_LINES]] or None


def snapshot_message(rev, certain, approx, state, at=None, lines=None):
    """lines: the overlay text (the same wording as local OBS), in "ext" - the protocol's free field for presentation. A relay
    stores and forwards it untouched; an overlay page that does not know it shows the plain counts instead."""
    message = {"type": "snapshot", "v": 1, "rev": rev, "certain": certain, "approx": approx, "state": state}
    if at:
        message["at"] = at
    if lines:
        message["ext"] = {"lines": list(lines)}
    return message


def links_message(active):
    """active: [(link id, token sha256), ...] -> the relay's full replacement list for the channel."""
    return {"type": "links", "active": [{"id": link_id, "sha256": digest} for link_id, digest in active]}


def links_plan(relay_ids, active, known_ids):
    """What to do about the channel's viewer links after hello (or after our links changed while connected).

    relay_ids: link ids the relay holds as active; active: {id: sha256} this PC wants active; known_ids: every link id this
    PC has ever made for the channel (active or revoked). -> ("keep", None) nothing to send, ("send", message), or
    ("unknown", ids) when the relay holds links this PC never made: they are left untouched (sending our list would revoke
    them), so a link made on another PC is never revoked by accident."""
    relay = set(relay_ids or ())
    unknown = sorted(relay - set(known_ids))
    if unknown:
        return "unknown", unknown
    if relay == set(active):
        return "keep", None
    return "send", links_message(sorted(active.items()))
