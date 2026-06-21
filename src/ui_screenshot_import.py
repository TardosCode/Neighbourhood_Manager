"""
Screenshot import dialog — turn a Derby Task Log screenshot (or pasted text)
into a prefilled "after-derby" snapshot.

The flow has two sections:

  A) Get the text — either OCR a screenshot (optional Tesseract dependency) or
     paste text the user copied on their phone (Google Lens / built-in "copy
     text from image"). The raw text lands in an editable Text box.

  B) Review & match — pressing "Parse" runs the pure parsing/matching logic in
     derby_ocr.py and renders one editable row per parsed entry, with a
     member picker (auto-matched where confident), editable task/point fields,
     and any validation warnings. Confirming hands a prefill snapshot dict to
     the on_done callback (which opens it in a fresh NewSnapshotTab).

All the heavy logic lives in derby_ocr.py (pure, tested) and ocr_engine.py
(the optional image→text step); this module is just the Tkinter shell around
them and never imports PIL/pytesseract itself.
"""

import datetime
import tkinter as tk
from tkinter import filedialog, messagebox

from theme import THEME
from widgets import RoundedButton
from ui_widgets_extra import SmoothScrolledFrame

import derby_ocr
import ocr_engine


SKIP_CHOICE = "— skip this row —"


class ScreenshotImportDialog(tk.Toplevel):
    """Modal dialog that produces an after-derby prefill snapshot from a
    screenshot or pasted Derby Task Log text.

    ``on_done(prefill_snapshot_dict)`` is invoked once the user confirms.
    """

    def __init__(self, parent, manager, on_done):
        super().__init__(parent)
        self.manager = manager
        self.on_done = on_done

        self.title("Import derby results from a screenshot")
        self.configure(bg=THEME["bg_main"])
        self.geometry("900x680")
        self.minsize(760, 560)
        self.transient(parent)
        self.grab_set()

        # per-review-row state, rebuilt on each Parse
        self._review_rows = []      # [{name, choice_var, tasks_var, max_var, points_var}, ...]
        self._members = {}          # member_id -> member dict (snapshot at parse time)
        self.var_date = tk.StringVar(
            value=datetime.date.today().isoformat())

        self._build_section_a()
        self._build_section_b_container()

    # =================================================================
    # SECTION A — get the text
    # =================================================================
    def _build_section_a(self):
        sec = tk.Frame(self, bg=THEME["bg_panel"], bd=2, relief="ridge")
        sec.pack(side="top", fill="x", padx=16, pady=(14, 8))

        tk.Label(sec, text="1) Get the text",
                 font=THEME["font_subheading"],
                 bg=THEME["bg_panel"], fg=THEME["text_dark"]
                 ).pack(side="top", anchor="w", padx=14, pady=(10, 2))

        # ---- load / parse button row ----
        btn_row = tk.Frame(sec, bg=THEME["bg_panel"])
        btn_row.pack(side="top", fill="x", padx=14, pady=(2, 4))

        RoundedButton(btn_row, text="📷 Load screenshot…",
                      command=self._on_load_screenshot,
                      width=200, height=40,
                      bg_color=THEME["btn_blue"],
                      hover_color=THEME["btn_blue_hover"]
                      ).pack(side="left")

        RoundedButton(btn_row, text="🔎 Parse",
                      command=self._on_parse,
                      width=130, height=40,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"]
                      ).pack(side="left", padx=(10, 0))

        tk.Label(sec,
                 text=("No Tesseract? On your phone, copy the text from the "
                       "screenshot (Google Lens / built-in text selection) and "
                       "paste it below."),
                 font=THEME["font_body"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"],
                 justify="left", wraplength=840, anchor="w"
                 ).pack(side="top", anchor="w", padx=14, pady=(0, 6))

        # ---- OCR / paste text box with scrollbar ----
        text_wrap = tk.Frame(sec, bg=THEME["bg_panel"])
        text_wrap.pack(side="top", fill="x", padx=14, pady=(0, 12))

        scroll = tk.Scrollbar(text_wrap, orient="vertical")
        scroll.pack(side="right", fill="y")
        self.text_box = tk.Text(text_wrap, height=8, wrap="word",
                                font=THEME["font_body"], relief="solid", bd=1,
                                yscrollcommand=scroll.set)
        self.text_box.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.text_box.yview)

    def _on_load_screenshot(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Choose a derby screenshot",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        available, reason = ocr_engine.ocr_available()
        if not available:
            messagebox.showinfo(
                "OCR not available",
                (reason or "OCR is not available.")
                + "\n\nYou can still paste the text manually below.",
                parent=self,
            )
            return

        # OCR can take a moment; show a busy cursor
        try:
            self.config(cursor="watch")
            self.update_idletasks()
            text = ocr_engine.image_to_text(path)
        except Exception as exc:
            messagebox.showerror(
                "Could not read the screenshot",
                f"{exc}\n\nYou can still paste the text manually below.",
                parent=self,
            )
            return
        finally:
            self.config(cursor="")

        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", text)

    def _on_parse(self):
        text = self.text_box.get("1.0", "end")
        result = derby_ocr.parse_task_log(text)
        rows = result.get("rows", [])
        if not rows:
            messagebox.showinfo(
                "Nothing to import",
                "No member rows were found in the text. Check that the text "
                "contains lines like 'FarmName  9/9  2791', then try again.",
                parent=self,
            )
            return

        self._members = self.manager.reload_data()["members"]
        matched = derby_ocr.match_rows_to_members(rows, self._members)
        self._render_review(matched, result)

    # =================================================================
    # SECTION B — review & match
    # =================================================================
    def _build_section_b_container(self):
        # footer first (packed to the bottom) so the scroll area fills the rest
        self._build_footer()

        self._section_b = tk.Frame(self, bg=THEME["bg_main"])
        self._section_b.pack(side="top", fill="both", expand=True,
                             padx=16, pady=(0, 8))

        self._review_scroll = SmoothScrolledFrame(self._section_b,
                                                  bg=THEME["bg_main"])
        self._review_scroll.pack(fill="both", expand=True)

        # initial placeholder until the user parses something
        tk.Label(self._review_scroll.inner,
                 text="Load a screenshot or paste text above, then press "
                      "“🔎 Parse” to review the results here.",
                 font=THEME["font_body"], bg=THEME["bg_main"],
                 fg=THEME["text_muted"], wraplength=820, justify="left"
                 ).pack(anchor="w", padx=8, pady=40)

    def _render_review(self, matched, result):
        self._review_rows = []
        inner = self._review_scroll.inner
        for child in inner.winfo_children():
            child.destroy()

        tk.Label(inner, text="2) Review & match",
                 font=THEME["font_subheading"],
                 bg=THEME["bg_main"], fg=THEME["text_dark"]
                 ).pack(side="top", anchor="w", padx=8, pady=(8, 4))

        # member-name options for the picker (alphabetical), plus the skip entry
        member_names = sorted(
            (m.get("name", mid) for mid, m in self._members.items()),
            key=lambda s: s.lower())
        options = [SKIP_CHOICE] + member_names

        # column header
        header = tk.Frame(inner, bg=THEME["bg_top"], bd=1, relief="solid")
        header.pack(side="top", fill="x", padx=8)
        for label, w in [("Screenshot name", 220), ("Member", 220),
                         ("Tasks", 70), ("Max", 60), ("Points", 80),
                         ("Notes", 200)]:
            f = tk.Frame(header, bg=THEME["bg_top"], width=w, height=28)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Label(f, text=label, font=THEME["font_body_bold"],
                     bg=THEME["bg_top"], fg=THEME["text_dark"]
                     ).pack(expand=True)

        for i, item in enumerate(matched):
            self._render_review_row(inner, item, options, i)

        # ---- bingo line ----
        bingo = result.get("bingo")
        if bingo:
            tk.Label(inner,
                     text=f"Bingo: {bingo.get('count', 0)} "
                          f"(bonus points: {bingo.get('points', 0)})",
                     font=THEME["font_body_bold"], bg=THEME["bg_main"],
                     fg=THEME["text_dark"]
                     ).pack(side="top", anchor="w", padx=8, pady=(8, 0))

        # ---- skipped-lines note ----
        skipped = result.get("skipped") or []
        if skipped:
            note = tk.Label(
                inner,
                text=(f"⚠ {len(skipped)} line(s) couldn't be parsed and were "
                      "skipped — double-check the text above if a member is "
                      "missing."),
                font=THEME["font_body"], bg=THEME["bg_main"],
                fg=THEME["text_warning"], wraplength=820, justify="left")
            note.pack(side="top", anchor="w", padx=8, pady=(6, 0))

        # ---- date field ----
        date_row = tk.Frame(inner, bg=THEME["bg_main"])
        date_row.pack(side="top", anchor="w", padx=8, pady=(12, 8))
        tk.Label(date_row, text="Snapshot date:",
                 font=THEME["font_body_bold"],
                 bg=THEME["bg_main"], fg=THEME["text_dark"]
                 ).pack(side="left")
        tk.Entry(date_row, textvariable=self.var_date, width=14,
                 font=THEME["font_body"], relief="solid", bd=1
                 ).pack(side="left", padx=(6, 0))

    def _render_review_row(self, parent, item, options, row_index):
        bg = THEME["bg_card"] if row_index % 2 == 0 else THEME["bg_panel"]
        row = item["row"]
        wrap = tk.Frame(parent, bg=bg, bd=1, relief="solid")
        wrap.pack(side="top", fill="x", padx=8)

        # ----- screenshot name (read-only) -----
        f = tk.Frame(wrap, bg=bg, width=220, height=40)
        f.pack(side="left")
        f.pack_propagate(False)
        tk.Label(f, text=row.get("name", ""), font=THEME["font_body_bold"],
                 bg=bg, fg=THEME["text_dark"], anchor="w"
                 ).pack(fill="both", expand=True, padx=8)

        # ----- member picker -----
        choice_var = tk.StringVar(
            value=item.get("member_name") or SKIP_CHOICE)
        f = tk.Frame(wrap, bg=bg, width=220, height=40)
        f.pack(side="left")
        f.pack_propagate(False)
        om = tk.OptionMenu(f, choice_var, *options)
        om.config(font=THEME["font_body"], bg=bg, anchor="w")
        om.pack(fill="x", expand=True, padx=4, pady=4)

        # ----- tasks / max / points (editable) -----
        tasks_var = tk.StringVar(value=str(row.get("tasks_done", "")))
        max_var = tk.StringVar(value=str(row.get("tasks_max", "")))
        points_var = tk.StringVar(value=str(row.get("points", "")))

        for var, w, ew in [(tasks_var, 70, 6), (max_var, 60, 5),
                           (points_var, 80, 8)]:
            f = tk.Frame(wrap, bg=bg, width=w, height=40)
            f.pack(side="left")
            f.pack_propagate(False)
            tk.Entry(f, textvariable=var, width=ew, font=THEME["font_body"],
                     relief="solid", bd=1, justify="center"
                     ).pack(expand=True, padx=4, pady=4)

        # ----- warnings -----
        f = tk.Frame(wrap, bg=bg, width=200, height=40)
        f.pack(side="left", fill="x", expand=True)
        f.pack_propagate(False)
        warnings = row.get("warnings") or []
        if warnings:
            tk.Label(f, text="; ".join(warnings), font=THEME["font_body"],
                     bg=bg, fg=THEME["text_warning"], anchor="w",
                     wraplength=190, justify="left"
                     ).pack(fill="both", expand=True, padx=4)

        self._review_rows.append({
            "choice_var": choice_var,
            "tasks_var": tasks_var,
            "max_var": max_var,
            "points_var": points_var,
        })

    # =================================================================
    # FOOTER — confirm / cancel
    # =================================================================
    def _build_footer(self):
        footer = tk.Frame(self, bg=THEME["bg_main"])
        footer.pack(side="bottom", fill="x", padx=16, pady=12)

        RoundedButton(footer, text="✅ Use these results",
                      command=self._on_confirm,
                      width=220, height=46,
                      bg_color=THEME["btn_green"],
                      hover_color=THEME["btn_green_hover"],
                      font=THEME["font_button_big"]
                      ).pack(side="right")

        RoundedButton(footer, text="Cancel",
                      command=self.destroy,
                      width=130, height=46,
                      bg_color=THEME["btn_grey"],
                      hover_color=THEME["btn_grey_hover"]
                      ).pack(side="right", padx=10)

    def _on_confirm(self):
        if not self._review_rows:
            messagebox.showinfo(
                "Nothing to use",
                "Parse a screenshot or pasted text first.",
                parent=self)
            return

        # name -> member_id lookup (first wins on duplicate names)
        name_to_id = {}
        for mid, m in self._members.items():
            name = m.get("name", mid)
            if name not in name_to_id:
                name_to_id[name] = mid

        items = []
        for rstate in self._review_rows:
            choice = rstate["choice_var"].get()
            if choice == SKIP_CHOICE:
                continue
            mid = name_to_id.get(choice)
            if mid is None:
                continue
            try:
                tasks_done = int(rstate["tasks_var"].get().strip() or 0)
                tasks_max = int(rstate["max_var"].get().strip() or 0)
                points = int(rstate["points_var"].get().strip() or 0)
            except ValueError:
                messagebox.showerror(
                    "Invalid number",
                    f"Tasks, max and points must be whole numbers "
                    f"(check the row for “{choice}”).",
                    parent=self)
                return
            items.append({
                "member_id": mid,
                "row": {
                    "tasks_done": tasks_done,
                    "tasks_max": tasks_max,
                    "points": points,
                },
            })

        if not items:
            messagebox.showinfo(
                "No rows selected",
                "Every row is set to “skip”. Pick at least one member to "
                "import, or press Cancel.",
                parent=self)
            return

        date_str = self.var_date.get().strip() or \
            datetime.date.today().isoformat()
        prefill = derby_ocr.build_prefill_snapshot(items, date_str)
        self.on_done(prefill)
        self.destroy()
