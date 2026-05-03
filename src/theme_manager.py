"""
Theme manager.

Loads color overrides from settings/theme.json and applies them to the
THEME dict in theme.py at runtime. The user only edits 6 "primary" colors
(see SIMPLE_PALETTE_KEYS); secondary colors (like btn_green_hover) are
derived automatically as darker shades.

After every change, all open frames need to be redrawn for the new colors
to take effect. The HayDayHelperApp does this by re-running show_frame on
the current screen.
"""

import json
import os
from typing import Optional

import theme as theme_module


# ----- color helpers --------------------------------------------------------

def _hex_to_rgb(s: str):
    s = s.lstrip("#")
    if len(s) != 6:
        raise ValueError(f"bad hex: {s}")
    return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb) -> str:
    r, g, b = (max(0, min(255, int(v))) for v in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def darken(hex_color: str, factor: float = 0.78) -> str:
    """Return a darker shade. factor in (0, 1); 0.78 ≈ 22% darker."""
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex((r * factor, g * factor, b * factor))


def lighten(hex_color: str, factor: float = 1.18) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex((min(255, r * factor),
                         min(255, g * factor),
                         min(255, b * factor)))


def derive_secondary_colors(primary: dict) -> dict:
    """Given the 6 primary user-editable colors, fill in all the secondary
    colors (hover variants, text-on-primary etc) automatically."""
    out = {}
    out["bg_main"] = primary["bg_main"]
    out["bg_top"] = primary["bg_top"]
    out["bg_panel"] = lighten(primary["bg_main"], 1.05)
    out["bg_card"] = lighten(primary["bg_main"], 1.10)
    out["bg_dialog"] = primary["bg_main"]

    out["btn_green"] = primary["btn_green"]
    out["btn_green_hover"] = darken(primary["btn_green"])
    out["btn_red"] = primary["btn_red"]
    out["btn_red_hover"] = darken(primary["btn_red"])
    out["btn_blue"] = primary["btn_blue"]
    out["btn_blue_hover"] = darken(primary["btn_blue"])
    # grey buttons stay neutral - we don't want them tinted by primary changes
    out["btn_grey"] = "#9A9A9A"
    out["btn_grey_hover"] = "#7A7A7A"
    out["btn_disabled"] = "#BFBFBF"

    out["text_dark"] = primary["text_dark"]
    out["text_light"] = "#FFFFFF"
    out["text_muted"] = darken(primary["text_dark"], 1.6) if False else "#7A6A4A"
    out["text_warning"] = darken(primary["btn_red"])
    out["text_ok"] = darken(primary["btn_green"])

    # activity status - derived from semantic buttons
    out["act_new"] = "#7A7A7A"
    out["act_inactive"] = primary["btn_red"]
    out["act_below"] = "#E89B3B"  # amber - kept fixed so it's never confusable with primary
    out["act_meeting"] = primary["btn_green"]
    out["act_no_rule"] = "#9A9A9A"

    out["border"] = "#7A5A2A"
    out["border_dark"] = "#5A3A0A"

    return out


# ----- manager --------------------------------------------------------------

class ThemeManager:
    """Owns the path to settings/theme.json and applies overrides on demand."""

    def __init__(self, settings_path: str):
        self.settings_path = settings_path
        # snapshot of factory defaults for the 6 primary keys
        self._factory_primary = {
            k: theme_module.DEFAULTS[k] for k, _label in theme_module.SIMPLE_PALETTE_KEYS
        }
        # apply persisted overrides on construction
        self.apply_saved_or_defaults()

    # ---- I/O --------------------------------------------------------------
    def _load_overrides(self) -> Optional[dict]:
        if not os.path.exists(self.settings_path):
            return None
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def _save_overrides(self, primary: dict):
        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(primary, f, indent=2)
        except OSError as e:
            print(f"[theme] could not save overrides: {e}")

    # ---- public API -------------------------------------------------------
    def get_primary_colors(self) -> dict:
        """Return the user-visible 6 colors currently in effect."""
        return {k: theme_module.THEME[k] for k, _ in theme_module.SIMPLE_PALETTE_KEYS}

    def apply_primary_colors(self, primary: dict, persist: bool = True):
        """Update THEME with a new palette derived from these 6 colors,
        and optionally save the override file."""
        new_full = derive_secondary_colors(primary)
        for k, v in new_full.items():
            theme_module.THEME[k] = v
        if persist:
            self._save_overrides(primary)

    def reset_to_defaults(self):
        # restore factory THEME values
        for k, v in theme_module.DEFAULTS.items():
            theme_module.THEME[k] = v
        # remove the override file so future starts come up clean
        if os.path.exists(self.settings_path):
            try:
                os.remove(self.settings_path)
            except OSError:
                pass

    def apply_saved_or_defaults(self):
        """Run on app startup. Loads overrides if any, else does nothing
        (the THEME dict already holds the defaults from import time)."""
        overrides = self._load_overrides()
        if overrides:
            # only the 6 primary keys are stored; derive the rest
            primary = {}
            for k, _label in theme_module.SIMPLE_PALETTE_KEYS:
                if k in overrides:
                    primary[k] = overrides[k]
                else:
                    primary[k] = theme_module.DEFAULTS[k]
            self.apply_primary_colors(primary, persist=False)
