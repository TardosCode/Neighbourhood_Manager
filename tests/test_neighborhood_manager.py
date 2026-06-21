"""Tests for neighborhood_manager.py — the data layer + file store."""

import json
import os

import pytest

import neighborhood_manager as nm


# ----- default data ---------------------------------------------------------

def test_default_neighborhood_data_keys():
    d = nm.default_neighborhood_data("My Clan", "#TAG", "notes")
    assert d["clan_name"] == "My Clan"
    assert d["clan_tag"] == "#TAG"
    assert d["notes"] == "notes"
    assert d["members"] == {}
    assert d["snapshots"] == []
    assert d["manual_activity_bonuses"] == []
    assert d["derby_plans"] == []
    assert d["ui_prefs"] == {}
    # default activity rules copied in
    assert len(d["activity_rules"]) == 3
    assert d["activity_rules"][0]["level_min"] == 1
    # must be deep copies, not the module-level list
    assert d["activity_rules"] is not nm.DEFAULT_ACTIVITY_RULES


def test_default_member_data():
    m = nm.default_member_data("#X", "Xavier", in_clan=True, role="elder")
    assert m["member_id"] == "#X"
    assert m["name"] == "Xavier"
    assert m["in_clan"] is True
    assert m["joined_date"] is not None
    assert m["left_date"] is None
    assert m["role"] == "elder"
    assert m["name_history"][0]["name"] == "Xavier"

    m2 = nm.default_member_data("#Y", "Yara", in_clan=False)
    assert m2["joined_date"] is None
    assert m2["role"] == "member"


# ----- add_member -----------------------------------------------------------

def test_add_member_basic():
    d = nm.default_neighborhood_data()
    nm.add_member(d, "#1", "One")
    assert "#1" in d["members"]
    assert d["members"]["#1"]["role"] == "member"


def test_add_member_duplicate_raises():
    d = nm.default_neighborhood_data()
    nm.add_member(d, "#1", "One")
    with pytest.raises(ValueError):
        nm.add_member(d, "#1", "Again")


def test_add_member_invalid_role_falls_back():
    d = nm.default_neighborhood_data()
    nm.add_member(d, "#1", "One", role="emperor")
    assert d["members"]["#1"]["role"] == "member"


def test_add_member_max_clan_size():
    d = nm.default_neighborhood_data()
    for i in range(nm.MAX_CLAN_SIZE):
        nm.add_member(d, f"#{i}", f"M{i}")
    assert sum(1 for m in d["members"].values() if m["in_clan"]) == 30
    with pytest.raises(ValueError):
        nm.add_member(d, "#over", "Over")
    # but a former member is allowed past the cap
    nm.add_member(d, "#former", "Former", in_clan=False)
    assert "#former" in d["members"]


# ----- update_member --------------------------------------------------------

def test_update_member_name_history():
    d = nm.default_neighborhood_data()
    nm.add_member(d, "#1", "Old")
    nm.update_member(d, "#1", name="New")
    m = d["members"]["#1"]
    assert m["name"] == "New"
    assert len(m["name_history"]) == 2
    assert m["name_history"][-1]["name"] == "New"
    # same name twice does not append
    nm.update_member(d, "#1", name="New")
    assert len(m["name_history"]) == 2


def test_update_member_leave_and_rejoin():
    d = nm.default_neighborhood_data()
    nm.add_member(d, "#1", "One")
    join = d["members"]["#1"]["joined_date"]
    nm.update_member(d, "#1", in_clan=False)
    assert d["members"]["#1"]["in_clan"] is False
    assert d["members"]["#1"]["left_date"] is not None
    # rejoin keeps original joined_date, clears left_date
    nm.update_member(d, "#1", in_clan=True)
    assert d["members"]["#1"]["in_clan"] is True
    assert d["members"]["#1"]["joined_date"] == join
    assert d["members"]["#1"]["left_date"] is None


