"""
App-wide Settings screen.

Three sub-sections selectable from a tab strip:
  - Audio: music + sfx volume, reload, skip, open music folder
  - Video: fullscreen toggle + 6-color palette editor with live preview
  - Neighbourhood: clan name/tag/notes + activity rules editor
                   (only available when a clan is active)
"""

import os
import sys
import subprocess
import tkinter as tk
from tkinter import colorchooser, messagebox

from theme import THEME, SIMPLE_PALETTE_KEYS
from widgets import RoundedButton, LabeledEntry
from neighborhood_manager import (
    DEFAULT_ACTIVITY_RULES, validate_activity_rules,
)


SECTIONS = ("Audio", "Video", "Neighbourhood")


class AppSettingsFrame(tk.Frame):
    def __init__(self, parent, app, return_to: str = None,
                 initial_section: str = "Audio"):
        super().__init__(parent, bg=THEME["bg_main"])
        self.app = app
        self.audio = app.audio_manager
        self.theme_mgr = app.theme_manager
        self.video = app.video_settings
        self.nm = app.neighborhood_manager
        self.return_to = return_to or self._guess_return_to()

        self.current_section = initial_section
        self._build_top_bar()
        self._build_section_tabs()

        self.body = tk.Frame(self, bg=THEME["bg_main"])
        self.body.pack(fill="both", expand=True)
        self._render_section()

    def _guess_return_to(self):
        # if there's a known previous frame we go back to it; else MainMenu
        prev = getattr(self.app, "_last_non_settings_frame", None)
        return prev or "MainMenu"

    # =================================================================
    # top bar
    # =================================================================
    def _build_top_bar(self):
        top = tk.Frame(self, bg=THEME["bg_top"], height=60)
        top.pack(side="top", fill="x")
        top.pack_propagate(False)

        RoundedButton(top, text="← Back",
                      command=lambda: self.app.show_frame(self.return_to),
                      width=110, height=40,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="left", padx=15, pady=10)

        tk.Label(top, text="Settings",
                 font=THEME["font_title"],
                 bg=THEME["bg_top"], fg=THEME["text_dark"]
                 ).pack(side="left", padx=20)

    def _build_section_tabs(self):
        bar = tk.Frame(self, bg=THEME["bg_main"], height=54)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)

        self._section_buttons = {}
        for sec in SECTIONS:
            disabled = (sec == "Neighbourhood"
                        and self.nm.get_active() is None)
            btn = RoundedButton(bar, text=sec,
                                command=(lambda s=sec: self._switch_section(s))
                                        if not disabled else None,
                                width=200, height=42,
                                bg_color=(THEME["btn_grey"] if disabled
                                          else THEME["btn_grey"]),
                                hover_color=THEME["btn_grey_hover"],
                                font=THEME["font_button"],
                                disabled=disabled)
            btn.pack(side="left", padx=6, pady=8)
            self._section_buttons[sec] = btn

        # add a hint about why neighbourhood may be disabled
        if self.nm.get_active() is None:
            tk.Label(bar,
                     text="(Select a clan to edit neighbourhood settings)",
                     font=THEME["font_body"],
                     bg=THEME["bg_main"], fg=THEME["text_muted"]
                     ).pack(side="left", padx=10)

        self._highlight_section(self.current_section)

    def _highlight_section(self, section: str):
        for sec, btn in self._section_buttons.items():
            disabled = (sec == "Neighbourhood"
                        and self.nm.get_active() is None)
            if disabled:
                continue
            if sec == section:
                btn.set_colors(THEME["btn_green"], THEME["btn_green_hover"])
            else:
                btn.set_colors(THEME["btn_grey"], THEME["btn_grey_hover"])

    def _switch_section(self, section: str):
        self.current_section = section
        self._highlight_section(section)
        self._render_section()

    def _render_section(self):
        for child in self.body.winfo_children():
            child.destroy()
        if self.current_section == "Audio":
            AudioSettingsBody(self.body, self).pack(fill="both", expand=True)
        elif self.current_section == "Video":
            VideoSettingsBody(self.body, self).pack(fill="both", expand=True)
        elif self.current_section == "Neighbourhood":
            NeighbourhoodSettingsBody(self.body, self).pack(fill="both", expand=True)


