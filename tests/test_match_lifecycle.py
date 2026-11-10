import os
import sys
from pathlib import Path
from threading import Event

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fortnite_chest_counter import match_lifecycle


START = (b"[2026.11.10-20.04.47:107][363]LogBattleRoyaleGamePhaseLogic: HandleGamePhaseChanged. "
         b"OldPhase = EAthenaGamePhase::Setup. NewPhase = EAthenaGamePhase::Warmup\r\n")
FRONTEND = (b"[2026.11.10-20.05.02:589][955]LogWorld: Bringing World /Game/Maps/Frontend.Frontend up for play "
            b"(max tick rate 360) at 2026.11.10-21.05.02\r\n")


def append(path, data):
    with path.open("ab") as stream:
        stream.write(data)


def test_tail_only_parses_new_complete_exact_markers(tmp_path, monkeypatch):
    path = tmp_path / "FortniteGame.log"
    path.write_bytes(START + FRONTEND + START[:30])
    monkeypatch.setattr(match_lifecycle.LogTail, "READ_SIZE", len(START) + len(FRONTEND))
    tail = match_lifecycle.LogTail(path)
    assert tail.poll() == (False, [])

    append(path, START[30:] + START[:20])
    assert tail.poll() == (False, [])
    append(path, START[20:] + FRONTEND)
    assert tail.poll() == (False, ["start", "finish"])

    append(path, START.replace(b"OldPhase", b"OtherPhase") + FRONTEND.replace(b"Frontend.Frontend", b"Other.Frontend"))
    assert tail.poll() == (False, [])
    assert tail.poll() == (False, [])


def test_tail_recovers_from_rotation_truncation_and_overlong_lines(tmp_path, monkeypatch):
    path = tmp_path / "FortniteGame.log"
    tail = match_lifecycle.LogTail(path)
    path.write_bytes(START)
    assert tail.poll() == (False, ["start"])
    append(path, FRONTEND[:25])
    assert tail.poll() == (False, [])
    path.rename(tmp_path / "FortniteGame-backup.log")
    path.write_bytes(FRONTEND[25:] + START)
    assert tail.poll() == (True, ["start"])

    path.write_bytes(FRONTEND + b"new content of a rewritten file\n" + START)
    assert tail.poll() == (True, ["finish", "start"])
    path.write_bytes(b"")
    assert tail.poll() == (True, [])

    monkeypatch.setattr(tail, "READ_SIZE", 250)
    monkeypatch.setattr(tail, "LINE_LIMIT", 200)
    append(path, b"x" * 500 + START + FRONTEND)
    assert tail.poll() == (False, [])
    assert tail.poll() == (False, [])
    assert tail.poll() == (False, [])
    assert tail.poll() == (False, ["finish"])


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    qt = pytest.importorskip("PySide6.QtWidgets")
    from fortnite_chest_counter.gui import app as gui

    application = qt.QApplication.instance() or qt.QApplication([])

    class Worker:
        def __init__(self):
            self.alive = False
            self.starts = 0
            self.stops = 0
            self.stderr_tail = []

        def running(self):
            return self.alive

        def start(self, argv):
            self.alive = True
            self.starts += 1

        def stop(self):
            self.stops += 1

    log = tmp_path / "FortniteGame.log"
    monkeypatch.setattr(gui.paths, "APP_DIR", tmp_path)
    monkeypatch.setattr(gui.discord_group, "load_webhook", lambda: None)
    monkeypatch.setattr(gui.discord_summary, "load", lambda: None)
    monkeypatch.setattr(match_lifecycle, "local_log_path", lambda: log)
    monkeypatch.setattr(gui.MainWindow, "refresh_sources", lambda self: None)
    monkeypatch.setattr(gui, "ask", lambda *args, **kwargs: True)
    monkeypatch.setattr(gui, "show_error", lambda parent, message: pytest.fail(message))
    win = gui.MainWindow()
    win.timer.stop()
    win.slow.stop()
    win.worker = Worker()
    win._fill_sources([], [(0, 0, 1280, 720), (1280, 0, 1920, 1080)])
    win.dashboard.source.setCurrentIndex(win.dashboard.source.findData({"source": "desktop", "monitor": 1}))
    try:
        yield gui, win, log
    finally:
        win.set_match_automation(False)
        win._workers_pending.clear()
        win.worker.alive = False
        win.close()
        application.processEvents()


def seed(gui, win, counts):
    gui.C.set_counts(win._cfg_for_actions(), *counts)
    win.read_state(force=True)


