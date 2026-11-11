import json

import pytest

from fortnite_chest_counter import discord_summary, match_history


def test_match_history_reads_both_sources_deduplicates_and_edits(tmp_path):
    primary = tmp_path / "primary.json"
    secondary = tmp_path / "secondary.json"
    primary.write_text(json.dumps({"certain": 4, "approximate": 7, "session_started_at": "one",
                                   "last_event_id": "E0007"}), encoding="utf-8")
    secondary.write_text(json.dumps({"certain": 2, "approximate": 5, "session_started_at": "two",
                                     "last_event_id": "E0005"}), encoding="utf-8")
    identity = "default@"
    single = match_history.read_snapshot(identity, (primary,))
    assert single == match_history.read_snapshot(identity, (primary, tmp_path / "missing.json"))
    key, certain, total = match_history.read_snapshot(identity, (primary, secondary))
    assert (certain, total) == (6, 12)
    match = match_history.Match(key, "2026-11-10 19:20", identity, "Default", "Squad", 6, 6, "0.008727%")
    target = tmp_path / "match_history.json"
    assert match_history.save_match(target, match)
    assert not match_history.save_match(target, match)
    assert match_history.edit_match(target, key, 5, 10, "0.007272%")
    rows = match_history.read_history(target)
    assert match_history.leaderboard(rows) == [("Default", 1, 10, 5)]
    assert "Total: 10 chests" in rows[0].summary()
    assert match_history.delete_match(target, key)
    assert match_history.read_history(target) == []


def test_invalid_counter_is_rejected(tmp_path):
    primary = tmp_path / "counter.json"
    primary.write_text('{"certain": 5, "approximate": 3}', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid counts"):
        match_history.read_snapshot("default", (primary,))


def test_discord_request_has_fixed_destination_and_no_mentions(monkeypatch):
    requested = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    class FakeOpener:
        def open(self, request, timeout):
            requested.append((request, timeout))
            return FakeResponse()

    monkeypatch.setattr(discord_summary, "build_opener", lambda *_: FakeOpener())
    settings = discord_summary.BotSettings("123456789012345678", "fixture.token")
    discord_summary.send(settings, "Summary @everyone")
    request, timeout = requested[0]
    assert request.get_method() == "POST"
    assert request.full_url == "https://discord.com/api/v10/channels/123456789012345678/messages"
    assert request.get_header("Authorization") == "Bot fixture.token"
    assert json.loads(request.data)["allowed_mentions"] == {"parse": []}
    assert timeout == 12
