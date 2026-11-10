import asyncio
import json
from threading import Event
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import discord
import pytest

from fortnite_chest_counter import discord_bot, discord_group, discord_summary, match_history


WEBHOOK = discord_group.Webhook("123456789012345678", "fixture-secret-token")
CONFIG = discord_summary.BotSettings("234567890123456789", "fixture.bot.token")


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def test_durable_webhook_retry_and_authenticated_reset(tmp_path, monkeypatch):
    store = discord_group.GroupStore(WEBHOOK.id, tmp_path / "group.db")
    match = SimpleNamespace(snapshot="local-1", total=18)
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            if len(requests) == 1:
                raise URLError("confirmation lost")
            return FakeResponse()

    monkeypatch.setattr(discord_group, "build_opener", lambda *_: Opener())
    assert store.queue(match, "Rin | West")
    assert not store.queue(match, "wrong player")
    with pytest.raises(ValueError, match="remains pending"):
        store.flush(WEBHOOK)
    reopened = discord_group.GroupStore(WEBHOOK.id, store.path)
    assert reopened.flush(WEBHOOK) == 1
    assert reopened.flush(WEBHOOK) == 0
    assert requests[0].data == requests[1].data
    assert requests[0].full_url == f"{WEBHOOK.url}?wait=true"
    body = json.loads(requests[0].data)
    assert body["allowed_mentions"] == {"parse": []}
    channel = SimpleNamespace(id=int(CONFIG.channel))

    def message(id, content, author=WEBHOOK.id):
        return SimpleNamespace(id=id, channel=channel, content=content, webhook_id=int(author))

    assert not reopened.ingest(message(100, body["content"], author=CONFIG.channel))
    assert reopened.ingest(message(101, body["content"]))
    assert not reopened.ingest(message(102, body["content"]))
    assert reopened.cursor(channel.id) == 102
    assert reopened.adjust("RIN | WEST", -3) == ("Rin | West", 15)
    assert reopened.adjust("rin | west", None) == ("Rin | West", 0)
    assert not reopened.ingest(message(103, body["content"]))
    assert reopened.ingest(message(104, '||FCC1 ["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","rin | west",6]||'))
    assert reopened.count("Rin | West")[1] == 6
    assert reopened.count(None) == ("Everyone", 6)


def test_report_embed_and_fallback(monkeypatch):
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(json.loads(request.data))
            if len(requests) == 1:
                raise HTTPError(request.full_url, 403, "Missing permissions", None, None)
            return FakeResponse()

    monkeypatch.setattr(discord_summary, "build_opener", lambda *_: Opener())
    match = match_history.Match("snapshot", "2026-11-10 10:00", "default", "Capture", "Solo", 4, 3, "1%")
    discord_summary.send(CONFIG, match)
    embed, = requests[0]["embeds"]
    assert [(field["name"], field["value"]) for field in embed["fields"]] == [
        ("Total chests", "7"), ("Certain", "4"), ("Estimated", "3"), ("Estimated Pirate Token chance", "1%")
    ]
    assert requests[1] == {"content": match.summary(), "allowed_mentions": {"parse": []}}


def test_group_breakdowns_and_zero_matches_survive_retry_and_corrections(tmp_path):
    store = discord_group.GroupStore(WEBHOOK.id, tmp_path / "group.db")
    channel = SimpleNamespace(id=int(CONFIG.channel))

    def event(message_id, count, *details):
        payload = json.dumps([f"{message_id:032x}", "Rin", count, *details])
        return SimpleNamespace(webhook_id=int(WEBHOOK.id), channel=channel, id=message_id,
                               content=f"||FCC1 {payload}||")

    assert store.ingest(event(1, 8, 5, {"chest": 3, "rare": 2, "unclassified": 3}))
    assert store.ingest(event(2, 7))
    assert store.ingest(event(3, 0, 0, {}))
    assert not store.ingest(event(4, 2, 0, {"sprite": 3}))
    assert store.adjust("Rin", -2) == ("Rin", 13)
    row, = store.leaderboard()
    assert (row.recorded, row.adjustment, row.certain, row.confirmed_total, row.matches) == (15, -2, 5, 8, 3)
    assert row.chest_types == {"chest": 3, "rare": 2, "unclassified": 3}
    assert store.adjust("Rin", None) == ("Rin", 0)
    assert store.ingest(event(5, 0, 0, {}))
    everyone = store.stats()
    assert (everyone.total, everyone.matches, everyone.certain, everyone.chest_types) == (0, 1, 0, {})