def test_update_member_rejoin_blocked_at_max():
    d = nm.default_neighborhood_data()
    for i in range(nm.MAX_CLAN_SIZE):
        nm.add_member(d, f"#{i}", f"M{i}")
    nm.add_member(d, "#former", "Former", in_clan=False)
    with pytest.raises(ValueError):
        nm.update_member(d, "#former", in_clan=True)


def test_update_member_role_and_notes():
    d = nm.default_neighborhood_data()
    nm.add_member(d, "#1", "One")
    nm.update_member(d, "#1", role="leader", notes="hi")
    assert d["members"]["#1"]["role"] == "leader"
    assert d["members"]["#1"]["notes"] == "hi"
    # invalid role ignored
    nm.update_member(d, "#1", role="bogus")
    assert d["members"]["#1"]["role"] == "leader"


def test_update_member_missing_raises():
    d = nm.default_neighborhood_data()
    with pytest.raises(ValueError):
        nm.update_member(d, "#nope", name="x")


# ----- delete_member --------------------------------------------------------

def test_delete_member_removes_from_snapshots(sample_clan):
    nm.delete_member(sample_clan, "#A")
    assert "#A" not in sample_clan["members"]
    for snap in sample_clan["snapshots"]:
        assert all(e["member_id"] != "#A" for e in snap["entries"])


def test_delete_member_missing_raises(sample_clan):
    with pytest.raises(ValueError):
        nm.delete_member(sample_clan, "#nope")


# ----- snapshots ------------------------------------------------------------

def test_add_snapshot_assigns_id_and_sorts():
    d = nm.default_neighborhood_data()
    nm.add_snapshot(d, {"date": "2026-03-01", "type": "quick", "entries": []})
    nm.add_snapshot(d, {"date": "2026-01-01", "type": "quick", "entries": []})
    nm.add_snapshot(d, {"date": "2026-02-01", "type": "quick", "entries": []})
    dates = [s["date"] for s in d["snapshots"]]
    assert dates == ["2026-01-01", "2026-02-01", "2026-03-01"]
    assert all("snapshot_id" in s for s in d["snapshots"])


def test_get_snapshot(sample_clan):
    assert nm.get_snapshot(sample_clan, "d1")["date"] == "2026-01-05"
    assert nm.get_snapshot(sample_clan, "nope") is None


def test_update_snapshot(sample_clan):
    nm.update_snapshot(sample_clan, "d1",
                       {"date": "2026-03-30", "type": "quick", "entries": []})
    snap = nm.get_snapshot(sample_clan, "d1")
    assert snap["date"] == "2026-03-30"
    assert snap["type"] == "quick"
    # re-sorted to the end
    assert sample_clan["snapshots"][-1]["snapshot_id"] == "d1"


def test_update_snapshot_missing_raises(sample_clan):
    with pytest.raises(ValueError):
        nm.update_snapshot(sample_clan, "nope", {"date": "2026-01-01"})


def test_delete_snapshot(sample_clan):
    nm.delete_snapshot(sample_clan, "d1")
    assert nm.get_snapshot(sample_clan, "d1") is None
    with pytest.raises(ValueError):
        nm.delete_snapshot(sample_clan, "d1")


# ----- latest_* helpers -----------------------------------------------------

def test_latest_levels(sample_clan):
    levels = nm.latest_levels(sample_clan)
    # quick snapshot 2026-02-09 has the newest levels
    assert levels["#A"] == 60
    assert levels["#B"] == 42
    assert levels["#C"] == 30
    assert levels["#D"] == 70  # last seen 2026-01-19
    assert levels["#E"] == 15


def test_latest_snapshot_date_for_member(sample_clan):
    assert nm.latest_snapshot_date_for_member(sample_clan, "#A") == "2026-02-09"
    assert nm.latest_snapshot_date_for_member(sample_clan, "#D") == "2026-01-19"
    assert nm.latest_snapshot_date_for_member(sample_clan, "#nope") is None


