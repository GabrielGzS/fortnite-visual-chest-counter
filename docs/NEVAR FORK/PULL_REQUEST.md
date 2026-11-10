# Pull request notes

## Current upstream PR

[PR #1 — Add French HUD tracking, dual-source capture, and a configurable overlay](https://github.com/GabrielGzS/fortnite-visual-chest-counter/pull/1)
targets upstream `main` from `NEVARLeVrai:french-match-tracker`. On 2026-11-10, GitHub reported that it was open and
mergeable, with zero check runs for head `fba6027c46a60931e6aa6d2f9f17ab0661efc0c6`.

That PR covers French recognition, two capture sources, capture and preview corrections, overlay settings, and the
Pirate Token estimate. The desktop restyling and cleanup button are on `ui/chest-tracker-dashboard`, based on that head.
This branch is local and awaiting the contributor's in-game test.

## Draft for a separate UI follow-up

**Title** — Refine the Windows UI with Material 3 navigation and animated chest variants

### Summary

- Rework the dashboard around the combined Total and Pirate Token estimate, with separate Certain and Approx cards and a
  recent-openings list that identifies the chest type and source.
- Use a fixed left Material-style rail, Google Sans and Google Material Icons. Apply shared Qt styling to prompts,
  controls, dropdowns and connected button groups.
- Show four animated chest variants on the Dashboard and screen overlay. Confirmed openings animate. Later type updates
  replace the illustration without replaying the animation.
- Add local match history and ranking, with manual match completion and a separate Discord tab for optional bot summaries.
- Offer opt-in Battle Royale detection from Fortnite's local log, a system tray mode, and automatic or manual
  Discord reports with a bot setup guide and a channel-scoped permissions checklist.
- Keep overlay wording, the selected example and the preview in sync. Show Total on its own line in stacked mode.
- Replace the source shell launchers with a buildable Windows development launcher.
- Add **Help → Clean logs and captures…** with destructive confirmation and a guard against active counting.
- Retain both source selectors and previews, profile state, the total-based estimate, and the existing sharing option.

### Validation to include

See [Validation](VALIDATION.md). Attach only scrubbed screenshots or synthetic fixtures. Local recordings and logs have
been cleaned up and are excluded from Git.

### References and review note

- [Material Design 3](https://m3.material.io/)
- [Material 3 navigation rail](https://m3.material.io/components/navigation-rail/overview)
- [Material 3 button groups](https://m3.material.io/components/button-groups/overview)
- [Chest Tracker](https://github.com/Xxoris190/chest-tracker), MIT-licensed illustration geometry adapted with attribution
- [Google Sans](https://github.com/googlefonts/googlesans) and [Google Material Icons](https://github.com/google/material-design-icons)
- [Independent Pirate Token drop-rate calculator](https://piratetoken.quest/drop-rate/)

The initial fork work used Codex assistance, including GPT-6.1 Sol with medium reasoning effort. Maintainers should
verify the detector results on their own recordings before merging.
