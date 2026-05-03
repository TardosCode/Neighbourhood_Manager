"""
Reusable widgets:
- RoundedButton: a Canvas-based button with hover/disabled states
- ImageCache:    loads PNGs and provides scaled PhotoImage instances
"""

import os
import tkinter as tk
from PIL import Image, ImageTk

from theme import THEME


# Click sound hook. The HayDayHelperApp installs an AudioManager via
# set_click_sound_handler() at startup; if no handler is installed,
# button clicks are silent (e.g. during tests).
_CLICK_HANDLER = None


def set_click_sound_handler(handler):
    """Register a no-arg callable invoked on every button press."""
    global _CLICK_HANDLER
    _CLICK_HANDLER = handler


def _play_click():
    if _CLICK_HANDLER is not None:
        try:
            _CLICK_HANDLER()
        except Exception:
            pass


# ---- image handling --------------------------------------------------------

class ImageCache:
    """Loads original PIL images once, then hands out resized PhotoImages.

    Tk's PhotoImage instances must be kept alive (anchored on `self`) or they
    get garbage-collected and the images vanish. The cache keeps everything in
    a dict keyed by (name, size).
    """

    def __init__(self, assets_dir: str):
        self.assets_dir = assets_dir
        self._originals = {}  # name -> PIL.Image
        self._photos = {}     # (name, w, h) -> ImageTk.PhotoImage

    def _get_original(self, name: str) -> Image.Image:
        if name not in self._originals:
            path = os.path.join(self.assets_dir, name + ".png")
            if not os.path.exists(path):
                raise FileNotFoundError(f"Image not found: {path}")
            self._originals[name] = Image.open(path).convert("RGBA")
        return self._originals[name]

    def get(self, name: str, max_size: int) -> ImageTk.PhotoImage:
        """Return a PhotoImage scaled so its longest side <= max_size px."""
        original = self._get_original(name)
        # compute target size keeping aspect ratio
        w, h = original.size
        scale = max_size / max(w, h)
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        key = (name, new_size[0], new_size[1])
        if key not in self._photos:
            resized = original.resize(new_size, Image.LANCZOS)
            self._photos[key] = ImageTk.PhotoImage(resized)
        return self._photos[key]

    def clear_scaled(self):
        """Free all resized variants. Call on big resize events."""
        self._photos.clear()


# ---- rounded button --------------------------------------------------------

