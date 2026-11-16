# Remote Sharing protocol v1

Fortnite Visual Chest Counter can publish its counter to a relay **you** run. The app knows only this protocol and a `wss://`
URL you type in; it contains no relay address, account or key of anyone else. Any server that implements this document is a
compatible relay. `tools/conformance.py` checks one (`python tools/conformance.py --help`).

This folder's Cloudflare Worker is one implementation (see README.md). It is a reference, not a service: every user deploys their own copy.

## Roles

| Role | Who | May |
| --- | --- | --- |
| Publisher | The app, on the PC that counts | publish snapshots and the list of active viewer links of a channel |
| Viewer | An OBS Browser Source, a browser, any client | read one channel's snapshots; send `ping`; nothing else |

A **channel** is one counter (in the app: one shared profile). Its id is random, 16-64 characters `[A-Za-z0-9_-]`. Nothing on a
channel is ever visible on another.

## Credentials

- **Publisher key**: a random secret (at least 32 bytes, URL-safe) that only the publisher holds. The relay stores only its
  SHA-256, lowercase hex: the **setup code**. A leaked setup code does not let anyone publish.
- **Viewer link**: `<channel>.<link id>.<token>`. The link id is 4-32 characters `[A-Za-z0-9_-]`, the token 16-128. The publisher
  tells the relay which links are active by sending each token's SHA-256; the relay never sees a token until a viewer presents it.
  Viewer links are read-only and should be treated as public.

## Endpoints

All WebSockets use the subprotocol `fcc.v1`; the relay answers with it.

| Request | Check | Refusal |
| --- | --- | --- |
| `GET /o/` | none: a static overlay page that holds no data | |
| `wss://<relay>/v1/publish/<channel>` with `Authorization: Bearer <publisher key>` | SHA-256(key) equals the setup code | `401` before the upgrade |
| `wss://<relay>/v1/view/<channel>` with subprotocols `fcc.v1, t.<link id>.<token>` | the link id is active on that channel and SHA-256(token) matches | `401`; `429` when the channel's viewer cap is reached |

A publisher should send a descriptive `User-Agent` (some hosts refuse default library agents). A relay must be served over TLS
(`wss://`) except on `localhost` for testing.

## Messages (JSON text frames)

Publisher -> relay

| `type` | Fields | Relay does |
| --- | --- | --- |
| `snapshot` | `rev` (integer >= 0, must increase), `certain`, `approx` (integers, `approx >= certain`), optional `v`, `epoch`, `at`, `types`, `state`, `last`, `label` (<= 40 characters shown), `ext` | stores it only if `rev` is higher than the stored one, sends it to every viewer, answers `ack` |
| `links` | `active`: up to 16 `{"id": <link id>, "sha256": <hex>}` | replaces the channel's active links; closes every connected viewer whose link left the list (close code `4003`), answers `ack` |
| `ping` | | answers `pong` |

A frame larger than 4,096 bytes closes the connection (`1009`). An unknown or malformed message gets `{"type":"error","code":…}`.

Relay -> publisher

| `type` | Fields | When |
| --- | --- | --- |
| `hello` | `protocol: 1`, `rev` (the stored snapshot's, 0 if none), `viewers`, `links` (active ids) | right after connecting; send nothing before it |
| `ack` | `rev` and `accepted` (snapshot), or `links` | after each message |
| `viewers` | `n` | when a viewer connects or leaves |
| `error` | `code` | a message was refused |

Relay -> viewer

| `type` | Fields | When |
| --- | --- | --- |
| `snapshot` | `snapshot` (the stored one, or `null`), `publisher` (`online`/`offline`), `since` (ms) | right after connecting, then on every accepted snapshot |
| `status` | `publisher`, `since` | the publisher connected or went away |
| `pong` | | answer to `{"type":"ping"}` |

Viewer -> relay: only the exact text `{"type":"ping"}`. Anything else closes the viewer (`1008`).

## Rules

1. **Full snapshots only.** A relay never adds to a count; a lost or repeated snapshot changes nothing by itself.
2. **Revisions.** The publisher uses `rev = max(unix milliseconds, last sent + 1, hello.rev + 1)`. A lower total after a Reset carries a
   newer `rev` and is accepted.
3. **One publisher per channel.** A new publisher connection closes the previous one with `4001`; that publisher must not reconnect by itself.
4. **Revocation is immediate.** Removing a link from `links` closes its connected viewers (`4003`) and refuses it afterwards (`401`).
5. **Heartbeats.** Both sides send `{"type":"ping"}` every 30 s and reconnect after 75 s of silence, with backoff 1, 2, 5, 10, 20, then 30 s, plus jitter.
6. **No commands.** Nothing a relay sends can make the publisher do anything but show a status.

## Close codes

| Code | Meaning |
| --- | --- |
| 1008 | a viewer sent something other than a ping |
| 1009 | a frame was too large |
| 4001 | a newer publisher took over this channel |
| 4003 | this viewer's link was revoked |
