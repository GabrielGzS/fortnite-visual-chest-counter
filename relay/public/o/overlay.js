// Fortnite Visual Chest Counter remote overlay (protocol v1, PROTOCOL.md). Read-only: it shows one channel's counter.
// The link lives in the URL fragment (#<channel>.<link id>.<token>&option=value...), which browsers never send to a server.
// Options: show=both|approx|certain   align=left|center|right   offline=show|dim|hide   label=0|1
(() => {
  "use strict";
  const PROTOCOL = "fcc.v1";
  const DELAYS = [1, 2, 5, 10, 20, 30];
  const byId = (id) => document.getElementById(id);
  const [credential, ...rest] = decodeURIComponent(location.hash.slice(1)).split("&");
  const options = {};
  for (const pair of rest) {
    const [key, value] = pair.split("=");
    if (key && value !== undefined) options[key] = value;
  }
  const pick = (value, allowed, fallback) => (allowed.includes(value) ? value : fallback);
  document.body.dataset.show = pick(options.show, ["both", "approx", "certain"], "both");
  document.body.dataset.align = pick(options.align, ["left", "center", "right"], "left");
  document.body.dataset.offline = pick(options.offline, ["show", "dim", "hide"], "show");
  const showLabel = options.label === "1";

  function setStatus(state, words) {
    document.body.dataset.state = state;
    byId("status").textContent = words;
  }

  const parts = (credential || "").split(".");
  if (parts.length !== 3 || !/^[A-Za-z0-9_-]{16,64}$/.test(parts[0]) || !/^[A-Za-z0-9_-]{4,32}$/.test(parts[1])
      || !/^[A-Za-z0-9_-]{16,128}$/.test(parts[2])) {
    setStatus("broken", "This overlay link is incomplete. Copy it again from the app.");
    return;
  }
  const [channel, linkId, token] = parts;
  const number = (n) => (Number.isSafeInteger(n) && n >= 0 ? n.toLocaleString("en-US") : "–");

  function render(message) {
    const snapshot = message.snapshot;
    if (snapshot && typeof snapshot === "object") {
      byId("certain").textContent = number(snapshot.certain);
      byId("approx").textContent = number(snapshot.approx);
      byId("label").textContent = showLabel && typeof snapshot.label === "string" ? snapshot.label.slice(0, 40) : "";
    }
    presence(message.publisher);
  }

  function presence(publisher) {
    if (publisher === "online") setStatus("live", "");
    else setStatus("offline", "Counter offline - showing the last count");
  }

  let socket = null;
  let attempt = 0;
  let heard = 0;

  function connect() {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    try {
      socket = new WebSocket(`${scheme}://${location.host}/v1/view/${channel}`, [PROTOCOL, `t.${linkId}.${token}`]);
    } catch {
      retry();
      return;
    }
    socket.onopen = () => { attempt = 0; heard = Date.now(); };
    socket.onmessage = (event) => {
      heard = Date.now();
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      if (message && message.type === "snapshot") render(message);
      else if (message && message.type === "status") presence(message.publisher);
    };
    socket.onclose = (event) => {
      socket = null;
      if (event.code === 4003) {
        setStatus("revoked", "This overlay link was revoked. Ask for a new one.");
        return;
      }
      if (document.body.dataset.state !== "offline") setStatus("reconnecting", "Reconnecting…");
      retry();
    };
    socket.onerror = () => {};
  }

  function retry() {
    const base = DELAYS[Math.min(attempt, DELAYS.length - 1)];
    attempt += 1;
    setTimeout(connect, (base + Math.random() * base * 0.3) * 1000);
  }

  setInterval(() => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      if (Date.now() - heard > 75000) socket.close(4000, "silent");
      else socket.send('{"type":"ping"}');
    }
  }, 30000);
  connect();
})();
