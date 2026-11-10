# Validation

## Published detector work

The development record covers 11 diagnostic recordings and 20,455 analysed frames. The rare group recovered four
rare openings and one Sprite opening. A separate replay confirmed one normal opening was counted once after
deduplication. See [French Match Tracker](FRENCH_MATCH_TRACKER.md) for known confidence and X2 limits. The diagnostic
recordings used in that work were local and have since been removed at the contributor's request.

## Local UI follow-up

- 77 selected tests passed from an isolated working directory, covering cleanup, overlay, two sources, the token
  formula, worker messages, and the update UI. This is a targeted result.
- The native Windows self-test opened the application and listed both SDR and HDR screen entries.
- A scripted Qt run at 920 × 640 exercised all four navigation destinations by keyboard, profile prompt validation,
  Enter and Escape on a destructive confirmation, numeric input, and capture layout.
- The four chest illustrations and lid motion were exercised with events from both simulated sources, including late
  type corrections.
- Cleanup was exercised with simulated logs and clips, an active counter guard, confirmation cancellation, and
  preserved unrelated files. The project cleanup removed roughly 7.49 GB of existing diagnostics.

## Manual checks before publishing the follow-up

1. Start from `launch-chest-counter.cmd`. Check Google Sans, the left rail, grouped profile actions, capture selectors,
   and the **Help → Clean logs and captures…** confirmation.
2. Count on one HDR and one SDR source. Check both previews, status on stop, separate Certain and Approx, and the
   Pirate Token percentage on the combined Total. Test the normal, rare, Sprite and unknown presentations.
3. Share the screen with Discord and check overlay visibility in both sharing modes. Confirm that the overlay shows
   the same counts and animates on confirmed openings.
4. Run another match with diagnostics off and compare frame cadence during actual play. No live-game performance
   claim is made from the Qt checks.
