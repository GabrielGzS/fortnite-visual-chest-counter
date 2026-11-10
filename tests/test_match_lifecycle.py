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
    monkeypatch.setattr(match_lifecycle, "local_log_path", lambda: log)
    monkeypatch.setattr(gui.MainWindow, "refresh_sources", lambda self: None)
    monkeypatch.setattr(gui, "ask", lambda *args, **kwargs: True)
    monkeypatch.setattr(gui, "show_error", lambda parent, message: pytest.fail(message))
    win = gui.MainWindow()
    win.timer.stop()
    win.slow.stop()
    win.worker, win.secondary_worker = Worker(), Worker()
    win._fill_sources([], [(0, 0, 1280, 720), (1280, 0, 1920, 1080)])
    win.dashboard.source.setCurrentIndex(win.dashboard.source.findData({"source": "desktop", "monitor": 1}))
    win.dashboard.secondary_source.setCurrentIndex(
        win.dashboard.secondary_source.findData({"source": "desktop", "monitor": 2}))
    try:
        yield gui, win, log
    finally:
        win.set_match_automation(False)
        win._workers_pending.clear()
        win.worker.alive = win.secondary_worker.alive = False
        win.close()
        application.processEvents()


def seed(gui, win, primary, secondary):
    cfg = win._cfg_for_actions()
    gui.C.set_counts(cfg, *primary)
    gui.C.set_counts(win._secondary_cfg(cfg), *secondary)
    win.read_state(force=True)
    win.read_secondary_state()


def exit_worker(win, role, code=0, acknowledged=True):
    handle = win.handle if role == "primary" else win.handle_secondary
    if acknowledged:
        handle({"type": "stopped", "stop_reason": "stopped in the app"})
    if role == "primary":
        win.worker.alive = False
    else:
        win.secondary_worker.alive = False
    handle({"type": "exit", "code": code})


@pytest.mark.parametrize("send_enabled", [False, True])
def test_qt_drains_both_before_saving_and_before_next_start(app, monkeypatch, send_enabled):
    gui, win, log = app
    delivered = Event()
    summaries = []

    def send(config, content):
        summaries.append(content)
        delivered.set()

    monkeypatch.setattr(gui.discord_summary, "load", lambda: object())
    monkeypatch.setattr(gui.discord_summary, "send", send)
    seed(gui, win, (4, 7), (1, 3))
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
    assert win.worker.starts == win.secondary_worker.starts == 1

    seed(gui, win, (6, 9), (2, 4))
    append(log, FRONTEND + FRONTEND + START)
    win.poll_match_log()
    assert win.worker.stops == win.secondary_worker.stops == 1
    exit_worker(win, "primary")
    win.poll_match_log()
    assert gui.match_history.read_history(win.match_history_path()) == []
    seed(gui, win, (6, 9), (3, 5))
    exit_worker(win, "secondary")
    saved, = gui.match_history.read_history(win.match_history_path())
    assert (saved.certain, saved.total) == win.counts == (9, 14)
    assert win.worker.starts == win.secondary_worker.starts == 1

    # Saving the same snapshot manually is still a no-op.
    win.finish_match()
    assert gui.match_history.read_history(win.match_history_path()) == [saved]
    assert delivered.wait(2 if send_enabled else 0.05) is send_enabled
    assert summaries == ([saved.summary()] if send_enabled else [])

    win.poll_match_log()
    assert win.worker.starts == win.secondary_worker.starts == 2
    assert win.counts == (0, 0)


def test_qt_save_failure_disarms_and_preserves_counts(app, monkeypatch):
    gui, win, log = app
    win.set_match_automation(True)
    append(log, START)
    win.poll_match_log()
    seed(gui, win, (5, 6), (2, 3))
    with monkeypatch.context() as failing:
        def fail(*args):
            raise OSError("test history write failure")

        failing.setattr(gui.match_history, "save_match", fail)
        append(log, FRONTEND + START)
        win.poll_match_log()
        exit_worker(win, "secondary")
        exit_worker(win, "primary")
    win.poll_match_log()
    assert win.worker.starts == win.secondary_worker.starts == 1
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
    seed(gui, win, (2, 3), (1, 2))
    log.rename(log.with_suffix(".backup"))
    log.write_bytes(FRONTEND + START)
    win.poll_match_log()
    assert win._match_tail is None
    assert win.counts == (3, 5)
    assert gui.match_history.read_history(win.match_history_path()) == []


