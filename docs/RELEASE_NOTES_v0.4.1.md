## Fortnite Visual Chest Counter v0.4.1 — Public Beta

### ⬇️ [Download for Windows: Fortnite-Visual-Chest-Counter-v0.4.1.zip](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases/download/v0.4.1/Fortnite-Visual-Chest-Counter-v0.4.1.zip)

Windows 10 / 11 · nothing to install · extract the zip and open **`Fortnite Visual Chest Counter.exe`**

A detection update. Fortnite's HUD Scale 75% gets its own experimental setting, and every player gets fewer double counts and more
accurate match times.

- **New, experimental: Fortnite HUD Scale 75%** (Settings, saved per profile). On the recording it was made from: 19 of 20 chests, 18
  of them CERTAIN, RARE CHEST pop-ups typed RARE, the match recognised from countdown to YOU PLACED
- A chest pop-up hidden for a moment (by the inventory, for example) is counted once, not twice
- Match play time stops at the death screen, the READY overlay and the return to the lobby
- Clearer Console wording for chests found by the blurred match

Your counts, profiles, settings and history are kept. Nothing changes for a profile unless you choose 75%.

<!-- highlights end -->

### Fortnite HUD Scale 75% (experimental)

Fortnite's HUD Scale (Settings > Game UI > HUD Scale) changes the size of the chest pop-up and of the match text, and the counter
reads them best at the size it was made for. Before v0.4.1, a 75% HUD gave APPROX only, missed some chests and never completed a match.

**Settings > Fortnite HUD Scale (this profile)**: choose **Fortnite HUD Scale 75% (experimental)** if, and only if, Fortnite's own
setting says 75%. Each profile keeps its own choice, so your own games can use 75% and a streamer's profile Standard. Stop and start
counting to use it.

On the maintainer's labelled recording (2560x1440 game, sent as 1280x720 at 30 fps over SRT):

| | v0.4.0 | v0.4.1, Standard | v0.4.1, 75% |
|---|---:|---:|---:|
| Chests found (of 20) | 16 | 16 | 19 |
| Counted twice / false | 1 / 0 | 0 / 0 | 0 / 0 |
| CERTAIN | 0 | 0 | 18 |
| RARE CHEST typed RARE (of 3) | 0 | 0 | 2, none typed wrong |
| Fully observed match Complete | no | no | yes (YOU PLACED) |
| That match's play time (true 912 s) | 974 s | 945 s | 913 s |

**Why it is experimental:** the 75% templates were cut from that same recording, so these numbers are not an independent test. A live
test is pending. The 75% setting is tested only for that setup; at another game resolution it is untested. The one chest it misses is
a CHEST line added to a CROWN BONUS pop-up that was already on screen: it looks too much like other pop-ups to be counted safely.
The README's [HUD Scale compatibility](https://github.com/GabrielGzS/fortnite-visual-chest-counter#hud-scale-compatibility) table lists
every tested combination and its status.

### Fixes for every HUD

- **Counted once:** when the inventory or another overlay hides a chest pop-up for a moment, it is no longer counted again when it
  comes back.
- **Play time:** a match's play stops at the ELIMINATED BY screen (also a short one), at the READY overlay ("PARTY TO READY UP",
  "NEXT MATCH") and at the grey CONNECTING of the return to the lobby, instead of running on until the next screen.
- **Console wording:** a chest found by the blurred match is "near-normal pop-up, shape not exact", not "drawn larger".

No detection threshold was lowered: CERTAIN means what it meant before.

### Known limitations

- **75% is provisional** (above). Other HUD Scale values have no setting of their own yet; Standard behaves as in v0.4.0 for them.
- Match tracking still reads English screens only.
- A line change hidden by an overlay (an X2 appearing just as the pop-up returns) can still be counted once too often or too few.
- The built-in updater's failure and rollback scenarios have not been run on real packages; if an update does not work, install by
  hand: extract the new zip to its own folder and copy `state\` and `config.toml`.

### Installing v0.4.1

**From v0.4.0:** the app offers the update by itself. Choose **Update available** in the sidebar (or **Settings > Check for updates**),
then **Download & Install**, then **Restart & Install**.

**By hand, or from an older version:** close the app, extract the new zip to its own folder, then copy `state\` and `config.toml`
from the old folder into the new one, and point your OBS Text source at the new `obs_output\`. Download it only from the official
[GitHub releases page](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases).

**Full details:** [README](https://github.com/GabrielGzS/fortnite-visual-chest-counter#readme)

Independent, unofficial project: not affiliated with, endorsed by or approved by Epic Games. "Fortnite" is a trademark of
Epic Games, Inc. MIT licence. Developed and tested during Fortnite Chapter 7 Season 5 (November 2026).
