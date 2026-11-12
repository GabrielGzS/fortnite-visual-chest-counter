# Match tracking and Analytics (experimental)

New in v0.3.0. While the app counts, match tracking follows your Fortnite matches and keeps a history of them on your PC.
The **Analytics** page shows what that history says; v0.4.0's chests per hour, per day and per week and Personal Bests are
explained in [ANALYTICS.md](ANALYTICS.md).

It is **on by default**, and it **never changes your counts or what OBS shows**. CERTAIN, APPROX and the OBS text are exactly
the same with it on or off. To turn it off, untick it in **Settings**; if you already turned it off, it stays off.

## What it can and cannot do yet

- It reads **English** Fortnite screens only. In another language your chests are still counted, but the match status stays
  on *Not sure yet* and no statistics are made up.
- It has been tested on recordings and on a few real matches, one of them recognised from start to finish. That is still
  little evidence, so a match it marks as complete deserves a look.
- Other game modes, reboots and squads have not been tested.
- It uses the picture only, like the rest of the app. It does not read your placement number.

## Settings

**Settings > Match tracking (experimental)** has **Track matches** and **Save progress every**: 30 seconds, 1 minute
(recommended), 5 minutes or 10 minutes. Changes apply the next time you click **Start counting**. Since v0.4.0 your chest history
(each chest and session, for chests per hour and per day) is kept whenever your counts are saved, with match tracking on or off;
match tracking adds the matches.

Matches are followed once a second whatever you choose. That setting only decides how often running totals are
written. A longer interval writes less to the disk, but after a crash more of the last moments count as uncertain.

## Following a match

The Dashboard has three views, switched at the top. Changing view never changes counting.

| View | What it shows |
|---|---|
| **Overview** | Your **lifetime** counts, the video source, **Start counting**, a line with the match status, and a small **Live preview** |
| **Game** | **This match only**: its chests, chests per minute, time played, and a larger **Live preview** |
| **Console** | The **Activity** log, warnings and **Diagnostic recording** |

The status says only what the picture supports: *In the lobby*, *Loading*, *Waiting for the match to start*, *In match*,
*Possibly in a match*, *Spectating or out of the match*, *Match over* or *Not sure yet*.

**Game** counts only chests detected during this match, starting from zero each match, plus the corrections you make there. Your
Overview totals, a **Reset...**, an **Edit counts...** or Overview's **+1 / −1** do not change it. It shows a dash, not a zero, until
the app is sure it is watching a match, and chests per minute appear after a minute of play. If the app joined late or part of the
match was not seen, it says so. The match status and details sit beside the **Live preview**; the numbers and the correction row
follow.

The **Live preview** can be hidden with its button. Only the one on screen updates, and neither affects counting.

## Analytics

The **Analytics** page reads the history of the selected profile. The numbers on the Dashboard stay your official totals. The two
can differ: history starts with v0.3.0, and matches are only recorded with match tracking on. This section is about the match
figures; see [ANALYTICS.md](ANALYTICS.md) for the whole page.

| Quality | Meaning | In the statistics? |
|---|---|---|
| **Complete** | Its start and the end of your part in it were both seen in English, with no break in the video before that end. It does not matter how it ended or how long it lasted: placed, won, or back to the menus | Everywhere |
| **Partial** | The start or the end was not seen: you joined late, counting stopped, or the video was lost | Match time and the rate including partial matches, never the main rate or complete-match averages |
| **Unconfirmed** | No English evidence that it was a real match | Listed only |

CERTAIN and APPROX are always shown apart. APPROX is the best estimate and already includes CERTAIN. CERTAIN needs the strongest
evidence, so on a small HUD it can stay at 0 while APPROX climbs. That is expected.

**Average detected chests / min** is the main number: APPROX chests the app detected by itself, divided by your time actively
playing, across complete matches only. It needs five minutes of active play across those matches together, and until then it says
*Not enough complete matches*. Short matches count, weighted by their length. **Including partial matches** is the same sum with
partial matches added, shown apart and never used in its place. A **−1** made in the Game view counts in both, because it removes a
chest that should not have counted; a **+1** made there counts only if you tick **Count my +1s from the Game view**. Overview's
corrections change only your total. **Broken chests (yours)** shows the broken-chest +1s you made for complete and partial matches,
and how many per complete match: your reports, not something the app detected.

**Recent matches** shows each match's own chests per minute. "seen" means only part of that match was seen, and a dash means
there is under a minute of play, or it is not a confirmed match.

A match still in progress is left out of the match count, match time and chests per minute until it ends. If counting stops
or the app closes during a match, that match becomes partial.

**How a match ended** only says what was on screen. *Placed* and *Victory Royale* were seen. *Left the match* and *Returned
to lobby* mean play went back to the menus with neither on screen: quitting, a disconnect or a missed ending all look the
same, so the app does not guess why. Such a match is still Complete if its start was seen: Complete says what was observed, not how
it went. *Waiting island* marks a record the countdown showed was never a match, and it stays out of the statistics.

**If something else is on screen during a match**, such as a browser page, the app stops counting that time as play after about
10 seconds, and Game shows it as **Unclear**. A hidden health bar alone does not do this, because the compass and the icons beside
the minimap still show the game is there. Such a break does not by itself make a match Partial, and over a minute of it does.

## Fixing mistakes

**A wrong match.** In **Recent matches**, **Not a match** leaves a match out of the statistics, and **Restore** puts it back
exactly as it was. Nothing is deleted, and its chests stay in your totals.

**A wrong chest count.** The **+1** and **−1** buttons next to the numbers on Overview change APPROX by one, also while counting.
In the **Game** view, **−1**, **+1** and **Undo** (*Fix this match*) also belong to the match on screen, or between matches to the one
that just ended; there you choose the reason next to +1 before adding.

- CERTAIN never changes this way, because the counter did not confirm that chest.
- APPROX cannot go below CERTAIN, so **−1** is disabled when they are equal. To correct CERTAIN, use **Edit counts...**.
- A line then shows the split, for example `Detector 231 · Manual +2 · Total 233`, with **Undo**.
- **Why?** is optional:

| Reason | Means | Says the counter made a mistake? |
|---|---|---|
| Not sure / balance fix (default) | You just want the number right | No |
| Broken chest | You broke a chest rather than opened it; counted apart in Analytics | No |
| Fortnite counted it, nothing else to see | Fortnite counted a chest with nothing to detect | No |
| A visible chest the counter missed | The pop-up was on screen and was not counted | Yes |
| Counted something that was not a chest | A false count | Yes |

Chests per minute and per match take your −1s always and your +1s only when you tick **Count my +1s from the Game view**. Chests
per hour, per day and per week include your corrections, like your total, and say how many you made (v0.4.0). **Reset...** and
**Edit counts...** replace the total, so corrections made before them can no longer be undone. They stay in the history.

## Where your data is

Everything stays on your PC, next to the app:

| Path | What it is |
|---|---|
| `state\history\<profile>\matches.jsonl` | Each match and how it went |
| `state\history\<profile>\chests.jsonl` | Each counted chest, and your corrections |
| `state\history\deleted\` | The history of a deleted profile, kept as a backup |

Each profile has its own history. The files are only ever added to, and a damaged line is skipped rather than stopping the
page.

**Updating.** An update replaces only the program files, so `state\` and your history are left in place. If you install by
hand, extract the new zip to its own folder and copy `state\` and `config.toml` into it.

**Going back.** v0.3.0 reads the history v0.4.0 writes. If you return to v0.2.3 or older, your counts, profiles and settings keep
working. Those versions ignore the history files without touching them, and nothing is recorded while you use them.
