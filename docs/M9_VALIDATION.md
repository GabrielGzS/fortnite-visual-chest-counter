# M9 validation record

Date: 2026-11-11. Branch `dev/v0.3.0`. The full run and rc1 are from `e44a7e4`, rc2 from `a77847b`, rc3 from `116e5a9`, rc4 from
`20447a6`, and rc5, the current candidate, from `fd7bc0f`. Nothing was pushed, merged, tagged or published, and the production keys were not used.

## Not verified

- **rc5 has not been used by hand yet.** rc2 and rc4 were, in real sessions; see "M9F" and "M9G" below and
  [M9_ACCEPTANCE_TEST.md](M9_ACCEPTANCE_TEST.md).
- **No footage has a full-screen map or the inventory,** so a switch away from the game moves time out of play but never makes a
  match Partial. See "M9G".
- **A real in-app update from v0.2.3 has not been run**, and neither has a real rollback or retry. It is blocked: see "The
  blue screen" below. Extract-over upgrades were tested instead.
- **Only one real match has been recognised as Complete** so far, in the maintainer's rc2 session. The reference clips end
  Partial (English) and Unconfirmed (Portuguese), both as designed.
- OBS Windowed Projector with a real capture card, and OBS WebSocket with a real OBS on a second PC, remain untested.

## Results

| Check | Result |
|---|---:|
| Test suites (24) | 1,121 of 1,121 pass |
| Mutations (8 runners) | 297 of 297 caught |
| New release-gate sabotage | 7 of 7 caught |
| Frozen detector files against `032df3b` | Identical |
| Full video, repository code, tracking off | Byte-identical to M0 (6 and 24 events) |
| Full video, **packaged build**, tracking on | Byte-identical to M0 (6 and 24 events) |
| Off / shadow / on, first 100 s | Identical |
| Packaged checks from a clean folder | 18 of 19; the other was a false alarm in the check (see below) |
| Extract-over upgrade, forward, back, forward | 17 of 17 |
| Publish gate with a throwaway key | Only "untrusted key", as expected |

The failed packaged check flagged `scipy/stats/_sobol_direction_numbers.npz`. That is SciPy's own data file, which the
build's audit deliberately allows, and it was the only file flagged. Nothing from this project leaked.

The publish gate ran on a copy of the zip in a temporary folder, signed with a key generated for that run and discarded
with it. rc1 itself has no signature file.

## Packaging

The 13 match templates were missing from the build list. They now ship, and the release gate refuses a package without
them or the match modules. Removing any one is caught.

rc1 is `build_out\v0.3.0-rc1\Fortnite-Visual-Chest-Counter-v0.3.0.zip`, 155.9 MB, unsigned. From a clean folder: every
module and template is byte-identical to the repository, the real launcher started the real window, and no development
files or user data are shipped.

rc1 is superseded by rc2.

## rc2

`build_out\v0.3.0-rc2\Fortnite-Visual-Chest-Counter-v0.3.0.zip`, 155.9 MB, unsigned, SHA-256
`a08783ad4b7ffd62527a584841550e5d1984d9b2ee11ec62776bfa34a1379fa3`.

Compared with rc1, exactly five files differ: `README.html`, `gui/app.py`, `input/video_sources.py` and those two modules'
compiled copies. The full-video comparison was not repeated: neither change is on its path, because `simulate` does not use
`LiveSource`, and the frozen detector files are still identical to `032df3b`.

| Check on rc2 | Result |
|---|---:|
| Actual zip from a clean folder: contents, guide, launcher, real counting, corrections, a real kill | 27 of 27 |
| Release gate on contents, sums and keys, with no signature involved | Pass |
| v0.2.3's own shipped code reading rc2's layout, unpacking nothing | Accepted |
| Affected suites, including 23 new stall checks | All pass |
| Affected mutations, including 19 new stall mutations | All caught |
| Real worker and real FFmpeg, stalled 15 s, tracking off and on | Warned at 10 s, cleared on return, reported about 15 s missed, OBS text untouched |
| Screenshots at 1120x800 and 920x640 | Nothing cut off |

At the minimum window size the Analytics table scrolls sideways when labels are long, by up to 170 pixels. The default size
does not. The first fix cut off the Not a match links by a few pixels; the screenshots caught it before rc2 was handed over.

## Real runs of the package

