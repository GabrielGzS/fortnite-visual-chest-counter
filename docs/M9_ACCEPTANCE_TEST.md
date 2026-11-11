# v0.3.0 hands-on acceptance test

For the maintainer, on the main PC, with the actual packaged build. These are the checks automation cannot do: nothing below
has been run yet. About one evening, most of it spent playing.

Write down the time of anything odd, then keep going. Send `logs\`, `state\history\` and a diagnostics report afterwards.

## Setup

1. Extract `Fortnite-Visual-Chest-Counter-v0.3.0.zip` to a **new, short folder**, for example `C:\fcc-rc\`. Leave your normal
   install alone, and close it first: only one counter can run at a time.
2. Open **Fortnite Visual Chest Counter.exe**. Create a profile called `RC test` and select it.
3. **Settings > Match tracking (experimental)**: tick it, keep **1 minute**, click **Save**.
4. OBS: **ChestDetectorFeed** showing clean gameplay, **Start Virtual Camera**. In the app choose **OBS Virtual Camera**.
5. Add an OBS **Text (GDI+)** source reading this copy's `obs_output\chest_counter.txt` (the **Overlay** page has the path).

## Tests

| # | Do this | Expect |
|---|---|---|
| 1 | Look through Overview, Game, Console, Analytics, Settings at your usual size, then shrink the window as far as it goes | Nothing cut off or overlapping; scrolling works |
| 2 | In the lobby, **Start counting**, open **Game** | *In the lobby*; Live preview shows the full picture |
| 3 | **Play one whole match** from the lobby, through the bus, to YOU PLACED or Victory, back to the lobby. Open some chests | Status follows along: *Loading*, *Waiting for the match to start*, *In match* with a running clock, *Match over*, *In the lobby* |
| 4 | During that match, compare chests opened with the numbers | CERTAIN / APPROX rise as usual, and OBS shows the same |
| 5 | After it: **Analytics** > **Refresh** | **1 match, Complete**, sensible duration, its chests listed, an ending of YOU PLACED or Victory |
| 6 | **Second match:** press **+1** mid-game, choose a **Why?**, then **−1**, then **Undo** | APPROX changes at once, also in OBS; CERTAIN does not; the line shows the split |
| 7 | **Third match:** **Stop counting** mid-match, wait 30 s, **Start counting** again, finish it | Listed as **Partial**, not Complete; no chest counted twice |
| 8 | **Fourth match:** mid-game, **Stop Virtual Camera** for 20 s, then start it again | App reports the lost video and recovers, or stops with a clear message; the match becomes **Partial**; counts kept |
| 9 | Die and spectate, if it comes up | *Spectating or out of the match*; chests opened by the player you watch are still counted, as before |
| 10 | Analytics: **Not a match** on one match, then **Restore** | Statistics change, then return exactly |
| 11 | Close the app during a match with Task Manager (**End task** on the app) and reopen it | Counts kept; that match shows as interrupted, not complete |
| 12 | Close and reopen normally | Counts, Analytics and corrections are all still there |
| 13 | Switch to the **Default** profile | Its counts and Analytics are separate from `RC test` |

## Pass or fail

**Must pass:** 4, 6, 7, 11, 12, 13, and no crash. A failure here blocks the release.

**Should pass:** 3 and 5. This is the first time a whole real match goes through match tracking. If it is not marked Complete,
send the logs. It can still ship as experimental with that limit written down, if the counts and history were right.

**Your judgment:** 1 and how the new Dashboard and Analytics feel to use.

## Not covered

Portuguese matches, reboots, squads, other modes, and real livestream URLs during a whole match. After this test,
docs should only say what actually happened.