def test_guild_registration_and_runtime_permission_check(tmp_path, monkeypatch):
    async def verify():
        guild = SimpleNamespace(id=123)
        channel = SimpleNamespace(id=int(CONFIG.channel), guild=guild)
        feed = SimpleNamespace(id=345, guild=guild)
        store = discord_group.GroupStore(WEBHOOK.id, tmp_path / "group.db")
        bot = discord_bot.GuildBot(CONFIG, store, lambda *_: None, WEBHOOK)
        bot._connection.application_id = 456
        monkeypatch.setattr(discord_bot.discord, "TextChannel", SimpleNamespace)
        upserts = []

        async def fetch_channel(id):
            return {channel.id: channel, feed.id: feed}[id]

        async def fetch_webhook(*, prefer_auth):
            assert not prefer_auth
            return SimpleNamespace(channel_id=feed.id, guild_id=guild.id)

        async def upsert(app, guild_id, payload):
            upserts.append((app, guild_id, payload))

        monkeypatch.setattr(bot, "fetch_channel", fetch_channel)
        monkeypatch.setattr(discord_bot.discord.Webhook, "partial",
                            lambda *_args, **_kwargs: SimpleNamespace(fetch=fetch_webhook))
        monkeypatch.setattr(bot.http, "upsert_guild_command", upsert)
        await bot.setup_hook()
        assert {(app, guild_id) for app, guild_id, _ in upserts} == {(456, 123)}
        assert {payload["name"] for _, _, payload in upserts} == {"chests", "leaderboard", "add", "reset"}
        assert not bot.tree.get_commands()
        assert bot.feed_channel is feed
        assert bot.intents.message_content and not bot.intents.members

        async def history(*, limit, after, before, oldest_first):
            assert (limit, after.id, before, oldest_first) == (None, 0, None, True)
            content = '||FCC1 ["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","Rin",8,4,{"rare":2}]||'
            yield SimpleNamespace(id=100, channel=feed, webhook_id=int(WEBHOOK.id), content=content)
            yield SimpleNamespace(id=101, channel=feed, webhook_id=777, content=content)

        feed.history = history
        await bot.on_ready()
        assert store.stats().total == 8
        assert store.cursor(feed.id) == 101
        assert store.cursor(channel.id) == 0

        calls = []

        async def send_message(*args, **kwargs):
            calls.append((args, kwargs))

        monkeypatch.setattr(store, "adjust", lambda *_: pytest.fail("Unauthorized write"))
        response = SimpleNamespace(send_message=send_message, is_done=lambda: False)
        add = bot.tree.get_command("add", guild=discord.Object(guild.id))
        reset = bot.tree.get_command("reset", guild=discord.Object(guild.id))
        await add.callback(SimpleNamespace(guild_id=123, permissions=discord.Permissions.none(), response=response),
                           "Rin", 5)
        await reset.callback(SimpleNamespace(guild_id=789, permissions=discord.Permissions.all(), response=response),
                             "Rin")
        assert "Manage Server" in calls[0][0][0]
        assert "configured server" in calls[1][0][0]
        assert all(options["ephemeral"] for _, options in calls)

    asyncio.run(verify())