| Test | Result |
|---|---|
| 15 corrections while counting | All applied. APPROX 18 = 5 detected + 14 − 1 undone. CERTAIN 5 unchanged. OBS showed 18 |
| Process killed while counting | Totals kept. Next start recorded that run as interrupted. 0 damaged rows |
| v0.2.3 counted, then v0.3.0 extracted over it | Every user file unchanged. Profiles, counts and settings read correctly |
| v0.3.0 counted on top | 4 → 8. Other profile untouched |
| Back to v0.2.3 with v0.3.0's data | Counted normally, kept totals, left history and `config.toml` alone |
| Forward to v0.3.0 again | Continued. History read with no damage |

## Performance

| Packaged build, 45 s real-time, 3 alternating rounds | CPU, percent of one core | Time per frame |
|---|---|---|
| v0.2.3 | 47.9 to 49.0 | 10.7 to 11.0 ms |
| v0.3.0 | 48.4 to 49.6 | 10.6 to 11.4 ms |

Both held 15 pictures per second. Tracking itself cost 0.37% of a core. An earlier reading of about 70% for both modes came right after extraction and did
not repeat; whole-process readings swing with load.

## The intermittent OBS test

Fixed in the test's fake server, and the assertion is unchanged. It closed the socket from a second thread while its own
read was blocked. On Windows that resets the connection and destroys the close frame, so the client saw `WinError 10054`
and not the kick code. Before: 15 of 40 runs failed. After: 0 of 120. Real OBS completes the close handshake, so the
program was not at fault.

## Streamer-readiness audit

From Codex's read-only audit, added to M9 by the maintainer.

### Documentation (done)

Windowed Projector steps and OBS WebSocket setup, including another PC, are now in the packaged guide. Same-PC file output
says why it needs the same PC. Livestream URL no longer claims the count is complete but delayed: it is described as a
lower-confidence convenience option. The acceptance test gained a real projector test and an event-by-event comparison.

### Stale input status

**Verified, by running the real worker with a real FFmpeg.** FFmpeg read from a local socket that stayed open with no data
for 15 s:

- The worker stayed alive and sent **no message at all** during the stall, with tracking off or on.
- No warning appeared, and FFmpeg did not exit.
- The next status arrived only when video resumed, reporting 1.6 pictures per second.

**Verified, by reading the code.**

- `LiveSource.frames()` waits one second at a time and loops forever with no check of how long it has been.
- Status, notices and syncing all sit inside the per-frame loop, so all of them stop.
- The Dashboard redraws the last status every tick, so it keeps saying "analysing 14.9 pictures/s" and "Counting" while the
  clock runs.
- With tracking on, the match line changes to "No video right now" after 5 s. With it off, nothing changes.
- Livestream URL is not affected: `StreamSource` has its own 10 s buffering notice.
- The app has no pause feature, recorded video reaches end of file, and Stop exits the wait.

**Assumed, not reproduced.** Which real inputs do this. A capture card losing signal or being unplugged may stall this way.
OBS Virtual Camera may instead send a placeholder picture when stopped, which would be a different symptom and would not
trigger the warning. Test 8 of the acceptance plan will show which.

**Fixed in rc2**, in the idle branch of `LiveSource.frames()` only:

- After 10 s without a new picture, the app says it is not receiving video, and does not guess why. When pictures return, the
  warning clears and it reports how long was not received and that chests may be missing.
- The Dashboard shows **No video**, and the old rate is cleared.
- No restart and no detector change. The check runs only when no frame is delivered, so it cannot affect a counted frame. The
  OBS text is not touched.
- It covers live inputs only, not the `file` source. `video` and `simulate` use a different class. End of file and Stop leave
  the loop before the check, and a hitch under 10 s stays silent.

## The blue screen

**What the evidence shows.** One bugcheck in the log: `0x101` CLOCK_WATCHDOG_TIMEOUT at 00:39 on 2026-11-09, during the first
real staging run. Its parameters name logical processor 18. It means one CPU stopped answering clock interrupts.

- No WHEA hardware errors are logged, and no disk errors around that time.
- The CPU is an i9-13900KF, on microcode `0x12B` and a BIOS from October 2024. VirtualBox is installed and VMware kernel
  drivers were loaded when last checked.
- Windows has not rebooted since. That span includes today's full test runs, 3 package builds and 7 full unpacks of the
  5,000-file package with real-time scanning on, with no crash.

**What it does not show.** The cause. A normal program cannot directly stop a CPU answering interrupts, which points to the CPU,
firmware or a kernel driver, with heavy work as a possible trigger. That is an inference, not a finding. The minidump
(`C:\Windows\Minidump\110926-11218-01.dmp`) needs administrator rights and was not read. Today's unpacks are not the same
operation as staging, which also reads everything back and runs the staged program.

