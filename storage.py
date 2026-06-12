import json
import os
from app_config import MEMORIA_FAJL

class MemoryManager:
    @staticmethod
    def load_memory():
        if os.path.exists(MEMORIA_FAJL):
            try:
                with open(MEMORIA_FAJL, "r", encoding="utf-8") as f:
                    return json.load(f).get("memoria", "A projekt még nem kezdődött el.")
            except Exception:
                return "A projekt még nem kezdődött el."
        return "A projekt még nem kezdődött el."

    @staticmethod
    def save_memory(memoria_szoveg):
        with open(MEMORIA_FAJL, "w", encoding="utf-8") as f:
            json.dump({"memoria": memoria_szoveg}, f, ensure_ascii=False, indent=4)

    @staticmethod
    def clear_memory():
        if os.path.exists(MEMORIA_FAJL):
            os.remove(MEMORIA_FAJL)
