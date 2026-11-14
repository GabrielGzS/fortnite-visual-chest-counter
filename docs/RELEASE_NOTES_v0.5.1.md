## Fortnite Visual Chest Counter v0.5.1 — Public Beta

### ⬇️ [Download for Windows: Fortnite-Visual-Chest-Counter-v0.5.1.zip](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases/download/v0.5.1/Fortnite-Visual-Chest-Counter-v0.5.1.zip)

Windows 10 / 11 · nothing to install · extract the zip and open **`Fortnite Visual Chest Counter.exe`**

A Settings fix. A setting you change but never save no longer looks the same as one you saved, and the app tells you which Fortnite HUD
Scale it is really using.

- **Save changes** is always at the top of Settings, beside a status: "Unsaved changes", "Settings saved" or what went wrong
- Leaving Settings, switching profiles or closing the app with unsaved changes asks: save, discard or stay
- Scrolling the page with the mouse wheel no longer changes the setting under the pointer
- When counting starts, the Console says the HUD Scale in use: "Fortnite HUD Scale: 75% (experimental) (profile ...)"
- The 75% HUD Scale setting, on a second recording it was not made from: 17 of 17 chests, 15 CERTAIN, the match Complete

Your counts, profiles, settings and history are kept. Chest detection is unchanged.

<!-- highlights end -->

### Why this release

A maintainer's test at Fortnite HUD Scale 75% showed APPROX only, never CERTAIN, and every match Partial. The cause was not the
detector: the 75% choice had never been saved, so the counter ran with Standard. The Settings page made that easy, with Save at the very
bottom, no sign that anything was unsaved, unsaved choices dropped silently on leaving the page, and the mouse wheel changing whatever
drop-down it passed over.

The same recording, counted again with each setting:

| | Standard (what ran) | 75% (what was chosen) |
|---|---:|---:|
| Chests found (of 17) | 12 | 17 |
| CERTAIN | 0 | 15 |
| Counted twice / false | 0 / 0 | 0 / 0 |
| The match | Partial | Complete (YOU PLACED) |

### Settings

- **Save changes** and the save status stay at the top of the page while you scroll. Save is available only when there is something to
  save. "Settings saved" appears only after the new values have been read back from `config.toml` and the profile.
- If saving fails, the page says why and your changes stay on screen so you can try again.
- Leaving the page, which also covers switching profiles on the Dashboard, and closing the app ask what to do with unsaved changes.
- The **Fortnite HUD Scale** card shows what is saved for the active profile.
- The mouse wheel over a drop-down or number box scrolls the page. Click a drop-down or use the keyboard to change it.

### Checking which HUD Scale is used

- The Console's first lines when counting starts: "Fortnite HUD Scale: Standard" or "Fortnite HUD Scale: 75% (experimental)", with
  the profile's name. The session log records it too.
- **Help & diagnostics > Run diagnostics** reports the active profile's HUD Scale.
- With Standard on a 75% HUD, the Console says "near-normal pop-up, shape not exact": that is the blurred match, which counts APPROX
  only. If you play at 75%, choose 75% and press **Save changes**.

### Known limitations

- **75% HUD Scale is still experimental**: it was tested on one player's game at 2560x1440 sent as 1280x720 at 30 fps, on two
  recordings. A live session with 75% saved has not been checked yet.
- At 75%, a NEW STORM PHASE line added to a chest pop-up can, for a moment, look like a chest line. On the recording, a real chest line
  followed, so the total was right, but on its own it could add one APPROX chest.
- Match tracking is still experimental and reads English screens only.
- The built-in updater's first real updates (v0.2.3 to v0.3.0, v0.4.0 to v0.4.1) worked. Its failure and rollback scenarios have not
  been run on real packages; if an update does not work, install by hand: extract the new zip to its own folder and copy `state\` and
  `config.toml`.

### Installing v0.5.1

**From v0.4.x or v0.5.0:** the app offers the update by itself. Choose **Update available** in the sidebar (or **Settings > Check for
updates**), then **Download & Install**, then **Restart & Install**.

**By hand, or from an older version:** close the app, extract the new zip to its own folder, then copy `state\` and `config.toml`
from the old folder into the new one, and point your OBS Text source at the new `obs_output\`. Download it only from the official
[GitHub releases page](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases).

**Full details:** [README](https://github.com/GabrielGzS/fortnite-visual-chest-counter#readme)

Independent, unofficial project: not affiliated with, endorsed by or approved by Epic Games. "Fortnite" is a trademark of
Epic Games, Inc. MIT licence. Developed and tested during Fortnite Chapter 7 (November 2026).
