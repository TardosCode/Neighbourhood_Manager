"""
Members tab.

Lists all members in the clan database, sorted by current level (highest first).
Lets the leader add, edit, delete, and toggle the in-clan flag for each.

Includes search and filter controls:
  - Search box matches name or tag (substring, case-insensitive)
  - Activity filter: toggle which statuses to show (Inactive/Below/On track/New)
  - Show former members on/off

Each row shows the member's role (with a colored chip + a soft tint
applied to the row background) and current activity-score total.
"""

import tkinter as tk
from tkinter import messagebox

from theme import (
    THEME, ACTIVITY_STATUS_COLORS,
    ROLES_ORDER, ROLE_LABELS, ROLE_COLORS, ROLE_ROW_TINTS,
    ROLE_MEMBER,
)
from widgets import RoundedButton, LabeledEntry
from ui_widgets_extra import SearchBox, attach_smooth_mousewheel
from neighborhood_manager import (
    add_member, update_member, delete_member, MAX_CLAN_SIZE,
    latest_levels, latest_snapshot_date_for_member,
    latest_fate_for_member, VALID_ROLES,
    ACTIVITY_NEW_MEMBER, ACTIVITY_INACTIVE, ACTIVITY_BELOW_TARGET,
    ACTIVITY_MEETING_TARGET, ACTIVITY_NO_RULE,
    get_ui_pref, set_ui_pref,
)
from clan_stats import member_activity_status
from activity_score import compute_scores