# =================================================================
# AUDIO sub-section
# =================================================================

class AudioSettingsBody(tk.Frame):
    def __init__(self, parent, settings_frame):
        super().__init__(parent, bg=THEME["bg_main"])
        self.sf = settings_frame
        self.audio = settings_frame.audio
        self.app = settings_frame.app

        wrap = self._scroll_wrap()
        self._build(wrap)

    def _scroll_wrap(self):
        canvas = tk.Canvas(self, bg=THEME["bg_main"],
                           highlightthickness=0, bd=0)
        sb = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(canvas, bg=THEME["bg_main"])
        win = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win, width=e.width))
        return body

    def _build(self, parent):
        box = tk.LabelFrame(parent, text=" Audio Settings ",
                            font=THEME["font_subheading"],
                            bg=THEME["bg_panel"], fg=THEME["text_dark"],
                            bd=2, relief="ridge", padx=14, pady=10)
        box.pack(fill="x", padx=20, pady=(15, 10))

        # ---- music ----
        music_frame = tk.Frame(box, bg=THEME["bg_panel"])
        music_frame.pack(fill="x", pady=(2, 8))

        tk.Label(music_frame, text="Background music",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(anchor="w")

        cur = self.audio.get_current_track()
        n_tracks = self.audio.get_playlist_count()
        if n_tracks == 0:
            track_text = ("No music files found. Drop .mp3 files into "
                          "audio/music/ then click Reload music. "
                          "Or click 'Open folder' to open it directly.")
        elif cur:
            track_text = f"Now playing: {cur}    ({n_tracks} tracks loaded)"
        else:
            track_text = f"{n_tracks} tracks loaded — paused or off"
        tk.Label(music_frame, text=track_text,
                 font=THEME["font_body"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"],
                 wraplength=900, justify="left"
                 ).pack(anchor="w", pady=(0, 4))

        controls = tk.Frame(music_frame, bg=THEME["bg_panel"])
        controls.pack(fill="x", pady=2)

        self.var_music_on = tk.BooleanVar(
            value=self.audio.settings["music_enabled"])
        tk.Checkbutton(controls, text="Enabled",
                       variable=self.var_music_on,
                       command=self._on_music_toggle,
                       font=THEME["font_body_bold"],
                       bg=THEME["bg_panel"], fg=THEME["text_dark"],
                       activebackground=THEME["bg_panel"],
                       selectcolor=THEME["bg_card"]
                       ).pack(side="left")

        tk.Label(controls, text="Volume:", font=THEME["font_body"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(side="left", padx=(20, 4))

        self.var_music_vol = tk.IntVar(
            value=int(self.audio.settings["music_volume"] * 100))
        tk.Scale(controls, from_=0, to=100, orient="horizontal",
                 length=240, variable=self.var_music_vol,
                 command=self._on_music_volume,
                 bg=THEME["bg_panel"], troughcolor=THEME["bg_card"],
                 highlightthickness=0
                 ).pack(side="left")

        RoundedButton(controls, text="Reload music",
                      command=self._reload_music,
                      width=130, height=32,
                      bg_color=THEME["btn_blue"],
                      hover_color=THEME["btn_blue_hover"],
                      font=("Arial", 10, "bold"), radius=8
                      ).pack(side="left", padx=(20, 4))

        RoundedButton(controls, text="Skip track",
                      command=self._skip_track,
                      width=110, height=32,
                      bg_color=THEME["btn_grey"],
                      hover_color=THEME["btn_grey_hover"],
                      font=("Arial", 10, "bold"), radius=8
                      ).pack(side="left", padx=2)

        RoundedButton(controls, text="📁 Open folder",
                      command=self._open_music_folder,
                      width=130, height=32,
                      bg_color=THEME["btn_blue"],
                      hover_color=THEME["btn_blue_hover"],
                      font=("Arial", 10, "bold"), radius=8
                      ).pack(side="left", padx=2)

        # ---- sfx ----
        sfx_frame = tk.Frame(box, bg=THEME["bg_panel"])
        sfx_frame.pack(fill="x", pady=(8, 4))

        tk.Label(sfx_frame, text="Click sound",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(anchor="w")

        controls2 = tk.Frame(sfx_frame, bg=THEME["bg_panel"])
        controls2.pack(fill="x", pady=2)

        self.var_sfx_on = tk.BooleanVar(
            value=self.audio.settings["sfx_enabled"])
        tk.Checkbutton(controls2, text="Enabled",
                       variable=self.var_sfx_on,
                       command=self._on_sfx_toggle,
                       font=THEME["font_body_bold"],
                       bg=THEME["bg_panel"], fg=THEME["text_dark"],
                       activebackground=THEME["bg_panel"],
                       selectcolor=THEME["bg_card"]
                       ).pack(side="left")

        tk.Label(controls2, text="Volume:", font=THEME["font_body"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(side="left", padx=(20, 4))

        self.var_sfx_vol = tk.IntVar(
            value=int(self.audio.settings["sfx_volume"] * 100))
        tk.Scale(controls2, from_=0, to=100, orient="horizontal",
                 length=240, variable=self.var_sfx_vol,
                 command=self._on_sfx_volume,
                 bg=THEME["bg_panel"], troughcolor=THEME["bg_card"],
                 highlightthickness=0
                 ).pack(side="left")

    def _on_music_toggle(self):
        self.audio.set_music_enabled(self.var_music_on.get())

    def _on_music_volume(self, val):
        try:
            v = float(val) / 100.0
        except ValueError:
            return
        self.audio.set_music_volume(v)

    def _on_sfx_toggle(self):
        self.audio.set_sfx_enabled(self.var_sfx_on.get())

    def _on_sfx_volume(self, val):
        try:
            v = float(val) / 100.0
        except ValueError:
            return
        self.audio.set_sfx_volume(v)
        if self.var_sfx_on.get():
            self.audio.play_click()

    def _reload_music(self):
        self.audio.reload_music()
        self.app.show_frame("AppSettings", initial_section="Audio")

    def _skip_track(self):
        self.audio.skip_track()
        self.app.show_frame("AppSettings", initial_section="Audio")

    def _open_music_folder(self):
        path = self.audio.music_dir
        os.makedirs(path, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showinfo(
                "Music folder",
                f"Music folder location:\n\n{path}\n\n(Could not open it "
                f"automatically: {e})"
            )


# =================================================================
# VIDEO sub-section
# =================================================================

class VideoSettingsBody(tk.Frame):
    def __init__(self, parent, settings_frame):
        super().__init__(parent, bg=THEME["bg_main"])
        self.sf = settings_frame
        self.video = settings_frame.video
        self.theme_mgr = settings_frame.theme_mgr
        self.app = settings_frame.app

        canvas = tk.Canvas(self, bg=THEME["bg_main"],
                           highlightthickness=0, bd=0)
        sb = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(canvas, bg=THEME["bg_main"])
        win = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win, width=e.width))

        self._build(body)

    def _build(self, parent):
        box = tk.LabelFrame(parent, text=" Video Settings ",
                            font=THEME["font_subheading"],
                            bg=THEME["bg_panel"], fg=THEME["text_dark"],
                            bd=2, relief="ridge", padx=14, pady=10)
        box.pack(fill="x", padx=20, pady=(15, 10))

        fs_row = tk.Frame(box, bg=THEME["bg_panel"])
        fs_row.pack(fill="x", pady=4)
        self.var_fullscreen = tk.BooleanVar(
            value=bool(self.video.get("fullscreen")))
        tk.Checkbutton(fs_row, text="Fullscreen (F11 to toggle)",
                       variable=self.var_fullscreen,
                       command=self._on_fullscreen_toggle,
                       font=THEME["font_body_bold"],
                       bg=THEME["bg_panel"], fg=THEME["text_dark"],
                       activebackground=THEME["bg_panel"],
                       selectcolor=THEME["bg_card"]
                       ).pack(side="left")

        tk.Label(box, text="Color palette",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(anchor="w", pady=(10, 2))
        tk.Label(box,
                 text="Click a color to edit it. Other colors (hover, "
                      "borders, panels) are derived automatically.",
                 font=THEME["font_body"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"]
                 ).pack(anchor="w", pady=(0, 6))

        palette_frame = tk.Frame(box, bg=THEME["bg_panel"])
        palette_frame.pack(fill="x", pady=4)

        primary = self.theme_mgr.get_primary_colors()
        for i, (key, label) in enumerate(SIMPLE_PALETTE_KEYS):
            cell = tk.Frame(palette_frame, bg=THEME["bg_panel"])
            cell.grid(row=0, column=i, padx=6, pady=4, sticky="n")

            tk.Label(cell, text=label,
                     font=THEME["font_body_bold"],
                     bg=THEME["bg_panel"], fg=THEME["text_dark"]
                     ).pack()

            swatch = tk.Frame(cell, bg=primary[key],
                              width=80, height=44, bd=2, relief="ridge",
                              cursor="hand2")
            swatch.pack(pady=2)
            swatch.pack_propagate(False)
            swatch.bind("<Button-1>",
                        lambda e, k=key, lab=label: self._pick_color(k, lab))

            tk.Label(cell, text=primary[key].upper(),
                     font=("Consolas", 9),
                     bg=THEME["bg_panel"], fg=THEME["text_muted"]
                     ).pack()

        reset_row = tk.Frame(box, bg=THEME["bg_panel"])
        reset_row.pack(fill="x", pady=8)
        RoundedButton(reset_row, text="Reset colors to defaults",
                      command=self._reset_theme,
                      width=200, height=36,
                      bg_color=THEME["btn_grey"],
                      hover_color=THEME["btn_grey_hover"]
                      ).pack(side="left")

    def _on_fullscreen_toggle(self):
        new_state = self.var_fullscreen.get()
        self.video.set("fullscreen", new_state)
        self.app.set_fullscreen(new_state)

    def _pick_color(self, key, label):
        current = self.theme_mgr.get_primary_colors()[key]
        result = colorchooser.askcolor(
            color=current, title=f"Pick {label} color", parent=self
        )
        if result is None or result[1] is None:
            return
        new_hex = result[1].upper()
        primary = self.theme_mgr.get_primary_colors()
        primary[key] = new_hex
        self.theme_mgr.apply_primary_colors(primary, persist=True)
        self.app.refresh_theme()

    def _reset_theme(self):
        if not messagebox.askyesno(
                "Reset colors",
                "Reset all colors to the default palette?"):
            return
        self.theme_mgr.reset_to_defaults()
        self.app.refresh_theme()


# =================================================================
# NEIGHBOURHOOD sub-section
# =================================================================

class NeighbourhoodSettingsBody(tk.Frame):
    def __init__(self, parent, settings_frame):
        super().__init__(parent, bg=THEME["bg_main"])
        self.sf = settings_frame
        self.app = settings_frame.app
        self.nm = settings_frame.nm

        clan_name = self.nm.get_active()
        if clan_name is None:
            tk.Label(self, text="No active clan. Select one first.",
                     font=THEME["font_body"],
                     bg=THEME["bg_main"], fg=THEME["text_muted"]
                     ).pack(pady=40)
            return
        self.clan_name = clan_name
        self.data = self.nm.load(clan_name)
        self.editing_rules = [dict(r) for r in self.data.get(
            "activity_rules", DEFAULT_ACTIVITY_RULES)]

        canvas = tk.Canvas(self, bg=THEME["bg_main"],
                           highlightthickness=0, bd=0)
        sb = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(canvas, bg=THEME["bg_main"])
        win = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win, width=e.width))

        self._build(body)

    def _build(self, parent):
        general = tk.LabelFrame(parent, text=f" General — {self.clan_name} ",
                                 font=THEME["font_subheading"],
                                 bg=THEME["bg_panel"], fg=THEME["text_dark"],
                                 bd=2, relief="ridge", padx=14, pady=10)
        general.pack(fill="x", padx=20, pady=(15, 10))

        self.entry_clan_name = LabeledEntry(general, "Clan name",
                                             default=self.data.get("clan_name", ""),
                                             width=40)
        self.entry_clan_name.pack(fill="x", pady=4)

        self.entry_clan_tag = LabeledEntry(general, "Clan tag (optional)",
                                            default=self.data.get("clan_tag", ""),
                                            width=40)
        self.entry_clan_tag.pack(fill="x", pady=4)

        tk.Label(general, text="Notes (optional)",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(anchor="w", pady=(8, 0))
        self.txt_notes = tk.Text(general, height=4,
                                  font=THEME["font_body"],
                                  relief="solid", bd=1)
        self.txt_notes.pack(fill="x", pady=4)
        self.txt_notes.insert("1.0", self.data.get("notes", ""))

        rules_box = tk.LabelFrame(parent, text=" Activity rules ",
                                   font=THEME["font_subheading"],
                                   bg=THEME["bg_panel"], fg=THEME["text_dark"],
                                   bd=2, relief="ridge", padx=14, pady=10)
        rules_box.pack(fill="x", padx=20, pady=10)

        explainer = (
            "Each row applies to members whose current level falls within "
            "[Level min … Level max]. Inactivity check: did the member gain "
            "at least N levels in the last X days? Levels must be covered "
            "with no gaps or overlaps; the first row must start at level 1.\n"
            "Note: members with less than 7 days of recorded data are always "
            "shown as 'New player' unless they over-perform."
        )
        tk.Label(rules_box, text=explainer, font=THEME["font_body"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"],
                 justify="left", wraplength=900
                 ).pack(anchor="w", pady=(2, 8))

        self.rules_table_frame = tk.Frame(rules_box, bg=THEME["bg_panel"])
        self.rules_table_frame.pack(fill="x", pady=(2, 8))
        self._render_rules_table()

        rules_btns = tk.Frame(rules_box, bg=THEME["bg_panel"])
        rules_btns.pack(fill="x", pady=(0, 4))
        RoundedButton(rules_btns, text="+ Add rule",
                      command=self._add_rule_row,
                      width=130, height=36,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="left")
        RoundedButton(rules_btns, text="Reset to defaults",
                      command=self._reset_rules,
                      width=160, height=36,
                      bg_color=THEME["btn_grey"],
                      hover_color=THEME["btn_grey_hover"]
                      ).pack(side="left", padx=8)

        action_bar = tk.Frame(parent, bg=THEME["bg_main"])
        action_bar.pack(fill="x", padx=20, pady=(10, 20))
        RoundedButton(action_bar, text="Save changes",
                      command=self._save,
                      width=180, height=46,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"],
                      font=THEME["font_button_big"]
                      ).pack(side="right")

    def _render_rules_table(self):
        for child in self.rules_table_frame.winfo_children():
            child.destroy()
        self._rule_entry_refs = []

        header = tk.Frame(self.rules_table_frame, bg=THEME["bg_top"], bd=1,
                          relief="solid")
        header.pack(fill="x")
        for label, w in [("Level min", 90), ("Level max", 90),
                          ("Min levels gained", 150),
                          ("Time window (days)", 150),
                          ("Actions", 120)]:
            f = tk.Frame(header, bg=THEME["bg_top"], width=w, height=28)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Label(f, text=label, font=THEME["font_body_bold"],
                     bg=THEME["bg_top"], fg=THEME["text_dark"]
                     ).pack(expand=True)

        sorted_rules = sorted(self.editing_rules, key=lambda r: r["level_min"])
        for i, rule in enumerate(sorted_rules):
            self._render_rule_row(rule, i, len(sorted_rules))

    def _render_rule_row(self, rule, index, total):
        bg = THEME["bg_card"] if index % 2 == 0 else THEME["bg_panel"]
        row = tk.Frame(self.rules_table_frame, bg=bg, bd=1, relief="solid")
        row.pack(fill="x")

        var_lo = tk.StringVar(value=str(rule["level_min"]))
        var_hi = tk.StringVar(value=str(rule["level_max"]))
        var_mlg = tk.StringVar(value=str(rule["min_levels_gained"]))
        var_twd = tk.StringVar(value=str(rule["time_window_days"]))

        def cell_entry(parent, var, width):
            f = tk.Frame(parent, bg=bg, width=width, height=36)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Entry(f, textvariable=var, font=THEME["font_body"],
                     relief="solid", bd=1, justify="center", width=8
                     ).pack(expand=True, padx=6, pady=4)

        cell_entry(row, var_lo, 90)
        cell_entry(row, var_hi, 90)
        cell_entry(row, var_mlg, 150)
        cell_entry(row, var_twd, 150)

        actions = tk.Frame(row, bg=bg, width=120, height=36)
        actions.pack(side="left")
        actions.pack_propagate(False)

        def remove_this():
            self._commit_rule_entries_to_state()
            sorted_rules = sorted(self.editing_rules,
                                   key=lambda r: r["level_min"])
            try:
                target = sorted_rules[index]
                self.editing_rules.remove(target)
            except (IndexError, ValueError):
                pass
            self._render_rules_table()

        if total > 1:
            RoundedButton(actions, text="Delete",
                          command=remove_this,
                          width=80, height=26,
                          bg_color=THEME["btn_red"],
                          hover_color=THEME["btn_red_hover"],
                          font=("Arial", 10, "bold"), radius=8
                          ).pack(expand=True)

        self._rule_entry_refs.append({
            "level_min": var_lo, "level_max": var_hi,
            "min_levels_gained": var_mlg, "time_window_days": var_twd,
        })

    def _commit_rule_entries_to_state(self):
        new_rules = []
        for refs in self._rule_entry_refs:
            try:
                rule = {k: int(v.get()) for k, v in refs.items()}
            except ValueError:
                rule = {k: v.get() for k, v in refs.items()}
            new_rules.append(rule)
        self.editing_rules = new_rules

    def _add_rule_row(self):
        self._commit_rule_entries_to_state()
        try:
            max_level_used = max(
                (int(r["level_max"]) for r in self.editing_rules
                 if str(r.get("level_max")).isdigit()),
                default=0
            )
        except (ValueError, TypeError):
            max_level_used = 0
        new_lo = max_level_used + 1 if max_level_used > 0 else 1
        new_hi = max(new_lo + 9, new_lo)
        self.editing_rules.append({
            "level_min": new_lo, "level_max": new_hi,
            "min_levels_gained": 1, "time_window_days": 7,
        })
        self._render_rules_table()

    def _reset_rules(self):
        if not messagebox.askyesno(
                "Reset rules",
                "Replace the current activity rules with the defaults?"):
            return
        self.editing_rules = [dict(r) for r in DEFAULT_ACTIVITY_RULES]
        self._render_rules_table()

    def _save(self):
        self._commit_rule_entries_to_state()
        clan_name = self.entry_clan_name.get().strip()
        if not clan_name:
            messagebox.showerror("Invalid", "Clan name is required.")
            return

        parsed = []
        for i, r in enumerate(self.editing_rules, start=1):
            try:
                parsed.append({k: int(v) for k, v in r.items()})
            except (TypeError, ValueError):
                messagebox.showerror(
                    "Invalid rule",
                    f"Rule {i}: all four fields must be integers.")
                return

        errs = validate_activity_rules(parsed)
        if errs:
            messagebox.showerror("Invalid rules", "\n".join(errs[:8]))
            return

        self.data["clan_tag"] = self.entry_clan_tag.get().strip()
        self.data["notes"] = self.txt_notes.get("1.0", tk.END).strip()
        self.data["activity_rules"] = parsed

        new_name = clan_name
        if new_name != self.clan_name:
            if self.nm.neighborhood_exists(new_name):
                messagebox.showerror(
                    "Conflict",
                    f"A neighborhood named '{new_name}' already exists.")
                return
            self.data["clan_name"] = new_name
            self.nm.save(new_name, self.data)
            try:
                self.nm.delete(self.clan_name)
            except OSError:
                pass
            self.nm.set_active(new_name)
            self.clan_name = new_name
        else:
            self.data["clan_name"] = new_name
            self.nm.save(self.clan_name, self.data)

        # invalidate the cache so other screens see the changes
        if hasattr(self.app, "data_cache"):
            self.app.data_cache.invalidate()

        messagebox.showinfo("Saved", "Settings saved.")
        self.app.show_frame("AppSettings", initial_section="Neighbourhood")
