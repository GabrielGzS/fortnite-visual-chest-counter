"""
Is this relay compatible? Checks a running relay against Remote Sharing protocol v1 (PROTOCOL.md):

    python tools/conformance.py --relay wss://your-relay.example                 (the key from tools/test_publisher.py keys)
    python tools/conformance.py --relay ws://127.0.0.1:8787                       (wrangler dev on this PC)

Every run uses a new random channel, so it never touches a real counter; that channel keeps one test snapshot, which nobody can see
without its links. About 25 short connections: well inside any free plan. The publisher key is read from the test publisher's
private file (or FCC_PUBLISHER_KEY) and never printed. Standard library only. Exit code 0 = every check passed.
"""

import argparse
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_publisher  # noqa: E402
import wsclient  # noqa: E402

PROTOCOL = "fcc.v1"


class Relay:
    def __init__(self, url, key):
        self.url, self.key = url.rstrip("/"), key
        self.channel = secrets.token_urlsafe(18)
        self.tokens = {}

    def publisher(self, key=None, channel=None):
        headers = {} if key is False else {"Authorization": f"Bearer {self.key if key is None else key}"}
        return wsclient.WebSocket.connect(f"{self.url}/v1/publish/{channel or self.channel}", headers=headers, protocols=(PROTOCOL,))

    def viewer(self, link_id, token=None, channel=None):
        token = token or self.tokens[link_id]
        return wsclient.WebSocket.connect(f"{self.url}/v1/view/{channel or self.channel}", protocols=(PROTOCOL, f"t.{link_id}.{token}"))

    def link(self, link_id):
        self.tokens.setdefault(link_id, secrets.token_urlsafe(32))
        return {"id": link_id, "sha256": hashlib.sha256(self.tokens[link_id].encode("ascii")).hexdigest()}


def refused(connect, status):
    try:
        ws = connect()
    except wsclient.HandshakeRefused as error:
        return error.status == status, f"HTTP {error.status}"
    ws.close()
    return False, "accepted"


def closed_with(ws, code, seconds=5.0):
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            ws.recv(max(0.1, deadline - time.monotonic()))
    except wsclient.Closed as closed:
        return closed.code == code, f"closed {closed.code}"
    except TimeoutError:
        return False, "still open"
    return False, "still open"


def next_of(ws, kind, seconds=5.0):
    deadline = time.monotonic() + seconds
    while True:
        message = ws.recv_json(max(0.1, deadline - time.monotonic()))
        if message.get("type") == kind:
            return message