class RoundedButton(tk.Canvas):
    """A simple rounded-rectangle button drawn on a Canvas.

    Why not ttk? ttk buttons are hard to recolor consistently across platforms,
    and we want the chunky Hay Day look (big, colorful, rounded).
    """

    def __init__(self, parent, text: str, command=None,
                 width: int = 120, height: int = 44,
                 bg_color: str = None, hover_color: str = None,
                 text_color: str = None, font=None, radius: int = 14,
                 disabled: bool = False, shadow: bool = True, **kwargs):
        bg_color = bg_color or THEME["btn_green"]
        hover_color = hover_color or THEME["btn_green_hover"]
        text_color = text_color or THEME["text_light"]
        font = font or THEME["font_button"]
        self._shadow_enabled = shadow

        # pull `bg` from kwargs if the caller passed one for the parent fill
        parent_bg = kwargs.pop("parent_bg", None)
        if parent_bg is None:
            try:
                parent_bg = parent.cget("bg")
            except tk.TclError:
                parent_bg = THEME["bg_main"]

        super().__init__(parent, width=width, height=height,
                         bg=parent_bg, highlightthickness=0, bd=0, **kwargs)

        self.command = command
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.text_color = text_color
        self.disabled_color = THEME["btn_disabled"]
        self.text = text
        self.font = font
        self.radius = radius
        self.disabled_state = disabled
        # NB: do NOT use self._w / self._h - those names are reserved by
        # tkinter (Misc._w stores the Tcl widget path, e.g. ".!frame.!canvas").
        # Overwriting it breaks pack() with "bad argument N: must be name of window".
        self._btn_w = width
        self._btn_h = height

        # we don't draw here - the first <Configure> event fires once the
        # widget is packed and has its actual geometry, and that's when we
        # do the initial paint. Trying to draw earlier (or via after_idle)
        # races with pack() and tk gets confused.
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Configure>", self._on_resize)

    def _draw(self, fill=None):
        try:
            self.delete("all")
        except tk.TclError:
            self.after_idle(lambda: self._draw(fill))
            return
        w = self.winfo_width() or self._btn_w
        h = self.winfo_height() or self._btn_h
        r = min(self.radius, h // 2, w // 2)
        color = (self.disabled_color if self.disabled_state
                 else (fill or self.bg_color))

        # ----- subtle drop shadow underneath the button -----
        # Drawn as a darker version of the parent bg, offset 2px down/right.
        # We don't draw shadow when disabled (looks weird) or for tiny buttons.
        if (self._shadow_enabled and not self.disabled_state
                and w > 40 and h > 24):
            shadow_color = self._shadow_color()
            sx, sy = 2, 2  # offset
            self.create_arc((0 + sx, 0 + sy, 2 * r + sx, 2 * r + sy),
                            start=90, extent=90,
                            fill=shadow_color, outline=shadow_color)
            self.create_arc((w - 2 * r + sx, 0 + sy, w + sx, 2 * r + sy),
                            start=0, extent=90,
                            fill=shadow_color, outline=shadow_color)
            self.create_arc((0 + sx, h - 2 * r + sy, 2 * r + sx, h + sy),
                            start=180, extent=90,
                            fill=shadow_color, outline=shadow_color)
            self.create_arc((w - 2 * r + sx, h - 2 * r + sy, w + sx, h + sy),
                            start=270, extent=90,
                            fill=shadow_color, outline=shadow_color)
            self.create_rectangle((r + sx, 0 + sy, w - r + sx, h + sy),
                                   fill=shadow_color, outline=shadow_color)
            self.create_rectangle((0 + sx, r + sy, w + sx, h - r + sy),
                                   fill=shadow_color, outline=shadow_color)

        # ----- main button on top of the shadow -----
        # rounded rectangle via 4 arcs + 2 rectangles
        self.create_arc((0, 0, 2 * r, 2 * r), start=90, extent=90,
                        fill=color, outline=color)
        self.create_arc((w - 2 * r, 0, w, 2 * r), start=0, extent=90,
                        fill=color, outline=color)
        self.create_arc((0, h - 2 * r, 2 * r, h), start=180, extent=90,
                        fill=color, outline=color)
        self.create_arc((w - 2 * r, h - 2 * r, w, h), start=270, extent=90,
                        fill=color, outline=color)
        self.create_rectangle((r, 0, w - r, h), fill=color, outline=color)
        self.create_rectangle((0, r, w, h - r), fill=color, outline=color)

        text_color = (THEME["text_muted"] if self.disabled_state
                      else self.text_color)
        self.create_text(w // 2, h // 2, text=self.text,
                         fill=text_color, font=self.font)

    def _shadow_color(self) -> str:
        """Return a slightly darker shade of the parent bg for the drop shadow.
        Falls back to a neutral grey if parent bg can't be parsed."""
        try:
            parent_bg = self.cget("bg")
            if not parent_bg.startswith("#") or len(parent_bg) != 7:
                return "#888888"
            r = int(parent_bg[1:3], 16)
            g = int(parent_bg[3:5], 16)
            b = int(parent_bg[5:7], 16)
            # darken by ~15%
            r = max(0, int(r * 0.78))
            g = max(0, int(g * 0.78))
            b = max(0, int(b * 0.78))
            return f"#{r:02X}{g:02X}{b:02X}"
        except (tk.TclError, ValueError):
            return "#888888"

    def _on_resize(self, event):
        self._btn_w, self._btn_h = event.width, event.height
        self._draw()

    def _on_enter(self, _event):
        if not self.disabled_state:
            self._draw(fill=self.hover_color)
            self.config(cursor="hand2")

    def _on_leave(self, _event):
        if not self.disabled_state:
            self._draw()
            self.config(cursor="")

    def _on_click(self, _event):
        if not self.disabled_state and self.command:
            _play_click()
            self.command()

    def set_disabled(self, disabled: bool):
        if self.disabled_state == disabled:
            return
        self.disabled_state = disabled
        self._draw()

    def set_text(self, text: str):
        self.text = text
        self._draw()

    def set_colors(self, bg_color: str, hover_color: str):
        self.bg_color = bg_color
        self.hover_color = hover_color
        self._draw()


# ---- entry with placeholder ------------------------------------------------

class LabeledEntry(tk.Frame):
    """A small composite widget: a label above an Entry, with optional default."""
    def __init__(self, parent, label: str, default: str = "", width: int = 22, **kwargs):
        super().__init__(parent, bg=parent.cget("bg"), **kwargs)
        tk.Label(self, text=label, font=THEME["font_body_bold"],
                 bg=self.cget("bg"), fg=THEME["text_dark"]).pack(anchor="w")
        self.var = tk.StringVar(value=default)
        self.entry = tk.Entry(self, textvariable=self.var, width=width,
                              font=THEME["font_body"], relief="solid", bd=1)
        self.entry.pack(fill="x", ipady=4)

    def get(self) -> str:
        return self.var.get().strip()

    def set(self, value: str):
        self.var.set(value)