**Decision: not run.** There is no credible explanation or mitigation yet, and no safe isolation on this PC. The only VM is
Ubuntu, which cannot run the Windows updater, and Windows 11 Home has no Sandbox. A Windows VM would protect data but not the
host from this kind of crash, because the guest runs on the same CPU. No test key was generated for this.

**What is covered without staging.** The updater code is unchanged since v0.2.3, passes 102 install checks on small synthetic
installations, and v0.2.3's shipped code accepted rc2's layout. Extract-over upgrades passed in both directions.

## M9F: hands-on feedback on rc2

**rc3:** `build_out\v0.3.0-rc3\Fortnite-Visual-Chest-Counter-v0.3.0.zip`, 155.9 MB, unsigned, SHA-256
`d4ba5aca59a80872b8ffd8b253eaae0541187b445a7e81a2b506332411070fb5`.

Added: live per-match numbers on Game, a preview on Overview, match tracking on by default, a per-match rate in Recent
matches, chest types in the log, clearer Analytics, and endings that say where play went. `match_state.py`, the detector and the
updater are unchanged.

| Check on rc3 | Result |
|---|---:|
| Actual zip from a clean folder, including the default path with no options | 24 of 24 |
| Live numbers against the stored history, real worker | Equal (6 and 6) |
| A manual +1 during a match | Reached the total, not the match |
| Full video, packaged, tracking on | Byte-identical to M0 (6 and 24 events) |
| Affected suites, including 78 new checks | All pass |
| Affected mutations, including 50 new ones | All caught |
| Screenshots at 1120x800 and 920x640 | Nothing cut off; Overview and Game fit at the default size |

**Preview cost**, packaged, three alternating rounds: 48.2 to 61.2% of a core with it on, 48.0 to 64.1% with it off, so no
measurable worker cost. Drawing takes 0.26 to 0.89 ms per picture, under 0.5% of a core.

**How the rates are calculated** (read from `match_analytics.py`, unchanged). Both divide chests credited during active play by
active seconds. Active time counts only usable pictures while alive on the bus or map, so frozen, black and spectating time is
out. Manual corrections are never included. The main rate used complete and partial matches and needed 5 minutes in total; the
complete-only rate had no minimum. *Changed in M9G: the main rate is complete matches only, with the 5-minute minimum.* A single match's rate needs 1 minute: the 5-minute rule is for a total, and would hide the
live figure for most of a match.

**Settings audit.** No published version ever wrote `[match]`, so an upgrade from v0.2.3 has made no choice and gets the new
default. An explicit `off` or `shadow` is kept. An invalid value falls back to `off`, so a typo cannot switch history on.

### Quitting a match

The rc2 session shows the state machine already handles this. Match 1 went from play straight to CONNECTING at 05:09:22 and
closed as Partial with 319 s of play and 28 chests. Only its label was unhelpful ("Left or not seen"). It now reads *Left the
match*, *Returned to lobby* or *Next match began*, from what was seen next, and never claims why. *Changed in M9G: with its start seen,
such a match is Complete.*

### The 9-second match

**Verified from the stored history. Cause: a false match on the waiting island.**

| Time | Source time | What happened |
|---|---:|---|
| 05:10:16 | 428.7 | CONNECTING |
| 05:10:22 | 434.9 | Health bar first seen: the waiting island has a HUD |
| 05:10:26 | 439.0 | Health bar in 5 of 8 samples and no text yet, so the rule for joining a match in progress opened match 2 |
| 05:10:31 | 443.1 | WAITING FOR PLAYERS first read |
| 05:10:32 | 445.2 | Text confirmed, match 2 closed, countdown begins |

It is not a duplicate or a session boundary: it is mid-run, holds no chests, and does not overlap match 3 (0.00 s between them).
At the other two game starts in this session the text was read first, so this is a race. It counted as Partial because the
WAITING FOR PLAYERS text arrived just before it closed and supplied the English evidence.

**Proposed fix, implemented in M9G.** Use evidence, not a delay. WAITING FOR PLAYERS only appears before a game, so
when it closes a match that opened on a health bar straight after a loading screen, with no chest counted in it, that record was the
waiting island. It is marked Unconfirmed, which keeps it in history for diagnostics and out of every statistic. Nothing waits, so
a real reconnect opens exactly when it does today. About 8 lines in `match_state.py`.

Tried on a private copy of the code, against today's state machine:

