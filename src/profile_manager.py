"""
Profile manager.

Each profile stores:
- player_name (display name in the app)
- player_tag (Hay Day in-game tag, e.g. #ABC123)
- player_level (Hay Day level, integer)
- silo: { capacity, items: { nail, screw, wood_panel } }
- barn: { capacity, items: { bolt, plank, duct_tape } }
- daily_limit_used (int, manually reset)

Profiles are stored as individual JSON files inside the `profiles/` folder.
A meta file `_active.json` remembers which profile was last selected.
"""

import json
import os
import re
from typing import Optional

from game_logic import INITIAL_CAPACITY, SILO_ITEMS, BARN_ITEMS


def _safe_filename(name: str) -> str:
    """Convert a profile name into a safe filename (keeps it readable)."""
    # allow letters, digits, dash, underscore, space; replace others with _
    safe = re.sub(r"[^\w\s\-]", "_", name, flags=re.UNICODE).strip()
    safe = re.sub(r"\s+", "_", safe)
    return safe or "profile"


def default_profile_data(player_name: str = "", player_tag: str = "",
                         player_level: int = 1,
                         silo_capacity: int = INITIAL_CAPACITY,
                         barn_capacity: int = INITIAL_CAPACITY) -> dict:
    """Build a fresh profile dictionary."""
    return {
        "player_name": player_name,
        "player_tag": player_tag,
        "player_level": player_level,
        "silo": {
            "capacity": silo_capacity,
            "items": {item: 0 for item in SILO_ITEMS},
        },
        "barn": {
            "capacity": barn_capacity,
            "items": {item: 0 for item in BARN_ITEMS},
        },
        "daily_limit_used": 0,
    }


class ProfileManager:
    def __init__(self, profiles_dir: str):
        self.profiles_dir = profiles_dir
        os.makedirs(profiles_dir, exist_ok=True)
        self._active_meta_path = os.path.join(profiles_dir, "_active.json")

    # ---- listing / loading ------------------------------------------------

    def list_profiles(self) -> list:
        """Return a list of profile names (without .json extension), sorted."""
        names = []
        for fname in os.listdir(self.profiles_dir):
            if fname.endswith(".json") and not fname.startswith("_"):
                names.append(fname[:-5])
        return sorted(names)

    def _path_for(self, profile_name: str) -> str:
        return os.path.join(self.profiles_dir, _safe_filename(profile_name) + ".json")

    def profile_exists(self, profile_name: str) -> bool:
        return os.path.exists(self._path_for(profile_name))

    def load(self, profile_name: str) -> dict:
        with open(self._path_for(profile_name), "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, profile_name: str, data: dict) -> None:
        with open(self._path_for(profile_name), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def create(self, profile_name: str, data: dict) -> None:
        if self.profile_exists(profile_name):
            raise ValueError(f"Profile '{profile_name}' already exists.")
        self.save(profile_name, data)

    def delete(self, profile_name: str) -> None:
        # check active status before we remove the file - get_active_profile()
        # verifies the profile exists, so it returns None right after deletion
        was_active = (self._raw_active_marker() == profile_name)
        path = self._path_for(profile_name)
        if os.path.exists(path):
            os.remove(path)
        if was_active:
            self.set_active_profile(None)

    def _raw_active_marker(self) -> Optional[str]:
        """Read the active-profile marker without verifying the profile exists."""
        if not os.path.exists(self._active_meta_path):
            return None
        try:
            with open(self._active_meta_path, "r", encoding="utf-8") as f:
                return json.load(f).get("active")
        except (json.JSONDecodeError, OSError):
            return None

    def rename(self, old_name: str, new_name: str) -> None:
        if not self.profile_exists(old_name):
            raise ValueError(f"Profile '{old_name}' does not exist.")
        if old_name == new_name:
            return
        if self.profile_exists(new_name):
            raise ValueError(f"Profile '{new_name}' already exists.")
        data = self.load(old_name)
        # capture active status BEFORE removing the old file
        was_active = (self._raw_active_marker() == old_name)
        self.save(new_name, data)
        os.remove(self._path_for(old_name))
        if was_active:
            self.set_active_profile(new_name)

    # ---- active profile tracking -----------------------------------------

    def get_active_profile(self) -> Optional[str]:
        if not os.path.exists(self._active_meta_path):
            return None
        try:
            with open(self._active_meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            name = data.get("active")
            if name and self.profile_exists(name):
                return name
        except (json.JSONDecodeError, OSError):
            pass
        return None

    def set_active_profile(self, profile_name: Optional[str]) -> None:
        with open(self._active_meta_path, "w", encoding="utf-8") as f:
            json.dump({"active": profile_name}, f)
