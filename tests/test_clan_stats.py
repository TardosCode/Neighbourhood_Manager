"""Tests for clan_stats.py — statistics over a neighborhood data dict."""

from datetime import date

import pytest

import clan_stats as cs
import neighborhood_manager as nm


# ----- per-member derby aggregations ----------------------------------------

def test_member_derby_history_only_after_derby(sample_clan):
    hist = cs.member_derby_history(sample_clan, "#A")
    assert len(hist) == 3
    assert [h["snapshot"]["snapshot_id"] for h in hist] == ["d1", "d2", "d3"]


def test_member_derby_participation_rate(sample_clan):
    assert cs.member_derby_participation_rate(sample_clan, "#A") == 1.0
    assert cs.member_derby_participation_rate(sample_clan, "#B") == pytest.approx(2 / 3)
    assert cs.member_derby_participation_rate(sample_clan, "#C") == pytest.approx(1 / 3)
    # no derby history
    assert cs.member_derby_participation_rate(sample_clan, "#E") is None


def test_member_derby_participation_rate_last_n(sample_clan):
    # Bob's last 2 derbies: d2 (no), d3 (yes) -> 1/2
    assert cs.member_derby_participation_rate(sample_clan, "#B", last_n=2) == 0.5
    # Bob's last 1 derby: d3 (yes) -> 1.0
    assert cs.member_derby_participation_rate(sample_clan, "#B", last_n=1) == 1.0


def test_member_avg_tasks(sample_clan):
    assert cs.member_avg_tasks(sample_clan, "#A") == 9.0
    assert cs.member_avg_tasks(sample_clan, "#B") == 6.0
    # Carol participated once with tasks_done=0
    assert cs.member_avg_tasks(sample_clan, "#C") == 0.0
    assert cs.member_avg_tasks(sample_clan, "#E") is None


def test_member_avg_points(sample_clan):
    assert cs.member_avg_points(sample_clan, "#A") == 95.0
    assert cs.member_avg_points(sample_clan, "#B") == 60.0
    assert cs.member_avg_points(sample_clan, "#C") == 10.0


def test_member_total_points_and_tasks(sample_clan):
    assert cs.member_total_points(sample_clan, "#A") == 285
    assert cs.member_total_tasks(sample_clan, "#A") == 27
    assert cs.member_total_points(sample_clan, "#B") == 120
    assert cs.member_total_tasks(sample_clan, "#B") == 12
    assert cs.member_total_points(sample_clan, "#C") == 10
    assert cs.member_total_tasks(sample_clan, "#C") == 0
    assert cs.member_total_points(sample_clan, "#E") == 0


def test_member_avg_task_completion(sample_clan):
    assert cs.member_avg_task_completion(sample_clan, "#A") == pytest.approx(0.9)
    assert cs.member_avg_task_completion(sample_clan, "#B") == pytest.approx(0.6)
    # Carol: only participation had tasks_max=0 -> div-by-zero guard -> None
    assert cs.member_avg_task_completion(sample_clan, "#C") is None
    assert cs.member_avg_task_completion(sample_clan, "#D") == pytest.approx(2.75 / 3)


def test_member_participation_count(sample_clan):
    assert cs.member_participation_count(sample_clan, "#A") == (3, 3)
    assert cs.member_participation_count(sample_clan, "#B") == (2, 3)
    assert cs.member_participation_count(sample_clan, "#C") == (1, 3)
    assert cs.member_participation_count(sample_clan, "#B", last_n=1) == (1, 1)


# ----- level progression ----------------------------------------------------

def test_member_level_progression(sample_clan):
    prog = cs.member_level_progression(sample_clan, "#A")
    assert prog == [("2026-01-05", 50), ("2026-01-12", 53),
                    ("2026-01-19", 58), ("2026-02-09", 60)]


