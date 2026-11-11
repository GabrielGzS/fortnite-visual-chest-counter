from types import SimpleNamespace

from fortnite_chest_counter import match_stats


def member(name, total, boost=1.0):
    return SimpleNamespace(name=name, certain=total, total=total, boost=boost)


def test_team_and_cumulative_count_each_session_once_and_preserve_solo():
    session = SimpleNamespace(players=(member("Alex", 10), member("Sam", 20, 2)))
    rows = [
        SimpleNamespace(snapshot="one", certain=10, total=10, boost=1, session_fingerprint="shared",
                        group_webhook_id="group", player="Alex"),
        SimpleNamespace(snapshot="two", certain=5, total=5, boost=1, session_fingerprint="solo",
                        group_webhook_id="", player="Alex"),
    ]
    team = match_stats.team(session, "alex", current=(11, 12, 1))
    assert team.member_totals == (("alex", 12), ("Sam", 20))
    assert sum(count for _, count in team.member_totals) == team.total
    sessions = {"shared": session}
    result = match_stats.cumulative(rows, sessions, "group", snapshot="one", total=10)
    assert result.total == 35
    expected = match_stats.personal(15, 15, 1) + match_stats.personal(20, 20, 2)
    assert result.chance == expected.chance
    # A completed match's still-visible counter contributes once.
    assert match_stats.cumulative(rows, sessions, "group", snapshot="two", total=5).total == 35
    # A new live game replaces its own delayed shared snapshot, then adds its teammate.
    live = match_stats.cumulative(rows, {"next": session, **sessions}, "group",
                                 snapshot="three", fingerprint="next", player="Alex",
                                 certain=12, total=12, boost=1, sharing=True)
    assert live.total == 67


def test_private_match_and_unverified_solo_have_no_team():
    solo = SimpleNamespace(players=(member("Alex", 10),))
    assert match_stats.team(solo, "Alex") is None
    assert match_stats.team(solo, "Sam") is None
    assert match_stats.team(None, "Alex") is None
    shared = SimpleNamespace(players=(member("Alex", 10), member("Sam", 20)))
    assert match_stats.team(shared, "Other") is None
    match = SimpleNamespace(session_fingerprint="x", group_webhook_id="", player="Alex")
    assert match_stats.saved_team(match, {"x": shared}, "group") is None
