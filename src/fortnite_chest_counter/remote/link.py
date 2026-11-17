"""
Remote Sharing's publisher: the active profile's counter, sent to the user's own relay (protocol.py).

It works like the OBS WebSocket output (obs/link.py): one background thread of the app, never the counting worker. It
only READS files - config.toml ([remote] url), profiles.json (the active profile and its channel) and that profile's
counter file - so the counting worker, Edit counts, Reset, the console commands and a profile switch all reach viewers the
same way, and a slow or missing relay can never block counting, saving or the window. Only the newest counts are sent.

Off unless all of these are true: a relay address in config.toml, the active profile has sharing turned on, and this PC
has a publisher key. Off means no socket is ever opened. One connection at a time, for the active profile only: a
profile switch closes the previous channel (its viewers see "offline" with the last count) before the next one opens.

Whether the counter is counting comes from the app (set_counting), not from the file: starting or stopping does not
necessarily change it.
"""

import json
import random
import ssl
import threading
import time
from collections import namedtuple
from pathlib import Path

from fortnite_chest_counter import profiles, settings
from fortnite_chest_counter.obs.websocket import ConnectionClosed, HandshakeRefused, WebSocket, WebSocketError
from fortnite_chest_counter.remote import protocol as P
from fortnite_chest_counter.remote import sharing

POLL_SECONDS = 0.25                     # how often files are checked (and how long the relay is listened to)
PING_SECONDS = 30
SILENCE_SECONDS = 75                    # nothing heard for this long: the connection is dead, reconnect
BACKOFF_SECONDS = (1, 2, 5, 10, 20, 30)
CONNECT_TIMEOUT = 10
KEY_RECHECK_SECONDS = 5                 # after the relay refused the key, look for a new one this often

Target = namedtuple("Target", "url profile_id profile_name channel counter_path overlay_path active known")

_tls = None


def connect_relay(url, channel, key):
    """Open the publisher connection to wss://<relay>/v1/publish/<channel>. Raises HandshakeRefused (401: wrong key)."""
    global _tls
    host, port, path, secure = P.endpoint(url, "publish", channel)
    if secure and _tls is None:
        _tls = P.tls_context()
    return WebSocket.connect(host, port, path, subprotocol=P.PROTOCOL, timeout=CONNECT_TIMEOUT,
                             ssl_context=_tls if secure else None,
                             headers={"Authorization": f"Bearer {key}", "User-Agent": P.USER_AGENT})


def _signature(path):
    try:
        st = Path(path).stat()
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


def _identity(target):
    return None if target is None else (target.url, target.profile_id, target.channel)


def _host(url):
    return P.endpoint(url, "publish", "x")[0] if url else ""


