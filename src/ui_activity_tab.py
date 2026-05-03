"""
Activity tab.

Shows the activity-score leaderboard for the in-clan members, with each
row optionally expandable to a per-category breakdown. The leader can
award manual bonuses (with a required comment) here too.

Score logic lives in activity_score.compute_scores().
"""

import tkinter as tk
from tkinter import messagebox

from theme import THEME, ROLE_COLORS, ROLE_LABELS, ROLE_ROW_TINTS, ROLE_MEMBER
from widgets import RoundedButton, LabeledEntry
from ui_widgets_extra import SearchBox, attach_smooth_mousewheel
from neighborhood_manager import (
    add_manual_activity_bonus, delete_manual_activity_bonus,
    manual_activity_bonuses_for_member,
    get_ui_pref, set_ui_pref,
)
from activity_score import (
    compute_scores, ACTIVITY_CATEGORIES,
)


class ActivityTab(tk.Frame):
    def __init__(self, parent, manager):
        super().__init__(parent, bg=THEME["bg_main"])
        self.manager = manager
        self.data = manager.reload_data()

        self.search_query = ""
        self.show_former = bool(get_ui_pref(self.data, "activity.show_former",
                                              False))
        # rows that are expanded to show breakdown
        self.expanded = set()

        self._build_toolbar()
        self._build_filter_bar()
        self._build_list_container()
        self._render_rows()

    # ---- toolbar --------------------------------------------------------
    def _build_toolbar(self):
        bar = tk.Frame(self, bg=THEME["bg_main"])
        bar.pack(side="top", fill="x", padx=20, pady=(10, 6))

        tk.Label(bar, text="Activity score leaderboard",
                 font=THEME["font_subheading"],
                 bg=THEME["bg_main"], fg=THEME["text_dark"]
                 ).pack(side="left")

        RoundedButton(bar, text="+ Award manual bonus",
                      command=self._award_bonus_dialog,
                      width=200, height=40,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="right")

    def _build_filter_bar(self):
        bar = tk.Frame(self, bg=THEME["bg_panel"], bd=1, relief="ridge")
        bar.pack(side="top", fill="x", padx=20, pady=(0, 6))

        SearchBox(bar,
                  on_change=self._on_search_change,
                  placeholder="Search by name or tag…",
                  width=22,
                  bg=THEME["bg_panel"]
                  ).pack(side="left", padx=(8, 12), pady=8)

        self.var_show_former = tk.BooleanVar(value=self.show_former)
        tk.Checkbutton(bar, text="Show former members",
                       variable=self.var_show_former,
                       command=self._on_former_toggle,
                       font=THEME["font_body_bold"],
                       bg=THEME["bg_panel"], fg=THEME["text_dark"],
                       activebackground=THEME["bg_panel"],
                       selectcolor=THEME["bg_card"]
                       ).pack(side="right", padx=12, pady=8)

        # explanation row
        info = tk.Frame(self, bg=THEME["bg_main"])
        info.pack(side="top", fill="x", padx=20, pady=(0, 4))
        tk.Label(info,
                 text=("Scoring per category: rank 1 → 5 pts, "
                       "ranks 2-6 → 3 pts, ranks 7-15 → 2 pts, "
                       "16+ → 1 pt, no data → 0. Manual bonuses add "
                       "directly to the total."),
                 font=("Arial", 9, "italic"),
                 bg=THEME["bg_main"], fg=THEME["text_muted"], anchor="w"
                 ).pack(side="left")

    def _on_search_change(self, query):
        self.search_query = query.strip().lower()
        self._render_rows()

    def _on_former_toggle(self):
        self.show_former = self.var_show_former.get()
        set_ui_pref(self.data, "activity.show_former", self.show_former)
        self.manager.save_data(self.data)
        self._render_rows()

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

    def _render_rows(self):
        for child in self._list_body.winfo_children():
            child.destroy()

        rows = compute_scores(self.data, include_former=self.show_former)

        # apply search filter
        q = self.search_query
        if q:
            rows = [r for r in rows
                    if q in r["name"].lower()
                    or q in r["member_id"].lower()]

        if not rows:
            tk.Label(self._list_body,
                     text="No members match the current filters.",
                     font=THEME["font_body"], bg=THEME["bg_main"],
                     fg=THEME["text_muted"]).pack(pady=40)
            return

        # column headers
        header = tk.Frame(self._list_body, bg=THEME["bg_top"], bd=1,
                           relief="solid")
        header.pack(fill="x")
        for label, w in [("#", 40), ("Name", 220), ("Tag", 100),
                          ("Role", 100), ("Score", 80),
                          ("Breakdown", 700)]:
            f = tk.Frame(header, bg=THEME["bg_top"], width=w, height=28)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Label(f, text=label, font=THEME["font_body_bold"],
                     bg=THEME["bg_top"], fg=THEME["text_dark"]
                     ).pack(expand=True)

        for i, row in enumerate(rows, start=1):
            self._render_row(row, rank=i, alt=(i % 2 == 0))

        # per-category leaderboards (collapsible)
        self._render_category_leaderboards(rows)

    def _render_category_leaderboards(self, all_rows):
        """Below the main score leaderboard, show one collapsible section
        per metric (Derby completion, Levels gained, etc.) with the top 5
        members ranked by that single metric. Useful for digging into who
        is leading in each category, beyond just the combined total."""
        from ui_widgets_extra import CollapsibleSection

        # spacing
        tk.Frame(self._list_body, bg=THEME["bg_main"], height=12).pack()

        tk.Label(self._list_body, text="Per-category leaderboards",
                 font=THEME["font_subheading"],
                 bg=THEME["bg_main"], fg=THEME["text_dark"]
                 ).pack(anchor="w", pady=(8, 4))
        tk.Label(self._list_body,
                 text=("Each section ranks the clan by a single metric. "
                       "Click to expand."),
                 font=("Arial", 10, "italic"),
                 bg=THEME["bg_main"], fg=THEME["text_muted"]
                 ).pack(anchor="w", pady=(0, 8))

        for cat_key, cat_label in ACTIVITY_CATEGORIES:
            sect = CollapsibleSection(
                self._list_body,
                title=f"Top members — {cat_label}",
                initial_open=False,
                on_first_open=(lambda body, ck=cat_key:
                                self._render_category_top(body, ck, all_rows)))
            sect.pack(fill="x", pady=2)

    def _render_category_top(self, parent, cat_key, all_rows):
        """Render the top members for one specific metric.

        For derby_completion / derby_part / levels_gained / donations:
          rank by raw value, descending. Show value + points awarded.
        For manual:
          rank by total manual points awarded (could be negative).
        """
        # extract (member, raw value, points) tuples
        ranked = []
        for r in all_rows:
            cat_info = r["categories"].get(cat_key, {})
            value = cat_info.get("value")
            pts = cat_info.get("points", 0)
            # for ranked categories, skip those with no data
            if cat_key != "manual" and value is None:
                continue
            # for manual, skip those with 0 points (they're not interesting)
            if cat_key == "manual" and (value is None or value == 0):
                continue
            ranked.append((r, value, pts))

        if not ranked:
            tk.Label(parent, text=f"No data for {cat_key} yet.",
                     font=THEME["font_body"], bg=THEME["bg_panel"],
                     fg=THEME["text_muted"]).pack(padx=10, pady=10)
            return

        # sort. For most categories higher is better; manual is also "higher
        # is better" but values can be negative.
        ranked.sort(key=lambda t: -float(t[1]))

        # show top 30 - cover the full clan even with former members visible
        top = ranked[:30]

        # mini header
        wrap = tk.Frame(parent, bg=THEME["bg_panel"])
        wrap.pack(fill="x", padx=10, pady=(6, 8))

        header = tk.Frame(wrap, bg=THEME["bg_top"])
        header.pack(fill="x")
        for label, w in [("#", 40), ("Name", 220), ("Tag", 100),
                          ("Value", 220), ("Points", 80)]:
            f = tk.Frame(header, bg=THEME["bg_top"], width=w, height=24)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Label(f, text=label, font=THEME["font_body_bold"],
                     bg=THEME["bg_top"], fg=THEME["text_dark"]
                     ).pack(expand=True)

        for i, (r, value, pts) in enumerate(top, start=1):
            row_bg = THEME["bg_card"] if i % 2 == 1 else "#FFFAEC"
            line = tk.Frame(wrap, bg=row_bg, bd=1, relief="solid")
            line.pack(fill="x")

            def cell(parent, text, width, anchor="center", fg=None,
                     font=("Arial", 10, "bold")):
                f = tk.Frame(parent, bg=row_bg, width=width, height=22)
                f.pack(side="left")
                f.pack_propagate(False)
                tk.Label(f, text=text, font=font, bg=row_bg,
                         fg=fg or THEME["text_dark"], anchor=anchor
                         ).pack(fill="both", expand=True, padx=6)

            cell(line, f"#{i}", 40, fg=THEME["btn_blue"])
            cell(line, r["name"], 220, anchor="w")
            cell(line, r["member_id"], 100, font=("Consolas", 9),
                 fg=THEME["text_muted"])

            # format value per category
            if cat_key == "derby_completion":
                value_str = f"{value*100:.0f}%"
            elif cat_key == "derby_part":
                value_str = f"{value*100:.0f}%"
            elif cat_key == "levels_gained":
                value_str = f"{int(value)} levels (last 30 days)"
            elif cat_key == "donations":
                value_str = f"{int(value):,} donated (last 4 weeks)"
            elif cat_key == "manual":
                value_str = (f"+{int(value)} pts"
                             if value > 0 else f"{int(value)} pts")
            else:
                value_str = str(value)
            cell(line, value_str, 220)

            pts_str = f"+{pts}" if pts >= 0 else str(pts)
            pts_color = (THEME["btn_green"] if pts > 0
                         else THEME["btn_red"] if pts < 0
                         else THEME["text_muted"])
            cell(line, pts_str, 80, fg=pts_color)

    def _render_row(self, row, rank, alt):
        mid = row["member_id"]
        in_clan = row["in_clan"]
        role = row.get("role", ROLE_MEMBER)

        # bg: role tint for in-clan, alternating otherwise
        if in_clan:
            tint = ROLE_ROW_TINTS.get(role)
            bg = tint if tint else (THEME["bg_card"] if alt
                                     else THEME["bg_panel"])
        else:
            bg = THEME["bg_card"] if alt else THEME["bg_panel"]

        text_color = THEME["text_dark"] if in_clan else THEME["text_muted"]

        # ----- main row -----
        rwrap = tk.Frame(self._list_body, bg=THEME["bg_main"])
        rwrap.pack(fill="x", pady=0)

        main = tk.Frame(rwrap, bg=bg, bd=1, relief="solid", cursor="hand2")
        main.pack(fill="x")

        # rank
        f = tk.Frame(main, bg=bg, width=40, height=44)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Label(f, text=f"#{rank}", font=("Arial Black", 12, "bold"),
                 bg=bg, fg=text_color).pack(expand=True)

        # name
        f = tk.Frame(main, bg=bg, width=220, height=44)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Label(f, text=row["name"], font=THEME["font_body_bold"],
                 bg=bg, fg=text_color, anchor="w"
                 ).pack(fill="both", expand=True, padx=8)

        # tag
        f = tk.Frame(main, bg=bg, width=100, height=44)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Label(f, text=mid, font=("Consolas", 10),
                 bg=bg, fg=text_color).pack(expand=True)

        # role chip
        role_color = ROLE_COLORS.get(role, ROLE_COLORS[ROLE_MEMBER])
        role_label = ROLE_LABELS.get(role, ROLE_LABELS[ROLE_MEMBER])
        f = tk.Frame(main, bg=bg, width=100, height=44)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Label(f, text=f"  {role_label}  ",
                 font=("Arial", 10, "bold"),
                 bg=role_color, fg=THEME["text_light"], padx=4, pady=2
                 ).pack(expand=True)

        # score
        f = tk.Frame(main, bg=bg, width=80, height=44)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Label(f, text=str(row["total"]),
                 font=("Arial Black", 16, "bold"),
                 bg=bg, fg=THEME["text_dark"]
                 ).pack(expand=True)

        # breakdown chips (small per-category pills)
        f = tk.Frame(main, bg=bg, width=700, height=44)
        f.pack(side="left")
        f.pack_propagate(False)
        self._render_breakdown_chips(f, row, bg)

        # toggle expanded on click of the main row (NOT on the breakdown chips
        # which are info only — but the child labels in the main row should
        # all toggle, too, so the user can click anywhere on the row)
        chev = "▼" if mid in self.expanded else "▶"
        chev_label = tk.Label(main, text=chev,
                               font=("Arial", 11, "bold"),
                               bg=bg, fg=text_color)
        chev_label.pack(side="right", padx=10)

        def on_click(_e, m=mid):
            self._toggle(m)

        # bind every label and frame in the main row, recursively, so
        # a click anywhere on the row (except on inner buttons) toggles it.
        def _bind_recursive(widget):
            try:
                widget.configure(cursor="hand2")
            except tk.TclError:
                pass
            widget.bind("<Button-1>", on_click)
            for child in widget.winfo_children():
                _bind_recursive(child)
        _bind_recursive(main)

        # ----- expanded body if open -----
        if mid in self.expanded:
            self._render_expanded(rwrap, row)

    def _render_breakdown_chips(self, parent, row, bg):
        """Compact one-line summary of category points."""
        # Render tiny "label: pts" pills
        for cat_key, label in ACTIVITY_CATEGORIES:
            info = row["categories"].get(cat_key, {})
            pts = info.get("points", 0)
            short_label = {
                "derby_completion": "DerbyDone",
                "derby_part":       "DerbyPart",
                "levels_gained":    "Levels",
                "donations":        "Don.",
                "manual":           "Manual",
            }.get(cat_key, label)
            if pts > 0:
                color = THEME["btn_green"]
                fg = "white"
            elif pts < 0:
                color = THEME["btn_red"]
                fg = "white"
            else:
                color = THEME["btn_disabled"]
                fg = THEME["text_muted"]
            tk.Label(parent, text=f" {short_label} +{pts} "
                                   if pts >= 0 else f" {short_label} {pts} ",
                     font=("Arial", 9, "bold"),
                     bg=color, fg=fg, padx=4, pady=2
                     ).pack(side="left", padx=2, pady=8)

    def _render_expanded(self, parent, row):
        """Detailed table of category → value, rank, points."""
        body = tk.Frame(parent, bg=THEME["bg_card"], bd=1, relief="solid")
        body.pack(fill="x", pady=(0, 6))

        # category header
        header = tk.Frame(body, bg=THEME["bg_top"])
        header.pack(fill="x")
        for label, w in [("Category", 220), ("Value", 200),
                          ("Rank", 80), ("Points", 80)]:
            f = tk.Frame(header, bg=THEME["bg_top"], width=w, height=22)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Label(f, text=label, font=THEME["font_body_bold"],
                     bg=THEME["bg_top"], fg=THEME["text_dark"]
                     ).pack(expand=True)

        # category rows
        for cat_key, label in ACTIVITY_CATEGORIES:
            info = row["categories"].get(cat_key, {})
            value = info.get("value")
            rank = info.get("rank")
            pts = info.get("points", 0)

            line = tk.Frame(body, bg=THEME["bg_card"])
            line.pack(fill="x")

            def cell(parent, text, width, anchor="center", fg=None):
                f = tk.Frame(parent, bg=THEME["bg_card"], width=width,
                             height=22)
                f.pack(side="left")
                f.pack_propagate(False)
                tk.Label(f, text=text,
                         font=("Arial", 10, "bold"),
                         bg=THEME["bg_card"],
                         fg=fg or THEME["text_dark"],
                         anchor=anchor
                         ).pack(fill="both", expand=True, padx=6)

            cell(line, label, 220, anchor="w")
            # value formatting
            if cat_key == "derby_completion" and value is not None:
                value_str = f"{value*100:.0f}%"
            elif cat_key == "derby_part" and value is not None:
                value_str = f"{value*100:.0f}%"
            elif cat_key == "levels_gained" and value is not None:
                value_str = f"{int(value)} levels (30d)"
            elif cat_key == "donations" and value is not None:
                value_str = f"{int(value)} donated (recent)"
            elif cat_key == "manual":
                bonuses = manual_activity_bonuses_for_member(self.data,
                                                              row["member_id"])
                value_str = f"{len(bonuses)} bonus(es)"
            elif value is None:
                value_str = "no data"
            else:
                value_str = str(value)
            cell(line, value_str, 200, fg=THEME["text_muted"]
                                       if value is None else None)
            cell(line, "—" if rank is None else f"#{rank}", 80)
            cell(line, f"+{pts}" if pts >= 0 else str(pts), 80,
                 fg=THEME["btn_green"] if pts > 0
                    else THEME["btn_red"] if pts < 0
                    else THEME["text_muted"])

        # show manual bonus list with delete buttons
        bonuses = manual_activity_bonuses_for_member(self.data,
                                                     row["member_id"])
        if bonuses:
            tk.Label(body, text="Manual bonuses:",
                     font=THEME["font_body_bold"],
                     bg=THEME["bg_card"], fg=THEME["text_dark"]
                     ).pack(anchor="w", padx=10, pady=(8, 2))
            for b in bonuses:
                bline = tk.Frame(body, bg=THEME["bg_card"])
                bline.pack(fill="x", padx=10, pady=1)
                pts = b.get("points", 0)
                pts_str = f"+{pts}" if pts >= 0 else str(pts)
                pts_color = (THEME["btn_green"] if pts > 0
                             else THEME["btn_red"] if pts < 0
                             else THEME["text_muted"])
                tk.Label(bline, text=pts_str,
                         font=("Arial Black", 11, "bold"),
                         bg=THEME["bg_card"], fg=pts_color, width=5
                         ).pack(side="left")
                tk.Label(bline,
                         text=b.get("comment", ""),
                         font=THEME["font_body"],
                         bg=THEME["bg_card"], fg=THEME["text_dark"],
                         anchor="w"
                         ).pack(side="left", padx=8, fill="x", expand=True)
                tk.Label(bline,
                         text=b.get("created_at", "")[:10],
                         font=("Arial", 9),
                         bg=THEME["bg_card"], fg=THEME["text_muted"]
                         ).pack(side="right", padx=8)
                RoundedButton(bline, text="✕",
                              command=lambda bid=b["id"]:
                                          self._delete_bonus(bid),
                              width=30, height=22,
                              bg_color=THEME["btn_red"],
                              hover_color=THEME["btn_red_hover"],
                              font=("Arial", 9, "bold"), radius=6
                              ).pack(side="right", padx=2)

    def _toggle(self, member_id):
        if member_id in self.expanded:
            self.expanded.remove(member_id)
        else:
            self.expanded.add(member_id)
        self._render_rows()

    # ---- bonus management ----------------------------------------------
    def _award_bonus_dialog(self):
        AwardBonusDialog(self.manager, on_done=self._on_bonus_added)

    def _on_bonus_added(self):
        self.data = self.manager.reload_data()
        self._render_rows()

    def _delete_bonus(self, bonus_id):
        if not messagebox.askyesno(
                "Delete bonus",
                "Delete this manual activity bonus?"):
            return
        delete_manual_activity_bonus(self.data, bonus_id)
        self.manager.save_data(self.data)
        self.data = self.manager.reload_data()
        self._render_rows()


