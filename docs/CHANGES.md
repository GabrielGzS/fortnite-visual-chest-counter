# Change and validation notes

This is the living implementation and review document for the desktop pull request. Update this page when the branch
changes; the pull request links here. Versioned release notes describe published releases.

## Changes

- Add French HUD detection and multi-frame classification for normal, Rare and Sprite chests. Deduplicate
  overlapping readings and retain an unknown type for ambiguous openings.
- Follow French qualified lines when notifications reflow around ammo/upgrade messages. Keep the XP gate and three
  stable readings, retain quantities across capture pauses, and rearm only after an observed disappearance.
  Keep a qualified chest's known type independent of another generic line as the stack moves.
- Keep one capture per app. Improve HDR-to-SDR handling and preview delivery, keep the original SDR colour path,
  and cap live preview at 5 FPS independently of the detector's 5/10/15 FPS settings.
- Close video pipes and reap stopped FFmpeg encoders and decoders, including command-wrapper shutdown, so recording
  and review cleanup does not race Windows file locks. Keep the console stop path nonblocking and bound stop waits.
- Replay diagnostics using the original recorded frame intervals. Keep video playback positions separate from the
  detector clock, so irregular live capture does not change temporal confidence or deduplication rules on replay.
- Canonicalize process paths during update safety checks, so Windows short-name and junction aliases cannot hide
  a running program inside the runtime or staged package.
- Separate confirmed openings, estimated-only openings and Total in the Dashboard. Use Total and the manual
  multiplier for the Pirate Token estimate.
- Use a Material 3-inspired Qt interface with Google Sans, a left navigation rail, connected actions, themed
  dialogs and animated chest variants. Configure overlay wording, chest types, drop chance, saved match count and
  screen-share visibility.
- Add local match history, batch deletion, local log-based start and finish, and automatic mode detection with
  a manual selector.
- Put sharing and bot setup together in Group. Add Host and Guest roles, one published leaderboard, Discord
  match reports and team matching by verified session fingerprint.
- Stagger Group clients and share a webhook cooldown across submissions and shared-board requests. Respect Discord retry/reset delays, retain queued results and avoid blocking the UI.
- Share coalesced current-match updates, recover edited live feed messages after reconnect and keep final saved results authoritative. Add matching team participants and totals to local history.
- Show personal, verified team and cumulative match totals with boost-aware Pirate Token estimates. Add overlay transparency and custom headings and multiline templates for Personal, Team and All matches, including cumulative match count.
- Use one section editor and renderer for the floating overlay, Dashboard preview and managed OBS text file. Remove
  the old layout radios. Apply global optional-statistic checkboxes consistently and reconcile worker counts with
  the latest shared context without duplicating a saved/current match.
- Publish the same detailed leaderboard from the app's channel dropdown or Discord's `/leaderboard publish:true`. Preserve a separate shared data message for Guest sync.
- Add a README banner and badges, preview assets and explicit component acknowledgements. Configure bot and webhook branding separately and rotate the bot presence through live team and saved group statistics.
- Apply bot username, avatar and banner explicitly. Keep the avatar chest centred and the banner text aligned;
  branding previews are labelled local simulations. Add Windows and Linux test jobs on pushes and pull requests.
- Add tray options, diagnostic cleanup and a Settings reset. Keep a console debug batch file and a buildable
  Windows development launcher.

## Defaults

The portable defaults mirror the verified setup in `config.example.toml`. Match automation and Auto mode are enabled,
the app opens normally and closes to the tray, and the on-screen overlay is visible in screen sharing. Group sharing remains
off. Automatic match reports also require a configured bot and enabled sharing.
Session logs, candidate logs, detection snapshots and diagnostic video are all off by default and require opt-in.
The example configuration is checked against the code defaults. Portable builds include no saved configuration,
credentials, player names, counters, diagnostic recordings or sample match data.

## Validation

- Detector development replayed 11 diagnostic recordings comprising 20,455 analysed frames. A rare-chest replay
  recovered four Rare openings and one Sprite opening. A separate replay counted a normal opening once after
  deduplication. A normal French X2 pop-up first seen with its multiplier already present can still count as one.
- Two local Fortnite logs from the same pair of Duo matches yielded two matching session fingerprints and detected
  Duo on both PCs. Automated tests exercised local history, mode selection, Discord publication and settings sync
  using simulated Discord responses.
- App previews capture the current interface with sample data. The Discord leaderboard and profile previews are locally rendered simulations, with the leaderboard using the actual embed payload.
- A further local HDR recording contains 9,168 frames. Both the unchanged baseline and the corrected full replay
  count 31 openings; the visually checked burst is exactly four Rare chests and one Sprite chest, with no extra
  count from ammo, fading notifications or inventory. One opening logged live is absent in both replays near a
  weak glyph threshold in the standard MJPEG recording; this is not counted as a new detector regression or hidden
  by lowering confidence thresholds. Static saved images additionally exercise the previously clipped X2 layouts.
- Before release, repeat tests with an installed Windows build, HDR and SDR capture, Discord screen sharing and
  a live Host/Guest setup. Live performance and Discord delivery need separate verification.

The initial work used Codex with GPT-6.1 Sol at medium reasoning effort. Maintainers should independently replay
their own recordings before merging detector changes.

## Acknowledgements

See [project, artwork and dependency credits](ACKNOWLEDGEMENTS.md).

## References

- [Material Design 3](https://m3.material.io/)
- [Chest Tracker](https://github.com/Xxoris190/chest-tracker)
- [Google Sans](https://github.com/googlefonts/googlesans)
- [Material Icons](https://github.com/google/material-design-icons)
- [Independent Pirate Token calculator](https://piratetoken.quest/drop-rate/)
