"""Visual theme constants - tweak here to change the whole app's look.

The THEME dict is the single source of truth. It can be customized at runtime
through theme_manager.py (which loads overrides from settings/theme.json).
Every screen reads colors lazily via THEME[key], so live updates take effect
the next time a screen rebuilds.
"""

# Hay Day inspired palette: warm bezel/sand background, green accents, red highlights
# activity status colors - reserved as kept fallback in THEME but the
# canonical, theme-INDEPENDENT versions are in ACTIVITY_STATUS_COLORS below.
# These act_* THEME entries exist so code that reads them keeps working,
# but new code should pull from ACTIVITY_STATUS_COLORS instead.
THEME = {
    # backgrounds
    "bg_main":       "#F4D9A4",   # warm sand (main play area)
    "bg_top":        "#A8E66B",   # bright Hay Day green (top bar)
    "bg_panel":      "#F8E4B8",   # lighter sand for inset panels
    "bg_card":       "#FFF1CC",   # almost-cream for inner cards
    "bg_dialog":     "#F4D9A4",

    # buttons
    "btn_green":     "#3FA63F",
    "btn_green_hover":"#2D8A2D",
    "btn_red":       "#D24545",
    "btn_red_hover": "#B23030",
    "btn_blue":      "#3F8BD2",
    "btn_blue_hover":"#2D6FAE",
    "btn_grey":      "#9A9A9A",
    "btn_grey_hover":"#7A7A7A",
    "btn_disabled":  "#BFBFBF",

    # text
    "text_dark":     "#2A2A2A",
    "text_light":    "#FFFFFF",
    "text_muted":    "#7A6A4A",
    "text_warning":  "#B23030",
    "text_ok":       "#2D8A2D",

    # activity status colors
    "act_new":       "#7A7A7A",   # grey
    "act_inactive":  "#D24545",   # red
    "act_below":     "#E89B3B",   # amber/yellow
    "act_meeting":   "#2D8A2D",   # green
    "act_no_rule":   "#9A9A9A",   # grey

    # borders / outlines
    "border":        "#7A5A2A",
    "border_dark":   "#5A3A0A",

    # font families - tkinter falls back to a sane default if a name is missing
    "font_title":    ("Arial Black", 22, "bold"),
    "font_heading":  ("Arial", 18, "bold"),
    "font_subheading":("Arial", 14, "bold"),
    "font_body":     ("Arial", 12),
    "font_body_bold":("Arial", 12, "bold"),
    "font_count":    ("Arial Black", 16, "bold"),
    "font_button":   ("Arial", 12, "bold"),
    "font_button_big":("Arial Black", 14, "bold"),
}


# Snapshot of the original palette - used by "Reset to defaults" in the
# theme editor. A shallow copy is fine: every value is an immutable str/tuple.
DEFAULTS = dict(THEME)


# ----- "simple" palette: the 6 colors the user can edit ---------------------
# Each entry: (THEME key, human label, derive_dark_variant?)
# Derived variants (e.g. *_hover) are computed automatically from these.
SIMPLE_PALETTE_KEYS = [
    ("bg_main",   "Background"),
    ("bg_top",    "Top bar"),
    ("btn_green", "Primary button"),
    ("btn_red",   "Danger button"),
    ("btn_blue",  "Secondary button"),
    ("text_dark", "Text color"),
]


# ----- fixed (theme-independent) activity status colors ---------------------
# These should ALWAYS be these specific shades regardless of any theme tweak,
# so the green/yellow/red semantic stays universally readable.
ACTIVITY_STATUS_COLORS = {
    "inactive": "#D24545",   # red
    "below":    "#E89B3B",   # amber/orange
    "meeting":  "#3FA63F",   # green
    "new":      "#9A9A9A",   # neutral grey
    "no_rule":  "#7A7A7A",   # darker grey
}


# ----- Member roles (theme-independent fixed shades) -----------------------
# Order matters: this is the displayed promotion ladder.
ROLE_MEMBER = "member"
ROLE_ELDER = "elder"
ROLE_CO_LEADER = "co_leader"
ROLE_LEADER = "leader"

ROLES_ORDER = [ROLE_MEMBER, ROLE_ELDER, ROLE_CO_LEADER, ROLE_LEADER]

ROLE_LABELS = {
    ROLE_MEMBER:    "Member",
    ROLE_ELDER:     "Elder",
    ROLE_CO_LEADER: "Co-Leader",
    ROLE_LEADER:    "Leader",
}

# Solid badge colors for the chip
ROLE_COLORS = {
    ROLE_MEMBER:    "#9A9A9A",   # grey
    ROLE_ELDER:     "#3FA63F",   # green (was blue, too close to Co-Leader)
    ROLE_CO_LEADER: "#9D5BD2",   # purple
    ROLE_LEADER:    "#E89B3B",   # gold/orange
}

# Soft tint for the row background. We compute a deeper-but-still-readable
# pastel of the corresponding role color so the row clearly carries the
# accent without overpowering the text.
ROLE_ROW_TINTS = {
    ROLE_MEMBER:    None,         # no tint - default alternating colors
    ROLE_ELDER:     "#CDEBC9",    # pastel green (matches the new chip color)
    ROLE_CO_LEADER: "#E0C6F4",    # stronger pastel purple
    ROLE_LEADER:    "#F7CF94",    # stronger pastel gold (clearly visible now)
}

