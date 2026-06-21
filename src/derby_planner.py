"""
Derby Planner & Predictor.

A planning tool that turns a clan's recorded derby history into actionable
advice for the *next* derby. Everything in this module is pure: functions take
the loaded neighborhood data dict (see neighborhood_manager.py) and return plain
Python values. Nothing here touches disk or the GUI, so the whole module is
unit-testable without a display.

There are three things this module does:

1.  Build a per-member "derby profile" from the after-derby snapshots — how
    often they show up, how many points/tasks they average, how consistent
    they are, which way their performance is trending, and a single
    participation-adjusted ``expected_points`` figure used for predictions.

2.  Predict the outcome of a hand-picked lineup (sum of expected points,
    optimistic ceiling, expected task completion, and which picks are risky).

3.  Recommend a lineup: greedily pick the most dependable members to reach a
    points target (or just rank everyone by expected contribution).

It also owns the persistence of saved derby plans, stored under a new
``derby_plans`` key on the neighborhood data dict. Older saves that predate
this feature simply have no such key; every accessor uses ``setdefault`` so
they keep working untouched.

A saved plan looks like::

    {
        "plan_id":       "<uuid>",
        "name":          "Derby 2026-06-19",
        "created_at":    "<iso datetime>",
        "derby_date":    "<iso date or ''>",
        "target_points": int or None,
        "member_ids":    ["#TAG1", "#TAG2", ...],
        "notes":         str,
    }
"""

import uuid
from datetime import datetime
from typing import Optional

from clan_stats import member_derby_history


# In Hay Day the whole neighbourhood (max 30) can join a derby.
DERBY_MAX_SLOTS = 30

# How many derbies of history we need before we trust a profile enough to
# classify its risk as anything other than "unknown".
MIN_DERBIES_FOR_CONFIDENCE = 2

# Risk tiers for a member's dependability in the next derby.
RISK_RELIABLE = "reliable"        # shows up and performs consistently
RISK_INCONSISTENT = "inconsistent"  # shows up but performance swings a lot
RISK_RISKY = "risky"              # frequently sits derbies out
RISK_UNKNOWN = "unknown"         # not enough history to judge

# Thresholds used by classify_risk(). Tweaking these in one place keeps the
# semantics consistent between the logic layer and anything that explains them.
RELIABLE_MIN_PARTICIPATION = 0.8
RELIABLE_MIN_CONSISTENCY = 0.7
RISKY_MAX_PARTICIPATION = 0.5

RISK_LABELS = {
    RISK_RELIABLE: "Reliable",
    RISK_INCONSISTENT: "Inconsistent",
    RISK_RISKY: "Risky",
    RISK_UNKNOWN: "Unknown",
}


# ----- small numeric helpers ------------------------------------------------

def _mean(values: list) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _pstdev(values: list) -> Optional[float]:
    """Population standard deviation. None for fewer than two data points."""
    if len(values) < 2:
        return None
    m = sum(values) / len(values)
    var = sum((v - m) ** 2 for v in values) / len(values)
    return var ** 0.5


def _consistency(values: list) -> Optional[float]:
    """Map a series of point scores to a 0..1 consistency rating.

    Uses the coefficient of variation (stddev / mean): the smaller the
    spread relative to the average, the more consistent. Clamped to [0, 1]
    so a single wild derby can't push it negative. None when there isn't
    enough data or the mean is zero (no meaningful ratio)."""
    if len(values) < 2:
        return None
    m = _mean(values)
    if not m:  # mean is 0 or None -> can't form a ratio
        return None
    sd = _pstdev(values)
    if sd is None:
        return None
    cv = sd / abs(m)
    return max(0.0, min(1.0, 1.0 - cv))


