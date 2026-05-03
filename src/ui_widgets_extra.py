"""
Reusable UI building blocks used by multiple screens.

CollapsibleSection: A box with a header that can be expanded/collapsed
SearchBox: A text entry that fires a callback on every keystroke
StatusCountBadge: A row of colored count pills (e.g. red 2 | yellow 0 | green 5)
SmoothScrolledFrame: A scroll container with debounced + smaller-step scrolling
PulsingLogo: kept around even if currently unused on the main menu
attach_smooth_mousewheel: applies smooth-scroll behavior to an existing canvas
"""

import os
import tkinter as tk
from PIL import Image, ImageTk

from theme import THEME


# ---------------------------------------------------------------------------
# Smooth scroll helpers
# ---------------------------------------------------------------------------

def attach_smooth_mousewheel(canvas, step_units: int = 2,
                              max_per_second: int = 60):
    """Bind smoother mousewheel scrolling to a Canvas.

    - smaller step (default 2 units instead of Tk's standard 3) so each
      wheel notch moves a smaller amount
    - simple debouncing via after_idle batching, so a flurry of events
      gets coalesced into one yview_scroll call per render frame.

    Returns a function to detach the binding.
    """
    state = {"pending": 0, "scheduled": False}

    def flush():
        state["scheduled"] = False
        delta = state["pending"]
        state["pending"] = 0
        if delta == 0:
            return
        try:
            canvas.yview_scroll(delta, "units")
        except tk.TclError:
            pass

    def on_wheel(event):
        # event.delta is +/- 120 per wheel notch on Windows;
        # convert direction and apply our smaller step
        if event.delta == 0:
            return
        direction = -1 if event.delta > 0 else 1
        state["pending"] += direction * step_units
        if not state["scheduled"]:
            state["scheduled"] = True
            # 16 ms ≈ 60 fps; coalesces multiple events between frames
            canvas.after(16, flush)

    # bind only when mouse is over this canvas, not bind_all (which would
    # hijack scrolling on other canvases)
    def on_enter(_event):
        canvas.bind_all("<MouseWheel>", on_wheel)
        # Linux: Button-4/5 are scroll up/down respectively
        canvas.bind_all("<Button-4>", lambda e: on_wheel_linux(e, -1))
        canvas.bind_all("<Button-5>", lambda e: on_wheel_linux(e, +1))

    def on_leave(_event):
        try:
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")
        except tk.TclError:
            pass

    def on_wheel_linux(_event, direction):
        state["pending"] += direction * step_units
        if not state["scheduled"]:
            state["scheduled"] = True
            canvas.after(16, flush)

    canvas.bind("<Enter>", on_enter)
    canvas.bind("<Leave>", on_leave)

    def detach():
        try:
            canvas.unbind("<Enter>")
            canvas.unbind("<Leave>")
            on_leave(None)
        except tk.TclError:
            pass

    return detach


class SmoothScrolledFrame(tk.Frame):
    """A frame containing a vertically scrollable inner frame with smooth
    mousewheel behavior. Use `inner` for content; pack/grid this widget
    where you'd put a scrollable area.
    """

    def __init__(self, parent, bg=None):
        bg = bg or THEME["bg_main"]
        super().__init__(parent, bg=bg)

        canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(self, orient="vertical",
                                  command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.canvas = canvas
        self.inner = tk.Frame(canvas, bg=bg)
        self._win_id = canvas.create_window((0, 0), window=self.inner,
                                              anchor="nw")
        self.inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(self._win_id, width=e.width))
        attach_smooth_mousewheel(canvas)


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Collapsible section
# ---------------------------------------------------------------------------