class RemoteLink:
    def __init__(self, config_path, connect=connect_relay, key_loader=sharing.load_publisher_key, clock=time.time,
                 poll=POLL_SECONDS):
        self.config_path = Path(config_path)
        self._connect, self._key_loader, self._clock, self.poll = connect, key_loader, clock, poll
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._thread = None
        self._counting = False
        self._version = 0
        self._status = {"state": "off", "detail": "", "warning": "", "viewers": 0, "profile": "", "relay": ""}
        self._config_sig = None
        self._url, self._base, self._overlay, self._resolved, self._resolved_key = "", None, None, (None, ""), None
        self._last_rev = 0                      # the newest rev sent on the current channel

    # ---- the app's side (any thread)
    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True, name="remote-sharing")
            self._thread.start()
        return self

    def stop(self, timeout=1.0):
        """Close the connection (viewers see "offline" with the last count) and end the thread."""
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def set_counting(self, counting):
        with self._lock:
            self._counting = bool(counting)
        self._wake.set()

    def status(self):
        """-> (version, status dict). The version changes whenever anything in the status does."""
        with self._lock:
            return self._version, dict(self._status)

    # ---- the thread
    def _set_status(self, **changes):
        with self._lock:
            new = {**self._status, **changes}
            if new != self._status:
                self._status = new
                self._version += 1

    def _wait(self, seconds):
        self._wake.wait(max(0.0, seconds))
        self._wake.clear()

    def _resolve(self):
        """-> (Target or None, why not). Re-reads config.toml / profiles.json only when they change. Never writes."""
        sig = _signature(self.config_path)
        if sig != self._config_sig:
            self._config_sig = sig
            try:
                cfg, _, _ = settings.load_config(self.config_path)
                root = self.config_path.parent                 # relative paths are relative to the program folder
                self._url, self._base = cfg["remote"]["url"], root / cfg["state"]["path"]
                self._overlay = root / cfg["state"]["obs_dir"] / "chest_counter.txt"
            except Exception:                      # a broken config: the app reports it; nothing is shared meanwhile
                self._url, self._base = "", None
        if not self._url or self._base is None:
            self._resolved = (None, "No relay address is set.")
            return self._resolved
        path = profiles.registry_path(self._base)
        key = (self._config_sig, _signature(path))
        if key == self._resolved_key:
            return self._resolved
        self._resolved_key = key
        try:
            reg = profiles._validate(json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            self._resolved = (None, "Remote Sharing is off for this profile.")
            return self._resolved
        except (OSError, ValueError):              # damaged or being rewritten: the app repairs it; try again next time
            self._resolved_key = None
            self._resolved = (None, "The profile list could not be read.")
            return self._resolved
        entry = profiles.get(reg, reg["active"])
        remote = entry.get("remote")
        if not remote or not remote["enabled"]:
            self._resolved = (None, f"Remote Sharing is off for {entry['name']}.")
            return self._resolved
        links = remote["links"]
        active = tuple((l["id"], l["sha256"]) for l in links if not l.get("revoked"))[:P.MAX_LINKS]
        self._resolved = (Target(self._url, entry["id"], entry["name"], remote["channel"],
                                 profiles.profile_state_path(self._base, entry["id"]), self._overlay, active,
                                 frozenset(l["id"] for l in links)), "")
        return self._resolved

    def _run(self):
        ws, conn, target = None, None, None
        halted, halted_key, attempt, next_try, key_checked = None, None, 0, 0.0, 0.0
        while not self._stopping.is_set():
            new, why = self._resolve()
            if _identity(new) != _identity(target):
                if ws is not None:
                    self._close(ws)
                    ws = None
                halted, attempt, next_try, self._last_rev = None, 0, 0.0, 0
            target = new
            now = time.monotonic()
            if target is None:
                self._set_status(state="off", detail=why, warning="", viewers=0, profile="", relay="")
                self._wait(self.poll)
                continue
            if ws is None:
                if halted == "key_rejected" and now - key_checked >= KEY_RECHECK_SECONDS:
                    key_checked = now
                    if self._key_loader() != halted_key:
                        halted = None
                if halted is not None or now < next_try:
                    self._wait(self.poll if halted else min(self.poll, next_try - now))
                    continue
                key = self._key_loader()
                if not key:
                    self._set_status(state="no_key", detail="This PC has no publisher key for the relay.", viewers=0,
                                     profile=target.profile_name, relay=_host(target.url))
                    self._wait(1.0)
                    continue
                self._set_status(state="connecting", detail="", profile=target.profile_name, relay=_host(target.url))
                try:
                    ws = self._connect(target.url, target.channel, key)
                    conn = self._hello(ws, target)
                    attempt = 0
                except HandshakeRefused as error:
                    ws = None
                    if error.status == 401:
                        halted, halted_key, key_checked = "key_rejected", key, now
                        self._set_status(state="key_rejected", viewers=0, detail="The relay did not accept this PC's "
                                         "publisher key: set its setup code on the relay, or import the right key.")
                        continue
                    next_try, attempt = self._retry_at(attempt), attempt + 1
                    self._set_status(state="retrying", viewers=0,
                                     detail=f"Not a compatible relay (it answered HTTP {error.status}).")
                except ssl.SSLCertVerificationError:
                    ws = self._drop(ws)
                    next_try, attempt = self._retry_at(attempt), attempt + 1
                    self._set_status(state="retrying", viewers=0, detail="The relay's certificate is not trusted.")
                except (OSError, WebSocketError, ValueError) as error:
                    ws = self._drop(ws)
                    next_try, attempt = self._retry_at(attempt), attempt + 1
                    self._set_status(state="retrying", viewers=0, detail=f"Cannot reach the relay ({_short(error)}).")
                continue
            try:
                self._publish(ws, conn, target)
                if (target.active, target.known) != conn["links_for"]:
                    self._sync_links(ws, conn, target)
                if now - conn["last_ping"] >= PING_SECONDS:
                    ws.send_text('{"type":"ping"}')
                    conn["last_ping"] = now
                message = ws.recv(self.poll)
                if message is not None:
                    conn["last_heard"] = time.monotonic()
                    self._handle(message, conn)
                elif time.monotonic() - conn["last_heard"] > SILENCE_SECONDS:
                    raise ConnectionClosed(1006, "the relay went silent")
            except ConnectionClosed as closed:
                ws = self._drop(ws)
                if closed.code == 4001:
                    halted = "taken_over"
                    self._set_status(state="taken_over", viewers=0, detail="Another PC is now publishing this profile's "
                                     "channel. Turn sharing off and on again to take it back.")
                else:
                    next_try, attempt = self._retry_at(0), 1
                    self._set_status(state="retrying", viewers=0, detail="The connection to the relay was lost.")
            except (OSError, WebSocketError, ValueError) as error:
                ws = self._drop(ws)
                next_try, attempt = self._retry_at(0), 1
                self._set_status(state="retrying", viewers=0, detail=f"The connection to the relay failed ({_short(error)}).")
        if ws is not None:
            self._close(ws)
        self._set_status(state="off", detail="Stopped.", viewers=0)

    def _retry_at(self, attempt):
        delay = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
        return time.monotonic() + delay + random.random() * delay * 0.3

    @staticmethod
    def _drop(ws):
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        return None

    @staticmethod
    def _close(ws):
        try:
            ws.close(1000)
        except Exception:
            pass

    def _hello(self, ws, target):
        deadline = time.monotonic() + CONNECT_TIMEOUT
        while True:
            text = ws.recv(max(0.05, deadline - time.monotonic()))
            if text is None:
                if time.monotonic() >= deadline:
                    raise WebSocketError("the relay did not say hello")
                continue
            hello = json.loads(text)
            if not isinstance(hello, dict) or hello.get("type") != "hello" or hello.get("protocol") != 1:
                raise WebSocketError("not a protocol v1 relay")
            break
        now = time.monotonic()
        relay_rev = hello.get("rev") if isinstance(hello.get("rev"), int) else 0
        conn = {"relay_rev": relay_rev, "relay_links": list(hello.get("links") or []), "links_for": None, "sent": None,
                "counter_sig": None, "last_ping": now, "last_heard": now}
        self._set_status(state="connected", detail="", warning="", viewers=int(hello.get("viewers") or 0))
        self._sync_links(ws, conn, target)
        self._publish(ws, conn, target, force=True)                  # the authoritative count, right after (re)connecting
        return conn

    def _sync_links(self, ws, conn, target):
        conn["links_for"] = (target.active, target.known)
        plan, data = P.links_plan(conn["relay_links"], dict(target.active), target.known)
        if plan == "send":
            ws.send_text(json.dumps(data))
            conn["relay_links"] = [link_id for link_id, _ in target.active]
            self._set_status(warning="")
        elif plan == "unknown":
            self._set_status(warning=f"The relay holds {len(data)} viewer link(s) this PC did not make; they were left as "
                                     "they are and new links cannot be added until they are revoked.")
        else:
            self._set_status(warning="")

    def _publish(self, ws, conn, target, force=False):
        """Send the counts if they (or counting/idle) changed since the last snapshot."""
        sig = (_signature(target.counter_path), _signature(target.overlay_path))
        with self._lock:
            counting = self._counting
        if not force and sig == conn["counter_sig"] and conn["sent"] is not None and conn["sent"][2] == counting:
            return
        conn["counter_sig"] = sig
        counts = P.read_counts(target.counter_path)
        if counts is None:
            self._set_status(detail="The counter file could not be read; viewers keep the last count.")
            return
        certain, approx, at = counts
        lines = P.read_overlay_lines(target.overlay_path)      # the active profile's text, as local OBS shows it
        current = (certain, approx, counting, tuple(lines or ()))
        if not force and current == conn["sent"]:
            return
        rev = P.next_rev(self._last_rev, conn["relay_rev"], self._clock() * 1000)
        ws.send_text(json.dumps(P.snapshot_message(rev, certain, approx, "counting" if counting else "idle", at, lines),
                                ensure_ascii=False))
        conn["sent"], self._last_rev = current, rev
        self._set_status(detail="")

    def _handle(self, text, conn):
        try:
            message = json.loads(text)
        except ValueError:
            return
        if not isinstance(message, dict):
            return
        kind = message.get("type")
        if kind == "viewers" and isinstance(message.get("n"), int):
            self._set_status(viewers=message["n"])
        elif kind == "ack" and isinstance(message.get("links"), list):
            conn["relay_links"] = list(message["links"])
        elif kind == "ack" and message.get("accepted") is False:     # the relay holds a newer rev: send again, newer
            if isinstance(message.get("rev"), int):
                conn["relay_rev"] = max(conn["relay_rev"], message["rev"])
            conn["sent"] = None
        elif kind == "error":
            self._set_status(detail=f"The relay refused a message ({message.get('code')}).")


def _short(error):
    text = str(error) or type(error).__name__
    return text if len(text) <= 80 else text[:77] + "..."