def run(relay):
    results = []

    def check(name, fn):
        try:
            ok, detail = fn()
        except Exception as error:                       # a check that crashes is a failed check
            ok, detail = False, f"{type(error).__name__}: {error}"
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   ({detail})" if detail else ""), flush=True)
        return ok

    rev = int(time.time() * 1000)
    state = {}

    check("1  the overlay page is served", lambda: overlay_page(relay))
    check("2  a publisher without a key is refused (401)", lambda: refused(lambda: relay.publisher(key=False), 401))
    check("3  a publisher with a wrong key is refused (401)", lambda: refused(lambda: relay.publisher(key=secrets.token_urlsafe(32)), 401))

    def hello():
        pub = relay.publisher()
        message = pub.recv_json()
        state["pub"] = pub
        return message.get("type") == "hello" and message.get("protocol") == 1 and message.get("rev") == 0 and message.get("links") == [], json.dumps(message)
    if not check("4  the right key gets hello (protocol 1, empty channel)", hello):
        return results
    pub = state["pub"]

    def first_snapshot():
        pub.send({"type": "links", "active": [relay.link("viewA"), relay.link("viewB")]})
        assert next_of(pub, "ack").get("links") == ["viewA", "viewB"]
        pub.send({"type": "snapshot", "v": 1, "rev": rev, "certain": 7, "approx": 10, "state": "counting"})
        assert next_of(pub, "ack").get("accepted") is True
        viewer = relay.viewer("viewA")
        message = viewer.recv_json()
        state["viewer"] = viewer
        return message.get("type") == "snapshot" and message["snapshot"]["approx"] == 10 and message["publisher"] == "online", json.dumps(message)
    check("5  a viewer gets the stored snapshot at once", first_snapshot)
    viewer = state.get("viewer")

    check("6  a forged token is refused (401)", lambda: refused(lambda: relay.viewer("viewA", token=secrets.token_urlsafe(32)), 401))
    check("7  a link of another channel is refused (401)", lambda: refused(lambda: relay.viewer("viewA", channel=secrets.token_urlsafe(18)), 401))

    def live():
        pub.send({"type": "snapshot", "v": 1, "rev": rev + 1, "certain": 7, "approx": 11})
        accepted = next_of(pub, "ack").get("accepted")
        message = next_of(viewer, "snapshot")
        return accepted is True and message["snapshot"]["approx"] == 11, ""
    check("8  a new snapshot reaches the viewer", live)

    def stale():
        pub.send({"type": "snapshot", "v": 1, "rev": rev, "certain": 9, "approx": 99})
        ack = next_of(pub, "ack")
        try:
            pushed = next_of(viewer, "snapshot", 1.5)
            return False, f"the viewer got {pushed}"
        except TimeoutError:
            return ack.get("accepted") is False, ""
    check("9  an older revision is ignored", stale)

    def reset():
        pub.send({"type": "snapshot", "v": 1, "rev": rev + 5, "certain": 0, "approx": 5})
        accepted = next_of(pub, "ack").get("accepted")
        return accepted is True and next_of(viewer, "snapshot")["snapshot"]["approx"] == 5, ""
    check("10 lower totals with a newer revision are accepted (Reset)", reset)

    def ping():
        viewer.send('{"type":"ping"}')
        return next_of(viewer, "pong").get("type") == "pong", ""
    check("11 a viewer's ping gets pong", ping)

    def viewer_cannot_publish():
        other = relay.viewer("viewB")
        other.recv_json()
        other.send({"type": "snapshot", "rev": rev + 99, "certain": 0, "approx": 12345})
        ok, detail = closed_with(other, 1008)
        fresh = relay.viewer("viewB")
        approx = fresh.recv_json()["snapshot"]["approx"]
        fresh.close()
        return ok and approx == 5, f"{detail}, stored APPROX {approx}"
    check("12 a viewer cannot publish (closed 1008, nothing stored)", viewer_cannot_publish)

    def revoke():
        pub.send({"type": "links", "active": [relay.link("viewB")]})
        ok, detail = closed_with(viewer, 4003)
        again_ok, again = refused(lambda: relay.viewer("viewA"), 401)
        return ok and again_ok, f"{detail}; reconnect {again}"
    check("13 revoking closes an open viewer (4003) and refuses it after", revoke)

    def oversized():
        other = relay.publisher()
        other.recv_json()
        ok_first, detail_first = closed_with(pub, 4001, 5.0)         # the new publisher took over
        other.send("x" * 5000)
        ok, detail = closed_with(other, 1009)
        return ok_first and ok, f"first publisher {detail_first}; oversized {detail}"
    check("14 a second publisher takes over (4001); an oversized frame closes (1009)", oversized)

    def offline():
        last = relay.publisher()
        last.recv_json()
        watcher = relay.viewer("viewB")
        watcher.recv_json()
        last.close()
        message = next_of(watcher, "status", 10)
        watcher.close()
        return message.get("publisher") == "offline", json.dumps(message)
    check("15 viewers hear when the publisher goes away", offline)
    return results


def overlay_page(relay):
    parts = urlsplit(relay.url)
    page = f"{'https' if parts.scheme == 'wss' else 'http'}://{parts.netloc}/o/"
    with urllib.request.urlopen(urllib.request.Request(page, headers={"User-Agent": wsclient.USER_AGENT}), timeout=10) as answer:
        body, csp = answer.read().decode("utf-8", errors="replace"), answer.headers.get("Content-Security-Policy") or ""
    return answer.status == 200 and "overlay.js" in body and "connect-src 'self'" in csp, f"CSP: {csp[:60]}"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check a relay against Remote Sharing protocol v1.")
    parser.add_argument("--relay", required=True, help="wss://... (ws:// only for localhost)")
    parser.add_argument("--secrets", type=Path, default=test_publisher.default_secrets(), help="the test publisher's private key file")
    args = parser.parse_args(argv)
    wsclient.check_url(args.relay)
    key = os.environ.get("FCC_PUBLISHER_KEY") or (test_publisher.load(args.secrets) or {}).get("publisher_key")
    if not key:
        sys.exit("No publisher key: run tools/test_publisher.py keys first (or set FCC_PUBLISHER_KEY).")
    print(f"Checking {urlsplit(args.relay).netloc} against protocol v1 ...")
    results = run(Relay(args.relay, key))
    passed = sum(results)
    print(f"{passed}/{len(results)} checks passed" + ("" if passed == len(results) == 15 else "  - NOT compatible"))
    sys.exit(0 if passed == len(results) == 15 else 1)


if __name__ == "__main__":
    main()
