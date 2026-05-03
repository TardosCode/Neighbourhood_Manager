"""
Snapshots history tab.

Each snapshot is a collapsible card. Closed by default — click the header
to expand and see per-member details. The header always shows the date,
type (After-Derby / Quick), and a quick summary line.

A search box at the top filters by date (substring match: type "2026-04"
to see all April 2026 snapshots, or "04-15" to find ones on the 15th of
any April).
"""

import tkinter as tk
from tkinter import messagebox

from theme import THEME
from widgets import RoundedButton
from ui_widgets_extra import SearchBox, attach_smooth_mousewheel
from neighborhood_manager import (
    delete_snapshot, get_snapshot,
    SNAPSHOT_TYPE_AFTER_DERBY, SNAPSHOT_TYPE_QUICK, SNAPSHOT_TYPE_DONATIONS,
    DONATION_CATEGORIES,
)


class SnapshotsTab(tk.Frame):
    def __init__(self, parent, manager):
        super().__init__(parent, bg=THEME["bg_main"])
        self.manager = manager
        self.data = manager.reload_data()

        # search query (date substring)
        self.search_query = ""

        self._build_header()
        self._build_list_container()
        self._render_snapshots()

    # ---- header ---------------------------------------------------------
    def _build_header(self):
        bar = tk.Frame(self, bg=THEME["bg_main"])
        bar.pack(side="top", fill="x", padx=20, pady=(10, 6))

        n = len(self.data.get("snapshots", []))
        tk.Label(bar, text=f"Snapshots: {n} total  (newest first)",
                 font=THEME["font_subheading"],
                 bg=THEME["bg_main"], fg=THEME["text_dark"]
                 ).pack(side="left")

        RoundedButton(bar, text="+  New snapshot",
                      command=lambda: self.manager.show_tab("New Snapshot"),
                      width=160, height=40,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="right")

        # search box on its own row
        search_row = tk.Frame(self, bg=THEME["bg_main"])
        search_row.pack(side="top", fill="x", padx=20, pady=(0, 6))
        SearchBox(search_row,
                  on_change=self._on_search_change,
                  placeholder="Filter by date (e.g. 2026-04)…",
                  width=28,
                  bg=THEME["bg_main"]
                  ).pack(side="left")

    def _on_search_change(self, query):
        self.search_query = query.strip().lower()
        self._render_snapshots()

    # ---- list container -------------------------------------------------
    def _build_list_container(self):
        wrap = tk.Frame(self, bg=THEME["bg_main"])
        wrap.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        canvas = tk.Canvas(wrap, bg=THEME["bg_main"],
                           highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(wrap, orient="vertical",
                                  command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._list_body = tk.Frame(canvas, bg=THEME["bg_main"])
        canvas_window = canvas.create_window(
            (0, 0), window=self._list_body, anchor="nw")
        self._list_body.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(canvas_window, width=e.width))
        attach_smooth_mousewheel(canvas)

    def _render_snapshots(self):
        for child in self._list_body.winfo_children():
            child.destroy()

        snaps = sorted(self.data.get("snapshots", []),
                       key=lambda s: (s.get("date", ""),
                                       s.get("snapshot_id", "")),
                       reverse=True)

        # apply date search filter
        if self.search_query:
            snaps = [s for s in snaps
                     if self.search_query in s.get("date", "").lower()]

        if not snaps:
            if self.search_query:
                msg = f"No snapshots match '{self.search_query}'."
            else:
                msg = ("No snapshots yet.\n"
                       "Click \"+ New snapshot\" to record one.")
            tk.Label(self._list_body, text=msg,
                     font=THEME["font_body"], bg=THEME["bg_main"],
                     fg=THEME["text_muted"]).pack(pady=40)
            return

        for snap in snaps:
            CollapsibleSnapshotCard(self._list_body, snap,
                                     manager=self.manager,
                                     all_data=self.data,
                                     on_delete=self._delete_snapshot,
                                     on_edit=self._edit_snapshot
                                     ).pack(fill="x", pady=4, padx=2)

    # ---- actions ---------------------------------------------------------
    def _delete_snapshot(self, snapshot_id: str):
        snap = get_snapshot(self.data, snapshot_id)
        if snap is None:
            return
        if not messagebox.askyesno(
                "Delete snapshot",
                f"Delete the snapshot from {snap['date']}?\n"
                "This cannot be undone."):
            return
        delete_snapshot(self.data, snapshot_id)
        self.manager.save_data(self.data)
        self.manager.refresh_top_bar()

    def _edit_snapshot(self, snapshot_id: str):
        snap = get_snapshot(self.data, snapshot_id)
        if snap is None:
            return
        for child in self.manager.content.winfo_children():
            child.destroy()
        from ui_new_snapshot_tab import NewSnapshotTab
        editor = NewSnapshotTab(self.manager.content, manager=self.manager,
                                prefill_snapshot=snap)
        editor.pack(fill="both", expand=True)
        self.manager._highlight_tab("New Snapshot")
        self.manager.current_tab = "New Snapshot"


# =================================================================
# Collapsible card for one snapshot
# =================================================================

class CollapsibleSnapshotCard(tk.Frame):
    """One snapshot rendered as a collapsible card.

    Header (always visible): date + type badge + summary stats + buttons
    Body (toggled): full per-member entries table
    """

    def __init__(self, parent, snap, manager, all_data,
                 on_delete, on_edit):
        super().__init__(parent, bg=THEME["bg_main"])
        self.snap = snap
        self.manager = manager
        self.all_data = all_data
        self.is_open = False
        self._on_delete = on_delete
        self._on_edit = on_edit

        # ---- header ----
        # Type badge color + label
        if snap["type"] == SNAPSHOT_TYPE_AFTER_DERBY:
            type_color = THEME["btn_green"]
            type_label = "After-Derby"
        elif snap["type"] == SNAPSHOT_TYPE_DONATIONS:
            type_color = "#9D5BD2"  # purple, distinct from derby/quick
            type_label = "Donations"
        else:
            type_color = THEME["btn_blue"]
            type_label = "Quick"

        self.header = tk.Frame(self, bg=THEME["bg_panel"], bd=2,
                                relief="ridge", cursor="hand2")
        self.header.pack(fill="x")

        # chevron
        self._chevron = tk.Label(self.header, text="▶",
                                  font=THEME["font_subheading"],
                                  bg=THEME["bg_panel"],
                                  fg=THEME["text_dark"], cursor="hand2")
        self._chevron.pack(side="left", padx=(10, 4), pady=8)

        # type badge (colored pill)
        badge = tk.Label(self.header, text=f" {type_label} ",
                         font=THEME["font_body_bold"],
                         bg=type_color, fg=THEME["text_light"],
                         padx=10, pady=4, cursor="hand2")
        badge.pack(side="left", padx=(2, 12))

        # date in big bold
        date_lbl = tk.Label(self.header, text=snap["date"],
                            font=THEME["font_subheading"],
                            bg=THEME["bg_panel"], fg=THEME["text_dark"],
                            cursor="hand2")
        date_lbl.pack(side="left")

        # quick summary on the same line
        summary = self._make_summary(snap)
        summary_lbl = tk.Label(self.header, text=f"   •   {summary}",
                                font=THEME["font_body"],
                                bg=THEME["bg_panel"],
                                fg=THEME["text_muted"], cursor="hand2")
        summary_lbl.pack(side="left", padx=(0, 8))

        # comment on right side if any
        if snap.get("derby_comment"):
            tk.Label(self.header,
                     text=f"💬 {snap['derby_comment']}",
                     font=THEME["font_body"],
                     bg=THEME["bg_panel"],
                     fg=THEME["text_muted"],
                     cursor="hand2"
                     ).pack(side="left", padx=(0, 8))

        # action buttons (do NOT toggle the card on click)
        RoundedButton(self.header, text="Delete",
                      command=lambda sid=snap["snapshot_id"]:
                                  on_delete(sid),
                      width=80, height=30,
                      bg_color=THEME["btn_red"],
                      hover_color=THEME["btn_red_hover"],
                      font=("Arial", 10, "bold"), radius=8
                      ).pack(side="right", padx=(4, 8), pady=4)
        RoundedButton(self.header, text="Edit",
                      command=lambda sid=snap["snapshot_id"]:
                                  on_edit(sid),
                      width=70, height=30,
                      bg_color=THEME["btn_blue"],
                      hover_color=THEME["btn_blue_hover"],
                      font=("Arial", 10, "bold"), radius=8
                      ).pack(side="right", padx=4, pady=4)

        # bind clicks on header (and its labels) to toggle, EXCEPT
        # the buttons themselves which have their own commands.
        for widget in (self.header, self._chevron, badge, date_lbl,
                        summary_lbl):
            widget.bind("<Button-1>", lambda _e: self.toggle())

        # body (lazy: only built on first open)
        self.body = tk.Frame(self, bg=THEME["bg_card"])
        self._body_built = False
        # not packed initially - collapsed

    def _make_summary(self, snap):
        n = len(snap.get("entries", []))
        if snap.get("type") == SNAPSHOT_TYPE_DONATIONS:
            total_d = 0
            total_r = 0
            for e in snap.get("entries", []):
                for cat in DONATION_CATEGORIES:
                    total_d += e.get(f"{cat}_donated", 0) or 0
                    total_r += e.get(f"{cat}_requested", 0) or 0
            return (f"{n} members  •  donated {total_d:,}  "
                    f"•  requested {total_r:,}")

        levels = [e["level"] for e in snap.get("entries", [])
                  if e.get("level") is not None]
        avg = sum(levels) / len(levels) if levels else 0
        if not levels:
            return f"{n} members"
        s = f"{n} members  •  avg lvl {avg:.1f}"
        if snap["type"] == SNAPSHOT_TYPE_AFTER_DERBY:
            participated = sum(1 for e in snap["entries"]
                                if e.get("derby_participated"))
            total_pts = sum(e.get("derby_points", 0)
                            for e in snap["entries"])
            s += f"  •  {participated}/{n} participated  •  {total_pts:,} pts"
        return s

    def toggle(self):
        if self.is_open:
            self.body.pack_forget()
            self._chevron.config(text="▶")
            self.is_open = False
        else:
            if not self._body_built:
                self._build_body()
                self._body_built = True
            self.body.pack(fill="x")
            self._chevron.config(text="▼")
            self.is_open = True

    def _build_body(self):
        snap = self.snap
        is_after = snap["type"] == SNAPSHOT_TYPE_AFTER_DERBY
        is_donations = snap["type"] == SNAPSHOT_TYPE_DONATIONS

        wrap = tk.Frame(self.body, bg=THEME["bg_card"])
        wrap.pack(fill="x", padx=10, pady=8)

        # header row
        header = tk.Frame(wrap, bg=THEME["bg_top"])
        header.pack(fill="x")

        if is_donations:
            cols = [("Name", 200), ("Tag", 100),
                    ("Crops d", 80), ("Crops r", 80),
                    ("Foods d", 80), ("Foods r", 80),
                    ("Tools d", 80), ("Tools r", 80),
                    ("Comment", 200)]
        else:
            cols = [("Name", 200), ("Tag", 100), ("Lv", 50)]
            if is_after:
                cols += [("Derby", 60), ("Tasks", 80), ("Points", 80)]
            cols += [("Comment", 220), ("Fate", 80)]
        for label, w in cols:
            f = tk.Frame(header, bg=THEME["bg_top"], width=w, height=24)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Label(f, text=label, font=("Arial", 10, "bold"),
                     bg=THEME["bg_top"], fg=THEME["text_dark"]
                     ).pack(expand=True)

        # data rows
        members = self.all_data.get("members", {})
        for i, e in enumerate(snap.get("entries", [])):
            bg = "#FFFAEC" if i % 2 == 0 else THEME["bg_card"]
            row = tk.Frame(wrap, bg=bg)
            row.pack(fill="x")

            mid = e["member_id"]
            mname = members.get(mid, {}).get("name", "(deleted)")

            def cell(parent, text, width, anchor="center",
                      font=("Arial", 10), fg=THEME["text_dark"]):
                f = tk.Frame(parent, bg=bg, width=width, height=22)
                f.pack(side="left")
                f.pack_propagate(False)
                tk.Label(f, text=text, font=font, bg=bg, fg=fg,
                         anchor=anchor).pack(fill="both", expand=True,
                                              padx=6)

            cell(row, mname, 200, anchor="w")
            cell(row, mid, 100, font=("Consolas", 9),
                 fg=THEME["text_muted"])

            if is_donations:
                # Crops d / Crops r / Foods d / Foods r / Tools d / Tools r / Comment
                for cat in DONATION_CATEGORIES:
                    cell(row, str(e.get(f"{cat}_donated", 0) or 0), 80,
                         font=("Arial", 10, "bold"))
                    cell(row, str(e.get(f"{cat}_requested", 0) or 0), 80,
                         fg=THEME["text_muted"])
                cell(row, e.get("member_comment", ""), 200, anchor="w",
                     fg=THEME["text_muted"])
                continue  # skip the derby/level branches

            cell(row, str(e.get("level", "—")), 50,
                 font=("Arial", 10, "bold"))

            if is_after:
                participated = e.get("derby_participated")
                cell(row, "yes" if participated else "no", 60,
                     fg=THEME["text_ok"] if participated
                        else THEME["text_muted"])
                if participated:
                    tmax = e.get("tasks_max", 12)
                    if tmax == 0:
                        tasks_str = "—"
                    else:
                        tasks_str = f"{e.get('tasks_done', 0)}/{tmax}"
                    points_str = str(e.get("derby_points", 0))
                else:
                    tasks_str = "—"
                    points_str = "—"
                cell(row, tasks_str, 80)
                cell(row, points_str, 80)

            cell(row, e.get("member_comment", ""), 220, anchor="w",
                 fg=THEME["text_muted"])

            fate = e.get("fate", "")
            fate_color = {
                "stay": THEME["text_ok"],
                "warning": "#D2851A",
                "kick": THEME["text_warning"],
            }.get(fate, THEME["text_muted"])
            cell(row, fate, 80, fg=fate_color, font=("Arial", 10, "bold"))
