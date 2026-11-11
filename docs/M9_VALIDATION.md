# M9 validation record

Date: 2026-11-11. Branch `dev/v0.3.0`. The full run and rc1 are from `e44a7e4`, rc2 from `a77847b`, rc3 from `116e5a9`, and rc4,
the current candidate, from `20447a6`. Nothing was pushed, merged, tagged or published, and the production keys were not used.

## Not verified

- **rc4 has not been used by hand yet.** rc2 was, in a real session; see "M9F" below and
  [M9_ACCEPTANCE_TEST.md](M9_ACCEPTANCE_TEST.md).
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
out. Manual corrections are never included. The main rate uses complete and partial matches and needs 5 minutes in total. The
complete-only rate has no minimum. A single match's rate needs 1 minute: the 5-minute rule is for a total, and would hide the
live figure for most of a match.

**Settings audit.** No published version ever wrote `[match]`, so an upgrade from v0.2.3 has made no choice and gets the new
default. An explicit `off` or `shadow` is kept. An invalid value falls back to `off`, so a typo cannot switch history on.

### Quitting a match

The rc2 session shows the state machine already handles this. Match 1 went from play straight to CONNECTING at 05:09:22 and
closed as Partial with 319 s of play and 28 chests. Only its label was unhelpful ("Left or not seen"). It now reads *Left the
match*, *Returned to lobby* or *Next match began*, from what was seen next. It stays Partial, and never claims why.

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

**Proposed fix, not implemented.** In `_maybe_joined_late`, when coming from LOADING, require a counted chest or about 30 s of
health bar before opening a match, giving the countdown text time to appear. Cost: a real reconnect into a match opens up to
30 s later, and is Partial anyway. It would need tests for this sequence, reconnects, back-to-back matches and lobby transitions,
the replay scorecard and one full-video pass. Existing records would not change; **Not a match** handles this one.

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

The one failed check compared the last live number (5) with the final history (6). The sixth chest appears to have finished after the
last status, which goes out once a second. That run's order was not kept, so the 46-status check above replaced it.

**`START_HERE.md` is in `runtime\`, not the root.** Verified against v0.2.3's shipped code: a package with an unknown root file is
refused as a whole ("Unexpected package contents: START_HERE.md"). The same text opens `README.html`, which is in the root.

**Corrected.** The docs said to extract a new version "into the same folder". Each version unpacks into its own folder, so that could
never replace anything. They now say to copy `state` and `config.toml` across. The earlier upgrade test copied files over directly,
so it does prove the data carries over, but it was not that documented step.

## Known issues

| Severity | Issue |
|---|---|
| Medium | False short match on the waiting island when the health bar is read before the countdown text. Fix proposed, awaiting review |
| Medium | Real in-app update, rollback and retry never run; a defect in v0.2.3's installer may force a manual install |
| Low | At the minimum window size, the Analytics table scrolls sideways when labels are long |
| Low | While counting, a correction applies on the next frame, so during a stall it waits |
| Low | The updater's backup covers saved counts and settings, not `state\history\`. Updates leave that folder in place |
