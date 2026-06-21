"""Tests for activity_score.py — ranking-based activity points."""

import pytest

import activity_score as asc
import neighborhood_manager as nm


# ----- points_for_rank ------------------------------------------------------

@pytest.mark.parametrize("rank,points", [
    (1, 5),
    (2, 3),
    (6, 3),
    (7, 2),
    (15, 2),
    (16, 1),
    (100, 1),
    (0, 0),
    (-1, 0),
    (None, 0),
])
def test_points_for_rank(rank, points):
    assert asc.points_for_rank(rank) == points


# ----- compute_scores -------------------------------------------------------
#
# With the sample clan (no manual bonuses, fixture dates months old so the
# 30-day "levels_gained" window is empty -> 0 points for everyone):
#
#   derby_completion:  A=0.9(1st,5)  B=0.6(2nd,3)  C=None(0)  E=None(0)
#   derby_part:        A=1.0(1st,5)  B=.667(2nd,3) C=.333(3rd,3) E=None(0)
#   levels_gained:     all 0 (window empty)
#   donations:         A=380(1st,5)  B=145(2nd,3)  C=17(3rd,3) E=None(0)
#   manual:            all 0
#
#   totals: A=15  B=9  C=6  E=0

def _by_id(rows):
    return {r["member_id"]: r for r in rows}


def test_compute_scores_totals_and_sort(sample_clan):
    rows = asc.compute_scores(sample_clan, include_former=False)
    # in-clan only -> A, B, C, E
    assert [r["member_id"] for r in rows] == ["#A", "#B", "#C", "#E"]
    by = _by_id(rows)
    # levels_gained window is empty for everyone -> 0 points each
    assert all(r["categories"]["levels_gained"]["points"] == 0 for r in rows)
    assert by["#A"]["total"] == 15
    assert by["#B"]["total"] == 9
    assert by["#C"]["total"] == 6
    assert by["#E"]["total"] == 0


def test_compute_scores_category_breakdown(sample_clan):
    by = _by_id(asc.compute_scores(sample_clan, include_former=False))
    a = by["#A"]["categories"]
    assert a["derby_completion"]["rank"] == 1
    assert a["derby_completion"]["points"] == 5
    assert a["derby_part"]["points"] == 5
    assert a["donations"]["points"] == 5

    c = by["#C"]["categories"]
    # Carol has no valid task-completion ratio -> value None, 0 points
    assert c["derby_completion"]["value"] is None
    assert c["derby_completion"]["rank"] is None
    assert c["derby_completion"]["points"] == 0
    # but she does rank in participation and donations
    assert c["derby_part"]["points"] == 3
    assert c["donations"]["points"] == 3


def test_compute_scores_zero_and_none_earn_nothing(sample_clan):
    by = _by_id(asc.compute_scores(sample_clan, include_former=False))
    e = by["#E"]["categories"]
    # Eve has no derby / donation data at all -> every category 0
    for key in ("derby_completion", "derby_part", "donations", "levels_gained"):
        assert e[key]["points"] == 0
    assert by["#E"]["total"] == 0


def test_compute_scores_manual_bonus_added_directly(sample_clan):
    nm.add_manual_activity_bonus(sample_clan, "#C", 10, "helpful")
    by = _by_id(asc.compute_scores(sample_clan, include_former=False))
    assert by["#C"]["categories"]["manual"]["points"] == 10
    # base total was 6 -> now 16
    assert by["#C"]["total"] == 16
    # which now beats Bob (9) -> Carol moves up in the sort
    rows = asc.compute_scores(sample_clan, include_former=False)
    order = [r["member_id"] for r in rows]
    assert order.index("#C") < order.index("#B")


def test_compute_scores_include_former(sample_clan):
    rows = asc.compute_scores(sample_clan, include_former=True)
    ids = [r["member_id"] for r in rows]
    assert "#D" in ids  # former member now included


def test_compute_scores_role_carried(sample_clan):
    by = _by_id(asc.compute_scores(sample_clan, include_former=False))
    assert by["#A"]["role"] == "leader"
    assert by["#B"]["role"] == "co_leader"


def test_compute_scores_empty_clan():
    d = nm.default_neighborhood_data("Empty")
    assert asc.compute_scores(d) == []


# ----- get_member_score -----------------------------------------------------

def test_get_member_score(sample_clan):
    # NOTE: get_member_score uses include_former=True, so Dave is in the
    # ranking pool. Dave beats Alice on derby_completion (~0.917 vs 0.9),
    # dropping Alice to rank 2 there (3 pts instead of 5):
    #   derby_completion 3 + derby_part 5 + donations 5 = 13
    r = asc.get_member_score(sample_clan, "#A")
    assert r["member_id"] == "#A"
    assert r["total"] == 13


def test_get_member_score_unknown(sample_clan):
    r = asc.get_member_score(sample_clan, "#nope")
    assert r["member_id"] == "#nope"
    assert r["total"] == 0
    assert r["categories"] == {}


def test_get_member_score_former(sample_clan):
    # get_member_score uses include_former=True internally
    r = asc.get_member_score(sample_clan, "#D")
    assert r["member_id"] == "#D"
