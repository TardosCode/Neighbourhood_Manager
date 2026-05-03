"""
Video settings manager: fullscreen on/off, persisted in settings/video.json.
Tiny module - mostly here so future video settings have a home.
"""

import json
import os


DEFAULT_VIDEO_SETTINGS = {
    "fullscreen": False,
}


class VideoSettings:
    def __init__(self, settings_path: str):
        self.settings_path = settings_path
        self.settings = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                merged = dict(DEFAULT_VIDEO_SETTINGS)
                merged.update(data)
                return merged
            except (OSError, json.JSONDecodeError):
                pass
        return dict(DEFAULT_VIDEO_SETTINGS)

    def save(self):
        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except OSError as e:
            print(f"[video] could not save: {e}")

    def get(self, key: str):
        return self.settings.get(key, DEFAULT_VIDEO_SETTINGS.get(key))

    def set(self, key: str, value):
        self.settings[key] = value
        self.save()