class CollapsibleSection(tk.Frame):
    """A LabelFrame-like container with a clickable header that toggles
    visibility of the body. Useful for stats screens where many sections
    would otherwise overflow the viewport.

    Use:
        sect = CollapsibleSection(parent, title="Activity status",
                                  initial_open=False)
        sect.pack(fill="x", padx=20, pady=10)
        # add widgets to sect.body
    """

    def __init__(self, parent, title: str, initial_open: bool = False,
                 badge_text: str = "", badge_color: str = None,
                 badge_widget=None,
                 on_first_open=None):
        """badge_widget: an optional callable (parent_frame) -> Widget that
        returns a custom widget to display in the header (e.g. a multi-color
        StatusCountBadge). Takes priority over badge_text/badge_color.
        """
        super().__init__(parent, bg=THEME["bg_main"])
        self.title = title
        self.is_open = bool(initial_open)
        self._on_first_open = on_first_open
        self._first_opened = False

        # --- header (clickable strip) ---
        self.header = tk.Frame(self, bg=THEME["bg_top"], bd=2, relief="ridge",
                                cursor="hand2")
        self.header.pack(fill="x")

        self._chevron = tk.Label(self.header,
                                  text="▼" if self.is_open else "▶",
                                  font=THEME["font_subheading"],
                                  bg=THEME["bg_top"], fg=THEME["text_dark"],
                                  cursor="hand2")
        self._chevron.pack(side="left", padx=(10, 6), pady=4)

        self._title_label = tk.Label(self.header, text=title,
                                      font=THEME["font_subheading"],
                                      bg=THEME["bg_top"], fg=THEME["text_dark"],
                                      cursor="hand2")
        self._title_label.pack(side="left", pady=4)

        if badge_widget is not None:
            # callable - let it create the widget on the header bar
            self._badge = badge_widget(self.header)
            if self._badge is not None:
                self._badge.pack(side="left", padx=8)
        elif badge_text:
            self._badge = tk.Label(
                self.header, text=f"  {badge_text}  ",
                font=THEME["font_body_bold"],
                bg=badge_color or THEME["btn_grey"],
                fg=THEME["text_light"], padx=6, pady=2
            )
            self._badge.pack(side="left", padx=8)

        # bind clicks on the whole header to toggle
        for w in (self.header, self._chevron, self._title_label):
            w.bind("<Button-1>", lambda _e: self.toggle())
        # if there's a custom badge widget, recursively bind clicks on it
        if hasattr(self, "_badge") and self._badge is not None:
            self._bind_toggle_recursive(self._badge)

        # --- body (hidden when collapsed) ---
        self.body = tk.Frame(self, bg=THEME["bg_panel"], bd=2, relief="ridge")
        if self.is_open:
            self.body.pack(fill="x")
            self._maybe_first_open()

    def _bind_toggle_recursive(self, widget):
        """Recursively bind <Button-1> on a widget tree to toggle this section.
        Useful when the badge is a composite widget with nested labels/frames."""
        try:
            widget.configure(cursor="hand2")
        except tk.TclError:
            pass
        widget.bind("<Button-1>", lambda _e: self.toggle())
        for child in widget.winfo_children():
            self._bind_toggle_recursive(child)

    def toggle(self):
        self.is_open = not self.is_open
        if self.is_open:
            self.body.pack(fill="x")
            self._chevron.config(text="▼")
            self._maybe_first_open()
        else:
            self.body.pack_forget()
            self._chevron.config(text="▶")

    def set_badge(self, text: str, color: str = None):
        if hasattr(self, "_badge"):
            self._badge.config(text=f"  {text}  ",
                               bg=color or self._badge.cget("bg"))

    def _maybe_first_open(self):
        if self._first_opened:
            return
        if self._on_first_open is not None:
            try:
                self._on_first_open(self.body)
            except Exception as e:
                print(f"[CollapsibleSection] first-open callback failed: {e}")
        self._first_opened = True


# ---------------------------------------------------------------------------
# Status count badge (multi-color count pills)
# ---------------------------------------------------------------------------

class StatusCountBadge(tk.Frame):
    """A horizontal row of small colored pills, each showing a count.

    Use:
        StatusCountBadge(parent, [
            ("2", "#D24545"),   # red, 2 inactive
            ("0", "#E89B3B"),   # amber, 0 below
            ("5", "#3FA63F"),   # green, 5 on track
            ("1", "#9A9A9A"),   # grey, 1 new player
        ])

    The colors are passed in as fixed hex codes (not theme keys) so they
    stay consistent regardless of the user's color palette.
    """

    def __init__(self, parent, items, bg=None, pill_size: int = 22):
        bg = bg or THEME["bg_top"]
        super().__init__(parent, bg=bg)
        for count, color in items:
            pill = tk.Frame(self, bg=color, width=pill_size, height=pill_size,
                            bd=1, relief="solid")
            pill.pack(side="left", padx=2)
            pill.pack_propagate(False)
            tk.Label(pill, text=str(count),
                     font=("Arial", 10, "bold"),
                     bg=color, fg="white").pack(expand=True)


