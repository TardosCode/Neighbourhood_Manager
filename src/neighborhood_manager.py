"""
Neighborhood (clan) manager.

Each neighborhood is its own database, stored as a single JSON file in
`neighborhoods/<name>.json`. A neighborhood database contains:

{
    "clan_name": str,
    "clan_tag": str (optional, e.g. "#ABC123"),
    "notes": str (optional),
    "members": {
        "<member_id>": {
            "member_id": str (Hay Day tag, primary key, e.g. "#XYZ789"),
            "name": str (current display name; may include emojis/unicode),
            "name_history": [
                {"name": str, "changed_on": iso-date}, ...
            ],
            "in_clan": bool (currently in the neighborhood?),
            "joined_date": iso-date or null,
            "left_date": iso-date or null,
            "notes": str (optional)
        },
        ...
    },
    "snapshots": [
        {
            "snapshot_id": str (uuid),
            "date": iso-date,
            "type": "after_derby" | "quick",
            "derby_comment": str,
            "entries": [
                {
                    "member_id": str,
                    "level": int,
                    # only present for after_derby snapshots:
                    "derby_participated": bool,
                    "tasks_done": int,
                    "tasks_max": int,
                    "derby_points": int,
                    # always optional:
                    "member_comment": str,
                    "fate": "stay" | "warning" | "kick"
                },
                ...
            ]
        },
        ...
    ]
}

Members are identified by their Hay Day tag (member_id), so renames don't
break history. Snapshots are append-only conceptually but can be edited or
deleted — every statistic recomputes from the raw snapshots, nothing is
cached.

A separate `_active.json` file tracks which neighborhood is currently
selected, mirroring the profile manager.
"""

import json
import os
import re
import uuid
from datetime import date, datetime
from typing import Optional


SNAPSHOT_TYPE_AFTER_DERBY = "after_derby"
SNAPSHOT_TYPE_QUICK = "quick"
SNAPSHOT_TYPE_DONATIONS = "donations"

FATE_STAY = "stay"
FATE_WARNING = "warning"
FATE_KICK = "kick"

VALID_FATES = (FATE_STAY, FATE_WARNING, FATE_KICK)
VALID_SNAPSHOT_TYPES = (SNAPSHOT_TYPE_AFTER_DERBY, SNAPSHOT_TYPE_QUICK,
                        SNAPSHOT_TYPE_DONATIONS)

# Donation categories shown in the UI
DONATION_CATEGORIES = ("crops", "foods", "tools")

# Member roles. Role labels and colors live in theme.py;
# the canonical role IDs live here so the data layer can validate them.
ROLE_MEMBER = "member"
ROLE_ELDER = "elder"
ROLE_CO_LEADER = "co_leader"
ROLE_LEADER = "leader"
VALID_ROLES = (ROLE_MEMBER, ROLE_ELDER, ROLE_CO_LEADER, ROLE_LEADER)

MAX_CLAN_SIZE = 30


# ----- Activity-rule constants ----------------------------------------------
# Activity status returned by clan_stats.member_activity_status:
ACTIVITY_NEW_MEMBER = "new_member"          # less than 2 snapshots
ACTIVITY_INACTIVE = "inactive"              # 0 levels gained in window (red)
ACTIVITY_BELOW_TARGET = "below_target"      # gained some but below rule (yellow)
ACTIVITY_MEETING_TARGET = "meeting_target"  # met the rule (green)
ACTIVITY_NO_RULE = "no_rule"                # no rule covers this level

# Default activity rules: (level_min, level_max, min_levels_gained, time_window_days)
# 30 belongs to the lower bracket; 31 starts the next.
DEFAULT_ACTIVITY_RULES = [
    {"level_min": 1,   "level_max": 30,   "min_levels_gained": 5, "time_window_days": 7},
    {"level_min": 31,  "level_max": 60,   "min_levels_gained": 3, "time_window_days": 7},
    {"level_min": 61,  "level_max": 9999, "min_levels_gained": 1, "time_window_days": 7},
]