def _trend(values: list) -> Optional[float]:
    """Recent-vs-older trend in points across participated derbies.

    Splits the chronological series in half and returns
    (mean of recent half) - (mean of older half). Positive means improving.
    None when there are fewer than two data points."""
    if len(values) < 2:
        return None
    mid = len(values) // 2
    older = values[:mid]
    recent = values[mid:]
    older_mean = _mean(older)
    recent_mean = _mean(recent)
    if older_mean is None or recent_mean is None:
        return None
    return recent_mean - older_mean


# ----- per-member derby profile ---------------------------------------------

def classify_risk(participation_rate: Optional[float],
                  consistency: Optional[float],
                  derbies_counted: int) -> str:
    """Bucket a member into a risk tier from their participation, consistency
    and how much history backs those numbers."""
    if (derbies_counted < MIN_DERBIES_FOR_CONFIDENCE
            or participation_rate is None):
        return RISK_UNKNOWN
    if participation_rate < RISKY_MAX_PARTICIPATION:
        return RISK_RISKY
    if (participation_rate >= RELIABLE_MIN_PARTICIPATION
            and consistency is not None
            and consistency >= RELIABLE_MIN_CONSISTENCY):
        return RISK_RELIABLE
    return RISK_INCONSISTENT


def member_derby_profile(data: dict, member_id: str,
                         last_n: Optional[int] = None) -> dict:
    """Build a dependability profile for one member from after-derby snapshots.

    ``last_n`` limits the analysis to the most recent N after-derby snapshots
    that contain this member (None = all of them).

    The returned dict always has every key below; values are None when there
    isn't enough data to compute them:

        member_id, name, in_clan, role
        derbies_counted      after-derby snapshots considered
        participated         how many of those they joined
        participation_rate   participated / derbies_counted (0..1) or None
        avg_points           mean points over participated derbies or None
        avg_tasks            mean tasks over participated derbies or None
        avg_completion       mean tasks_done/tasks_max (0..1) or None
        points_stddev        population stddev of participated points or None
        consistency          0..1 consistency rating or None
        trend                recent-minus-older points delta or None
        last_points          most recent participated points or None
        expected_points      avg_points * participation_rate or None
        risk                 one of the RISK_* constants
    """
    member = data.get("members", {}).get(member_id, {})
    profile = {
        "member_id": member_id,
        "name": member.get("name", member_id),
        "in_clan": bool(member.get("in_clan")),
        "role": member.get("role", "member"),
        "derbies_counted": 0,
        "participated": 0,
        "participation_rate": None,
        "avg_points": None,
        "avg_tasks": None,
        "avg_completion": None,
        "points_stddev": None,
        "consistency": None,
        "trend": None,
        "last_points": None,
        "expected_points": None,
        "risk": RISK_UNKNOWN,
    }

    history = member_derby_history(data, member_id)
    if last_n is not None:
        history = history[-last_n:]
    if not history:
        return profile

    profile["derbies_counted"] = len(history)

    points_series = []   # points for derbies they participated in, in order
    tasks_series = []
    completion_series = []
    for h in history:
        e = h["entry"]
        if not e.get("derby_participated"):
            continue
        profile["participated"] += 1
        pts = e.get("derby_points", 0) or 0
        points_series.append(pts)
        tasks_series.append(e.get("tasks_done", 0) or 0)
        tmax = e.get("tasks_max", 0)
        if tmax:
            completion_series.append((e.get("tasks_done", 0) or 0) / tmax)

    profile["participation_rate"] = (
        profile["participated"] / profile["derbies_counted"]
        if profile["derbies_counted"] else None
    )

    if points_series:
        profile["avg_points"] = _mean(points_series)
        profile["points_stddev"] = _pstdev(points_series)
        profile["consistency"] = _consistency(points_series)
        profile["trend"] = _trend(points_series)
        profile["last_points"] = points_series[-1]
    if tasks_series:
        profile["avg_tasks"] = _mean(tasks_series)
    if completion_series:
        profile["avg_completion"] = _mean(completion_series)

    if profile["avg_points"] is not None and profile["participation_rate"] is not None:
        profile["expected_points"] = (
            profile["avg_points"] * profile["participation_rate"]
        )

    profile["risk"] = classify_risk(
        profile["participation_rate"],
        profile["consistency"],
        profile["derbies_counted"],
    )
    return profile


