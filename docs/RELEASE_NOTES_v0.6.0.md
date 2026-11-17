## Fortnite Visual Chest Counter v0.6.0 — Public Beta

### ⬇️ [Download for Windows: Fortnite-Visual-Chest-Counter-v0.6.0.zip](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases/download/v0.6.0/Fortnite-Visual-Chest-Counter-v0.6.0.zip)

Windows 10 / 11 · nothing to install · extract the zip and open **`Fortnite Visual Chest Counter.exe`**

The two-PC update: show your counter in OBS on another PC or network, take a profile to another PC, give each streamer their own
overlay wording, and let the app add estimated broken chests for you.

- **Remote Sharing (preview):** an OBS Browser Source anywhere shows your live count, through a relay **you** run - never a
  connection into your PC. Off until you set it up; a free relay of your own, with a Deploy button, is documented
- **Export / Import** one profile - counts, whole history and its own wording - to move it to another PC
- **Each profile can have its own overlay wording**; switching profile switches it. `\n` starts a new line: `CHESTS OPENED\n≈ #`
- **Estimated broken chests** (off by default, 20 %) also for matches with a short gap in the video, as long as your Placed or
  Victory was seen. Analytics shows what it added, e.g. `54 (+11 · 20%)`
- **Settings and Overlay** are tabbed pages with one Save, and say what is unsaved

Your counts, profiles, settings, history and OBS sources are kept. Chest detection is unchanged.

<!-- highlights end -->

### Remote Sharing (preview)

**Overlay → Remote Sharing** sends the active profile's counter to a relay you choose, so an OBS **Browser Source** on any PC or
network shows it - with exactly the wording of your Overlay page, updated within a second.

```
your PC (the counter) --wss--> YOUR relay <--wss-- OBS Browser Source / any browser (read-only)
```

- **Nothing is sent until you set it up**, and the app makes no connection at all until then. It contains no relay, address or
  account of anyone else: you enter your relay's `wss://` address.
- Your PC only connects **out**: no open port, no port forwarding, your address never shown to viewers.
- **Create key** makes this PC's publisher key and keeps it in Windows Credential Manager - it is never shown. You give your relay
  only its **setup code** (the key's SHA-256), which cannot publish anything by itself.
- **Share this profile's counter** per profile: each profile has its own channel and its own links. Switching profile takes the
  previous one's overlays offline ("Counter offline - showing the last count") and shares the new one.
- **New link** copies a read-only link for an OBS Browser Source; **Revoke** closes it everywhere at once. Links are stored only as
  fingerprints.
- It reconnects by itself after a dropped connection and resends the right count; a Reset to lower numbers is shown at once. If
  another PC starts sharing the same profile, this one stops and says so instead of fighting over it.
- Certificates are always checked (the Mozilla list bundled with the app). Relays that use a company's private certificate
  authority are not supported.
- **Setup guide** (on the tab) explains it all. A free **reference relay** you can deploy into your own Cloudflare account (Workers
  Free plan, Deploy button, no Node.js needed): [relay/](https://github.com/GabrielGzS/fortnite-visual-chest-counter/tree/b0-relay/relay).
  Any server that speaks its documented protocol works the same way. A relay deployed before this release needs its three overlay
  files updated once to show your wording (see "Updating your relay" in its README).

### Move a profile to another PC

**Dashboard → Export / Import**:

- **Export this profile...** saves one `.fccprofile` file: its counts, its whole match history (corrections, estimates,
  predictions included), HUD Scale, own wording and livestream link.
- **Import a profile...** on the other PC checks the whole file first and shows what it holds. If that PC already has the profile:
  **Replace** it (the old counts and history are kept in a backup) or **Import as a copy**. Never merged, so nothing is counted twice.
- Never in the file: that PC's settings, other profiles, logs, recordings, keys or link addresses. Remote Sharing stays off for an
  imported profile until you turn it on there; its existing OBS links keep working once you do (their addresses cannot be shown on
  the new PC - make a new link if you need to copy one).
- Disabled while counting, so counts and history always belong together. A damaged or altered file is refused before anything is
  written, and a failed import changes nothing.

### Overlay wording per profile, and on two lines

- **Overlay → Display**: "The same wording for every profile" or "Own wording for <profile> only" - for example one wording per
  streamer. Local OBS, OBS WebSocket and Remote Sharing all follow the profile you switch to.
- Type `\n` in a wording box to start a new line (once per text), e.g. `CHESTS OPENED\n≈ #` shows
  ```
  CHESTS OPENED
  ≈ 25,001
  ```
- New installs start with `CHESTS OPENED ≈ #`; a button brings that wording back. Your existing wording is kept.

### Estimated broken chests

**Dashboard → Game → Add estimated broken chests when a match ends** (off by default, 20 %). Broken chests show no pop-up, so the
counter cannot see them; this adds that share of the chests detected in a match to APPROX, minus the Broken chest +1s you already made
for it. Never CERTAIN, once per match, kept apart from your +1s, and Undo takes it back.

- New in v0.6.0: a match whose video had a short gap ("Partial") also gets it, as long as your **Placed** or **Victory** was seen.
  A match cut off by Stop, lost, or not confirmed as a match still gets none. "Partial" itself and your statistics do not change.
  Matches already in your history are not changed.
- **Analytics → Matches** shows it in the APPROX column, e.g. `66 (+11 · 20%)`: APPROX already includes it. The tooltip says what it
  was worked out from, or why a match got none. A plain `(+8)` is your own +1s.

### Settings and Overlay

- Both are pages with tabs and **one Save** that writes everything or nothing, shows what is unsaved, and asks before you leave with
  unsaved changes.

### Good to know

- Going back to v0.5.1 later keeps your counts and history, but forgets each profile's own wording and Remote Sharing setup.
- Remote Sharing is a preview: it was tested end to end with the reference relay on Cloudflare and OBS on a second PC.
- Match tracking is still experimental and reads English screens only.
- The built-in updater's first real updates (v0.2.3 to v0.3.0, v0.4.0 to v0.4.1) worked. Its failure and rollback scenarios have not
  been run on real packages; if an update does not work, install by hand: extract the new zip to its own folder and copy `state\` and
  `config.toml`.

### Installing v0.6.0

**From v0.4.x or v0.5.x:** the app offers the update by itself. Choose **Update available** in the sidebar (or **Settings > Check for
updates**), then **Download & Install**, then **Restart & Install**.

**By hand, or from an older version:** close the app, extract the new zip to its own folder, then copy `state\` and `config.toml`
from the old folder into the new one, and point your OBS Text source at the new `obs_output\`. Download it only from the official
[GitHub releases page](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases).

**Full details:** [README](https://github.com/GabrielGzS/fortnite-visual-chest-counter#readme)

Independent, unofficial project: not affiliated with, endorsed by or approved by Epic Games. "Fortnite" is a trademark of
Epic Games, Inc. MIT licence. Developed and tested during Fortnite Chapter 7 (November 2026).