| Situation | Result |
|---|---|
| The recorded sequence (health bar 8 s before the text) | Partial becomes Unconfirmed; the real match that follows stays Complete |
| Reconnect into a running game, with or without chests | Unchanged, same opening time |
| A chest counted in it, then a countdown | Unchanged |
| Normal start, quit to lobby, joined late with no loading screen | Unchanged |
| 5 recorded timelines | Byte-identical |
| Match state, audit, replay, tracker, recording, analytics, live match suites | All pass |

**Limit.** None of the 5 recorded timelines contains this race, so the fix is proven only on a reconstruction of the timestamps
from one real session. Existing records would not change; **Not a match** handles this one.

**The 12-minute Complete match is genuine.** Countdown from 445.2, bus at 460.9, YOU PLACED read at 1186.5 (score 0.978), then
ELIMINATED BY and CONNECTING. Duration 725.6 s, 53 English chests, no break.

## Packaging hotfix: extraction in Windows Explorer

**rc4:** `build_out\v0.3.0-rc4\Fortnite-Visual-Chest-Counter-v0.3.0.zip`, 155.8 MB, unsigned, SHA-256
`0d9d557d115d35989e065b5ddb83498a4b087ede7198475ebc54c3ebbb147e0b`.

**Cause.** Explorer's Extract All puts a folder named after the zip in front of each entry. Extracted in place from
`build_out\v0.3.0-rc3`, the longest entry reached exactly 260 characters. Measured with Explorer's own zip engine: a file at 259
characters extracts and one at 260 does not. A folder over 247 also fails.

| | rc3 | rc4 |
|---|---:|---:|
| Longest entry in the zip | 140 | 130 |
| Deepest folder | 120 | 120 |
| Files | 5,044 | 5,030 |
| Zip size, bytes | 155,903,551 | 155,826,641 |

**Removed, 15 files.** `lxml/isoschematron` (XML schema validation, 11 files): Streamlink and the program never import it, shown by
importing every program module and all Streamlink plugins. 4 compiled caches over the budget: 3 from SciPy, 1 from a Trio test.
Their sources stay, and Python compiles them in a few milliseconds. The version folder, `runtime\lib` and the official Python
stay as they are: v0.2.3's updater requires that layout.

**Prevention.** The build and the publish gate refuse any file over 130 characters or folder over 120, which leaves room for a zip
in a folder of up to 90 characters.

**Verified.** The whole zip went through Explorer's engine at the very edge of that budget (longest path 257). All 5,030 files
arrived intact, and the program started and counted from that folder. An earlier run at a tighter edge lost one file, which is how
the folder limit was found.

| Check on rc4 | Result |
|---|---:|
| Actual zip from a clean folder | 24 of 25, see below |
| Each of 46 live statuses against the chests finished before it, real worker | All agree |
| Release gate, unsigned, with the final budget | Pass |
| v0.2.3's own code reading rc4's layout | Accepted |
| Release tests / sabotage of the new protections | 68 of 68 / 11 of 11 |

The one failed check compared the last live number (5) with the final history (6), expecting them to be equal at shutdown. That
expectation was wrong, and the discrepancy was then reproduced on purpose. Counting was stopped just after a chest, three ways, on
rc4: by duration twice and by Stop once. Each time the chest finished after the last status (live 2 or 3, final 3 or 4), and all
of these agreed event by event: the saved totals, the app's final message, the three OBS files, the session log, the history
(no duplicates, no gaps, no damaged rows), the run's closing totals, Analytics, and the numbers after reopening. So a chest in the
last second of a session can be missing from the final live status only, and is not lost or counted twice.

