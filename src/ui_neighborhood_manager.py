"""
Neighborhood Manager main screen.

Once a neighborhood is active, this screen hosts the four tabs:
- Members
- New Snapshot
- Snapshots history
- Statistics (placeholder for stage 2/3)

Each tab is built lazily: clicking a tab destroys the current content frame
and rebuilds the new one. This keeps the data fresh after every edit.
"""

import tkinter as tk
from tkinter import messagebox

from theme import THEME
from widgets import RoundedButton

from ui_members_tab import MembersTab
from ui_new_snapshot_tab import NewSnapshotTab
from ui_snapshots_tab import SnapshotsTab
from ui_statistics_tab import StatisticsTab


class NeighborhoodManagerFrame(tk.Frame):
    TABS = ("Members", "New Snapshot", "Snapshots", "Activity", "Statistics")

    def __init__(self, parent, app):
        super().__init__(parent, bg=THEME["bg_main"])
        self.app = app
        self.nm = app.neighborhood_manager

        clan_name = self.nm.get_active()
        if clan_name is None:
            messagebox.showerror("No neighborhood", "No active neighborhood.")
            self.app.show_frame("NeighborhoodSelect", first_run=True)
            return

        self.clan_name = clan_name

        self._build_top_bar()
        self._build_tab_bar()

        # content area (replaced when switching tabs)
        self.content = tk.Frame(self, bg=THEME["bg_main"])
        self.content.pack(fill="both", expand=True)

        self.current_tab = None
        self.show_tab("Members")

    # =================================================================
    # data access
    # =================================================================
    def reload_data(self) -> dict:
        """Tabs call this to get the current state of the clan.
        Served from cache; only re-read from disk after invalidate()."""
        return self.nm.load(self.clan_name)

    def save_data(self, data: dict) -> None:
        self.nm.save(self.clan_name, data)

    def _refresh_all(self):
        """Manual refresh — drops the cache and rebuilds the current tab."""
        self.nm.invalidate_cache(self.clan_name)
        self.refresh_top_bar()

    # =================================================================
    # top bar - clan info, switch clan, back
    # =================================================================
    def _build_top_bar(self):
        top = tk.Frame(self, bg=THEME["bg_top"], height=60)
        top.pack(side="top", fill="x")
        top.pack_propagate(False)

        RoundedButton(top, text="← Menu",
                      command=lambda: self.app.show_frame("MainMenu"),
                      width=110, height=40,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="left", padx=15, pady=10)

        # title shows clan name + tag if any
        data = self.nm.load(self.clan_name)
        title_text = f"{data.get('clan_name', self.clan_name)}"
        if data.get("clan_tag"):
            title_text += f"  ({data['clan_tag']})"
        tk.Label(top, text=title_text, font=THEME["font_title"],
                 bg=THEME["bg_top"], fg=THEME["text_dark"]).pack(side="left",
                                                                  expand=True)

        RoundedButton(top, text="🏘  Switch clan",
                      command=lambda: self.app.show_frame(
                          "NeighborhoodSelect", return_to="NeighborhoodManager"),
                      width=150, height=40,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="right", padx=(0, 15), pady=10)

        RoundedButton(top, text="⚙ Settings",
                      command=lambda: self.app.show_frame(
                          "AppSettings", initial_section="Neighbourhood"),
                      width=120, height=40,
                      bg_color=THEME["btn_blue"],
                      hover_color=THEME["btn_blue_hover"]
                      ).pack(side="right", padx=(0, 5), pady=10)

        RoundedButton(top, text="↻ Refresh",
                      command=self._refresh_all,
                      width=110, height=40,
                      bg_color=THEME["btn_grey"],
                      hover_color=THEME["btn_grey_hover"]
                      ).pack(side="right", padx=(0, 5), pady=10)

        # sub bar with member count
        active = sum(1 for m in data["members"].values() if m["in_clan"])
        total = len(data["members"])
        n_snaps = len(data.get("snapshots", []))
        sub = tk.Frame(self, bg=THEME["bg_panel"], height=28)
        sub.pack(side="top", fill="x")
        sub.pack_propagate(False)
        info = (f"Members in clan: {active}/30   •   "
                f"Total in database: {total}   •   "
                f"Snapshots: {n_snaps}")
        tk.Label(sub, text=info, font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"]).pack(side="left",
                                                                    padx=20)

    # =================================================================
    # tab bar
    # =================================================================
    def _build_tab_bar(self):
        bar = tk.Frame(self, bg=THEME["bg_main"], height=54)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)

        self.tab_buttons = {}
        for tab in self.TABS:
            btn = RoundedButton(bar, text=tab,
                                command=lambda t=tab: self.show_tab(t),
                                width=180, height=40,
                                bg_color=THEME["btn_grey"],
                                hover_color=THEME["btn_grey_hover"],
                                font=THEME["font_button"])
            btn.pack(side="left", padx=6, pady=8)
            self.tab_buttons[tab] = btn

    def _highlight_tab(self, tab_name: str):
        for tab, btn in self.tab_buttons.items():
            if tab == tab_name:
                btn.set_colors(THEME["btn_green"], THEME["btn_green_hover"])
            else:
                btn.set_colors(THEME["btn_grey"], THEME["btn_grey_hover"])

    # =================================================================
    # tab switching
    # =================================================================
    def show_tab(self, tab_name: str):
        # destroy old content
        for child in self.content.winfo_children():
            child.destroy()

        self.current_tab = tab_name
        self._highlight_tab(tab_name)

        if tab_name == "Members":
            tab = MembersTab(self.content, manager=self)
        elif tab_name == "New Snapshot":
            tab = NewSnapshotTab(self.content, manager=self)
        elif tab_name == "Snapshots":
            tab = SnapshotsTab(self.content, manager=self)
        elif tab_name == "Activity":
            from ui_activity_tab import ActivityTab
            tab = ActivityTab(self.content, manager=self)
        elif tab_name == "Statistics":
            tab = StatisticsTab(self.content, manager=self)
        else:
            tab = tk.Frame(self.content, bg=THEME["bg_main"])

        tab.pack(fill="both", expand=True)

    def _build_stats_placeholder(self):
        """Kept for fallback only; the real stats tab now exists."""
        f = tk.Frame(self.content, bg=THEME["bg_main"])
        tk.Label(f, text="Statistics", font=THEME["font_heading"],
                 bg=THEME["bg_main"], fg=THEME["text_muted"]).pack(pady=80)
        return f

    def open_imported_snapshot(self, prefill):
        """Open a NEW snapshot prefilled from a screenshot import.

        Clears the content area and shows a NewSnapshotTab seeded with the
        parsed prefill (editing=False → Save creates a brand-new snapshot).
        """
        for child in self.content.winfo_children():
            child.destroy()
        self.current_tab = "New Snapshot"
        self._highlight_tab("New Snapshot")
        tab = NewSnapshotTab(self.content, manager=self,
                             prefill_snapshot=prefill, editing=False)
        tab.pack(fill="both", expand=True)

    def refresh_current_tab(self):
        """Re-render the current tab from disk. Used after edits in dialogs."""
        if self.current_tab:
            self.show_tab(self.current_tab)

    def refresh_top_bar(self):
        """Rebuild top bar - call when member counts change."""
        # destroy and rebuild only the sub-bar; fastest correct option
        for child in self.winfo_children():
            child.destroy()
        self._build_top_bar()
        self._build_tab_bar()
        self.content = tk.Frame(self, bg=THEME["bg_main"])
        self.content.pack(fill="both", expand=True)
        self.show_tab(self.current_tab or "Members")