def test_member_total_levels_gained(sample_clan):
    assert cs.member_total_levels_gained(sample_clan, "#A") == 10
    assert cs.member_total_levels_gained(sample_clan, "#B") == 2
    assert cs.member_total_levels_gained(sample_clan, "#C") == 0
    assert cs.member_total_levels_gained(sample_clan, "#D") == 5
    # Eve has only one data point
    assert cs.member_total_levels_gained(sample_clan, "#E") is None


def test_member_levels_gained_between(sample_clan):
    # Alice from 2026-01-12 onward: 53 -> 60 = 7
    assert cs.member_levels_gained_between(sample_clan, "#A", "2026-01-12") == 7
    # cutoff after the last-but-one leaves <2 points -> None
    assert cs.member_levels_gained_between(sample_clan, "#A", "2026-03-01") is None


# ----- clan leaderboards ----------------------------------------------------

def test_clan_top_n_by_task_completion(sample_clan):
    rows = cs.clan_top_n_by_task_completion(sample_clan, n=5, include_former=True)
    ids = [r[0] for r in rows]
    # Dave (~0.917) > Alice (0.9) > Bob (0.6); Carol excluded (no valid ratios)
    assert ids == ["#D", "#A", "#B"]
    assert rows[0][2] == pytest.approx(2.75 / 3)
    assert rows[1][2] == pytest.approx(0.9)


def test_clan_top_n_by_task_completion_exclude_former(sample_clan):
    rows = cs.clan_top_n_by_task_completion(sample_clan, n=5, include_former=False)
    ids = [r[0] for r in rows]
    assert "#D" not in ids
    assert ids == ["#A", "#B"]


def test_clan_top_n_by_total_points(sample_clan):
    rows = cs.clan_top_n_by_total_points(sample_clan, n=5, include_former=True)
    assert [r[0] for r in rows] == ["#A", "#D", "#B", "#C"]
    assert rows[0][2] == 285  # total points
    assert rows[0][3] == 27   # total tasks
    # Eve has no derby points/tasks -> excluded entirely
    assert all(r[0] != "#E" for r in rows)


def test_clan_bottom_n_by_recent_participation(sample_clan):
    rows = cs.clan_bottom_n_by_recent_participation(
        sample_clan, n=5, last_n_derbies=3, include_former=True)
    rates = {r[0]: r[2] for r in rows}
    assert rates["#A"] == 1.0
    assert rates["#B"] == pytest.approx(2 / 3)
    assert rates["#C"] == pytest.approx(1 / 3)
    # ascending order -> lowest first
    assert rows[0][0] == "#C"


def test_members_with_kick_warning_flag(sample_clan):
    rows = cs.members_with_kick_warning_flag(sample_clan, only_in_clan=True)
    flags = {r[0]: r[2] for r in rows}
    assert flags == {"#B": "warning", "#C": "kick"}


# ----- activity status ------------------------------------------------------

TODAY = date(2026, 2, 16)


def test_member_activity_status_below_target(sample_clan):
    info = cs.member_activity_status(sample_clan, "#A", today=TODAY)
    assert info["status"] == nm.ACTIVITY_BELOW_TARGET
    assert info["current_level"] == 60
    assert info["baseline_level"] == 58
    assert info["levels_gained"] == 2
    assert info["target"] == 3


def test_member_activity_status_inactive(sample_clan):
    info = cs.member_activity_status(sample_clan, "#C", today=TODAY)
    assert info["status"] == nm.ACTIVITY_INACTIVE
    assert info["levels_gained"] == 0


def test_member_activity_status_meeting_target(sample_clan):
    # Dave gained 3 levels in his last window (target for 61+ is 1)
    info = cs.member_activity_status(sample_clan, "#D", today=TODAY)
    assert info["status"] == nm.ACTIVITY_MEETING_TARGET
    assert info["levels_gained"] == 3
    assert info["target"] == 1


