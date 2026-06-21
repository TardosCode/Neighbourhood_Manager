"""
Tests for derby_planner — the Derby Planner & Predictor logic layer.

These tests are intentionally self-contained: each builds the small
neighborhood data dicts it needs inline rather than relying on shared
fixtures, so the file documents exactly which inputs produce which
predictions. All numbers asserted here are computed by hand from the
inline data.
"""

import math

import pytest

import derby_planner as dp


# --------------------------------------------------------------------------
# data builders
# --------------------------------------------------------------------------

def _member(mid, name, in_clan=True, role="member"):
    return {"member_id": mid, "name": name, "in_clan": in_clan, "role": role}


def _derby_snap(snap_id, date, entries):
    return {"snapshot_id": snap_id, "date": date,
            "type": "after_derby", "entries": entries}


def _entry(mid, participated, points=0, tasks=0, tmax=0, level=50):
    return {"member_id": mid, "level": level,
            "derby_participated": participated,
            "tasks_done": tasks, "tasks_max": tmax, "derby_points": points}


@pytest.fixture
def clan():
    """Three members with hand-chosen derby histories:

    Alice  — joined all 3, points 900/950/1000 (rising, consistent)  -> reliable
    Bob    — joined 1 of 3, points 500                               -> risky
    Cara   — joined 2 of 3, points 800/700                           -> inconsistent
    """
    return {
        "members": {
            "#A": _member("#A", "Alice", role="leader"),
            "#B": _member("#B", "Bob"),
            "#C": _member("#C", "Cara"),
        },
        "snapshots": [
            _derby_snap("s1", "2026-05-01", [
                _entry("#A", True, 900, 9, 10, 80),
                _entry("#B", True, 500, 5, 10, 70),
                _entry("#C", False, 0, 0, 10, 60),
            ]),
            _derby_snap("s2", "2026-05-08", [
                _entry("#A", True, 950, 10, 10, 81),
                _entry("#B", False, 0, 0, 10, 70),
                _entry("#C", True, 800, 8, 10, 61),
            ]),
            _derby_snap("s3", "2026-05-15", [
                _entry("#A", True, 1000, 10, 10, 82),
                _entry("#B", False, 0, 0, 10, 70),
                _entry("#C", True, 700, 7, 10, 62),
            ]),
        ],
    }


# --------------------------------------------------------------------------
# numeric helpers
# --------------------------------------------------------------------------

def test_mean_and_pstdev():
    assert dp._mean([]) is None
    assert dp._mean([2, 4, 6]) == 4
    assert dp._pstdev([5]) is None              # need >= 2 points
    assert dp._pstdev([2, 4, 6]) == pytest.approx(math.sqrt(8 / 3))


def test_consistency_clamped_and_none_cases():
    assert dp._consistency([5]) is None         # too few
    assert dp._consistency([0, 0]) is None       # mean 0 -> no ratio
    # identical values -> perfectly consistent
    assert dp._consistency([100, 100, 100]) == 1.0
    # spread >= mean (cv >= 1) -> clamped to 0, never negative
    assert dp._consistency([0, 300]) == 0.0       # mean 150, stddev 150, cv 1.0
    val = dp._consistency([90, 100, 110])
    assert 0.0 < val < 1.0


def test_trend_sign():
    assert dp._trend([10]) is None
    # improving: recent half mean > older half mean
    assert dp._trend([100, 200, 300]) > 0
    # declining
    assert dp._trend([300, 200, 100]) < 0


# --------------------------------------------------------------------------
# member_derby_profile
# --------------------------------------------------------------------------

def test_profile_reliable_member(clan):
    p = dp.member_derby_profile(clan, "#A")
    assert p["name"] == "Alice"
    assert p["derbies_counted"] == 3
    assert p["participated"] == 3
    assert p["participation_rate"] == 1.0
    assert p["avg_points"] == pytest.approx((900 + 950 + 1000) / 3)
    assert p["avg_completion"] == pytest.approx((0.9 + 1.0 + 1.0) / 3)
    assert p["last_points"] == 1000
    # expected = avg * participation = avg * 1.0
    assert p["expected_points"] == pytest.approx(950.0)
    assert p["trend"] > 0                         # rising scores
    assert p["risk"] == dp.RISK_RELIABLE


def test_profile_risky_member(clan):
    p = dp.member_derby_profile(clan, "#B")
    assert p["participated"] == 1
    assert p["participation_rate"] == pytest.approx(1 / 3)
    assert p["avg_points"] == 500
    # expected points discounted heavily by low participation
    assert p["expected_points"] == pytest.approx(500 / 3)
    assert p["risk"] == dp.RISK_RISKY
    # only one participated derby -> stddev/consistency undefined
    assert p["points_stddev"] is None
    assert p["consistency"] is None


