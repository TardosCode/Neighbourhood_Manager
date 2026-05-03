"""
New Snapshot tab — two-step workflow.

Step 1: Select members
  - Clean list (just name, tag, in-clan indicator)
  - Per-row include checkbox
  - Search by name or tag
  - Filter: in-clan / out-of-clan
  - "Next" button proceeds to Step 2

Step 2: Fill data
  - Only the members selected in Step 1 are shown
  - Date, Type (After-Derby / Quick / Donations), header comment
  - Per-row data entry depends on type:
      After-Derby: Level, Derby?, Tasks, Max, Points, Comment, Fate
      Quick: Level, Comment, Fate
      Donations: Crops d/r, Foods d/r, Tools d/r (no level - donations
                 reset weekly and don't carry level info)
  - "← Back" returns to Step 1 (selection is preserved)
  - "Save snapshot" persists

When editing an existing snapshot, the workflow is the same — Step 1 starts
with all members in the snapshot already checked, and changing the selection
adjusts who appears in Step 2.
"""

import tkinter as tk
from tkinter import messagebox
from datetime import date

from theme import THEME
from widgets import RoundedButton
from ui_widgets_extra import SearchBox, attach_smooth_mousewheel
from neighborhood_manager import (
    add_snapshot, new_snapshot_id, latest_levels, update_snapshot,
    SNAPSHOT_TYPE_AFTER_DERBY, SNAPSHOT_TYPE_QUICK, SNAPSHOT_TYPE_DONATIONS,
    VALID_FATES, FATE_STAY, DONATION_CATEGORIES,
)


