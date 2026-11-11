# Start here

Fortnite Visual Chest Counter counts the chests opened in Fortnite gameplay video. It needs Windows 10 or 11, and nothing else
installed. You only need OBS if you want the numbers on your stream, or want to count from your own OBS scene.

## Install

1. Right-click the ZIP and choose **Extract All**. A normal folder such as Downloads or Desktop is fine, but not Program Files.
2. Open the extracted folder and double-click **Fortnite Visual Chest Counter.exe**. It is the only thing you open.

Do not run the app from inside the ZIP.

## Keep the folder together

> **Important:** always extract the complete archive. Do not delete files from the `runtime` folder or move individual files
> out of the app's folder. Doing so may stop the app from starting or counting correctly.

The `runtime` folder holds what the app needs: its own copy of Python, FFmpeg for reading video, and the window toolkit. These
are expected parts of the app, and you do not install them separately.

## Your data

Everything stays on your PC, next to the app:

| In the app's folder | What it is |
|---|---|
| `state` | Your counts, profiles and match history |
| `config.toml` | Your settings, once you have changed one |
| `obs_output` | The text files OBS reads |
| `logs`, `captures` | Session logs and optional diagnostic recordings |

To back up, close the app and copy `state` and `config.toml` somewhere safe. Deleting the app's folder deletes these too.

## Updating

From v0.2.3 on, the app offers new versions itself: choose **Update available**, then **Download & Install**. The built-in
updater is experimental and has not yet installed a real update.

To update by hand, which works from any version:

1. Close the app and extract the new ZIP to its own folder.
2. Copy `state` and `config.toml` from the old folder into the new one.
3. Open the new app. If you use OBS, point your Text source at the new `obs_output` folder.

## Help

Open **README.html** in this folder for setup, OBS and troubleshooting. To report a problem, use **Help & diagnostics** in the app
and include the report in an issue at https://github.com/GabrielGzS/fortnite-visual-chest-counter/issues.
