"""
Neighborhood selector screen.

Used in two situations:
- "Choose / create a neighborhood" before opening the manager
- Anytime you want to switch clans

Mirrors the profile screen but for clans. Independent of player profile.
"""

import tkinter as tk
from tkinter import messagebox

from theme import THEME
from widgets import RoundedButton, LabeledEntry
from neighborhood_manager import default_neighborhood_data


class NeighborhoodSelectorScreen(tk.Frame):
    def __init__(self, parent, app, return_to: str = "MainMenu",
                 first_run: bool = False):
        super().__init__(parent, bg=THEME["bg_main"])
        self.app = app
        self.nm = app.neighborhood_manager
        self.return_to = return_to
        self.first_run = first_run
        self.selected_clan = None

        self._build_top_bar()
        self._build_body()
        self._refresh_list()

    # ---- top bar ---------------------------------------------------------
    def _build_top_bar(self):
        top = tk.Frame(self, bg=THEME["bg_top"], height=60)
        top.pack(side="top", fill="x")
        top.pack_propagate(False)

        if not self.first_run:
            RoundedButton(top, text="← Back",
                          command=self._go_back,
                          width=100, height=40,
                          bg_color=THEME["btn_green"],
                          hover_color=THEME["btn_green_hover"]
                          ).pack(side="left", padx=15, pady=10)

        title = "Neighborhoods"
        if self.first_run:
            title += " — please create or pick one"
        tk.Label(top, text=title, font=THEME["font_title"],
                 bg=THEME["bg_top"], fg=THEME["text_dark"]).pack(side="left", padx=20)

    # ---- body ------------------------------------------------------------
    def _build_body(self):
        body = tk.Frame(self, bg=THEME["bg_main"])
        body.pack(fill="both", expand=True, padx=20, pady=20)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        # LEFT: list of saved clans
        left = tk.Frame(body, bg=THEME["bg_panel"], bd=2, relief="ridge")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        tk.Label(left, text="Saved neighborhoods", font=THEME["font_subheading"],
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
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="left", padx=(0, 6))
        RoundedButton(list_btns, text="Delete", command=self._delete_selected,
                      width=110, height=38,
                      bg_color=THEME["btn_red"],
                      hover_color=THEME["btn_red_hover"]
                      ).pack(side="left")

        # RIGHT: form
        right = tk.Frame(body, bg=THEME["bg_panel"], bd=2, relief="ridge")
        right.grid(row=0, column=1, sticky="nsew")

        tk.Label(right, text="Create or edit neighborhood",
                 font=THEME["font_subheading"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]).pack(pady=(10, 10))

        form = tk.Frame(right, bg=THEME["bg_panel"])
        form.pack(padx=20, pady=10, fill="x")

        self.entry_clan_name = LabeledEntry(form, "Clan name",
                                            default="", width=30)
        self.entry_clan_name.pack(fill="x", pady=4)

        self.entry_clan_tag = LabeledEntry(form, "Clan tag (optional, e.g. #ABC123)",
                                           default="", width=30)
        self.entry_clan_tag.pack(fill="x", pady=4)

        # multiline notes - LabeledEntry only does single line, so build manually
        tk.Label(form, text="Notes (optional)",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]).pack(anchor="w",
                                                                   pady=(8, 0))
        self.txt_notes = tk.Text(form, height=4, font=THEME["font_body"],
                                 relief="solid", bd=1)
        self.txt_notes.pack(fill="x", pady=4)

        # action buttons
        action_btns = tk.Frame(right, bg=THEME["bg_panel"])
        action_btns.pack(pady=15)
        RoundedButton(action_btns, text="Save as new",
                      command=self._save_as_new,
                      width=160, height=44,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="left", padx=6)
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
                      hover_color=THEME["btn_grey_hover"]
                      ).pack(side="left", padx=6)

    # ---- helpers ---------------------------------------------------------
    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for name in self.nm.list_neighborhoods():
            label = name
            if name == self.nm.get_active():
                label += "  ★"
            self.listbox.insert(tk.END, label)

    def _selected_name(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        return self.listbox.get(sel[0]).replace("  ★", "").strip()

    def _on_select(self, _event=None):
        name = self._selected_name()
        if name is None:
            return
        self.selected_clan = name
        try:
            data = self.nm.load(name)
        except (OSError, ValueError):
            return
        self.entry_clan_name.set(name)
        self.entry_clan_tag.set(data.get("clan_tag", ""))
        self.txt_notes.delete("1.0", tk.END)
        self.txt_notes.insert("1.0", data.get("notes", ""))
        self.btn_update.set_disabled(False)

    def _clear_form(self):
        self.selected_clan = None
        self.entry_clan_name.set("")
        self.entry_clan_tag.set("")
        self.txt_notes.delete("1.0", tk.END)
        self.btn_update.set_disabled(True)
        self.listbox.selection_clear(0, tk.END)

    def _read_form(self):
        name = self.entry_clan_name.get()
        if not name:
            messagebox.showerror("Invalid", "Clan name is required.")
            return None
        return {
            "clan_name": name,
            "clan_tag": self.entry_clan_tag.get(),
            "notes": self.txt_notes.get("1.0", tk.END).strip(),
        }

    # ---- actions ---------------------------------------------------------
    def _save_as_new(self):
        form = self._read_form()
        if form is None:
            return
        if self.nm.neighborhood_exists(form["clan_name"]):
            messagebox.showerror("Already exists",
                                 f"A neighborhood named '{form['clan_name']}' already exists.")
            return
        data = default_neighborhood_data(
            clan_name=form["clan_name"],
            clan_tag=form["clan_tag"],
            notes=form["notes"],
        )
        self.nm.create(form["clan_name"], data)
        if self.nm.get_active() is None:
            self.nm.set_active(form["clan_name"])
        messagebox.showinfo("Saved", f"Neighborhood '{form['clan_name']}' created.")
        self._refresh_list()
        self._clear_form()

    def _update_selected(self):
        if self.selected_clan is None:
            messagebox.showinfo("No selection", "Pick a neighborhood from the list first.")
            return
        form = self._read_form()
        if form is None:
            return

        data = self.nm.load(self.selected_clan)
        data["clan_tag"] = form["clan_tag"]
        data["notes"] = form["notes"]

        new_name = form["clan_name"]
        if new_name != self.selected_clan:
            if self.nm.neighborhood_exists(new_name):
                messagebox.showerror("Conflict",
                                     f"A neighborhood named '{new_name}' already exists.")
                return
            self.nm.save(new_name, data)
            try:
                self.nm.delete(self.selected_clan)
            except OSError:
                pass
            self.selected_clan = new_name
        else:
            self.nm.save(self.selected_clan, data)

        messagebox.showinfo("Updated", f"Neighborhood '{self.selected_clan}' updated.")
        self._refresh_list()

    def _use_selected(self):
        name = self._selected_name()
        if name is None:
            messagebox.showinfo("No selection", "Pick a neighborhood from the list first.")
            return
        self.nm.set_active(name)
        self.app.show_frame("NeighborhoodManager")

    def _delete_selected(self):
        name = self._selected_name()
        if name is None:
            messagebox.showinfo("No selection", "Pick a neighborhood from the list first.")
            return
        if not messagebox.askyesno(
                "Delete neighborhood",
                f"Delete '{name}' and ALL its members and snapshots?\n"
                "This cannot be undone."):
            return
        self.nm.delete(name)
        self._refresh_list()
        self._clear_form()

    # ---- nav -------------------------------------------------------------
    def _go_back(self):
        self.app.show_frame(self.return_to)
