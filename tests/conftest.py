"""Reusable fixtures for the pure-logic test suite.

The `sample_clan` fixture returns a hand-built neighborhood data dict with
exactly known numbers so tests can assert precise expected values. The data
is intentionally laid out so every expectation in the test modules can be
derived by hand from the snapshots below.

Member roster
-------------
  #A  Alice  in_clan, leader     -> rich derby + donation history
  #B  Bob    in_clan, co_leader  -> participates sometimes, has a warning fate
  #C  Carol  in_clan, elder      -> low participation, a kick fate
  #D  Dave   former, member      -> left the clan, has some history
  #E  Eve    in_clan, member     -> brand-new (single snapshot only)

Snapshots (chronological)
-------------------------
  2026-01-05  after_derby  D1
  2026-01-12  after_derby  D2
  2026-01-19  after_derby  D3
  2026-01-26  donations    DN1
  2026-02-02  donations    DN2
  2026-02-09  quick        Q1   (Eve's only appearance)
"""

import pytest

from neighborhood_manager import NeighborhoodManager


def _entry(member_id, level=None, participated=None, tasks_done=None,
           tasks_max=None, points=None, fate=None):
    e = {"member_id": member_id}
    if level is not None:
        e["level"] = level
    if participated is not None:
        e["derby_participated"] = participated
        e["tasks_done"] = tasks_done if tasks_done is not None else 0
        e["tasks_max"] = tasks_max if tasks_max is not None else 0
        e["derby_points"] = points if points is not None else 0
    if fate is not None:
        e["fate"] = fate
    return e


def _donation_entry(member_id, cd=0, cr=0, fd=0, fr=0, td=0, tr=0):
    return {
        "member_id": member_id,
        "crops_donated": cd, "crops_requested": cr,
        "foods_donated": fd, "foods_requested": fr,
        "tools_donated": td, "tools_requested": tr,
    }


