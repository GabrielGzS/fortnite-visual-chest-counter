## Fortnite Visual Chest Counter v0.3.0 — Public Beta

### ⬇️ [Download for Windows: Fortnite-Visual-Chest-Counter-v0.3.0.zip](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases/download/v0.3.0/Fortnite-Visual-Chest-Counter-v0.3.0.zip) (about 156 MB)

Windows 10 / 11 · nothing to install · extract the zip and open **`Fortnite Visual Chest Counter.exe`**

**Match tracking, a first Analytics page and quick count corrections.** v0.3.0 can follow your matches while it counts, keep a
history of them and show what that history says. It is experimental and off by default. Chest detection has not changed.

### What's new at a glance

| New in v0.3.0 | Why it matters |
|---|---|
| **Match tracking (experimental)** | Follows lobby, loading, match and ending while counting. Turn it on in **Settings**. It never changes your counts or what OBS shows |
| **Analytics** | A new page with matches, match time and chests per match and per minute, CERTAIN and APPROX kept apart |
| **Honest match quality** | A match only counts as **Complete** if its start and ending were both seen. **Partial** matches never enter complete-match averages |
| **Dashboard views** | **Overview**, **Game** and **Console** replace one long page. The Live preview is in Game; Activity and Diagnostic recording are in Console |
| **+1 / −1** | Fix APPROX by one chest with a click, also while counting, with an optional reason and Undo |
| **Not a match / Restore** | Leave a wrong match out of the statistics, and put it back any time. Nothing is deleted |
| **Save progress every** | Choose how often match tracking writes running totals: 30 seconds to 10 minutes |

### Turning on match tracking

**Settings > Match tracking (experimental)**, tick **Track matches and keep a match history**, click **Save**. It starts the next
time you click **Start counting**. Full guide: [docs/MATCH_TRACKING.md](https://github.com/GabrielGzS/fortnite-visual-chest-counter/blob/main/docs/MATCH_TRACKING.md).

### Detection and counting

Unchanged from v0.2.3. With match tracking on or off, the chests counted, CERTAIN, APPROX and the OBS text are the same.

### Known limitations

- **Match tracking reads English screens only.** In another language your chests are still counted, but matches show as *Not
  sure yet* and no statistics are made up.
- Match tracking has been tested on recordings, and has not yet been confirmed on a full real match from start to finish.
  Other game modes, reboots and squads are untested.
- Analytics only covers chests recorded with match tracking on, and leaves out manual corrections. The Dashboard stays the
  official total.
- The built-in updater is experimental. v0.3.0 is the first release it can install, so this is its first real update. If it
  does not work, install v0.3.0 by hand as described below.
- APPROX is an estimate; CERTAIN is the conservative number.
- HUD sizes other than normal, about 1.3x larger and about 0.8x smaller are untested; Portuguese pop-ups are recognised on a
  normal HUD only, and Portuguese stacked pop-ups are untested.
- Chest types: English only; the rare / sprite split is based on a small number of streams.
- Livestream URL is a lower-confidence convenience option: it counts what viewers get, and can miss chests through compression, ad
  breaks, buffering or reconnects. How many has not been measured.
- **Fair play:** the app only analyses video pixels and never touches Fortnite. In one developer session it analysed a
  livestream on the same PC while Fortnite was being played without a BattlEye interruption - one observation, not a
  guarantee; anti-cheat compatibility has not been officially verified. See the README's *Fair play and compatibility*.

### Installing v0.3.0

**From v0.2.3:** the app offers the update by itself. Choose **Update available**, then **Download & Install**, then **Restart &
Install**.

**By hand, or from an older version:** close the app, extract the new zip **into the same folder** and replace the files -
counts, settings, profiles and OBS sources keep working (or copy `state\` and `config.toml` to a new folder). Download it only
from the official [GitHub releases page](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases).

**Full details:** [README](https://github.com/GabrielGzS/fortnite-visual-chest-counter#readme)

Independent, unofficial project: not affiliated with, endorsed by or approved by Epic Games. "Fortnite" is a trademark of
Epic Games, Inc. MIT licence. Developed and tested during Fortnite Chapter 7 Season 5 (November 2026).