@pytest.mark.parametrize("draining,code,acknowledged", [(False, 0, False), (True, 0, False), (True, 1, True)])
def test_qt_incomplete_secondary_exit_disarms_without_saving(app, draining, code, acknowledged):
    gui, win, log = app
    win.set_match_automation(True)
    append(log, START)
    win.poll_match_log()
    seed(gui, win, (2, 4), (3, 5))
    if draining:
        append(log, FRONTEND)
        win.poll_match_log()
    exit_worker(win, "secondary", code=code, acknowledged=acknowledged)
    exit_worker(win, "primary")
    append(log, FRONTEND + START)
    win.poll_match_log()
    assert win._match_tail is None
    assert win.counts == (5, 9)
    assert gui.match_history.read_history(win.match_history_path()) == []


def test_qt_restores_both_state_files_if_one_reset_cannot_save(app, monkeypatch):
    gui, win, log = app
    seed(gui, win, (2, 4), (3, 5))
    cfg = win._cfg_for_actions()
    primary = Path(cfg["state"]["path"])
    secondary = Path(win._secondary_cfg(cfg)["state"]["path"])
    previous = [path.read_bytes() for path in (primary, secondary)]
    save_state = gui.C.save_state

    def fail_secondary(path, state):
        if Path(path) == secondary:
            raise OSError("test state write failure")
        save_state(path, state)

    monkeypatch.setattr(gui.C, "save_state", fail_secondary)
    win.set_match_automation(True)
    append(log, START)
    win.poll_match_log()
    assert [path.read_bytes() for path in (primary, secondary)] == previous
    assert win.counts == (5, 9)
    assert win.worker.starts == win.secondary_worker.starts == 0
    assert win._match_tail is None


def test_qt_skips_stale_backlog_and_leaves_unselected_source_untouched(app, monkeypatch):
    gui, win, log = app
    seed(gui, win, (2, 4), (3, 5))
    cfg = win._cfg_for_actions()
    secondary = Path(win._secondary_cfg(cfg)["state"]["path"])
    before = secondary.read_bytes()
    win.dashboard.secondary_source.setCurrentIndex(0)
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
    assert win.worker.starts == 1 and win.secondary_worker.starts == 0
    assert secondary.read_bytes() == before


def test_qt_deferred_start_waits_for_modal_and_source_scan(app, monkeypatch):
    gui, win, log = app
    from PySide6.QtWidgets import QApplication

    win.start_counting()
    win.set_match_automation(True)
    append(log, START)
    win.poll_match_log()
    assert win.worker.stops == win.secondary_worker.stops == 1
    exit_worker(win, "primary")
    exit_worker(win, "secondary")
    with monkeypatch.context() as blocked:
        blocked.setattr(QApplication, "activeModalWidget", lambda: object())
        win.poll_match_log()
        assert win.worker.starts == 1
    win._source_scan = object()
    win.poll_match_log()
    assert win.worker.starts == 1
    win._source_scan = None
    win.poll_match_log()
    assert win.worker.starts == win.secondary_worker.starts == 2


def test_qt_fresh_manual_finish_schedules_one_report_with_current_bot(app, monkeypatch):
    gui, win, _ = app
    seed(gui, win, (2, 4), (3, 5))
    win.discord.auto_report.setChecked(True)
    delivered = Event()
    calls = []
    setup = object()
    owner_thread = gui.threading.current_thread()

    def load():
        assert gui.threading.current_thread() is owner_thread
        return setup

    def send(config, summary):
        calls.append((config, summary, gui.threading.current_thread().daemon))
        delivered.set()

    monkeypatch.setattr(gui.discord_summary, "load", load)
    monkeypatch.setattr(gui.discord_summary, "send", send)
    win.finish_match()
    win.finish_match()
    saved, = gui.match_history.read_history(win.match_history_path())
    assert delivered.wait(2)
    assert calls == [(setup, saved.summary(), False)]
