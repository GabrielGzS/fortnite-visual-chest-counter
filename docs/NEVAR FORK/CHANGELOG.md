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

- Add a dedicated recent-match card and a Group tab for editing and deleting saved matches and viewing local ranks.
  Save a match from both capture sources, manually or with opt-in local Battle Royale detection.
- Add a Discord tab for bot setup, manual reports and optional automatic reports after a new match saves.
  Store credentials in Windows Credential Manager.
- Add optional start in system tray and close to tray. Use the tray menu to reopen or quit the app.
- Show Total on its own line in the stacked on-screen overlay. Render the selected layout example and preview from
  the same wording and counts. Use a tonal button to restore wording defaults.
- Replace the shell launchers with a buildable local Windows executable and a console-only debug batch file. Update the app icon to the skull chest.
- Place Total and Pirate Token chance in the main stage, with separate Certain and Approx cards above recent openings. Align the two selectors and move profile actions to the right of the profile.
- Replace the collapsible sidebar with a fixed 96-unit left navigation rail with a distinct surface. Keep all six
  destinations keyboard-accessible and show the full update status in the content area.
- Bundle Google Sans and official Material Icons with their licenses. Use connected action groups, themed dropdown
  chevrons, checkboxes, radio controls and numeric steppers.
- Group Capture settings with Activity and Live preview, with capture status next to the sources. Group Edit counts
  with Reset and Finish match and Analyse a recording with Mark moment. Give the on-screen summary a card and a shortcut to Overlay.
- Apply themed confirmations and profile prompts. Destructive confirmations default to Cancel. The Windows file
  picker remains a system dialog.
- Use static Google Sans faces, animate the selection indicator and dropdowns with reduced-motion support, and keep
  mouse selection free of the extra navigation focus outline. Connect dialog actions and round the floating overlay.
- Update overlay examples from the combined live counts and draft wording. The OBS text file still uses the primary source.
- Reuse the animated on-screen overlay preview on the Dashboard. Add source and profile chips, centered numeric values,
  corrected connected button corners, and reduced-motion-aware page, dialog and capture panel transitions.
- Draw and animate normal, Sprite, blue rare, and unknown chests on the Dashboard and on-screen overlay. Honour the
  Windows reduced-motion preference and keep the latest displayed type in sync with classification corrections.
- Add cleanup for recognized diagnostic videos, session logs and snapshots, including logs from retired secondary
  profiles. Preserve profiles, counts, settings, and unrelated files.
