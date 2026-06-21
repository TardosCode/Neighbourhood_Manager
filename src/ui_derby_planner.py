"""
Derby Planner screen.

A planning tool that turns a clan's recorded derby history into a concrete
lineup for the *next* derby. All the number crunching lives in
derby_planner.py (pure, unit-tested); this module is only the Tkinter shell
that lets the user tick members in/out and watch the prediction update live.

Layout (two regions side by side):

    [<-- Back]        🏇 Derby Planner            [⚙ Settings]

    ┌─ Roster (scrollable) ──────┐   ┌─ Prediction ─────────────┐
    │ [✓] Name      [Leader]     │   │ Predicted:   1234         │
    │     85%  410 avg  348 exp  │   │ Ceiling:     1500         │
    │     [Reliable]             │   │ Completion:  92%          │
    │ [ ] Name      [Member]     │   │ Selected:    12           │
    │     50%  300 avg  150 exp  │   │ Risky/unknown picks: 3    │
    │     [Risky]                │   │ Risk: Alice, Bob, ...     │
    │  ...                       │   │                           │
    │                            │   │ Target: [____]            │
    │                            │   │ [Auto-pick best lineup]   │
    │                            │   │ target met / not met      │
    │                            │   │ ── Saved plans ──         │
    │                            │   │ Plan name  [Load][Delete] │
    │                            │   │ [Save plan]               │
    └────────────────────────────┘   └───────────────────────────┘

The roster is sorted by expected points (derby_planner.all_member_profiles),
each row carrying a tk.BooleanVar checkbox. Any checkbox change recomputes
the prediction via derby_planner.predict_lineup. Saved plans are persisted on
the clan data dict under "derby_plans" and survive across sessions.
"""

import tkinter as tk
from tkinter import messagebox, simpledialog

from theme import THEME, ROLE_COLORS, ROLE_LABELS
from widgets import RoundedButton
from ui_widgets_extra import SmoothScrolledFrame
import derby_planner


# Semantic risk-tier colors. The amber here mirrors theme.py's
# ACTIVITY_STATUS_COLORS["below"] — it's a fixed semantic shade, not a
# themeable surface color, so the green/amber/red meaning stays readable.
RISK_COLORS = {
    derby_planner.RISK_RELIABLE:     THEME["btn_green"],
    derby_planner.RISK_INCONSISTENT: "#E89B3B",          # amber
    derby_planner.RISK_RISKY:        THEME["btn_red"],
    derby_planner.RISK_UNKNOWN:      THEME["btn_grey"],
}


class DerbyPlannerFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=THEME["bg_main"])
        self.app = app
        self.nm = app.neighborhood_manager

        # guard a missing active clan exactly like the other clan screens do
        clan = self.nm.get_active()
        if clan is None:
            messagebox.showinfo("No neighborhood",
                                "No active neighborhood. "
                                "Returning to the neighborhood screen.")
            self.app.show_frame("NeighborhoodSelect", first_run=True)
            return

        self.clan = clan
        self.data = self.nm.load(clan)

        # member_id -> tk.BooleanVar (whether the member is in the lineup)
        self._check_vars = {}
        # widgets we rebuild/update after each change (set in _build_* methods)
        self._plans_holder = None

        self._build_top_bar()
        self._build_body()

        # initial render of the live prediction panel
        self._refresh_prediction()

    # =================================================================
    # top bar
    # =================================================================
    def _build_top_bar(self):
        top = tk.Frame(self, bg=THEME["bg_top"], height=60)
        top.pack(side="top", fill="x")
        top.pack_propagate(False)

        # back button (left) -> Other tools menu
        RoundedButton(top, text="← Back",
                      command=lambda: self.app.show_frame("OtherTools"),
                      width=100, height=40,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="left", padx=15, pady=10)

        # title (center)
        tk.Label(top, text="🏇 Derby Planner",
                 font=THEME["font_title"],
                 bg=THEME["bg_top"], fg=THEME["text_dark"]).pack(side="left",
                                                                 expand=True)

        # settings button (right)
        RoundedButton(top, text="⚙ Settings",
                      command=lambda: self.app.show_frame(
                          "AppSettings", return_to="DerbyPlanner"),
                      width=120, height=38,
                      bg_color=THEME["btn_blue"],
                      hover_color=THEME["btn_blue_hover"]
                      ).pack(side="right", padx=15, pady=10)

    # =================================================================
    # body: two columns (roster | prediction)
    # =================================================================
    def _build_body(self):
        body = tk.Frame(self, bg=THEME["bg_main"])
        body.pack(fill="both", expand=True, padx=15, pady=15)

        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        roster = self._build_roster_panel(body)
        roster.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        prediction = self._build_prediction_panel(body)
        prediction.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    # ---- left: scrollable roster --------------------------------------
    def _build_roster_panel(self, parent):
        frame = tk.Frame(parent, bg=THEME["bg_panel"], bd=2, relief="ridge")

        tk.Label(frame, text="Roster", font=THEME["font_heading"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]).pack(pady=(6, 0))
        tk.Label(frame,
                 text="Tick the members you plan to field. "
                      "Sorted by expected points.",
                 font=THEME["font_body"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"]).pack(pady=(0, 6))

        # scroll container fills the rest of the panel
        scroller = SmoothScrolledFrame(frame, bg=THEME["bg_panel"])
        scroller.pack(fill="both", expand=True, padx=6, pady=(0, 8))
        rows = scroller.inner

        # profiles come pre-sorted by expected points (best first)
        profiles = derby_planner.all_member_profiles(self.data)
        if not profiles:
            tk.Label(rows, text="No in-clan members to plan with yet.",
                     font=THEME["font_body"], bg=THEME["bg_panel"],
                     fg=THEME["text_muted"]).pack(pady=20)
            return frame

        for prof in profiles:
            self._build_roster_row(rows, prof)

        return frame

    def _build_roster_row(self, parent, profile: dict):
        """One member card: checkbox + name + role chip + derby numbers."""
        mid = profile["member_id"]

        card = tk.Frame(parent, bg=THEME["bg_card"], bd=1, relief="solid")
        card.pack(fill="x", padx=4, pady=3)

        # checkbox drives lineup membership; toggling re-runs the prediction
        var = tk.BooleanVar(value=False)
        self._check_vars[mid] = var
        chk = tk.Checkbutton(card, variable=var, bg=THEME["bg_card"],
                             activebackground=THEME["bg_card"],
                             command=self._refresh_prediction)
        chk.pack(side="left", padx=(6, 4), pady=6)

        # text block on the right of the checkbox
        text_col = tk.Frame(card, bg=THEME["bg_card"])
        text_col.pack(side="left", fill="x", expand=True, pady=4)

        # top line: name + role chip
        name_row = tk.Frame(text_col, bg=THEME["bg_card"])
        name_row.pack(fill="x", anchor="w")
        tk.Label(name_row, text=profile["name"], font=THEME["font_body_bold"],
                 bg=THEME["bg_card"], fg=THEME["text_dark"]).pack(side="left")

        role = profile.get("role", "member")
        tk.Label(name_row, text=f"  {ROLE_LABELS.get(role, role)}  ",
                 font=("Arial", 9, "bold"),
                 bg=ROLE_COLORS.get(role, THEME["btn_grey"]),
                 fg=THEME["text_light"]).pack(side="left", padx=(8, 0))

        # bottom line: derby numbers + risk badge
        stats_row = tk.Frame(text_col, bg=THEME["bg_card"])
        stats_row.pack(fill="x", anchor="w", pady=(2, 0))

        tk.Label(stats_row, text=self._stats_text(profile),
                 font=THEME["font_body"], bg=THEME["bg_card"],
                 fg=THEME["text_muted"]).pack(side="left")

        risk = profile.get("risk", derby_planner.RISK_UNKNOWN)
        tk.Label(stats_row,
                 text=f"  {derby_planner.RISK_LABELS.get(risk, risk)}  ",
                 font=("Arial", 9, "bold"),
                 bg=RISK_COLORS.get(risk, THEME["btn_grey"]),
                 fg=THEME["text_light"]).pack(side="left", padx=(8, 0))

    @staticmethod
    def _stats_text(profile: dict) -> str:
        """Compact one-liner of participation / avg / expected points."""
        rate = profile.get("participation_rate")
        avg = profile.get("avg_points")
        exp = profile.get("expected_points")
        rate_s = f"{round(rate * 100)}%" if rate is not None else "–%"
        avg_s = f"{round(avg)}" if avg is not None else "–"
        exp_s = f"{round(exp)}" if exp is not None else "–"
        return f"part {rate_s}   avg {avg_s}   exp {exp_s}"

    # ---- right: prediction + plans ------------------------------------
    def _build_prediction_panel(self, parent):
        frame = tk.Frame(parent, bg=THEME["bg_panel"], bd=2, relief="ridge")

        tk.Label(frame, text="Prediction", font=THEME["font_heading"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]).pack(pady=(6, 4))

        # ----- live prediction figures (updated in _refresh_prediction) -----
        stats = tk.Frame(frame, bg=THEME["bg_panel"])
        stats.pack(fill="x", padx=12, pady=(0, 6))

        self._lbl_points = self._stat_line(stats, "Predicted points")
        self._lbl_ceiling = self._stat_line(stats, "Optimistic ceiling")
        self._lbl_completion = self._stat_line(stats, "Task completion")
        self._lbl_selected = self._stat_line(stats, "Members selected")
        self._lbl_risky = self._stat_line(stats, "Risky / unknown picks")

        # risk member names (wraps onto multiple lines)
        self._lbl_risk_names = tk.Label(
            frame, text="", font=THEME["font_body"],
            bg=THEME["bg_panel"], fg=THEME["text_muted"],
            wraplength=320, justify="left", anchor="w")
        self._lbl_risk_names.pack(fill="x", padx=12, pady=(0, 8))

        # ----- target + auto-pick -----
        target_row = tk.Frame(frame, bg=THEME["bg_panel"])
        target_row.pack(fill="x", padx=12, pady=(4, 2))
        tk.Label(target_row, text="Target points:",
                 font=THEME["font_body_bold"], bg=THEME["bg_panel"],
                 fg=THEME["text_dark"]).pack(side="left")
        self._target_var = tk.StringVar(value="")
        tk.Entry(target_row, textvariable=self._target_var, width=10,
                 font=THEME["font_body"], relief="solid", bd=1
                 ).pack(side="left", padx=(8, 0), ipady=2)

        RoundedButton(frame, text="✨ Auto-pick best lineup",
                      command=self._auto_pick,
                      width=240, height=40,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(pady=(8, 4))

        # target met / not met message
        self._lbl_target_status = tk.Label(
            frame, text="", font=THEME["font_body_bold"],
            bg=THEME["bg_panel"], fg=THEME["text_muted"])
        self._lbl_target_status.pack(pady=(0, 8))

        # ----- saved plans -----
        tk.Frame(frame, bg=THEME["border"], height=2).pack(fill="x", padx=12,
                                                           pady=4)
        tk.Label(frame, text="Saved plans", font=THEME["font_subheading"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]).pack(pady=(2, 4))

        RoundedButton(frame, text="💾 Save current lineup as plan",
                      command=self._save_plan,
                      width=260, height=36,
                      bg_color=THEME["btn_blue"],
                      hover_color=THEME["btn_blue_hover"],
                      font=THEME["font_body_bold"]
                      ).pack(pady=(0, 6))

        # holder we repopulate whenever the plans list changes
        self._plans_holder = tk.Frame(frame, bg=THEME["bg_panel"])
        self._plans_holder.pack(fill="x", padx=12, pady=(0, 10))
        self._refresh_plans()

        return frame

    def _stat_line(self, parent, label: str) -> tk.Label:
        """Create a 'label: value' row, returning the value Label to update."""
        row = tk.Frame(parent, bg=THEME["bg_panel"])
        row.pack(fill="x", pady=1)
        tk.Label(row, text=f"{label}:", font=THEME["font_body"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"]).pack(side="left")
        value = tk.Label(row, text="–", font=THEME["font_body_bold"],
                         bg=THEME["bg_panel"], fg=THEME["text_dark"])
        value.pack(side="right")
        return value

    # =================================================================
    # selection helpers
    # =================================================================
    def _selected_ids(self) -> list:
        """member_ids whose checkbox is currently ticked, in roster order."""
        return [mid for mid, var in self._check_vars.items() if var.get()]

    def _parse_target(self):
        """Return the target as an int, or None if blank/invalid."""
        raw = self._target_var.get().strip()
        if not raw:
            return None
        try:
            value = int(raw)
        except ValueError:
            return None
        return value if value >= 0 else None

    # =================================================================
    # actions
    # =================================================================
    def _auto_pick(self):
        """Run the recommender and tick the recommended members' boxes."""
        target = self._parse_target()
        result = derby_planner.recommend_lineup(self.data, target_points=target)
        recommended = set(result["selected"])

        if not recommended:
            messagebox.showinfo(
                "Nothing to recommend",
                "No members have enough derby history to build a lineup yet.")
            return

        for mid, var in self._check_vars.items():
            var.set(mid in recommended)
        self._refresh_prediction()

    def _save_plan(self):
        """Prompt for a name and persist the current lineup as a saved plan."""
        selected = self._selected_ids()
        if not selected:
            messagebox.showinfo("No members selected",
                                "Tick at least one member before saving a plan.")
            return

        name = simpledialog.askstring("Save plan", "Plan name:", parent=self)
        if not name or not name.strip():
            return

        try:
            derby_planner.add_derby_plan(
                self.data, name, selected,
                target_points=self._parse_target())
        except ValueError as exc:
            messagebox.showerror("Could not save plan", str(exc))
            return

        self.nm.save(self.clan, self.data)
        self._refresh_plans()

    def _load_plan(self, plan: dict):
        """Tick exactly the members stored in this plan, restore its target."""
        wanted = set(plan.get("member_ids", []))
        for mid, var in self._check_vars.items():
            var.set(mid in wanted)
        target = plan.get("target_points")
        self._target_var.set("" if target is None else str(target))
        self._refresh_prediction()

    def _delete_plan(self, plan: dict):
        if not messagebox.askyesno(
                "Delete plan",
                f"Delete the saved plan '{plan.get('name', '')}'?"):
            return
        try:
            derby_planner.delete_derby_plan(self.data, plan["plan_id"])
        except ValueError as exc:
            messagebox.showerror("Could not delete plan", str(exc))
            return
        self.nm.save(self.clan, self.data)
        self._refresh_plans()

    # =================================================================
    # rendering
    # =================================================================
    def _refresh_prediction(self):
        """Recompute the lineup prediction and update the right-panel labels."""
        selected = self._selected_ids()
        pred = derby_planner.predict_lineup(self.data, selected)

        self._lbl_points.config(text=str(round(pred["predicted_points"])))
        self._lbl_ceiling.config(
            text=str(round(pred["predicted_points_optimistic"])))

        completion = pred["predicted_completion"]
        self._lbl_completion.config(
            text=f"{round(completion * 100)}%" if completion is not None
            else "–")

        self._lbl_selected.config(text=str(pred["n_selected"]))

        n_risk = len(pred["risk_members"])
        self._lbl_risky.config(text=str(n_risk))

        # resolve risk member ids to readable names
        if pred["risk_members"]:
            members = self.data.get("members", {})
            names = [members.get(mid, {}).get("name", mid)
                     for mid in pred["risk_members"]]
            self._lbl_risk_names.config(text="Risk picks: " + ", ".join(names))
        else:
            self._lbl_risk_names.config(text="No risky or unknown picks.")

        self._refresh_target_status(pred)

    def _refresh_target_status(self, prediction: dict):
        """Show whether the current prediction meets the entered target."""
        target = self._parse_target()
        if target is None:
            self._lbl_target_status.config(text="", fg=THEME["text_muted"])
            return
        predicted = prediction["predicted_points"]
        if predicted >= target:
            self._lbl_target_status.config(
                text=f"✓ Target met ({round(predicted)} ≥ {target})",
                fg=THEME["text_ok"])
        else:
            self._lbl_target_status.config(
                text=f"✗ Below target ({round(predicted)} < {target})",
                fg=THEME["text_warning"])

    def _refresh_plans(self):
        """Rebuild the saved-plans list (each row: name + Load + Delete)."""
        for child in self._plans_holder.winfo_children():
            child.destroy()

        plans = derby_planner.list_derby_plans(self.data)
        if not plans:
            tk.Label(self._plans_holder, text="No saved plans yet.",
                     font=THEME["font_body"], bg=THEME["bg_panel"],
                     fg=THEME["text_muted"]).pack(anchor="w")
            return

        for plan in plans:
            row = tk.Frame(self._plans_holder, bg=THEME["bg_card"],
                           bd=1, relief="solid")
            row.pack(fill="x", pady=2)

            # name + member count, left-aligned
            count = len(plan.get("member_ids", []))
            label = f"{plan.get('name', '(unnamed)')}  ({count})"
            tk.Label(row, text=label, font=THEME["font_body_bold"],
                     bg=THEME["bg_card"], fg=THEME["text_dark"]
                     ).pack(side="left", padx=8, pady=4)

            RoundedButton(row, text="Delete",
                          command=lambda p=plan: self._delete_plan(p),
                          width=70, height=28,
                          bg_color=THEME["btn_red"],
                          hover_color=THEME["btn_red_hover"],
                          font=("Arial", 10, "bold"), radius=8
                          ).pack(side="right", padx=(2, 6), pady=4)
            RoundedButton(row, text="Load",
                          command=lambda p=plan: self._load_plan(p),
                          width=70, height=28,
                          bg_color=THEME["btn_green"],
                          hover_color=THEME["btn_green_hover"],
                          font=("Arial", 10, "bold"), radius=8
                          ).pack(side="right", padx=2, pady=4)
