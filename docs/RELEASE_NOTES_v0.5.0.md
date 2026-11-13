## Fortnite Visual Chest Counter v0.5.0 — Public Beta

### ⬇️ [Download for Windows: Fortnite-Visual-Chest-Counter-v0.5.0.zip](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases/download/v0.5.0/Fortnite-Visual-Chest-Counter-v0.5.0.zip)

Windows 10 / 11 · nothing to install · extract the zip and open **`Fortnite Visual Chest Counter.exe`**

The Predictions update. What do your chests mean for this season's treasure rewards? A new **Predictions** page turns your counted chests
and Epic's published odds into chances, forecasts and a bit of perspective on how wild those odds are.

- **My Progress**: your chance for every Treasure Hunters reward, from the Gizmo (1 in 127) to the Weekly Gold Outfit (1 in 1,562,500)
- Chests and hours to 50% and 90% at your own pace, for Solo, Duo, Trio or Squad
- Gizmo cycles, weekly rewards that start again at the Sunday rotation, and a sentence on how normal (or unlucky) your wait is
- **What If?**: roll a random first drop and see how many chests it could take
- Start new cycle, Mark obtained and Undo, per profile; nothing is ever deleted

Your counts, profiles, settings and history are kept, and your history since the season began is used straight away.

<!-- highlights end -->

### Estimates, not detections

The app does not see what drops: there is no treasure recognition yet. Every number is a statistical estimate from the chests the
counter counted (the APPROX side, the same chests Analytics uses) and Epic's normal odds per chest, which are the same for every player.
Chests the counter missed, or opened while it was not counting, are not in the numbers. **Mark obtained** is your own report, saved with
its date as yours. A Gizmo cycle reaching 90% is a statistical milestone, never a Gizmo found.

### My Progress

One card per reward: the chance of having found it in this cycle, a bar toward the 90% mark (measured in chests), chests and hours to 50%
and 90% at your pace (chests per hour of real life, from Analytics), what you could statistically have found this season, and a fixed
sentence on how unusual your wait is ("Perfectly normal: 41% of players would still be waiting").

- **Gizmos** start a new cycle by themselves at 90% (292 chests).
- **Weekly rewards** start again at the Sunday rotation, 9 AM New York time. **Pirate Shop Access** runs for the whole season.
- **Start new cycle** counts from now (to help a friend, say); **Mark obtained** stops that reward's chance with the date. Both have Undo.
- **Solo / Duo / Trio / Squad** changes only the time, assuming teammates open as many chests as you and rewards are shared (not confirmed
  by Epic). It never changes the chance per chest.

### What If?

Pick a reward, a team and, if you like, a Treasure Hour multiplier (1.5x to 10x, for the whole hunt: a what-if), then **Roll a
prediction**: how many chests it took this time, who found it, how long at your pace, and how lucky that roll was. Every roll is
independent, and nothing is saved.

### Known limitations

- The odds and the weekly rotation time come from Epic's published table as reported; the Gizmo's 1 in 127 was not in the press coverage
  we checked. The season's end date (about 5 December) is an estimate.
- Treasure Hours boost a chest only when the pool lists that event's exact times; none is listed yet, so every chest uses the normal odds.
- Predictions use the chests in your saved history, which starts with v0.3.0 and only covers time the app was counting.
- Match tracking still reads English screens only; Predictions work in any language.

### Installing v0.5.0

**From v0.4.x:** the app offers the update by itself. Choose **Update available** in the sidebar (or **Settings > Check for updates**),
then **Download & Install**, then **Restart & Install**.

**By hand, or from an older version:** close the app, extract the new zip to its own folder, then copy `state\` and `config.toml`
from the old folder into the new one, and point your OBS Text source at the new `obs_output\`. Download it only from the official
[GitHub releases page](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases).

**Full details:** [README](https://github.com/GabrielGzS/fortnite-visual-chest-counter#readme)

Independent, unofficial project: not affiliated with, endorsed by or approved by Epic Games. "Fortnite" is a trademark of
Epic Games, Inc. MIT licence. Developed and tested during Fortnite Chapter 7 (November 2026).