class MembersTab(tk.Frame):
    def __init__(self, parent, manager):
        super().__init__(parent, bg=THEME["bg_main"])
        self.manager = manager
        self.data = manager.reload_data()

        # cached score totals so each row doesn't recompute from scratch
        self._scores_by_id = {}

        # filter state - show_former is persisted on the clan data
        self.search_query = ""
        self.show_former = bool(get_ui_pref(self.data, "members.show_former",
                                              False))
        # activity filter: dict of status -> bool. all on by default.
        self.show_status = {
            ACTIVITY_INACTIVE: True,
            ACTIVITY_BELOW_TARGET: True,
            ACTIVITY_MEETING_TARGET: True,
            ACTIVITY_NEW_MEMBER: True,
            ACTIVITY_NO_RULE: True,
        }

        self._build_toolbar()
        self._build_filter_bar()
        self._build_table()

    # ---- toolbar ---------------------------------------------------------
    def _build_toolbar(self):
        bar = tk.Frame(self, bg=THEME["bg_main"])
        bar.pack(side="top", fill="x", padx=20, pady=(10, 6))

        RoundedButton(bar, text="+  Add member",
                      command=self._add_member_dialog,
                      width=160, height=40,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="left")

        active = sum(1 for m in self.data["members"].values() if m["in_clan"])
        total = len(self.data["members"])
        info = f"In clan: {active}/{MAX_CLAN_SIZE}   •   In database: {total}"
        tk.Label(bar, text=info, font=THEME["font_body_bold"],
                 bg=THEME["bg_main"], fg=THEME["text_muted"]
                 ).pack(side="right", padx=10)

    # ---- filter bar (search + activity multi-select + former toggle) ----
    def _build_filter_bar(self):
        bar = tk.Frame(self, bg=THEME["bg_panel"], bd=1, relief="ridge")
        bar.pack(side="top", fill="x", padx=20, pady=(0, 6))

        SearchBox(bar,
                  on_change=self._on_search_change,
                  placeholder="Search by name or tag…",
                  width=22,
                  bg=THEME["bg_panel"]
                  ).pack(side="left", padx=(8, 12), pady=8)

        # activity status filter — colored toggle pills
        tk.Label(bar, text="Activity:",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(side="left", padx=(8, 4))

        self._status_toggle_buttons = {}
        for status, label, color in [
            (ACTIVITY_INACTIVE, "Inactive", ACTIVITY_STATUS_COLORS["inactive"]),
            (ACTIVITY_BELOW_TARGET, "Below", ACTIVITY_STATUS_COLORS["below"]),
            (ACTIVITY_MEETING_TARGET, "On track", ACTIVITY_STATUS_COLORS["meeting"]),
            (ACTIVITY_NEW_MEMBER, "New", ACTIVITY_STATUS_COLORS["new"]),
        ]:
            btn = tk.Label(bar, text=f"  {label}  ",
                            font=("Arial", 10, "bold"),
                            bg=color, fg="white",
                            padx=6, pady=4, cursor="hand2",
                            bd=2, relief="raised")
            btn.pack(side="left", padx=2, pady=8)
            btn.bind("<Button-1>",
                      lambda _e, s=status: self._toggle_status_filter(s))
            self._status_toggle_buttons[status] = (btn, color)

        # show former members
        self.var_show_former = tk.BooleanVar(value=self.show_former)
        tk.Checkbutton(bar, text="Show former members",
                       variable=self.var_show_former,
                       command=self._on_former_toggle,
                       font=THEME["font_body_bold"],
                       bg=THEME["bg_panel"], fg=THEME["text_dark"],
                       activebackground=THEME["bg_panel"],
                       selectcolor=THEME["bg_card"]
                       ).pack(side="right", padx=12, pady=8)

    def _on_search_change(self, query):
        self.search_query = query.strip().lower()
        self._refresh_rows()

    def _on_former_toggle(self):
        self.show_former = self.var_show_former.get()
        # persist preference on clan data so it sticks across tab switches
        # and app restarts
        set_ui_pref(self.data, "members.show_former", self.show_former)
        self.manager.save_data(self.data)
        self._refresh_rows()

    def _toggle_status_filter(self, status):
        self.show_status[status] = not self.show_status[status]
        # update visual appearance: raised + full color = on, sunken + grey = off
        btn, color = self._status_toggle_buttons[status]
        if self.show_status[status]:
            btn.config(bg=color, fg="white", relief="raised")
        else:
            btn.config(bg=THEME["btn_disabled"], fg=THEME["text_muted"],
                       relief="sunken")
        self._refresh_rows()

    def _refresh_rows(self):
        if hasattr(self, "body"):
            for child in self.body.winfo_children():
                child.destroy()
            self._populate_rows()

    # ---- table -----------------------------------------------------------
    def _build_table(self):
        # outer frame with scrollbar
        wrap = tk.Frame(self, bg=THEME["bg_main"])
        wrap.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        # column headers
        header = tk.Frame(wrap, bg=THEME["bg_top"], bd=1, relief="solid")
        header.pack(fill="x")
        self._make_header_cell(header, "#", 45)
        self._make_header_cell(header, "Lv", 50)
        self._make_header_cell(header, "Name", 200)
        self._make_header_cell(header, "Tag", 100)
        self._make_header_cell(header, "Role", 100)
        self._make_header_cell(header, "In clan", 60)
        self._make_header_cell(header, "Activity", 110)
        self._make_header_cell(header, "Score", 60)
        self._make_header_cell(header, "Last update", 100)
        self._make_header_cell(header, "Fate", 70)
        self._make_header_cell(header, "Actions", 230)

        # scrollable body
        body_wrap = tk.Frame(wrap, bg=THEME["bg_main"])
        body_wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(body_wrap, bg=THEME["bg_main"],
                           highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(body_wrap, orient="vertical",
                                 command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.body = tk.Frame(canvas, bg=THEME["bg_main"])
        canvas_window = canvas.create_window((0, 0), window=self.body, anchor="nw")

        def _on_body_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        self.body.bind("<Configure>", _on_body_configure)

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        # smooth mouse wheel scrolling
        attach_smooth_mousewheel(canvas)

        self._populate_rows()

    def _make_header_cell(self, parent, text: str, width: int):
        f = tk.Frame(parent, bg=THEME["bg_top"], width=width, height=34)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Label(f, text=text, font=THEME["font_body_bold"],
                 bg=THEME["bg_top"], fg=THEME["text_dark"]).pack(expand=True)

    def _populate_rows(self):
        levels = latest_levels(self.data)

        # compute scores once for the whole clan, then index by member_id
        self._scores_by_id = {}
        try:
            for row in compute_scores(self.data, include_former=False):
                self._scores_by_id[row["member_id"]] = row["total"]
        except Exception as e:
            print(f"[MembersTab] activity score compute failed: {e}")

        members = list(self.data["members"].values())
        members.sort(key=lambda m: (
            not m["in_clan"],
            -(levels.get(m["member_id"], 0)),
            m["name"].lower(),
        ))

        # apply filters
        q = self.search_query
        filtered = []
        for m in members:
            # former members toggle
            if not m["in_clan"] and not self.show_former:
                continue
            # search match (name or tag)
            if q and (q not in m["name"].lower()
                      and q not in m["member_id"].lower()):
                continue
            # activity status filter (only meaningful for in-clan members;
            # former members show "—" so they're not affected)
            if m["in_clan"]:
                info = member_activity_status(self.data, m["member_id"])
                status = info["status"]
                if not self.show_status.get(status, True):
                    continue
            filtered.append(m)

        if not filtered:
            if q or not all(self.show_status.values()) or not self.show_former:
                msg = "No members match the current filters / search."
            else:
                msg = "No members yet. Click \"Add member\" to start."
            tk.Label(self.body, text=msg,
                     font=THEME["font_body"], bg=THEME["bg_main"],
                     fg=THEME["text_muted"]).pack(pady=40)
            return

        for i, m in enumerate(filtered):
            self._build_row(m, levels, row_index=i)

    def _build_row(self, member: dict, levels: dict, row_index: int):
        # default alternating bg
        default_bg = THEME["bg_card"] if row_index % 2 == 0 else THEME["bg_panel"]
        # role-based tint takes priority for in-clan members
        role = member.get("role", ROLE_MEMBER)
        if member["in_clan"]:
            tint = ROLE_ROW_TINTS.get(role)
            bg = tint if tint else default_bg
        else:
            bg = default_bg
        text_color = THEME["text_dark"] if member["in_clan"] else THEME["text_muted"]

        row = tk.Frame(self.body, bg=bg, bd=1, relief="solid")
        row.pack(fill="x")

        # ----- rank number cell -----
        # rank is 1-indexed and counts from current filtered list. Former
        # members are sorted to the bottom by _populate_rows so they
        # naturally pick up numbers above the in-clan ones.
        rank_str = f"#{row_index + 1}"
        self._make_cell(row, rank_str, 45, bg=bg,
                        fg=THEME["btn_blue"] if member["in_clan"]
                           else THEME["text_muted"],
                        font=("Arial", 10, "bold"))

        level = levels.get(member["member_id"])
        level_str = str(level) if level is not None else "—"

        self._make_cell(row, level_str, 50, bg=bg, fg=text_color,
                        font=THEME["font_body_bold"])
        self._make_cell(row, member["name"], 200, bg=bg, fg=text_color,
                        anchor="w", padx=8)
        self._make_cell(row, member["member_id"], 100, bg=bg, fg=text_color,
                        font=("Consolas", 10))

        # ----- Role chip -----
        role_color = ROLE_COLORS.get(role, ROLE_COLORS[ROLE_MEMBER])
        role_label = ROLE_LABELS.get(role, ROLE_LABELS[ROLE_MEMBER])
        role_cell = tk.Frame(row, bg=bg, width=100, height=44)
        role_cell.pack(side="left")
        role_cell.pack_propagate(False)
        tk.Label(role_cell, text=f"  {role_label}  ",
                 font=("Arial", 10, "bold"),
                 bg=role_color, fg=THEME["text_light"], padx=4, pady=2
                 ).pack(expand=True)

        # ----- in clan ✓/— -----
        self._make_cell(row, "✓" if member["in_clan"] else "—",
                        60, bg=bg,
                        fg=THEME["text_ok"] if member["in_clan"]
                           else THEME["text_muted"],
                        font=THEME["font_body_bold"])

        # ----- Activity status chip (in-clan members only) -----
        if member["in_clan"]:
            info = member_activity_status(self.data, member["member_id"])
            chip_map = {
                ACTIVITY_NEW_MEMBER:     ("New", ACTIVITY_STATUS_COLORS["new"]),
                ACTIVITY_INACTIVE:       ("Inactive", ACTIVITY_STATUS_COLORS["inactive"]),
                ACTIVITY_BELOW_TARGET:   ("Below", ACTIVITY_STATUS_COLORS["below"]),
                ACTIVITY_MEETING_TARGET: ("On track", ACTIVITY_STATUS_COLORS["meeting"]),
                ACTIVITY_NO_RULE:        ("No rule", ACTIVITY_STATUS_COLORS["no_rule"]),
            }
            chip_text, chip_color = chip_map.get(info["status"],
                                                  ("?", ACTIVITY_STATUS_COLORS["new"]))
            chip_cell = tk.Frame(row, bg=bg, width=110, height=44)
            chip_cell.pack(side="left")
            chip_cell.pack_propagate(False)
            tk.Label(chip_cell, text=f"  {chip_text}  ",
                     font=THEME["font_body_bold"],
                     bg=chip_color, fg=THEME["text_light"], padx=4, pady=2
                     ).pack(expand=True)
        else:
            self._make_cell(row, "—", 110, bg=bg, fg=THEME["text_muted"])

        # ----- Activity score (computed once per refresh, cached on self) ---
        score_total = self._scores_by_id.get(member["member_id"], 0)
        if member["in_clan"] and score_total > 0:
            self._make_cell(row, str(score_total), 60, bg=bg,
                            fg=THEME["text_dark"],
                            font=("Arial Black", 12, "bold"))
        elif member["in_clan"]:
            self._make_cell(row, "0", 60, bg=bg, fg=THEME["text_muted"])
        else:
            self._make_cell(row, "—", 60, bg=bg, fg=THEME["text_muted"])

        last = latest_snapshot_date_for_member(self.data, member["member_id"])
        self._make_cell(row, last or "never", 100, bg=bg, fg=text_color)

        fate = latest_fate_for_member(self.data, member["member_id"])
        if fate:
            fate_color = {
                "stay": THEME["text_ok"],
                "warning": ACTIVITY_STATUS_COLORS["below"],
                "kick": THEME["text_warning"],
            }.get(fate, text_color)
            self._make_cell(row, fate, 70, bg=bg, fg=fate_color,
                            font=THEME["font_body_bold"])
        else:
            self._make_cell(row, "—", 70, bg=bg, fg=THEME["text_muted"])

        # actions cell - Details / Edit / Delete
        actions = tk.Frame(row, bg=bg, width=230, height=44)
        actions.pack(side="left")
        actions.pack_propagate(False)
        RoundedButton(actions, text="Details",
                      command=lambda mid=member["member_id"]:
                                  self._open_details(mid),
                      width=72, height=28,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"],
                      font=("Arial", 10, "bold"), radius=8
                      ).pack(side="left", padx=(6, 4), pady=8)
        RoundedButton(actions, text="Edit",
                      command=lambda mid=member["member_id"]:
                                  self._edit_member_dialog(mid),
                      width=54, height=28,
                      bg_color=THEME["btn_blue"],
                      hover_color=THEME["btn_blue_hover"],
                      font=("Arial", 10, "bold"), radius=8
                      ).pack(side="left", padx=4, pady=8)
        RoundedButton(actions, text="Delete",
                      command=lambda mid=member["member_id"]:
                                  self._delete_member(mid),
                      width=68, height=28,
                      bg_color=THEME["btn_red"],
                      hover_color=THEME["btn_red_hover"],
                      font=("Arial", 10, "bold"), radius=8
                      ).pack(side="left", padx=4, pady=8)

    def _make_cell(self, parent, text: str, width: int, bg: str,
                   fg: str = None, font=None, anchor="center", padx=0):
        f = tk.Frame(parent, bg=bg, width=width, height=44)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Label(f, text=text, font=font or THEME["font_body"],
                 bg=bg, fg=fg or THEME["text_dark"], anchor=anchor
                 ).pack(fill="both", expand=True, padx=padx)

    # ---- add / edit dialogs ----------------------------------------------
    def _add_member_dialog(self):
        MemberFormDialog(self, mode="add", manager=self.manager)

    def _edit_member_dialog(self, member_id: str):
        MemberFormDialog(self, mode="edit", manager=self.manager,
                         member_id=member_id)

    def _open_details(self, member_id: str):
        self.manager.app.show_frame("MemberDetail", member_id=member_id)

    def _delete_member(self, member_id: str):
        member = self.data["members"][member_id]
        if not messagebox.askyesno(
                "Delete member",
                f"Delete '{member['name']}' ({member_id}) from the database?\n\n"
                "This will also remove this member's entries from ALL snapshots.\n"
                "This cannot be undone."):
            return
        delete_member(self.data, member_id)
        self.manager.save_data(self.data)
        self.manager.refresh_top_bar()


# ---------- add / edit dialog ------------------------------------------------

class MemberFormDialog(tk.Toplevel):
    """Modal dialog for adding or editing a member."""

    def __init__(self, parent, mode: str, manager, member_id: str = None):
        # The manager is a stable, long-lived widget; the parent (a tab) gets
        # rebuilt on every refresh which would invalidate this dialog's parent.
        super().__init__(manager)
        self.parent = parent
        self.manager = manager
        self.mode = mode
        self.member_id = member_id

        self.title("Add member" if mode == "add" else "Edit member")
        self.configure(bg=THEME["bg_main"])
        self.resizable(False, False)
        self.transient(manager)
        self.grab_set()

        self.data = manager.reload_data()

        body = tk.Frame(self, bg=THEME["bg_panel"], padx=20, pady=20)
        body.pack(padx=10, pady=10)

        self.entry_name = LabeledEntry(body, "Display name (in-game)", width=30)
        self.entry_name.pack(fill="x", pady=4)

        self.entry_tag = LabeledEntry(body, "Player tag (e.g. #ABC123) — primary key, can't change later",
                                      width=30)
        self.entry_tag.pack(fill="x", pady=4)

        # in-clan checkbox
        cb_frame = tk.Frame(body, bg=THEME["bg_panel"])
        cb_frame.pack(fill="x", pady=8)
        self.var_in_clan = tk.BooleanVar(value=True)
        cb = tk.Checkbutton(cb_frame, text="Currently in the neighborhood",
                            variable=self.var_in_clan,
                            font=THEME["font_body_bold"],
                            bg=THEME["bg_panel"], fg=THEME["text_dark"],
                            activebackground=THEME["bg_panel"])
        cb.pack(side="left")

        # Role picker
        role_frame = tk.Frame(body, bg=THEME["bg_panel"])
        role_frame.pack(fill="x", pady=(8, 4))
        tk.Label(role_frame, text="Role",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(side="left")
        self.var_role = tk.StringVar(value=ROLE_LABELS[ROLE_MEMBER])
        role_choices = [ROLE_LABELS[r] for r in ROLES_ORDER]
        om = tk.OptionMenu(role_frame, self.var_role, *role_choices)
        om.config(font=THEME["font_body"], bg=THEME["bg_panel"])
        om.pack(side="left", padx=(8, 0))

        # notes
        tk.Label(body, text="Notes (optional)",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(anchor="w", pady=(8, 0))
        self.txt_notes = tk.Text(body, height=4, width=40,
                                 font=THEME["font_body"],
                                 relief="solid", bd=1)
        self.txt_notes.pack(fill="x", pady=4)

        # if editing, prefill
        if mode == "edit":
            m = self.data["members"][member_id]
            self.entry_name.set(m["name"])
            self.entry_tag.set(m["member_id"])
            self.entry_tag.entry.config(state="disabled")  # tag is the primary key
            self.var_in_clan.set(m["in_clan"])
            self.txt_notes.insert("1.0", m.get("notes", ""))
            current_role = m.get("role", ROLE_MEMBER)
            self.var_role.set(ROLE_LABELS.get(current_role, ROLE_LABELS[ROLE_MEMBER]))

        # buttons
        btns = tk.Frame(body, bg=THEME["bg_panel"])
        btns.pack(pady=(15, 0))
        RoundedButton(btns, text="Save",
                      command=self._save,
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

        # center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_reqwidth()) // 2
        y = (self.winfo_screenheight() - self.winfo_reqheight()) // 2
        self.geometry(f"+{x}+{y}")

        self.entry_name.entry.focus_set()

    def _save(self):
        name = self.entry_name.get().strip()
        tag = self.entry_tag.get().strip()
        in_clan = self.var_in_clan.get()
        notes = self.txt_notes.get("1.0", tk.END).strip()

        # convert role label back to role id
        role_label = self.var_role.get()
        role_id = ROLE_MEMBER
        for rid, rlabel in ROLE_LABELS.items():
            if rlabel == role_label:
                role_id = rid
                break

        if not name:
            messagebox.showerror("Invalid", "Name is required.", parent=self)
            return
        if not tag:
            messagebox.showerror("Invalid", "Player tag is required.", parent=self)
            return

        try:
            if self.mode == "add":
                add_member(self.data, member_id=tag, name=name,
                           in_clan=in_clan, notes=notes, role=role_id)
            else:
                update_member(self.data, member_id=self.member_id,
                              name=name, in_clan=in_clan, notes=notes,
                              role=role_id)
        except ValueError as e:
            messagebox.showerror("Cannot save", str(e), parent=self)
            return

        self.manager.save_data(self.data)
        self.destroy()
        self.manager.refresh_top_bar()
