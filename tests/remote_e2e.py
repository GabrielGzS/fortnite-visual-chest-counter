"""
Remote Sharing end to end (B3), outside the normal test run: two app folders stand in for PC A and PC B, a real relay runs
locally (`wrangler dev` in a checkout of the reference relay), and the app's real code does everything - profile export on A,
import on B, the publisher, per-profile wording, viewer links made on A still working after the move, the one-publisher rule,
revocation and a profile switch. Prints PASS/FAIL per step; never prints a key or a token.

    python tests/remote_e2e.py RELAY_FOLDER KEY_FILE
        RELAY_FOLDER  the reference relay (with node_modules and a .dev.vars whose setup code matches the key)
        KEY_FILE      a JSON file {"publisher_key": ...} (e.g. tools/test_publisher.py's secrets file for that relay)
"""
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "src"))

import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from fortnite_chest_counter import counter, profiles, settings
from fortnite_chest_counter import profile_transfer as T
from fortnite_chest_counter.obs.websocket import ConnectionClosed, WebSocket
from fortnite_chest_counter.remote import link as L
from fortnite_chest_counter.remote import protocol as P
from fortnite_chest_counter.remote import sharing

URL = "ws://127.0.0.1:8787"
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   ({detail})" if detail else ""), flush=True)


class Creds:
    """One in-memory Credential Manager per PC (never the real one)."""

    def __init__(self):
        self.store = {}

    def load_password(self, target=""):
        return self.store.get(target, "")

    def save_password(self, password, target="", comment="", username=""):
        self.store[target] = password

    def forget_password(self, target=""):
        self.store.pop(target, None)


class PC:
    def __init__(self, name):
        self.name, self.dir, self.creds = name, Path(tempfile.mkdtemp(prefix=f"fcc-{name}-")), Creds()
        self.base = self.dir / "state" / "chest_state.json"
        self.config = self.dir / "config.toml"
        self.config.write_text(f'[state]\npath = "{self.base.as_posix()}"\nobs_dir = "{(self.dir / "obs_output").as_posix()}"\n'
                               f'\n[remote]\nurl = "{URL}"\n', encoding="utf-8")

    def use(self):
        sharing.credentials = self.creds                     # this PC's Credential Manager
        return self

    def counts(self, pid, certain, approx):
        path = profiles.profile_state_path(self.base, pid)
        path.parent.mkdir(parents=True, exist_ok=True)
        state = counter.fresh_state()
        state.update(certain=certain, approximate=approx)
        counter.save_state(path, state)
        self.write_obs()

    def write_obs(self):
        """What the app does after a change: the OBS files of the ACTIVE profile, with its wording (profiles.apply)."""
        cfg = settings.load_config(str(self.config))[0]
        profiles.apply(cfg)
        counter.CounterSession(cfg).write_obs()

    def link(self, key):
        self.use()
        return L.RemoteLink(self.config, key_loader=lambda: key, poll=0.1).start()