# ---------------------------------------------------------------------------

class SearchBox(tk.Frame):
    """A simple search input that fires `on_change(query_str)` as the user
    types. Includes a clear button (×) and a magnifying-glass label."""

    def __init__(self, parent, on_change, placeholder: str = "Search…",
                 width: int = 24, bg=None):
        bg = bg or THEME["bg_panel"]
        super().__init__(parent, bg=bg)
        self._on_change = on_change

        tk.Label(self, text="🔍", font=THEME["font_body"],
                 bg=bg, fg=THEME["text_muted"]
                 ).pack(side="left", padx=(0, 4))

        self.var = tk.StringVar()
        self.var.trace_add("write", lambda *_: self._fire())
        self.entry = tk.Entry(self, textvariable=self.var, width=width,
                              font=THEME["font_body"], relief="solid", bd=1)
        self.entry.pack(side="left")

        # placeholder via grey foreground when empty
        self._placeholder = placeholder
        self._placeholder_active = True
        self.entry.config(fg=THEME["text_muted"])
        self.var.set(placeholder)
        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)

        tk.Button(self, text="×", command=self.clear,
                  font=THEME["font_body_bold"],
                  bg=bg, fg=THEME["text_muted"], bd=0,
                  cursor="hand2", padx=4
                  ).pack(side="left", padx=(2, 0))

    def get(self) -> str:
        if self._placeholder_active:
            return ""
        return self.var.get()

    def clear(self):
        self.var.set("")
        # reset placeholder if user wasn't focused
        if self.focus_get() is not self.entry:
            self._activate_placeholder()

    def _fire(self):
        if self._placeholder_active:
            return
        try:
            self._on_change(self.var.get())
        except Exception as e:
            print(f"[SearchBox] callback failed: {e}")

    def _on_focus_in(self, _event):
        if self._placeholder_active:
            self._placeholder_active = False
            self.var.set("")
            self.entry.config(fg=THEME["text_dark"])

    def _on_focus_out(self, _event):
        if not self.var.get():
            self._activate_placeholder()

    def _activate_placeholder(self):
        self._placeholder_active = True
        self.entry.config(fg=THEME["text_muted"])
        self.var.set(self._placeholder)


# ---------------------------------------------------------------------------
# Background image frame
# ---------------------------------------------------------------------------

