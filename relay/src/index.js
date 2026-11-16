// Fortnite Visual Chest Counter - reference relay for Remote Sharing, protocol v1 (PROTOCOL.md).
//
// You deploy your own copy; nobody else's app or server is involved. One Durable Object per channel (one per shared profile)
// holds that counter's latest snapshot and its active viewer links. The publisher (your app) proves itself with the key whose
// SHA-256 you set as PUBLISHER_KEY_SHA256 when deploying; viewers are read-only and present a link token, checked against the
// channel's active links, revocable at once. WebSocket Hibernation keeps an idle channel free of duration charges.
import { DurableObject } from "cloudflare:workers";

const PROTOCOL = "fcc.v1";
const CHANNEL_RE = /^[A-Za-z0-9_-]{16,64}$/;
const LINK_ID_RE = /^[A-Za-z0-9_-]{4,32}$/;
const TOKEN_RE = /^[A-Za-z0-9_-]{16,128}$/;
const HEX64_RE = /^[0-9a-f]{64}$/;
const MAX_PUBLISHER_MESSAGE = 4096;
const MAX_LINKS = 16;
const PING = '{"type":"ping"}';
const PONG = '{"type":"pong"}';
const SNAPSHOT_KEYS = ["v", "rev", "epoch", "at", "certain", "approx", "types", "state", "last", "label", "ext"];
const OPEN = 1;

const encoder = new TextEncoder();

async function sha256hex(value) {
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(value));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function sameHex(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  return crypto.subtle.timingSafeEqual(encoder.encode(a), encoder.encode(b));
}

