# Fortnite Visual Chest Counter

A Windows app that counts Fortnite chest openings, saves match stats and estimates your Pirate Token odds. Count locally, show your stats on stream or compare results with friends through Discord.

PH

[Get started](#get-started) · [Features](#features) · [Capture setups](#capture-setups) · [Documentation](docs/index.md)

## Get started

1. Download a Windows ZIP from the [upstream releases](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases), or build this branch using the [development guide](docs/DEVELOPMENT.md). The features below describe this branch.
2. Extract the whole ZIP and launch **Fortnite Visual Chest Counter.exe**. The ZIP includes the runtime. On this branch the app starts in the Windows system tray. Open it from its tray icon.
3. In **Dashboard → Capture settings**, choose one source. The default is **Screen 1 HDR → SDR**. For an SDR monitor, choose its regular **Screen** entry. Use fullscreen gameplay in 16:9 with the HUD visible.
4. In **Settings → Fortnite language**, select the language of your game. English is the default. French, Brazilian Portuguese and a combined English/Portuguese option are available.
5. Click **Start counting** for manual capture. **Match automation** is enabled by default and can start the next local Battle Royale match and save it when you return to the lobby.

## Features

### Live chest counter

- **Certain** shows confirmed openings. **Approx** shows additional estimated openings. **Total** adds them together. For example, 42 confirmed and 9 estimated gives a total of 51.
- **Recent openings** shows detections as they happen. The chest-type breakdown distinguishes normal, Rare and Sprite chests when there is enough evidence. Ambiguous openings can still count with an unknown type.
- **Activity** shows detector decisions and **Live preview** shows the image being analysed. Choose 5, 10 or 15 analysed frames per second in Settings.
- **Profiles** keep separate counts, chest types and capture settings. One profile and one source count at a time. Use **Edit** to correct the counts and **Reset** to clear the live counter.
- **Analyse a recording** counts a video file separately from the live counter.

### Match tracking and Pirate Token odds

- **Finish match** saves manually. With automation enabled, new warmup and lobby entries from the local Fortnite log drive reset, start and save.
- Choose **Auto** to detect the Battle Royale playlist, or pick **Solo**, **Duo**, **Trio** or **Squad** manually. Auto mode can run with manual start and finish.
- **Match history** lets you edit saved counts and delete checked matches. Deleting local history preserves results already shared with the group.
- **Pirate Token chance** estimates the chance of at least one drop across the current Total. The model assumes independent rolls and uses a base rate of 1 in 137,500 per chest with the selected multiplier. For `n` chests and boosted probability `p` per chest, the estimate is `1 − (1 − p)^n`. [Fortnite Status](https://x.com/FortniteStatus/status/2119202610322227327) · [Independent calculator](https://piratetoken.quest/drop-rate/)

### Overlay and OBS

- The floating overlay shows an animated chest, configurable count layouts and wording, and optional token odds, chest types and saved match count. Preview it in the app and choose whether it appears when you share your screen.
- OBS can read `obs_output\chest_counter.txt` through **Text (GDI+)** or receive direct updates over OBS WebSocket. The OBS and CLI **APPROX** figure includes **CERTAIN**. See the [overlay guide](docs/guides/obs-overlay.md).

### Group and Discord

- Each player counts their own gameplay. Enable sharing and enter a player name and the shared webhook to submit matches. The **Host** runs the bot and publishes one leaderboard. **Guests** use its message link or ID to see the same standings.
- The app groups contributions with the same verified Fortnite session fingerprint, even when players return to the lobby at different times. The board shows per-player totals, confidence counts, chest types and match counts where available. Team odds use the chests submitted so far.
- Guests with sharing enabled follow the Host's published mode and multiplier. Turn sharing off for local-only matches and personal settings.
- The Host can send rich match reports manually or automatically, reset selected players in the standings or delete the published message. Discord commands include `/chests`, `/leaderboard`, `/add` and `/reset`. See the [setup and permissions guide](docs/guides/matches-and-discord.md).

### Windows settings and diagnostics

- Start in the tray, keep counting when the window closes and remember its position. **Reset all** restores defaults for the Settings page and preserves counts, profiles, history, overlay and Discord setup.
- Save session logs and popup snapshots, or record diagnostic footage. Press **Ctrl+Alt+M** to mark a missed opening and use **Review captures** to replay it.
- **Help & diagnostics** can run and copy a report, open the logs folder and clean generated logs and captures when counting is stopped.
- Packaged builds support optional update checks and a configurable download limit. See [how updates work](docs/maintenance/UPDATER.md).

## Capture setups

| Gameplay source | Setup guide |
|---|---|
| Your game, a video or a stream on a monitor | [Screen capture, including HDR](docs/guides/screen-capture.md) |
| Twitch or YouTube live URL | [Livestream capture](docs/guides/livestream-url.md) |
| OBS and Fortnite on the same PC | [OBS Virtual Camera](docs/guides/obs-single-pc.md) |
| Two PCs on the same network | [OBS over SRT](docs/guides/obs-dual-pc-srt.md) |
| OBS feed when Virtual Camera is already in use | [OBS projector](docs/guides/obs-projector.md) |
| Console or second PC through a capture device | [Capture card](docs/guides/capture-card.md) |
| A saved gameplay file | [Recorded video](docs/guides/recorded-video.md) |

## Compatibility and data

Detection depends on the visible chest pop-up. HUD size, compression, occlusion and fast consecutive openings can affect the count. Chest-type detection has been tested on English and French footage. Unsupported playlists or matches already underway may require manual tracking. See [troubleshooting](docs/guides/troubleshooting.md) and the [validation notes](docs/CHANGES.md).

Counting reads video frames. Optional match features read the local Fortnite log. Optional Discord sharing sends match statistics and a session fingerprint. The app is independent and has no Epic Games approval.

## Development and license

Run the GUI from an editable Python installation or use `debug-chest-counter.bat` from a configured checkout. The [development guide](docs/DEVELOPMENT.md) covers the Windows launcher, tests and packaging. The [documentation index](docs/index.md) links to research, release notes and maintenance guides.

[MIT License](LICENSE). See [bundled dependency notices](packaging/LICENSE-NOTICE.txt). Fortnite is a trademark of Epic Games, Inc.
