# Fortnite Visual Chest Counter

**Automatically count Fortnite chests from gameplay video.**

A free, open-source Windows app that recognises the chest-opening pop-ups visible in Fortnite gameplay and keeps a running
count - from a Twitch or YouTube livestream link, anything shown on a screen, your own stream's OBS feed (single-PC or
dual-PC), a capture card, or a recorded video. The numbers go to a text file that an OBS Text source can show on stream, so
nobody has to count by hand.

Chest counts come from gameplay video. Optional match automation and automatic mode selection read Fortnite's local
Windows log. See [fair play and compatibility](#fair-play-and-compatibility).

PH

> **Two PCs, no capture card required — tested.** Use OBS's built-in SRT support to send gameplay video from your gaming
> PC to a second PC running Fortnite Visual Chest Counter. Successfully tested with v0.2.0 on November 7, 2026, with
> numerous chests counted and no noticeable lag. **[Dual-PC SRT setup guide](docs/guides/obs-dual-pc-srt.md)**

> Independent, unofficial project: not affiliated with, endorsed by or approved by Epic Games. "Fortnite" is a trademark of
> Epic Games, Inc.
> Published baseline: **v0.2.3 public beta**. The guides also describe the local desktop changes. Developed and tested during Fortnite Chapter 7 Season 5 (November 2026) -
> see [Fortnite compatibility](#fortnite-compatibility). Windows 10 / 11. Nothing to install.

**Contents:** [Chest counters](#chest-counters) · [Download](#download) · [Choose your setup](#choose-your-setup) ·
[Quick start](#quick-start) · [Show it on stream](#show-it-on-stream) · [Using the app](#using-the-app) ·
[Fair play](#fair-play-and-compatibility) · [Updating](#updating) · [Troubleshooting](#troubleshooting) ·
[Known limitations](#known-limitations) · [How it works](#how-it-works) ·
[Development](#development)

## Chest counters

| Dashboard counter | Meaning |
|---|---|
| **Certain** | Openings confirmed by strong visual evidence. |
| **Approx** | Additional estimated openings. |
| **Total** | Certain plus Approx. For example, 42 confirmed and 9 estimated gives a total of 51. |

The OBS text output and CLI retain the original convention. Their **APPROX** is the estimated total of 51 and already
includes the 42 confirmed openings. The on-screen overlay uses the Dashboard convention.

## Download

1. Open the [**Releases** page](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases) and download the latest
   `Fortnite-Visual-Chest-Counter-v….zip` (about 155 MB; it includes everything it needs). `SHA256SUMS.txt` lets you verify
   it, and `ffmpeg-source-*.tar.gz` is the source code of the bundled video helper (licence requirement).
2. Right-click the ZIP → **Extract All**. Use a normal folder (Desktop or Documents). Do not run it from inside the ZIP or
   from Program Files.

```text
Fortnite Visual Chest Counter.exe   <- the app: the only thing you open
README.html                         offline copy of the setup guide
config.example.toml                 optional advanced settings
obs_output\                         the text files OBS reads
state\  logs\                       your counter and logs (kept when you update)
runtime\                            program files (official python.org Python, FFmpeg, Qt) - do not touch
```

## Choose your setup

Pick what you want to count - most people need one of the first two, which need no OBS at all. Step-by-step guides:

| What you want to count | Guide | Tested |
|---|---|---|
| A **Twitch or YouTube livestream** - paste the link | [Livestream URL](docs/guides/livestream-url.md) | **Yes** - incl. a 3-hour session (~500 chests), 2026-11-08 |
| Anything **on a screen** - a stream or video playing fullscreen, or your own game | [Screen](docs/guides/screen-capture.md) | **Yes** - 2026-11-08 |
| **Your own stream**, Fortnite and OBS on one PC | [Single PC with OBS](docs/guides/obs-single-pc.md) | Yes |
| **Gaming PC + streaming PC** on the same network, no capture card | [Dual PC over the network (SRT)](docs/guides/obs-dual-pc-srt.md) | **Yes** - 2026-11-07, v0.2.0 |
| A **video file** | [Recorded video](docs/guides/recorded-video.md) | Yes |
| **Console or gaming PC + capture card** + streaming PC | [Capture card](docs/guides/capture-card.md) | *Less tested:* counter side yes; not yet with a physical card |
| Capture card **owned by OBS** and **Virtual Camera used by another program** | [OBS projector window](docs/guides/obs-projector.md) | *Less tested:* window capture yes; not yet with a real OBS projector |

Then [show the numbers on stream](docs/guides/obs-overlay.md) - from the text file, or instantly through OBS's built-in
WebSocket (optional). Virtual Camera already used by another program? Read your gameplay from an
[OBS projector window](docs/guides/obs-projector.md).

## Quick start

A fresh setup uses English HUD recognition at 15 analysed frames per second, Screen 1 with HDR-to-SDR conversion,
automatic local match tracking and **Auto** mode. The app starts in the Windows system tray. Open it from its tray icon
to change the capture source or turn off **Start in the system tray**. The on-screen overlay starts enabled, with one-line
counts and optional statistics shown. Group sharing stays off until you enable it.

Open **`Fortnite Visual Chest Counter.exe`**, then use **Dashboard → Capture settings** to pick one video source.
For a French HUD, set **Settings → Fortnite language → French** and save.

```text
A livestream:   Livestream URL -> paste the link (https://www.twitch.tv/CHANNEL or a YouTube live link) -> Start counting
A screen:       play the stream, video or game FULLSCREEN -> pick that Screen -> Start counting
Your own OBS:   in OBS make a scene `ChestDetectorFeed` with only your game, Virtual Camera gear -> Output Type: Scene ->
                ChestDetectorFeed -> Start Virtual Camera; in the app pick "OBS Virtual Camera" -> Start counting
```

Want the numbers on stream? In OBS add a Text (GDI+) source (Read from file) pointing at `obs_output\chest_counter.txt` (the
app's Overlay page shows the exact path and lets you choose what it says).

The counter needs **clean Fortnite gameplay**: 16:9, HUD visible, nothing covering the chest pop-up right of the crosshair.
Every click explained: [setup guides](docs/guides/index.md).

## Show it on stream

In the scene your viewers see: **Sources → + → Text (GDI+)** → tick **Read from file** → choose
**`obs_output\chest_counter.txt`** (the app's **Overlay** page shows the exact path, with **Copy path**). That is the only file
OBS ever needs. The Overlay page chooses what it says - both numbers on two lines or one line, estimated total only, or
confirmed only - and your own wording; changes apply within a second, even while counting.
Details and the other files: [overlay guide](docs/guides/obs-overlay.md).

## Using the app

- **Dashboard:** Choose one capture source per app. Start or stop counting, edit confirmed and estimated openings,
  or reset the live count. Capture settings also holds profiles, source refresh and diagnostic recording.
- **Profiles:** Each profile has its own source, counts and chest-type split. Profile actions are next to the selector.
- **Recent openings:** Shows the detection result. The counter distinguishes normal, Rare and Sprite chests where the
  pop-up supplies enough evidence. Unknown and unclassified openings still count toward the total.
- **Pirate Token:** The percentage estimates the chance of at least one drop across the current Total, assuming
  independent rolls. With per-chest probability `p` and `n` openings, the estimate is `1 − (1 − p)^n`.
  The normal rate used by the app is 1 in 137,500 per chest. The multiplier is a manual setting.
  [Fortnite Status announcement](https://x.com/FortniteStatus/status/2119202610322227327) ·
  [Independent Pirate Token calculator](https://piratetoken.quest/drop-rate/).
- **Overlay:** Configure the animated on-screen overlay, screen-share visibility, wording and optional token chance,
  chest types and saved match count. The OBS text output has its own legacy count convention.
- **Settings:** Set the Fortnite HUD language, 5/10/15 analysed frames per second, diagnostic and tray options, match
  automation and updates. **Reset all** restores the defaults for this page and keeps counts, profiles and history.
- **Help & diagnostics:** Run and copy a report, open logs, clean diagnostics when capture is stopped, or open the upstream project page.

See [match tracking and Discord](docs/guides/matches-and-discord.md),
[overlay setup](docs/guides/obs-overlay.md) and the [documentation index](docs/index.md).

## Fair play and compatibility

The counter is built for statistics and stream presentation: it counts chest openings that are **already visible on
screen**. It gives no competitive information - it does not locate hidden chests, reveal enemies, aim, move or play for you.
Chest detection reads video frames. The optional match features read the local Fortnite log. Network features
include livestream capture, update checks and the optional Discord integration. Ctrl+Alt+M marks a missed chest
using a Windows hotkey.

Epic Games' rules prohibit tools that use real-time gameplay information to gain a competitive advantage. This app is
designed for counting, not for competitive assistance - but Epic does not certify individual third-party applications, and
this one has not been reviewed or approved by Epic. The most conservative ways to use it:

- **Count recorded video** (Dashboard -> Capture settings -> Analyse a recording), or
- **run the counter on a separate streaming PC** (dual-PC setup, [over the network with SRT](docs/guides/obs-dual-pc-srt.md)
  or [with a capture card](docs/guides/capture-card.md)), so the counter and the game run on different PCs.

Running the counter on the same PC as Fortnite works technically. In one developer session (2026-11-08) the app analysed a
livestream on the same PC while Fortnite was being played, and BattlEye did not interrupt the game. That is one observation,
not a verification: the app's compatibility with Fortnite's anti-cheat has not been officially verified, and anti-cheat
behaviour can change at any time. A dual-PC setup is not a compliance guarantee either; it simply keeps the counter away from
the game. Tournament or event rules can be stricter than normal play - check them if you compete.

## Updating

**From v0.2.3 on, the app has a built-in updater (experimental).** Shortly after opening it checks for a new version and, if there is
one, shows a small **Update available** link in the sidebar. Choose **Download & Install**: counting keeps running while the update is
downloaded and prepared, and **Restart & Install** finishes it. It is built to keep your counts, profiles, settings and OBS sources, and
to return to the previous version by itself if a new one does not start properly. Nothing is downloaded or installed unless you choose
to. The automatic check and the download speed are in **Settings > Updates**.

The updater has not installed a real update yet: v0.2.4 will be the first. If it does not work, install that version by hand as
described below.

**Getting v0.2.3 takes a manual download**, because older versions have no updater. Download it only from the official
[GitHub releases page](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases).

Your data is stored next to, not inside, the program files: `state\` (counts of every profile), `config.toml` (settings), `logs\`,
`captures\`, `obs_output\` (re-created automatically). Easiest: close the app, extract the new ZIP **into the same folder** and
replace files; opening the app writes your real numbers back into the OBS text files. If you extract to a new folder, copy
`state\` and `config.toml` and re-point the OBS Text source.

**Coming from v0.1.x:** delete the old `.bat` and `.cmd` files after extracting. Counts, settings and OBS sources keep working.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `OBS Virtual Camera was not found` | Open OBS Studio 28+, click **Start Virtual Camera**, click **Start counting** again. |
| Number never changes | Turn on **Live preview**: 16:9, full screen, HUD visible? Does the chest pop-up ("CHEST" / "BAÚ") appear? Screen source: the stream must play **fullscreen** - a small player inside a web page is too small. |
| Livestream URL: "Buffering" / video in bursts | Normal for a live stream; the counter catches up and keeps counting. Keep **Stream stability: Maximum stability** for long sessions. |
| SRT picture black on the streaming PC | Address, port, Media Source settings and Windows Firewall: [SRT troubleshooting](docs/guides/obs-dual-pc-srt.md#troubleshooting). |
| OBS text blank / not updating | The Text source must have **Read from file** ticked and point at the file shown on the Overlay page. |
| Anything else | Help & diagnostics → **Run diagnostics** → **Copy report**; include any `logs\crash_*.txt` in an [issue](https://github.com/GabrielGzS/fortnite-visual-chest-counter/issues). |

More: [full troubleshooting guide](docs/guides/troubleshooting.md).

## Fortnite compatibility

The chest detection in v0.2.2 was developed and live-tested during **Fortnite Chapter 7 Season 5** (November 2026);
its automated tests also use recordings of earlier gameplay. It recognises Fortnite's on-screen chest pop-up and HUD
elements, which Epic Games can change in any update. If chests stop being counted after an update, please
[open an issue](https://github.com/GabrielGzS/fortnite-visual-chest-counter/issues) with the diagnostics report and, if you
can, a diagnostic capture.

## Known limitations

- **APPROX is an estimate** and can be slightly high or low. CERTAIN is the conservative number.
- **Language-specific:** chest detection reads the word in the pop-up: English (CHEST), Brazilian Portuguese (BAÚ), or
  French (COFFRE). The counter reads chest **types** (normal / rare / sprite) from English and French pop-ups.
  It shows "unknown type" when it cannot classify the line reliably.
- **HUD layout/scale:** assumes a 16:9 picture with the HUD in its usual place. For **English** pop-ups a HUD drawn larger
  (up to about 1.3x) or smaller (about 0.8x, tested on one stream) is recognised; those chests count in **APPROX only**,
  never CERTAIN. Other HUD sizes, a moved or hidden HUD, Portuguese pop-ups on a non-standard HUD, and 4:3 / vertical
  video will not work well.
- **Chests opened in quick succession** are ADDED to the pop-up on screen ("RARE CHEST X2", "X3", another "... CHEST"
  line). v0.2.2 counts those steps (multiplier steps in APPROX only); two chests within a fraction of a second can count as
  one - never as two for one chest. Portuguese stacked pop-ups are not tested.
- **Livestream URL:** video arrives as viewers get it - in bursts, with buffering, ad breaks and reconnects; footage the
  platform never delivered cannot be counted (the app says when that happens).
- **Screen source:** the gameplay must fill the screen; a small player inside a web page is not counted.
- **Clean gameplay feed recommended:** overlays on top of the HUD can hide the clues.
- **Audio is not used**; only the picture is analysed.
- **Match automation:** requires new Battle Royale warmup and lobby markers in the local log. Use manual controls
  for a match already underway, a remote feed or an unrecognised playlist.
- Tested on a limited set of recordings (PC English, PS5 Portuguese, their stream-compressed versions, diagnostic
  recordings of streams with a larger and a smaller HUD, 11 labelled real-world cases), live sessions (incl. a 3-hour
  livestream) and one dual-PC SRT setup. Physical capture cards and real OBS projectors are untested. Windows only.



## How it works

The app is a window around a separate counting process (the same engine the console version runs), so the window can never
slow counting down. The counter samples 15 frames per second (rescaled to 1280x720) and looks for visual clues: the
"CHEST"/"BAÚ" XP pop-up, the "CONTAINER OPENED" tag, the interaction-button prompt with chest-coloured objects near it, and
ammo-counter changes that indicate shooting (which downgrades ambiguous pop-ups of short, less specific words). Clues are
merged into one event per chest, each event gets a confidence tier, and the tier decides whether it adds to CERTAIN + APPROX
or to APPROX only. Because stream compression slightly smears the small pop-up text, a medium-confidence pop-up is also
checked with a compression-tolerant (blurred) glyph match; if that match is strong it is promoted to CERTAIN. Some streams
draw the HUD larger, so the English word no longer matches at its normal size: when the pop-up area is lit but the normal
match finds nothing, the counter also tries the blurred match at a few smaller picture scales. Such a chest counts in
APPROX only, and never when the normal match already found that pop-up. Measurements:
[docs/ACCURACY_NOTES.md](docs/reference/ACCURACY_NOTES.md). Research history: [docs/DETECTOR_NOTES.md](docs/reference/DETECTOR_NOTES.md).
Live analysis uses a latest-frame policy. Optional diagnostics can save local clips. Discord integration sends match statistics when sharing is enabled.

## Development

Use Python 3.11 or later and FFmpeg on PATH when running from source.

See [development notes](docs/DEVELOPMENT.md) for the local Windows launcher and test commands.

```text
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python -m fortnite_chest_counter.gui      # the app
.venv\Scripts\python -m fortnite_chest_counter --help   # the command line (live, video, review, configure, ...)
.venv\Scripts\python tests\test_release.py ; .venv\Scripts\python tests\test_app.py
```

Layout: `src/fortnite_chest_counter/` (`counter.py` engine + commands, `estimator.py`, `detection/`, `input/`, `gui/` app,
`capture.py` + `review.py` diagnostic capture, `templates/`), `tests/`, `packaging/` (release builder + launcher source),
`docs/` (`docs/guides/` = user setup guides), `research/`. Large recordings (`samples/`) are intentionally not in Git. See
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md); plans: [docs/ROADMAP.md](docs/ROADMAP.md).

## License

[MIT](LICENSE) - free to use, modify and share. The Windows download also bundles FFmpeg (LGPL v3, unmodified; its exact
source is attached to each GitHub release), Qt for Python / Qt (LGPL v3, unmodified), the official python.org Python runtime,
NumPy and SciPy under their own licenses; see `packaging/LICENSE-NOTICE.txt`.

Not affiliated with or endorsed by Epic Games. "Fortnite" is a trademark of Epic Games, Inc.
