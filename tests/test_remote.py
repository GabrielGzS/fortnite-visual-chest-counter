"""
Remote Sharing, the publisher (B1): protocol rules, profile data, the background link against an in-process fake relay
that enforces protocol v1 (no network), the WebSocket client's TLS/header additions, and the "off = no socket" rule.
Run:   python tests/test_remote.py     (or pytest)
"""
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "src"))   # run without installing

import json
import queue
import re
import socket
import ssl
import tempfile
import threading
import time
from pathlib import Path

from fortnite_chest_counter import counter, profiles, settings
from fortnite_chest_counter.obs import websocket as wsmod
from fortnite_chest_counter.obs.websocket import ConnectionClosed, HandshakeRefused
from fortnite_chest_counter.remote import link as L
from fortnite_chest_counter.remote import protocol as P
from fortnite_chest_counter.remote import sharing

KEY = "k" * 43
NL = chr(10)
SRC =Path(__file__).resolve().parent.parent / "src" / "fortnite_chest_counter"


# ==================================================================
# a fake relay (protocol v1 rules, in process) and helpers
# ==================================================================

class FakeConn:
    def __init__(self, relay, channel):
        self.relay, self.channel, self.inbox, self.sent, self.closed_with = relay, channel, queue.Queue(), [], None

    def send_text(self, text):
        if self.closed_with is not None:
            raise ConnectionClosed(1006, "closed")
        message = json.loads(text)
        self.sent.append(message)
        self.relay.receive(self, message)

    def recv(self, timeout):
        try:
            item = self.inbox.get(timeout=max(timeout, 0.001))
        except queue.Empty:
            return None
        if isinstance(item, ConnectionClosed):
            self.closed_with = item.code
            raise item
        return item

    def close(self, code=1000):
        if self.closed_with is None:
            self.closed_with = code
            self.relay.closed(self, code)


class FakeRelay:
    def __init__(self, key=KEY):
        self.key, self.lock, self.channels, self.connects, self.events = key, threading.Lock(), {}, [], []

    def channel(self, name):
        return self.channels.setdefault(name, {"rev": 0, "snapshot": None, "links": {}, "pub": None, "history": []})

    def connect(self, url, channel, key):
        with self.lock:
            self.connects.append((url, channel))
            self.events.append(("connect", channel))
            if key != self.key:
                raise HandshakeRefused(401, "HTTP/1.1 401 Unauthorized")
            ch = self.channel(channel)
            if ch["pub"] is not None and ch["pub"].closed_with is None:
                ch["pub"].closed_with = 4001
                ch["pub"].inbox.put(ConnectionClosed(4001, "replaced"))
            conn = FakeConn(self, channel)
            ch["pub"] = conn
            conn.inbox.put(json.dumps({"type": "hello", "protocol": 1, "rev": ch["rev"], "viewers": 1,
                                       "links": sorted(ch["links"])}))
            return conn

    def receive(self, conn, message):
        with self.lock:
            ch = self.channel(conn.channel)
            if message["type"] == "snapshot":
                accepted = message["rev"] > ch["rev"]
                if accepted:
                    ch["rev"], ch["snapshot"] = message["rev"], message
                    ch["history"].append((message["certain"], message["approx"], message["state"], message["rev"],
                                          tuple((message.get("ext") or {}).get("lines") or ())))
                conn.inbox.put(json.dumps({"type": "ack", "rev": ch["rev"], "accepted": accepted}))
            elif message["type"] == "links":
                ch["links"] = {l["id"]: l["sha256"] for l in message["active"]}
                conn.inbox.put(json.dumps({"type": "ack", "links": sorted(ch["links"])}))
            elif message["type"] == "ping":
                conn.inbox.put('{"type":"pong"}')

    def closed(self, conn, code):
        with self.lock:
            self.events.append(("close", conn.channel, code))

    def drop(self, channel, code=1006):
        conn = self.channel(channel)["pub"]
        conn.inbox.put(ConnectionClosed(code, "dropped"))