def test_latest_fate_for_member(sample_clan):
    # Bob: warning on 2026-01-12 (his only fate)
    assert nm.latest_fate_for_member(sample_clan, "#B") == "warning"
    # Carol: kick on 2026-01-19 (latest)
    assert nm.latest_fate_for_member(sample_clan, "#C") == "kick"
    # Alice: stay (2026-01-12 latest stay)
    assert nm.latest_fate_for_member(sample_clan, "#A") == "stay"
    # Eve: no fate
    assert nm.latest_fate_for_member(sample_clan, "#E") is None


# ----- activity rule validation ---------------------------------------------

def test_validate_activity_rules_valid(sample_clan):
    assert nm.validate_activity_rules(sample_clan["activity_rules"]) == []


def test_validate_activity_rules_empty():
    errs = nm.validate_activity_rules([])
    assert len(errs) == 1


def test_validate_activity_rules_first_not_one():
    rules = [{"level_min": 2, "level_max": 60, "min_levels_gained": 3,
              "time_window_days": 7}]
    errs = nm.validate_activity_rules(rules)
    assert any("level 1" in e for e in errs)


def test_validate_activity_rules_gap():
    rules = [
        {"level_min": 1, "level_max": 30, "min_levels_gained": 5,
         "time_window_days": 7},
        {"level_min": 40, "level_max": 60, "min_levels_gained": 3,
         "time_window_days": 7},
    ]
    errs = nm.validate_activity_rules(rules)
    assert any("Gap" in e for e in errs)


def test_validate_activity_rules_overlap():
    rules = [
        {"level_min": 1, "level_max": 30, "min_levels_gained": 5,
         "time_window_days": 7},
        {"level_min": 25, "level_max": 60, "min_levels_gained": 3,
         "time_window_days": 7},
    ]
    errs = nm.validate_activity_rules(rules)
    assert any("overlap" in e for e in errs)


def test_validate_activity_rules_bad_fields():
    rules = [{"level_min": "x", "level_max": 30, "min_levels_gained": 5,
              "time_window_days": 7}]
    errs = nm.validate_activity_rules(rules)
    assert any("non-integer" in e for e in errs)


def test_validate_activity_rules_bad_ranges():
    rules = [{"level_min": 0, "level_max": -1, "min_levels_gained": -2,
              "time_window_days": 0}]
    errs = nm.validate_activity_rules(rules)
    # level_min<1, level_max<level_min, mlg<0, twd<1 -> 4 errors
    assert len(errs) == 4


def test_find_rule_for_level(sample_clan):
    rules = sample_clan["activity_rules"]
    assert nm.find_rule_for_level(rules, 30)["min_levels_gained"] == 5
    assert nm.find_rule_for_level(rules, 31)["min_levels_gained"] == 3
    assert nm.find_rule_for_level(rules, 100)["min_levels_gained"] == 1
    assert nm.find_rule_for_level([], 50) is None


# ----- manual bonuses -------------------------------------------------------

def test_manual_bonus_add_total_delete(sample_clan):
    e1 = nm.add_manual_activity_bonus(sample_clan, "#A", 5, "great")
    e2 = nm.add_manual_activity_bonus(sample_clan, "#A", -2, "oops")
    assert nm.manual_activity_total_for_member(sample_clan, "#A") == 3
    assert len(nm.manual_activity_bonuses_for_member(sample_clan, "#A")) == 2
    nm.delete_manual_activity_bonus(sample_clan, e1["id"])
    assert nm.manual_activity_total_for_member(sample_clan, "#A") == -2
    assert e2["points"] == -2


def test_manual_bonus_validation(sample_clan):
    with pytest.raises(ValueError):
        nm.add_manual_activity_bonus(sample_clan, "#nope", 5, "x")
    with pytest.raises(ValueError):
        nm.add_manual_activity_bonus(sample_clan, "#A", 5, "   ")
    with pytest.raises(ValueError):
        nm.add_manual_activity_bonus(sample_clan, "#A", 1.5, "x")