function text(status, body) {
  return new Response(body, { status, headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" } });
}

function offeredProtocols(request) {
  return (request.headers.get("Sec-WebSocket-Protocol") || "").split(",").map((p) => p.trim()).filter(Boolean);
}

function isCount(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const route = url.pathname.match(/^\/v1\/(publish|view)\/([^/]+)$/);
    if (!route) {
      if (url.pathname === "/") return text(200, "Fortnite Visual Chest Counter relay (protocol v1). Overlay: /o/#<your overlay link>\n");
      return text(404, "Not found\n");
    }
    const [, role, channel] = route;
    if (!CHANNEL_RE.test(channel)) return text(404, "Not found\n");
    if ((request.headers.get("Upgrade") || "").toLowerCase() !== "websocket") return text(426, "A WebSocket is expected here.\n");
    if (!offeredProtocols(request).includes(PROTOCOL)) return text(400, `The ${PROTOCOL} subprotocol is required.\n`);
    if (role === "publish") {
      const auth = request.headers.get("Authorization") || "";
      const key = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
      const expected = String(env.PUBLISHER_KEY_SHA256 || "").trim().toLowerCase();
      if (!key || !HEX64_RE.test(expected) || !sameHex(await sha256hex(key), expected)) return text(401, "Unauthorized\n");
    }
    return env.CHANNEL.get(env.CHANNEL.idFromName(channel)).fetch(request);
  },
};

export class Channel extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair(PING, PONG));    // answered without waking the object
  }

  maxViewers() {
    const n = Number.parseInt(this.env.MAX_VIEWERS || "50", 10);
    return Number.isSafeInteger(n) && n > 0 ? n : 50;
  }

  open(tag, except) {
    return this.ctx.getWebSockets(tag).filter((ws) => ws !== except && ws.readyState === OPEN);
  }

  async fetch(request) {
    const role = new URL(request.url).pathname.split("/")[2];
    return role === "publish" ? this.acceptPublisher() : this.acceptViewer(request);
  }

  async acceptViewer(request) {
    const offered = offeredProtocols(request).find((p) => p.startsWith("t.")) || "";
    const parts = offered.split(".");
    const links = (await this.ctx.storage.get("links")) || {};
    if (parts.length !== 3 || !LINK_ID_RE.test(parts[1]) || !TOKEN_RE.test(parts[2]) || !links[parts[1]]
        || !sameHex(await sha256hex(parts[2]), links[parts[1]])) {
      return text(401, "Unauthorized\n");
    }
    if (this.open("view").length >= this.maxViewers()) return text(429, "Too many viewers on this channel.\n");
    const pair = new WebSocketPair();
    this.ctx.acceptWebSocket(pair[1], ["view", `link:${parts[1]}`]);
    pair[1].send(JSON.stringify(await this.viewerSnapshot()));
    this.tellViewerCount();
    return new Response(null, { status: 101, webSocket: pair[0], headers: { "Sec-WebSocket-Protocol": PROTOCOL } });
  }

  async acceptPublisher() {
    for (const old of this.ctx.getWebSockets("pub")) {
      try { old.close(4001, "replaced by a newer publisher"); } catch {}
    }
    const pair = new WebSocketPair();
    this.ctx.acceptWebSocket(pair[1], ["pub"]);
    const links = (await this.ctx.storage.get("links")) || {};
    const snapshot = await this.ctx.storage.get("snapshot");
    const since = Date.now();
    await this.ctx.storage.put("presence_since", since);
    pair[1].send(JSON.stringify({ type: "hello", protocol: 1, rev: snapshot ? snapshot.rev : 0, viewers: this.open("view").length,
                                  links: Object.keys(links) }));
    this.broadcast({ type: "status", publisher: "online", since });
    return new Response(null, { status: 101, webSocket: pair[0], headers: { "Sec-WebSocket-Protocol": PROTOCOL } });
  }

  async viewerSnapshot() {
    const snapshot = (await this.ctx.storage.get("snapshot")) || null;
    const since = (await this.ctx.storage.get("presence_since")) || null;
    return { type: "snapshot", snapshot, publisher: this.open("pub").length ? "online" : "offline", since };
  }

  broadcast(message) {
    const data = JSON.stringify(message);
    for (const ws of this.open("view")) {
      try { ws.send(data); } catch {}
    }
  }

  tellViewerCount(except) {
    const data = JSON.stringify({ type: "viewers", n: this.open("view", except).length });
    for (const ws of this.open("pub")) {
      try { ws.send(data); } catch {}
    }
  }

  reply(ws, message) {
    try { ws.send(JSON.stringify(message)); } catch {}
  }

  async webSocketMessage(ws, message) {
    if (!this.ctx.getTags(ws).includes("pub")) {        // a viewer's exact ping never gets here (auto-response)
      try { ws.close(1008, "viewers may only ping"); } catch {}
      return;
    }
    if (typeof message !== "string" || message.length > MAX_PUBLISHER_MESSAGE) {
      try { ws.close(1009, "message too large"); } catch {}
      return;
    }
    let msg;
    try { msg = JSON.parse(message); } catch { return this.reply(ws, { type: "error", code: "bad_json" }); }
    if (!msg || typeof msg !== "object" || Array.isArray(msg)) return this.reply(ws, { type: "error", code: "bad_message" });
    if (msg.type === "snapshot") return this.onSnapshot(ws, msg);
    if (msg.type === "links") return this.onLinks(ws, msg);
    if (msg.type === "ping") return this.reply(ws, { type: "pong" });
    return this.reply(ws, { type: "error", code: "unknown_type" });
  }

  async onSnapshot(ws, msg) {
    if (!isCount(msg.rev) || !isCount(msg.certain) || !isCount(msg.approx) || msg.approx < msg.certain) {
      return this.reply(ws, { type: "error", code: "bad_snapshot" });
    }
    const stored = await this.ctx.storage.get("snapshot");
    if (stored && msg.rev <= stored.rev) return this.reply(ws, { type: "ack", rev: stored.rev, accepted: false });
    const snapshot = {};
    for (const key of SNAPSHOT_KEYS) if (msg[key] !== undefined) snapshot[key] = msg[key];
    if (typeof snapshot.label === "string") snapshot.label = snapshot.label.slice(0, 40);
    else delete snapshot.label;
    await this.ctx.storage.put("snapshot", snapshot);
    const since = (await this.ctx.storage.get("presence_since")) || null;
    this.broadcast({ type: "snapshot", snapshot, publisher: "online", since });
    this.reply(ws, { type: "ack", rev: snapshot.rev, accepted: true });
  }

  async onLinks(ws, msg) {
    if (!Array.isArray(msg.active) || msg.active.length > MAX_LINKS) return this.reply(ws, { type: "error", code: "bad_links" });
    const next = {};
    for (const link of msg.active) {
      if (!link || typeof link !== "object" || !LINK_ID_RE.test(link.id) || !HEX64_RE.test(link.sha256)) {
        return this.reply(ws, { type: "error", code: "bad_links" });
      }
      next[link.id] = link.sha256;
    }
    const before = (await this.ctx.storage.get("links")) || {};
    await this.ctx.storage.put("links", next);
    for (const id of Object.keys(before)) {
      if (next[id] !== before[id]) {
        for (const viewer of this.ctx.getWebSockets(`link:${id}`)) {
          try { viewer.close(4003, "link revoked"); } catch {}
        }
      }
    }
    this.reply(ws, { type: "ack", links: Object.keys(next) });
  }

  async webSocketClose(ws, code, reason) {
    try { ws.close(code, reason); } catch {}                 // completes the closing handshake (reserved codes cannot be echoed)
    await this.gone(ws);
  }

  async webSocketError(ws) {
    await this.gone(ws);
  }

  async gone(ws) {
    if (this.ctx.getTags(ws).includes("pub")) {
      if (!this.open("pub", ws).length) {
        const since = Date.now();
        await this.ctx.storage.put("presence_since", since);
        this.broadcast({ type: "status", publisher: "offline", since });
      }
    } else {
      this.tellViewerCount(ws);
    }
  }
}
