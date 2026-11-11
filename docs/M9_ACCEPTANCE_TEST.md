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
| 14 | **OBS Windowed Projector, with the capture card and Virtual Camera already in use.** Keep OBS holding the card and another program using the Virtual Camera. Right-click the gameplay source > **Windowed Projector (Source)**, at least 1280x720. In the app **Refresh**, pick the projector, **Start counting**, play a match | OBS and the other program carry on undisturbed; Live preview shows only the gameplay; chests count |
| 15 | During 14: put another window over the projector, then minimize it for 20 s, then restore it | Covered: keeps counting. Minimized: the app warns and counts again once restored |
| 16 | During 14: close the projector | Counting stops with a clear message; counts kept |

## Pass or fail

**Must pass:** 4, 6, 7, 11, 12, 13, and no crash. A failure here blocks the release.

**Needed before calling the projector tested:** 14 to 16. Until then the docs keep saying it is less tested.

**Should pass:** 3 and 5. This is the first time a whole real match goes through match tracking. If it is not marked Complete,
send the logs. It can still ship as experimental with that limit written down, if the counts and history were right.

**Your judgment:** 1 and how the new Dashboard and Analytics feel to use.

## Event by event

Totals can match while individual chests are wrong: one miss and one false count cancel out. For the whole match in test 3,
and for test 14, compare each chest:

1. Before counting, set Dashboard > **Console** > **Diagnostic recording** to **Whole session** (about 10 GB per hour).
2. Afterwards, open `captures\<session>\labels.csv`. It has one row per decision. Fill in `truth`: `chest`, `not_chest`,
   `missed_chest` and so on, and add a `missed_chest` row for any chest the counter never noticed.
3. **Settings > Review captures...** compares the decisions with your labels.

| Check | Where it comes from | What counts as a problem |
|---|---|---|
| Misses | `truth` = `missed_chest`, or a real chest counted in neither number | Any, with its time |
| False positives | `truth` = `not_chest` on a counted row | Any, with its time |
| CERTAIN / APPROX | The decision on each `chest` row | A false chest in CERTAIN is serious. A real chest in APPROX only is expected now and then |
| Frame gaps | `session_end` in `logs\session_*.jsonl`: `frames_processed`, `frames_dropped` and `seconds`, about 15 frames per second expected | A big shortfall, or a chest missed during one |

Only one counter runs at a time, so two inputs cannot watch the same match live. To compare inputs, label each one's match
separately and compare miss and false-positive rates, never just the totals.

## Not covered

Portuguese matches, reboots, squads, other modes, and real livestream URLs during a whole match. After this test,
docs should only say what actually happened.
