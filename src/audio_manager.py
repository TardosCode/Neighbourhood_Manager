"""
Audio manager for the Hay Day Helper.

Two channels:
  - Music: background tracks from audio/music/. Shuffled once into a playlist,
    plays one after another. When the list ends, re-shuffles and starts over.
    A new random shuffle ensures the same track doesn't repeat back-to-back.
  - SFX: short click sound played on every button.

Audio settings are persisted in settings/audio.json:
  {
    "music_enabled": bool, "music_volume": 0..1,
    "sfx_enabled": bool, "sfx_volume": 0..1
  }

If pygame fails to initialize (e.g. missing audio device, headless env),
the manager silently no-ops. Better than crashing on machines without
sound hardware.
"""

import json
import os
import random
import threading
from typing import Optional


# ----- defaults -------------------------------------------------------------

DEFAULT_AUDIO_SETTINGS = {
    "music_enabled": True,
    "music_volume": 0.4,
    "sfx_enabled": True,
    "sfx_volume": 0.5,
}


def _load_pygame():
    """Try to import and init pygame. Returns the module on success, None
    otherwise. We don't want to hard-fail the whole app if audio is missing."""
    try:
        import pygame
        # explicitly init only the mixer - pygame.init() pulls in display too
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        return pygame
    except Exception as e:
        # any failure (no device, missing libsdl, etc.) - run silently
        print(f"[audio] pygame init failed, audio disabled: {e}")
        return None


class AudioManager:
    """Owns the audio state and plays files. One instance per app."""

    def __init__(self, music_dir: str, sfx_dir: str, settings_path: str):
        self.music_dir = music_dir
        self.sfx_dir = sfx_dir
        self.settings_path = settings_path

        self.settings = self._load_settings()

        # pygame (or None if unavailable)
        self._pg = _load_pygame()

        # state
        self._playlist = []         # list of full mp3 paths
        self._playlist_index = -1
        self._current_track = None  # filename only, for display
        self._click_sound = None    # pygame Sound instance for sfx
        self._poll_thread = None
        self._poll_stop = threading.Event()

        # one mixer channel for click so it doesn't fight with music
        self._click_channel = None

        if self._pg is not None:
            self._pg.mixer.set_num_channels(8)
            self._click_channel = self._pg.mixer.Channel(0)
            self._load_click()
            self.reload_music()
            self._start_poll_thread()

    # ---- settings ---------------------------------------------------------
    def _load_settings(self) -> dict:
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # merge in any new defaults
                merged = dict(DEFAULT_AUDIO_SETTINGS)
                merged.update(data)
                return merged
            except (OSError, json.JSONDecodeError):
                pass
        return dict(DEFAULT_AUDIO_SETTINGS)

    def _save_settings(self):
        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except OSError as e:
            print(f"[audio] could not save settings: {e}")

    # ---- music ------------------------------------------------------------
    def reload_music(self):
        """Re-scan the music folder. If a track is currently playing, finish
        it before rotating to the new shuffle."""
        if self._pg is None:
            return
        if not os.path.isdir(self.music_dir):
            self._playlist = []
            return
        files = []
        for name in os.listdir(self.music_dir):
            if name.lower().endswith(".mp3"):
                files.append(os.path.join(self.music_dir, name))
        random.shuffle(files)
        # avoid having the currently-playing track be also the first one of
        # the new shuffle - rotate it out if needed
        if self._current_track and len(files) > 1:
            cur_full = os.path.join(self.music_dir, self._current_track)
            if files and files[0] == cur_full:
                files.append(files.pop(0))
        self._playlist = files
        self._playlist_index = -1

        if self.settings["music_enabled"] and self._playlist and not self._is_music_playing():
            self._advance_track()

    def _is_music_playing(self) -> bool:
        if self._pg is None:
            return False
        try:
            return self._pg.mixer.music.get_busy()
        except Exception:
            return False

    def _advance_track(self):
        """Move to the next track. Re-shuffles when the list ends."""
        if self._pg is None or not self._playlist:
            return
        self._playlist_index += 1
        if self._playlist_index >= len(self._playlist):
            # reshuffle
            random.shuffle(self._playlist)
            self._playlist_index = 0

        track = self._playlist[self._playlist_index]
        self._current_track = os.path.basename(track)
        try:
            self._pg.mixer.music.load(track)
            self._pg.mixer.music.set_volume(self.settings["music_volume"])
            self._pg.mixer.music.play()
        except Exception as e:
            print(f"[audio] failed to play {track}: {e}")
            # skip and try the next
            self._current_track = None

    def skip_track(self):
        if self._pg is None:
            return
        try:
            self._pg.mixer.music.stop()
        except Exception:
            pass
        self._advance_track()

    def _start_poll_thread(self):
        """Background thread that advances the track when the current one
        ends. pygame doesn't fire events for that without a tk-incompatible
        event loop, so we poll."""
        if self._poll_thread is not None:
            return

        def loop():
            while not self._poll_stop.is_set():
                self._poll_stop.wait(0.5)
                if self._poll_stop.is_set():
                    break
                if (self.settings["music_enabled"]
                        and self._playlist
                        and not self._is_music_playing()):
                    try:
                        self._advance_track()
                    except Exception:
                        pass

        self._poll_thread = threading.Thread(target=loop, daemon=True)
        self._poll_thread.start()

    # ---- sfx --------------------------------------------------------------
    def _load_click(self):
        if self._pg is None:
            return
        path = os.path.join(self.sfx_dir, "click.mp3")
        if not os.path.exists(path):
            return
        try:
            self._click_sound = self._pg.mixer.Sound(path)
        except Exception as e:
            print(f"[audio] could not load click sound: {e}")
            self._click_sound = None

    def play_click(self):
        if (self._pg is None or self._click_sound is None
                or not self.settings["sfx_enabled"]):
            return
        try:
            self._click_sound.set_volume(self.settings["sfx_volume"])
            self._click_channel.play(self._click_sound)
        except Exception:
            pass

    # ---- runtime controls -------------------------------------------------
    def set_music_enabled(self, on: bool):
        self.settings["music_enabled"] = bool(on)
        self._save_settings()
        if self._pg is None:
            return
        if on:
            if self._playlist and not self._is_music_playing():
                self._advance_track()
        else:
            try:
                self._pg.mixer.music.stop()
            except Exception:
                pass

    def set_music_volume(self, vol: float):
        v = max(0.0, min(1.0, float(vol)))
        self.settings["music_volume"] = v
        self._save_settings()
        if self._pg is None:
            return
        try:
            self._pg.mixer.music.set_volume(v)
        except Exception:
            pass

    def set_sfx_enabled(self, on: bool):
        self.settings["sfx_enabled"] = bool(on)
        self._save_settings()

    def set_sfx_volume(self, vol: float):
        v = max(0.0, min(1.0, float(vol)))
        self.settings["sfx_volume"] = v
        self._save_settings()

    def get_current_track(self) -> Optional[str]:
        if self._pg is None or not self.settings["music_enabled"]:
            return None
        return self._current_track if self._is_music_playing() else None

    def get_playlist_count(self) -> int:
        return len(self._playlist)

    # ---- shutdown ---------------------------------------------------------
    def shutdown(self):
        self._poll_stop.set()
        if self._pg is not None:
            try:
                self._pg.mixer.music.stop()
                self._pg.mixer.quit()
            except Exception:
                pass