def test_manual_total_empty(sample_clan):
    assert nm.manual_activity_total_for_member(sample_clan, "#B") == 0


# ----- UI prefs -------------------------------------------------------------

def test_ui_prefs(sample_clan):
    assert nm.get_ui_pref(sample_clan, "members.show_former") is None
    assert nm.get_ui_pref(sample_clan, "members.show_former", True) is True
    nm.set_ui_pref(sample_clan, "members.show_former", False)
    assert nm.get_ui_pref(sample_clan, "members.show_former") is False


# ----- NeighborhoodManager file store ---------------------------------------

def test_manager_create_load_save(manager):
    d = nm.default_neighborhood_data("Clan A", "#A")
    manager.create("Clan A", d)
    assert manager.neighborhood_exists("Clan A")
    loaded = manager.load("Clan A")
    assert loaded["clan_name"] == "Clan A"


def test_manager_create_duplicate_raises(manager):
    manager.create("Clan A", nm.default_neighborhood_data("Clan A"))
    with pytest.raises(ValueError):
        manager.create("Clan A", nm.default_neighborhood_data("Clan A"))


def test_manager_list(manager):
    manager.create("Bravo", nm.default_neighborhood_data("Bravo"))
    manager.create("Alpha", nm.default_neighborhood_data("Alpha"))
    assert manager.list_neighborhoods() == ["Alpha", "Bravo"]


def test_manager_rename(manager):
    manager.create("Old", nm.default_neighborhood_data("Old"))
    manager.set_active("Old")
    manager.rename("Old", "New")
    assert not manager.neighborhood_exists("Old")
    assert manager.neighborhood_exists("New")
    assert manager.load("New")["clan_name"] == "New"
    # active pointer followed the rename
    assert manager.get_active() == "New"


def test_manager_rename_missing_raises(manager):
    with pytest.raises(ValueError):
        manager.rename("Ghost", "New")


def test_manager_rename_to_existing_raises(manager):
    manager.create("A", nm.default_neighborhood_data("A"))
    manager.create("B", nm.default_neighborhood_data("B"))
    with pytest.raises(ValueError):
        manager.rename("A", "B")


def test_manager_delete_clears_active(manager):
    manager.create("Clan", nm.default_neighborhood_data("Clan"))
    manager.set_active("Clan")
    assert manager.get_active() == "Clan"
    manager.delete("Clan")
    assert not manager.neighborhood_exists("Clan")
    assert manager.get_active() is None


def test_manager_get_active_none(manager):
    assert manager.get_active() is None


def test_manager_set_get_active(manager):
    manager.create("Clan", nm.default_neighborhood_data("Clan"))
    manager.set_active("Clan")
    assert manager.get_active() == "Clan"
    # active pointing at a non-existent clan resolves to None
    manager.set_active("Ghost")
    assert manager.get_active() is None


def test_manager_load_backfills_missing_keys(manager, tmp_path):
    # write a minimal/old-style file directly, bypassing defaults
    old = {
        "clan_name": "Legacy",
        "members": {
            "#1": {"member_id": "#1", "name": "One", "in_clan": True,
                   "joined_date": None, "left_date": None, "name_history": []},
        },
        "snapshots": [],
    }
    path = os.path.join(manager.dir, "Legacy.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(old, f)
    loaded = manager.load("Legacy")
    assert "activity_rules" in loaded and len(loaded["activity_rules"]) == 3
    assert loaded["manual_activity_bonuses"] == []
    assert loaded["derby_plans"] == []
    assert loaded["ui_prefs"] == {}
    # member role backfilled
    assert loaded["members"]["#1"]["role"] == "member"


def test_manager_cache(manager):
    manager.create("Clan", nm.default_neighborhood_data("Clan"))
    a = manager.load("Clan")
    b = manager.load("Clan")
    assert a is b  # served from cache
    manager.invalidate_cache("Clan")
    c = manager.load("Clan")
    assert c is not a
