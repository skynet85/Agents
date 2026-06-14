import json
import os
from datetime import datetime

# Ha nálad a config.py-ból jön, azt is használhatod, de itt biztonságból fixáljuk
MEMORIA_FAJL = "szimulacio_memoria.json"

def load_all_runs():
    """Betölti az összes korábbi futást a JSON fájlból egy listába."""
    if os.path.exists(MEMORIA_FAJL):
        try:
            with open(MEMORIA_FAJL, "r", encoding="utf-8") as f:
                adat = json.load(f)
                return adat.get("runs", [])
        except Exception:
            return []
    return []

def save_run(run_id, datum, feladat, memoria, uzenetek, telemetria, ertekelesek):
    """Elmenti vagy frissíti az adott futást az egyedi azonosítója (run_id) alapján."""
    runs = load_all_runs()
    
    run_data = {
        "run_id": run_id,
        "datum": datum,
        "feladat": feladat,
        "memoria": memoria,
        "uzenetek": uzenetek,
        "telemetria": telemetria,
        "ertekelesek": ertekelesek
    }
    
    # Megkeressük, hogy létezik-e már ez a futás. Ha igen, felülírjuk az új adatokkal, ha nem, hozzáfűzzük.
    existing_idx = next((i for i, r in enumerate(runs) if r.get("run_id") == run_id), None)
    if existing_idx is not None:
        runs[existing_idx] = run_data
    else:
        runs.append(run_data)
        
    with open(MEMORIA_FAJL, "w", encoding="utf-8") as f:
        json.dump({"runs": runs}, f, ensure_ascii=False, indent=4)

def clear_memory_file():
    """Törli a mentett memóriát egy teljes hard reset esetén."""
    if os.path.exists(MEMORIA_FAJL):
        os.remove(MEMORIA_FAJL)