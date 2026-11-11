# M9 validation record

Date: 2026-11-11. Branch `dev/v0.3.0`. Tests and rc1 were built from `e44a7e4`. Nothing was pushed, merged, tagged or
published, and the production keys were not used.

## Not verified

- **No person has used this build, and no real OBS Virtual Camera or live Fortnite session has run through it.** See
  [M9_ACCEPTANCE_TEST.md](M9_ACCEPTANCE_TEST.md).
- **A real in-app update from v0.2.3 has not been run**, and neither has a real rollback. Extract-over upgrades were
  tested instead. The kit is prepared, but it signs a copy of the RC with a test key, so it needs the maintainer's approval.
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

`packaging/README.html` changed after rc1 (streamer audit below), so rc1's offline guide is out of date.

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
OBS Virtual Camera may instead send a placeholder picture when stopped, which would be a different symptom. Test 8 of the
acceptance plan will show which.

**Severity: medium.** The number stays correct for what was seen, but chests during a stall are lost with nothing to say so.

**Proposed fix, not implemented.** In the idle branch of `LiveSource.frames()` only:

- After 10 s without a picture, warn once. When pictures return, say how long was not seen.
- A new "no video" state shows on the Dashboard, and the frozen rate is cleared.
- No restart and no detector change. The check runs only when no frame is delivered, so it cannot affect a counted frame.
- It is enabled only for live inputs, not the `file` source. `video` and `simulate` use a different class. End of file and
  Stop leave the loop before the check. Startup is already covered by `open()`, and a hitch under 10 s stays silent.

## Known issues

| Severity | Issue |
|---|---|
| Medium | Stale status during an input stall (above) |
| Medium | Real in-app update and rollback never run; a defect in v0.2.3's installer may force a manual install |
| Medium | No real full match through match tracking yet |
| Low | At the minimum window size, the Analytics table cuts off its Started, Duration, CERTAIN and APPROX columns. Fine at the default size |
| Low | While counting, a correction applies on the next frame, so during a stall it waits |
| Low | The updater's backup covers saved counts and settings, not `state\history\`. Updates leave that folder in place |