**`START_HERE.md` is in `runtime\`, not the root.** Verified against v0.2.3's shipped code: a package with an unknown root file is
refused as a whole ("Unexpected package contents: START_HERE.md"). The same text opens `README.html`, which is in the root.

**Corrected.** The docs said to extract a new version "into the same folder". Each version unpacks into its own folder, so that could
never replace anything. They now say to copy `state` and `config.toml` across. The earlier upgrade test copied files over directly,
so it does prove the data carries over, but it was not that documented step.

## M9G: final recognition fixes and rc5

**rc5:** `build_out\v0.3.0-rc5\Fortnite-Visual-Chest-Counter-v0.3.0.zip`, 155.8 MB, unsigned, SHA-256
`9d953e0661322e8849902bdaf9cb730766aab80f5fefd09c4258d3d3a0f45765`, built from `fd7bc0f`. It keeps rc4's Explorer fix.

From the maintainer's hands-on test on a streamer's broadcast (captures `20261111_071106`, a private copy used here). Commits `7f50f5b`,
`2ab3cdd`, `e3ed346`, `3d09066` and `fd7bc0f`. The detector, its templates and the updater are unchanged.

### Why that stream had no complete match and 0 CERTAIN

The streamer draws the HUD at about 0.78x. WAITING FOR PLAYERS and the bus countdown were on screen, but the templates scored under 0.3,
so every game read as *joined late*, and the waiting island counted as play. All 83 chests were small-HUD pop-ups, which are APPROX only
by design, so 0 CERTAIN was correct.

**Fix:** one more template at that size for each of the two sentences, through the existing signal table. No new matcher.

| Method, on 2,358 frames | Small HUD, waiting / bus | Highest on wrong screens | Cost, both cues |
|---|---|---|---|
| Normal template only | 0.17 to 0.19 / 0.14 to 0.17 | 0.21 / 0.27 | 0.17 ms |
| **Small-size template (chosen)** | **0.92 to 0.98 / 0.93 to 0.99** | **0.34 / 0.30** | **+0.11 ms** |
| Scale search, plain | 0.67 to 0.70 / 0.53 to 0.57 | 0.35 / 0.36 | 1.36 ms |
| Scale search, blurred | 0.82 to 0.86 / 0.82 to 0.85 | 0.63 / 0.56 | 3.44 ms |

### Complete, by what was observed

A match is Complete when its start was seen and the player's part in it ended on screen, for any reason: placed, won, eliminated and
left, or back to the menus. There is no minimum length. Partial means the start or the end was not seen. Video stopping is not an
ending. How it ended stays a separate field and is never guessed. A record the countdown proves was the waiting island is Unconfirmed,
with no timer involved (the proposal in "The 9-second match" above).

### Is the game still on screen?

The maintainer asked whether the minimap, compass and hotbar could tell gameplay from something else. Average edges over many seconds
of play leave only the fixed shapes. Templates were built from one source per HUD size and judged on the others.

| Piece of the HUD | Browser pages, highest | Held-out play, 10th percentile | Verdict |
|---|---:|---:|---|
| Stat icons beside the minimap | 0.19 | 0.54 | Used |
| Compass arrow | 0.00 | 0.41 | Used |
| Minimap frame | 0.28 | 0.39 | Left out: too close |
| Map pin | 0.65 | 0.41 | Left out: browser pages score higher |
| Hotbar | 0.18 | 0.16 | Left out: it moves with the selected slot |

With the two used pieces: held-out play 162 of 162 seen, browser pages 0 of 36, waiting island 55 of 58. Over 1,447 s inside matches the
longest stretch with nothing of the game in view was 3 s; the two browser pages ran 18 s and 20 s. The jump in the picture when the page
appeared (76) is within ordinary play (99th percentile 66) and below a real loading screen (82), so it is not used. Lines 0.8x to 1.25x
of the chosen ones give the same results.

What it does: the HUD keeps a match alive without a health bar, and after 10 s with nothing in view that time moves from play to
uncertain. It never opens or closes a match, because the waiting island has the same HUD.

**Not done, deliberately:** making such a match Partial. No footage contains a full-screen map or the inventory, so it cannot be shown
that they would be told apart from a browser page. Acceptance test 26 asks for that footage.

### Before and after on the real clip

| | Before | After |
|---|---|---|
| Waiting island | Read as play, joined late at 1769.5 | Read as pre-game at 1766.5 |
| Play starts | 1765.5 | 1785.5 |
| Start seen | No | Yes |
| Active time | 54 s | 34 s |
| Quality | Partial | Partial, correctly: the recording stops mid-match |
| The clip's one chest (1818.1) | In that match | In that match |
| Browser page inside an open match | 151 s active, 2 s unclear | 135 s active, 18 s unclear, "game not in view" |

The last row first showed no change. A still page reads as a frozen picture now and then, which restarted the count, so 18 s split into
9 s and 6 s. Fixed in `fd7bc0f`, with a test copying the real sequence.

### Interface

Overview and Game: CERTAIN left, APPROX right, same colours, both highlight on an increase. Game has one live rate, APPROX per minute.
"Since counting started" replaces "Since the app joined this match". Console keeps CERTAIN and APPROX under Mark moment, and chest types
have their own colours. The main Analytics rate uses complete matches only and needs 5 minutes of active play across them, as total
chests over total minutes. **Including partial matches** is shown apart and never stands in for it.

### Validation

| Check | Result |
|---|---:|
| Test suites (26) | 1,280 of 1,282; the other 2 are timing budgets that failed under load and passed on rerun |
| Mutations (11 runners) | 418 of 418 caught |
| Cue evaluation | Accepted: every signal passes, p99 8.9 ms against a 10 ms budget |
| HUD evaluation, held-out footage | Accepted (above) |
| Frozen detector files against `032df3b` | Identical |
| Full video, repository and **packaged**, tracking on | Byte-identical to M0 (6 and 24 events) |
| Recorded timelines | Same match events as before |
| rc5 from a clean folder | 24 of 25: the known last-second gap below |
| Windows Explorer's engine, folder at the edge of the budget | 5,036 files, none missing or damaged, longest path 257, then counted |
| Screenshots at 1120x800 and 920x640, packaged | Nothing cut off |

The one failed package check compares the final live status with history. The sixth chest is at 83 s of an 85 s run and is finalised
after the last status, the case explained under "M9F" above. History and Analytics have all 6.

**Timing under load.** Fortnite was running at about 65% CPU throughout. Measured with old and new code interleaved, tracking costs
0.26 to 0.46% of one core on real footage (before: 0.24 to 0.40%). The worst painted frames cost 0.82% with a health bar and 0.87%
without, against a 1% budget. Inside the test suite the same measurement read up to 0.3 points higher, from what earlier tests leave
in the process, so the budget tests now measure in a fresh one with the same line. Two exact savings: the HUD is read only when no health
bar, chest or text shows the game, and a box with too few edges is not compared.

### Limits

- The small-HUD templates come from one streamer; other sizes are untested.
- No footage shows an end screen at the small HUD, so it is not known whether YOU PLACED is read there. Leaving through the menus
  completes a match either way.
- Short Complete matches now exist, so the per-match minimum for a rate in Recent matches (1 minute) matters more.

## M9H: rc5 acceptance failures

**rc6:** `build_out\v0.3.0-rc6\Fortnite-Visual-Chest-Counter-v0.3.0.zip`, 155.8 MB, unsigned, SHA-256
`99e5ca5031e209165ea666a240a4ead19971916907777956451f65222905cb4e`, built from `f8e3251` (commits `e82453e`, `8d30c78`, `f8e3251`).
Package checks only: Defender found nothing; extracted to a clean folder, the packaged program counted the retained 720p clip's two
chests (rc5: none) and the 1080p clip's seven, two of them CERTAIN, with the corrected console wording. For hands-on acceptance.

From the maintainer's rc5 test (`captures\20261111_231622`, desktop capture of a 1080p browser showing Thiefs' stream, read only) and
two short captures of the same live stream through the URL input at 720p (15 min in all; only the verified windows were kept, in
`samples\cases\`). Every chest below was checked frame by frame. Development tests only; no release validation was run.

### A chest counted in the total but not in the match

**Cause (confirmed):** the detector finishes a chest about 2 s after it appears. A chest that showed a match was being played opened
it at the next sample, 2.3 s later, and both the Game view and Analytics credit a chest only from the match's opening time. So the
very chest that opened the match was left out (E0001 at 0.48 s, match from 3.27 s; E0002 at 1.00 s, match from 3.33 s), while the
match record itself counted it. **Fix:** a match opened by a chest is dated from that chest's own time, never back into a menu or
loading screen or the previous match. Checked end to end through the live loop, history and attribution: chest at 1.08 s, match
from 1.08 s, credited.

### Lobby read as a short match

**Cause (confirmed):** in a party, the lobby shows blue PARTY CHANNEL tiles exactly where a 0.78x HUD draws the health bar, and they
pass the shield-colour test. After CONNECTING they gave 130-285 "bar" pixels for 26 s and 38 s (rc5) and opened a match. A third case
came from the lobby itself in the stream capture. Over the M9H footage all 67 menu samples with a bar were blue only, while 123 of 126
in play had the green health bar (the other 3: a thin shield bar at low health). **Fix:** only the green health bar may open a match;
the shield bar alone still keeps an open match going. No minimum duration. Replayed on all three phantoms: none opens; real late
joins, the waiting-island rule and the countdown start are unchanged.

**Also found, not fixed:** the lobby menu is not recognised on the current lobby. A TREASURE tab (and PASSES while it loads) moves
LOCKER, QUESTS and CAREER 100 px or more from where the words are looked for. Searching the whole bar finds them (0.81-0.93, other
screens at most 0.34; 15 matchmaking frames of the M9G footage turned out to be unlabelled lobby frames), but costs 2.9 ms more per
sample and broke the 10 ms budget, so it was reverted. Leaving still shows CONNECTING, which closes the match, so nothing depends on it now.

### Small-HUD chests: CERTAIN never, and many missed at 720p

| Verified chests (new pop-ups) | rc5 | Now |
|---|---:|---:|
| 1080p desktop capture, rc5 footage | 3/3, 0 CERTAIN | 3/3, 2 CERTAIN |
| 720p stream, lossless recording | 1/7 | 6/7 |
| 720p stream, standard-quality recording (replayed) | 4/27 | 25/29 |
| Duplicates / counts on anything not a chest | 0 / 0 | 0 / 0 |
| Existing cases (11, four streamers and HUD sizes) | 28/28, 0 duplicates, 0 false | the same |

**Causes (confirmed):** CERTAIN was impossible by rule: every small-HUD pop-up was forced to MEDIUM. At 720p the 22 x 7 px word
loses its exact shape (the stream's colour is stored at 640 x 360), so the exact match of real chests fell to 0.59-0.78, under the
0.75 trigger, while the blurred match stayed 0.86-0.94.

| Score of the small word | Real chests, 1080p | Real chests, 720p | Anything else, highest |
|---|---:|---:|---:|
| Exact | 0.81-0.92 | 0.59-0.78 | 0.62 (PS5), 0.61 (Thiefs) |
| Blurred, at that place | 0.95-0.98 | 0.86-0.94 | 0.865 (PS5), 0.86 (Thiefs) |

Anything else = every frame of the English and PS5 reference videos (25 min, normal HUD) and every frame of Thiefs' footage outside a
verified chest. **Fixes:** the exact trigger is 0.60 and the blurred confirmation stays 0.90, so the blurred match now decides. A new
small-HUD pop-up is HIGH (CERTAIN by default) when the exact match is at least 0.85 and the blurred at least 0.95, the normal word's
own HIGH line with a second condition (non-chests: 0.62 / 0.865). Stacked steps stay APPROX only, as before. A lower trigger made one
duplicate possible: a 0.6 s full-screen map hid a pop-up and it was counted again when it came back. A pop-up lasts about 2 s, and
separate ones began 2.33 s or more apart, so the same word at the same place within 2 s of an onset is the same pop-up.

New cases: `thiefs_720p_stream_chests` (0/3 before, 3/3), `thiefs_720p_map_flash` (counted twice without the 2 s rule, once with
it) and `thiefs_1080p_small_hud` (7/7, CERTAIN 0 before, 2 now). Normal-HUD videos are unchanged by construction: no frame of them
reaches 0.90 blurred, so the small channel can never fire there.

The console described every scaled pop-up as "large-HUD ... drawn larger than usual (approx only)", small-HUD ones included; it now
names the HUD size and says "approx only" only when it is true.

**Limits:** one streamer and one HUD size. At 720p nothing reaches CERTAIN, so it stays APPROX. On the standard-quality recording,
stacked steps were found 4 of 8 times (live, on the stream itself, 3 of 4). The capture tool's "standard" quality changes small-HUD
scores enough to change decisions (11 counted live, 7 on replay with rc5's rules), so small-HUD evidence should be recorded lossless.

### Not fixed: 720p match start

On the 720p stream, WAITING FOR PLAYERS scored 0.61-0.64 and the bus countdown 0.55-0.60 (1080p: 0.92-0.98), so the start was read
as joined late and that match can only be Partial. Counting is unaffected. A 720p template would come from the single island in this
footage, so its real accuracy could not be measured on held-out footage; left for review.

### Tests run (development only)

| Check | Result |
|---|---:|
| Match state, tracker, defects, cues, live match, recording, replay (incl. new tests and a real-footage party-lobby fixture) | all pass |
| Cases, unit (fixtures) | 16/16 |
| Cases, full frames (14) | 39/39 found, 0 missed, 0 duplicates, 0 false |
| Release, input stall, match history, Analytics | all pass |
| Cue evaluation | unchanged (the bar search was reverted) |
| English and PS5 full videos | not rerun: covered by the measurement above |

## M9I: after the rc6 test on Replays' stream

**rc7:** `build_out\v0.3.0-rc7\Fortnite-Visual-Chest-Counter-v0.3.0.zip`, 155.9 MB, unsigned, SHA-256
`03d375f99f434c48276349180ed7f6fab5193063f8d90b652749542080f465b6`, built from `b7a931d` (commits `5982c83`, `b7a931d`). Package checks
only: Defender found nothing; from a clean folder the packaged program counted the retained 720p clip (2 chests, as rc6), and its own
window rendered the new Game view and Analytics page at 920 x 640 with nothing cut off. The chest detector is unchanged since rc6.

Chest counting and match tracking held up on a second streamer at normal HUD, 1080p. Two things remained, both about what the history
claims rather than what the detector sees.

### A 38 s "match" between two real ones

**Cause (confirmed from the session log):** WAITING FOR PLAYERS was read once (565.9 s), then the island's text went unread for 36 s
(the known weakness of white text over bright sky). After 15 s with no countdown the bus was *guessed* to have left, and a match was
opened. At 602.4 s LAUNCHING IN proved the bus had not left; the record was closed as Partial and the real match began after it.
**Fix:** a match whose start was only guessed by the 15 s fallback (the bus never seen leaving), that a countdown then closes with no
chest and no ending, was the waiting island: the rule M9G already had for a late join after a loading screen. Such a record stays in
history, but Analytics leaves it out of the match count, the list and every statistic, and its time is no one's play time. No minimum
duration and no chest count decide it: a match with a chest, or whose bus was seen leaving, is never second-guessed.

### Manual chests in the Game view

The Game view has −1, +1 and Undo for the match on screen (or, between matches, the one that just ended). They are Overview's own
correction: the running session applies it, APPROX changes, CERTAIN never does, Undo and reasons work the same, and the history row
now also names the match. In that match a manual chest is shown as manual ("incl. +2 manual"), never as a detected type.

| | Count shown (Game, Recent matches) | Statistics (chests per minute, per match) |
|---|---|---|
| Detected chest | yes | yes |
| Your −1 for a match | yes | yes: it takes off a chest that should not have counted |
| Your +1 for a match | yes | only with "Count my +1s" ticked on Analytics (off by default) |
| A correction on Overview | your total only | no |
| A correction for what turned out to be the island | your total only | no |

### Why a chest was added: broken chests

Every +1 keeps its reason as a fixed id, so later wording never changes history: `manual` (not sure / balance fix, the default),
`broken_chest`, `missed` (a visible chest the counter missed) and `not_visible` (Fortnite counted it, nothing else to see). The Game
view chooses it next to +1; the default claims nothing, because these records will feed later statistics, and a chosen reason stays
chosen for the next chest. Only `missed` and `false_positive` are claims about the detector. Analytics shows **Broken chests (yours)**:
the broken-chest +1s made for complete and partial matches, and their average per complete match, labelled as reported by you. No
estimate or correction factor is derived from them yet (v0.4.0 material).

Rendered at 920 x 640 and 1120 x 800: the first version of the Game row and a fourth tile on the Analytics row pushed both pages wider
than the window; the row was shortened and the tile given its own row, and nothing is cut off now. At the maintainer's request the
Game view was also rearranged to make room: the match status (on its title's line; its fixed explanation is the card's tooltip, idle
messages still show) and the five details in a 3 + 2 grid now sit beside the live preview, which no longer takes a row of its own;
the counts, the correction row and the last match follow. With the preview off its column shrinks to the toggle. Cards and tiles there
have less padding. Other pages are unchanged, and every view still fits 920 x 640 without sideways scrolling (the existing check).

### Tests run (development only)

| Check | Result |
|---|---:|
| Match state (incl. the rc6 sequence and its two counter-cases) | 119/119 |
| Analytics (island, counts, rates with and without +1s, island correction, broken chests) | 61/61 |
| Corrections, counter and window (match kept and undone, bad match refused, Game view, targeting between matches and after a restart, rate, checkbox, reasons) | 82/82 |
| App, Dashboard views (incl. fit at 920 x 640), match UI, live match, release, update window, history, tracker | 30, 27, 50, 88, 78, 70, 98, 68: all pass |
| Mutations: corrections, Analytics, match UI, live match, Dashboard, match state | 58/58, 51/51, 41/41, 59/59, 25/25, 36/36 |

## Known issues

| Severity | Issue |
|---|---|
| Medium | A switch away from the game is left out of play time but does not make the match Partial, until footage of the full-screen map and inventory exists |
| Medium | At 720p the small-HUD start text is not read, so those matches are Partial (M9H) |
| Low | The lobby menu is not recognised while the TREASURE tab is shown; leaving still ends the match through CONNECTING (M9H) |
| Low | Small-HUD start text has been checked on one streamer only |
| Medium | Real in-app update, rollback and retry never run; a defect in v0.2.3's installer may force a manual install |
| Low | At the minimum window size, the Analytics table scrolls sideways when labels are long |
| Low | While counting, a correction applies on the next frame, so during a stall it waits |
| Low | The updater's backup covers saved counts and settings, not `state\history\`. Updates leave that folder in place |
