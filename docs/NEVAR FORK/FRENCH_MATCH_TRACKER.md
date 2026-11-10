# French Match Tracker

## Setup and features

Launch the release executable, or start the GUI from the development environment with
`python -m fortnite_chest_counter.gui`. See [development notes](../DEVELOPMENT.md) for the local Windows launcher.
Capture features that depend on Windows still require Windows.

The app uses English labels. To read a French Fortnite HUD, select **French** in **Settings → Fortnite language**.
The upstream English and Brazilian Portuguese defaults remain available. The Dashboard can combine two sources and
show their previews independently. **Certain** counts confirmed openings, **Approx** counts only estimated openings,
and **Total** is their sum. Use **Overlay → Wording** to customise the on-screen total. The Discord screen-share option
is in **Overlay**.

The Pirate Token estimate uses **Total** and the selected boost. It models independent drops using
`1 - (1 - p)^n`, where `p` is the boosted per-chest rate and `n` is the total chest count.
[Fortnite Status announcement](https://x.com/FortniteStatus/status/2119202610322227327).
[Independent probability calculator](https://piratetoken.quest/drop-rate/).

## Detector and capture changes

- French classification uses the XP line and agreement across multiple frames. It recognises normal, rare and sprite
  chests, including overlapping rare lines with **X2**. Ambiguous types remain unknown.
- Each live preview is capped at 5 frames per second. Desktop previews are produced by the capture reader while the
  counting worker analyses frames independently.
- HDR conversion processes smaller batches with identical pixel output. FFmpeg passes through the capture cadence
  without filling gaps with repeated frames.
- The SDR capture path uses the original colour conversion. Diagnostic encoding uses fewer threads and lower process
  priority on Windows. The dashboard offers 5, 10 and 15 analysed frames per second.

## Verification and limitations

Eleven diagnostic recordings, comprising 20,455 frames, were replayed during development. The rare group recovered
four rare openings and one sprite opening. A separate replay confirmed that two visual readings of the same normal
opening now count once. The Windows HDR capture, both recording formats, two-source aggregation and overlay settings
were also tested locally. The effect on frame drops during live play still needs independent verification.

A normal **COFFRE X2** first seen with the multiplier already present can still count as one. Very brief or unclear
pop-ups can remain estimated. Recheck counts and confidence on independent English, Brazilian Portuguese and French
recordings before merging. Local recordings, logs and user settings are ignored by Git.
