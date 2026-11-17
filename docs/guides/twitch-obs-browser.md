# Single-PC Twitch capture with OBS Browser Source and Virtual Camera

Count a Twitch livestream on **one Windows PC with one monitor**. OBS loads the channel inside a Browser Source and sends
the gameplay to the counter through its Virtual Camera. The Twitch page lives inside OBS, so you can keep the counter in
front while the stream plays.

```text
Twitch livestream -> OBS Browser Source -> OBS Virtual Camera -> Fortnite Visual Chest Counter
```

You need **OBS Studio 28 or newer**, a live Twitch channel and the app extracted from its ZIP
([download](../../README.md#download)). The input is **OBS Virtual Camera**. This setup needs no capture card, second
monitor, desktop capture or separate Chrome/Edge window, and uses OBS's browser for Twitch playback instead of the app's
Livestream URL input.

> **Capture setup verified by the maintainer on 2026-11-17** on one PC with one monitor. The Browser Source layout and
> gameplay reaching the counter were checked successfully. Detector accuracy for this capture method has not been measured
> independently.

## 1. Create the scene and Browser Source

1. Open OBS Studio.
2. In **Scenes**, click **+** and name the scene `Twitch Counter`.
3. In **Sources**, click **+** -> **Browser**, name it `Twitch gameplay` and click **OK**.
4. Leave **Local file** unchecked and enter the streamer's regular channel URL in **URL**, for example
   `https://www.twitch.tv/CHANNELNAME`.
5. Set **Width** to **1280** and **Height** to **720** (16:9).
6. Leave **Shutdown source when not visible** unchecked.
7. Leave **Refresh browser source when scene becomes active** unchecked, then click **OK**.

The source settings control whether OBS unloads or refreshes the page when you switch scenes. Keeping both options off
helps the player continue without interruption. OBS documents these settings in its
[Browser Source reference](https://obsproject.com/kb/browser-source).

## 2. Set up the Twitch player inside OBS

1. Right-click `Twitch gameplay` in **Sources** -> **Interact**.
2. Dismiss the Twitch cookie banner if it appears.
3. Enable Twitch **Theater Mode** and collapse the Twitch chat.
4. Move the pointer away from the player controls and check that the Fortnite gameplay occupies the source correctly,
   with the **complete HUD visible**. Twitch can move its Theater Mode and chat controls as its interface changes.
5. Close the **Interact** window. Check the OBS preview again. Keep the scene 16:9 and fit the source to the canvas if
   needed (right-click the source -> **Transform** -> **Fit to screen**).

The tested setup used Twitch's regular channel page and its player controls. Custom CSS was unnecessary. Keep the whole
gameplay picture when adjusting the source, including the chest notifications to the right of the crosshair.

## 3. Send the scene through OBS Virtual Camera

1. In **Controls**, click the **gear** next to **Start Virtual Camera**.
2. Set **Output Type** to **Scene** and **Output Selection** to `Twitch Counter`, then close the dialog. This keeps the
   camera on this scene when you switch the main OBS preview to another scene.
3. Click **Start Virtual Camera**.

OBS explains the scene output option in its [Virtual Camera guide](https://obsproject.com/kb/virtual-camera-guide).

## 4. Start counting

1. Open **Fortnite Visual Chest Counter.exe**.
2. On **Dashboard** -> **Overview**, select **OBS Virtual Camera** in **Video source**. Click **Refresh** if needed.
3. Click **Start counting**, then open **Live preview**.
4. Confirm that moving gameplay keeps arriving and that the complete Fortnite HUD is visible.
5. Close the OBS **Interact** window if it is still open and bring the counter to the foreground. Watch the live preview
   briefly to confirm that playback continues in the background.

Keep OBS, its Browser Source and Virtual Camera running during counting. Background playback depends on Twitch's player
remaining active inside OBS. If the picture freezes, reopen **Interact** and check that the player is still playing.

To put the resulting numbers on your stream, follow the [OBS overlay guide](obs-overlay.md). Remote Sharing sends the
counter's output to an OBS Browser Source on another PC or network. This guide covers the incoming gameplay picture.
The [README's Remote Sharing section](../../README.md#remote-sharing-preview-v060) explains that output option.

## Troubleshooting and limits

| Symptom | What to check |
|---|---|
| A cookie banner, chat or player controls cover the gameplay | Open **Interact**, dismiss the banner, enable Theater Mode, collapse chat and move the pointer away from the player. |
| The counter shows the wrong scene | Set Virtual Camera **Output Type** to **Scene** and select `Twitch Counter`. |
| The picture freezes when you switch scenes or bring another window forward | Check the Browser Source's two shutdown/refresh options above, then use **Interact** to check playback. An active embedded player is still required. |
| Twitch is buffering, showing an ad or the channel goes offline | Wait for live gameplay to return and check it in Live preview. Chests opened while gameplay is unavailable cannot be counted. |
| Gameplay arrives, but chests are missed | Check picture quality, the full HUD and the chest notification area. A streamer's webcam, overlays or unusual layout can obscure or shrink the notifications. |
| OBS Virtual Camera is missing or in use | Follow the [input troubleshooting steps](troubleshooting.md#the-counter-does-not-get-a-picture). |

Other capture methods are listed in the [setup guides](README.md). The app can also receive a
[livestream URL directly](livestream-url.md).
