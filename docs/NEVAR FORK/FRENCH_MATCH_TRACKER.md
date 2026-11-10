# French Match Tracker

## Setup and features

Launch the release executable, or start the GUI from the development environment with
`python -m fortnite_chest_counter.gui`. See [development notes](../DEVELOPMENT.md) for the local Windows launcher.
Capture features that depend on Windows still require Windows.

The app uses English labels. To read a French Fortnite HUD, select **French** in **Settings → Fortnite language**.
The upstream English and Brazilian Portuguese defaults remain available. Each app uses one capture source.
**Certain** counts confirmed openings, **Approx** counts only estimated openings,
and **Total** is their sum. Use **Overlay → Wording** to customise the on-screen total. The Discord screen-share option
is in **Overlay**.

The Pirate Token estimate uses **Total** and the selected boost. It models independent drops using
`1 - (1 - p)^n`, where `p` is the boosted per-chest rate and `n` is the total chest count.
[Fortnite Status announcement](https://x.com/FortniteStatus/status/2119202610322227327).
[Independent probability calculator](https://piratetoken.quest/drop-rate/).

## Automatic match reports

Enable **Settings → Match automation** and save. The app watches new lines in Fortnite's local Windows log.
Battle Royale warmup resets and starts the counter. Returning to the local lobby stops counting and saves the match.
Totals stay visible in the lobby. For a match already underway when opening
the app, use the manual controls.

In **Discord → Match reports**, enable **Automatically send new match reports** to send newly saved matches.
Manual sending is also available. For rich reports grant **View Channel**, **Send Messages**, and **Embed Links**
in the webhook's channel. Enter the Application ID to use **Invite bot**, which requests no server-wide permissions.
**Start bot**, **Stop bot**, and the startup option control the persistent Discord connection.

## One shared leaderboard

Each player chooses a distinct name and saves the same webhook in **Group → Player setup**. Only the host
configures the bot token. The webhook determines the collection and report channel. Grant the bot **View Channel**
and **Read Message History** there, and enable **Message Content Intent** in the Developer Portal.
Share the webhook only with trusted players, as it can post in that channel.

The host starts the bot and clicks **Publish leaderboard** in Group once. Give the resulting message ID to the
other players to paste into **Leaderboard message**. The app updates the same message as the ranking changes.
The leaderboard shows totals, available confidence and chest-type counts, and the number of shared matches.
Use **Overlay → Show saved match count on screen** for your local match count.
Turn off **Share matches with my group** before playing solo to keep new matches local and skip automatic reports.

`/chests` and `/leaderboard` work across the server where Discord allows the commands.
`/add` and `/reset` require **Manage Server** and update the shared leaderboard. Editing a local match does
not change a contribution already shared in Discord.

- [Discord Developer Portal](https://discord.com/developers/applications)
- [Discord channel permissions](https://docs.discord.com/developers/topics/permissions)
- [Original Chest Tracker setup guide](https://github.com/Xxoris190/chest-tracker#set-up-the-discord-bot)

Under **Settings → Window**, enable **Start in the system tray** or **Keep counting in the system tray when the window
closes**. Choose **Open** or **Quit** from the tray icon's menu.

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
