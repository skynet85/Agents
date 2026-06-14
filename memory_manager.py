# memory_manager.py
import json
import os
from config import MEMORIA_FAJL

def load_memory():
    """Betölti a projekt memóriát, a telemetriát pedig nullázza induláskor."""
    if os.path.exists(MEMORIA_FAJL):
        try:
            with open(MEMORIA_FAJL, "r", encoding="utf-8") as f:
                adat = json.load(f)
                return adat.get("memoria", "A projekt még nem kezdődött el."), {'osszes_ido': 0.0, 'osszes_token': 0, 'agensek': {}}
        except Exception:
            return "A projekt még nem kezdődött el.", {'osszes_ido': 0.0, 'osszes_token': 0, 'agensek': {}}
    return "A projekt még nem kezdődött el.", {'osszes_ido': 0.0, 'osszes_token': 0, 'agensek': {}}

def save_memory(memoria_szoveg, telemetria):
    """Kimenti a projekt memóriát és a telemetriát a fizikai JSON fájlba."""
    with open(MEMORIA_FAJL, "w", encoding="utf-8") as f:
        json.dump({"memoria": memoria_szoveg, "telemetria": telemetria}, f, ensure_ascii=False, indent=4)

def clear_memory_file():
    """Törli a mentett memóriát egy teljes reset esetén."""
    if os.path.exists(MEMORIA_FAJL):
        os.remove(MEMORIA_FAJL)