"""
Expansion Helper screen.

Layout (mirrors the user's mockup):

    [<-- back]   Expansion - Helper           [profile button]
    [reset all]
                 SILO        Daily Limit       BARN
                 [img]       [ 46 / 89 ]       [img]
                 750 -> 775     [+1]           725 -> 750
                                [-1]
                 [n] [s] [w]                   [b] [p] [d]
                 13/29 20/29 37/29             11/28 0/28 25/28
                 +1  +1  +1   [^upgrade]   [^upgrade]  +1  +1  +1
                 -1  -1  -1                              -1  -1  -1
"""

import tkinter as tk
from tkinter import messagebox

from theme import THEME
from widgets import RoundedButton, ImageCache
from game_logic import (
    SILO_ITEMS, BARN_ITEMS, ITEM_DISPLAY_NAMES,
    get_required_items, get_next_capacity,
    can_upgrade, DAILY_LIMIT_MAX, BARN_MAX_CAPACITY,
)


class ExpansionHelperFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=THEME["bg_main"])
        self.app = app
        self.pm = app.profile_manager
        self.images = ImageCache(app.assets_dir)

        # current profile snapshot - we mutate this and save on every change
        self.profile_name = self.pm.get_active_profile()
        if self.profile_name is None:
            messagebox.showerror("No profile",
                                 "No active profile. Returning to profile screen.")
            self.app.show_frame("ProfileScreen", first_run=True)
            return
        self.data = self.pm.load(self.profile_name)

        self._build_top_bar()
        self._build_main_layout()

        # keep references to widgets we need to update
        # (built inside _build_main_layout)

        # initial render of all dynamic values
        self._refresh_all()

    # =================================================================
    # top bar
    # =================================================================
    def _build_top_bar(self):
        top = tk.Frame(self, bg=THEME["bg_top"], height=60)
        top.pack(side="top", fill="x")
        top.pack_propagate(False)

        # back button (left)
        RoundedButton(top, text="← Back",
                      command=lambda: self.app.show_frame("MainMenu"),
                      width=100, height=40,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="left", padx=15, pady=10)

        # title (center)
        tk.Label(top, text="Expansion - Helper",
                 font=THEME["font_title"],
                 bg=THEME["bg_top"], fg=THEME["text_dark"]).pack(side="left",
                                                                  expand=True)

        # profile button (right)
        RoundedButton(top, text="👤 Profile",
                      command=lambda: self.app.show_frame(
                          "ProfileScreen", return_to="ExpansionHelper"),
                      width=130, height=40,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="right", padx=15, pady=10)

        # show active profile name + level/tag in a thin info line
        sub = tk.Frame(self, bg=THEME["bg_panel"], height=28)
        sub.pack(side="top", fill="x")
        sub.pack_propagate(False)

        info_bits = [self.profile_name]
        if self.data.get("player_name"):
            info_bits.append(self.data["player_name"])
        if self.data.get("player_tag"):
            info_bits.append(self.data["player_tag"])
        if self.data.get("player_level"):
            info_bits.append(f"Lv {self.data['player_level']}")
        info_text = "  •  ".join(info_bits)

        tk.Label(sub, text=info_text, font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"]).pack(side="left",
                                                                    padx=20)

        # reset all button (right of sub-bar)
        RoundedButton(sub, text="Reset items + daily",
                      command=self._reset_all,
                      width=180, height=24,
                      bg_color=THEME["btn_red"],
                      hover_color=THEME["btn_red_hover"],
                      font=("Arial", 10, "bold"), radius=8
                      ).pack(side="right", padx=15, pady=2)

    # =================================================================
    # main layout: 3 columns (silo | center | barn)
    # =================================================================
    def _build_main_layout(self):
        body = tk.Frame(self, bg=THEME["bg_main"])
        body.pack(fill="both", expand=True, padx=15, pady=15)

        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, weight=2)
        body.grid_rowconfigure(0, weight=1)

        # column 0: SILO
        silo_frame = self._build_building_panel(body, "silo", "Silo", SILO_ITEMS)
        silo_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        # column 1: CENTER (daily limit)
        center_frame = self._build_center_panel(body)
        center_frame.grid(row=0, column=1, sticky="nsew", padx=8)

        # column 2: BARN
        barn_frame = self._build_building_panel(body, "barn", "Barn", BARN_ITEMS)
        barn_frame.grid(row=0, column=2, sticky="nsew", padx=(8, 0))

    # ---- building panel (silo/barn) -----------------------------------
    def _build_building_panel(self, parent, building_key: str, label: str, item_keys: list):
        frame = tk.Frame(parent, bg=THEME["bg_panel"], bd=2, relief="ridge")

        # label
        tk.Label(frame, text=label, font=THEME["font_heading"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]).pack(pady=(6, 2))

        # building image
        img_holder = tk.Label(frame, bg=THEME["bg_panel"])
        img_holder.pack(pady=2)
        # use a slightly smaller building image so the upgrade button stays visible
        # at the default window size; the layout still scales when resized
        building_photo = self.images.get(building_key, max_size=130)
        img_holder.config(image=building_photo)
        img_holder.image = building_photo  # anchor reference

        # capacity progression label - "750 -> 775"
        cap_label = tk.Label(frame, text="", font=THEME["font_subheading"],
                             bg=THEME["bg_panel"], fg=THEME["text_dark"])
        cap_label.pack(pady=(4, 6))

        # items row
        items_row = tk.Frame(frame, bg=THEME["bg_panel"])
        items_row.pack(pady=4)

        item_widgets = {}  # item_key -> dict with refs to labels/buttons
        for i, item_key in enumerate(item_keys):
            cell = tk.Frame(items_row, bg=THEME["bg_card"], bd=1, relief="solid",
                            padx=8, pady=8)
            cell.grid(row=0, column=i, padx=4)

            # icon
            photo = self.images.get(item_key, max_size=64)
            icon = tk.Label(cell, image=photo, bg=THEME["bg_card"])
            icon.image = photo
            icon.pack()

            # name (small)
            tk.Label(cell, text=ITEM_DISPLAY_NAMES[item_key],
                     font=("Arial", 9, "bold"),
                     bg=THEME["bg_card"], fg=THEME["text_muted"]).pack(pady=(2, 0))

            # current/needed counter
            count_lbl = tk.Label(cell, text="0/0", font=THEME["font_count"],
                                 bg=THEME["bg_card"], fg=THEME["text_dark"])
            count_lbl.pack(pady=4)

            # +/- buttons stacked vertically
            btn_col = tk.Frame(cell, bg=THEME["bg_card"])
            btn_col.pack()

            plus_btn = RoundedButton(
                btn_col, text="+1",
                command=lambda b=building_key, k=item_key: self._change_item(b, k, +1),
                width=58, height=34,
                bg_color=THEME["btn_green"], hover_color=THEME["btn_green_hover"]
            )
            plus_btn.pack(pady=(0, 4))

            minus_btn = RoundedButton(
                btn_col, text="-1",
                command=lambda b=building_key, k=item_key: self._change_item(b, k, -1),
                width=58, height=34,
                bg_color=THEME["btn_red"], hover_color=THEME["btn_red_hover"]
            )
            minus_btn.pack()

            item_widgets[item_key] = {
                "count_label": count_lbl,
                "cell": cell,
            }

        # upgrade button - lights up when ready
        upgrade_btn = RoundedButton(
            frame, text="⬆  UPGRADE",
            command=lambda b=building_key: self._do_upgrade(b),
            width=200, height=50,
            bg_color=THEME["btn_grey"], hover_color=THEME["btn_grey_hover"],
            font=THEME["font_button_big"], disabled=True
        )
        upgrade_btn.pack(pady=(8, 10))

        # store everything we need for _refresh_all
        setattr(self, f"_{building_key}_cap_label", cap_label)
        setattr(self, f"_{building_key}_item_widgets", item_widgets)
        setattr(self, f"_{building_key}_upgrade_btn", upgrade_btn)

        return frame

    # ---- center panel -------------------------------------------------
    def _build_center_panel(self, parent):
        frame = tk.Frame(parent, bg=THEME["bg_panel"], bd=2, relief="ridge")

        tk.Label(frame, text="Daily Limit", font=THEME["font_heading"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]).pack(pady=(20, 4))

        tk.Label(frame, text="Items bought today",
                 font=("Arial", 10),
                 bg=THEME["bg_panel"], fg=THEME["text_muted"]).pack()

        self._daily_label = tk.Label(frame, text="0 / 89",
                                     font=("Arial Black", 28, "bold"),
                                     bg=THEME["bg_panel"], fg=THEME["text_dark"])
        self._daily_label.pack(pady=(20, 20))

        btn_col = tk.Frame(frame, bg=THEME["bg_panel"])
        btn_col.pack(pady=10)

        RoundedButton(btn_col, text="+1",
                      command=lambda: self._change_daily(+1),
                      width=80, height=44,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"],
                      font=THEME["font_button_big"]
                      ).pack(pady=4)

        RoundedButton(btn_col, text="-1",
                      command=lambda: self._change_daily(-1),
                      width=80, height=44,
                      bg_color=THEME["btn_red"],
                      hover_color=THEME["btn_red_hover"],
                      font=THEME["font_button_big"]
                      ).pack(pady=4)

        RoundedButton(btn_col, text="Reset",
                      command=self._reset_daily,
                      width=80, height=34,
                      bg_color=THEME["btn_grey"],
                      hover_color=THEME["btn_grey_hover"]
                      ).pack(pady=(14, 4))

        return frame

    # =================================================================
    # data manipulation
    # =================================================================
    def _change_item(self, building_key: str, item_key: str, delta: int):
        items = self.data[building_key]["items"]
        new_value = items[item_key] + delta
        if new_value < 0:
            return  # can't go negative
        items[item_key] = new_value
        self._save()
        self._refresh_building(building_key)

    def _change_daily(self, delta: int):
        new_value = self.data.get("daily_limit_used", 0) + delta
        if new_value < 0:
            return
        if new_value > DAILY_LIMIT_MAX:
            new_value = DAILY_LIMIT_MAX  # cap at max
        self.data["daily_limit_used"] = new_value
        self._save()
        self._refresh_daily()

    def _reset_daily(self):
        self.data["daily_limit_used"] = 0
        self._save()
        self._refresh_daily()

    def _reset_all(self):
        if not messagebox.askyesno(
                "Reset items and daily limit",
                "This will set ALL expansion item counts to 0\n"
                "and reset the daily limit to 0.\n\n"
                "Capacity values will NOT change.\n\n"
                "Are you sure?"):
            return
        for building_key, item_keys in (("silo", SILO_ITEMS), ("barn", BARN_ITEMS)):
            for k in item_keys:
                self.data[building_key]["items"][k] = 0
        self.data["daily_limit_used"] = 0
        self._save()
        self._refresh_all()

    def _do_upgrade(self, building_key: str):
        capacity = self.data[building_key]["capacity"]
        if not can_upgrade(building_key, capacity):
            messagebox.showinfo(
                "Maxed out",
                f"This {building_key} is already at maximum capacity "
                f"({BARN_MAX_CAPACITY})."
            )
            return

        needed = get_required_items(capacity)
        items = self.data[building_key]["items"]
        item_keys = SILO_ITEMS if building_key == "silo" else BARN_ITEMS

        # double-check we have enough (button should be disabled, but be defensive)
        for k in item_keys:
            if items[k] < needed:
                return

        # confirm
        new_capacity = get_next_capacity(capacity)
        if not messagebox.askyesno(
                f"Upgrade {building_key}?",
                f"This will:\n"
                f"  • Subtract {needed} from each expansion item\n"
                f"  • Increase capacity: {capacity} → {new_capacity}\n\n"
                f"Continue?"):
            return

        # apply
        for k in item_keys:
            items[k] -= needed
        self.data[building_key]["capacity"] = new_capacity
        self._save()
        self._refresh_building(building_key)

    def _save(self):
        self.pm.save(self.profile_name, self.data)

    # =================================================================
    # rendering
    # =================================================================
    def _refresh_all(self):
        self._refresh_building("silo")
        self._refresh_building("barn")
        self._refresh_daily()

    def _refresh_building(self, building_key: str):
        capacity = self.data[building_key]["capacity"]
        items = self.data[building_key]["items"]
        item_keys = SILO_ITEMS if building_key == "silo" else BARN_ITEMS

        cap_label = getattr(self, f"_{building_key}_cap_label")
        item_widgets = getattr(self, f"_{building_key}_item_widgets")
        upgrade_btn = getattr(self, f"_{building_key}_upgrade_btn")

        # capacity progression text
        if can_upgrade(building_key, capacity):
            next_cap = get_next_capacity(capacity)
            cap_label.config(text=f"{capacity}  →  {next_cap}")
            needed = get_required_items(capacity)
        else:
            cap_label.config(text=f"{capacity}  (MAX)")
            needed = None

        # update item counters and detect ready-to-upgrade
        all_ready = needed is not None
        for k in item_keys:
            current = items[k]
            widgets = item_widgets[k]
            if needed is None:
                widgets["count_label"].config(text=str(current),
                                              fg=THEME["text_muted"])
            else:
                widgets["count_label"].config(text=f"{current}/{needed}")
                if current >= needed:
                    widgets["count_label"].config(fg=THEME["text_ok"])
                else:
                    widgets["count_label"].config(fg=THEME["text_dark"])
                    all_ready = False

        # upgrade button: light up when ready, grey when not
        if all_ready:
            upgrade_btn.set_disabled(False)
            upgrade_btn.set_colors(THEME["btn_green"], THEME["btn_green_hover"])
        elif needed is None:
            upgrade_btn.set_disabled(True)
            upgrade_btn.set_text("MAXED")
        else:
            upgrade_btn.set_disabled(True)

    def _refresh_daily(self):
        used = self.data.get("daily_limit_used", 0)
        self._daily_label.config(text=f"{used} / {DAILY_LIMIT_MAX}")
        # color cue when close to limit
        if used >= DAILY_LIMIT_MAX:
            self._daily_label.config(fg=THEME["text_warning"])
        elif used >= DAILY_LIMIT_MAX - 10:
            self._daily_label.config(fg="#D2851A")  # amber
        else:
            self._daily_label.config(fg=THEME["text_dark"])
