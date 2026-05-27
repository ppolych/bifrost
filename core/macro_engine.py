import logging

from core.platform_utils import atomic_write_json, config_path, load_json

log = logging.getLogger(__name__)


class MacroEngine:
    def __init__(self, filename: str = "macros.json"):
        self.filename = config_path(filename)
        self.macros = self.load()
        self.recording = False
        self.current_macro: list[str] = []

    def load(self):
        return load_json(self.filename, {})

    def save(self):
        try:
            atomic_write_json(self.filename, self.macros)
        except OSError:
            log.exception("Failed to save macros to %s", self.filename)

    def start_recording(self):
        self.recording = True
        self.current_macro = []

    def stop_recording(self, name):
        self.recording = False
        if self.current_macro:
            self.macros[name] = self.current_macro
            self.save()
            return True
        return False

    def record_key(self, key):
        if self.recording:
            self.current_macro.append(key)

    def get_macro(self, name):
        return self.macros.get(name, [])