def all_member_profiles(data: dict, last_n: Optional[int] = None,
                        in_clan_only: bool = True) -> list:
    """Profiles for every member, sorted by expected_points descending.

    Members with no expected_points (no derby history) sort to the bottom but
    are still included so the UI can show "no data yet" rows."""
    profiles = []
    for mid, m in data.get("members", {}).items():
        if in_clan_only and not m.get("in_clan"):
            continue
        profiles.append(member_derby_profile(data, mid, last_n=last_n))
    profiles.sort(
        key=lambda p: (p["expected_points"] is not None,
                       p["expected_points"] or 0.0,
                       p["avg_points"] or 0.0),
        reverse=True,
    )
    return profiles


# ----- prediction for a chosen lineup ---------------------------------------

def predict_lineup(data: dict, member_ids: list,
                   last_n: Optional[int] = None) -> dict:
    """Predict the outcome of a derby run by the given members.

    Returns::

        {
          "members":                 [profile, ...],   # in input order
          "predicted_points":        float,  # sum of expected_points
          "predicted_points_optimistic": float,  # sum of avg_points (all show)
          "predicted_completion":    float|None,  # mean of known avg_completion
          "n_selected":              int,
          "n_with_data":             int,
          "n_unknown":               int,    # selected members lacking history
          "risk_members":            [member_id, ...],  # risky or unknown picks
        }
    """
    profiles = [member_derby_profile(data, mid, last_n=last_n)
                for mid in member_ids]

    predicted = 0.0
    optimistic = 0.0
    completions = []
    n_with_data = 0
    n_unknown = 0
    risk_members = []

    for p in profiles:
        if p["expected_points"] is not None:
            predicted += p["expected_points"]
        if p["avg_points"] is not None:
            optimistic += p["avg_points"]
        if p["avg_completion"] is not None:
            completions.append(p["avg_completion"])
        if p["expected_points"] is not None:
            n_with_data += 1
        else:
            n_unknown += 1
        if p["risk"] in (RISK_RISKY, RISK_UNKNOWN):
            risk_members.append(p["member_id"])

    return {
        "members": profiles,
        "predicted_points": predicted,
        "predicted_points_optimistic": optimistic,
        "predicted_completion": _mean(completions) if completions else None,
        "n_selected": len(profiles),
        "n_with_data": n_with_data,
        "n_unknown": n_unknown,
        "risk_members": risk_members,
    }


# ----- lineup recommendation ------------------------------------------------

def recommend_lineup(data: dict, target_points: Optional[int] = None,
                     max_slots: int = DERBY_MAX_SLOTS,
                     last_n: Optional[int] = None,
                     in_clan_only: bool = True) -> dict:
    """Greedily build the most dependable lineup.

    Members are ranked by ``expected_points`` (then raw ``avg_points`` as a
    tiebreak). Only members with usable history (positive expected points) are
    auto-selected — you can't predict a contribution for someone with no derby
    record. Selection stops when either:

      * the projected ``predicted_points`` reaches ``target_points`` (if given), or
      * ``max_slots`` members have been picked, or
      * there are no more candidates with data.

    Returns::

        {
          "selected":               [member_id, ...],
          "prediction":             <predict_lineup result for selected>,
          "target_points":          target_points,
          "target_met":             bool|None,   # None when no target given
          "candidates_considered":  int,
        }
    """
    if max_slots < 0:
        max_slots = 0

    ranked = [p for p in all_member_profiles(data, last_n=last_n,
                                             in_clan_only=in_clan_only)
              if p["expected_points"] is not None and p["expected_points"] > 0]

    selected = []
    running = 0.0
    for p in ranked:
        if len(selected) >= max_slots:
            break
        if target_points is not None and running >= target_points:
            break
        selected.append(p["member_id"])
        running += p["expected_points"]

    prediction = predict_lineup(data, selected, last_n=last_n)
    target_met = (prediction["predicted_points"] >= target_points
                  if target_points is not None else None)

    return {
        "selected": selected,
        "prediction": prediction,
        "target_points": target_points,
        "target_met": target_met,
        "candidates_considered": len(ranked),
    }


