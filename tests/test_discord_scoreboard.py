from fortnite_chest_counter import discord_group, discord_scoreboard
import pytest


def test_shared_scoreboard_round_trip_and_update(monkeypatch):
    webhook = discord_group.Webhook("123456789012345678", "fake-webhook-token")
    ident = "123456789012345679"
    ranking = discord_scoreboard.rows([
        discord_group.Player("Alex", 12, certain=6, chest_types={"rare": 3}, confirmed_total=10, matches=2),
        discord_group.Player("Sam", 5, matches=1),
    ])
    calls = []
    message = {"webhook_id": webhook.id, "id": ident, "channel_id": "123456789012345680"}

    def request(values, suffix, method, payload=None):
        assert values == webhook
        calls.append((suffix, method))
        if payload is not None:
            assert payload["allowed_mentions"] == {"parse": []}
            message.update(payload)
        return message

    monkeypatch.setattr(discord_scoreboard, "_request", request)
    assert discord_scoreboard.publish(webhook, "", ranking)[0] == ident
    assert discord_scoreboard.fetch(webhook, ident) == ranking
    assert ranking[0].estimated == 4
    assert discord_scoreboard.publish(webhook, ident, ranking)[0] == ident
    assert [method for _, method in calls] == ["POST", "GET", "GET", "PATCH"]
    message["embeds"] = []
    with pytest.raises(ValueError, match="not a valid leaderboard"):
        discord_scoreboard.publish(webhook, ident, ranking)
    assert calls[-1][1] == "GET"


def test_scoreboard_accepts_only_message_id_or_discord_message_link():
    ident = "123456789012345679"
    assert discord_scoreboard.message_id(ident) == ident
    assert discord_scoreboard.message_id(f"https://discord.com/channels/1/2/{ident}") == ident
    with pytest.raises(ValueError, match="message link"):
        discord_scoreboard.message_id(f"https://example.com/channels/1/2/{ident}")