def build_sample_clan():
    """Return a fresh sample neighborhood data dict (no shared mutable state)."""
    members = {
        "#A": {
            "member_id": "#A", "name": "Alice",
            "name_history": [{"name": "Alice", "changed_on": "2026-01-01"}],
            "in_clan": True, "joined_date": "2026-01-01", "left_date": None,
            "notes": "", "role": "leader",
        },
        "#B": {
            "member_id": "#B", "name": "Bob",
            "name_history": [{"name": "Bob", "changed_on": "2026-01-01"}],
            "in_clan": True, "joined_date": "2026-01-01", "left_date": None,
            "notes": "", "role": "co_leader",
        },
        "#C": {
            "member_id": "#C", "name": "Carol",
            "name_history": [{"name": "Carol", "changed_on": "2026-01-01"}],
            "in_clan": True, "joined_date": "2026-01-01", "left_date": None,
            "notes": "", "role": "elder",
        },
        "#D": {
            "member_id": "#D", "name": "Dave",
            "name_history": [{"name": "Dave", "changed_on": "2026-01-01"}],
            "in_clan": False, "joined_date": "2026-01-01",
            "left_date": "2026-02-01", "notes": "", "role": "member",
        },
        "#E": {
            "member_id": "#E", "name": "Eve",
            "name_history": [{"name": "Eve", "changed_on": "2026-02-09"}],
            "in_clan": True, "joined_date": "2026-02-09", "left_date": None,
            "notes": "", "role": "member",
        },
    }

    snapshots = [
        {
            "snapshot_id": "d1", "date": "2026-01-05", "type": "after_derby",
            "derby_comment": "Derby 1",
            "entries": [
                # Alice: participated, 10/10 tasks, 100 pts, level 50
                _entry("#A", level=50, participated=True, tasks_done=10,
                       tasks_max=10, points=100, fate="stay"),
                # Bob: participated, 5/10 tasks, 50 pts, level 40
                _entry("#B", level=40, participated=True, tasks_done=5,
                       tasks_max=10, points=50),
                # Carol: did NOT participate, level 30
                _entry("#C", level=30, participated=False, tasks_done=0,
                       tasks_max=0, points=0),
                # Dave: participated, 8/8, 80 pts, level 65
                _entry("#D", level=65, participated=True, tasks_done=8,
                       tasks_max=8, points=80),
            ],
        },
        {
            "snapshot_id": "d2", "date": "2026-01-12", "type": "after_derby",
            "derby_comment": "Derby 2",
            "entries": [
                # Alice: participated, 8/10, 90 pts, level 53
                _entry("#A", level=53, participated=True, tasks_done=8,
                       tasks_max=10, points=90, fate="stay"),
                # Bob: did NOT participate, level 40 (no level gain)
                _entry("#B", level=40, participated=False, tasks_done=0,
                       tasks_max=0, points=0, fate="warning"),
                # Carol: participated, tasks_max=0 (dirty data, div-by-zero
                # guard), level 30
                _entry("#C", level=30, participated=True, tasks_done=0,
                       tasks_max=0, points=10),
                # Dave: participated, 6/8, 60 pts, level 67
                _entry("#D", level=67, participated=True, tasks_done=6,
                       tasks_max=8, points=60),
            ],
        },
        {
            "snapshot_id": "d3", "date": "2026-01-19", "type": "after_derby",
            "derby_comment": "Derby 3",
            "entries": [
                # Alice: participated, 9/10, 95 pts, level 58
                _entry("#A", level=58, participated=True, tasks_done=9,
                       tasks_max=10, points=95),
                # Bob: participated, 7/10, 70 pts, level 41
                _entry("#B", level=41, participated=True, tasks_done=7,
                       tasks_max=10, points=70),
                # Carol: did NOT participate, level 30, kick fate
                _entry("#C", level=30, participated=False, tasks_done=0,
                       tasks_max=0, points=0, fate="kick"),
                # Dave: participated, 8/8, 88 pts, level 70
                _entry("#D", level=70, participated=True, tasks_done=8,
                       tasks_max=8, points=88),
            ],
        },
        {
            "snapshot_id": "dn1", "date": "2026-01-26", "type": "donations",
            "derby_comment": "",
            "entries": [
                _donation_entry("#A", cd=100, cr=10, fd=50, fr=5, td=20, tr=2),
                _donation_entry("#B", cd=40, cr=20, fd=10, fr=10, td=5, tr=5),
                _donation_entry("#C", cd=0, cr=30, fd=0, fr=15, td=0, tr=8),
            ],
        },
        {
            "snapshot_id": "dn2", "date": "2026-02-02", "type": "donations",
            "derby_comment": "",
            "entries": [
                _donation_entry("#A", cd=120, cr=12, fd=60, fr=6, td=30, tr=3),
                _donation_entry("#B", cd=60, cr=30, fd=20, fr=20, td=10, tr=10),
                _donation_entry("#C", cd=10, cr=40, fd=5, fr=20, td=2, tr=12),
            ],
        },
        {
            "snapshot_id": "q1", "date": "2026-02-09", "type": "quick",
            "derby_comment": "",
            "entries": [
                _entry("#A", level=60),
                _entry("#B", level=42),
                _entry("#C", level=30),
                _entry("#E", level=15),
            ],
        },
    ]

    return {
        "clan_name": "Test Clan",
        "clan_tag": "#TEST",
        "notes": "fixture",
        "activity_rules": [
            {"level_min": 1, "level_max": 30, "min_levels_gained": 5,
             "time_window_days": 7},
            {"level_min": 31, "level_max": 60, "min_levels_gained": 3,
             "time_window_days": 7},
            {"level_min": 61, "level_max": 9999, "min_levels_gained": 1,
             "time_window_days": 7},
        ],
        "members": members,
        "snapshots": snapshots,
        "manual_activity_bonuses": [],
        "derby_plans": [],
        "ui_prefs": {},
    }


@pytest.fixture
def sample_clan():
    return build_sample_clan()


@pytest.fixture
def manager(tmp_path):
    return NeighborhoodManager(str(tmp_path / "neighborhoods"))
