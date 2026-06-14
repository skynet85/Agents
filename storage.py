# storage.py

import json
from pathlib import Path
from typing import Dict, Any, Optional

MEMORY_FILE = Path("project_memory.json")


class MemoryManager:
    """High-level memory management wrapper (e.g., for chat history, personas)."""

    def __init__(self):
        self._storage = MemoryStorage()

    def get(self, key: str, default=None) -> Any:
        return self._storage.retrieve(key, default)

    def set(self, key: str, value: Any):
        self._storage.store(key, value)

    def save(self, filepath=MEMORY_FILE):
        self._storage.save_to_file(filepath)

    @classmethod
    def load(cls, filepath=MEMORY_FILE) -> "MemoryManager":
        mm = cls()
        mm._storage = MemoryStorage.load_from_file(filepath)
        return mm

    # Convenience: act like a dict for common keys
    def __contains__(self, key):
        return key in self._storage._data

    def items(self):
        return self._storage._data.items()


class MemoryStorage:
    """Low-level JSON-backed storage."""

    def __init__(self):
        self._data = {}

    def store(self, key: str, value):
        self._data[key] = value

    def retrieve(self, key: str, default=None):
        return self._data.get(key, default)

    def save_to_file(self, filepath=MEMORY_FILE):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load_from_file(cls, filepath=MEMORY_FILE) -> "MemoryStorage":
        storage = cls()
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    storage._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return storage


# Legacy helpers for compatibility
def save_memory(proj_mem: str):
    mm = MemoryManager()
    mm.set("projekt_memoria", proj_mem)
    mm.save()


def load_memory() -> str:
    mm = MemoryManager.load()
    return mm.get("projekt_memoria", "")