def relay_up(folder):
    proc = subprocess.Popen("npx wrangler dev --port 8787 --ip 127.0.0.1", cwd=folder, shell=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            urllib.request.urlopen("http://127.0.0.1:8787/", timeout=1).read()
            return proc
        except OSError:
            time.sleep(0.5)
    raise SystemExit("the relay did not start")


def viewer(channel, link_id, token):
    host, port, path, _ = P.endpoint(URL, "view", channel)
    return WebSocket.connect(host, port, path, subprotocol=[P.PROTOCOL, f"t.{link_id}.{token}"], timeout=5)


def next_of(ws, kind, seconds=8.0, where=None):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            text = ws.recv(max(0.05, deadline - time.monotonic()))
        except ConnectionClosed as closed:
            return {"type": "closed", "code": closed.code}
        if text is None:
            continue
        message = json.loads(text)
        if message.get("type") == kind and (where is None or where(message)):
            return message
    return None


def wait_state(link, state, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and link.status()[1]["state"] != state:
        time.sleep(0.1)
    return link.status()[1]["state"] == state


def main():
    relay_folder, key = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))["publisher_key"]
    proc = relay_up(relay_folder)
    a_link = b_link = None
    try:
        # ---- PC A: a streamer's profile, its own wording, shared, one OBS link
        a = PC("A").use()
        profiles.create(a.base, "Streamer B", activate=True)
        profiles.set_display(a.base, "streamer-b", {"show": "approx", "approx_text": "CHESTS OPENED ≈ {count}"})
        channel = sharing.set_enabled(a.base, "streamer-b", True)["channel"]
        link_id, token = sharing.add_link(a.base, "streamer-b", "OBS on PC B")
        a.counts("streamer-b", 1200, 3456)
        a_link = a.link(key)
        check("A publishes its profile", wait_state(a_link, "connected"))
        obs = viewer(channel, link_id, token)
        m = next_of(obs, "snapshot", where=lambda m: (m["snapshot"] or {}).get("ext"))
        check("the OBS link shows A's wording", m and m["snapshot"]["ext"]["lines"] == ["CHESTS OPENED ≈ 3,456"],
              (m or {}).get("snapshot", {}).get("ext"))
        a_link.stop(timeout=2)
        a_link = None
        package_path = Path(tempfile.mkdtemp()) / f"Streamer B{T.SUFFIX}"
        T.export_profile(a.base, "streamer-b", package_path, "e2e")

        # ---- PC B: import, turn sharing on, publish; the link made on A keeps working
        b = PC("B").use()
        package = T.read_package(package_path)
        entry = T.import_profile(b.base, package, "copy")
        profiles.set_active(b.base, entry["id"])
        check("the import arrives with sharing off", entry["remote"]["enabled"] is False and entry["remote"]["channel"] == channel)
        b.write_obs()
        b_link = b.link(key)
        time.sleep(0.6)
        check("B makes no connection until sharing is turned on", b_link.status()[1]["state"] == "off")
        sharing.set_enabled(b.base, entry["id"], True)
        check("B publishes after sharing is turned on", wait_state(b_link, "connected"))
        b.counts(entry["id"], 1201, 3460)
        m = next_of(obs, "snapshot", where=lambda m: m["snapshot"]["approx"] == 3460)
        check("the OBS link made on A shows B's counts and wording (no new link needed)",
              m and m["snapshot"]["ext"]["lines"] == ["CHESTS OPENED ≈ 3,460"] and m["publisher"] == "online")
        check("B cannot show the old link's address (no secret on B)", sharing.link_token(b.base, entry["id"], link_id) is None)

        # ---- one publisher per channel
        a.use()
        a_link = a.link(key)
        check("A publishing again takes the channel over; B stops instead of fighting", wait_state(b_link, "taken_over"))
        a_link.stop(timeout=2)
        a_link = None
        b.use()
        sharing.set_enabled(b.base, entry["id"], False)
        time.sleep(0.5)
        sharing.set_enabled(b.base, entry["id"], True)
        check("B takes it back after sharing off and on", wait_state(b_link, "connected"))

        # ---- revocation and a profile switch on B
        sharing.revoke_link(b.base, entry["id"], link_id)
        m = next_of(obs, "closed", seconds=10)
        check("revoking on B closes the OBS link at once", m and m["code"] == 4003, m)
        new_id, new_token = sharing.add_link(b.base, entry["id"], "OBS new")
        time.sleep(1.0)
        watch = viewer(channel, new_id, new_token)
        first = next_of(watch, "snapshot")
        check("a new link made on B works", first and first["snapshot"]["approx"] == 3460)
        profiles.set_active(b.base, profiles.DEFAULT_ID)
        b.write_obs()
        off = next_of(watch, "status", where=lambda m: m["publisher"] == "offline")
        check("switching B to a profile without sharing takes the channel offline", off is not None and wait_state(b_link, "off"))
    finally:
        for link in (a_link, b_link):
            if link is not None:
                link.stop(timeout=2)
        subprocess.run(f"taskkill /T /F /PID {proc.pid}", shell=True, capture_output=True)
    print(f"{sum(results)}/{len(results)} end-to-end steps passed")
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
