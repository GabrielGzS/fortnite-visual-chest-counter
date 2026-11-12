## Fortnite Visual Chest Counter v0.4.0 — Public Beta (DRAFT, not released)

The Analytics update. See how fast you really progress: chests per hour of real life, per day and per week, next to chests per minute
of play, plus your Personal Bests.

- Chests per hour, with queues, the lobby and breaks included
- Today, this week, the last 7 and 30 days, and averages per day and per week
- Personal Bests: your best match, hour, day, week and session
- A calmer match status, an easier update notice, and fixes to the match list

Your counts, profiles, settings and history are kept. Update from v0.3.0 with the "Update available" link in the app's sidebar, or
Settings > Check for updates.

<!-- highlights end -->

### What's new at a glance

| New in v0.4.0 | Why it matters |
|---|---|
| **Chests per hour** | Your chests divided by your real session time, breaks included: your true pace, not chests per minute × 60 |
| **Days & weeks** | Today, yesterday, this week, the last 7 and 30 days, averages per day counted, per day with chests and per calendar day, best day and week |
| **Personal Bests** | Best match, chests per minute, hour, day, week and session, each with when it happened |
| **Four Analytics tabs** | Performance, Days & weeks, Personal Bests, History: one question per tab |
| **Chest history always** | Kept whenever your counts are saved, with match tracking on or off |
| **Calmer match status** | Partial is a small note, not large yellow text |
| **Update notice** | A found update shows a quiet line on the Dashboard and in Help & diagnostics; release notes are readable |

### Analytics

**Performance** shows chests per hour beside chests per minute of play, for today, this week, the last 7 or 30 days or all time, with a
chart of your chests adding up and where they came from (detected, or added by you). **Days & weeks** shows your days and weeks; a day
nobody counted is shown as not counted, never as a zero. **Personal Bests** are worked out again every time, so excluding a match or
undoing a correction updates them. **History** lists your matches and sessions; a new match moves the list to the top, and a match that
ends while the page is open appears by itself.

What is counted: the chests the app detected plus your +1s and minus your −1s, always shown apart. Chests seen while spectating someone
else are left out. Reset, Edit counts and a starting count are not chests. Full guide: docs/ANALYTICS.md.

### Also new

- **Match status:** the state at a calmer size and colour; "Partial: joined after the start" as a small note.
- **Updates:** every automatic check is logged in the Console; a found update shows a dismissible line on the Dashboard and an Updates
  card in Help & diagnostics; release notes show their highlights first, as formatted text.
- **Settings:** the match tracking option is now "Track matches"; your chest history is kept either way.

### Known limitations

- History starts with v0.3.0: chests counted with older versions are in your total but cannot be placed on a day.
- Time between matches is known only when matches are recognised (English screens). Otherwise active play shows as "at least".
- A day nobody counted is unknown, not zero: per-calendar-day averages say how many days were not counted.
- The updater's failure and rollback scenarios have not been run on real packages (one real update, v0.2.3 to v0.3.0, succeeded).
- Detection is unchanged from v0.3.0, including its known limits (720p small-HUD start text, the lobby menu with the TREASURE tab).
