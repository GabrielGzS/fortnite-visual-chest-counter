"""
Remote Sharing setup: what belongs to a profile and what belongs to this PC.

    per profile, in state/profiles.json        enabled, channel id, viewer links (id, label, created_at, revoked, token SHA-256)
    per profile, in Credential Manager          the secret the profile's viewer-link tokens are derived from
    per PC, in config.toml [remote] url         the relay address (one relay; the user's own)
    per PC, in Credential Manager               the publisher key (the relay stores only its SHA-256, the "setup code")

Only hashes of viewer tokens are written to profiles.json, so a copied profile can keep existing overlay links working
(the relay checks hashes) without carrying anything that lets someone watch or publish. Showing a link's address again
needs the secret, which stays on the PC that made it.
"""

import re
import time

from fortnite_chest_counter import profiles
from fortnite_chest_counter.obs import credentials
from fortnite_chest_counter.remote import protocol as P

KEY_TARGET = "Fortnite Visual Chest Counter/Remote Sharing publisher key"
LINKS_TARGET = "Fortnite Visual Chest Counter/Remote Sharing links/"        # + profile id
_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{32,256}$")


class SharingError(ValueError):
    """A request that cannot be done; the message is meant for the user."""


# ---- the publisher key (per PC)

def load_publisher_key():
    try:
        return credentials.load_password(KEY_TARGET)
    except OSError:
        return ""


def save_publisher_key(key):
    key = (key or "").strip()
    if not _KEY_RE.match(key):
        raise SharingError("A publisher key is 32-256 characters of A-Z a-z 0-9 _ -.")
    credentials.save_password(key, KEY_TARGET, comment="Remote Sharing publisher key", username="remote-sharing")


def forget_publisher_key():
    credentials.forget_password(KEY_TARGET)


# ---- a profile's channel and viewer links

def remote_of(base_state_path, profile_id):
    """The profile's Remote Sharing data, or None if it never had any."""
    return profiles.get(profiles.load(base_state_path), profile_id).get("remote")


def _store(base_state_path, profile_id, remote):
    try:
        profiles.set_remote(base_state_path, profile_id, remote)
    except profiles.ProfileError as error:
        raise SharingError(str(error))


def set_enabled(base_state_path, profile_id, enabled):
    """Turn sharing on or off for one profile. The first time it is turned on, the profile gets its own channel."""
    remote = remote_of(base_state_path, profile_id) or {"channel": P.new_channel_id(), "links": []}
    _store(base_state_path, profile_id, {**remote, "enabled": bool(enabled)})
    return remote_of(base_state_path, profile_id)


def _link_secret(profile_id, create):
    target = LINKS_TARGET + profile_id
    secret = credentials.load_password(target)
    if not secret and create:
        secret = P.new_secret()
        credentials.save_password(secret, target, comment="Remote Sharing viewer links", username="remote-sharing")
    return secret


def add_link(base_state_path, profile_id, label):
    """A new read-only viewer link for the profile's channel. -> (link id, token). The token is not stored anywhere."""
    remote = remote_of(base_state_path, profile_id)
    if remote is None:
        raise SharingError("Turn Remote Sharing on for this profile first.")
    if sum(not link.get("revoked") for link in remote["links"]) >= P.MAX_LINKS:
        raise SharingError(f"A profile can have at most {P.MAX_LINKS} active viewer links. Revoke one first.")
    secret = _link_secret(profile_id, create=True)
    link_id = P.new_link_id()
    token = P.link_token(secret, remote["channel"], link_id)
    link = {"id": link_id, "label": " ".join(str(label or "").split())[:P.MAX_LABEL], "sha256": P.sha256_hex(token),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    _store(base_state_path, profile_id, {**remote, "links": remote["links"] + [link]})
    return link_id, token


def revoke_link(base_state_path, profile_id, link_id):
    remote = remote_of(base_state_path, profile_id)
    links = (remote or {}).get("links", [])
    if not any(link["id"] == link_id for link in links):
        raise SharingError(f"This profile has no viewer link {link_id}.")
    _store(base_state_path, profile_id, {**remote, "links": [{**link, "revoked": True} if link["id"] == link_id else link
                                                             for link in links]})


def link_token(base_state_path, profile_id, link_id):
    """The token of one of the profile's links, if this PC can still derive it (it holds the secret), else None."""
    remote = remote_of(base_state_path, profile_id)
    link = next((l for l in (remote or {}).get("links", []) if l["id"] == link_id), None)
    secret = _link_secret(profile_id, create=False) if link else ""
    if not secret:
        return None
    token = P.link_token(secret, remote["channel"], link_id)
    return token if P.sha256_hex(token) == link["sha256"] else None