def test_profile_inconsistent_member(clan):
    p = dp.member_derby_profile(clan, "#C")
    assert p["participated"] == 2
    assert p["participation_rate"] == pytest.approx(2 / 3)
    assert p["avg_points"] == pytest.approx(750.0)
    assert p["expected_points"] == pytest.approx(500.0)
    # participates >50% but consistency not high enough for "reliable"
    # given a 0.67 rate (< 0.8), it lands as inconsistent
    assert p["risk"] == dp.RISK_INCONSISTENT


def test_profile_unknown_member_no_history():
    data = {"members": {"#X": _member("#X", "Xander")}, "snapshots": []}
    p = dp.member_derby_profile(data, "#X")
    assert p["derbies_counted"] == 0
    assert p["participation_rate"] is None
    assert p["expected_points"] is None
    assert p["risk"] == dp.RISK_UNKNOWN


def test_profile_last_n_limits_window(clan):
    # last 1 derby for Alice -> only the 1000-point derby
    p = dp.member_derby_profile(clan, "#A", last_n=1)
    assert p["derbies_counted"] == 1
    assert p["avg_points"] == 1000
    assert p["last_points"] == 1000


def test_classify_risk_thresholds():
    # not enough history
    assert dp.classify_risk(1.0, 1.0, 1) == dp.RISK_UNKNOWN
    # no participation data
    assert dp.classify_risk(None, 1.0, 5) == dp.RISK_UNKNOWN
    # below risky cutoff
    assert dp.classify_risk(0.4, 1.0, 5) == dp.RISK_RISKY
    # high participation + high consistency
    assert dp.classify_risk(0.9, 0.8, 5) == dp.RISK_RELIABLE
    # high participation but low consistency -> inconsistent
    assert dp.classify_risk(0.9, 0.3, 5) == dp.RISK_INCONSISTENT
    # mid participation -> inconsistent
    assert dp.classify_risk(0.6, 0.9, 5) == dp.RISK_INCONSISTENT


# --------------------------------------------------------------------------
# all_member_profiles
# --------------------------------------------------------------------------

def test_all_profiles_sorted_by_expected_points(clan):
    profiles = dp.all_member_profiles(clan)
    order = [p["member_id"] for p in profiles]
    assert order == ["#A", "#C", "#B"]            # 950 > 500 > 167


def test_all_profiles_excludes_former_by_default():
    data = {
        "members": {
            "#A": _member("#A", "Alice", in_clan=True),
            "#G": _member("#G", "Ghost", in_clan=False),
        },
        "snapshots": [
            _derby_snap("s1", "2026-05-01", [
                _entry("#A", True, 900, 9, 10),
                _entry("#G", True, 800, 8, 10),
            ]),
            _derby_snap("s2", "2026-05-08", [
                _entry("#A", True, 900, 9, 10),
                _entry("#G", True, 800, 8, 10),
            ]),
        ],
    }
    ids = [p["member_id"] for p in dp.all_member_profiles(data)]
    assert ids == ["#A"]
    ids_all = [p["member_id"] for p in
               dp.all_member_profiles(data, in_clan_only=False)]
    assert set(ids_all) == {"#A", "#G"}


# --------------------------------------------------------------------------
# predict_lineup
# --------------------------------------------------------------------------

def test_predict_lineup_sums_expected(clan):
    pred = dp.predict_lineup(clan, ["#A", "#C"])
    assert pred["n_selected"] == 2
    assert pred["n_with_data"] == 2
    assert pred["n_unknown"] == 0
    # expected = 950 + 500
    assert pred["predicted_points"] == pytest.approx(1450.0)
    # optimistic = avg + avg = 950 + 750
    assert pred["predicted_points_optimistic"] == pytest.approx(1700.0)
    assert pred["predicted_completion"] is not None
    assert pred["risk_members"] == []             # both are non-risky


def test_predict_lineup_flags_risky_and_unknown(clan):
    clan["members"]["#X"] = _member("#X", "Xander")  # no history
    pred = dp.predict_lineup(clan, ["#A", "#B", "#X"])
    assert pred["n_unknown"] == 1                  # Xander has no data
    # Bob is risky, Xander is unknown -> both flagged
    assert set(pred["risk_members"]) == {"#B", "#X"}
    # Xander contributes nothing to the projection
    assert pred["predicted_points"] == pytest.approx(950.0 + 500 / 3)


def test_predict_empty_lineup(clan):
    pred = dp.predict_lineup(clan, [])
    assert pred["predicted_points"] == 0
    assert pred["predicted_completion"] is None
    assert pred["n_selected"] == 0


# --------------------------------------------------------------------------
# recommend_lineup
# --------------------------------------------------------------------------

def test_recommend_stops_at_target(clan):
    rec = dp.recommend_lineup(clan, target_points=900)
    # Alice alone (950) already clears 900
    assert rec["selected"] == ["#A"]
    assert rec["target_met"] is True
    assert rec["prediction"]["predicted_points"] == pytest.approx(950.0)


