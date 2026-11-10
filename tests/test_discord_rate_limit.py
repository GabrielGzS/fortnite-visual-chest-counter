import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from fortnite_chest_counter import discord_group as group
from fortnite_chest_counter import discord_scoreboard as board


WEBHOOK = group.Webhook("123456789012345678", "rate-fixture-token")


class Response(io.BytesIO):
    status = 200

    def __init__(self, content=b"{}", headers=None):
        super().__init__(content)
        self.headers = headers or {}


@pytest.fixture
def clock(monkeypatch):
    value = [1000.0]
    monkeypatch.setattr(group, "_WEBHOOK_COOLDOWNS", {})
    monkeypatch.setattr(group.time, "monotonic", lambda: value[0])
    monkeypatch.setattr(group.random, "uniform", lambda first, last: (first + last) / 2)
    monkeypatch.setattr(group, "_CLIENT_STAGGER", 1.0)
    return value


def limited(*, headers=None, body=None):
    return HTTPError(WEBHOOK.url, 429, "Too many requests", headers or {},
                     io.BytesIO(json.dumps(body or {}).encode()))


def test_429_preserves_final_event_and_does_not_request_during_cooldown(tmp_path, monkeypatch, clock):
    store = group.GroupStore(WEBHOOK.id, tmp_path / "group.db")
    assert store.queue(SimpleNamespace(snapshot="one", total=4), "Alex")
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            if len(requests) == 1:
                raise limited(headers={"Retry-After": "1.5"}, body={"retry_after": 2.75})
            return Response()

    monkeypatch.setattr(group, "build_opener", lambda *_: Opener())
    with pytest.raises(group.WebhookRateLimited) as caught:
        store.flush(WEBHOOK)
    assert caught.value.retry_after >= 2.75
    assert len(requests) == 1
    with pytest.raises(group.WebhookRateLimited):
        store.flush(WEBHOOK)
    assert len(requests) == 1
    clock[0] += caught.value.retry_after
    assert store.flush(WEBHOOK) == 1
    assert requests[0].data == requests[1].data
    assert store.flush(WEBHOOK) == 0


def test_live_snapshots_still_coalesce_while_discord_is_rate_limiting(tmp_path, monkeypatch, clock):
    store = group.GroupStore(WEBHOOK.id, tmp_path / "group.db")
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            if len(requests) == 1:
                raise limited(body={"retry_after": 3})
            return Response(b'{"id":"234567890123456789"}')

    monkeypatch.setattr(group, "build_opener", lambda *_: Opener())
    assert store.queue_live("a" * 64, "Alex", 1, 2, 1.0)
    with pytest.raises(group.WebhookRateLimited):
        store.flush(WEBHOOK)
    assert store.queue_live("a" * 64, "Alex", 2, 5, 1.0)
    with pytest.raises(group.WebhookRateLimited):
        store.flush(WEBHOOK)
    assert len(requests) == 1
    clock[0] += group.webhook_retry_after(WEBHOOK)
    assert store.flush(WEBHOOK) == 1
    payload = json.loads(requests[-1].data)
    _, latest = group._parse_live(payload["content"])
    assert latest.total == 5 and latest.revision == 2


def test_board_and_contribution_paths_share_one_webhook_cooldown(monkeypatch, clock):
    attempts = []

    class Opener:
        def open(self, request, timeout):
            attempts.append(request)
            raise limited(headers={"Retry-After": "12"})

    monkeypatch.setattr(board, "build_opener", lambda *_: Opener())
    with pytest.raises(group.WebhookRateLimited):
        board._request(WEBHOOK, "/messages/234567890123456789", "GET")
    monkeypatch.setattr(group, "build_opener", lambda *_: pytest.fail("Cooldown allowed an outgoing contribution"))
    with pytest.raises(group.WebhookRateLimited):
        group._publish(WEBHOOK, "b" * 32, "Alex", 3, 2, {})
    with pytest.raises(group.WebhookRateLimited):
        group._publish_live(WEBHOOK, "a" * 64, "Alex", 1, 2, 3, 1.0)
    assert len(attempts) == 1


def test_exhausted_successful_bucket_keeps_other_finals_pending(tmp_path, monkeypatch, clock):
    store = group.GroupStore(WEBHOOK.id, tmp_path / "group.db")
    store.queue(SimpleNamespace(snapshot="one", total=2), "Alex")
    store.queue(SimpleNamespace(snapshot="two", total=3), "Sam")
    payloads = []

    class Opener:
        def open(self, request, timeout):
            payloads.append(json.loads(request.data))
            return Response(headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset-After": "2"})

    monkeypatch.setattr(group, "build_opener", lambda *_: Opener())
    with pytest.raises(group.WebhookRateLimited):
        store.flush(WEBHOOK)
    assert len(payloads) == 1
    with store.connection() as db:
        assert db.execute("SELECT sent FROM outbox ORDER BY rowid").fetchall() == [(1,), (0,)]
    clock[0] += group.webhook_retry_after(WEBHOOK)
    assert store.flush(WEBHOOK) == 1
    assert len(payloads) == 2
    assert payloads[0]["content"] != payloads[1]["content"]


@pytest.mark.parametrize(("headers", "body", "minimum"), [
    ({"Retry-After": "86400"}, {"retry_after": 3600}, 86400),
    ({}, {"retry_after": 0}, 0.5),
    ({}, {"retry_after": -1}, 1),
    ({}, {"retry_after": 10 ** 1000}, 1),
    ({"Retry-After": "NaN"}, {"retry_after": float("inf")}, 1),
    ({"Retry-After": "garbage"}, {"retry_after": True}, 1),
])
def test_retry_metadata_is_validated_without_shortening_server_wait(headers, body, minimum, clock):
    error = group.webhook_rate_limited(WEBHOOK, limited(headers=headers, body=body))
    assert minimum <= error.retry_after <= minimum + 0.5
    assert group.webhook_retry_after(WEBHOOK.id) == error.retry_after


def test_global_discord_limit_and_stagger_use_monotonic_time(clock):
    error = group.webhook_rate_limited(WEBHOOK, limited(body={"retry_after": 9, "global": True}))
    assert group.webhook_retry_after("different-webhook") == error.retry_after
    assert group.webhook_sync_delay("different-webhook", base=5) >= error.retry_after
    clock[0] += error.retry_after
    assert group.webhook_sync_delay(None, base=0) == 1.5
    assert group.webhook_sync_delay("", base=5) == 6.5


@pytest.mark.parametrize("header", [{"X-RateLimit-Global": "true"}, {"X-RateLimit-Scope": "global"}])
def test_global_header_pauses_other_webhooks_without_json_global_flag(header, clock):
    group.webhook_rate_limited(WEBHOOK, limited(headers={**header, "Retry-After": "12"}))
    assert group.webhook_retry_after("987654321098765432") >= 12
