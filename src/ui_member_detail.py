"""
Member detail screen.

Shows everything the leader knows about one member:
  - Header: name, tag, joined date, current level, in-clan flag, latest fate,
            and an activity-status badge
  - Level progression chart (matplotlib, embedded in tk)
  - Derby points chart (only after-derby snapshots)
  - Derby statistics (participation rate, avg tasks, avg points)
  - Notes editor (saves directly from this screen)
  - Snapshot history table
  - Name history (if the member was renamed)
"""

import tkinter as tk
from tkinter import messagebox
from datetime import datetime

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates

from theme import (
    THEME, ACTIVITY_STATUS_COLORS,
    ROLE_COLORS, ROLE_LABELS, ROLE_MEMBER,
)
from widgets import RoundedButton
from ui_widgets_extra import CollapsibleSection
from neighborhood_manager import (
    update_member, latest_levels, latest_fate_for_member,
    SNAPSHOT_TYPE_AFTER_DERBY, SNAPSHOT_TYPE_QUICK, SNAPSHOT_TYPE_DONATIONS,
    DONATION_CATEGORIES,
    ACTIVITY_NEW_MEMBER, ACTIVITY_INACTIVE, ACTIVITY_BELOW_TARGET,
    ACTIVITY_MEETING_TARGET, ACTIVITY_NO_RULE,
    manual_activity_bonuses_for_member,
)
from clan_stats import (
    member_history, member_level_progression, member_derby_history,
    member_derby_participation_rate, member_avg_tasks, member_avg_points,
    member_avg_task_completion, member_total_points, member_total_tasks,
    member_activity_status,
    member_donations_avg, member_donations_total, member_donation_history,
)
from activity_score import get_member_score, ACTIVITY_CATEGORIES


# Maps activity status to (display label, color hex)
ACTIVITY_LABELS = {
    ACTIVITY_NEW_MEMBER:     ("New member",   ACTIVITY_STATUS_COLORS["new"]),
    ACTIVITY_INACTIVE:       ("Inactive",     ACTIVITY_STATUS_COLORS["inactive"]),
    ACTIVITY_BELOW_TARGET:   ("Below target", ACTIVITY_STATUS_COLORS["below"]),
    ACTIVITY_MEETING_TARGET: ("On track",     ACTIVITY_STATUS_COLORS["meeting"]),
    ACTIVITY_NO_RULE:        ("No rule",      ACTIVITY_STATUS_COLORS["no_rule"]),
}

FATE_COLORS = {
    "stay":    THEME["text_ok"],
    "warning": ACTIVITY_STATUS_COLORS["below"],
    "kick":    THEME["text_warning"],
}


