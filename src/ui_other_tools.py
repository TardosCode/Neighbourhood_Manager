"""
Other tools screen.

Listed below "Neighbourhood Manager" in the main menu, this is where
secondary or supporting tools live. For now: just the Expansion Helper.
"""

import tkinter as tk

from theme import THEME
from widgets import RoundedButton


class OtherToolsFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=THEME["bg_main"])
        self.app = app

        # ---- top bar ------------------------------------------------------
        top = tk.Frame(self, bg=THEME["bg_top"], height=60)
        top.pack(side="top", fill="x")
        top.pack_propagate(False)

        RoundedButton(top, text="← Back",
                      command=lambda: self.app.show_frame("MainMenu"),
                      width=110, height=40,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="left", padx=15, pady=10)

        tk.Label(top, text="Other tools",
                 font=THEME["font_title"],
                 bg=THEME["bg_top"], fg=THEME["text_dark"]
                 ).pack(side="left", padx=20)

        RoundedButton(top, text="⚙ Settings",
                      command=lambda: self.app.show_frame("AppSettings"),
                      width=120, height=38,
                      bg_color=THEME["btn_blue"],
                      hover_color=THEME["btn_blue_hover"]
                      ).pack(side="right", padx=15, pady=10)

        # ---- body --------------------------------------------------------
        body = tk.Frame(self, bg=THEME["bg_main"])
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Pick a tool",
                 font=THEME["font_heading"],
                 bg=THEME["bg_main"], fg=THEME["text_dark"]
                 ).pack(pady=(40, 20))

        # tools grid - currently just one tool but easy to extend
        grid = tk.Frame(body, bg=THEME["bg_main"])
        grid.pack()

        active_profile = self.app.profile_manager.get_active_profile() or "(none)"

        col = tk.Frame(grid, bg=THEME["bg_main"])
        col.grid(row=0, column=0, padx=12, pady=12)
        RoundedButton(
            col, text="🌾  Expansion - Helper",
            command=lambda: self.app.show_frame("ExpansionHelper"),
            width=320, height=70,
            bg_color=THEME["btn_green"], hover_color=THEME["btn_green_hover"],
            font=THEME["font_button_big"]
        ).pack()
        tk.Label(col, text=f"Active profile: {active_profile}",
                 font=THEME["font_body"],
                 bg=THEME["bg_main"], fg=THEME["text_muted"]
                 ).pack(pady=(8, 0))

        # placeholder for future tools
        col2 = tk.Frame(grid, bg=THEME["bg_main"])
        col2.grid(row=0, column=1, padx=12, pady=12)
        RoundedButton(
            col2, text="More tools coming soon...",
            command=None, disabled=True,
            width=320, height=70,
            bg_color=THEME["btn_grey"], hover_color=THEME["btn_grey_hover"],
            font=THEME["font_button_big"]
        ).pack()
        tk.Label(col2, text=" ",
                 font=THEME["font_body"],
                 bg=THEME["bg_main"], fg=THEME["text_muted"]
                 ).pack(pady=(8, 0))
