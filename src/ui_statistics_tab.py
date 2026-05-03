"""
Statistics tab - clan-wide overview with collapsible sections.

Sections (each is collapsible; only the summary tiles are open by default):
  - Stat tiles
  - Activity status (with sub-lists for inactive, below, on-track, new player)
  - Average level trend chart
  - Top 5 by task completion %
  - Top 5 by total points
  - Lowest derby participation
  - Members with warning / kick fate (in-clan only)
"""

import tkinter as tk
from datetime import datetime

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates

from theme import THEME, ACTIVITY_STATUS_COLORS
from widgets import RoundedButton
from ui_widgets_extra import CollapsibleSection, StatusCountBadge, SearchBox
from neighborhood_manager import (
    SNAPSHOT_TYPE_AFTER_DERBY, SNAPSHOT_TYPE_DONATIONS,
    DONATION_CATEGORIES,
    ACTIVITY_NEW_MEMBER, ACTIVITY_INACTIVE, ACTIVITY_BELOW_TARGET,
    ACTIVITY_MEETING_TARGET, ACTIVITY_NO_RULE,
)
from clan_stats import (
    snapshot_average_level, clan_avg_level_over_time,
    clan_top_n_by_task_completion, clan_top_n_by_total_points,
    clan_bottom_n_by_recent_participation,
    members_with_kick_warning_flag, members_grouped_by_activity_status,
    member_activity_status,
    clan_total_donations, clan_donations_per_snapshot,
    clan_top_n_by_donations, clan_top_n_by_requests,
)
from activity_score import compute_scores


# Order in which we display activity status sections.
# Colors come from ACTIVITY_STATUS_COLORS (theme-independent, always
# the same red/amber/green/grey shades).
ACTIVITY_DISPLAY_ORDER = [
    (ACTIVITY_INACTIVE, "Inactive (0 levels gained)",
     ACTIVITY_STATUS_COLORS["inactive"]),
    (ACTIVITY_BELOW_TARGET, "Below target",
     ACTIVITY_STATUS_COLORS["below"]),
    (ACTIVITY_MEETING_TARGET, "On track",
     ACTIVITY_STATUS_COLORS["meeting"]),
    (ACTIVITY_NEW_MEMBER, "New player",
     ACTIVITY_STATUS_COLORS["new"]),
    (ACTIVITY_NO_RULE, "No rule covers this level",
     ACTIVITY_STATUS_COLORS["no_rule"]),
]


