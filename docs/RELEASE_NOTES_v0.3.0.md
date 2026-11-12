## Fortnite Visual Chest Counter v0.3.0 — Public Beta

### ⬇️ [Download for Windows: Fortnite-Visual-Chest-Counter-v0.3.0.zip](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases/download/v0.3.0/Fortnite-Visual-Chest-Counter-v0.3.0.zip) (about 156 MB)

Windows 10 / 11 · nothing to install · extract the zip and open **`Fortnite Visual Chest Counter.exe`**

**The Match Tracking & Analytics update.** v0.3.0 follows your matches while it counts, shows each match's chests live, keeps a
match history with statistics, and lets you correct a match's count as you play, including chests you broke rather than opened.
Small-HUD chests are found far more often on compressed video, and strong ones can now be CERTAIN. Match tracking is experimental,
on by default, and never changes your counts or what OBS shows.

### What's new at a glance

| New in v0.3.0 | Why it matters |
|---|---|
| **Match tracking (experimental)** | Follows the lobby, loading, the waiting island, the bus, play and the end of your match while counting. On by default |
| **Game view** | This match only, live: its CERTAIN and APPROX chests, chests per minute, play time, and whether its start was seen, beside the live preview |
| **Analytics** | A new page: matches, match time, time actively playing, chests per complete match, chests per minute, and a list of recent matches |
| **Fix this match** | **−1**, **+1** and **Undo** in the Game view correct that match and your total at once |
| **Broken chests** | Say why you added a chest. **Broken chest** is counted apart in Analytics, as reported by you |
| **Your choice of rates** | Chests per minute stay what the app detected unless you tick **Count my +1s**. Your −1s always count, because they remove a wrong chest |
| **Better small-HUD detection** | Chests on a smaller HUD are found far more often in compressed video, and the clearest can now be CERTAIN |
| **Dashboard views** | **Overview**, **Game** and **Console** replace one long page. Activity names each chest type in its own colour |

### Match tracking

While counting, the app works out where you are: lobby, loading, the waiting island, the bus, in the match, or out of it. Each match
is recorded as:

- **Complete**: its start and the end of your part in it were both seen, however it ended (placed, won, or back to the menus).
- **Partial**: part of it was not seen, for example when you started counting mid-match. It keeps its time but stays out of the main
  chests-per-minute figure.
- **Unconfirmed**: not enough evidence that it was a match. It stays out of every statistic.

There is no minimum match length: a real 20-second match is still a match. The waiting island is never counted as one, and the chest
that shows a match is under way belongs to that match. If a recorded match is wrong anyway, **Not a match** leaves it out of the
statistics and **Restore** puts it back; nothing is deleted.

To turn it off: **Settings > Match tracking (experimental)**, untick **Track matches and keep a match history**, click **Save**.
Full guide: [docs/MATCH_TRACKING.md](https://github.com/GabrielGzS/fortnite-visual-chest-counter/blob/main/docs/MATCH_TRACKING.md).

### Game view

Everything about the current match in one place: match status and details beside the **Live preview**, then **MATCH CERTAIN**,
**MATCH APPROX** and chests per minute, then the correction row, then the last match's final numbers. Your lifetime totals stay on
**Overview**.

### Corrections and broken chests

- **Overview:** **+1** and **−1** change your total, with an optional reason and **Undo**.
- **Game view:** **−1**, **+1** and **Undo** change the match on screen (between matches, the one that just ended) and your total.
  Next to +1 choose why: *Not sure / balance fix* (the default, which claims nothing), **Broken chest**, *A visible chest the counter
  missed*, or *Fortnite counted it, nothing else to see*. Choose Broken chest only when you know one was broken.
- A chest you add is shown as **manual**, never as a detected chest, and never changes CERTAIN.
- **Analytics** shows **Broken chests (yours)**: how many you reported and how many per complete match. They are your reports, not
  something the app detected.

### Analytics

**Average detected chests / min** uses complete matches only and needs five minutes of active play across them; **Including partial
matches** is shown apart. **Recent matches** lists each match with its time, CERTAIN, APPROX (and any manual chests), its own rate,
its quality and how it ended. The numbers on the Dashboard stay your official totals.

### Also new

- **No video warning:** if a live input stays open but stops delivering pictures for 10 seconds, the Dashboard says so, and tells you
  when video returns that some footage may be missing.
- **Save progress every:** choose how often match tracking saves its running totals, from 30 seconds to 10 minutes.
- **Live preview** is on by default and can be hidden; **Activity** and **Diagnostic recording** moved to the Console view.

### Detection and counting

- **Smaller HUD (about 0.8x):** on compressed video the chest word blurs, and most such chests were missed. In our test recordings of
  a 720p stream, found chests went from 1 of 7 to 6 of 7, and from 4 of 29 to 25 of 29, with no false counts and no duplicates. These are
  examples from specific recordings, not an accuracy guarantee.
- **CERTAIN on a smaller HUD:** a small-HUD pop-up whose match is as clear as a normal one now counts as CERTAIN. Less clear ones stay
  APPROX, as before.
- **One count per pop-up:** a pop-up hidden for a moment (by the full-screen map, for example) and seen again is counted once.
- **Normal HUD:** unchanged. All 11 earlier real-world cases give the same results.

### Known limitations

- **Match tracking reads English screens only.** In another language your chests are still counted, but matches show as *Not sure
  yet* and no statistics are made up.
- Match tracking has been tested on recordings, two streamers and a few real matches, which is still little evidence. Other game
  modes, reboots and squads are untested.
- **720p video:** on a smaller HUD the island and bus text are often not read, so those matches are recorded as Partial. 1080p works
  best. Stacked pop-ups (several chests in one pop-up) are also found less often at 720p.
- The lobby is recognised by its matchmaking button and loading screens, not yet by its menu bar while the TREASURE tab is shown.
  Leaving a match is still recognised.
- A short switch away from the game during a match, such as to a browser page, is left out of play time but does not make the match
  Partial.
- Broken chests come only from your own +1s; the app does not detect them.
- Analytics only covers matches recorded with match tracking on. The Dashboard stays the official total.
- The built-in updater is experimental. v0.3.0 is the first release it can install, so this is its first real update. If it does
  not work, install v0.3.0 by hand as described below.
- APPROX is an estimate; CERTAIN is the conservative number.
- Small-HUD detection is based on one streamer's HUD size; other sizes are untested. Portuguese pop-ups are recognised on a normal HUD
  only.
- Livestream URL is a lower-confidence convenience option: it counts what viewers get, and can miss chests through compression, ad
  breaks, buffering or reconnects.
- **Fair play:** the app only analyses video pixels and never touches Fortnite. Anti-cheat compatibility has not been officially
  verified. See the README's *Fair play and compatibility*.

### Installing v0.3.0

**From v0.2.3:** the app offers the update by itself. Choose **Update available**, then **Download & Install**, then **Restart &
Install**.

**By hand, or from an older version:** close the app, extract the new zip to its own folder, then copy `state\` and `config.toml`
from the old folder into the new one, and point your OBS Text source at the new `obs_output\`. Download it only from the official
[GitHub releases page](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases).

**Full details:** [README](https://github.com/GabrielGzS/fortnite-visual-chest-counter#readme)

Independent, unofficial project: not affiliated with, endorsed by or approved by Epic Games. "Fortnite" is a trademark of
Epic Games, Inc. MIT licence. Developed and tested during Fortnite Chapter 7 Season 5 (November 2026).
