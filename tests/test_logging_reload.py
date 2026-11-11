from copy import deepcopy
import json
import os
from types import SimpleNamespace

import numpy as np

from fortnite_chest_counter import counter, estimator, settings


def make_session(tmp_path, *, enabled=True, snapshots=True):
    config = tmp_path / "config.toml"
    log_dir = tmp_path / "logs"
    cfg = deepcopy(settings.DEFAULTS)
    cfg["state"].update(persist=False, path=str(tmp_path / "state.json"), obs_dir=str(tmp_path / "obs"))
    cfg["logging"].update(enabled=enabled, save_snapshots=snapshots, dir=str(log_dir))
    config.write_text("[logging]\nenabled = " + str(enabled).lower() + "\nsave_snapshots = "
                      + str(snapshots).lower() + "\ndir = " + json.dumps(str(log_dir)) + "\n", encoding="utf-8")
    session = counter.CounterSession(cfg)
    watcher = counter.DisplayConfigWatcher(SimpleNamespace(config=str(config)))
    return config, session, watcher


def write_logging(config, watcher, *, enabled, snapshots, candidates=True):
    config.write_text("[logging]\nenabled = " + str(enabled).lower()
                      + "\nsave_snapshots = " + str(snapshots).lower()
                      + "\nlog_candidates = " + str(candidates).lower() + "\n", encoding="utf-8")
    stamp = watcher.mtime + 1_000_000_000
    os.utime(config, ns=(stamp, stamp))


def event(second, *, counted=True):
    return {"time": second, "source": "popup", "adjusted_tier": "HIGH", "certain_counted": counted,
            "approx_counted": counted, "reason": "fixture", "_snapshot": np.full((3, 4, 3), 123, np.uint8)}


def test_no_config_defaults_keep_diagnostics_off_without_disabling_counts(tmp_path, monkeypatch):
    config = tmp_path / "missing.toml"
    monkeypatch.setattr(settings, "DEFAULT_CONFIG_PATH", config)
    cfg, _, warnings = settings.load_config(None, {
        ("state", "path"): str(tmp_path / "state.json"),
        ("state", "obs_dir"): str(tmp_path / "obs"),
        ("logging", "dir"): str(tmp_path / "logs"),
    })
    assert not warnings and not config.exists()
    assert all(cfg["logging"][key] is False for key in ("enabled", "log_candidates", "save_snapshots"))
    assert cfg["capture"]["mode"] == "off"
    session = counter.CounterSession(cfg)
    # Both a rejected candidate and a counted popup carry snapshot pixels: neither
    # may create diagnostics when the user has not opted in.
    session.apply([event(1, counted=False), event(3)], 4, quiet=True)
    assert session.log.path is None and not (tmp_path / "logs").exists()
    assert not list(tmp_path.rglob("*.jsonl")) and not list(tmp_path.rglob("*.png"))
    assert session.state["certain"] == session.state["approximate"] == 1
    assert json.loads((tmp_path / "state.json").read_text())["certain"] == 1
    assert (tmp_path / "obs" / "certain_chests.txt").read_text() == "CERTAIN OPENED CHESTS: 1\n"
    assert (tmp_path / "obs" / "approximate_chests.txt").read_text() == "APPROX. OPENED CHESTS: 1\n"


def test_saved_logging_switch_stops_files_and_snapshots_then_resumes_same_session(tmp_path, monkeypatch):
    config, session, watcher = make_session(tmp_path)
    monkeypatch.setattr(estimator, "SAVE_SNAPSHOTS", True)
    session.apply([event(1)], 2, quiet=True)
    original_path = session.log.path
    original_log = original_path.read_bytes()
    original_snapshots = list(session.log.snapshot_dir.glob("*.png"))
    assert len(original_snapshots) == 1
    write_logging(config, watcher, enabled=False, snapshots=True)
    assert watcher.check(session)
    assert not session.log.enabled and not estimator.SAVE_SNAPSHOTS
    session.apply([event(3)], 4, quiet=True)
    assert original_path.read_bytes() == original_log
    assert list((tmp_path / "logs" / "snapshots").rglob("*.png")) == original_snapshots
    assert session.state["certain"] == 2

    write_logging(config, watcher, enabled=True, snapshots=False, candidates=False)
    assert watcher.check(session)
    assert session.log.path == original_path
    assert not estimator.SAVE_SNAPSHOTS and not session.log.log_candidates
    session.apply([event(5, counted=False)], 6, quiet=True)
    assert original_path.read_bytes() == original_log
    session.apply([event(7)], 8, quiet=True)
    assert len(original_path.read_text().splitlines()) == 2
    assert list((tmp_path / "logs" / "snapshots").rglob("*.png")) == original_snapshots

    write_logging(config, watcher, enabled=True, snapshots=True)
    assert watcher.check(session)
    assert estimator.SAVE_SNAPSHOTS
    session.apply([event(9)], 10, quiet=True)
    assert session.log.path == original_path
    assert len(list((tmp_path / "logs" / "snapshots").rglob("*.png"))) == 2


def test_disabled_session_creates_no_logs_and_can_be_enabled_without_restart(tmp_path, monkeypatch):
    config, session, watcher = make_session(tmp_path, enabled=False)
    monkeypatch.setattr(estimator, "SAVE_SNAPSHOTS", False)
    assert session.log.path is None and not (tmp_path / "logs").exists()
    session.apply([event(1)], 2, quiet=True)
    write_logging(config, watcher, enabled=False, snapshots=True)
    assert watcher.check(session)
    session.apply([event(3)], 4, quiet=True)
    assert not (tmp_path / "logs").exists()
    assert session.log.save_snapshot("direct.png", np.zeros((2, 2, 3), np.uint8)) is None

    write_logging(config, watcher, enabled=True, snapshots=True)
    assert watcher.check(session)
    assert session.log.directory == tmp_path / "logs"
    assert estimator.SAVE_SNAPSHOTS
    session.apply([event(5)], 6, quiet=True)
    assert session.log.path.is_file()
    assert len(list((tmp_path / "logs" / "snapshots").rglob("*.png"))) == 1
