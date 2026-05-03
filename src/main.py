"""
Hay Day Helper - main entry point.

Run from the project root:
    python src/main.py
"""

import os
import sys
import tkinter as tk
from tkinter import messagebox

# Local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_manager import ProfileManager
from neighborhood_manager import NeighborhoodManager
from audio_manager import AudioManager
from theme_manager import ThemeManager
from video_settings import VideoSettings

import widgets  # for set_click_sound_handler

from ui_main_menu import MainMenuFrame
from ui_expansion_helper import ExpansionHelperFrame
from ui_profile_screen import ProfileScreen
from ui_neighborhood_select import NeighborhoodSelectorScreen
from ui_neighborhood_manager import NeighborhoodManagerFrame
from ui_member_detail import MemberDetailFrame
from ui_app_settings import AppSettingsFrame
from ui_other_tools import OtherToolsFrame
from theme import THEME


# ---------- path helpers -----------------------------------------------------

def get_base_dir() -> str:
    """Return the project root, whether running from source or PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_assets_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", get_base_dir()), "assets")
    return os.path.join(get_base_dir(), "assets")


def get_profiles_dir() -> str:
    return os.path.join(get_base_dir(), "profiles")


def get_neighborhoods_dir() -> str:
    return os.path.join(get_base_dir(), "neighborhoods")


def get_settings_dir() -> str:
    return os.path.join(get_base_dir(), "settings")


def get_audio_dir() -> str:
    return os.path.join(get_base_dir(), "audio")


# ---------- main app ---------------------------------------------------------

class HayDayHelperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Neighbourhood Manager")
        self.geometry("1100x700")
        self.minsize(900, 640)

        # ----- config / managers must be set up BEFORE THEME-dependent UI -----
        os.makedirs(get_settings_dir(), exist_ok=True)
        settings_dir = get_settings_dir()

        # theme: load saved overrides into THEME before any widget reads colors
        self.theme_manager = ThemeManager(
            os.path.join(settings_dir, "theme.json"))

        # video settings (fullscreen)
        self.video_settings = VideoSettings(
            os.path.join(settings_dir, "video.json"))

        self.configure(bg=THEME["bg_main"])

        # icon
        try:
            icon_path = os.path.join(get_assets_dir(), "silo.png")
            if os.path.exists(icon_path):
                self.iconphoto(True, tk.PhotoImage(file=icon_path))
        except tk.TclError:
            pass

        # data managers
        self.assets_dir = get_assets_dir()
        self.profile_manager = ProfileManager(get_profiles_dir())
        self.neighborhood_manager = NeighborhoodManager(get_neighborhoods_dir())

        # audio - last because it's expensive to init and we don't want
        # other init failures to leave the audio thread orphaned
        audio_dir = get_audio_dir()
        self.audio_manager = AudioManager(
            music_dir=os.path.join(audio_dir, "music"),
            sfx_dir=os.path.join(audio_dir, "sfx"),
            settings_path=os.path.join(settings_dir, "audio.json"),
        )
        # hook click sound into every RoundedButton
        widgets.set_click_sound_handler(self.audio_manager.play_click)

        # apply persisted fullscreen state
        if self.video_settings.get("fullscreen"):
            try:
                self.attributes("-fullscreen", True)
            except tk.TclError:
                pass

        # F11 toggles fullscreen
        self.bind("<F11>", self._on_f11)
        self.bind("<Escape>",
                  lambda e: self.set_fullscreen(False) if self.attributes("-fullscreen") else None)

        # close-window handler - clean shutdown for audio thread
        self.protocol("WM_DELETE_WINDOW", self.quit_app)

        # frame container
        self.container = tk.Frame(self, bg=THEME["bg_main"])
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        self.current_frame_name = None

        # initial screen
        active = self.profile_manager.get_active_profile()
        if active is None:
            self.show_frame("ProfileScreen", first_run=True)
        else:
            self.show_frame("MainMenu")

    # ---- screen management -----------------------------------------------
    def show_frame(self, name: str, **kwargs):
        if self.current_frame_name is not None:
            old = self.frames.pop(self.current_frame_name, None)
            if old is not None:
                old.destroy()

        if name == "MainMenu":
            frame = MainMenuFrame(self.container, app=self)
        elif name == "ExpansionHelper":
            frame = ExpansionHelperFrame(self.container, app=self)
        elif name == "ProfileScreen":
            frame = ProfileScreen(self.container, app=self,
                                  first_run=kwargs.get("first_run", False),
                                  return_to=kwargs.get("return_to", "MainMenu"))
        elif name == "NeighborhoodSelect":
            frame = NeighborhoodSelectorScreen(
                self.container, app=self,
                first_run=kwargs.get("first_run", False),
                return_to=kwargs.get("return_to", "MainMenu"),
            )
        elif name == "NeighborhoodManager":
            if self.neighborhood_manager.get_active() is None:
                frame = NeighborhoodSelectorScreen(self.container, app=self,
                                                   first_run=True)
                self.current_frame_name = "NeighborhoodSelect"
                self.frames["NeighborhoodSelect"] = frame
                frame.grid(row=0, column=0, sticky="nsew")
                return
            frame = NeighborhoodManagerFrame(self.container, app=self)
        elif name == "MemberDetail":
            mid = kwargs.get("member_id")
            if mid is None:
                raise ValueError("MemberDetail requires member_id")
            frame = MemberDetailFrame(self.container, app=self, member_id=mid)
        elif name == "AppSettings":
            initial_section = kwargs.get("initial_section", "Audio")
            return_to = kwargs.get("return_to",
                                    getattr(self, "_last_non_settings_frame",
                                            "MainMenu"))
            frame = AppSettingsFrame(self.container, app=self,
                                      return_to=return_to,
                                      initial_section=initial_section)
        elif name == "OtherTools":
            frame = OtherToolsFrame(self.container, app=self)
        else:
            raise ValueError(f"Unknown frame: {name}")

        # remember the last non-settings frame so Settings can return to it
        if name != "AppSettings":
            self._last_non_settings_frame = name

        frame.grid(row=0, column=0, sticky="nsew")
        self.frames[name] = frame
        self.current_frame_name = name

    # ---- theme refresh ---------------------------------------------------
    def refresh_theme(self):
        """Re-render the current frame so theme changes are visible.
        Also re-apply our own bg color."""
        try:
            self.configure(bg=THEME["bg_main"])
            self.container.configure(bg=THEME["bg_main"])
        except tk.TclError:
            pass
        if self.current_frame_name:
            self.show_frame(self.current_frame_name)

    # ---- fullscreen ------------------------------------------------------
    def set_fullscreen(self, on: bool):
        try:
            self.attributes("-fullscreen", bool(on))
        except tk.TclError:
            pass
        self.video_settings.set("fullscreen", bool(on))

    def _on_f11(self, _event=None):
        cur = bool(self.attributes("-fullscreen"))
        self.set_fullscreen(not cur)

    # ---- exit -----------------------------------------------------------
    def quit_app(self):
        try:
            self.audio_manager.shutdown()
        except Exception:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass


def main():
    app = HayDayHelperApp()
    app.mainloop()


if __name__ == "__main__":
    main()
