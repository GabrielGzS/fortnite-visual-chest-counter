# Remote Sharing (preview)

Remote Sharing sends a profile's counter to **a relay you run**, so an OBS Browser Source on another PC or another network shows it
live - with exactly the wording of the app's Overlay page. It is off until you set it up, and the app then makes no connection at all.

```
your PC (the counter) --wss--> YOUR relay <--wss-- OBS Browser Source / any browser (read-only), anywhere
```

Your PC only connects **out** to your relay; viewers only connect to the relay. Nothing ever connects to your PC, and no port
forwarding is needed. The app contains no relay of its own and no account of anyone else: you choose where your counts go.

## What you need

A relay that speaks **Remote Sharing protocol v1** (`relay/PROTOCOL.md` in the project). The project includes a reference relay
you can run for free in your own account on Cloudflare's Workers Free plan, with a Deploy button and no Node.js on your PC: see
https://github.com/GabrielGzS/fortnite-visual-chest-counter/tree/b0-relay/relay (its README). Any other server that passes `relay/tools/conformance.py` works the same way.

## Set it up (Overlay > Remote Sharing)

1. **Create key.** The app makes this PC's publisher key and keeps it in Windows Credential Manager - it is never shown. Next to it
   is the **setup code** (the key's SHA-256): **Copy** it and give it to your relay (the reference relay asks for it as
   `PUBLISHER_KEY_SHA256` when you deploy it). The setup code alone cannot publish anything.
2. **Relay address:** your relay's `wss://` address. **Save changes.**
3. **Share this profile's counter**, then **Save changes**. The status line says **Live** when the relay accepted this PC.
4. **New link** makes a read-only viewer link and copies it. In OBS: Sources > + > **Browser**, paste it as the URL, about 600 x 150.
   Keep links out of public chat: anyone with one can watch (never change) this counter. **Revoke** stops a link at once.

Fonts, colours and size: OBS's Custom CSS for the Browser Source. The wording, layout and thousands separator: the Overlay page's
Display tab - for every profile, or this profile's own wording.

## Profiles

Each profile has its own channel, sharing switch and viewer links; only the profile you count with is shared. Switching profile
switches what your viewers see: the previous profile's overlays show "Counter offline - showing the last count".

## Two PCs

- **The relay never moves**: it runs at your relay host, not on a PC.
- To publish from another PC: **Create key** there and give your relay that PC's setup code (for the reference relay: replace
  `PUBLISHER_KEY_SHA256` in its settings). From then on the relay refuses the old PC's key. The app never shows a key, so a key
  cannot be copied between PCs; **Enter key...** is only for a key you already keep elsewhere. Only one PC can publish a profile's
  channel at a time: a second one takes over and the first stops, with a message.
- Profile export/import moves a profile's channel and its links' fingerprints, never a key: the links keep working, but their
  addresses cannot be shown on the new PC - make a new link there if you need to copy one.

## When something is wrong

| The app says | What to do |
| --- | --- |
| This PC has no publisher key | Create key, then give the relay the setup code |
| The relay did not accept this PC's publisher key | The relay has another setup code: copy this PC's setup code to the relay again |
| Another PC is now publishing this profile's channel | Turn sharing off and on again (and save) to take it back |
| The relay's certificate is not trusted | The address is wrong, or the relay uses a private certificate authority (not supported) |
| Not a compatible relay (HTTP ...) | Check the address: it must be the relay itself, e.g. `wss://your-relay.example` |

An overlay that keeps saying "Cannot reach the counter" either lost its relay or uses a revoked link: make a new link.
