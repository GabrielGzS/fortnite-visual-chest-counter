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



def test_board_keeps_legacy_rows_and_round_trips_optional_team_summary(monkeypatch):
    webhook = discord_group.Webhook("123456789012345678", "fake-webhook-token")
    ident = "234567890123456789"
    ranking = (discord_scoreboard.Row("Sam", 20, 2),)
    response = {"id": ident, "channel_id": "345678901234567890", "webhook_id": webhook.id}
    edits = []

    def request(_, suffix, method, payload=None):
        if payload:
            response.update(payload)
            edits.append(method)
        return response

    monkeypatch.setattr(discord_scoreboard, "_request", request)
    discord_scoreboard.publish(webhook, "", ranking)
    assert discord_scoreboard.fetch(webhook, ident, with_team=True) == (ranking, None)
    for team in (discord_group.TeamSummary(), discord_group.TeamSummary(1, 1, 0),
                 discord_group.TeamSummary(1, 2, 20, 4567, "0.021896%")):
        discord_scoreboard.publish(webhook, ident, ranking, team)
        assert discord_scoreboard.fetch(webhook, ident) == ranking
        assert discord_scoreboard.fetch(webhook, ident, with_team=True) == (ranking, team)
    assert edits == ["POST", "PATCH", "PATCH", "PATCH"]
    assert discord_scoreboard.fetch(webhook, ident, with_settings=True) == (ranking, team, None)
    discord_scoreboard.publish(webhook, ident, ranking, team, settings=("Duo", 1.5))
    assert discord_scoreboard.fetch(webhook, ident, with_settings=True) == (ranking, team, ("Duo", 1.5))
    assert discord_scoreboard.fetch(webhook, ident, with_team=True) == (ranking, team)


def test_delete_requires_a_matching_leaderboard(monkeypatch):
    webhook = discord_group.Webhook("123456789012345678", "fake-webhook-token")
    ident = "234567890123456789"
    message = {"webhook_id": webhook.id, "embeds": []}
    methods = []

    def request(_, suffix, method, payload=None):
        assert suffix == f"/messages/{ident}"
        methods.append(method)
        return message if method == "GET" else None

    monkeypatch.setattr(discord_scoreboard, "_request", request)
    with pytest.raises(ValueError, match="not a valid leaderboard"):
        discord_scoreboard.delete(webhook, ident)
    assert methods == ["GET"]
    message["embeds"] = [{"footer": {"text": "Fortnite Visual Chest Counter | Shared leaderboard v1"}}]
    discord_scoreboard.delete(webhook, ident)
    assert methods == ["GET", "GET", "DELETE"]
