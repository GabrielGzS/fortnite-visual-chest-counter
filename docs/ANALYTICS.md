# Analytics

New in v0.4.0. The **Analytics** page turns what the app recorded into the numbers that tell you how you are really progressing:

| Number | Tells you |
|---|---|
| **Chests per minute of play** | How fast you loot while you are in a match |
| **Chests per hour** | How fast you progress in real life, with queues, the lobby and breaks included |
| **Chests per day and per week** | How much you really get done, days off included |

Everything comes from the history saved on your PC for the selected profile. It never changes your counts or what OBS shows, and the
numbers on the Dashboard stay your official totals.

## What is counted

Your **chests** here are the chests the app detected, plus your **+1**s and minus your **−1**s, each on the moment you made it. The page
always says how many of them you added yourself.

Left out, on purpose:

- A chest seen while **spectating someone else** after you were out of a recognised match. It is not yours. The page says how many were
  left out.
- **Reset**, **Edit counts** and a **starting count**. They change your total, but they are not chests you opened at that moment.
- Videos you analyse with **Analyse a recording**. They never enter your history.

The history is kept whenever your counts are saved, with match tracking on or off. Match tracking adds the matches: chests per minute,
match bests and the match list need it, the rest does not. History starts with v0.3.0: chests counted with older versions are in your
total but have no date, so Analytics cannot place them.

## Time

| Term | Means |
|---|---|
| **Session time** | From the moment you start counting to the moment you stop, with breaks in it. Counting runs less than 30 minutes apart are one session |
| **Time counting** | Only the time the app was actually counting. The gap between two runs of one session is time that passed, but nobody watched it |
| **Active play** | Alive on the bus or the map in recognised matches. Shown as "at least" when some play was not recognised (another language, an unrecognised mode) |
| **Between matches** | Time counting minus active play: the lobby, queues, the waiting island, after you were out, and breaks |

**Chests per hour** is your chests in sessions divided by your session time. It is never chests per minute times sixty: that would leave
out everything between matches. It needs at least 30 minutes of session time.

## The tabs

### Performance

Choose a period: **Today**, **This week**, **Last 7 days**, **Last 30 days** or **All time**. You see chests per hour and chests per minute
of play side by side, your chests, session time, active play and matches, and a chart of your chests adding up. On the chart, the
shaded stretches are when the app was counting; a flat line outside them is time nobody watched, not time with no chests.

**Where your chests came from** splits them into detected chests and your own +1s (broken chests, missed chests, others) and −1s. Your
+1s and −1s are your reports. Only "a visible chest the counter missed" and "counted something that was not a chest" say anything about
the detector.

Chests per minute of play work as before: complete matches only, five minutes of active play needed, your −1s always count and your
+1s only if you tick **Count my +1s from the Game view**.

### Days & weeks

**Today**, **yesterday**, **this week** (Monday to Sunday), the **last 7** and **last 30 days**, and how many of those days were counted.

On the chart, a **bar** is a day with chests, a **short line** a day you counted with none, and a **ring** a day nobody counted. A day
nobody counted is never treated as a zero: the app does not know what happened on it.

Three averages, over finished days only:

| Average | Divides your chests by |
|---|---|
| **Per day counted** | The days the app was counting, including counted days with no chests |
| **Per day with chests** | The days you got chests |
| **Per calendar day** | Every day since your first recorded day, counted or not. The honest pace for planning; the page says how many of those days were not counted |

**Per week** is the per-calendar-day average times seven. Days run from midnight to midnight in your PC's time zone, daylight saving
included.

### Personal Bests

Your best match, chests per minute, hour, day, week and session, with when it happened and how. They are worked out again every time,
so marking a match **Not a match** or undoing a correction updates them.

| Best | Counts only |
|---|---|
| Most chests in a match | Complete matches |
| Best chests per minute | Complete matches with at least 5 minutes of play |
| Best hour | 60 real minutes all spent counting. A shorter session is never scaled up to an hour |
| Best session pace | Sessions of an hour or more |
| Most broken chests in a match | Complete and partial matches, as you reported them |

A tie goes to the first time it happened. "At least" means part of it was not saved (the app closed unexpectedly).

### History

**Matches**: your last 100 matches, newest first, with **Not a match** and **Restore** as before. When a new match is added, the list
moves to the top; otherwise it stays where you were. If a match ends while the page is open, it appears by itself a few seconds later.

**Sessions**: each session with its session time, time counting, chests, chests per hour and your corrections.

## Good to know

- A session still going counts up to now. A run that ended without a clean stop (a crash) counts only up to the last moment the app
  saved its progress: "at least".
- Each profile has its own history and its own Analytics. A profile that counts someone else's stream only knows the days you watched.
- Your history stays in `state\history\` next to the app, and an update leaves it in place. See [MATCH_TRACKING.md](MATCH_TRACKING.md).
