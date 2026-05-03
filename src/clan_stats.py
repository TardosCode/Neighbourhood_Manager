"""
Pure functions that compute statistics from a neighborhood data dict.

All functions accept the loaded neighborhood JSON as their first argument and
return plain Python values - they don't touch disk or the GUI. The point is
that statistics are always derived from the raw snapshots; nothing is cached
inside the data file.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from neighborhood_manager import (
    SNAPSHOT_TYPE_AFTER_DERBY, SNAPSHOT_TYPE_QUICK,
    SNAPSHOT_TYPE_DONATIONS,
    ACTIVITY_NEW_MEMBER, ACTIVITY_INACTIVE, ACTIVITY_BELOW_TARGET,
    ACTIVITY_MEETING_TARGET, ACTIVITY_NO_RULE,
    find_rule_for_level,
)


# ---------- per-snapshot helpers --------------------------------------------

def snapshot_average_level(snapshot: dict) -> Optional[float]:
    levels = [e["level"] for e in snapshot.get("entries", [])
              if e.get("level") is not None]
    if not levels:
        return None
    return sum(levels) / len(levels)


def snapshot_min_level(snapshot: dict) -> Optional[int]:
    levels = [e["level"] for e in snapshot.get("entries", [])
              if e.get("level") is not None]
    return min(levels) if levels else None


def snapshot_max_level(snapshot: dict) -> Optional[int]:
    levels = [e["level"] for e in snapshot.get("entries", [])
              if e.get("level") is not None]
    return max(levels) if levels else None


# ---------- per-member aggregations -----------------------------------------

def member_history(data: dict, member_id: str) -> list:
    """Return all snapshot entries for one member, in chronological order.
    Each item in the result is a dict {snapshot, entry} so the caller has
    access to both the snapshot context (date, type) and the per-member data.
    """
    out = []
    for snap in sorted(data.get("snapshots", []),
                       key=lambda s: (s.get("date", ""), s.get("snapshot_id", ""))):
        for e in snap.get("entries", []):
            if e.get("member_id") == member_id:
                out.append({"snapshot": snap, "entry": e})
                break
    return out


def member_level_progression(data: dict, member_id: str) -> list:
    """[(date_iso, level), ...] sorted by date. Includes both snapshot types
    because we want as many data points as possible for the level chart."""
    points = []
    for h in member_history(data, member_id):
        lv = h["entry"].get("level")
        if lv is not None:
            points.append((h["snapshot"]["date"], lv))
    return points


def member_derby_history(data: dict, member_id: str) -> list:
    """Only after-derby snapshots, with derby fields. Used for participation/
    points/tasks statistics."""
    out = []
    for h in member_history(data, member_id):
        snap = h["snapshot"]
        if snap.get("type") != SNAPSHOT_TYPE_AFTER_DERBY:
            continue
        out.append(h)
    return out


def member_derby_participation_rate(data: dict, member_id: str,
                                    last_n: Optional[int] = None) -> Optional[float]:
    """Fraction of after-derby snapshots in which the member participated.
    Considers the last N snapshots if last_n is given. Returns None if there's
    nothing to base it on."""
    derbies = member_derby_history(data, member_id)
    if last_n is not None:
        derbies = derbies[-last_n:]
    if not derbies:
        return None
    participated = sum(1 for h in derbies if h["entry"].get("derby_participated"))
    return participated / len(derbies)


def member_avg_tasks(data: dict, member_id: str,
                     last_n: Optional[int] = None) -> Optional[float]:
    """Average number of tasks completed across after-derby snapshots where
    the member participated."""
    derbies = member_derby_history(data, member_id)
    if last_n is not None:
        derbies = derbies[-last_n:]
    relevant = [h["entry"] for h in derbies if h["entry"].get("derby_participated")]
    if not relevant:
        return None
    vals = [e.get("tasks_done", 0) for e in relevant]
    return sum(vals) / len(vals)


def member_avg_points(data: dict, member_id: str,
                      last_n: Optional[int] = None) -> Optional[float]:
    derbies = member_derby_history(data, member_id)
    if last_n is not None:
        derbies = derbies[-last_n:]
    relevant = [h["entry"] for h in derbies if h["entry"].get("derby_participated")]
    if not relevant:
        return None
    vals = [e.get("derby_points", 0) for e in relevant]
    return sum(vals) / len(vals)


def member_total_points(data: dict, member_id: str) -> int:
    """Sum of all derby points the member ever earned (only counts derbies
    they participated in - non-participated entries always have 0 points)."""
    total = 0
    for h in member_derby_history(data, member_id):
        if h["entry"].get("derby_participated"):
            total += h["entry"].get("derby_points", 0) or 0
    return total


def member_total_tasks(data: dict, member_id: str) -> int:
    """Sum of all tasks the member completed across derbies."""
    total = 0
    for h in member_derby_history(data, member_id):
        if h["entry"].get("derby_participated"):
            total += h["entry"].get("tasks_done", 0) or 0
    return total


def member_avg_task_completion(data: dict, member_id: str,
                                last_n: Optional[int] = None) -> Optional[float]:
    """Average of (tasks_done / tasks_max) across after-derby snapshots in
    which the member PARTICIPATED. Skipped derbies don't drag the ratio
    down. Returns a fraction in [0, 1+] (can exceed 1 if data is dirty),
    or None if no participation history."""
    derbies = member_derby_history(data, member_id)
    if last_n is not None:
        derbies = derbies[-last_n:]
    ratios = []
    for h in derbies:
        e = h["entry"]
        if not e.get("derby_participated"):
            continue
        tmax = e.get("tasks_max", 0)
        if not tmax:
            continue  # avoid div-by-zero on bad data
        tdone = e.get("tasks_done", 0) or 0
        ratios.append(tdone / tmax)
    if not ratios:
        return None
    return sum(ratios) / len(ratios)


def member_participation_count(data: dict, member_id: str,
                                last_n: Optional[int] = None) -> tuple:
    """Return (n_participated, n_eligible) for after-derby snapshots."""
    derbies = member_derby_history(data, member_id)
    if last_n is not None:
        derbies = derbies[-last_n:]
    eligible = len(derbies)
    participated = sum(1 for h in derbies if h["entry"].get("derby_participated"))
    return participated, eligible


def member_total_levels_gained(data: dict, member_id: str) -> Optional[int]:
    """Net level change from first recorded level to last."""
    prog = member_level_progression(data, member_id)
    if len(prog) < 2:
        return None
    return prog[-1][1] - prog[0][1]


def member_levels_gained_between(data: dict, member_id: str,
                                 since_date: str) -> Optional[int]:
    """Levels gained from the first snapshot >= since_date to the latest."""
    prog = [(d, lv) for d, lv in member_level_progression(data, member_id)
            if d >= since_date]
    if len(prog) < 2:
        return None
    return prog[-1][1] - prog[0][1]


# ---------- clan-wide aggregations ------------------------------------------

def clan_avg_level_over_time(data: dict) -> list:
    """[(date, type, avg_level), ...] for all snapshots, in order."""
    out = []
    for snap in data.get("snapshots", []):
        avg = snapshot_average_level(snap)
        if avg is not None:
            out.append((snap["date"], snap["type"], avg))
    return out


def clan_size_over_time(data: dict) -> list:
    """[(date, count_of_members_in_snapshot), ...] in order."""
    return [(snap["date"], len(snap.get("entries", [])))
            for snap in data.get("snapshots", [])]


def clan_top_n_by_task_completion(data: dict, n: int = 5,
                                   last_n_derbies: Optional[int] = None,
                                   include_former: bool = True) -> list:
    """Members ranked by average task-completion percentage.

    Ratio = tasks_done / tasks_max, only counted for derbies where the
    member participated. Skipped derbies do NOT lower the score.

    last_n_derbies = None means "all derbies, all-time" (the default in this
    app per user request - the % never resets).

    Returns [(member_id, name, avg_completion_ratio, in_clan), ...].
    """
    after_derbies = [s for s in data.get("snapshots", [])
                     if s.get("type") == SNAPSHOT_TYPE_AFTER_DERBY]
    after_derbies = sorted(after_derbies,
                           key=lambda s: (s.get("date", ""), s.get("snapshot_id", "")))
    if last_n_derbies is not None:
        after_derbies = after_derbies[-last_n_derbies:]

    member_to_ratios = defaultdict(list)
    for snap in after_derbies:
        for e in snap.get("entries", []):
            if not e.get("derby_participated"):
                continue
            tmax = e.get("tasks_max", 0)
            if not tmax:
                continue
            tdone = e.get("tasks_done", 0) or 0
            member_to_ratios[e["member_id"]].append(tdone / tmax)

    rows = []
    for mid, ratios in member_to_ratios.items():
        if not ratios:
            continue
        member = data["members"].get(mid)
        if member is None:
            continue
        in_clan = bool(member.get("in_clan"))
        if not in_clan and not include_former:
            continue
        rows.append((mid, member["name"], sum(ratios) / len(ratios), in_clan))
    rows.sort(key=lambda r: -r[2])
    return rows[:n]


# Kept as alias for callers expecting the old name; same task-completion logic.
clan_top_n_by_recent_points = clan_top_n_by_task_completion


def clan_top_n_by_total_points(data: dict, n: int = 5,
                                include_former: bool = True) -> list:
    """All-time leaderboard by SUM of derby points. Useful as a curiosity
    list; the user explicitly wants this kept around."""
    rows = []
    for mid, member in data["members"].items():
        in_clan = bool(member.get("in_clan"))
        if not in_clan and not include_former:
            continue
        total_pts = member_total_points(data, mid)
        total_tasks = member_total_tasks(data, mid)
        if total_pts == 0 and total_tasks == 0:
            continue
        rows.append((mid, member["name"], total_pts, total_tasks, in_clan))
    rows.sort(key=lambda r: -r[2])
    return rows[:n]


def clan_bottom_n_by_recent_participation(data: dict, n: int = 5,
                                          last_n_derbies: int = 5,
                                          include_former: bool = True) -> list:
    """Members with the lowest derby participation rate over the recent N
    after-derby snapshots. Only considers members who appear in at least one
    of those snapshots. Returns [(member_id, name, rate, in_clan), ...]."""
    member_to_part = defaultdict(list)
    after_derbies = [s for s in data.get("snapshots", [])
                     if s.get("type") == SNAPSHOT_TYPE_AFTER_DERBY]
    after_derbies = sorted(after_derbies,
                           key=lambda s: (s.get("date", ""), s.get("snapshot_id", "")))
    recent = after_derbies[-last_n_derbies:]
    for snap in recent:
        for e in snap.get("entries", []):
            member_to_part[e["member_id"]].append(
                bool(e.get("derby_participated"))
            )
    rows = []
    for mid, parts in member_to_part.items():
        if not parts:
            continue
        member = data["members"].get(mid)
        if member is None:
            continue
        in_clan = bool(member.get("in_clan"))
        if not in_clan and not include_former:
            continue
        rows.append((mid, member["name"], sum(parts) / len(parts), in_clan))
    rows.sort(key=lambda r: r[2])
    return rows[:n]


def members_with_kick_warning_flag(data: dict,
                                    only_in_clan: bool = True) -> list:
    """Members whose most recent fate marker is 'warning' or 'kick'.
    By default only in-clan members are returned (former kicked members
    are noise once they've actually been kicked).
    Returns [(member_id, name, fate), ...]."""
    from neighborhood_manager import latest_fate_for_member
    out = []
    for mid, m in data["members"].items():
        if only_in_clan and not m.get("in_clan"):
            continue
        fate = latest_fate_for_member(data, mid)
        if fate in ("warning", "kick"):
            out.append((mid, m["name"], fate))
    return out


# ============================================================================
# Activity status (level progression vs. activity rules)
# ============================================================================

def _parse_iso(date_str: str) -> Optional[date]:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def member_activity_status(data: dict, member_id: str,
                           today: Optional[date] = None) -> dict:
    """Compute the activity status of one member based on the clan's rules
    and their level progression.

    Returns a dict with:
        status:           one of ACTIVITY_* constants
        rule:             the matching rule dict (or None)
        current_level:    most recent recorded level (or None)
        baseline_level:   the level at the start of the time window (or None)
        baseline_date:    iso date of the baseline (or None)
        levels_gained:    int (or None if not enough data)
        target:           int from rule.min_levels_gained (or None)
        days_covered:     how many days the actual baseline-to-now range covers
                          (only meaningful when status != NEW_MEMBER)
    """
    if today is None:
        today = date.today()

    rules = data.get("activity_rules", [])
    progression = member_level_progression(data, member_id)

    result = {
        "status": ACTIVITY_NEW_MEMBER,
        "rule": None,
        "current_level": None,
        "baseline_level": None,
        "baseline_date": None,
        "levels_gained": None,
        "target": None,
        "days_covered": None,
    }

    if len(progression) < 2:
        # New member: only one (or zero) data points so far.
        if progression:
            result["current_level"] = progression[-1][1]
        return result

    # latest data point
    latest_date_str, current_level = progression[-1]
    result["current_level"] = current_level

    # find rule for current level
    rule = find_rule_for_level(rules, current_level)
    if rule is None:
        result["status"] = ACTIVITY_NO_RULE
        return result
    result["rule"] = rule
    result["target"] = rule["min_levels_gained"]

    window_days = rule["time_window_days"]
    latest_date = _parse_iso(latest_date_str) or today
    cutoff = latest_date - timedelta(days=window_days)

    # baseline: the latest snapshot whose date is <= cutoff
    # (i.e. "the level the member had window_days ago")
    baseline_date = None
    baseline_level = None
    for d_str, lv in progression:
        d = _parse_iso(d_str)
        if d is None:
            continue
        if d <= cutoff:
            baseline_date = d_str
            baseline_level = lv
        else:
            break

    if baseline_level is None:
        # member's earliest snapshot is more recent than the cutoff -
        # they don't have a full window of data yet. Fall back to their
        # earliest data point so they still get a reading.
        earliest_date_str, earliest_level = progression[0]
        # if even the earliest data point is the same as the latest,
        # we can't compute a delta - treat as new
        if earliest_date_str == latest_date_str:
            return result  # still NEW_MEMBER
        baseline_date = earliest_date_str
        baseline_level = earliest_level

    result["baseline_level"] = baseline_level
    result["baseline_date"] = baseline_date

    levels_gained = current_level - baseline_level
    result["levels_gained"] = levels_gained

    # days covered (for display/transparency)
    bd = _parse_iso(baseline_date)
    if bd:
        result["days_covered"] = (latest_date - bd).days

    # decide status
    target = rule["min_levels_gained"]
    if levels_gained >= target:
        # Met or exceeded the target - always "On track" regardless of how
        # much data we have. Over-performance is rewarded immediately.
        result["status"] = ACTIVITY_MEETING_TARGET
    else:
        # Did not (yet) meet the target. Don't penalize someone who hasn't
        # had enough time to prove themselves: if their oldest data point
        # is less than 7 days old, treat them as New player.
        days_covered = result.get("days_covered") or 0
        if days_covered < 7:
            result["status"] = ACTIVITY_NEW_MEMBER
        elif levels_gained == 0:
            result["status"] = ACTIVITY_INACTIVE
        else:
            result["status"] = ACTIVITY_BELOW_TARGET

    return result


def members_grouped_by_activity_status(data: dict,
                                       today: Optional[date] = None) -> dict:
    """Group all in-clan members by their activity status.
    Returns {status_constant: [(member_id, member_dict, status_info_dict), ...]}.
    """
    out = defaultdict(list)
    for mid, m in data.get("members", {}).items():
        if not m.get("in_clan"):
            continue
        info = member_activity_status(data, mid, today=today)
        out[info["status"]].append((mid, m, info))
    return dict(out)


# ========================================================================
# Donations statistics
# ========================================================================
# Donations snapshots have entries shaped like:
#   {
#     "member_id": ...,
#     "crops_donated": int, "crops_requested": int,
#     "foods_donated": int, "foods_requested": int,
#     "tools_donated": int, "tools_requested": int
#   }
# We aggregate them per member or clan-wide.

DONATION_CATEGORIES_LIST = ("crops", "foods", "tools")


def member_donation_history(data: dict, member_id: str) -> list:
    """All donation entries for a member, oldest first."""
    out = []
    for snap in data.get("snapshots", []):
        if snap.get("type") != SNAPSHOT_TYPE_DONATIONS:
            continue
        for e in snap.get("entries", []):
            if e.get("member_id") == member_id:
                out.append({"date": snap.get("date", ""),
                            "snapshot_id": snap.get("snapshot_id", ""),
                            "entry": e})
                break
    out.sort(key=lambda h: (h["date"], h["snapshot_id"]))
    return out


def member_donations_avg(data: dict, member_id: str,
                         last_n_weeks: Optional[int] = None) -> dict:
    """Per-category weekly average for a member.

    Returns {"crops_donated": float, "crops_requested": float,
             "foods_donated": float, ..., "tools_requested": float,
             "weeks_counted": int}.
    """
    history = member_donation_history(data, member_id)
    if last_n_weeks is not None:
        history = history[-last_n_weeks:]
    n = len(history)
    out = {f"{cat}_donated": 0.0 for cat in DONATION_CATEGORIES_LIST}
    out.update({f"{cat}_requested": 0.0 for cat in DONATION_CATEGORIES_LIST})
    out["weeks_counted"] = n
    if n == 0:
        return out
    for cat in DONATION_CATEGORIES_LIST:
        out[f"{cat}_donated"] = sum(
            h["entry"].get(f"{cat}_donated", 0) or 0 for h in history) / n
        out[f"{cat}_requested"] = sum(
            h["entry"].get(f"{cat}_requested", 0) or 0 for h in history) / n
    return out


def member_donations_total(data: dict, member_id: str) -> dict:
    """All-time total donations and requests per category for a member.

    Returns {"crops_donated": int, "crops_requested": int, ..., "all_donated": int,
             "all_requested": int}.
    """
    history = member_donation_history(data, member_id)
    out = {f"{cat}_donated": 0 for cat in DONATION_CATEGORIES_LIST}
    out.update({f"{cat}_requested": 0 for cat in DONATION_CATEGORIES_LIST})
    out["all_donated"] = 0
    out["all_requested"] = 0
    for h in history:
        e = h["entry"]
        for cat in DONATION_CATEGORIES_LIST:
            out[f"{cat}_donated"] += e.get(f"{cat}_donated", 0) or 0
            out[f"{cat}_requested"] += e.get(f"{cat}_requested", 0) or 0
            out["all_donated"] += e.get(f"{cat}_donated", 0) or 0
            out["all_requested"] += e.get(f"{cat}_requested", 0) or 0
    return out


def clan_total_donations(data: dict) -> dict:
    """Aggregate donations across the whole clan, all snapshots."""
    out = {f"{cat}_donated": 0 for cat in DONATION_CATEGORIES_LIST}
    out.update({f"{cat}_requested": 0 for cat in DONATION_CATEGORIES_LIST})
    out["all_donated"] = 0
    out["all_requested"] = 0
    out["snapshots_counted"] = 0
    for snap in data.get("snapshots", []):
        if snap.get("type") != SNAPSHOT_TYPE_DONATIONS:
            continue
        out["snapshots_counted"] += 1
        for e in snap.get("entries", []):
            for cat in DONATION_CATEGORIES_LIST:
                out[f"{cat}_donated"] += e.get(f"{cat}_donated", 0) or 0
                out[f"{cat}_requested"] += e.get(f"{cat}_requested", 0) or 0
                out["all_donated"] += e.get(f"{cat}_donated", 0) or 0
                out["all_requested"] += e.get(f"{cat}_requested", 0) or 0
    return out


def clan_donations_per_snapshot(data: dict) -> list:
    """Per-snapshot total donations for a trend view.
    Returns [(date, all_donated, all_requested), ...] oldest first."""
    out = []
    for snap in sorted(data.get("snapshots", []),
                       key=lambda s: (s.get("date", ""),
                                       s.get("snapshot_id", ""))):
        if snap.get("type") != SNAPSHOT_TYPE_DONATIONS:
            continue
        d = 0
        r = 0
        for e in snap.get("entries", []):
            for cat in DONATION_CATEGORIES_LIST:
                d += e.get(f"{cat}_donated", 0) or 0
                r += e.get(f"{cat}_requested", 0) or 0
        out.append((snap.get("date", ""), d, r))
    return out


def clan_top_n_by_donations(data: dict, n: int = 5,
                            last_n_weeks: Optional[int] = None,
                            include_former: bool = False) -> list:
    """Members ranked by total donations across all categories.
    Returns [(member_id, name, total_donated, total_requested, in_clan), ...].
    """
    rows = []
    for mid, member in data["members"].items():
        in_clan = bool(member.get("in_clan"))
        if not in_clan and not include_former:
            continue
        history = member_donation_history(data, mid)
        if last_n_weeks is not None:
            history = history[-last_n_weeks:]
        total_d = 0
        total_r = 0
        for h in history:
            e = h["entry"]
            for cat in DONATION_CATEGORIES_LIST:
                total_d += e.get(f"{cat}_donated", 0) or 0
                total_r += e.get(f"{cat}_requested", 0) or 0
        if total_d == 0 and total_r == 0:
            continue
        rows.append((mid, member["name"], total_d, total_r, in_clan))
    rows.sort(key=lambda r: -r[2])
    return rows[:n]


def clan_top_n_by_requests(data: dict, n: int = 5,
                           last_n_weeks: Optional[int] = None,
                           include_former: bool = False) -> list:
    """Members ranked by total requests across all categories.
    Returns [(member_id, name, total_requested, total_donated, in_clan), ...].
    """
    rows = []
    for mid, member in data["members"].items():
        in_clan = bool(member.get("in_clan"))
        if not in_clan and not include_former:
            continue
        history = member_donation_history(data, mid)
        if last_n_weeks is not None:
            history = history[-last_n_weeks:]
        total_d = 0
        total_r = 0
        for h in history:
            e = h["entry"]
            for cat in DONATION_CATEGORIES_LIST:
                total_d += e.get(f"{cat}_donated", 0) or 0
                total_r += e.get(f"{cat}_requested", 0) or 0
        if total_d == 0 and total_r == 0:
            continue
        rows.append((mid, member["name"], total_r, total_d, in_clan))
    rows.sort(key=lambda r: -r[2])
    return rows[:n]