def exit_worker(win, code=0, acknowledged=True):
    if acknowledged:
        win.handle({"type": "stopped", "stop_reason": "stopped in the app"})
    win.worker.alive = False
    win.handle({"type": "exit", "code": code})


def online_bot(win, config):
    from types import SimpleNamespace

    win.discord.runner = SimpleNamespace(status=("online", ""), config=config, report_config=config, stop=lambda **_: None)


@pytest.mark.parametrize("send_enabled", [False, True])
def test_qt_drains_before_saving_and_before_next_start(app, monkeypatch, send_enabled):
    gui, win, log = app
    delivered = Event()
    summaries = []

    def send(config, content):
        summaries.append(content)
        delivered.set()

    online_bot(win, object())
    monkeypatch.setattr(gui.discord_summary, "send", send)
    seed(gui, win, (5, 10))
    log.write_bytes(START)
    win.poll_match_log()
    assert win.counts == (5, 10)
    win.settings_page.auto_match.setChecked(True)
    win.discord.auto_report.setChecked(send_enabled)
    win.settings_page.save()
    win.poll_match_log()
    assert win.counts == (5, 10)
    assert win.worker.starts == 0

    append(log, FRONTEND + START + START)
    from PySide6.QtTest import QTest

    win.match_timer.setInterval(10)
    QTest.qWait(100)
    assert win.counts == (0, 0)
    assert win.worker.starts == 1

    seed(gui, win, (8, 13))
    append(log, FRONTEND + FRONTEND + START)
    win.poll_match_log()
    assert win.worker.stops == 1
    assert gui.match_history.read_history(win.match_history_path()) == []
    seed(gui, win, (9, 14))
    exit_worker(win)
    saved, = gui.match_history.read_history(win.match_history_path())
    assert (saved.certain, saved.total) == win.counts == (9, 14)
    assert win.worker.starts == 1
    display = {**gui.load_cfg()[0]["display"], "screen_show_matches": True}
    assert "Matches saved · 1" in win.dashboard.screen_overlay_text(display)

    # Saving the same snapshot manually is still a no-op.
    win.finish_match()
    assert gui.match_history.read_history(win.match_history_path()) == [saved]
    assert delivered.wait(2 if send_enabled else 0.05) is send_enabled
    assert summaries == ([saved] if send_enabled else [])

    win.poll_match_log()
    assert win.worker.starts == 2
    assert win.counts == (0, 0)


def test_qt_save_failure_disarms_and_preserves_counts(app, monkeypatch):
    gui, win, log = app
    win.set_match_automation(True)
    append(log, START)
    win.poll_match_log()
    seed(gui, win, (7, 9))
    with monkeypatch.context() as failing:
        def fail(*args):
            raise OSError("test history write failure")

        failing.setattr(gui.match_history, "save_match", fail)
        append(log, FRONTEND + START)
        win.poll_match_log()
        exit_worker(win)
    win.poll_match_log()
    assert win.worker.starts == 1
    assert win.counts == (7, 9)
    assert win._match_tail is None and not win.settings_page.auto_match.isChecked()
    assert not gui.load_cfg()[0]["app"]["auto_match_lifecycle"]
    win.finish_match()
    assert gui.match_history.read_history(win.match_history_path())[0].total == 9


def test_qt_active_rotation_preserves_counts_without_inventing_a_finish(app):
    gui, win, log = app
    win.set_match_automation(True)
    append(log, START)
    win.poll_match_log()
    seed(gui, win, (3, 5))
    log.rename(log.with_suffix(".backup"))
    log.write_bytes(FRONTEND + START)
    win.poll_match_log()
    assert win._match_tail is None
    assert win.counts == (3, 5)
    assert gui.match_history.read_history(win.match_history_path()) == []


@pytest.mark.parametrize("draining,code,acknowledged", [(False, 0, False), (True, 0, False), (True, 1, True)])
def test_qt_incomplete_exit_disarms_without_saving(app, draining, code, acknowledged):
    gui, win, log = app
    win.set_match_automation(True)
    append(log, START)
    win.poll_match_log()
    seed(gui, win, (5, 9))
    if draining:
        append(log, FRONTEND)
        win.poll_match_log()
    exit_worker(win, code=code, acknowledged=acknowledged)
    append(log, FRONTEND + START)
    win.poll_match_log()
    assert win._match_tail is None
    assert win.counts == (5, 9)
    assert gui.match_history.read_history(win.match_history_path()) == []