# ===================================================================
# Award bonus dialog
# ===================================================================

class AwardBonusDialog(tk.Toplevel):
    """Dialog for awarding a manual activity bonus to a member."""

    def __init__(self, manager, on_done):
        super().__init__(manager)
        self.manager = manager
        self.on_done = on_done
        self.data = manager.reload_data()

        self.title("Award manual bonus")
        self.configure(bg=THEME["bg_main"])
        self.resizable(False, False)
        self.transient(manager)
        self.grab_set()

        body = tk.Frame(self, bg=THEME["bg_panel"], padx=20, pady=20)
        body.pack(padx=10, pady=10)

        tk.Label(body, text="Award activity points to a member",
                 font=THEME["font_subheading"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(pady=(0, 10))

        # member picker
        tk.Label(body, text="Member",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(anchor="w")
        in_clan_members = [(mid, m["name"]) for mid, m
                            in self.data["members"].items()
                            if m.get("in_clan")]
        in_clan_members.sort(key=lambda t: t[1].lower())
        if not in_clan_members:
            tk.Label(body, text="No members to award.",
                     font=THEME["font_body"], bg=THEME["bg_panel"],
                     fg=THEME["text_muted"]).pack()
            RoundedButton(body, text="Close",
                          command=self.destroy,
                          width=120, height=40,
                          bg_color=THEME["btn_grey"],
                          hover_color=THEME["btn_grey_hover"]
                          ).pack(pady=10)
            return

        self._member_choices = in_clan_members
        self.var_member_label = tk.StringVar(
            value=f"{in_clan_members[0][1]}  ({in_clan_members[0][0]})")
        choice_strings = [f"{n}  ({mid})" for mid, n in in_clan_members]
        om = tk.OptionMenu(body, self.var_member_label, *choice_strings)
        om.config(font=THEME["font_body"], bg=THEME["bg_panel"])
        om.pack(fill="x", pady=4)

        # points
        self.entry_points = LabeledEntry(body, "Points (positive or negative)",
                                          default="1", width=10)
        self.entry_points.pack(fill="x", pady=4)

        # comment
        tk.Label(body, text="Comment (required, why?)",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(anchor="w", pady=(8, 0))
        self.txt_comment = tk.Text(body, height=4, width=44,
                                    font=THEME["font_body"],
                                    relief="solid", bd=1)
        self.txt_comment.pack(fill="x", pady=4)

        # buttons
        btns = tk.Frame(body, bg=THEME["bg_panel"])
        btns.pack(pady=(15, 0))
        RoundedButton(btns, text="Award",
                      command=self._award,
                      width=120, height=40,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="left", padx=6)
        RoundedButton(btns, text="Cancel",
                      command=self.destroy,
                      width=120, height=40,
                      bg_color=THEME["btn_grey"],
                      hover_color=THEME["btn_grey_hover"]
                      ).pack(side="left", padx=6)

        # center
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_reqwidth()) // 2
        y = (self.winfo_screenheight() - self.winfo_reqheight()) // 2
        self.geometry(f"+{x}+{y}")

    def _award(self):
        # parse inputs
        choice = self.var_member_label.get()
        # find the member_id corresponding to this label
        mid = None
        for cmid, cname in self._member_choices:
            label = f"{cname}  ({cmid})"
            if label == choice:
                mid = cmid
                break
        if mid is None:
            messagebox.showerror("Invalid", "Pick a member.", parent=self)
            return

        try:
            pts = int(self.entry_points.get().strip())
        except ValueError:
            messagebox.showerror("Invalid",
                                  "Points must be an integer (positive or "
                                  "negative).", parent=self)
            return

        comment = self.txt_comment.get("1.0", tk.END).strip()
        if not comment:
            messagebox.showerror("Invalid",
                                  "A comment is required for manual bonuses.",
                                  parent=self)
            return

        try:
            add_manual_activity_bonus(self.data, mid, pts, comment)
        except ValueError as e:
            messagebox.showerror("Cannot save", str(e), parent=self)
            return
        self.manager.save_data(self.data)
        self.destroy()
        self.on_done()
