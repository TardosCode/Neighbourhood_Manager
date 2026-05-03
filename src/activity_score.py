"""
Activity score system.

Each in-clan member earns activity points based on a few different
metrics. For each metric, all in-clan members are ranked, and points are
awarded based on rank:

  Rank 1        → 5 points
  Rank 2-6      → 3 points
  Rank 7-15     → 2 points
  Rank 16+      → 1 point
  No data       → 0 points

The total score is the sum of points across all metrics, plus any
manual bonuses the leader has assigned.

Metrics (the "categories" of contribution):
  derby_completion  — average task completion % across derbies
  derby_part        — derby participation rate over recent derbies
  levels_gained     — levels gained over the last 30 days
  donations         — total donations (all categories) over recent weeks
  manual            — manual bonuses assigned by the leader

Scores are computed live from the latest data, never persisted. This
keeps the system intuitive: change any input data and the score updates
on next render.
"""

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from neighborhood_manager import (
    SNAPSHOT_TYPE_AFTER_DERBY, SNAPSHOT_TYPE_QUICK,
    SNAPSHOT_TYPE_DONATIONS,
    manual_activity_total_for_member,
    manual_activity_bonuses_for_member,
)
from clan_stats import (
    member_avg_task_completion, member_derby_participation_rate,
    member_donation_history,
    DONATION_CATEGORIES_LIST,
    _parse_iso,
)


# Categories the user sees. (key, human-readable label)
ACTIVITY_CATEGORIES = [
    ("derby_completion", "Derby task completion %"),
    ("derby_part",       "Derby participation"),
    ("levels_gained",    "Levels gained (30 days)"),
    ("donations",        "Donations (recent)"),
    ("manual",           "Manual bonuses"),
]


# ----- ranking → points mapping ---------------------------------------------

def points_for_rank(rank: int) -> int:
    """Return the activity points awarded for a 1-indexed rank.
    Rank 1 -> 5, 2-6 -> 3, 7-15 -> 2, 16+ -> 1.
    rank=None or 0 → 0 points (caller should not call us in that case)."""
    if rank is None or rank < 1:
        return 0
    if rank == 1:
        return 5
    if rank <= 6:
        return 3
    if rank <= 15:
        return 2
    return 1


# ----- per-member metric values --------------------------------------------

def _levels_gained_last_n_days(data: dict, member_id: str,
                               days: int = 30,
                               today: Optional[date] = None) -> Optional[int]:
    """How many levels did this member gain in the last N days?
    None means insufficient data (no snapshot inside the window)."""
    if today is None:
        today = date.today()
    cutoff = today - timedelta(days=days)

    # find earliest snapshot >= cutoff that has a level for this member,
    # and the latest snapshot overall that has a level for this member.
    earliest_in_window = None
    latest_overall = None
    for snap in sorted(data.get("snapshots", []),
                       key=lambda s: (s.get("date", ""),
                                       s.get("snapshot_id", ""))):
        d = _parse_iso(snap.get("date", ""))
        if d is None:
            continue
        for e in snap.get("entries", []):
            if e.get("member_id") != member_id:
                continue
            lvl = e.get("level")
            if lvl is None:
                continue
            if d >= cutoff and earliest_in_window is None:
                earliest_in_window = (d, lvl)
            latest_overall = (d, lvl)
            break
    if earliest_in_window is None or latest_overall is None:
        return None
    if earliest_in_window[0] == latest_overall[0]:
        return 0  # only one data point in window
    return max(0, latest_overall[1] - earliest_in_window[1])


def _total_donations_recent(data: dict, member_id: str,
                            last_n_weeks: int = 4) -> Optional[int]:
    """Total donations across all categories over the last N donation
    snapshots. Returns None if no donation snapshots exist for them."""
    history = member_donation_history(data, member_id)
    if not history:
        return None
    recent = history[-last_n_weeks:]
    total = 0
    for h in recent:
        e = h["entry"]
        for cat in DONATION_CATEGORIES_LIST:
            total += e.get(f"{cat}_donated", 0) or 0
    return total


