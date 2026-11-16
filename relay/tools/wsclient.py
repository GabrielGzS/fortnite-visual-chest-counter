"""
A small WebSocket client (RFC 6455) for the relay's tools: TLS with certificate checks, extra headers, subprotocols, text frames,
ping/pong and close codes. Standard library only (Python 3.9+), so the tools run anywhere without installing anything.
`ws://` is accepted only for localhost (testing `wrangler dev`); everything else must be `wss://`.
"""

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import time
from urllib.parse import urlsplit

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
USER_AGENT = "FortniteVisualChestCounter-relay-tools/1"
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


class HandshakeRefused(Exception):
    """The relay answered the upgrade with an HTTP status instead of 101 (e.g. 401 Unauthorized)."""

    def __init__(self, status, body=""):
        self.status, self.body = status, body
        super().__init__(f"the relay refused the connection: HTTP {status} {body.strip()[:80]}")


class Closed(Exception):
    def __init__(self, code=None, reason=""):
        self.code, self.reason = code, reason
        super().__init__(f"connection closed (code {code}{': ' + reason if reason else ''})")


def check_url(url):
    parts = urlsplit(url)
    if parts.scheme not in ("ws", "wss") or not parts.hostname:
        raise ValueError(f"not a WebSocket URL: {url!r} (expected wss://...)")
    if parts.scheme == "ws" and parts.hostname not in LOCAL_HOSTS:
        raise ValueError("ws:// is only allowed for localhost; a relay on the internet must use wss://")
    return parts


class WebSocket:
    def __init__(self, sock):
        self.sock, self.buf, self.closed, self.protocol = sock, bytearray(), False, None

    @classmethod
    def connect(cls, url, headers=None, protocols=(), timeout=10.0):
        parts = check_url(url)
        secure = parts.scheme == "wss"
        raw = socket.create_connection((parts.hostname, parts.port or (443 if secure else 80)), timeout=timeout)
        try:
            sock = ssl.create_default_context().wrap_socket(raw, server_hostname=parts.hostname) if secure else raw
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
            host = parts.hostname + ("" if parts.port is None else f":{parts.port}")
            lines = [f"GET {path} HTTP/1.1", f"Host: {host}", "Upgrade: websocket", "Connection: Upgrade", f"Sec-WebSocket-Key: {key}",
                     "Sec-WebSocket-Version: 13", f"User-Agent: {USER_AGENT}"]
            if protocols:
                lines.append("Sec-WebSocket-Protocol: " + ", ".join(protocols))
            lines += [f"{name}: {value}" for name, value in (headers or {}).items()]
            sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
            ws = cls(sock)
            status, head, body = ws._read_head(timeout)
            if status != 101:
                raise HandshakeRefused(status, body)
            if head.get("sec-websocket-accept") != base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii"):
                raise ConnectionError("the relay's WebSocket handshake answer is wrong")
            ws.protocol = head.get("sec-websocket-protocol")
            return ws
        except BaseException:
            raw.close()
            raise

    def _read_head(self, timeout):
        deadline = time.monotonic() + timeout
        while b"\r\n\r\n" not in self.buf:
            self.sock.settimeout(max(0.05, deadline - time.monotonic()))
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("the relay closed the connection during the handshake")
            self.buf += chunk
            if len(self.buf) > 65536:
                raise ConnectionError("handshake answer too long")
        head, _, rest = bytes(self.buf).partition(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        status = int(lines[0].split(" ")[1])
        headers = {name.strip().lower(): value.strip() for name, _, value in (line.partition(":") for line in lines[1:])}
        self.buf = bytearray(rest)
        return status, headers, rest.decode("utf-8", errors="replace") if status != 101 else ""

    # ---- frames
    def _send_frame(self, opcode, payload):
        header = bytearray([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack("!H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", n)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def send(self, message):
        """A text frame: a str as it is, anything else as JSON."""
        text = message if isinstance(message, str) else json.dumps(message, separators=(",", ":"))
        self._send_frame(1, text.encode("utf-8"))

    def _parse(self):
        b = self.buf
        if len(b) < 2:
            return None
        opcode, length, pos = b[0] & 0x0F, b[1] & 0x7F, 2
        if length == 126:
            if len(b) < 4:
                return None
            length, pos = struct.unpack("!H", bytes(b[2:4]))[0], 4
        elif length == 127:
            if len(b) < 10:
                return None
            length, pos = struct.unpack("!Q", bytes(b[2:10]))[0], 10
        if b[1] & 0x80:
            pos += 4                                     # servers do not mask; tolerate it anyway
        if len(b) < pos + length:
            return None
        payload = bytes(b[pos:pos + length])
        del b[:pos + length]
        return opcode, payload

    def recv(self, timeout=10.0):
        """The next text message. Answers pings. Raises Closed when the connection ends, TimeoutError when nothing came."""
        deadline = time.monotonic() + timeout
        while True:
            frame = self._parse()
            if frame is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("no message from the relay")
                self.sock.settimeout(remaining)
                try:
                    chunk = self.sock.recv(65536)
                except socket.timeout:
                    raise TimeoutError("no message from the relay") from None
                if not chunk:
                    self.closed = True
                    raise Closed(1006, "connection lost")
                self.buf += chunk
                continue
            opcode, payload = frame
            if opcode == 1:
                return payload.decode("utf-8")
            if opcode == 9:
                self._send_frame(10, payload)
            elif opcode == 8:
                code = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else 1005
                self.closed = True
                try:
                    self._send_frame(8, payload[:2])
                except OSError:
                    pass
                raise Closed(code, payload[2:].decode("utf-8", errors="replace"))

    def recv_json(self, timeout=10.0):
        return json.loads(self.recv(timeout))

    def close(self, code=1000):
        if not self.closed:
            self.closed = True
            try:
                self._send_frame(8, struct.pack("!H", code))
            except OSError:
                pass
        try:
            self.sock.close()
        except OSError:
            pass
