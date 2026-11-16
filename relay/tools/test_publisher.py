"""
A disposable test publisher for a Remote Sharing relay (protocol v1, PROTOCOL.md): it plays the app's part with simulated counts, so a
relay can be tried end to end - publisher -> relay -> an OBS Browser Source somewhere else - before the app itself publishes anything.

    python tools/test_publisher.py keys [--rotate]                 make (or replace) the publisher key; prints the SETUP CODE for the relay
    python tools/test_publisher.py link [--label OBS]              make a viewer link; prints the overlay URL once --relay is known
    python tools/test_publisher.py run --relay wss://...           publish simulated counts until Ctrl+C (sends the active links first)
    python tools/test_publisher.py revoke LINK_ID --relay wss://... revoke one viewer link at once (its open overlays close)
    python tools/test_publisher.py show                            the channel, links and setup code (never the key)

Secrets live in a private file outside any repository (--secrets PATH to choose; default under %LOCALAPPDATA% or ~). The publisher key
is never printed, sent anywhere but the relay you name, or written into this folder. Standard library only.
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import random
import secrets
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wsclient  # noqa: E402

PROTOCOL = "fcc.v1"
BACKOFF = (1, 2, 5, 10, 20, 30)


def default_secrets():
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "FortniteVisualChestCounter-relay-test" / "secrets.json"


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def setup_code(key):
    return hashlib.sha256(key.encode("ascii")).hexdigest()


def token(data, link_id):
    digest = hmac.new(data["link_secret"].encode("ascii"), f"{data['channel']}.{link_id}".encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def overlay_url(relay, data, link_id, options="show=both"):
    parts = urlsplit(relay)
    scheme = "https" if parts.scheme == "wss" else "http"
    return f"{scheme}://{parts.netloc}/o/#{data['channel']}.{link_id}.{token(data, link_id)}" + (f"&{options}" if options else "")


def active_links(data):
    return [{"id": link["id"], "sha256": hashlib.sha256(token(data, link["id"]).encode("ascii")).hexdigest()}
            for link in data["links"] if not link.get("revoked")]


def need(path):
    data = load(path)
    if data is None:
        sys.exit(f"No test keys yet. Run:  python {Path(__file__).name} keys")
    return data


# ---------------------------------------------------------------------- commands

def cmd_keys(args):
    data = load(args.secrets)
    if data is not None and not args.rotate:
        print(f"Keys already exist ({args.secrets}). Setup code:\n\n  {setup_code(data['publisher_key'])}\n\n(--rotate makes a new key.)")
        return
    data = {**(data or {}), "publisher_key": secrets.token_urlsafe(32)}
    data.setdefault("link_secret", secrets.token_urlsafe(32))
    data.setdefault("channel", secrets.token_urlsafe(18))
    data.setdefault("links", [])
    save(args.secrets, data)
    print(f"Publisher key stored privately in {args.secrets} (never shown, never put in the repository).\n")
    print("SETUP CODE - paste this as PUBLISHER_KEY_SHA256 when you deploy the relay (it is the key's SHA-256, not the key):\n")
    print(f"  {setup_code(data['publisher_key'])}\n")
    if args.rotate:
        print("This replaced the old key: set the new setup code on the relay (or the publisher is refused).")


def cmd_link(args):
    data = need(args.secrets)
    link_id = secrets.token_urlsafe(6)
    data["links"].append({"id": link_id, "label": args.label, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    save(args.secrets, data)
    print(f"Viewer link {link_id} ({args.label}) made. It becomes active the next time `run` connects.")
    if args.relay:
        print(f"\nOBS Browser Source URL:\n\n  {overlay_url(args.relay, data, link_id)}\n")


def cmd_show(args):
    data = need(args.secrets)
    print(f"Secrets file : {args.secrets}\nSetup code   : {setup_code(data['publisher_key'])}\nChannel      : {data['channel']}")
    for link in data["links"]:
        state = "revoked" if link.get("revoked") else "active"
        print(f"Link {link['id']:<10} {link.get('label') or '':<12} {state}" + (f"   {overlay_url(args.relay, data, link['id'])}" if args.relay and state == "active" else ""))


def connect(relay, data):
    url = relay.rstrip("/") + f"/v1/publish/{data['channel']}"
    ws = wsclient.WebSocket.connect(url, headers={"Authorization": f"Bearer {data['publisher_key']}"}, protocols=(PROTOCOL,))
    hello = ws.recv_json(10)
    if hello.get("type") != "hello" or hello.get("protocol") != 1:
        ws.close()
        raise ConnectionError(f"not a protocol v1 relay (it said {hello!r})")
    ws.send({"type": "links", "active": active_links(data)})
    return ws, hello


def cmd_revoke(args):
    data = need(args.secrets)
    link = next((l for l in data["links"] if l["id"] == args.link_id), None)
    if link is None:
        sys.exit(f"No link {args.link_id}.")
    link["revoked"] = True
    save(args.secrets, data)
    ws, _ = connect(args.relay, data)
    answer = ws.recv_json(10)
    ws.close()
    print(f"Link {args.link_id} revoked: open overlays with it were closed. Active links now: {answer.get('links')}")


def cmd_run(args):
    data = need(args.secrets)
    certain, approx = args.start_certain, args.start
    last_rev, attempt = 0, 0
    print(f"Publishing simulated counts for channel {data['channel']} to {urlsplit(args.relay).netloc}. Ctrl+C stops.")
    for link in data["links"]:
        if not link.get("revoked"):
            print(f"  overlay {link['id']}: {overlay_url(args.relay, data, link['id'])}")
    try:
        while True:
            try:
                ws, hello = connect(args.relay, data)
                attempt = 0
                last_rev = max(last_rev, hello.get("rev") or 0)
                print(f"connected; relay holds rev {hello.get('rev')}, {hello.get('viewers')} viewer(s)")
                ws.recv_json(10)                                  # the links ack
                next_send = 0.0
                while True:
                    now = time.monotonic()
                    if now >= next_send:
                        if random.random() < 0.7:
                            approx += 1
                            certain += random.random() < 0.6
                        last_rev = max(int(time.time() * 1000), last_rev + 1)
                        ws.send({"type": "snapshot", "v": 1, "rev": last_rev, "certain": certain, "approx": approx,
                                 "state": "counting", "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
                        next_send = now + args.interval
                    try:
                        message = ws.recv_json(min(1.0, max(0.05, next_send - time.monotonic())))
                    except TimeoutError:
                        continue
                    if message.get("type") == "viewers":
                        print(f"  {message.get('n')} viewer(s) connected")
                    elif message.get("type") == "ack" and "rev" in message:
                        print(f"  rev {message['rev']}: CERTAIN {certain}  APPROX {approx}" + ("" if message.get("accepted") else "  (relay kept a newer one)"))
                    elif message.get("type") == "error":
                        print(f"  relay error: {message.get('code')}")
            except wsclient.Closed as closed:
                if closed.code == 4001:
                    print("Another publisher took over this channel; stopping (by design, no reconnect).")
                    return
                print(f"disconnected ({closed}); reconnecting")
            except (OSError, ConnectionError, TimeoutError, wsclient.HandshakeRefused) as error:
                if isinstance(error, wsclient.HandshakeRefused) and error.status == 401:
                    sys.exit("The relay refused the publisher key (401): set this setup code on the relay:\n  " + setup_code(data["publisher_key"]))
                print(f"cannot reach the relay ({error}); retrying")
            delay = BACKOFF[min(attempt, len(BACKOFF) - 1)]
            attempt += 1
            time.sleep(delay + random.random() * delay * 0.3)
    except KeyboardInterrupt:
        print("\nStopped. The relay keeps the last count; overlays show it as offline.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--secrets", type=Path, default=default_secrets(), help="private file for the test keys (default: %(default)s)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("keys", help="make the publisher key and print the setup code")
    p.add_argument("--rotate", action="store_true", help="replace an existing key")
    p = sub.add_parser("link", help="make a viewer link")
    p.add_argument("--label", default="OBS")
    p.add_argument("--relay", help="the relay's wss:// URL, to print the overlay URL")
    p = sub.add_parser("show", help="what is stored (never the key)")
    p.add_argument("--relay")
    p = sub.add_parser("run", help="publish simulated counts")
    p.add_argument("--relay", required=True)
    p.add_argument("--interval", type=float, default=5.0, help="seconds between snapshots (default 5)")
    p.add_argument("--start", type=int, default=1000, help="starting APPROX (default 1000)")
    p.add_argument("--start-certain", type=int, default=400)
    p = sub.add_parser("revoke", help="revoke a viewer link at once")
    p.add_argument("link_id")
    p.add_argument("--relay", required=True)
    args = parser.parse_args(argv)
    for name in ("relay",):
        if getattr(args, name, None):
            wsclient.check_url(getattr(args, name))
    {"keys": cmd_keys, "link": cmd_link, "show": cmd_show, "run": cmd_run, "revoke": cmd_revoke}[args.command](args)


if __name__ == "__main__":
    main()