def _safe_filename(name: str) -> str:
    """Make a safe filename from a clan name (preserves unicode where possible)."""
    safe = re.sub(r"[^\w\s\-]", "_", name, flags=re.UNICODE).strip()
    safe = re.sub(r"\s+", "_", safe)
    return safe or "clan"


def _today_iso() -> str:
    return date.today().isoformat()


def default_neighborhood_data(clan_name: str = "", clan_tag: str = "",
                              notes: str = "") -> dict:
    return {
        "clan_name": clan_name,
        "clan_tag": clan_tag,
        "notes": notes,
        "activity_rules": [dict(r) for r in DEFAULT_ACTIVITY_RULES],
        "members": {},
        "snapshots": [],
        # Manual activity-score adjustments. Each entry:
        # {id, member_id, points: int, comment, created_at}
        "manual_activity_bonuses": [],
        # Saved derby plans (see derby_planner.py). Each entry:
        # {plan_id, name, created_at, derby_date, target_points,
        #  member_ids, notes}
        "derby_plans": [],
        # Persisted UI preferences (per-clan). Keys are arbitrary strings;
        # callers should namespace with the screen name.
        # e.g. "members.show_former" -> bool
        "ui_prefs": {},
    }


def default_member_data(member_id: str, name: str,
                        in_clan: bool = True,
                        notes: str = "",
                        role: str = ROLE_MEMBER) -> dict:
    today = _today_iso()
    return {
        "member_id": member_id,
        "name": name,
        "name_history": [{"name": name, "changed_on": today}],
        "in_clan": in_clan,
        "joined_date": today if in_clan else None,
        "left_date": None,
        "notes": notes,
        "role": role,
    }


def new_snapshot_id() -> str:
    return str(uuid.uuid4())


