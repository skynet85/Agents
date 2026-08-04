# memory_manager.py
"""JSON-alapú, atomikus perzisztencia a szimulációs futásokhoz."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

import config

logger = logging.getLogger(__name__)


def load_all_runs() -> List[Dict[str, Any]]:
    """Betölti az összes korábbi futást. Sérült fájl esetén üres listát ad."""
    if not config.MEMORIA_FAJL.exists():
        return []
    try:
        with open(config.MEMORIA_FAJL, "r", encoding="utf-8") as f:
            adat = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("A memóriafájl nem olvasható (%s). Üres előzménnyel indulunk.", exc)
        return []

    runs = adat.get("runs", []) if isinstance(adat, dict) else []
    # Csak a strukturálisan érvényes futásokat adjuk vissza.
    return [r for r in runs if isinstance(r, dict) and r.get("run_id")]


def _atomic_write(payload: Dict[str, Any]) -> None:
    """Ideiglenes fájlba ír, majd atomikusan átnevez.

    Így egy megszakadt mentés nem teszi tönkre a korábbi adatokat.
    """
    cel = config.MEMORIA_FAJL
    cel.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=str(cel.parent), prefix=".memoria_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, cel)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def save_run(
    run_id: Optional[str],
    datum: Optional[str],
    feladat: str,
    memoria: str,
    uzenetek: List[Dict[str, str]],
    telemetria: Dict[str, Any],
    ertekelesek: Dict[str, int],
    munkaterulet: Optional[Dict[str, Any]] = None,
) -> bool:
    """Elmenti vagy frissíti az adott futást a `run_id` alapján.

    `True`-val tér vissza, ha a mentés sikerült.
    """
    if not run_id:
        logger.warning("save_run hívás run_id nélkül – a mentés kimarad.")
        return False

    runs = load_all_runs()
    run_data = {
        "run_id": run_id,
        "datum": datum or "",
        "feladat": feladat or "",
        "memoria": memoria or "",
        "uzenetek": uzenetek or [],
        "telemetria": telemetria or {},
        "ertekelesek": ertekelesek or {},
        "munkaterulet": munkaterulet or {},
    }

    existing_idx = next((i for i, r in enumerate(runs) if r.get("run_id") == run_id), None)
    if existing_idx is not None:
        runs[existing_idx] = run_data
    else:
        runs.append(run_data)

    try:
        _atomic_write({"runs": runs})
        return True
    except OSError as exc:
        logger.error("A futás mentése sikertelen: %s", exc)
        return False


def delete_run(run_id: str) -> bool:
    """Töröl egyetlen futást az előzményekből."""
    runs = load_all_runs()
    maradek = [r for r in runs if r.get("run_id") != run_id]
    if len(maradek) == len(runs):
        return False
    try:
        _atomic_write({"runs": maradek})
        return True
    except OSError as exc:
        logger.error("A futás törlése sikertelen: %s", exc)
        return False


def clear_memory_file() -> None:
    """Törli a mentett memóriát egy teljes hard reset esetén."""
    try:
        config.MEMORIA_FAJL.unlink(missing_ok=True)
    except OSError as exc:
        logger.error("A memóriafájl törlése sikertelen: %s", exc)