class MemberDetailFrame(tk.Frame):
    def __init__(self, parent, app, member_id: str):
        super().__init__(parent, bg=THEME["bg_main"])
        self.app = app
        self.nm = app.neighborhood_manager
        self.member_id = member_id

        clan_name = self.nm.get_active()
        if clan_name is None:
            messagebox.showerror("No neighborhood", "No active neighborhood.")
            self.app.show_frame("MainMenu")
            return
        self.clan_name = clan_name
        self.data = self.nm.load(clan_name)

        if member_id not in self.data["members"]:
            messagebox.showerror("Not found",
                                 f"Member {member_id} not found.")
            self.app.show_frame("NeighborhoodManager")
            return

        self.member = self.data["members"][member_id]

        self._build_top_bar()
        self._build_body()

    # ---- top bar ---------------------------------------------------------
    def _build_top_bar(self):
        top = tk.Frame(self, bg=THEME["bg_top"], height=60)
        top.pack(side="top", fill="x")
        top.pack_propagate(False)

        RoundedButton(top, text="← Back to clan",
                      command=lambda: self.app.show_frame("NeighborhoodManager"),
                      width=160, height=40,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="left", padx=15, pady=10)

        title = f"{self.member['name']}  ({self.member['member_id']})"
        tk.Label(top, text=title, font=THEME["font_title"],
                 bg=THEME["bg_top"], fg=THEME["text_dark"]
                 ).pack(side="left", padx=20)

    # ---- main body -------------------------------------------------------
    def _build_body(self):
        # outer scrollable region - this screen has a lot of content
        wrap = tk.Frame(self, bg=THEME["bg_main"])
        wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(wrap, bg=THEME["bg_main"],
                           highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg=THEME["bg_main"])
        canvas_window = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(canvas_window, width=e.width))
        # smooth scroll
        from ui_widgets_extra import attach_smooth_mousewheel
        attach_smooth_mousewheel(canvas)

        self._build_summary_card(body)
        self._build_activity_score_section(body)
        self._build_donations_section(body)
        self._build_charts(body)
        self._build_derby_stats(body)
        self._build_notes(body)
        self._build_snapshot_history(body)
        self._build_name_history(body)

    # ---- activity score breakdown ---------------------------------------
    def _build_activity_score_section(self, parent):
        try:
            score = get_member_score(self.data, self.member_id)
        except Exception:
            return
        total = score.get("total", 0)
        sect = CollapsibleSection(
            parent,
            title=f"Activity score breakdown — Total: {total} pts",
            initial_open=False)
        sect.pack(fill="x", padx=20, pady=10)
        body = sect.body
        body.configure(padx=10, pady=10)

        # category table
        header = tk.Frame(body, bg=THEME["bg_top"])
        header.pack(fill="x")
        for label, w in [("Category", 240), ("Value", 220),
                          ("Rank", 80), ("Points", 80)]:
            f = tk.Frame(header, bg=THEME["bg_top"], width=w, height=24)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Label(f, text=label, font=THEME["font_body_bold"],
                     bg=THEME["bg_top"], fg=THEME["text_dark"]
                     ).pack(expand=True)

        for cat_key, label in ACTIVITY_CATEGORIES:
            info = score["categories"].get(cat_key, {})
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

            cell(line, label, 240, anchor="w")
            if cat_key == "derby_completion" and value is not None:
                value_str = f"{value*100:.0f}%"
            elif cat_key == "derby_part" and value is not None:
                value_str = f"{value*100:.0f}%"
            elif cat_key == "levels_gained" and value is not None:
                value_str = f"{int(value)} levels (last 30 days)"
            elif cat_key == "donations" and value is not None:
                value_str = f"{int(value)} donated (last 4 weeks)"
            elif cat_key == "manual":
                bonuses = manual_activity_bonuses_for_member(self.data,
                                                              self.member_id)
                value_str = f"{len(bonuses)} bonus(es)"
            elif value is None:
                value_str = "no data"
            else:
                value_str = str(value)
            cell(line, value_str, 220,
                 fg=THEME["text_muted"] if value is None else None)
            cell(line, "—" if rank is None else f"#{rank}", 80)
            cell(line, f"+{pts}" if pts >= 0 else str(pts), 80,
                 fg=THEME["btn_green"] if pts > 0
                    else THEME["btn_red"] if pts < 0
                    else THEME["text_muted"])

        # manual bonus list
        bonuses = manual_activity_bonuses_for_member(self.data,
                                                      self.member_id)
        if bonuses:
            tk.Label(body, text="Manual bonuses awarded:",
                     font=THEME["font_body_bold"],
                     bg=THEME["bg_panel"], fg=THEME["text_dark"]
                     ).pack(anchor="w", pady=(10, 4))
            for b in bonuses:
                bline = tk.Frame(body, bg=THEME["bg_card"])
                bline.pack(fill="x", pady=1)
                pts_str = f"+{b['points']}" if b['points'] >= 0 else str(b['points'])
                pts_color = (THEME["btn_green"] if b['points'] > 0
                             else THEME["btn_red"] if b['points'] < 0
                             else THEME["text_muted"])
                tk.Label(bline, text=pts_str,
                         font=("Arial Black", 11, "bold"),
                         bg=THEME["bg_card"], fg=pts_color, width=5
                         ).pack(side="left")
                tk.Label(bline, text=b.get("comment", ""),
                         font=THEME["font_body"],
                         bg=THEME["bg_card"], fg=THEME["text_dark"],
                         anchor="w"
                         ).pack(side="left", padx=8, fill="x", expand=True)
                tk.Label(bline, text=b.get("created_at", "")[:10],
                         font=("Arial", 9),
                         bg=THEME["bg_card"], fg=THEME["text_muted"]
                         ).pack(side="right", padx=8)

    # ---- donations section ----------------------------------------------
    def _build_donations_section(self, parent):
        # only render if there's any donations data anywhere
        history = member_donation_history(self.data, self.member_id)
        if not history:
            return  # no donations yet, skip silently

        avg = member_donations_avg(self.data, self.member_id)
        total = member_donations_total(self.data, self.member_id)
        n_weeks = avg.get("weeks_counted", 0)

        sect = CollapsibleSection(
            parent,
            title=f"Donations — {n_weeks} week(s) tracked, "
                  f"{total['all_donated']:,} donated / "
                  f"{total['all_requested']:,} requested all-time",
            initial_open=False)
        sect.pack(fill="x", padx=20, pady=10)
        body = sect.body
        body.configure(padx=14, pady=10)

        # weekly average per category
        tk.Label(body, text="Weekly average:",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(anchor="w", pady=(0, 4))

        avg_table = tk.Frame(body, bg=THEME["bg_panel"])
        avg_table.pack(fill="x", pady=(0, 8))
        # header
        header = tk.Frame(avg_table, bg=THEME["bg_top"])
        header.pack(fill="x")
        for label, w in [("Category", 140), ("Avg donated/wk", 140),
                          ("Avg requested/wk", 140)]:
            f = tk.Frame(header, bg=THEME["bg_top"], width=w, height=24)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Label(f, text=label, font=THEME["font_body_bold"],
                     bg=THEME["bg_top"], fg=THEME["text_dark"]
                     ).pack(expand=True)
        # rows
        for cat in DONATION_CATEGORIES:
            line = tk.Frame(avg_table, bg=THEME["bg_card"])
            line.pack(fill="x")
            for text, w in [
                (cat.capitalize(), 140),
                (f"{avg[f'{cat}_donated']:.1f}", 140),
                (f"{avg[f'{cat}_requested']:.1f}", 140),
            ]:
                f = tk.Frame(line, bg=THEME["bg_card"], width=w, height=22)
                f.pack(side="left")
                f.pack_propagate(False)
                tk.Label(f, text=text, font=("Arial", 10, "bold"),
                         bg=THEME["bg_card"], fg=THEME["text_dark"]
                         ).pack(expand=True)

        # all-time totals per category
        tk.Label(body, text="All-time totals:",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(anchor="w", pady=(8, 4))

        tot_table = tk.Frame(body, bg=THEME["bg_panel"])
        tot_table.pack(fill="x")
        header = tk.Frame(tot_table, bg=THEME["bg_top"])
        header.pack(fill="x")
        for label, w in [("Category", 140), ("Total donated", 140),
                          ("Total requested", 140)]:
            f = tk.Frame(header, bg=THEME["bg_top"], width=w, height=24)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Label(f, text=label, font=THEME["font_body_bold"],
                     bg=THEME["bg_top"], fg=THEME["text_dark"]
                     ).pack(expand=True)
        for cat in DONATION_CATEGORIES:
            line = tk.Frame(tot_table, bg=THEME["bg_card"])
            line.pack(fill="x")
            for text, w in [
                (cat.capitalize(), 140),
                (f"{total[f'{cat}_donated']:,}", 140),
                (f"{total[f'{cat}_requested']:,}", 140),
            ]:
                f = tk.Frame(line, bg=THEME["bg_card"], width=w, height=22)
                f.pack(side="left")
                f.pack_propagate(False)
                tk.Label(f, text=text, font=("Arial", 10, "bold"),
                         bg=THEME["bg_card"], fg=THEME["text_dark"]
                         ).pack(expand=True)
        # combined total row
        line = tk.Frame(tot_table, bg=THEME["bg_top"])
        line.pack(fill="x")
        for text, w in [
            ("All categories", 140),
            (f"{total['all_donated']:,}", 140),
            (f"{total['all_requested']:,}", 140),
        ]:
            f = tk.Frame(line, bg=THEME["bg_top"], width=w, height=24)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Label(f, text=text, font=THEME["font_body_bold"],
                     bg=THEME["bg_top"], fg=THEME["text_dark"]
                     ).pack(expand=True)

    # ---- summary card ----------------------------------------------------
    def _build_summary_card(self, parent):
        card = tk.LabelFrame(parent, text=" Overview ",
                             font=THEME["font_subheading"],
                             bg=THEME["bg_panel"], fg=THEME["text_dark"],
                             bd=2, relief="ridge", padx=14, pady=10)
        card.pack(fill="x", padx=20, pady=(15, 10))

        # left: facts; right: status badges
        cols = tk.Frame(card, bg=THEME["bg_panel"])
        cols.pack(fill="x")
        cols.grid_columnconfigure(0, weight=1)
        cols.grid_columnconfigure(1, weight=1)

        # left column - facts
        left = tk.Frame(cols, bg=THEME["bg_panel"])
        left.grid(row=0, column=0, sticky="nsew")

        levels = latest_levels(self.data)
        cur_lvl = levels.get(self.member_id)
        cur_lvl_str = str(cur_lvl) if cur_lvl is not None else "—"

        joined = self.member.get("joined_date") or "—"
        left_date = self.member.get("left_date")
        in_clan = self.member.get("in_clan", False)

        facts = [
            ("Current level", cur_lvl_str, THEME["font_count"]),
            ("Player tag", self.member["member_id"], ("Consolas", 11, "bold")),
            ("Joined", joined, THEME["font_body"]),
        ]
        if not in_clan and left_date:
            facts.append(("Left clan", left_date, THEME["font_body"]))

        for label, val, font in facts:
            row = tk.Frame(left, bg=THEME["bg_panel"])
            row.pack(anchor="w", pady=2)
            tk.Label(row, text=f"{label}: ", font=THEME["font_body_bold"],
                     bg=THEME["bg_panel"], fg=THEME["text_dark"]
                     ).pack(side="left")
            tk.Label(row, text=str(val), font=font,
                     bg=THEME["bg_panel"], fg=THEME["text_dark"]
                     ).pack(side="left")

        # right column - badges
        right = tk.Frame(cols, bg=THEME["bg_panel"])
        right.grid(row=0, column=1, sticky="nse")

        # role chip (top of right column)
        role = self.member.get("role", ROLE_MEMBER)
        role_color = ROLE_COLORS.get(role, ROLE_COLORS[ROLE_MEMBER])
        role_label = ROLE_LABELS.get(role, ROLE_LABELS[ROLE_MEMBER])
        tk.Label(right, text=f"  Role: {role_label}  ",
                 font=THEME["font_body_bold"],
                 bg=role_color, fg=THEME["text_light"], padx=10, pady=4
                 ).pack(side="top", anchor="e", pady=2)

        # activity score
        try:
            score_info = get_member_score(self.data, self.member_id)
            score_total = score_info.get("total", 0)
        except Exception:
            score_total = 0
        tk.Label(right, text=f"  Score: {score_total} pts  ",
                 font=THEME["font_body_bold"],
                 bg=THEME["btn_blue"], fg=THEME["text_light"],
                 padx=10, pady=4
                 ).pack(side="top", anchor="e", pady=2)

        # in-clan badge
        in_clan_text = "✓ In clan" if in_clan else "Not in clan"
        in_clan_color = THEME["btn_green"] if in_clan else THEME["btn_grey"]
        tk.Label(right, text=f"  {in_clan_text}  ",
                 font=THEME["font_body_bold"],
                 bg=in_clan_color, fg=THEME["text_light"], padx=10, pady=4
                 ).pack(side="top", anchor="e", pady=2)

        # activity status badge
        info = member_activity_status(self.data, self.member_id)
        label, color_hex = ACTIVITY_LABELS.get(info["status"],
                                                ("Unknown",
                                                 ACTIVITY_STATUS_COLORS["new"]))
        # add detail to the badge if relevant
        detail = ""
        if info["status"] in (ACTIVITY_INACTIVE, ACTIVITY_BELOW_TARGET,
                              ACTIVITY_MEETING_TARGET):
            gained = info.get("levels_gained", 0)
            target = info.get("target", 0)
            days = info.get("days_covered", 0)
            detail = f"   ({gained}/{target} levels in {days}d)"
        tk.Label(right, text=f"  {label}{detail}  ",
                 font=THEME["font_body_bold"],
                 bg=color_hex, fg=THEME["text_light"], padx=10, pady=4
                 ).pack(side="top", anchor="e", pady=2)

        # latest fate badge
        fate = latest_fate_for_member(self.data, self.member_id)
        if fate:
            fate_color = FATE_COLORS.get(fate, THEME["text_dark"])
            tk.Label(right, text=f"  Fate: {fate}  ",
                     font=THEME["font_body_bold"],
                     bg=fate_color, fg=THEME["text_light"], padx=10, pady=4
                     ).pack(side="top", anchor="e", pady=2)

    # ---- charts ----------------------------------------------------------
    def _build_charts(self, parent):
        prog = member_level_progression(self.data, self.member_id)

        if not prog:
            box = tk.LabelFrame(parent, text=" Charts ",
                                font=THEME["font_subheading"],
                                bg=THEME["bg_panel"], fg=THEME["text_dark"],
                                bd=2, relief="ridge", padx=14, pady=10)
            box.pack(fill="x", padx=20, pady=10)
            tk.Label(box, text="No data yet — charts will appear after the "
                              "first snapshot containing this member.",
                     font=THEME["font_body"], bg=THEME["bg_panel"],
                     fg=THEME["text_muted"]).pack(pady=20)
            return

        # ---- level progression chart ----
        lvl_box = tk.LabelFrame(parent, text=" Level progression ",
                                font=THEME["font_subheading"],
                                bg=THEME["bg_panel"], fg=THEME["text_dark"],
                                bd=2, relief="ridge", padx=14, pady=10)
        lvl_box.pack(fill="x", padx=20, pady=10)

        self._build_level_chart(lvl_box, prog)

        # ---- derby points chart ----
        derby_history = member_derby_history(self.data, self.member_id)
        if derby_history:
            pts_box = tk.LabelFrame(parent, text=" Derby points ",
                                    font=THEME["font_subheading"],
                                    bg=THEME["bg_panel"], fg=THEME["text_dark"],
                                    bd=2, relief="ridge", padx=14, pady=10)
            pts_box.pack(fill="x", padx=20, pady=10)
            self._build_points_chart(pts_box, derby_history)

    def _build_level_chart(self, parent, progression):
        # need to differentiate after-derby and quick snapshots in the
        # plot - look up snapshot type by date
        snaps_by_id = {s["snapshot_id"]: s for s in self.data.get("snapshots", [])}
        history = member_history(self.data, self.member_id)

        dates = []
        levels = []
        types = []
        for h in history:
            d = self._parse_date(h["snapshot"]["date"])
            lv = h["entry"].get("level")
            if d is None or lv is None:
                continue
            dates.append(d)
            levels.append(lv)
            types.append(h["snapshot"]["type"])

        fig = Figure(figsize=(8, 3.2), dpi=90, facecolor=THEME["bg_panel"])
        ax = fig.add_subplot(111)
        ax.set_facecolor(THEME["bg_card"])

        # base line connecting all points (chronological)
        ax.plot(dates, levels, color=THEME["btn_green"], linewidth=2,
                zorder=2, alpha=0.85)

        # markers per type
        ad_x = [d for d, t in zip(dates, types) if t == SNAPSHOT_TYPE_AFTER_DERBY]
        ad_y = [lv for lv, t in zip(levels, types) if t == SNAPSHOT_TYPE_AFTER_DERBY]
        q_x = [d for d, t in zip(dates, types) if t == SNAPSHOT_TYPE_QUICK]
        q_y = [lv for lv, t in zip(levels, types) if t == SNAPSHOT_TYPE_QUICK]

        if ad_x:
            ax.scatter(ad_x, ad_y, color=THEME["btn_green"], s=60, zorder=3,
                       label="After-Derby", edgecolors="white", linewidth=1.5)
        if q_x:
            ax.scatter(q_x, q_y, color=THEME["btn_blue"], s=50, zorder=3,
                       marker="s", label="Quick",
                       edgecolors="white", linewidth=1.2)

        ax.set_ylabel("Level", fontsize=10)
        ax.grid(True, alpha=0.3, linestyle="--")
        if len(dates) > 1:
            ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
            fig.autofmt_xdate()
        if ad_x or q_x:
            ax.legend(loc="best", fontsize=9, frameon=True)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="x", expand=True)

    def _build_points_chart(self, parent, derby_history):
        dates = []
        points = []
        participated_flags = []
        for h in derby_history:
            d = self._parse_date(h["snapshot"]["date"])
            if d is None:
                continue
            dates.append(d)
            points.append(h["entry"].get("derby_points", 0))
            participated_flags.append(h["entry"].get("derby_participated", False))

        fig = Figure(figsize=(8, 2.8), dpi=90, facecolor=THEME["bg_panel"])
        ax = fig.add_subplot(111)
        ax.set_facecolor(THEME["bg_card"])

        # bar chart - participated bars green, missed bars red/grey
        colors = [THEME["btn_green"] if p else THEME["btn_grey"]
                  for p in participated_flags]
        ax.bar(dates, points, color=colors, width=2.5,
               edgecolor="white", linewidth=1)

        ax.set_ylabel("Points", fontsize=10)
        ax.grid(True, alpha=0.3, linestyle="--", axis="y")
        if len(dates) > 1:
            ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
            fig.autofmt_xdate()
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="x", expand=True)

    @staticmethod
    def _parse_date(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d")
        except (ValueError, TypeError):
            return None

    # ---- derby statistics block ------------------------------------------
    def _build_derby_stats(self, parent):
        derby_history = member_derby_history(self.data, self.member_id)
        if not derby_history:
            return

        box = tk.LabelFrame(parent, text=" Derby statistics ",
                            font=THEME["font_subheading"],
                            bg=THEME["bg_panel"], fg=THEME["text_dark"],
                            bd=2, relief="ridge", padx=14, pady=10)
        box.pack(fill="x", padx=20, pady=10)

        n_derbies = len(derby_history)
        rate = member_derby_participation_rate(self.data, self.member_id) or 0
        avg_tasks = member_avg_tasks(self.data, self.member_id)
        avg_completion = member_avg_task_completion(self.data, self.member_id)
        total_pts = member_total_points(self.data, self.member_id)
        total_tasks = member_total_tasks(self.data, self.member_id)

        rate_pct = rate * 100
        n_participated = sum(1 for h in derby_history
                             if h["entry"].get("derby_participated"))

        # 5 stat tiles - now with completion % as the primary judgment metric
        tiles = tk.Frame(box, bg=THEME["bg_panel"])
        tiles.pack(fill="x", pady=4)
        for i in range(5):
            tiles.grid_columnconfigure(i, weight=1)

        self._make_stat_tile(tiles, 0, "Derbies seen", str(n_derbies))
        self._make_stat_tile(tiles, 1, "Participated",
                             f"{n_participated}/{n_derbies}  ({rate_pct:.0f}%)")
        self._make_stat_tile(
            tiles, 2, "Avg task completion",
            f"{avg_completion*100:.0f}%" if avg_completion is not None else "—"
        )
        self._make_stat_tile(tiles, 3, "Avg tasks (when in)",
                             f"{avg_tasks:.1f}" if avg_tasks is not None else "—")
        self._make_stat_tile(
            tiles, 4, "Total pts / tasks",
            f"{total_pts:,} / {total_tasks}"
        )

    def _make_stat_tile(self, parent, col, label, value):
        tile = tk.Frame(parent, bg=THEME["bg_card"], bd=1, relief="solid",
                        padx=12, pady=8)
        tile.grid(row=0, column=col, sticky="nsew", padx=4, pady=4)
        tk.Label(tile, text=label, font=("Arial", 10, "bold"),
                 bg=THEME["bg_card"], fg=THEME["text_muted"]
                 ).pack(anchor="w")
        tk.Label(tile, text=value, font=THEME["font_count"],
                 bg=THEME["bg_card"], fg=THEME["text_dark"]
                 ).pack(anchor="w")

    # ---- notes editor ----------------------------------------------------
    def _build_notes(self, parent):
        box = tk.LabelFrame(parent, text=" Notes ",
                            font=THEME["font_subheading"],
                            bg=THEME["bg_panel"], fg=THEME["text_dark"],
                            bd=2, relief="ridge", padx=14, pady=10)
        box.pack(fill="x", padx=20, pady=10)

        self.txt_notes = tk.Text(box, height=4, font=THEME["font_body"],
                                  relief="solid", bd=1)
        self.txt_notes.pack(fill="x", pady=4)
        self.txt_notes.insert("1.0", self.member.get("notes", ""))

        btn_row = tk.Frame(box, bg=THEME["bg_panel"])
        btn_row.pack(fill="x", pady=(4, 0))
        RoundedButton(btn_row, text="Save notes",
                      command=self._save_notes,
                      width=130, height=34,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="right")

    def _save_notes(self):
        new_notes = self.txt_notes.get("1.0", tk.END).strip()
        try:
            update_member(self.data, self.member_id, notes=new_notes)
        except ValueError as e:
            messagebox.showerror("Could not save", str(e))
            return
        self.nm.save(self.clan_name, self.data)
        # tiny inline confirmation - no popup spam
        self.member["notes"] = new_notes
        messagebox.showinfo("Saved", "Notes updated.")

    # ---- snapshot history table ------------------------------------------
    def _build_snapshot_history(self, parent):
        history = member_history(self.data, self.member_id)
        if not history:
            return

        box = tk.LabelFrame(parent, text=" Snapshot history ",
                            font=THEME["font_subheading"],
                            bg=THEME["bg_panel"], fg=THEME["text_dark"],
                            bd=2, relief="ridge", padx=14, pady=10)
        box.pack(fill="x", padx=20, pady=10)

        # header
        header = tk.Frame(box, bg=THEME["bg_top"], bd=1, relief="solid")
        header.pack(fill="x")
        cols = [("Date", 110), ("Type", 100), ("Lv", 50),
                ("Derby", 60), ("Tasks", 80), ("Points", 80),
                ("Comment", 220), ("Fate", 80)]
        for label, w in cols:
            f = tk.Frame(header, bg=THEME["bg_top"], width=w, height=24)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Label(f, text=label, font=("Arial", 10, "bold"),
                     bg=THEME["bg_top"], fg=THEME["text_dark"]
                     ).pack(expand=True)

        # rows - newest first
        for i, h in enumerate(reversed(history)):
            snap = h["snapshot"]
            entry = h["entry"]
            bg = "#FFFAEC" if i % 2 == 0 else THEME["bg_card"]
            row = tk.Frame(box, bg=bg)
            row.pack(fill="x")

            is_after = snap["type"] == SNAPSHOT_TYPE_AFTER_DERBY
            type_str = "After-Derby" if is_after else "Quick"

            def cell(parent, text, width, fg=THEME["text_dark"],
                     font=("Arial", 10), anchor="center"):
                f = tk.Frame(parent, bg=bg, width=width, height=22)
                f.pack(side="left")
                f.pack_propagate(False)
                tk.Label(f, text=text, font=font, bg=bg, fg=fg,
                         anchor=anchor).pack(fill="both", expand=True, padx=6)

            cell(row, snap["date"], 110, font=("Arial", 10, "bold"))
            cell(row, type_str, 100,
                 fg=THEME["btn_green"] if is_after else THEME["btn_blue"])
            cell(row, str(entry.get("level", "—")), 50,
                 font=("Arial", 10, "bold"))

            if is_after:
                participated = entry.get("derby_participated")
                cell(row, "yes" if participated else "no", 60,
                     fg=THEME["text_ok"] if participated else THEME["text_muted"])
                if participated:
                    cell(row, f"{entry.get('tasks_done', 0)}/"
                              f"{entry.get('tasks_max', 12)}", 80)
                    cell(row, str(entry.get("derby_points", 0)), 80)
                else:
                    cell(row, "—", 80)
                    cell(row, "—", 80)
            else:
                cell(row, "—", 60, fg=THEME["text_muted"])
                cell(row, "—", 80)
                cell(row, "—", 80)

            cell(row, entry.get("member_comment", ""), 220, anchor="w",
                 fg=THEME["text_muted"])

            fate = entry.get("fate", "")
            fate_color = {"stay": THEME["text_ok"],
                          "warning": ACTIVITY_STATUS_COLORS["below"],
                          "kick": THEME["text_warning"]}.get(fate,
                                                              THEME["text_muted"])
            cell(row, fate, 80, fg=fate_color, font=("Arial", 10, "bold"))

    # ---- name history ----------------------------------------------------
    def _build_name_history(self, parent):
        history = self.member.get("name_history", [])
        if len(history) <= 1:
            return  # no rename

        box = tk.LabelFrame(parent, text=" Name history ",
                            font=THEME["font_subheading"],
                            bg=THEME["bg_panel"], fg=THEME["text_dark"],
                            bd=2, relief="ridge", padx=14, pady=10)
        box.pack(fill="x", padx=20, pady=(10, 20))

        for entry in history:
            name = entry.get("name", "")
            when = entry.get("changed_on", "")
            tk.Label(box, text=f"  {when}: {name}",
                     font=THEME["font_body"],
                     bg=THEME["bg_panel"], fg=THEME["text_dark"]
                     ).pack(anchor="w", pady=1)