class NeighborhoodManager:
    """File-based store of all clans plus a pointer to the active one."""

    def __init__(self, neighborhoods_dir: str):
        self.dir = neighborhoods_dir
        os.makedirs(self.dir, exist_ok=True)
        self._active_path = os.path.join(self.dir, "_active.json")
        # in-memory cache: clan_name -> data dict
        # Reads and writes go through the cache; UI screens that re-render
        # frequently (Members, New Snapshot, Statistics) hit the cache instead
        # of disk. This noticeably reduces flicker when scrolling between tabs.
        self._cache = {}

    def invalidate_cache(self, clan_name: Optional[str] = None) -> None:
        """Drop one or all entries from the cache."""
        if clan_name is None:
            self._cache.clear()
        else:
            self._cache.pop(clan_name, None)

    # ---- listing / loading ------------------------------------------------

    def list_neighborhoods(self) -> list:
        names = []
        for f in os.listdir(self.dir):
            if f.endswith(".json") and not f.startswith("_"):
                names.append(f[:-5])
        return sorted(names)

    def _path_for(self, clan_name: str) -> str:
        return os.path.join(self.dir, _safe_filename(clan_name) + ".json")

    def neighborhood_exists(self, clan_name: str) -> bool:
        return os.path.exists(self._path_for(clan_name))

    def load(self, clan_name: str) -> dict:
        # serve from cache if available
        if clan_name in self._cache:
            return self._cache[clan_name]
        with open(self._path_for(clan_name), "r", encoding="utf-8") as f:
            data = json.load(f)
        # backward-compat: fill in fields older saves may lack
        if "activity_rules" not in data:
            data["activity_rules"] = [dict(r) for r in DEFAULT_ACTIVITY_RULES]
        if "manual_activity_bonuses" not in data:
            data["manual_activity_bonuses"] = []
        if "derby_plans" not in data:
            data["derby_plans"] = []
        if "ui_prefs" not in data:
            data["ui_prefs"] = {}
        # ensure every member has a 'role' field; old members default to Member
        for m in data.get("members", {}).values():
            if "role" not in m:
                m["role"] = ROLE_MEMBER
        self._cache[clan_name] = data
        return data

    def save(self, clan_name: str, data: dict) -> None:
        with open(self._path_for(clan_name), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._cache[clan_name] = data

    def create(self, clan_name: str, data: dict) -> None:
        if self.neighborhood_exists(clan_name):
            raise ValueError(f"Neighborhood '{clan_name}' already exists.")
        self.save(clan_name, data)

    def delete(self, clan_name: str) -> None:
        was_active = (self._raw_active_marker() == clan_name)
        path = self._path_for(clan_name)
        if os.path.exists(path):
            os.remove(path)
        self._cache.pop(clan_name, None)
        if was_active:
            self.set_active(None)

    def rename(self, old_name: str, new_name: str) -> None:
        if not self.neighborhood_exists(old_name):
            raise ValueError(f"Neighborhood '{old_name}' does not exist.")
        if old_name == new_name:
            return
        if self.neighborhood_exists(new_name):
            raise ValueError(f"Neighborhood '{new_name}' already exists.")
        data = self.load(old_name)
        data["clan_name"] = new_name  # keep stored display name in sync
        was_active = (self._raw_active_marker() == old_name)
        self.save(new_name, data)
        os.remove(self._path_for(old_name))
        self._cache.pop(old_name, None)
        if was_active:
            self.set_active(new_name)

    # ---- active neighborhood tracking ------------------------------------

    def get_active(self) -> Optional[str]:
        marker = self._raw_active_marker()
        if marker and self.neighborhood_exists(marker):
            return marker
        return None

    def _raw_active_marker(self) -> Optional[str]:
        if not os.path.exists(self._active_path):
            return None
        try:
            with open(self._active_path, "r", encoding="utf-8") as f:
                return json.load(f).get("active")
        except (json.JSONDecodeError, OSError):
            return None

    def set_active(self, clan_name: Optional[str]) -> None:
        with open(self._active_path, "w", encoding="utf-8") as f:
            json.dump({"active": clan_name}, f)


# ----- helpers that operate on a loaded neighborhood dict --------------------

def add_member(data: dict, member_id: str, name: str,
               in_clan: bool = True, notes: str = "",
               role: str = ROLE_MEMBER) -> None:
    """Add a member. Raises ValueError if member_id already exists."""
    if member_id in data["members"]:
        raise ValueError(f"Member with tag '{member_id}' already exists.")
    if in_clan:
        active_count = sum(1 for m in data["members"].values() if m["in_clan"])
        if active_count >= MAX_CLAN_SIZE:
            raise ValueError(
                f"Cannot mark new member as in-clan: already {MAX_CLAN_SIZE} active members."
            )
    if role not in VALID_ROLES:
        role = ROLE_MEMBER
    data["members"][member_id] = default_member_data(
        member_id=member_id, name=name, in_clan=in_clan, notes=notes,
        role=role
    )


def update_member(data: dict, member_id: str,
                  name: Optional[str] = None,
                  in_clan: Optional[bool] = None,
                  notes: Optional[str] = None,
                  role: Optional[str] = None) -> None:
    """Mutate a member's editable fields. Tracks name history and clan
    join/leave dates automatically."""
    if member_id not in data["members"]:
        raise ValueError(f"Member '{member_id}' not found.")
    m = data["members"][member_id]
    today = _today_iso()

    if name is not None and name != m["name"]:
        m["name"] = name
        m.setdefault("name_history", []).append({"name": name, "changed_on": today})

    if in_clan is not None and in_clan != m["in_clan"]:
        if in_clan:
            active_count = sum(1 for x in data["members"].values() if x["in_clan"])
            if active_count >= MAX_CLAN_SIZE:
                raise ValueError(
                    f"Cannot add to clan: already {MAX_CLAN_SIZE} active members."
                )
            m["in_clan"] = True
            if m.get("joined_date") is None:
                m["joined_date"] = today
            m["left_date"] = None
        else:
            m["in_clan"] = False
            m["left_date"] = today

    if notes is not None:
        m["notes"] = notes

    if role is not None and role in VALID_ROLES:
        m["role"] = role


def delete_member(data: dict, member_id: str) -> None:
    """Remove a member completely from the database AND from any snapshot
    entries that reference them. Use with care — irreversible."""
    if member_id not in data["members"]:
        raise ValueError(f"Member '{member_id}' not found.")
    del data["members"][member_id]
    for snap in data.get("snapshots", []):
        snap["entries"] = [e for e in snap.get("entries", [])
                           if e.get("member_id") != member_id]


def add_snapshot(data: dict, snapshot: dict) -> None:
    """Append a snapshot. Caller is responsible for filling in the dict."""
    if "snapshot_id" not in snapshot:
        snapshot["snapshot_id"] = new_snapshot_id()
    data.setdefault("snapshots", []).append(snapshot)
    # keep snapshots sorted by date asc; ties broken by insertion order
    data["snapshots"].sort(key=lambda s: (s.get("date", ""), s.get("snapshot_id", "")))


def update_snapshot(data: dict, snapshot_id: str, new_data: dict) -> None:
    for i, s in enumerate(data.get("snapshots", [])):
        if s.get("snapshot_id") == snapshot_id:
            new_data["snapshot_id"] = snapshot_id  # keep id stable
            data["snapshots"][i] = new_data
            data["snapshots"].sort(
                key=lambda s: (s.get("date", ""), s.get("snapshot_id", ""))
            )
            return
    raise ValueError(f"Snapshot '{snapshot_id}' not found.")


def delete_snapshot(data: dict, snapshot_id: str) -> None:
    snaps = data.get("snapshots", [])
    new = [s for s in snaps if s.get("snapshot_id") != snapshot_id]
    if len(new) == len(snaps):
        raise ValueError(f"Snapshot '{snapshot_id}' not found.")
    data["snapshots"] = new


def get_snapshot(data: dict, snapshot_id: str) -> Optional[dict]:
    for s in data.get("snapshots", []):
        if s.get("snapshot_id") == snapshot_id:
            return s
    return None


def in_clan_members_sorted_by_level(data: dict) -> list:
    """Return active members sorted by their most recent known level (desc)."""
    members = [m for m in data["members"].values() if m["in_clan"]]
    levels = latest_levels(data)
    members.sort(key=lambda m: (-(levels.get(m["member_id"], 0)), m["name"].lower()))
    return members


def latest_levels(data: dict) -> dict:
    """Return {member_id: latest_known_level} from any snapshot type.
    Members with no recorded level get nothing in the dict."""
    result = {}
    # walk snapshots in chronological order; later entries overwrite earlier
    for snap in sorted(data.get("snapshots", []),
                       key=lambda s: (s.get("date", ""), s.get("snapshot_id", ""))):
        for e in snap.get("entries", []):
            if "level" in e and e["level"] is not None:
                result[e["member_id"]] = e["level"]
    return result


def latest_snapshot_date_for_member(data: dict, member_id: str) -> Optional[str]:
    """Return the date of the most recent snapshot containing this member."""
    latest = None
    for snap in data.get("snapshots", []):
        for e in snap.get("entries", []):
            if e.get("member_id") == member_id:
                d = snap.get("date")
                if d and (latest is None or d > latest):
                    latest = d
                break
    return latest


def latest_fate_for_member(data: dict, member_id: str) -> Optional[str]:
    """Return the most recent fate marker recorded for a member."""
    latest_date = None
    latest_fate = None
    for snap in data.get("snapshots", []):
        for e in snap.get("entries", []):
            if e.get("member_id") == member_id and e.get("fate"):
                d = snap.get("date", "")
                if latest_date is None or d > latest_date:
                    latest_date = d
                    latest_fate = e["fate"]
    return latest_fate


# ----- activity rule validation ---------------------------------------------

def validate_activity_rules(rules: list) -> list:
    """Return a list of human-readable errors. Empty list means valid."""
    errors = []
    if not rules:
        errors.append("At least one activity rule is required.")
        return errors

    # field-level checks
    for i, r in enumerate(rules, start=1):
        try:
            lo = int(r["level_min"])
            hi = int(r["level_max"])
            mlg = int(r["min_levels_gained"])
            twd = int(r["time_window_days"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"Rule {i}: missing or non-integer fields.")
            continue

        if lo < 1:
            errors.append(f"Rule {i}: level_min must be >= 1 (got {lo}).")
        if hi < lo:
            errors.append(f"Rule {i}: level_max ({hi}) is below level_min ({lo}).")
        if mlg < 0:
            errors.append(f"Rule {i}: min_levels_gained must be >= 0 (got {mlg}).")
        if twd < 1:
            errors.append(f"Rule {i}: time_window_days must be >= 1 (got {twd}).")

    if errors:
        return errors  # don't continue range checks if individual rules are bad

    # sort by level_min and check for gaps and overlaps
    sorted_rules = sorted(rules, key=lambda r: r["level_min"])
    if sorted_rules[0]["level_min"] != 1:
        errors.append(
            f"First rule must start at level 1 (starts at {sorted_rules[0]['level_min']})."
        )
    for i in range(1, len(sorted_rules)):
        prev = sorted_rules[i - 1]
        cur = sorted_rules[i]
        if cur["level_min"] != prev["level_max"] + 1:
            if cur["level_min"] <= prev["level_max"]:
                errors.append(
                    f"Rules overlap: {prev['level_min']}-{prev['level_max']} "
                    f"and {cur['level_min']}-{cur['level_max']}."
                )
            else:
                errors.append(
                    f"Gap between rules: {prev['level_max']} and {cur['level_min']}."
                )
    return errors


def find_rule_for_level(rules: list, level: int) -> Optional[dict]:
    """Return the rule whose [level_min, level_max] contains the given level,
    or None if no rule matches."""
    for r in rules:
        if r["level_min"] <= level <= r["level_max"]:
            return r
    return None


# ========================================================================
# Manual activity-score bonuses
# ========================================================================
# Each bonus is a small dict:
#   {
#     "id":         "<uuid>",         (auto-generated)
#     "member_id":  "<member tag>",
#     "points":     <int, can be negative>,
#     "comment":    "<why>",
#     "created_at": "<iso datetime>"
#   }

def add_manual_activity_bonus(data: dict, member_id: str,
                              points: int, comment: str) -> dict:
    """Append a manual activity bonus to the clan. Returns the new entry."""
    if member_id not in data.get("members", {}):
        raise ValueError(f"Member '{member_id}' not found.")
    if not isinstance(points, int):
        raise ValueError("points must be an int")
    if not comment or not comment.strip():
        raise ValueError("A comment is required for manual bonuses.")
    entry = {
        "id": str(uuid.uuid4()),
        "member_id": member_id,
        "points": points,
        "comment": comment.strip(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    data.setdefault("manual_activity_bonuses", []).append(entry)
    return entry


def delete_manual_activity_bonus(data: dict, bonus_id: str) -> None:
    bonuses = data.get("manual_activity_bonuses", [])
    data["manual_activity_bonuses"] = [b for b in bonuses if b.get("id") != bonus_id]


def manual_activity_bonuses_for_member(data: dict, member_id: str) -> list:
    """All manual bonuses for one member, newest first."""
    bonuses = [b for b in data.get("manual_activity_bonuses", [])
               if b.get("member_id") == member_id]
    bonuses.sort(key=lambda b: b.get("created_at", ""), reverse=True)
    return bonuses


def manual_activity_total_for_member(data: dict, member_id: str) -> int:
    return sum(b.get("points", 0)
               for b in data.get("manual_activity_bonuses", [])
               if b.get("member_id") == member_id)


# ========================================================================
# UI preferences (per-clan)
# ========================================================================
# Small dictionary stored on the clan data so things like "show former
# members" toggle persist across tab switches and even across app restarts.
# Keys are conventionally namespaced by screen, e.g.
#   "members.show_former"
#   "activity.show_former"
#   "snapshots.search_query"   (if we want to remember it later)

def get_ui_pref(data: dict, key: str, default=None):
    return data.get("ui_prefs", {}).get(key, default)


def set_ui_pref(data: dict, key: str, value) -> None:
    """Mutate the clan data with a UI preference. Caller is responsible
    for persisting the data (NeighborhoodManager.save)."""
    data.setdefault("ui_prefs", {})[key] = value
