# Remote Sharing relay (reference implementation)

Fortnite Visual Chest Counter can send its counter to **a relay you own**, so an OBS Browser Source or a browser anywhere can show it.
The app contains no relay, address or account of anyone else: you choose where your counts go. Any server that speaks
[protocol v1](PROTOCOL.md) works; `tools/conformance.py` tells you whether one does.

This folder is one such relay, for Cloudflare's free Workers plan. Every user deploys their **own** copy into their **own** account.
Nothing here is a service run by the app's developer.

```
your PC (the counter) --wss--> your relay <--wss-- OBS Browser Source / browser, anywhere (read-only)
```

What it is: one Worker, one SQLite-backed Durable Object per shared counter, and a static overlay page at `/o/`. Your home address is
never shown to viewers: both sides only talk to the relay, and nothing connects to your PC.

## Cloudflare quick start (free)

You need a Cloudflare account on the **Workers Free** plan (no card, no domain) and a GitHub or GitLab account for the Deploy button.
Deploying does not need Node.js on your PC.

1. **Make your keys.** Until the app has its Remote Sharing tab, the test publisher plays its part:
   `python tools/test_publisher.py keys`. It stores the publisher key in a private file outside this folder and prints a
   **setup code**: the key's SHA-256. The setup code goes to the relay; the key itself never leaves your PC.
2. **Deploy.** [![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/GabrielGzS/fortnite-visual-chest-counter/tree/b0-relay/relay)
   Cloudflare asks you to sign in, connect your GitHub/GitLab account (it creates a copy of this folder in **your** account; allow
   it only that repository), name the Worker (keep `live`: it must match `wrangler.jsonc`), and paste your setup code into
   **PUBLISHER_KEY_SHA256**. Then it builds and deploys on Cloudflare's side.
3. **Your relay address** is `https://live.<your-subdomain>.workers.dev`; the app and the tools use `wss://live.<your-subdomain>.workers.dev`.
   Your `workers.dev` subdomain is part of every overlay link: choose a neutral one, not your name.
4. **Check it:** `python tools/conformance.py --relay wss://live.<your-subdomain>.workers.dev` should say `15/15 checks passed`.
5. **A viewer link:** `python tools/test_publisher.py link --label OBS --relay wss://…` prints an overlay URL. In OBS: Sources > + >
   Browser > paste it, size 600 x 150. Keep it out of public chat; anyone with it can watch this counter (read-only).
6. **Publish:** `python tools/test_publisher.py run --relay wss://…` sends simulated counts until Ctrl+C. The overlay follows within a second.

Overlay options go after the link, in the same `#…` part: `&show=both|approx|certain`, `&align=left|center|right`,
`&offline=show|dim|hide`, `&label=1`. Fonts and colours: OBS's Custom CSS field, with the classes in `public/o/overlay.css`.

### What it costs

Nothing on Workers Free. Requests are tiny: a WebSocket connection is one request, and everyone's 30-second pings are answered
without waking the channel's Durable Object. The figure to watch is Durable Object **duration** (free: 13,000 GB-s a day): the
object counts 128 MB for every second it is awake, and it sleeps a few seconds after the last snapshot. Snapshots every few
seconds (the test publisher sends one every 5 s) keep it awake: about 450 GB-s an hour, so a day's free allowance covers more than
24 hours of nonstop publishing; real play, with a snapshot only when a count changes, uses less. Over a limit, Cloudflare refuses
requests until 00:00 UTC; the Free plan does not bill. Keep the account on Workers Free and do not add a payment method for this.

## Without the Deploy button

With Node.js: `npm install`, `npx wrangler login`, `npx wrangler secret put PUBLISHER_KEY_SHA256` (paste the setup code), `npx wrangler deploy`.
To try it on this PC first: copy `.dev.vars.example` to `.dev.vars`, put your setup code in it, run `npx wrangler dev`, and use `ws://127.0.0.1:8787`.

## Revoke, rotate, remove

- **Revoke one viewer link:** `python tools/test_publisher.py revoke <link id> --relay wss://…` - open overlays with it close at once (code 4003).
- **Rotate the publisher key:** `python tools/test_publisher.py keys --rotate`, then set the new setup code on the relay
  (Cloudflare dashboard: your `live` Worker > Settings > Variables and Secrets > PUBLISHER_KEY_SHA256). The old key stops working.
- **Remove everything:** delete the `live` Worker in the Cloudflare dashboard (Workers & Pages > live > Settings > Delete) and check
  that no `Channel` Durable Object namespace is left under Durable Objects; delete the repository copy the Deploy button made in your
  GitHub/GitLab account; remove Cloudflare's access in GitHub (Settings > Applications > Installed GitHub Apps); delete the test
  publisher's secrets file (`python tools/test_publisher.py show` prints where it is). Menu names may differ slightly over time.

## Security, in short

- The publisher key never leaves your PC; the relay holds only its SHA-256. Viewer links are read-only, one channel each, revocable.
- Viewers can only ping. Snapshots are size-capped and allow-listed; the overlay page sets text only, under a strict CSP, with no third-party scripts.
- Cloudflare sees your IP and your viewers' IPs and the counts, as any relay host would. This relay's code logs nothing.