# ============================================================================
# Saved derby plans (persisted under data["derby_plans"])
# ============================================================================

def ensure_derby_plans(data: dict) -> list:
    """Return the plans list, creating it on the data dict if absent."""
    return data.setdefault("derby_plans", [])


def new_plan_id() -> str:
    return str(uuid.uuid4())


def _validate_member_ids(data: dict, member_ids: list) -> list:
    """Keep only ids that exist in the clan, preserving order and dropping
    duplicates. Raises ValueError if the result would be empty for a
    non-empty input of all-unknown ids."""
    known = data.get("members", {})
    seen = set()
    out = []
    for mid in member_ids:
        if mid in known and mid not in seen:
            seen.add(mid)
            out.append(mid)
    return out


def add_derby_plan(data: dict, name: str, member_ids: list,
                   target_points: Optional[int] = None,
                   derby_date: str = "", notes: str = "") -> dict:
    """Create and append a derby plan. Returns the new plan dict."""
    if not name or not name.strip():
        raise ValueError("A plan name is required.")
    if target_points is not None:
        target_points = int(target_points)
        if target_points < 0:
            raise ValueError("target_points must be >= 0.")
    entry = {
        "plan_id": new_plan_id(),
        "name": name.strip(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "derby_date": derby_date or "",
        "target_points": target_points,
        "member_ids": _validate_member_ids(data, member_ids),
        "notes": notes or "",
    }
    ensure_derby_plans(data).append(entry)
    return entry


def update_derby_plan(data: dict, plan_id: str, *,
                      name: Optional[str] = None,
                      member_ids: Optional[list] = None,
                      target_points=...,
                      derby_date: Optional[str] = None,
                      notes: Optional[str] = None) -> dict:
    """Mutate an existing plan's fields. Only provided fields change.

    ``target_points`` uses an Ellipsis sentinel so that passing None can
    explicitly clear the target, while omitting it leaves the target alone.
    Returns the updated plan. Raises ValueError if the plan is not found."""
    plan = get_derby_plan(data, plan_id)
    if plan is None:
        raise ValueError(f"Derby plan '{plan_id}' not found.")
    if name is not None:
        if not name.strip():
            raise ValueError("A plan name is required.")
        plan["name"] = name.strip()
    if member_ids is not None:
        plan["member_ids"] = _validate_member_ids(data, member_ids)
    if target_points is not ...:
        if target_points is None:
            plan["target_points"] = None
        else:
            tp = int(target_points)
            if tp < 0:
                raise ValueError("target_points must be >= 0.")
            plan["target_points"] = tp
    if derby_date is not None:
        plan["derby_date"] = derby_date
    if notes is not None:
        plan["notes"] = notes
    return plan


def delete_derby_plan(data: dict, plan_id: str) -> None:
    plans = ensure_derby_plans(data)
    new = [p for p in plans if p.get("plan_id") != plan_id]
    if len(new) == len(plans):
        raise ValueError(f"Derby plan '{plan_id}' not found.")
    data["derby_plans"] = new


def get_derby_plan(data: dict, plan_id: str) -> Optional[dict]:
    for p in data.get("derby_plans", []):
        if p.get("plan_id") == plan_id:
            return p
    return None


def list_derby_plans(data: dict) -> list:
    """All saved plans, newest first by creation time."""
    plans = list(data.get("derby_plans", []))
    plans.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return plans
