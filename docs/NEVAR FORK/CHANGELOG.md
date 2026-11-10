# Fork change log

## Published in PR #1

- French HUD detection and multi-frame classification for normal, rare and Sprite chests. Leave ambiguous types
  unknown and deduplicate fallback readings around French XP qualifiers and X2 overlaps.
- Aggregate both video sources into one profile with separate previews, Certain and Approx counts, and a combined
  Total. The Pirate Token estimate uses the Total, with mode selection, boosts, and manual reset.
- Improve HDR-to-SDR conversion and preview delivery. Keep the original SDR colour conversion, decouple preview
  generation from detection, limit live preview to 5 FPS, and offer 5, 10 and 15 analysed frames per second.
- Configure the on-screen overlay and wording, including the total, token chance and chest types. Persist display and
  sharing preferences.
- Keep English as the default UI language and allow French separately for Fortnite detection. Provide the Windows and
  shell development launchers.

## Local UI follow-up

- Place Total and Pirate Token chance in the main stage, with separate centred Certain and Approx cards and recent
  openings grouped by source and type. Align the two selectors and move profile actions to the right of the profile.
- Replace the collapsible sidebar with a fixed 96-unit left navigation rail with a distinct surface. Keep all four
  destinations keyboard-accessible and show the full update status in the content area.
- Bundle Google Sans and official Material Icons with their licenses. Use connected action groups, themed dropdown
  chevrons, checkboxes, radio controls and numeric steppers.
- Keep Start counting as the sole primary action in the header. Place capture status next to the sources, and group
  Edit counts with Reset and Analyse a recording with Mark moment.
- Apply themed confirmations and profile prompts. Destructive confirmations default to Cancel. The Windows file
  picker remains a system dialog.
- Draw and animate normal, Sprite, blue rare, and unknown chests on the Dashboard and on-screen overlay. Honour the
  Windows reduced-motion preference and keep the latest displayed type in sync with classification corrections.
- Add cleanup for recognized diagnostic videos, session logs and snapshots, including logs from retired secondary
  profiles. Preserve profiles, counts, settings, and unrelated files.