def test_gateway_runner_closes_on_stop(monkeypatch):
    online = Event()
    closed = Event()

    class FakeBot:
        failure = None
        feed_channel = None

        def __init__(self, config, store, status, webhook):
            self.status = status

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            closed.set()

        async def start(self, token):
            assert token == CONFIG.token
            self.status("online", "Connected")
            online.set()
            await asyncio.Future()

    monkeypatch.setattr(discord_bot, "GuildBot", FakeBot)
    runner = discord_bot.BotRunner(CONFIG, None, lambda: None)
    runner.start()
    assert online.wait(2)
    assert runner.status == ("online", "Connected")
    runner.stop(timeout=2)
    assert closed.is_set()
    assert runner.status[0] == "stopped"


def test_qt_autostart_tray_hide_and_real_close(tmp_path, monkeypatch):
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QApplication
    from fortnite_chest_counter.gui import app as gui

    qt = QApplication.instance() or QApplication([])
    monkeypatch.setattr(gui.paths, "APP_DIR", tmp_path)
    monkeypatch.setattr(gui.MainWindow, "refresh_sources", lambda *_: None)
    monkeypatch.setattr(gui.MainWindow, "show_update_result", lambda *_: None)
    monkeypatch.setattr(gui.update_install, "clear_orphaned_journal", lambda: None)
    monkeypatch.setattr(gui.discord_summary, "load", lambda: CONFIG)
    monkeypatch.setattr(gui.discord_group, "load_webhook", lambda: WEBHOOK)
    monkeypatch.setattr(gui.discord_group, "flush", lambda *_: 0)
    gui.C.update_config_file(gui.config_file(), "app", {"auto_start_discord_sender": True, "close_to_tray": True})
    gui.C.update_config_file(gui.config_file(), "update", {"check_automatically": False})
    calls = []

    class Runner:
        def __init__(self, config, webhook, changed):
            self.config = config
            self.webhook = webhook
            self.report_config = config
            self.status = ("connecting", "Connecting")
            self.changed = changed

        def start(self):
            calls.append("start")
            self.status = ("online", "Connected")
            self.changed()

        def stop(self, *, timeout=None):
            calls.append("stop")
            self.status = ("stopped", "")

    monkeypatch.setattr(gui.discord_bot, "BotRunner", Runner)
    win = gui.MainWindow()
    try:
        assert calls == []
        win.after_start(installing=True)
        assert calls == []
        win.after_start()
        qt.processEvents()
        assert calls == ["start"]
        assert "Bot online" in win.discord.sender_status.text()
        win._tray = SimpleNamespace(isVisible=lambda: True, hide=lambda: None)
        hide = QCloseEvent()
        win.closeEvent(hide)
        assert not hide.isAccepted() and win._hidden_in_tray
        assert calls == ["start"]
        win._tray_exit = True
        close = QCloseEvent()
        win.closeEvent(close)
        assert close.isAccepted() and calls == ["start", "stop"]
    finally:
        win.deleteLater()
        qt.processEvents()



def test_team_summary_counts_first_submission_per_session_and_player(tmp_path, monkeypatch):
    store = discord_group.GroupStore(WEBHOOK.id, tmp_path / "group.db")
    channel = SimpleNamespace(id=int(CONFIG.channel))
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(json.loads(request.data))
            return FakeResponse()

    monkeypatch.setattr(discord_group, "build_opener", lambda *_: Opener())

    def submit(snapshot, session, player, total, boost=1.0):
        assert store.queue(SimpleNamespace(snapshot=snapshot, session_fingerprint=session, total=total, boost=boost), player)
        assert store.flush(WEBHOOK) == 1
        body = requests[-1]
        message = SimpleNamespace(id=len(requests), channel=channel, webhook_id=int(WEBHOOK.id), content=body["content"],
                                  embeds=[discord.Embed.from_dict(body["embeds"][0])])
        assert store.ingest(message)
        return message

    first, second = "a" * 64, "b" * 64
    submit("one", first, "Rin", 10)
    solo_chance = 1 - (1 - 1 / 137_500) ** 10
    assert store.team_summary() == discord_group.TeamSummary(1, 1, 10, 13750, f"{solo_chance:.6%}")
    submit("two", first, "Sam", 4, 2.0)
    chance = 1 - (1 - 1 / 137_500) ** 10 * (1 - 2 / 137_500) ** 4
    shared = discord_group.TeamSummary(1, 2, 14, round(1 / chance), f"{chance:.6%}")
    assert store.team_summary() == shared
    submit("three", first, "rIN", 100, 1.5)
    assert store.team_summary() == shared
    assert store.stats("Rin").matches == 2
    submit("four", "", "Rin", 200)
    submit("five", "1" * 32, "Sam", 40)
    assert store.team_summary() == shared
    assert store.adjust("Sam", None) == ("Sam", 0)
    assert store.team_summary() == shared

    message = submit("six", second, "Sam", 0)
    assert store.team_summary() == discord_group.TeamSummary(2, 1, 0, chance_percent="0.000000%")
    message.id += 1
    assert not store.ingest(message)
    assert store.team_summary() == discord_group.TeamSummary(2, 1, 0, chance_percent="0.000000%")