def test_member_activity_status_new_member(sample_clan):
    info = cs.member_activity_status(sample_clan, "#E", today=TODAY)
    assert info["status"] == nm.ACTIVITY_NEW_MEMBER
    assert info["current_level"] == 15
    assert info["levels_gained"] is None


def test_member_activity_status_no_rule(sample_clan):
    # remove every rule covering Alice's current level (60) -> NO_RULE
    sample_clan["activity_rules"] = [
        {"level_min": 1, "level_max": 40, "min_levels_gained": 5,
         "time_window_days": 7},
    ]
    info = cs.member_activity_status(sample_clan, "#A", today=TODAY)
    assert info["status"] == nm.ACTIVITY_NO_RULE
    assert info["rule"] is None


def test_members_grouped_by_activity_status(sample_clan):
    groups = cs.members_grouped_by_activity_status(sample_clan, today=TODAY)
    # only in-clan members: A, B, C, E (Dave is former)
    assert sorted(m[0] for m in groups.get(nm.ACTIVITY_BELOW_TARGET, [])) == ["#A", "#B"]
    assert [m[0] for m in groups.get(nm.ACTIVITY_INACTIVE, [])] == ["#C"]
    assert [m[0] for m in groups.get(nm.ACTIVITY_NEW_MEMBER, [])] == ["#E"]
    # Dave must not appear anywhere (former)
    all_ids = [m[0] for v in groups.values() for m in v]
    assert "#D" not in all_ids


# ----- donations ------------------------------------------------------------

def test_member_donation_history(sample_clan):
    hist = cs.member_donation_history(sample_clan, "#A")
    assert [h["date"] for h in hist] == ["2026-01-26", "2026-02-02"]


def test_member_donations_total(sample_clan):
    t = cs.member_donations_total(sample_clan, "#A")
    assert t["crops_donated"] == 220
    assert t["foods_donated"] == 110
    assert t["tools_donated"] == 50
    assert t["all_donated"] == 380
    assert t["all_requested"] == 38


def test_member_donations_avg(sample_clan):
    a = cs.member_donations_avg(sample_clan, "#A")
    assert a["weeks_counted"] == 2
    assert a["crops_donated"] == 110.0
    assert a["foods_requested"] == pytest.approx(5.5)
    # member with no donations
    none = cs.member_donations_avg(sample_clan, "#E")
    assert none["weeks_counted"] == 0
    assert none["crops_donated"] == 0.0


def test_clan_total_donations(sample_clan):
    t = cs.clan_total_donations(sample_clan)
    assert t["snapshots_counted"] == 2
    assert t["all_donated"] == 542
    assert t["all_requested"] == 258


def test_clan_donations_per_snapshot(sample_clan):
    rows = cs.clan_donations_per_snapshot(sample_clan)
    assert rows == [("2026-01-26", 225, 105), ("2026-02-02", 317, 153)]


def test_clan_top_n_by_donations(sample_clan):
    rows = cs.clan_top_n_by_donations(sample_clan, n=5)
    # default include_former=False -> only in-clan A, B, C
    assert [r[0] for r in rows] == ["#A", "#B", "#C"]
    assert rows[0][2] == 380   # total_donated
    assert rows[0][3] == 38    # total_requested


def test_clan_top_n_by_requests(sample_clan):
    rows = cs.clan_top_n_by_requests(sample_clan, n=5)
    # ranked by requests desc: Carol (125) > Bob (95) > Alice (38)
    assert [r[0] for r in rows] == ["#C", "#B", "#A"]
    assert rows[0][2] == 125   # total_requested
    assert rows[0][3] == 17    # total_donated


# ----- empty clan edge cases ------------------------------------------------

def test_empty_clan():
    d = nm.default_neighborhood_data("Empty")
    assert cs.clan_top_n_by_donations(d) == []
    assert cs.clan_top_n_by_total_points(d) == []
    assert cs.clan_total_donations(d)["all_donated"] == 0
    assert cs.members_grouped_by_activity_status(d, today=TODAY) == {}