def _metric_value(data: dict, member_id: str, key: str) -> Optional[float]:
    """Compute the raw metric value used for ranking.
    None means 'no data' which always awards 0 points."""
    if key == "derby_completion":
        return member_avg_task_completion(data, member_id)
    if key == "derby_part":
        return member_derby_participation_rate(data, member_id)
    if key == "levels_gained":
        return _levels_gained_last_n_days(data, member_id, days=30)
    if key == "donations":
        return _total_donations_recent(data, member_id, last_n_weeks=4)
    if key == "manual":
        # manual is special - the points are the manual total directly,
        # there's no ranking to do. Returning None here means we'll
        # compute manual differently in compute_scores().
        return None
    return None


# ----- compute scores for all in-clan members ------------------------------

def compute_scores(data: dict, include_former: bool = False) -> list:
    """Compute the full activity-score breakdown for all members.

    Returns a list of dicts, one per member:
      {
        "member_id": ...,
        "name": ...,
        "in_clan": bool,
        "role": str,
        "total": int,                # sum across categories
        "categories": {              # category key -> dict
          "derby_completion": {"value": float, "rank": int, "points": int},
          ...
          "manual": {"value": int, "rank": None, "points": int}
        }
      }

    The list is sorted by total score descending (highest first).
    """
    # Gather candidate members
    members = []
    for mid, m in data.get("members", {}).items():
        in_clan = bool(m.get("in_clan"))
        if not in_clan and not include_former:
            continue
        members.append((mid, m))

    # For each ranked metric, compute (member_id, raw value), then rank
    # the values and assign points. Members with None values get 0 points.
    breakdown = {mid: {"member_id": mid,
                       "name": m["name"],
                       "in_clan": bool(m.get("in_clan")),
                       "role": m.get("role", "member"),
                       "total": 0,
                       "categories": {}} for mid, m in members}

    for cat_key, _label in ACTIVITY_CATEGORIES:
        if cat_key == "manual":
            continue  # handled below

        # raw values
        values = {}
        for mid, _m in members:
            v = _metric_value(data, mid, cat_key)
            values[mid] = v

        # Rank only members who actually performed (non-None AND > 0).
        # Zero performance doesn't earn the consolation +1 point that a
        # rank-16+ player would otherwise pick up — if you donated 0,
        # gained 0 levels, or completed 0% of derby tasks, you contributed
        # nothing to that category and earn nothing.
        rankable = [(mid, v) for mid, v in values.items()
                    if v is not None and float(v) > 0]
        rankable.sort(key=lambda t: -float(t[1]))

        # Assign rank 1, 2, 3 ... ties get the same rank? Keep it simple:
        # use distinct ranks (deterministic order ensures fairness).
        ranks = {}
        for i, (mid, v) in enumerate(rankable, start=1):
            ranks[mid] = i

        for mid, _m in members:
            v = values[mid]
            # treat None and 0 alike: no rank, no points
            if v is None or float(v) <= 0:
                breakdown[mid]["categories"][cat_key] = {
                    "value": v,  # keep the raw value (0 vs None) for display
                    "rank": None,
                    "points": 0,
                }
            else:
                rank = ranks[mid]
                pts = points_for_rank(rank)
                breakdown[mid]["categories"][cat_key] = {
                    "value": v, "rank": rank, "points": pts,
                }
                breakdown[mid]["total"] += pts

    # manual bonuses: total per member, no ranking
    for mid, _m in members:
        manual_pts = manual_activity_total_for_member(data, mid)
        breakdown[mid]["categories"]["manual"] = {
            "value": manual_pts, "rank": None, "points": manual_pts,
        }
        breakdown[mid]["total"] += manual_pts

    rows = list(breakdown.values())
    rows.sort(key=lambda r: -r["total"])
    return rows


def get_member_score(data: dict, member_id: str) -> dict:
    """Compute the activity score for a single member.
    Equivalent to compute_scores() then filter, but keeps the API explicit."""
    rows = compute_scores(data, include_former=True)
    for r in rows:
        if r["member_id"] == member_id:
            return r
    return {"member_id": member_id, "total": 0, "categories": {}}
