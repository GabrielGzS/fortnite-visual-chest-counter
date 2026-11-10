# Acknowledgements and licenses

## Project and illustration

[Fortnite Visual Chest Counter](https://github.com/GabrielGzS/fortnite-visual-chest-counter), created by Gabriel Gomez, is the upstream project. Its source code is distributed under the [MIT License](../LICENSE).

The animated chest geometry is adapted from [Chest Tracker](https://github.com/Xxoris190/chest-tracker), also under the MIT License. The illustration credit is retained in [the source](../src/fortnite_chest_counter/gui/chest_illustration.py) and the project license. The app logo and README banner reuse the app's chest artwork.

The README layout takes cues from Chest Tracker and [N-Zik’s README](https://github.com/N-Zik-Group/N-Zik#readme). The app's tonal surfaces and component direction follow [Material Design 3](https://m3.material.io/).

## Fonts, icons and runtime

| Component | License and retained notice |
|---|---|
| Google Sans | SIL Open Font License 1.1. [Bundled font license](../src/fortnite_chest_counter/gui/assets/google-sans-license.txt). |
| Google Material Icons | Apache License 2.0. [Bundled icon license](../src/fortnite_chest_counter/gui/assets/material-icons-license.txt). |
| Python | PSF License. The portable build includes the official embeddable runtime and its license. |
| Qt, PySide6 and Shiboken6 | LGPL v3. [Qt notice](../packaging/QT-NOTICE.txt), with license texts and source information in portable builds. |
| FFmpeg | Unmodified LGPL v3 build, run as a separate program. [FFmpeg notice](../packaging/FFMPEG-NOTICE.txt). The matching source archive accompanies the build. |
| NumPy and SciPy | BSD 3-Clause and the licenses of their bundled libraries. Portable builds retain their distribution notices. |
| Streamlink | BSD 2-Clause, with each streaming dependency notice retained in the portable runtime. |
| discord.py and HTTP dependencies | MIT, Apache-2.0 and PSF-2.0 as applicable. Portable builds retain each dependency's notices. |

The [distribution notice](../packaging/LICENSE-NOTICE.txt) lists runtime locations. Each packaged build also contains `runtime/PROVENANCE.txt` with versions, origins and checksums.

## Research and development

The Pirate Token estimate can be compared with the [independent calculator](https://piratetoken.quest/drop-rate/) and the [Fortnite Status announcement](https://x.com/FortniteStatus/status/2119202610322227327). The formula and assumptions are described in the [overlay guide](guides/obs-overlay.md).

The upstream commit history credits [Claude Opus 5.5](https://github.com/GabrielGzS/fortnite-visual-chest-counter/commit/032df3b4ebdaea57e49dbc54ba6496d9c2e0364b) as a co-author. Development on this branch used Codex assistance, including GPT-6.1 Sol at medium reasoning effort. Validation notes distinguish automated checks and replay evidence from live verification. See [changes and validation](CHANGES.md).

Fortnite is a trademark of Epic Games, Inc. This independent project has no Epic Games affiliation or approval.
