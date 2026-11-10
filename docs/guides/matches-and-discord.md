# Matches and Discord

## Track a match locally

In **Dashboard → Capture settings**, choose one video source. To track a match manually, reset before the match,
start counting and use **Finish match** to save the result. **Group → Match history** lets you edit a saved match
or tick one or more rows and delete them. **Select all matches** selects every row. Edits and deletions affect the
local history. Previously shared results stay in the shared standings.

**Settings → Match automation** is enabled by default. Turn it off and save if you prefer manual start and finish. The app reads new entries in
`%LOCALAPPDATA%\FortniteGame\Saved\Logs\FortniteGame.log`. Battle Royale warmup starts a fresh count and a return to
the lobby stops counting and saves it. Use manual controls for a match already underway when the app started.

The Dashboard mode selector defaults to **Auto** to read the Battle Royale playlist from the same log.
This works independently of automatic start and finish. The last detected mode remains visible at the lobby so you
can finish a match manually. You can also choose **Solo**, **Duo**, **Trio** or **Squad**. The Pirate Token multiplier
is set manually. Unrecognised playlists may require a manual mode selection.

PH

## Share results with a group

1. Each player uses their own app and capture. In **Group → Player setup**, save a distinct player name and the same
   Discord webhook. The webhook URL identifies the destination channel. Share it privately.
2. Choose **Host** on the PC running the bot and **Guest** on the other PCs. Enable **Share matches with my group**
   on PCs that should submit new matches. Turn it off to keep new matches local and restore personal mode and boost controls.
3. After setting up the bot, the Host clicks **Publish leaderboard**. Guests paste the message ID or link into
   **Leaderboard message** and save. The Dashboard shows a compact ranking above recent matches.

Matching local Fortnite session IDs let the app group contributions even when players leave at different times.
Only a fingerprint is sent. The team match count covers verified sessions. Other player results can still appear
individually. The team drop estimate uses the chests submitted so far and updates as players submit.

Guests with sharing enabled follow the mode and multiplier in the published leaderboard. They can read the last published
settings when the bot is offline. The bot must be online to collect submissions and refresh the rankings.

PH

## Set up the host bot

1. In the [Discord Developer Portal](https://discord.com/developers/applications), create an application and enable
   **Message Content Intent** under **Bot**.
2. In **Group**, open the bot settings, save the Application ID and bot token, then click **Invite bot**. The
   invitation requests zero guild-wide permissions. Grant **View Channel** and **Read Message History** in the webhook
   channel. For reports there, grant **Send Messages** and **Embed Links** as well.
3. Click **Start bot**. Enable the startup option to launch the bot with the app. **Match reports** offers manual
   sending and optional automatic sending for newly shared matches.

`/chests` and `/leaderboard` are available wherever Discord allows them in the configured server.
`/add` and `/reset` require **Manage Server**. The Host can reset checked players or delete the published leaderboard
message from **Group**. These actions preserve local match history.

Bot and webhook credentials are stored in Windows Credential Manager.

[Chest Tracker bot setup reference](https://github.com/Xxoris190/chest-tracker#set-up-the-discord-bot)