class NewSnapshotTab(tk.Frame):
    def __init__(self, parent, manager, prefill_snapshot: dict = None):
        super().__init__(parent, bg=THEME["bg_main"])
        self.manager = manager
        self.data = manager.reload_data()
        self.prefill = prefill_snapshot
        self.is_editing = prefill_snapshot is not None

        # the active step: 1 = select members, 2 = fill data
        self.step = 1
        # tracks which snapshot type Step 2 last rendered with, so we know
        # when a type switch needs a full re-render (Donations <-> derby)
        self._last_rendered_type = None

        # selection state shared between the two steps
        # member_id -> bool (True if included in this snapshot)
        if self.is_editing:
            self.selected = {e["member_id"]: True
                             for e in prefill_snapshot["entries"]}
        else:
            # default: in-clan members preselected
            self.selected = {mid: bool(m["in_clan"])
                             for mid, m in self.data["members"].items()}

        # data-entry state for step 2 - filled only when needed, but
        # persisted across step toggles so users don't lose typing
        # member_id -> dict of StringVars/BooleanVars
        self.row_state = {}

        # the date/type/comment - shared form state
        default_date = (self.prefill["date"] if self.is_editing
                        else date.today().isoformat())
        default_type = (self.prefill["type"] if self.is_editing
                        else SNAPSHOT_TYPE_AFTER_DERBY)
        default_comment = (self.prefill.get("derby_comment", "")
                           if self.is_editing else "")
        self.var_date = tk.StringVar(value=default_date)
        self.var_type = tk.StringVar(value=default_type)
        self.var_derby_comment = tk.StringVar(value=default_comment)

        # filter / search state on step 1
        self.var_show_in_clan = tk.BooleanVar(value=True)
        self.var_show_out_of_clan = tk.BooleanVar(value=self.is_editing)
        self.search_query = ""

        self._render()

    # =================================================================
    # high-level render dispatcher
    # =================================================================
    def _render(self):
        for child in self.winfo_children():
            child.destroy()
        if self.step == 1:
            self._render_step1()
        else:
            self._render_step2()

    # =================================================================
    # STEP 1 - select members
    # =================================================================
    def _render_step1(self):
        # ---- header bar ----
        bar = tk.Frame(self, bg=THEME["bg_panel"], bd=2, relief="ridge")
        bar.pack(side="top", fill="x", padx=20, pady=(10, 6))

        title = "Edit snapshot — Step 1 of 2: Select members" \
                if self.is_editing else \
                "New snapshot — Step 1 of 2: Select members"
        tk.Label(bar, text=title, font=THEME["font_subheading"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(side="top", pady=(8, 4))

        tk.Label(bar,
                 text="Pick the members affected by this snapshot. "
                      "You'll fill in their data on the next step.",
                 font=THEME["font_body"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"]
                 ).pack(side="top", padx=20, pady=(0, 6))

        # ---- search + filters row ----
        row = tk.Frame(bar, bg=THEME["bg_panel"])
        row.pack(side="top", fill="x", padx=20, pady=(2, 8))

        SearchBox(row,
                  on_change=self._on_search_change,
                  placeholder="Search by name or tag…",
                  width=22,
                  bg=THEME["bg_panel"]
                  ).pack(side="left", padx=(0, 14))

        tk.Label(row, text="Show:",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(side="left")

        tk.Checkbutton(row, text="In clan",
                       variable=self.var_show_in_clan,
                       command=self._refresh_member_list,
                       font=THEME["font_body_bold"],
                       bg=THEME["bg_panel"], fg=THEME["text_dark"],
                       activebackground=THEME["bg_panel"],
                       selectcolor=THEME["bg_card"]
                       ).pack(side="left", padx=(6, 12))
        tk.Checkbutton(row, text="Out of clan (former / not yet joined)",
                       variable=self.var_show_out_of_clan,
                       command=self._refresh_member_list,
                       font=THEME["font_body_bold"],
                       bg=THEME["bg_panel"], fg=THEME["text_dark"],
                       activebackground=THEME["bg_panel"],
                       selectcolor=THEME["bg_card"]
                       ).pack(side="left")

        RoundedButton(row, text="Check all visible",
                      command=lambda: self._set_all_visible(True),
                      width=140, height=28,
                      bg_color=THEME["btn_grey"],
                      hover_color=THEME["btn_grey_hover"],
                      font=("Arial", 10, "bold"), radius=8
                      ).pack(side="right", padx=2)
        RoundedButton(row, text="Uncheck all",
                      command=lambda: self._set_all_visible(False),
                      width=120, height=28,
                      bg_color=THEME["btn_grey"],
                      hover_color=THEME["btn_grey_hover"],
                      font=("Arial", 10, "bold"), radius=8
                      ).pack(side="right", padx=2)

        # ---- member list (clean: only Inc / Name / Tag / In clan) ----
        list_wrap = tk.Frame(self, bg=THEME["bg_main"])
        list_wrap.pack(side="top", fill="both", expand=True, padx=20)

        # column header
        header = tk.Frame(list_wrap, bg=THEME["bg_top"], bd=1, relief="solid")
        header.pack(side="top", fill="x")
        for label, w in [("Inc.", 60), ("Name", 320), ("Tag", 140),
                          ("In clan", 100)]:
            f = tk.Frame(header, bg=THEME["bg_top"], width=w, height=28)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Label(f, text=label, font=THEME["font_body_bold"],
                     bg=THEME["bg_top"], fg=THEME["text_dark"]
                     ).pack(expand=True)

        # scrollable body
        body_wrap = tk.Frame(list_wrap, bg=THEME["bg_main"])
        body_wrap.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(body_wrap, bg=THEME["bg_main"],
                           highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(body_wrap, orient="vertical",
                                 command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._step1_body = tk.Frame(canvas, bg=THEME["bg_main"])
        self._step1_canvas_window = canvas.create_window(
            (0, 0), window=self._step1_body, anchor="nw")
        self._step1_body.bind("<Configure>",
                               lambda e: canvas.configure(
                                   scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(
                        self._step1_canvas_window, width=e.width))
        attach_smooth_mousewheel(canvas)

        self._render_step1_rows()

        # ---- footer with Next button + selected count ----
        footer = tk.Frame(self, bg=THEME["bg_main"])
        footer.pack(side="bottom", fill="x", padx=20, pady=10)

        n_selected = sum(1 for v in self.selected.values() if v)
        self._step1_count_label = tk.Label(
            footer, text=f"{n_selected} member(s) selected",
            font=THEME["font_body_bold"],
            bg=THEME["bg_main"], fg=THEME["text_dark"]
        )
        self._step1_count_label.pack(side="left")

        RoundedButton(footer, text="Next →",
                      command=self._goto_step2,
                      width=160, height=46,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"],
                      font=THEME["font_button_big"]
                      ).pack(side="right")

        if self.is_editing:
            RoundedButton(footer, text="Cancel",
                          command=lambda: self.manager.show_tab("Snapshots"),
                          width=140, height=46,
                          bg_color=THEME["btn_grey"],
                          hover_color=THEME["btn_grey_hover"]
                          ).pack(side="right", padx=10)

    def _on_search_change(self, query):
        self.search_query = query.lower()
        self._refresh_member_list()

    def _refresh_member_list(self):
        if self.step == 1 and hasattr(self, "_step1_body"):
            for child in self._step1_body.winfo_children():
                child.destroy()
            self._render_step1_rows()
            self._update_step1_count()

    def _render_step1_rows(self):
        # which members to show given filters + search
        levels = latest_levels(self.data)
        all_members = list(self.data["members"].values())
        all_members.sort(key=lambda m: (
            not m["in_clan"],
            -(levels.get(m["member_id"], 0)),
            m["name"].lower(),
        ))

        show_in = self.var_show_in_clan.get()
        show_out = self.var_show_out_of_clan.get()
        q = self.search_query

        any_visible = False
        i = 0
        for m in all_members:
            in_clan = m["in_clan"]
            if in_clan and not show_in:
                continue
            if not in_clan and not show_out:
                continue
            if q:
                if (q not in m["name"].lower()
                        and q not in m["member_id"].lower()):
                    continue

            self._render_step1_row(m, i)
            any_visible = True
            i += 1

        if not any_visible:
            tk.Label(self._step1_body,
                     text=("No members match the current filters / search."
                           if q else
                           "No members match the current filters."),
                     font=THEME["font_body"], bg=THEME["bg_main"],
                     fg=THEME["text_muted"]).pack(pady=40)

    def _render_step1_row(self, member, row_index):
        bg = THEME["bg_card"] if row_index % 2 == 0 else THEME["bg_panel"]
        text_color = (THEME["text_dark"] if member["in_clan"]
                      else THEME["text_muted"])
        row = tk.Frame(self._step1_body, bg=bg, bd=1, relief="solid")
        row.pack(fill="x")

        # ----- Inc checkbox -----
        var = tk.BooleanVar(
            value=self.selected.get(member["member_id"], False))

        def _on_toggle(mid=member["member_id"], v=var):
            self.selected[mid] = v.get()
            self._update_step1_count()

        var.trace_add("write", lambda *_: _on_toggle())

        f_inc = tk.Frame(row, bg=bg, width=60, height=36)
        f_inc.pack(side="left")
        f_inc.pack_propagate(False)
        tk.Checkbutton(f_inc, variable=var,
                       bg=bg, activebackground=bg,
                       selectcolor=THEME["bg_card"]).pack(expand=True)

        # ----- name -----
        f = tk.Frame(row, bg=bg, width=320, height=36)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Label(f, text=member["name"], font=THEME["font_body_bold"],
                 bg=bg, fg=text_color, anchor="w"
                 ).pack(fill="both", expand=True, padx=8)

        # ----- tag -----
        f = tk.Frame(row, bg=bg, width=140, height=36)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Label(f, text=member["member_id"], font=("Consolas", 10),
                 bg=bg, fg=text_color).pack(expand=True)

        # ----- in-clan marker -----
        f = tk.Frame(row, bg=bg, width=100, height=36)
        f.pack(side="left")
        f.pack_propagate(False)
        if member["in_clan"]:
            tk.Label(f, text="✓ in clan", font=THEME["font_body_bold"],
                     bg=bg, fg=THEME["text_ok"]).pack(expand=True)
        else:
            tk.Label(f, text="— former", font=THEME["font_body"],
                     bg=bg, fg=THEME["text_muted"]).pack(expand=True)

    def _set_all_visible(self, value: bool):
        # only flip the ones currently visible according to filters/search
        all_members = list(self.data["members"].values())
        show_in = self.var_show_in_clan.get()
        show_out = self.var_show_out_of_clan.get()
        q = self.search_query
        for m in all_members:
            if m["in_clan"] and not show_in:
                continue
            if not m["in_clan"] and not show_out:
                continue
            if q and (q not in m["name"].lower()
                       and q not in m["member_id"].lower()):
                continue
            self.selected[m["member_id"]] = value
        self._refresh_member_list()

    def _update_step1_count(self):
        if hasattr(self, "_step1_count_label"):
            n = sum(1 for v in self.selected.values() if v)
            try:
                self._step1_count_label.config(
                    text=f"{n} member(s) selected")
            except tk.TclError:
                pass

    def _goto_step2(self):
        n = sum(1 for v in self.selected.values() if v)
        if n == 0:
            messagebox.showerror(
                "No selection",
                "Please select at least one member to include in the snapshot."
            )
            return
        self.step = 2
        self._render()

    # =================================================================
    # STEP 2 - fill data
    # =================================================================
    def _render_step2(self):
        # ---- header bar ----
        bar = tk.Frame(self, bg=THEME["bg_panel"], bd=2, relief="ridge")
        bar.pack(side="top", fill="x", padx=20, pady=(10, 6))

        title = ("Edit snapshot — Step 2 of 2: Fill data"
                 if self.is_editing else
                 "New snapshot — Step 2 of 2: Fill data")
        tk.Label(bar, text=title, font=THEME["font_subheading"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(side="top", pady=(8, 4))

        # row 1: date + type
        row1 = tk.Frame(bar, bg=THEME["bg_panel"])
        row1.pack(side="top", fill="x", padx=20, pady=4)

        tk.Label(row1, text="Date:", font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(side="left")
        tk.Entry(row1, textvariable=self.var_date, width=14,
                 font=THEME["font_body"], relief="solid", bd=1
                 ).pack(side="left", padx=(6, 24))

        tk.Label(row1, text="Type:", font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(side="left")

        tk.Radiobutton(row1, text="After-Derby (full)",
                       variable=self.var_type,
                       value=SNAPSHOT_TYPE_AFTER_DERBY,
                       command=self._on_type_change,
                       font=THEME["font_body_bold"],
                       bg=THEME["bg_panel"], fg=THEME["text_dark"],
                       activebackground=THEME["bg_panel"],
                       selectcolor=THEME["bg_card"]
                       ).pack(side="left", padx=(6, 6))
        tk.Radiobutton(row1, text="Quick (levels only)",
                       variable=self.var_type,
                       value=SNAPSHOT_TYPE_QUICK,
                       command=self._on_type_change,
                       font=THEME["font_body_bold"],
                       bg=THEME["bg_panel"], fg=THEME["text_dark"],
                       activebackground=THEME["bg_panel"],
                       selectcolor=THEME["bg_card"]
                       ).pack(side="left", padx=(6, 6))
        tk.Radiobutton(row1, text="Donations (weekly)",
                       variable=self.var_type,
                       value=SNAPSHOT_TYPE_DONATIONS,
                       command=self._on_type_change,
                       font=THEME["font_body_bold"],
                       bg=THEME["bg_panel"], fg=THEME["text_dark"],
                       activebackground=THEME["bg_panel"],
                       selectcolor=THEME["bg_card"]
                       ).pack(side="left", padx=(6, 6))

        # row 2: comment (label changes by type)
        row2 = tk.Frame(bar, bg=THEME["bg_panel"])
        row2.pack(side="top", fill="x", padx=20, pady=(2, 8))
        self._comment_label = tk.Label(row2, text="Derby comment (optional):",
                                        font=THEME["font_body_bold"],
                                        bg=THEME["bg_panel"],
                                        fg=THEME["text_dark"])
        self._comment_label.pack(side="left")
        tk.Entry(row2, textvariable=self.var_derby_comment, width=60,
                 font=THEME["font_body"], relief="solid", bd=1
                 ).pack(side="left", padx=(6, 0), fill="x", expand=True)

        # ---- member rows (only the ones selected in step 1) ----
        list_wrap = tk.Frame(self, bg=THEME["bg_main"])
        list_wrap.pack(side="top", fill="both", expand=True, padx=20)

        # column header (depends on snapshot type)
        snap_type = self.var_type.get()
        if snap_type == SNAPSHOT_TYPE_DONATIONS:
            cols = [("Name", 200), ("Tag", 100),
                    ("Crops d", 80), ("Crops r", 80),
                    ("Foods d", 80), ("Foods r", 80),
                    ("Tools d", 80), ("Tools r", 80),
                    ("Comment", 200)]
        else:
            cols = [("Name", 200), ("Tag", 100), ("Level", 60),
                    ("Derby?", 60), ("Tasks", 70), ("Max", 60),
                    ("Points", 80), ("Comment", 200), ("Fate", 140)]

        header = tk.Frame(list_wrap, bg=THEME["bg_top"], bd=1, relief="solid")
        header.pack(side="top", fill="x")
        for label, w in cols:
            f = tk.Frame(header, bg=THEME["bg_top"], width=w, height=28)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Label(f, text=label, font=THEME["font_body_bold"],
                     bg=THEME["bg_top"], fg=THEME["text_dark"]
                     ).pack(expand=True)

        # scrollable body with smooth scroll
        body_wrap = tk.Frame(list_wrap, bg=THEME["bg_main"])
        body_wrap.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(body_wrap, bg=THEME["bg_main"],
                           highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(body_wrap, orient="vertical",
                                 command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg=THEME["bg_main"])
        canvas_window = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(canvas_window, width=e.width))
        attach_smooth_mousewheel(canvas)

        # render rows for selected members only (sorted by level desc)
        levels = latest_levels(self.data)
        selected_ids = [mid for mid, sel in self.selected.items() if sel]
        selected_members = [self.data["members"][mid] for mid in selected_ids
                             if mid in self.data["members"]]
        selected_members.sort(key=lambda m: (
            not m["in_clan"],
            -(levels.get(m["member_id"], 0)),
            m["name"].lower(),
        ))

        prefill_by_id = {}
        if self.is_editing:
            for e in self.prefill["entries"]:
                prefill_by_id[e["member_id"]] = e

        for i, m in enumerate(selected_members):
            if snap_type == SNAPSHOT_TYPE_DONATIONS:
                self._render_step2_donations_row(
                    body, m, prefill_by_id.get(m["member_id"]), row_index=i)
            else:
                self._render_step2_row(body, m, levels, prefill_by_id.get(
                    m["member_id"]), row_index=i)

        # ---- footer: Back / Save ----
        footer = tk.Frame(self, bg=THEME["bg_main"])
        footer.pack(side="bottom", fill="x", padx=20, pady=10)

        save_text = "Save changes" if self.is_editing else "Save snapshot"
        RoundedButton(footer, text=save_text,
                      command=self._save,
                      width=200, height=46,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"],
                      font=THEME["font_button_big"]
                      ).pack(side="right")

        RoundedButton(footer, text="← Back",
                      command=self._goto_step1,
                      width=120, height=46,
                      bg_color=THEME["btn_grey"],
                      hover_color=THEME["btn_grey_hover"]
                      ).pack(side="right", padx=10)

        n = len(selected_members)
        tk.Label(footer, text=f"Filling data for {n} member(s)",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_main"], fg=THEME["text_dark"]
                 ).pack(side="left")

        # apply derby field locking immediately
        self._toggle_derby_fields()
        self._update_comment_label()
        self._last_rendered_type = self.var_type.get()

    def _render_step2_row(self, parent, member, levels, prefill, row_index):
        bg = THEME["bg_card"] if row_index % 2 == 0 else THEME["bg_panel"]
        text_color = (THEME["text_dark"] if member["in_clan"]
                      else THEME["text_muted"])
        row = tk.Frame(parent, bg=bg, bd=1, relief="solid")
        row.pack(fill="x")

        # use pre-existing state if user already typed something (e.g.
        # after going Back to Step 1 and returning to Step 2)
        existing = self.row_state.get(member["member_id"]) or {}

        # ----- name -----
        f = tk.Frame(row, bg=bg, width=200, height=36)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Label(f, text=member["name"], font=THEME["font_body_bold"],
                 bg=bg, fg=text_color, anchor="w"
                 ).pack(fill="both", expand=True, padx=8)

        # ----- tag -----
        f = tk.Frame(row, bg=bg, width=100, height=36)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Label(f, text=member["member_id"], font=("Consolas", 10),
                 bg=bg, fg=text_color).pack(expand=True)

        # ----- level -----
        if "level" in existing:
            level_default = existing["level"].get()
        elif prefill is not None and prefill.get("level") is not None:
            level_default = str(prefill["level"])
        elif levels.get(member["member_id"]) is not None:
            level_default = str(levels[member["member_id"]])
        else:
            level_default = ""
        var_level = tk.StringVar(value=level_default)
        f = tk.Frame(row, bg=bg, width=60, height=36)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Entry(f, textvariable=var_level, width=5,
                 font=THEME["font_body"], relief="solid", bd=1, justify="center"
                 ).pack(expand=True, padx=4, pady=4)

        # ----- derby? -----
        if "participated" in existing:
            part_default = existing["participated"].get()
        elif prefill is not None:
            part_default = bool(prefill.get("derby_participated"))
        else:
            part_default = False
        var_part = tk.BooleanVar(value=part_default)

        if "tasks" in existing:
            tasks_default = existing["tasks"].get()
        elif prefill is not None:
            tasks_default = str(prefill.get("tasks_done", ""))
        else:
            tasks_default = ""
        var_tasks = tk.StringVar(value=tasks_default)

        if "tasks_max" in existing:
            max_default = existing["tasks_max"].get()
        elif prefill is not None:
            max_default = str(prefill.get("tasks_max", 12))
        else:
            max_default = "12"
        var_tasks_max = tk.StringVar(value=max_default)

        if "points" in existing:
            points_default = existing["points"].get()
        elif prefill is not None:
            points_default = str(prefill.get("derby_points", ""))
        else:
            points_default = ""
        var_points = tk.StringVar(value=points_default)

        f_part = tk.Frame(row, bg=bg, width=60, height=36)
        f_part.pack(side="left")
        f_part.pack_propagate(False)
        cb_part = tk.Checkbutton(f_part, variable=var_part,
                                 bg=bg, activebackground=bg,
                                 selectcolor=THEME["bg_card"])
        cb_part.pack(expand=True)

        f_tasks = tk.Frame(row, bg=bg, width=70, height=36)
        f_tasks.pack(side="left")
        f_tasks.pack_propagate(False)
        e_tasks = tk.Entry(f_tasks, textvariable=var_tasks, width=6,
                           font=THEME["font_body"], relief="solid", bd=1,
                           justify="center")
        e_tasks.pack(expand=True, padx=4, pady=4)

        f_max = tk.Frame(row, bg=bg, width=60, height=36)
        f_max.pack(side="left")
        f_max.pack_propagate(False)
        e_max = tk.Entry(f_max, textvariable=var_tasks_max, width=5,
                         font=THEME["font_body"], relief="solid", bd=1,
                         justify="center")
        e_max.pack(expand=True, padx=4, pady=4)

        f_points = tk.Frame(row, bg=bg, width=80, height=36)
        f_points.pack(side="left")
        f_points.pack_propagate(False)
        e_points = tk.Entry(f_points, textvariable=var_points, width=8,
                            font=THEME["font_body"], relief="solid", bd=1,
                            justify="center")
        e_points.pack(expand=True, padx=4, pady=4)

        # ----- comment -----
        if "comment" in existing:
            comment_default = existing["comment"].get()
        elif prefill is not None:
            comment_default = prefill.get("member_comment", "")
        else:
            comment_default = ""
        var_comment = tk.StringVar(value=comment_default)
        f = tk.Frame(row, bg=bg, width=200, height=36)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Entry(f, textvariable=var_comment,
                 font=THEME["font_body"], relief="solid", bd=1
                 ).pack(expand=True, fill="x", padx=4, pady=4)

        # ----- fate -----
        if "fate" in existing:
            fate_default = existing["fate"].get()
        elif prefill is not None:
            fate_default = prefill.get("fate", FATE_STAY)
        else:
            fate_default = FATE_STAY
        var_fate = tk.StringVar(value=fate_default)
        f = tk.Frame(row, bg=bg, width=140, height=36)
        f.pack(side="left")
        f.pack_propagate(False)
        om = tk.OptionMenu(f, var_fate, *VALID_FATES)
        om.config(font=THEME["font_body"], bg=bg)
        om.pack(expand=True, padx=4, pady=4)

        self.row_state[member["member_id"]] = {
            "level": var_level,
            "participated": var_part,
            "tasks": var_tasks,
            "tasks_max": var_tasks_max,
            "points": var_points,
            "comment": var_comment,
            "fate": var_fate,
            "derby_widgets": [cb_part, e_tasks, e_max, e_points],
        }

    def _render_step2_donations_row(self, parent, member, prefill, row_index):
        """Render a row for the Donations snapshot type.

        Columns: Name | Tag | Crops d | Crops r | Foods d | Foods r |
                 Tools d | Tools r | Comment

        No level / derby / fate fields — donations snapshots only carry
        the six donation counts plus an optional comment.
        """
        bg = THEME["bg_card"] if row_index % 2 == 0 else THEME["bg_panel"]
        text_color = (THEME["text_dark"] if member["in_clan"]
                      else THEME["text_muted"])
        row = tk.Frame(parent, bg=bg, bd=1, relief="solid")
        row.pack(fill="x")

        existing = self.row_state.get(member["member_id"]) or {}

        # ----- name -----
        f = tk.Frame(row, bg=bg, width=200, height=36)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Label(f, text=member["name"], font=THEME["font_body_bold"],
                 bg=bg, fg=text_color, anchor="w"
                 ).pack(fill="both", expand=True, padx=8)

        # ----- tag -----
        f = tk.Frame(row, bg=bg, width=100, height=36)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Label(f, text=member["member_id"], font=("Consolas", 10),
                 bg=bg, fg=text_color).pack(expand=True)

        # ----- 6 donation entries (3 categories × 2 directions) -----
        # We store StringVars under stable keys: "crops_donated" etc.
        donation_vars = {}
        for cat in DONATION_CATEGORIES:
            for direction in ("donated", "requested"):
                key = f"{cat}_{direction}"
                if key in existing:
                    default = existing[key].get()
                elif prefill is not None and prefill.get(key) is not None:
                    default = str(prefill[key])
                else:
                    default = ""
                var = tk.StringVar(value=default)
                donation_vars[key] = var
                cell = tk.Frame(row, bg=bg, width=80, height=36)
                cell.pack(side="left")
                cell.pack_propagate(False)
                tk.Entry(cell, textvariable=var, width=6,
                         font=THEME["font_body"], relief="solid", bd=1,
                         justify="center"
                         ).pack(expand=True, padx=4, pady=4)

        # ----- comment -----
        if "comment" in existing:
            comment_default = existing["comment"].get()
        elif prefill is not None:
            comment_default = prefill.get("member_comment", "")
        else:
            comment_default = ""
        var_comment = tk.StringVar(value=comment_default)
        f = tk.Frame(row, bg=bg, width=200, height=36)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Entry(f, textvariable=var_comment,
                 font=THEME["font_body"], relief="solid", bd=1
                 ).pack(expand=True, fill="x", padx=4, pady=4)

        # store all donation vars + comment in row_state
        state = dict(donation_vars)
        state["comment"] = var_comment
        # no derby_widgets for donation rows - the toggle should ignore them
        state["derby_widgets"] = []
        self.row_state[member["member_id"]] = state

    def _goto_step1(self):
        # snapshot the user-typed StringVars to plain strings before destroying
        # the step-2 widgets - otherwise re-entering step 2 would lose typing
        self._snapshot_row_state_strings()
        self.step = 1
        self._render()

    def _snapshot_row_state_strings(self):
        """Convert tk variables to a serializable form so they survive
        widget destruction. We store a tiny shim object that mimics .get()
        until it's replaced by a fresh StringVar in the next render."""
        class _StringHolder:
            def __init__(self, value):
                self._v = value
            def get(self):
                return self._v
        # all the keys we know about in the various row state shapes
        donation_keys = []
        for cat in DONATION_CATEGORIES:
            donation_keys.append(f"{cat}_donated")
            donation_keys.append(f"{cat}_requested")
        all_keys = ["level", "tasks", "tasks_max", "points",
                    "comment", "fate"] + donation_keys
        for mid, st in list(self.row_state.items()):
            try:
                new_st = {}
                for key in all_keys:
                    if key in st:
                        new_st[key] = _StringHolder(st[key].get())
                if "participated" in st:
                    new_st["participated"] = _StringHolder(
                        bool(st["participated"].get()))
                self.row_state[mid] = new_st
            except tk.TclError:
                pass

    def _toggle_derby_fields(self):
        is_after = self.var_type.get() == SNAPSHOT_TYPE_AFTER_DERBY
        for mid, st in self.row_state.items():
            for w in st.get("derby_widgets", []):
                try:
                    w.config(state="normal" if is_after else "disabled")
                except tk.TclError:
                    pass

    def _on_type_change(self):
        """Called when the user picks After-Derby / Quick / Donations.
        After-Derby <-> Quick keep the same column layout, so we just
        re-enable/disable the derby fields. Switching to or from
        Donations needs a full re-render because the columns change.
        """
        new_type = self.var_type.get()
        if new_type == SNAPSHOT_TYPE_DONATIONS or self._last_rendered_type == SNAPSHOT_TYPE_DONATIONS:
            # full re-render
            self._snapshot_row_state_strings()
            self._render()
            return
        # safe inline toggle for derby <-> quick
        self._toggle_derby_fields()
        self._update_comment_label()

    def _update_comment_label(self):
        if not hasattr(self, "_comment_label"):
            return
        try:
            if self.var_type.get() == SNAPSHOT_TYPE_DONATIONS:
                self._comment_label.config(text="Comment (optional):")
            else:
                self._comment_label.config(text="Derby comment (optional):")
        except tk.TclError:
            pass

    # =================================================================
    # SAVE
    # =================================================================
    def _save(self):
        snapshot_type = self.var_type.get()
        snap_date = self.var_date.get().strip()
        if not snap_date:
            messagebox.showerror("Invalid", "Snapshot date is required.")
            return

        entries = []
        errors = []
        for member_id, st in self.row_state.items():
            if not self.selected.get(member_id):
                continue  # not selected on step 1

            entry = {"member_id": member_id}

            if snapshot_type == SNAPSHOT_TYPE_DONATIONS:
                # Donations have no level / derby / fate, just 6 numeric
                # category fields and an optional comment.
                bad = False
                for cat in DONATION_CATEGORIES:
                    for direction in ("donated", "requested"):
                        key = f"{cat}_{direction}"
                        try:
                            raw = st[key].get().strip() if key in st else ""
                            val = int(raw) if raw else 0
                            if val < 0:
                                errors.append(
                                    f"{key} cannot be negative for {member_id}")
                                bad = True
                                break
                            entry[key] = val
                        except (ValueError, KeyError):
                            errors.append(
                                f"{key} not a number for {member_id}")
                            bad = True
                            break
                    if bad:
                        break
                if bad:
                    continue
                comment = (st["comment"].get().strip()
                           if "comment" in st else "")
                if comment:
                    entry["member_comment"] = comment
            else:
                # After-Derby + Quick: level required, plus derby fields
                try:
                    level_str = st["level"].get().strip()
                    if not level_str:
                        errors.append(f"Level missing for {member_id}")
                        continue
                    entry["level"] = int(level_str)
                except ValueError:
                    errors.append(f"Level not a number for {member_id}")
                    continue

                comment = st["comment"].get().strip()
                if comment:
                    entry["member_comment"] = comment

                fate = st["fate"].get()
                if fate:
                    entry["fate"] = fate

                if snapshot_type == SNAPSHOT_TYPE_AFTER_DERBY:
                    participated = bool(st["participated"].get())
                    entry["derby_participated"] = participated
                    if participated:
                        try:
                            entry["tasks_done"] = int(st["tasks"].get() or 0)
                        except ValueError:
                            errors.append(f"Tasks not a number for {member_id}")
                            continue
                        try:
                            entry["tasks_max"] = int(st["tasks_max"].get() or 12)
                        except ValueError:
                            errors.append(f"Tasks max not a number for {member_id}")
                            continue
                        try:
                            entry["derby_points"] = int(st["points"].get() or 0)
                        except ValueError:
                            errors.append(f"Points not a number for {member_id}")
                            continue
                    else:
                        entry["tasks_done"] = 0
                        entry["tasks_max"] = int(st["tasks_max"].get() or 12)
                        entry["derby_points"] = 0

            entries.append(entry)

        if errors:
            messagebox.showerror("Cannot save",
                                 "Fix these issues:\n" + "\n".join(errors[:10]))
            return

        if not entries:
            messagebox.showerror(
                "Cannot save",
                "No members were selected. Go back to step 1 to pick some."
            )
            return

        snapshot = {
            "snapshot_id": (self.prefill["snapshot_id"] if self.is_editing
                            else new_snapshot_id()),
            "date": snap_date,
            "type": snapshot_type,
            # We keep the field name "derby_comment" for backward compat,
            # but it serves as a generic header comment for Donations too.
            "derby_comment": self.var_derby_comment.get().strip(),
            "entries": entries,
        }

        if self.is_editing:
            update_snapshot(self.data, self.prefill["snapshot_id"], snapshot)
            self.manager.save_data(self.data)
            messagebox.showinfo("Saved",
                                f"Snapshot updated ({len(entries)} entries).")
            self.manager.show_tab("Snapshots")
        else:
            add_snapshot(self.data, snapshot)
            self.manager.save_data(self.data)
            messagebox.showinfo(
                "Saved",
                f"Snapshot for {snap_date} created with {len(entries)} entries."
            )
            self.manager.show_tab("Snapshots")