def test_qt_restores_state_file_if_reset_cannot_save(app, monkeypatch):
    gui, win, log = app
    seed(gui, win, (5, 9))
    cfg = win._cfg_for_actions()
    primary = Path(cfg["state"]["path"])
    previous = primary.read_bytes()

    def fail_write(path, state):
        raise OSError("test state write failure")

    monkeypatch.setattr(gui.C, "save_state", fail_write)
    win.set_match_automation(True)
    append(log, START)
    win.poll_match_log()
    assert primary.read_bytes() == previous
    assert win.counts == (5, 9)
    assert win.worker.starts == 0
    assert win._match_tail is None


def test_qt_skips_stale_backlog_and_leaves_legacy_capture_untouched(app, monkeypatch):
    gui, win, log = app
    seed(gui, win, (2, 4))
    cfg = win._cfg_for_actions()
    secondary = gui.profiles.secondary_state_path(cfg["state"]["path"])
    secondary.parent.mkdir(parents=True, exist_ok=True)
    before = b"Legacy secondary capture data"
    secondary.write_bytes(before)
    win.set_match_automation(True)
    monkeypatch.setattr(match_lifecycle.LogTail, "READ_SIZE", len(START))
    append(log, START + FRONTEND)
    win.poll_match_log()
    assert win.worker.starts == 0
    win.poll_match_log()
    assert win.worker.starts == 0
    assert win.counts == (2, 4)
    append(log, START)
    win.poll_match_log()
    assert win.worker.starts == 1
    assert secondary.read_bytes() == before


def test_qt_deferred_start_waits_for_modal_and_source_scan(app, monkeypatch):
    gui, win, log = app
    from PySide6.QtWidgets import QApplication

    win.start_counting()
    win.set_match_automation(True)
    append(log, START)
    win.poll_match_log()
    assert win.worker.stops == 1
    exit_worker(win)
    with monkeypatch.context() as blocked:
        blocked.setattr(QApplication, "activeModalWidget", lambda: object())
        win.poll_match_log()
        assert win.worker.starts == 1
    win._source_scan = object()
    win.poll_match_log()
    assert win.worker.starts == 1
    win._source_scan = None
    win.poll_match_log()
    assert win.worker.starts == 2


def test_qt_fresh_manual_finish_schedules_one_report_with_current_bot(app, monkeypatch):
    gui, win, _ = app
    seed(gui, win, (5, 9))
    win.discord.auto_report.setChecked(True)
    delivered = Event()
    calls = []
    setup = object()
    online_bot(win, setup)

    def send(config, summary):
        calls.append((config, summary, gui.threading.current_thread().daemon))
        delivered.set()

    monkeypatch.setattr(gui.discord_summary, "send", send)
    win.finish_match()
    win.finish_match()
    saved, = gui.match_history.read_history(win.match_history_path())
    assert delivered.wait(2)
    assert calls == [(setup, saved, False)]


def test_qt_saved_match_recovers_group_outbox_after_enqueue_failure(app, monkeypatch):
    gui, win, _ = app
    group = gui.discord_group
    webhook = group.Webhook("123456789012345678", "fixture-webhook-token")
    monkeypatch.setattr(group, "load_webhook", lambda: webhook)
    gui.C.update_config_file(gui.config_file(), "app", {"group_player": "Rin"})
    seed(gui, win, (5, 9))
    delivered = Event()
    sent = []
    queue_match = group.queue_match
    attempts = 0

    def queue(*args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("simulated local outbox failure")
        return queue_match(*args)

    def publish(values, event, name, count, certain, chest_types):
        sent.append((values.id, event, name, count, certain, chest_types))
        delivered.set()

    monkeypatch.setattr(group, "queue_match", queue)
    monkeypatch.setattr(group, "_publish", publish)
    win.finish_match()
    win.finish_match()
    saved, = gui.match_history.read_history(win.match_history_path())
    assert saved.group_webhook_id == webhook.id and saved.player == "Rin"
    assert delivered.wait(3)
    assert len(sent) == 1 and sent[0][2:] == ("Rin", 9, 5, {"unclassified": 9})


def test_qt_solo_match_stays_local_with_group_configured(app, monkeypatch):
    gui, win, _ = app
    gui.C.update_config_file(gui.config_file(), "app", {"group_player": "Rin", "auto_discord_summary": True})
    win.group.share_matches.setChecked(False)
    monkeypatch.setattr(gui.discord_group, "queue_match", lambda *_: pytest.fail("Unexpected group contribution"))
    monkeypatch.setattr(win, "deliver_saved_match", lambda *_: pytest.fail("Unexpected automatic report"))
    seed(gui, win, (2, 4))
    win.finish_match()
    saved, = gui.match_history.read_history(win.match_history_path())
    assert (saved.player, saved.total, saved.group_webhook_id) == ("Rin", 4, "")