def wait_until(condition, timeout=5.0, what="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {what}")


class FakeCreds:
    def __init__(self):
        self.store = {}

    def load_password(self, target=""):
        return self.store.get(target, "")

    def save_password(self, password, target="", comment="", username=""):
        self.store[target] = password

    def forget_password(self, target=""):
        self.store.pop(target, None)


class Setup:
    """A temporary app folder: config.toml with an absolute state path, profiles, a fake Credential Manager."""

    def __init__(self, url="wss://relay.test"):
        self.dir = Path(tempfile.mkdtemp())
        self.base = self.dir / "state" / "chest_state.json"
        self.config = self.dir / "config.toml"
        self.write_config(url)
        self._saved_creds = sharing.credentials
        sharing.credentials = FakeCreds()

    def write_config(self, url):
        self.config.write_text(f'[state]\npath = "{self.base.as_posix()}"\n\n[remote]\nurl = "{url}"\n', encoding="utf-8")

    def counts(self, profile_id, certain, approx):
        path = profiles.profile_state_path(self.base, profile_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        state = counter.fresh_state()
        state.update(certain=certain, approximate=approx)
        counter.save_state(path, state)
        time.sleep(0.03)                           # a new mtime even on coarse clocks

    def close(self):
        sharing.credentials = self._saved_creds


def started(setup, relay, key=KEY, **kwargs):
    return L.RemoteLink(setup.config, connect=relay.connect, key_loader=lambda: key, poll=0.05, **kwargs).start()


def history(relay, channel):
    return relay.channel(channel)["history"]


# ==================================================================
# pure rules
# ==================================================================

def test_relay_addresses_wss_only_except_this_pc():
    ok = ["", "wss://relay.example", "wss://relay.example:8443", "wss://relay.example/base", "ws://127.0.0.1:8787",
          "ws://localhost:8787"]
    bad = ["http://relay.example", "ws://relay.example", "wss://", "wss://relay.example/?x=1", "wss://a b",
           "wss://user:pw@relay.example", "relay.example"]
    for url in ok:
        assert P.relay_url_problem(url) is None, url
    for url in bad:
        assert P.relay_url_problem(url), url
    assert P.endpoint("wss://relay.example/base", "publish", "C" * 16) == ("relay.example", 443, f"/base/v1/publish/{'C' * 16}", True)
    assert P.endpoint("ws://127.0.0.1:8787", "view", "x")[1:] == (8787, "/v1/view/x", False)
    assert P.overlay_url("wss://relay.example", "CH", "LID", "TOK") == "https://relay.example/o/#CH.LID.TOK&show=both"
    ok_cfg, problem = settings._check("remote", "url", "ws://relay.example")
    assert not ok_cfg and "wss" in problem


def test_revisions_always_rise_after_resets_clock_jumps_and_relay_state():
    assert P.next_rev(0, 0, 1000) == 1000
    assert P.next_rev(5000, 0, 1000) == 5001           # the clock went back
    assert P.next_rev(0, 9000, 1000) == 9001           # the relay holds a newer one (another session)
    assert P.next_rev(1000, 1000, 1000) == 1001


def test_counter_file_is_read_without_ever_being_changed():
    folder = Path(tempfile.mkdtemp())
    path = folder / "c.json"
    assert P.read_counts(path) == (0, 0, None)                      # a profile that never counted
    path.write_text("{broken", encoding="utf-8")
    assert P.read_counts(path) is None
    assert path.read_text(encoding="utf-8") == "{broken" and sorted(p.name for p in folder.iterdir()) == ["c.json"]
    path.write_text(json.dumps({"certain": 9, "approximate": 4, "updated_at": "T"}), encoding="utf-8")
    assert P.read_counts(path) == (9, 9, "T")                       # APPROX includes CERTAIN
    path.write_text(json.dumps({"certain": True, "approximate": 4}), encoding="utf-8")
    assert P.read_counts(path) is None


def test_links_plan_never_revokes_links_this_pc_did_not_make():
    assert P.links_plan([], {}, set()) == ("keep", None)
    assert P.links_plan(["a1b2"], {"a1b2": "h"}, {"a1b2"}) == ("keep", None)
    kind, message = P.links_plan([], {"a1b2": "h"}, {"a1b2"})
    assert kind == "send" and message == {"type": "links", "active": [{"id": "a1b2", "sha256": "h"}]}
    assert P.links_plan(["a1b2", "old1"], {"a1b2": "h"}, {"a1b2", "old1"})[0] == "send"      # our revoked link: removed
    assert P.links_plan(["zzzz"], {"a1b2": "h"}, {"a1b2"}) == ("unknown", ["zzzz"])           # made elsewhere: untouched


def test_tls_always_verifies_against_the_bundled_root_list():
    import certifi
    ctx = P.tls_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    bundled = Path(certifi.where()).read_text(encoding="ascii").count("BEGIN CERTIFICATE")
    assert len(ctx.get_ca_certs()) == bundled                      # only certifi's roots, not the Windows store


def test_no_host_or_provider_is_named_in_the_app():
    pattern = re.compile(r"cloudflare|workers\.dev|overlaychestcounter|durable object", re.I)
    files = list((SRC / "remote").glob("*.py")) + [SRC / "settings.py", SRC / "profiles.py", SRC / "obs" / "websocket.py"]
    hits = [f"{f.name}: {m.group(0)}" for f in files for m in pattern.finditer(f.read_text(encoding="utf-8"))]
    assert not hits, hits


# ==================================================================
# profile data
# ==================================================================

def test_profile_remote_data_survives_saves_and_bad_data_is_dropped():
    s = Setup()
    try:
        profiles.create(s.base, "Streamer B", activate=False)
        remote = sharing.set_enabled(s.base, "streamer-b", True)
        assert remote["enabled"] and P.CHANNEL_RE.match(remote["channel"]) and remote["links"] == []
        link_id, token = sharing.add_link(s.base, "streamer-b", "OBS on PC B")
        profiles.rename(s.base, "streamer-b", "Streamer Bee")                 # an unrelated save keeps it
        profiles.set_hud(s.base, "streamer-b", "standard")
        again = sharing.remote_of(s.base, "streamer-b")
        assert again["channel"] == remote["channel"] and again["links"][0]["id"] == link_id
        assert again["links"][0]["sha256"] == P.sha256_hex(token)
        assert token not in profiles.registry_path(s.base).read_text(encoding="utf-8")   # only the hash is stored
        assert sharing.link_token(s.base, "streamer-b", link_id) == token
        assert sharing.remote_of(s.base, "default") is None                    # other profiles untouched
        sharing.revoke_link(s.base, "streamer-b", link_id)
        assert sharing.remote_of(s.base, "streamer-b")["links"][0]["revoked"] is True
        data = json.loads(profiles.registry_path(s.base).read_text(encoding="utf-8"))
        data["profiles"][1]["remote"] = {"enabled": True, "channel": "short"}      # damaged: dropped, sharing off
        profiles.registry_path(s.base).write_text(json.dumps(data), encoding="utf-8")
        assert sharing.remote_of(s.base, "streamer-b") is None
    finally:
        s.close()


# ==================================================================
# the link
# ==================================================================

def test_off_unless_relay_key_and_profile_sharing_are_all_set_and_off_opens_no_socket():
    s = Setup(url="")
    calls = []
    real = socket.create_connection
    socket.create_connection = lambda *a, **k: calls.append(a) or real(*a, **k)
    try:
        link = L.RemoteLink(s.config, key_loader=lambda: KEY, poll=0.05).start()      # the REAL connect function
        time.sleep(0.4)
        assert link.status()[1]["state"] == "off"
        s.write_config("wss://relay.invalid")                                       # a relay, but sharing is off
        time.sleep(0.4)
        assert link.status()[1]["state"] == "off" and "off for" in link.status()[1]["detail"]
        link.stop()                                            # (this link has a key: with sharing on it WOULD connect)
        sharing.set_enabled(s.base, "default", True)
        link = L.RemoteLink(s.config, key_loader=lambda: "", poll=0.05).start()       # sharing on, but no key
        wait_until(lambda: link.status()[1]["state"] == "no_key", what="no_key")
        link.stop()
        assert calls == [], calls
    finally:
        socket.create_connection = real
        s.close()


def test_publishes_the_active_profiles_counts_and_every_change():
    s, relay = Setup(), FakeRelay()
    try:
        channel = sharing.set_enabled(s.base, "default", True)["channel"]
        s.counts("default", 10, 25)
        link = started(s, relay)
        wait_until(lambda: history(relay, channel)[-1:] and history(relay, channel)[-1][:3] == (10, 25, "idle"), what="first")
        assert link.status()[1]["state"] == "connected"
        s.counts("default", 11, 27)                                      # the worker / Edit counts writes the file
        wait_until(lambda: history(relay, channel)[-1][:2] == (11, 27), what="change")
        link.set_counting(True)                                          # Start counting: no file change needed
        wait_until(lambda: history(relay, channel)[-1][2] == "counting", what="counting")
        s.counts("default", 0, 3)                                        # Reset to a lower total
        wait_until(lambda: history(relay, channel)[-1][:2] == (0, 3), what="reset")
        revs = [h[3] for h in history(relay, channel)]
        assert revs == sorted(revs) and len(set(revs)) == len(revs)
        before = len(history(relay, channel))
        s.counts("default", 0, 3)                                        # rewritten, same counts: nothing new to send
        time.sleep(0.3)
        assert len(history(relay, channel)) == before
        link.stop()
        assert ("close", channel, 1000) in relay.events                  # a clean close: viewers see "offline"
    finally:
        s.close()


def test_profile_switch_closes_the_old_channel_before_opening_the_next():
    s, relay = Setup(), FakeRelay()
    try:
        profiles.create(s.base, "Other", activate=False)
        profiles.create(s.base, "Private", activate=False)
        a = sharing.set_enabled(s.base, "default", True)["channel"]
        b = sharing.set_enabled(s.base, "other", True)["channel"]
        s.counts("default", 1, 2)
        s.counts("other", 7, 70)
        s.counts("private", 5, 50)
        link = started(s, relay)
        wait_until(lambda: history(relay, a), what="channel a")
        profiles.set_active(s.base, "other")
        wait_until(lambda: history(relay, b) and history(relay, b)[-1][:2] == (7, 70), what="channel b")
        closed_a = relay.events.index(("close", a, 1000))
        assert closed_a < relay.events.index(("connect", b))             # the old channel is closed first
        connects = len(relay.connects)
        profiles.set_active(s.base, "private")                           # sharing never turned on for this one
        wait_until(lambda: ("close", b, 1000) in relay.events, what="close b")
        time.sleep(0.3)
        assert len(relay.connects) == connects and link.status()[1]["state"] == "off"
        assert all(ch == a or ch == b for _, ch in relay.connects)       # nothing ever went to another channel
        assert all(h[:2] != (5, 50) for c in relay.channels.values() for h in c["history"])
        link.stop()
    finally:
        s.close()


def test_reconnect_resends_the_authoritative_count_with_a_newer_rev():
    s, relay = Setup(), FakeRelay()
    saved = L.BACKOFF_SECONDS
    L.BACKOFF_SECONDS = (0.05,)
    try:
        channel = sharing.set_enabled(s.base, "default", True)["channel"]
        s.counts("default", 3, 9)
        link = started(s, relay)
        wait_until(lambda: history(relay, channel), what="first")
        first_rev = history(relay, channel)[-1][3]
        relay.drop(channel)                                              # Wi-Fi lost
        wait_until(lambda: len(relay.connects) == 2 and len(history(relay, channel)) == 2, what="reconnect")
        assert history(relay, channel)[-1][:2] == (3, 9) and history(relay, channel)[-1][3] > first_rev
        link.stop()
    finally:
        L.BACKOFF_SECONDS = saved
        s.close()


def test_taken_over_or_refused_key_stop_retrying_until_something_changes():
    s, relay = Setup(), FakeRelay()
    saved = L.KEY_RECHECK_SECONDS
    L.KEY_RECHECK_SECONDS = 0.1
    try:
        channel = sharing.set_enabled(s.base, "default", True)["channel"]
        link = started(s, relay)
        wait_until(lambda: link.status()[1]["state"] == "connected", what="connected")
        relay.connect("wss://relay.test", channel, KEY)                  # another PC takes the channel over
        wait_until(lambda: link.status()[1]["state"] == "taken_over", what="taken over")
        connects = len(relay.connects)
        time.sleep(0.4)
        assert len(relay.connects) == connects                           # no fight over the channel
        sharing.set_enabled(s.base, "default", False)
        time.sleep(0.2)
        sharing.set_enabled(s.base, "default", True)                     # off and on again: take it back
        wait_until(lambda: link.status()[1]["state"] == "connected", what="taken back")
        link.stop()

        keys = ["wrong-key-" + "x" * 30]
        link = L.RemoteLink(s.config, connect=relay.connect, key_loader=lambda: keys[0], poll=0.05).start()
        wait_until(lambda: link.status()[1]["state"] == "key_rejected", what="key rejected")
        connects = len(relay.connects)
        time.sleep(0.4)
        assert len(relay.connects) == connects                           # a refused key is not hammered
        assert keys[0] not in json.dumps(link.status()[1])               # never in a status / log line
        keys[0] = KEY                                                    # the right key imported
        wait_until(lambda: link.status()[1]["state"] == "connected", what="new key")
        link.stop()
    finally:
        L.KEY_RECHECK_SECONDS = saved
        s.close()


def test_viewer_links_are_kept_on_reconnect_and_unknown_ones_never_revoked():
    s, relay = Setup(), FakeRelay()
    try:
        channel = sharing.set_enabled(s.base, "default", True)["channel"]
        link_id, token = sharing.add_link(s.base, "default", "OBS")
        link = started(s, relay)
        wait_until(lambda: relay.channel(channel)["links"] == {link_id: P.sha256_hex(token)}, what="links sent")
        link.stop()
        first = relay.channel(channel)["pub"]
        assert sum(m["type"] == "links" for m in first.sent) == 1
        link = started(s, relay)                                         # reconnect: the relay already has them
        wait_until(lambda: link.status()[1]["state"] == "connected", what="connected")
        time.sleep(0.2)
        assert not [m for m in relay.channel(channel)["pub"].sent if m["type"] == "links"]
        relay.channel(channel)["links"]["made-elsewhere"] = "0" * 64     # a link another PC made
        link.stop()
        link = started(s, relay)
        wait_until(lambda: link.status()[1]["warning"], what="warning")
        assert "made-elsewhere" in relay.channel(channel)["links"]       # left untouched
        assert not [m for m in relay.channel(channel)["pub"].sent if m["type"] == "links"]
        link.stop()
        del relay.channel(channel)["links"]["made-elsewhere"]
        link = started(s, relay)
        wait_until(lambda: link.status()[1]["state"] == "connected", what="connected again")
        sharing.revoke_link(s.base, "default", link_id)                  # revoked while connected
        wait_until(lambda: relay.channel(channel)["links"] == {}, what="revoked on the relay")
        link.stop()
    finally:
        s.close()


def test_the_overlay_text_travels_with_the_counts_and_a_wording_change_alone_reaches_viewers():
    s, relay = Setup(), FakeRelay()
    try:
        channel = sharing.set_enabled(s.base, "default", True)["channel"]
        overlay = s.dir / "obs_output" / "chest_counter.txt"
        overlay.parent.mkdir(parents=True)
        overlay.write_text("CHESTS OPENED ≈ 1,250" + NL, encoding="utf-8")
        s.counts("default", 500, 1250)
        link = started(s, relay)
        wait_until(lambda: history(relay, channel) and history(relay, channel)[-1][4] == ("CHESTS OPENED ≈ 1,250",),
                   what="lines")
        before = len(history(relay, channel))
        time.sleep(0.05)
        overlay.write_text("CERTAIN: 500" + NL + "APPROX: 1,250" + NL, encoding="utf-8")    # the Overlay page saved new wording
        wait_until(lambda: history(relay, channel)[-1][4] == ("CERTAIN: 500", "APPROX: 1,250"), what="new wording")
        assert len(history(relay, channel)) == before + 1 and history(relay, channel)[-1][:2] == (500, 1250)
        link.stop()
    finally:
        s.close()


def test_a_running_counter_picks_up_its_profiles_own_wording():
    from types import SimpleNamespace
    s = Setup()
    try:
        profiles.create(s.base, "Streamer B", activate=True)
        args = SimpleNamespace(config=str(s.config), profile="streamer-b")
        cfg = counter.make_config(args)[0]
        written = []
        session = SimpleNamespace(display=cfg["display"], state=counter.fresh_state(), obs_dir=s.dir / "obs_output",
                                  write_obs=lambda: written.append(dict(session.display)), announce=lambda: None)
        watcher = counter.DisplayConfigWatcher(args)
        time.sleep(0.05)
        profiles.set_display(s.base, "streamer-b", {"show": "approx", "approx_text": "CHESTS OPENED ≈ {count}"})
        assert watcher.check(session) is True and written[-1]["approx_text"] == "CHESTS OPENED ≈ {count}"
        time.sleep(0.05)
        sharing.set_enabled(s.base, "streamer-b", True)          # profiles.json changes, the wording does not
        assert watcher.check(session) is False and len(written) == 1
    finally:
        s.close()


# ==================================================================
# the WebSocket client's additions (headers, several subprotocols, refused handshakes)
# ==================================================================

def test_handshake_sends_headers_and_subprotocols_and_reports_the_status():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port, seen = server.getsockname()[1], {}

    def answer():
        conn, _ = server.accept()
        data = b""
        while b"\r\n\r\n" not in data:
            data += conn.recv(4096)
        seen["head"] = data.decode("latin-1")
        conn.sendall(b"HTTP/1.1 401 Unauthorized\r\ncontent-length: 0\r\n\r\n")
        conn.close()

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    try:
        wsmod.WebSocket.connect("127.0.0.1", port, "/v1/publish/x", subprotocol=["fcc.v1", "t.a.b"],
                                headers={"Authorization": "Bearer K", "User-Agent": "UA/1"})
        raise AssertionError("a 401 must not connect")
    except HandshakeRefused as refused:
        assert refused.status == 401 and isinstance(refused, wsmod.WebSocketError)
    thread.join(2)
    server.close()
    head = seen["head"]
    assert "Sec-WebSocket-Protocol: fcc.v1, t.a.b\r\n" in head and "Authorization: Bearer K\r\n" in head
    assert f"Host: 127.0.0.1:{port}\r\n" in head and "User-Agent: UA/1\r\n" in head


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"ok    {t.__name__}")
        except Exception as error:
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {t.__name__}: {error!r}")
    print(f"{len(tests) - failed}/{len(tests)} Remote Sharing checks passed")
    raise SystemExit(1 if failed else 0)