class StatisticsTab(tk.Frame):
    def __init__(self, parent, manager):
        super().__init__(parent, bg=THEME["bg_main"])
        self.manager = manager
        self.data = manager.reload_data()

        # outer scroll wrapper
        canvas = tk.Canvas(self, bg=THEME["bg_main"],
                           highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg=THEME["bg_main"])
        canvas_window = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(canvas_window, width=e.width))

        # smooth mousewheel
        from ui_widgets_extra import attach_smooth_mousewheel
        attach_smooth_mousewheel(canvas)

        self._build_stat_tiles(body)
        self._build_activity_section(body)
        self._build_top_score_section(body)
        self._build_donations_clan_section(body)
        self._build_top_donations_section(body)
        self._build_top_requests_section(body)
        self._build_donations_trend_section(body)
        self._build_trend_chart_section(body)
        self._build_top_completion_section(body)
        self._build_top_points_section(body)
        self._build_bottom_participation_section(body)
        self._build_warning_kick_section(body)

    # =================================================================
    # 1. always-visible stat tiles
    # =================================================================
    def _build_stat_tiles(self, parent):
        snapshots = self.data.get("snapshots", [])
        n_snaps = len(snapshots)
        n_derbies = sum(1 for s in snapshots
                         if s["type"] == SNAPSHOT_TYPE_AFTER_DERBY)
        in_clan_count = sum(1 for m in self.data["members"].values()
                             if m["in_clan"])
        total_db = len(self.data["members"])

        if snapshots:
            latest = sorted(snapshots, key=lambda s: s["date"])[-1]
            avg_lvl = snapshot_average_level(latest)
            levels = [e["level"] for e in latest["entries"]
                      if e.get("level") is not None]
            max_lvl = max(levels) if levels else 0
            min_lvl = min(levels) if levels else 0
        else:
            avg_lvl = None
            max_lvl = min_lvl = 0

        avg_str = f"{avg_lvl:.1f}" if avg_lvl is not None else "—"

        wrap = tk.Frame(parent, bg=THEME["bg_main"])
        wrap.pack(fill="x", padx=20, pady=(15, 10))

        tiles = [
            ("Members in clan", f"{in_clan_count}/30", THEME["btn_green"]),
            ("In database", str(total_db), THEME["btn_blue"]),
            ("Snapshots", str(n_snaps), THEME["btn_green"]),
            ("Derbies recorded", str(n_derbies), THEME["btn_green"]),
            ("Latest avg level", avg_str, THEME["btn_blue"]),
            ("Latest max / min", f"{max_lvl} / {min_lvl}", THEME["btn_blue"]),
        ]
        for i in range(len(tiles)):
            wrap.grid_columnconfigure(i, weight=1)
        for i, (label, val, accent) in enumerate(tiles):
            self._make_stat_tile(wrap, 0, i, label, val, accent)

    def _make_stat_tile(self, parent, row, col, label, value, accent):
        tile = tk.Frame(parent, bg=THEME["bg_card"], bd=1, relief="solid",
                        padx=10, pady=8)
        tile.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
        tk.Label(tile, text=label, font=("Arial", 9, "bold"),
                 bg=THEME["bg_card"], fg=THEME["text_muted"]
                 ).pack(anchor="w")
        tk.Label(tile, text=value, font=THEME["font_count"],
                 bg=THEME["bg_card"], fg=accent
                 ).pack(anchor="w")

    # =================================================================
    # 2. activity status with full per-status lists
    # =================================================================
    def _build_activity_section(self, parent):
        grouped = members_grouped_by_activity_status(self.data)
        n_in = len(grouped.get(ACTIVITY_INACTIVE, []))
        n_bel = len(grouped.get(ACTIVITY_BELOW_TARGET, []))
        n_ok = len(grouped.get(ACTIVITY_MEETING_TARGET, []))
        n_new = len(grouped.get(ACTIVITY_NEW_MEMBER, []))

        # multi-color count pills, theme-independent fixed colors
        def make_badge(parent_frame):
            return StatusCountBadge(parent_frame, [
                (n_in, ACTIVITY_STATUS_COLORS["inactive"]),
                (n_bel, ACTIVITY_STATUS_COLORS["below"]),
                (n_ok, ACTIVITY_STATUS_COLORS["meeting"]),
                (n_new, ACTIVITY_STATUS_COLORS["new"]),
            ], bg=THEME["bg_top"])

        sect = CollapsibleSection(parent,
                                   title="Activity status (in-clan members)",
                                   initial_open=False,
                                   badge_widget=make_badge)
        sect.pack(fill="x", padx=20, pady=10)
        body = sect.body
        body.configure(padx=10, pady=8)

        # Per-status sub-lists - all four meaningful statuses get a list
        for status, label, color_key in ACTIVITY_DISPLAY_ORDER:
            members = grouped.get(status, [])
            if not members:
                continue
            self._render_activity_substatus(body, label, color_key, members)

    def _render_activity_substatus(self, parent, label, color, members):
        """color is a literal hex string (theme-independent)."""
        sub = tk.Frame(parent, bg=THEME["bg_panel"])
        sub.pack(fill="x", pady=(8, 2))

        tk.Label(sub, text=f"{label}  ({len(members)})",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=color
                 ).pack(anchor="w")

        # sort by levels_gained ascending (worst first)
        # for new_member sort by current_level desc; for inactive sort by name
        def _sort_key(item):
            mid, m, info = item
            lg = info.get("levels_gained")
            return (lg if lg is not None else 999, m["name"].lower())

        for mid, m, info in sorted(members, key=_sort_key):
            gained = info.get("levels_gained")
            target = info.get("target") or 0
            days = info.get("days_covered") or 0
            cur = info.get("current_level", "—")

            row = tk.Frame(sub, bg=THEME["bg_card"], bd=1, relief="solid")
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"  Lv {cur}  ", font=("Arial", 10, "bold"),
                     bg=THEME["bg_card"], fg=THEME["text_dark"], width=8
                     ).pack(side="left")
            tk.Label(row, text=m["name"], font=THEME["font_body_bold"],
                     bg=THEME["bg_card"], fg=THEME["text_dark"], width=24,
                     anchor="w"
                     ).pack(side="left", padx=4)
            tk.Label(row, text=mid, font=("Consolas", 10),
                     bg=THEME["bg_card"], fg=THEME["text_muted"], width=14,
                     anchor="w"
                     ).pack(side="left", padx=4)

            # per-status detail string
            if gained is None:
                detail = f"only {days} days of data"
            else:
                detail = f"gained {gained}/{target} levels in {days} days"
            tk.Label(row, text=detail,
                     font=THEME["font_body"],
                     bg=THEME["bg_card"], fg=THEME["text_muted"],
                     anchor="w"
                     ).pack(side="left", padx=8, fill="x", expand=True)

            RoundedButton(row, text="Details",
                          command=lambda mid=mid:
                                      self.manager.app.show_frame(
                                          "MemberDetail", member_id=mid),
                          width=80, height=24,
                          bg_color=THEME["btn_blue"],
                          hover_color=THEME["btn_blue_hover"],
                          font=("Arial", 9, "bold"), radius=8
                          ).pack(side="right", padx=6, pady=2)

    # =================================================================
    # 3. trend chart (lazy: only renders when section is opened)
    # =================================================================
    def _build_trend_chart_section(self, parent):
        sect = CollapsibleSection(parent,
                                   title="Average level trend",
                                   initial_open=False,
                                   on_first_open=self._render_trend_chart)
        sect.pack(fill="x", padx=20, pady=10)

    def _render_trend_chart(self, parent):
        snapshots = self.data.get("snapshots", [])
        if not snapshots:
            tk.Label(parent, text="No snapshots yet.",
                     font=THEME["font_body"], bg=THEME["bg_panel"],
                     fg=THEME["text_muted"]).pack(pady=10)
            return

        timeline = clan_avg_level_over_time(self.data)
        parsed = []
        for date_str, type_, avg in timeline:
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d")
            except (ValueError, TypeError):
                continue
            parsed.append((d, type_, avg))

        if not parsed:
            return

        dates = [d for d, t, a in parsed]
        avgs = [a for d, t, a in parsed]
        types = [t for d, t, a in parsed]

        fig = Figure(figsize=(8, 3.0), dpi=90, facecolor=THEME["bg_panel"])
        ax = fig.add_subplot(111)
        ax.set_facecolor(THEME["bg_card"])
        ax.plot(dates, avgs, color=THEME["btn_green"], linewidth=2,
                zorder=2, alpha=0.85)

        ad_x = [d for d, t in zip(dates, types)
                if t == SNAPSHOT_TYPE_AFTER_DERBY]
        ad_y = [a for a, t in zip(avgs, types)
                if t == SNAPSHOT_TYPE_AFTER_DERBY]
        q_x = [d for d, t in zip(dates, types)
               if t != SNAPSHOT_TYPE_AFTER_DERBY]
        q_y = [a for a, t in zip(avgs, types)
               if t != SNAPSHOT_TYPE_AFTER_DERBY]

        if ad_x:
            ax.scatter(ad_x, ad_y, color=THEME["btn_green"], s=60, zorder=3,
                       label="After-Derby", edgecolors="white", linewidth=1.5)
        if q_x:
            ax.scatter(q_x, q_y, color=THEME["btn_blue"], s=50, zorder=3,
                       marker="s", label="Quick",
                       edgecolors="white", linewidth=1.2)

        ax.set_ylabel("Avg level", fontsize=10)
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

    # =================================================================
    # 4. Top 5 by task completion %
    # =================================================================
    def _build_top_completion_section(self, parent):
        if not hasattr(self, "var_include_former_completion"):
            self.var_include_former_completion = tk.BooleanVar(value=False)

        sect = CollapsibleSection(parent,
                                   title="Top 5 by task completion %",
                                   initial_open=False,
                                   on_first_open=self._render_completion_body)
        sect.pack(fill="x", padx=20, pady=10)

    def _render_completion_body(self, parent):
        # filter toggle
        toggle_bar = tk.Frame(parent, bg=THEME["bg_panel"])
        toggle_bar.pack(fill="x", padx=10, pady=(8, 4))
        tk.Checkbutton(
            toggle_bar,
            text="Include former members (greyed out)",
            variable=self.var_include_former_completion,
            command=lambda: self._refresh_section_body(
                parent, self._render_completion_body),
            font=THEME["font_body_bold"],
            bg=THEME["bg_panel"], fg=THEME["text_dark"],
            activebackground=THEME["bg_panel"],
            selectcolor=THEME["bg_card"],
        ).pack(side="left")

        include_former = self.var_include_former_completion.get()

        # all-time
        tk.Label(parent, text="All-time average",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"]
                 ).pack(anchor="w", padx=10, pady=(8, 2))
        rows_all = clan_top_n_by_task_completion(
            self.data, n=5, last_n_derbies=None,
            include_former=include_former)
        self._render_completion_rows(parent, rows_all)

        # last 3
        tk.Label(parent, text="Last 3 derbies",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"]
                 ).pack(anchor="w", padx=10, pady=(10, 2))
        rows_last3 = clan_top_n_by_task_completion(
            self.data, n=5, last_n_derbies=3,
            include_former=include_former)
        self._render_completion_rows(parent, rows_last3)

        # bottom padding
        tk.Frame(parent, bg=THEME["bg_panel"], height=8).pack()

    def _render_completion_rows(self, parent, rows):
        if not rows:
            tk.Label(parent, text="No participation data yet.",
                     font=THEME["font_body"], bg=THEME["bg_panel"],
                     fg=THEME["text_muted"]).pack(padx=10, pady=4)
            return
        wrap = tk.Frame(parent, bg=THEME["bg_panel"])
        wrap.pack(fill="x", padx=10)
        for i, (mid, name, ratio, in_clan) in enumerate(rows, start=1):
            row = tk.Frame(wrap, bg=THEME["bg_card"], bd=1, relief="solid")
            row.pack(fill="x", pady=1)
            name_color = (THEME["text_dark"] if in_clan
                          else THEME["text_muted"])
            badge_text = "" if in_clan else " [former]"
            tk.Label(row, text=f"  #{i}  ", font=("Arial", 10, "bold"),
                     bg=THEME["bg_card"], fg=THEME["btn_green"], width=4
                     ).pack(side="left")
            tk.Label(row, text=name + badge_text,
                     font=THEME["font_body_bold"],
                     bg=THEME["bg_card"], fg=name_color, anchor="w"
                     ).pack(side="left", padx=6, fill="x", expand=True)
            tk.Label(row, text=f"{ratio*100:.0f}%",
                     font=("Arial", 10, "bold"),
                     bg=THEME["bg_card"], fg=THEME["text_dark"]
                     ).pack(side="right", padx=8)

    # =================================================================
    # 5. Top 5 by total points (curiosity list)
    # =================================================================
    def _build_top_points_section(self, parent):
        if not hasattr(self, "var_include_former_points"):
            self.var_include_former_points = tk.BooleanVar(value=False)

        sect = CollapsibleSection(parent,
                                   title="Top 5 by total points (all-time)",
                                   initial_open=False,
                                   on_first_open=self._render_points_body)
        sect.pack(fill="x", padx=20, pady=10)

    def _render_points_body(self, parent):
        toggle_bar = tk.Frame(parent, bg=THEME["bg_panel"])
        toggle_bar.pack(fill="x", padx=10, pady=(8, 4))
        tk.Checkbutton(
            toggle_bar,
            text="Include former members",
            variable=self.var_include_former_points,
            command=lambda: self._refresh_section_body(
                parent, self._render_points_body),
            font=THEME["font_body_bold"],
            bg=THEME["bg_panel"], fg=THEME["text_dark"],
            activebackground=THEME["bg_panel"],
            selectcolor=THEME["bg_card"],
        ).pack(side="left")

        include_former = self.var_include_former_points.get()
        pts_top = clan_top_n_by_total_points(
            self.data, n=5, include_former=include_former)
        if not pts_top:
            tk.Label(parent, text="No derby data yet.",
                     font=THEME["font_body"], bg=THEME["bg_panel"],
                     fg=THEME["text_muted"]).pack(padx=10, pady=10)
            return

        wrap = tk.Frame(parent, bg=THEME["bg_panel"])
        wrap.pack(fill="x", padx=10, pady=(2, 8))
        for i, (mid, name, total_pts, total_tasks, in_clan) in enumerate(
                pts_top, start=1):
            row = tk.Frame(wrap, bg=THEME["bg_card"], bd=1, relief="solid")
            row.pack(fill="x", pady=1)
            name_color = (THEME["text_dark"] if in_clan
                          else THEME["text_muted"])
            badge_text = "" if in_clan else " [former]"
            tk.Label(row, text=f"  #{i}  ", font=("Arial", 10, "bold"),
                     bg=THEME["bg_card"], fg=THEME["btn_blue"], width=4
                     ).pack(side="left")
            tk.Label(row, text=name + badge_text,
                     font=THEME["font_body_bold"],
                     bg=THEME["bg_card"], fg=name_color, anchor="w"
                     ).pack(side="left", padx=6, fill="x", expand=True)
            tk.Label(row, text=f"{total_pts:,} pts  ({total_tasks} tasks)",
                     font=("Arial", 10, "bold"),
                     bg=THEME["bg_card"], fg=THEME["text_dark"]
                     ).pack(side="right", padx=8)

    # =================================================================
    # 6. Lowest derby participation
    # =================================================================
    def _build_bottom_participation_section(self, parent):
        if not hasattr(self, "var_include_former_part"):
            self.var_include_former_part = tk.BooleanVar(value=False)

        sect = CollapsibleSection(
            parent,
            title="Lowest derby participation (last 5 derbies)",
            initial_open=False,
            on_first_open=self._render_participation_body)
        sect.pack(fill="x", padx=20, pady=10)

    def _render_participation_body(self, parent):
        toggle_bar = tk.Frame(parent, bg=THEME["bg_panel"])
        toggle_bar.pack(fill="x", padx=10, pady=(8, 4))
        tk.Checkbutton(
            toggle_bar,
            text="Include former members",
            variable=self.var_include_former_part,
            command=lambda: self._refresh_section_body(
                parent, self._render_participation_body),
            font=THEME["font_body_bold"],
            bg=THEME["bg_panel"], fg=THEME["text_dark"],
            activebackground=THEME["bg_panel"],
            selectcolor=THEME["bg_card"],
        ).pack(side="left")

        include_former = self.var_include_former_part.get()
        bot_rows = clan_bottom_n_by_recent_participation(
            self.data, n=5, last_n_derbies=5,
            include_former=include_former)
        if not bot_rows:
            tk.Label(parent, text="No participation data yet.",
                     font=THEME["font_body"], bg=THEME["bg_panel"],
                     fg=THEME["text_muted"]).pack(padx=10, pady=10)
            return

        wrap = tk.Frame(parent, bg=THEME["bg_panel"])
        wrap.pack(fill="x", padx=10, pady=(2, 8))
        for i, (mid, name, rate, in_clan) in enumerate(bot_rows, start=1):
            row = tk.Frame(wrap, bg=THEME["bg_card"], bd=1, relief="solid")
            row.pack(fill="x", pady=1)
            rate_color = (THEME["text_warning"] if rate == 0
                          else THEME["act_below"] if rate < 0.5
                          else THEME["text_dark"])
            name_color = (THEME["text_dark"] if in_clan
                          else THEME["text_muted"])
            badge_text = "" if in_clan else " [former]"
            tk.Label(row, text=f"  #{i}  ", font=("Arial", 10, "bold"),
                     bg=THEME["bg_card"], fg=rate_color, width=4
                     ).pack(side="left")
            tk.Label(row, text=name + badge_text,
                     font=THEME["font_body_bold"],
                     bg=THEME["bg_card"], fg=name_color, anchor="w"
                     ).pack(side="left", padx=6, fill="x", expand=True)
            tk.Label(row, text=f"{rate*100:.0f}%",
                     font=("Arial", 10, "bold"),
                     bg=THEME["bg_card"], fg=rate_color
                     ).pack(side="right", padx=8)

    # =================================================================
    # 7. warning/kick fate (in-clan only by default)
    # =================================================================
    def _build_warning_kick_section(self, parent):
        flagged = members_with_kick_warning_flag(self.data, only_in_clan=True)
        if not flagged:
            return

        sect = CollapsibleSection(
            parent,
            title="Members with warning / kick fate",
            badge_text=str(len(flagged)),
            badge_color=THEME["text_warning"],
            initial_open=False,
            on_first_open=lambda body: self._render_warning_body(body, flagged))
        sect.pack(fill="x", padx=20, pady=(10, 20))

    def _render_warning_body(self, parent, flagged):
        wrap = tk.Frame(parent, bg=THEME["bg_panel"])
        wrap.pack(fill="x", padx=10, pady=(6, 8))
        for mid, name, fate in sorted(
                flagged, key=lambda r: (r[2] != "kick", r[1])):
            row = tk.Frame(wrap, bg=THEME["bg_card"], bd=1, relief="solid")
            row.pack(fill="x", pady=1)
            color = (THEME["text_warning"] if fate == "kick"
                     else THEME["act_below"])
            tk.Label(row, text=f"  {fate.upper()}  ",
                     font=("Arial", 10, "bold"),
                     bg=color, fg=THEME["text_light"], padx=6, pady=2
                     ).pack(side="left")
            tk.Label(row, text=name, font=THEME["font_body_bold"],
                     bg=THEME["bg_card"], fg=THEME["text_dark"], anchor="w"
                     ).pack(side="left", padx=8, fill="x", expand=True)
            tk.Label(row, text=mid, font=("Consolas", 10),
                     bg=THEME["bg_card"], fg=THEME["text_muted"]
                     ).pack(side="right", padx=8)
            RoundedButton(row, text="Details",
                          command=lambda mid=mid:
                                      self.manager.app.show_frame(
                                          "MemberDetail", member_id=mid),
                          width=80, height=24,
                          bg_color=THEME["btn_blue"],
                          hover_color=THEME["btn_blue_hover"],
                          font=("Arial", 9, "bold"), radius=8
                          ).pack(side="right", padx=6, pady=2)

    # =================================================================
    # 8. top 5 by activity score
    # =================================================================
    def _build_top_score_section(self, parent):
        sect = CollapsibleSection(
            parent,
            title="Top 5 by activity score",
            initial_open=False,
            on_first_open=self._render_top_score_body)
        sect.pack(fill="x", padx=20, pady=10)

    def _render_top_score_body(self, parent):
        scores = compute_scores(self.data, include_former=False)
        # only show those with > 0 total
        scores = [s for s in scores if s["total"] > 0][:5]
        if not scores:
            tk.Label(parent, text="No activity data yet.",
                     font=THEME["font_body"], bg=THEME["bg_panel"],
                     fg=THEME["text_muted"]).pack(padx=10, pady=10)
            return

        wrap = tk.Frame(parent, bg=THEME["bg_panel"])
        wrap.pack(fill="x", padx=10, pady=(2, 8))
        for i, row in enumerate(scores, start=1):
            line = tk.Frame(wrap, bg=THEME["bg_card"], bd=1, relief="solid")
            line.pack(fill="x", pady=1)
            tk.Label(line, text=f"  #{i}  ", font=("Arial", 10, "bold"),
                     bg=THEME["bg_card"], fg=THEME["btn_blue"], width=4
                     ).pack(side="left")
            tk.Label(line, text=row["name"],
                     font=THEME["font_body_bold"],
                     bg=THEME["bg_card"], fg=THEME["text_dark"], anchor="w"
                     ).pack(side="left", padx=6, fill="x", expand=True)
            tk.Label(line, text=f"{row['total']} pts",
                     font=("Arial Black", 12, "bold"),
                     bg=THEME["bg_card"], fg=THEME["text_dark"]
                     ).pack(side="right", padx=8)

    # =================================================================
    # 9. donations - clan-wide overview
    # =================================================================
    def _build_donations_clan_section(self, parent):
        # only render if there's at least one donations snapshot
        n_donations_snapshots = sum(
            1 for s in self.data.get("snapshots", [])
            if s.get("type") == SNAPSHOT_TYPE_DONATIONS)
        if n_donations_snapshots == 0:
            return

        sect = CollapsibleSection(
            parent,
            title="Donations — clan-wide overview",
            initial_open=False,
            on_first_open=self._render_donations_clan_body)
        sect.pack(fill="x", padx=20, pady=10)

    def _render_donations_clan_body(self, parent):
        totals = clan_total_donations(self.data)

        tk.Label(parent,
                 text=f"  {totals['snapshots_counted']} weekly snapshot(s) "
                      f"recorded.",
                 font=THEME["font_body"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"]
                 ).pack(anchor="w", padx=10, pady=(8, 4))

        # per-category table
        table = tk.Frame(parent, bg=THEME["bg_panel"])
        table.pack(fill="x", padx=10, pady=4)
        # header
        header = tk.Frame(table, bg=THEME["bg_top"])
        header.pack(fill="x")
        for label, w in [("Category", 200), ("Total donated", 220),
                          ("Total requested", 220)]:
            f = tk.Frame(header, bg=THEME["bg_top"], width=w, height=24)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Label(f, text=label, font=THEME["font_body_bold"],
                     bg=THEME["bg_top"], fg=THEME["text_dark"]
                     ).pack(expand=True)
        for cat in DONATION_CATEGORIES:
            line = tk.Frame(table, bg=THEME["bg_card"])
            line.pack(fill="x")
            for text, w in [(cat.capitalize(), 200),
                             (f"{totals[f'{cat}_donated']:,}", 220),
                             (f"{totals[f'{cat}_requested']:,}", 220)]:
                f = tk.Frame(line, bg=THEME["bg_card"], width=w, height=22)
                f.pack(side="left")
                f.pack_propagate(False)
                tk.Label(f, text=text, font=("Arial", 10, "bold"),
                         bg=THEME["bg_card"], fg=THEME["text_dark"]
                         ).pack(expand=True)
        # combined
        line = tk.Frame(table, bg=THEME["bg_top"])
        line.pack(fill="x")
        for text, w in [("All categories", 200),
                         (f"{totals['all_donated']:,}", 220),
                         (f"{totals['all_requested']:,}", 220)]:
            f = tk.Frame(line, bg=THEME["bg_top"], width=w, height=24)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Label(f, text=text, font=THEME["font_body_bold"],
                     bg=THEME["bg_top"], fg=THEME["text_dark"]
                     ).pack(expand=True)
        # bottom padding
        tk.Frame(parent, bg=THEME["bg_panel"], height=8).pack()

    # =================================================================
    # 10. top 5 by donations / requests
    # =================================================================
    def _build_top_donations_section(self, parent):
        n_donations = sum(1 for s in self.data.get("snapshots", [])
                           if s.get("type") == SNAPSHOT_TYPE_DONATIONS)
        if n_donations == 0:
            return
        sect = CollapsibleSection(
            parent,
            title="Top 5 by donations (recent 4 weeks)",
            initial_open=False,
            on_first_open=self._render_top_donations_body)
        sect.pack(fill="x", padx=20, pady=10)

    def _render_top_donations_body(self, parent):
        rows = clan_top_n_by_donations(self.data, n=5, last_n_weeks=4,
                                        include_former=False)
        if not rows:
            tk.Label(parent, text="No donation data yet.",
                     font=THEME["font_body"], bg=THEME["bg_panel"],
                     fg=THEME["text_muted"]).pack(padx=10, pady=10)
            return
        wrap = tk.Frame(parent, bg=THEME["bg_panel"])
        wrap.pack(fill="x", padx=10, pady=(2, 8))
        for i, (mid, name, total_d, total_r, in_clan) in enumerate(rows, start=1):
            line = tk.Frame(wrap, bg=THEME["bg_card"], bd=1, relief="solid")
            line.pack(fill="x", pady=1)
            tk.Label(line, text=f"  #{i}  ", font=("Arial", 10, "bold"),
                     bg=THEME["bg_card"], fg=THEME["btn_green"], width=4
                     ).pack(side="left")
            tk.Label(line, text=name,
                     font=THEME["font_body_bold"],
                     bg=THEME["bg_card"], fg=THEME["text_dark"], anchor="w"
                     ).pack(side="left", padx=6, fill="x", expand=True)
            tk.Label(line, text=f"donated {total_d:,}",
                     font=("Arial", 10, "bold"),
                     bg=THEME["bg_card"], fg=THEME["btn_green"]
                     ).pack(side="right", padx=8)
            tk.Label(line, text=f"   (req {total_r:,})",
                     font=THEME["font_body"],
                     bg=THEME["bg_card"], fg=THEME["text_muted"]
                     ).pack(side="right")

    def _build_top_requests_section(self, parent):
        n_donations = sum(1 for s in self.data.get("snapshots", [])
                           if s.get("type") == SNAPSHOT_TYPE_DONATIONS)
        if n_donations == 0:
            return
        sect = CollapsibleSection(
            parent,
            title="Top 5 by requests (recent 4 weeks)",
            initial_open=False,
            on_first_open=self._render_top_requests_body)
        sect.pack(fill="x", padx=20, pady=10)

    def _render_top_requests_body(self, parent):
        rows = clan_top_n_by_requests(self.data, n=5, last_n_weeks=4,
                                       include_former=False)
        if not rows:
            tk.Label(parent, text="No request data yet.",
                     font=THEME["font_body"], bg=THEME["bg_panel"],
                     fg=THEME["text_muted"]).pack(padx=10, pady=10)
            return
        wrap = tk.Frame(parent, bg=THEME["bg_panel"])
        wrap.pack(fill="x", padx=10, pady=(2, 8))
        for i, (mid, name, total_r, total_d, in_clan) in enumerate(rows, start=1):
            line = tk.Frame(wrap, bg=THEME["bg_card"], bd=1, relief="solid")
            line.pack(fill="x", pady=1)
            tk.Label(line, text=f"  #{i}  ", font=("Arial", 10, "bold"),
                     bg=THEME["bg_card"], fg=THEME["btn_blue"], width=4
                     ).pack(side="left")
            tk.Label(line, text=name,
                     font=THEME["font_body_bold"],
                     bg=THEME["bg_card"], fg=THEME["text_dark"], anchor="w"
                     ).pack(side="left", padx=6, fill="x", expand=True)
            tk.Label(line, text=f"req {total_r:,}",
                     font=("Arial", 10, "bold"),
                     bg=THEME["bg_card"], fg=THEME["btn_blue"]
                     ).pack(side="right", padx=8)
            tk.Label(line, text=f"   (donated {total_d:,})",
                     font=THEME["font_body"],
                     bg=THEME["bg_card"], fg=THEME["text_muted"]
                     ).pack(side="right")

    # =================================================================
    # 11. donations trend chart
    # =================================================================
    def _build_donations_trend_section(self, parent):
        n_donations = sum(1 for s in self.data.get("snapshots", [])
                           if s.get("type") == SNAPSHOT_TYPE_DONATIONS)
        if n_donations < 2:
            return
        sect = CollapsibleSection(
            parent,
            title="Donations trend (clan-wide weekly)",
            initial_open=False,
            on_first_open=self._render_donations_trend)
        sect.pack(fill="x", padx=20, pady=10)

    def _render_donations_trend(self, parent):
        timeline = clan_donations_per_snapshot(self.data)
        if len(timeline) < 2:
            tk.Label(parent, text="Need at least 2 donations snapshots.",
                     font=THEME["font_body"], bg=THEME["bg_panel"],
                     fg=THEME["text_muted"]).pack(padx=10, pady=10)
            return

        parsed = []
        for date_str, d, r in timeline:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
            except (ValueError, TypeError):
                continue
            parsed.append((dt, d, r))

        if len(parsed) < 2:
            return

        dates = [p[0] for p in parsed]
        ds = [p[1] for p in parsed]
        rs = [p[2] for p in parsed]

        fig = Figure(figsize=(8, 3.0), dpi=90, facecolor=THEME["bg_panel"])
        ax = fig.add_subplot(111)
        ax.set_facecolor(THEME["bg_card"])
        ax.plot(dates, ds, color=THEME["btn_green"], linewidth=2,
                marker="o", label="Donated")
        ax.plot(dates, rs, color=THEME["btn_blue"], linewidth=2,
                marker="s", label="Requested")
        ax.set_ylabel("Total per week", fontsize=10)
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        fig.autofmt_xdate()
        ax.legend(loc="best", fontsize=9, frameon=True)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="x", expand=True)

    # =================================================================
    # helpers
    # =================================================================
    def _refresh_section_body(self, body, render_fn):
        """Used by collapsible sections that need to redraw their content
        when a toggle inside changes."""
        for child in body.winfo_children():
            child.destroy()
        render_fn(body)
