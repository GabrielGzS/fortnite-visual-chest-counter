# M9 validation record

Date: 2026-11-11. Branch `dev/v0.3.0`. The full run and rc1 are from `e44a7e4`; rc2, the candidate for hands-on testing, is
from `a77847b`. Nothing was pushed, merged, tagged or published, and the production keys were not used.

## Not verified

- **No person has used this build, and no real OBS Virtual Camera or live Fortnite session has run through it.** See
  [M9_ACCEPTANCE_TEST.md](M9_ACCEPTANCE_TEST.md).
- **A real in-app update from v0.2.3 has not been run**, and neither has a real rollback or retry. It is blocked: see "The
  blue screen" below. Extract-over upgrades were tested instead.
- **No real footage has produced a Complete match.** The English clip ends Partial and the Portuguese one Unconfirmed,
  both as designed. The Complete path is proven on synthetic timelines only.
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

## Known issues

| Severity | Issue |
|---|---|
| Medium | Real in-app update, rollback and retry never run; a defect in v0.2.3's installer may force a manual install |
| Medium | No real full match through match tracking yet |
| Low | At the minimum window size, the Analytics table scrolls sideways when labels are long |
| Low | While counting, a correction applies on the next frame, so during a stall it waits |
| Low | The updater's backup covers saved counts and settings, not `state\history\`. Updates leave that folder in place |
