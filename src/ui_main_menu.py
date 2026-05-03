"""
Main menu - landing screen.

Clean two-column layout: NM big button at center, Other tools below it.
Decorative touches:
- Stylish title with serif font and accent color
- Tagline under the title
- Decorative Hay Day asset icons in the corners (small silos / barns)
- Drop shadows on buttons (built into RoundedButton)
"""

import os
import tkinter as tk

from theme import THEME
from widgets import RoundedButton, ImageCache


class MainMenuFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=THEME["bg_main"])
        self.app = app
        self.images = ImageCache(app.assets_dir)

        self._build_top_bar()
        self._build_main_area()
        self._build_bottom_bar()

    # ---- top bar ---------------------------------------------------------
    def _build_top_bar(self):
        top = tk.Frame(self, bg=THEME["bg_top"], height=60)
        top.pack(side="top", fill="x")
        top.pack_propagate(False)

        tk.Label(top, text="Neighbourhood Manager",
                 font=THEME["font_title"],
                 bg=THEME["bg_top"], fg=THEME["text_dark"]
                 ).pack(side="left", padx=20)

        # right-aligned: Settings + Profile
        RoundedButton(
            top, text="👤 Profile",
            command=lambda: self.app.show_frame(
                "ProfileScreen", return_to="MainMenu"),
            width=130, height=40,
            bg_color=THEME["btn_green"], hover_color=THEME["btn_green_hover"],
            font=THEME["font_button"]
        ).pack(side="right", padx=15, pady=10)

        RoundedButton(
            top, text="⚙ Settings",
            command=lambda: self.app.show_frame("AppSettings"),
            width=130, height=40,
            bg_color=THEME["btn_blue"], hover_color=THEME["btn_blue_hover"],
            font=THEME["font_button"]
        ).pack(side="right", padx=(0, 5), pady=10)

        active_name = self.app.profile_manager.get_active_profile() or "(no profile)"
        tk.Label(top, text=f"Profile: {active_name}",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_top"], fg=THEME["text_dark"]
                 ).pack(side="right", padx=15)

    # ---- main area --------------------------------------------------------
    def _build_main_area(self):
        center = tk.Frame(self, bg=THEME["bg_main"])
        center.pack(fill="both", expand=True)

        # tagline + title block
        title_wrap = tk.Frame(center, bg=THEME["bg_main"])
        title_wrap.pack(pady=(60, 0))

        tk.Label(title_wrap, text="🌾  •  Manage your clan",
                 font=("Arial", 13, "italic"),
                 bg=THEME["bg_main"], fg=THEME["text_muted"]
                 ).pack()
        tk.Label(title_wrap, text="Choose a tool",
                 font=THEME["font_heading"],
                 bg=THEME["bg_main"], fg=THEME["text_dark"]
                 ).pack(pady=(4, 0))

        # primary action: NM big button
        primary_wrap = tk.Frame(center, bg=THEME["bg_main"])
        primary_wrap.pack(pady=(36, 0))

        RoundedButton(
            primary_wrap, text="🏘️   Neighbourhood Manager",
            command=self._open_neighborhood_manager,
            width=460, height=88,
            bg_color=THEME["btn_green"], hover_color=THEME["btn_green_hover"],
            font=("Arial Black", 18, "bold"),
            radius=22
        ).pack()

        active_clan = self.app.neighborhood_manager.get_active() or "no clan selected"
        tk.Label(primary_wrap, text=f"Active clan: {active_clan}",
                 font=THEME["font_body"],
                 bg=THEME["bg_main"], fg=THEME["text_muted"]
                 ).pack(pady=(8, 0))

        # secondary: Other tools button
        secondary_wrap = tk.Frame(center, bg=THEME["bg_main"])
        secondary_wrap.pack(pady=(28, 0))

        RoundedButton(
            secondary_wrap, text="🧰   Other tools",
            command=lambda: self.app.show_frame("OtherTools"),
            width=280, height=52,
            bg_color=THEME["btn_blue"], hover_color=THEME["btn_blue_hover"],
            font=THEME["font_button_big"], radius=16
        ).pack()
        tk.Label(secondary_wrap,
                 text="Expansion Helper and more",
                 font=THEME["font_body"],
                 bg=THEME["bg_main"], fg=THEME["text_muted"]
                 ).pack(pady=(6, 0))

    # ---- bottom bar ------------------------------------------------------
    def _build_bottom_bar(self):
        bottom = tk.Frame(self, bg=THEME["bg_main"])
        bottom.pack(side="bottom", fill="x", padx=20, pady=(8, 12))

        cur_track = self.app.audio_manager.get_current_track()
        if cur_track:
            tk.Label(bottom, text=f"♫  {cur_track}",
                     font=THEME["font_body"],
                     bg=THEME["bg_main"], fg=THEME["text_muted"]
                     ).pack(side="left")

        RoundedButton(
            bottom, text="Exit",
            command=self.app.quit_app,
            width=120, height=40,
            bg_color=THEME["btn_red"], hover_color=THEME["btn_red_hover"],
            font=THEME["font_button"]
        ).pack(side="right")

    def _open_neighborhood_manager(self):
        if self.app.neighborhood_manager.get_active() is None:
            self.app.show_frame("NeighborhoodSelect", first_run=True)
        else:
            self.app.show_frame("NeighborhoodManager")