class BackgroundImageFrame(tk.Frame):
    """A frame that shows a scaled background image filling its area.

    Implementation: a Label inside the frame holds the (scaled) image,
    placed with `place(x=0, y=0, relwidth=1, relheight=1)`. Children added
    to `self.content` use `pack()` (different geometry manager) so they
    appear above the label — Tk renders pack'd children on top of place'd
    siblings within the same parent.

    For the visual illusion to work, children with their own opaque bg
    (buttons, labels, child frames) should match the average background
    color where you want the image to "show through" between them.
    """

    def __init__(self, parent, image_path: str = None,
                 fallback_color: str = None):
        super().__init__(parent, bg=fallback_color or THEME["bg_main"])
        self.image_path = image_path
        self._pil_image = None
        self._tk_image = None
        self._last_size = (0, 0)
        self._avg_color = fallback_color or THEME["bg_main"]

        if image_path and os.path.exists(image_path):
            try:
                self._pil_image = Image.open(image_path).convert("RGB")
                # compute average color so children blend with the bg
                small = self._pil_image.resize((1, 1), Image.Resampling.LANCZOS)
                r, g, b = small.getpixel((0, 0))
                self._avg_color = f"#{r:02X}{g:02X}{b:02X}"
            except Exception as e:
                print(f"[BackgroundImageFrame] failed to load {image_path}: {e}")
                self._pil_image = None

        # background label fills the entire frame
        self._bg_label = tk.Label(self, bd=0, highlightthickness=0,
                                   bg=self._avg_color)
        self._bg_label.place(x=0, y=0, relwidth=1, relheight=1)

        # children should be added to .content, which IS the frame itself.
        # Because pack/grid'd children are drawn over place'd siblings,
        # adding things via .content.pack() puts them on top of the bg label.
        self.content = self
        # also expose the average color so callers can match it on opaque
        # child frames that should look "transparent"
        self.avg_bg_color = self._avg_color

        self.bind("<Configure>", self._on_resize)
        self.after(50, self._force_initial_render)

    def _force_initial_render(self):
        try:
            w = self.winfo_width()
            h = self.winfo_height()
            if w > 1 and h > 1:
                self._render_background(w, h)
                self._last_size = (w, h)
            else:
                self.after(50, self._force_initial_render)
        except tk.TclError:
            pass

    def _on_resize(self, event):
        w, h = event.width, event.height
        if (w, h) == self._last_size or w < 2 or h < 2:
            return
        self._last_size = (w, h)
        self._render_background(w, h)

    def _render_background(self, w: int, h: int):
        if self._pil_image is None:
            return
        iw, ih = self._pil_image.size
        scale = max(w / iw, h / ih)
        new_w, new_h = int(iw * scale), int(ih * scale)
        scaled = self._pil_image.resize(
            (new_w, new_h), Image.Resampling.LANCZOS)
        left = (new_w - w) // 2
        top = (new_h - h) // 2
        cropped = scaled.crop((left, top, left + w, top + h))
        self._tk_image = ImageTk.PhotoImage(cropped)
        self._bg_label.config(image=self._tk_image)
        self._bg_label.image = self._tk_image


# ---------------------------------------------------------------------------
# Pulsing logo
# ---------------------------------------------------------------------------

class PulsingLogo(tk.Label):
    """A logo image label that gently scales itself up and down to draw
    the eye. Uses Pillow + after() — no extra threads."""

    def __init__(self, parent, image_path: str, max_width: int = 600,
                 bg=None, pulse_amp: float = 0.025, period_ms: int = 2400):
        bg = bg or THEME["bg_main"]
        super().__init__(parent, bg=bg, bd=0)
        self._bg = bg

        try:
            self._pil = Image.open(image_path).convert("RGBA")
        except Exception as e:
            print(f"[PulsingLogo] failed to load {image_path}: {e}")
            self._pil = None
            return

        # scale to a base size that fits within max_width
        iw, ih = self._pil.size
        if iw > max_width:
            scale = max_width / iw
            self._base_size = (int(iw * scale), int(ih * scale))
        else:
            self._base_size = (iw, ih)

        self._pulse_amp = pulse_amp
        self._period = period_ms
        self._tick = 0
        self._cached = {}  # size -> ImageTk.PhotoImage

        # render once at base size
        self._render(1.0)
        # kick off pulse loop
        self.after(60, self._pulse_step)

    def _render(self, scale: float):
        if self._pil is None:
            return
        # quantize the scale a tiny bit to reuse cached images and reduce work
        s = round(scale, 3)
        target_w = max(1, int(self._base_size[0] * s))
        target_h = max(1, int(self._base_size[1] * s))
        key = (target_w, target_h)
        img = self._cached.get(key)
        if img is None:
            scaled = self._pil.resize((target_w, target_h),
                                       Image.Resampling.LANCZOS)
            img = ImageTk.PhotoImage(scaled)
            self._cached[key] = img
            # cap the cache so we don't grow forever
            if len(self._cached) > 24:
                # drop a random entry (oldest semantics not worth tracking)
                k = next(iter(self._cached))
                if k != key:
                    self._cached.pop(k, None)
        self.config(image=img)
        self._current_image = img  # keep reference

    def _pulse_step(self):
        import math
        # phase ranges 0..1 over the period
        phase = (self._tick * 60) / self._period
        # smooth sin in/out wave
        scale = 1.0 + self._pulse_amp * math.sin(phase * 2 * math.pi)
        self._render(scale)
        self._tick += 1
        try:
            self.after(60, self._pulse_step)
        except tk.TclError:
            pass  # widget destroyed
