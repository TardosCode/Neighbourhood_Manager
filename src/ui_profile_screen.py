"""
Profile screen: list / create / edit / delete / activate profiles.

Used in two situations:
- First run (no profiles yet) -> user MUST create one to continue
- Anytime via the profile button in the top bar
"""

import tkinter as tk
from tkinter import messagebox, simpledialog

from theme import THEME
from widgets import RoundedButton, LabeledEntry
from profile_manager import default_profile_data
from game_logic import (
    INITIAL_CAPACITY, BARN_MAX_CAPACITY, is_valid_capacity,
)


class ProfileScreen(tk.Frame):
    def __init__(self, parent, app, first_run: bool = False, return_to: str = "MainMenu"):
        super().__init__(parent, bg=THEME["bg_main"])
        self.app = app
        self.first_run = first_run
        self.return_to = return_to
        self.pm = app.profile_manager
        self.selected_profile = None  # currently highlighted in the listbox

        # ---- top bar ------------------------------------------------------
        top = tk.Frame(self, bg=THEME["bg_top"], height=60)
        top.pack(side="top", fill="x")
        top.pack_propagate(False)

        if not first_run:
            RoundedButton(top, text="← Back",
                          command=self._go_back,
                          width=100, height=40,
                          bg_color=THEME["btn_green"],
                          hover_color=THEME["btn_green_hover"]
                          ).pack(side="left", padx=15, pady=10)

        tk.Label(top, text="Profiles" + (" — please create one to start" if first_run else ""),
                 font=THEME["font_title"],
                 bg=THEME["bg_top"], fg=THEME["text_dark"]).pack(side="left", padx=20)

        # ---- main area: two columns --------------------------------------
        body = tk.Frame(self, bg=THEME["bg_main"])
        body.pack(fill="both", expand=True, padx=20, pady=20)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        # LEFT: profile list
        left = tk.Frame(body, bg=THEME["bg_panel"], bd=2, relief="ridge")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        tk.Label(left, text="Saved profiles", font=THEME["font_subheading"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]).pack(pady=(10, 6))

        list_wrap = tk.Frame(left, bg=THEME["bg_panel"])
        list_wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.listbox = tk.Listbox(list_wrap, font=THEME["font_body_bold"],
                                  activestyle="dotbox", bd=1, relief="solid",
                                  selectbackground=THEME["btn_green"],
                                  selectforeground=THEME["text_light"])
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar = tk.Scrollbar(list_wrap, command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        list_btns = tk.Frame(left, bg=THEME["bg_panel"])
        list_btns.pack(fill="x", padx=10, pady=(0, 10))
        RoundedButton(list_btns, text="Use this", command=self._use_selected,
                      width=130, height=38,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]).pack(side="left", padx=(0, 6))
        RoundedButton(list_btns, text="Delete", command=self._delete_selected,
                      width=110, height=38,
                      bg_color=THEME["btn_red"],
                      hover_color=THEME["btn_red_hover"]).pack(side="left")

        # RIGHT: form for creating/editing
        right = tk.Frame(body, bg=THEME["bg_panel"], bd=2, relief="ridge")
        right.grid(row=0, column=1, sticky="nsew")

        tk.Label(right, text="Create or edit profile", font=THEME["font_subheading"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]).pack(pady=(10, 10))

        form = tk.Frame(right, bg=THEME["bg_panel"])
        form.pack(padx=20, pady=10, fill="x")

        self.entry_profile_name = LabeledEntry(form, "Profile name (used for filename)",
                                               default="")
        self.entry_profile_name.pack(fill="x", pady=4)

        self.entry_player_name = LabeledEntry(form, "Player name (in-game)")
        self.entry_player_name.pack(fill="x", pady=4)

        self.entry_player_tag = LabeledEntry(form, "Player tag (e.g. #ABC123)")
        self.entry_player_tag.pack(fill="x", pady=4)

        self.entry_player_level = LabeledEntry(form, "Player level", default="1")
        self.entry_player_level.pack(fill="x", pady=4)

        self.entry_silo_capacity = LabeledEntry(form, f"Silo capacity (start: {INITIAL_CAPACITY})",
                                                default=str(INITIAL_CAPACITY))
        self.entry_silo_capacity.pack(fill="x", pady=4)

        self.entry_barn_capacity = LabeledEntry(form, f"Barn capacity (start: {INITIAL_CAPACITY})",
                                                default=str(INITIAL_CAPACITY))
        self.entry_barn_capacity.pack(fill="x", pady=4)

        # action buttons
        action_btns = tk.Frame(right, bg=THEME["bg_panel"])
        action_btns.pack(pady=20)
        RoundedButton(action_btns, text="Save as new",
                      command=self._save_as_new,
                      width=160, height=44,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]).pack(side="left", padx=6)
        self.btn_update = RoundedButton(action_btns, text="Update selected",
                                         command=self._update_selected,
                                         width=180, height=44,
                                         bg_color=THEME["btn_blue"],
                                         hover_color=THEME["btn_blue_hover"],
                                         disabled=True)
        self.btn_update.pack(side="left", padx=6)
        RoundedButton(action_btns, text="Clear form",
                      command=self._clear_form,
                      width=140, height=44,
                      bg_color=THEME["btn_grey"],
                      hover_color=THEME["btn_grey_hover"]).pack(side="left", padx=6)

        self._refresh_list()

    # ---- helpers ----------------------------------------------------------

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for name in self.pm.list_profiles():
            label = name
            if name == self.pm.get_active_profile():
                label += "  ★"  # mark the active profile
            self.listbox.insert(tk.END, label)

    def _selected_name(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        text = self.listbox.get(sel[0])
        return text.replace("  ★", "").strip()

    def _on_select(self, _event=None):
        name = self._selected_name()
        if name is None:
            return
        self.selected_profile = name
        try:
            data = self.pm.load(name)
        except (OSError, ValueError):
            return
        self.entry_profile_name.set(name)
        self.entry_player_name.set(data.get("player_name", ""))
        self.entry_player_tag.set(data.get("player_tag", ""))
        self.entry_player_level.set(str(data.get("player_level", 1)))
        self.entry_silo_capacity.set(str(data.get("silo", {}).get("capacity", INITIAL_CAPACITY)))
        self.entry_barn_capacity.set(str(data.get("barn", {}).get("capacity", INITIAL_CAPACITY)))
        self.btn_update.set_disabled(False)

    def _clear_form(self):
        self.selected_profile = None
        self.entry_profile_name.set("")
        self.entry_player_name.set("")
        self.entry_player_tag.set("")
        self.entry_player_level.set("1")
        self.entry_silo_capacity.set(str(INITIAL_CAPACITY))
        self.entry_barn_capacity.set(str(INITIAL_CAPACITY))
        self.btn_update.set_disabled(True)
        self.listbox.selection_clear(0, tk.END)

    # ---- form validation --------------------------------------------------

    def _read_form(self):
        """Validate inputs and return a dict with parsed fields, or None on error."""
        name = self.entry_profile_name.get()
        if not name:
            messagebox.showerror("Invalid", "Profile name is required.")
            return None

        try:
            level = int(self.entry_player_level.get() or "1")
            if level < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid", "Player level must be a positive integer.")
            return None

        try:
            silo_cap = int(self.entry_silo_capacity.get())
        except ValueError:
            messagebox.showerror("Invalid", "Silo capacity must be a number.")
            return None
        if not is_valid_capacity(silo_cap):
            messagebox.showerror(
                "Invalid",
                f"Silo capacity {silo_cap} is not a valid Hay Day value.\n"
                f"Allowed: {INITIAL_CAPACITY}, 75, 100, ... 1000, 1050, 1100, ..."
            )
            return None

        try:
            barn_cap = int(self.entry_barn_capacity.get())
        except ValueError:
            messagebox.showerror("Invalid", "Barn capacity must be a number.")
            return None
        if not is_valid_capacity(barn_cap):
            messagebox.showerror(
                "Invalid",
                f"Barn capacity {barn_cap} is not a valid Hay Day value."
            )
            return None
        if barn_cap > BARN_MAX_CAPACITY:
            messagebox.showerror(
                "Invalid",
                f"Barn capacity cannot exceed {BARN_MAX_CAPACITY}."
            )
            return None

        return {
            "profile_name": name,
            "player_name": self.entry_player_name.get(),
            "player_tag": self.entry_player_tag.get(),
            "player_level": level,
            "silo_capacity": silo_cap,
            "barn_capacity": barn_cap,
        }

    # ---- actions ----------------------------------------------------------

    def _save_as_new(self):
        form = self._read_form()
        if form is None:
            return
        if self.pm.profile_exists(form["profile_name"]):
            messagebox.showerror("Already exists",
                                 f"A profile named '{form['profile_name']}' already exists.\n"
                                 "Pick another name or use 'Update selected'.")
            return
        data = default_profile_data(
            player_name=form["player_name"],
            player_tag=form["player_tag"],
            player_level=form["player_level"],
            silo_capacity=form["silo_capacity"],
            barn_capacity=form["barn_capacity"],
        )
        self.pm.create(form["profile_name"], data)
        # if this is the first profile, mark it active automatically
        if self.pm.get_active_profile() is None:
            self.pm.set_active_profile(form["profile_name"])
        messagebox.showinfo("Saved", f"Profile '{form['profile_name']}' saved.")
        self._refresh_list()
        self._clear_form()

    def _update_selected(self):
        if self.selected_profile is None:
            messagebox.showinfo("No selection", "Pick a profile from the list first.")
            return
        form = self._read_form()
        if form is None:
            return

        # load existing so we keep item counts and daily limit
        data = self.pm.load(self.selected_profile)
        data["player_name"] = form["player_name"]
        data["player_tag"] = form["player_tag"]
        data["player_level"] = form["player_level"]

        # if the user changed capacities manually, accept the new values
        # (they might have upgraded outside the app)
        data["silo"]["capacity"] = form["silo_capacity"]
        data["barn"]["capacity"] = form["barn_capacity"]

        new_name = form["profile_name"]
        if new_name != self.selected_profile:
            # rename: make sure target doesn't exist
            if self.pm.profile_exists(new_name):
                messagebox.showerror("Conflict",
                                     f"A profile named '{new_name}' already exists.")
                return
            # save under new name, then remove old
            self.pm.save(new_name, data)
            # rename helper handles active-profile pointer too
            try:
                self.pm.delete(self.selected_profile)
            except OSError:
                pass
            self.selected_profile = new_name
        else:
            self.pm.save(self.selected_profile, data)

        messagebox.showinfo("Updated", f"Profile '{self.selected_profile}' updated.")
        self._refresh_list()

    def _use_selected(self):
        name = self._selected_name()
        if name is None:
            messagebox.showinfo("No selection", "Pick a profile from the list first.")
            return
        self.pm.set_active_profile(name)
        # go to the helper screen (or back to main menu if already there)
        self.app.show_frame("MainMenu")

    def _delete_selected(self):
        name = self._selected_name()
        if name is None:
            messagebox.showinfo("No selection", "Pick a profile from the list first.")
            return
        if not messagebox.askyesno("Delete profile",
                                    f"Are you sure you want to delete '{name}'?\n"
                                    "This cannot be undone."):
            return
        self.pm.delete(name)
        self._refresh_list()
        self._clear_form()

    # ---- navigation -------------------------------------------------------

    def _go_back(self):
        if self.pm.get_active_profile() is None:
            messagebox.showinfo("Profile required",
                                "Please create and select a profile first.")
            return
        self.app.show_frame(self.return_to)
