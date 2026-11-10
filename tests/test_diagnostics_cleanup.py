from fortnite_chest_counter import diagnostics_cleanup


def test_cleanup_removes_only_generated_diagnostics(tmp_path):
    config = {
        "profile": {"state_base": "state/count.json"},
        "logging": {"dir": "custom-logs"},
        "capture": {"dir": "captures"},
    }
    generated = (
        "custom-logs/session_20261110_100000.jsonl",
        "custom-logs/snapshots/session_20261110_100000/event.png",
        "state/count-secondary/logs/session_20261110_100000.jsonl",
        "state/profiles/old-secondary/logs/session_20261110_100000.jsonl",
        "captures/20261110_100000/capture.json",
        "captures/20261110_100000/video/clip.mp4",
    )
    preserved = (
        "custom-logs/notes.txt",
        "captures/20261110_100001/my-video.mp4",
        "state/count.json",
        "state/profiles/old-secondary/old.json",
        "config.toml",
    )
    for name in generated + preserved:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")

    artifacts = diagnostics_cleanup.diagnostic_artifacts(tmp_path, config)
    assert diagnostics_cleanup.remove_diagnostic_artifacts(artifacts) == (5, [])
    assert not diagnostics_cleanup.diagnostic_artifacts(tmp_path, config)
    assert all(not (tmp_path / name).exists() for name in generated)
    assert all((tmp_path / name).exists() for name in preserved)