def test_recommend_fills_in_priority_order(clan):
    rec = dp.recommend_lineup(clan, target_points=5000)  # unreachable
    # all three with data, best-first
    assert rec["selected"] == ["#A", "#C", "#B"]
    assert rec["target_met"] is False
    assert rec["candidates_considered"] == 3


def test_recommend_respects_max_slots(clan):
    rec = dp.recommend_lineup(clan, max_slots=2)
    assert rec["selected"] == ["#A", "#C"]
    assert rec["target_met"] is None              # no target supplied


def test_recommend_skips_members_without_data():
    data = {
        "members": {
            "#A": _member("#A", "Alice"),
            "#X": _member("#X", "Xander"),         # never in a derby
        },
        "snapshots": [
            _derby_snap("s1", "2026-05-01", [_entry("#A", True, 900, 9, 10)]),
            _derby_snap("s2", "2026-05-08", [_entry("#A", True, 900, 9, 10)]),
        ],
    }
    rec = dp.recommend_lineup(data)
    assert rec["selected"] == ["#A"]              # Xander excluded (no data)


# --------------------------------------------------------------------------
# saved plans (persistence helpers)
# --------------------------------------------------------------------------

def test_add_and_list_plan(clan):
    plan = dp.add_derby_plan(clan, "Spring Derby", ["#A", "#C"],
                             target_points=1800, derby_date="2026-05-22",
                             notes="push hard")
    assert plan["name"] == "Spring Derby"
    assert plan["member_ids"] == ["#A", "#C"]
    assert plan["target_points"] == 1800
    assert plan["derby_date"] == "2026-05-22"
    assert "plan_id" in plan and "created_at" in plan
    assert len(dp.list_derby_plans(clan)) == 1


def test_add_plan_drops_unknown_and_duplicate_members(clan):
    plan = dp.add_derby_plan(clan, "P", ["#A", "#A", "#zzz", "#C"])
    assert plan["member_ids"] == ["#A", "#C"]      # dedup + drop unknown


def test_add_plan_requires_name(clan):
    with pytest.raises(ValueError):
        dp.add_derby_plan(clan, "   ", ["#A"])


def test_add_plan_rejects_negative_target(clan):
    with pytest.raises(ValueError):
        dp.add_derby_plan(clan, "P", ["#A"], target_points=-5)


def test_update_plan_fields(clan):
    plan = dp.add_derby_plan(clan, "P", ["#A"], target_points=1000)
    pid = plan["plan_id"]
    dp.update_derby_plan(clan, pid, name="Renamed",
                         member_ids=["#A", "#B"], notes="n")
    updated = dp.get_derby_plan(clan, pid)
    assert updated["name"] == "Renamed"
    assert updated["member_ids"] == ["#A", "#B"]
    assert updated["notes"] == "n"
    assert updated["target_points"] == 1000        # untouched


def test_update_plan_clears_target_with_none(clan):
    plan = dp.add_derby_plan(clan, "P", ["#A"], target_points=1000)
    pid = plan["plan_id"]
    # passing target_points=None explicitly clears it...
    dp.update_derby_plan(clan, pid, target_points=None)
    assert dp.get_derby_plan(clan, pid)["target_points"] is None


def test_update_plan_omitting_target_leaves_it(clan):
    plan = dp.add_derby_plan(clan, "P", ["#A"], target_points=1000)
    pid = plan["plan_id"]
    # ...but omitting it entirely must NOT clear it (Ellipsis sentinel)
    dp.update_derby_plan(clan, pid, notes="just a note")
    assert dp.get_derby_plan(clan, pid)["target_points"] == 1000


def test_update_missing_plan_raises(clan):
    with pytest.raises(ValueError):
        dp.update_derby_plan(clan, "nope", name="x")


def test_delete_plan(clan):
    plan = dp.add_derby_plan(clan, "P", ["#A"])
    dp.delete_derby_plan(clan, plan["plan_id"])
    assert dp.list_derby_plans(clan) == []
    with pytest.raises(ValueError):
        dp.delete_derby_plan(clan, plan["plan_id"])   # already gone


def test_list_plans_newest_first(clan):
    p1 = dp.add_derby_plan(clan, "First", ["#A"])
    p2 = dp.add_derby_plan(clan, "Second", ["#A"])
    # created_at uses second resolution; force a deterministic order
    p1["created_at"] = "2026-05-01T10:00:00"
    p2["created_at"] = "2026-05-02T10:00:00"
    names = [p["name"] for p in dp.list_derby_plans(clan)]
    assert names == ["Second", "First"]


def test_ensure_derby_plans_creates_key():
    data = {"members": {}}
    plans = dp.ensure_derby_plans(data)
    assert plans == []
    assert data["derby_plans"] is plans            # same list object
