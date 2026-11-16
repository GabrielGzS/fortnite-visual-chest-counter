# Milestone A — tabbed Settings and Overlay, one save model (validation notes)

Branch `dev/remote-sharing`, from `36631d0` (v0.5.1). Part of the next release together with Remote Sharing and the end-of-match
estimate; not released on its own. Plan: the "Remote Sharing plan" tab of the planning doc (Milestone A section).

## What changed

- **Settings** has four tabs (Gameplay, Tracking, Application, Advanced); **Overlay** has two (Display, OBS WebSocket). Every card,
  wording and option is the same; nothing moved between pages. The tabs reuse the Dashboard / Analytics view-button style.
- **One save model for both pages** (`gui/save_state.py`, Qt-free, + `SavedPage` in `gui/app.py`): the status ("All changes saved" /
  "● Unsaved changes" / "Not saved: …"), **Discard changes** and **Save changes** stay above the tabs. Switching tabs never asks and
  never drops anything; leaving the page or closing the app with unsaved changes asks save / discard / stay, on either page.
- **Saves are diff-based and all or nothing.** Only settings that changed are written (plus defaults shown for values in config.toml
  that did not load, as saving always repaired them), in ONE checked write of config.toml (`counter.update_config_sections`: the
  result is loaded from a candidate file first; only a candidate that reads back exactly replaces config.toml). If a later step fails
  (the HUD Scale into profiles.json, the OBS password into Credential Manager, a read-back), config.toml and profiles.json are put
  back byte for byte (`restore_config_file`, `atomic_write_bytes`) and nothing is reported as saved; the edits stay on the page.
- **Overlay migration.** Apply / Undo are gone (Save / Discard). OBS on/off, host, port and the Text source are saved with Save, no
  longer instantly. Live effects happen only after the save is read back: the OBS files are rewritten when the wording changed
  (a running counter re-reads it within a second, as before); OBS is reconnected only when host, port or password changed, re-targeted
  when only the source changed, and not touched at all otherwise. **Connect** reconnects with the saved settings; with unsaved changes
  it reads **Save and connect** (a failed save does not connect). **Forget password** asks first and deletes at once.
- **Password states:** an empty box never touches the saved password; a typed one is stored in Credential Manager on Save (and read
  back), never in `_values()`, config.toml or logs; Forget is explicit and confirmed.
- **Background updates never change what is being edited:** the OBS link's status (once a second) keeps showing the source picked on
  the page; when OBS renames the source and the app saves that, the page's saved value moves (`SaveState.rebase`) without touching the
  user's unsaved edits, and a later wording save no longer writes the old name back.
- Guides: `docs/guides/obs-overlay.md` and `packaging/README.html` say Save changes instead of Apply.

## Tests

| Suite | Result |
| --- | --- |
| `tests/test_settings_ui.py` (16 existing, unchanged + 7 new: tabs, tab switching, Discard, all-or-nothing, diff-based, SaveState rules, config transactions) | 23/23 |
| `tests/test_overlay_ui.py` (new) | 21/21 |
| Every other suite except `test_cases` (detector replays; detector untouched): 34 suites, among them `test_app` 30/30, `test_update_gui` 70/70, `test_obs` 18/18, `test_match_ui` 50/50, `test_corrections` 82/82, `test_release` 79/79, `test_update_install` 102/102 | all pass |

Found by the gate run and fixed: `test_match_ui::test_invalid_config_values_show_the_safe_defaults` — a diff-based save no longer
rewrote a value that had not loaded ("maybe" for `[match] mode`). Both pages now remember which of their keys did not load and write
the default they show on the next save (a repaired OBS key never reconnects).

Mutation check (10 hand-made mutations of the new code, each must fail a suite): 10/10 caught after strengthening one test
(a failed save followed by changing everything back must show "All changes saved").

## Known limitations / not checked

- Only an off-screen render was looked at (no fonts there): the tab row and header layout on a real screen still need a look.
- The Dashboard's own controls, Analytics and Predictions are unchanged (not settings pages).
- Undoing a failed save is best effort: if putting config.toml back itself fails, the error is still reported and nothing claims success.