def test_qt_guest_startup_and_role_switch(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from fortnite_chest_counter.gui import app as gui

    qt = QApplication.instance() or QApplication([])
    monkeypatch.setattr(gui.paths, "APP_DIR", tmp_path)
    monkeypatch.setattr(gui.MainWindow, "refresh_sources", lambda *_: None)
    monkeypatch.setattr(gui.MainWindow, "show_update_result", lambda *_: None)
    monkeypatch.setattr(gui.update_install, "clear_orphaned_journal", lambda: None)
    monkeypatch.setattr(gui.discord_summary, "load", lambda: None)
    monkeypatch.setattr(gui.discord_group, "load_webhook", lambda: WEBHOOK)
    monkeypatch.setattr(gui.discord_group, "flush", lambda *_: 0)
    gui.C.update_config_file(gui.config_file(), "app", {"group_role": "guest"})
    gui.C.update_config_file(gui.config_file(), "update", {"check_automatically": False})
    calls = []

    class Runner:
        def __init__(self, config, webhook, changed):
            self.webhook = webhook
            self.status = ("stopped", "")

        def start(self):
            calls.append("start")
            self.status = ("online", "Connected")

        def stop(self, *, timeout=None):
            if self.status[0] == "online":
                calls.append("stop")
            self.status = ("stopped", "")

    monkeypatch.setattr(gui.discord_bot, "BotRunner", Runner)
    win = gui.MainWindow()
    win.timer.stop()
    win.slow.stop()
    try:
        assert win.group.role.currentData() == "guest"
        assert win.group.publish_board.isHidden()
        assert win.group.bot_section.isHidden()
        assert not win.group.share_matches.isChecked()
        monkeypatch.setattr(gui.discord_summary, "load", lambda: CONFIG)
        win.after_start()
        win.discord.start_bot()
        assert calls == []
        win.group.role.setCurrentIndex(win.group.role.findData("host"))
        assert calls == ["start"]
        assert not win.group.publish_board.isHidden()
        assert not win.group.bot_section.isHidden()
        assert win.discord.isHidden()
        assert gui.load_cfg()[0]["app"]["group_role"] == "host"
        win.group.role.setCurrentIndex(win.group.role.findData("guest"))
        assert calls == ["start", "stop"]
        assert win.group.publish_board.isHidden()
        assert win.group.bot_section.isHidden()
        assert gui.load_cfg()[0]["app"]["group_role"] == "guest"
        win.discord.start_bot()
        assert calls == ["start", "stop"]
    finally:
        win.close()
        qt.processEvents()

    reopened = gui.MainWindow()
    try:
        assert reopened.group.role.currentData() == "guest"
        assert reopened.group.publish_board.isHidden()
        assert reopened.group.bot_section.isHidden()
        reopened.after_start()
        assert calls == ["start", "stop"]
    finally:
        reopened.close()
        qt.processEvents()
