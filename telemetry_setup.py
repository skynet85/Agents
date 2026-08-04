# telemetry_setup.py
"""OpenTelemetry inicializálás: a span-eket egy helyi JSON fájlba írjuk.

Két korábbi hiba javítva:
  * a BatchSpanProcessor puffere sosem ürült ki (nem volt shutdown/flush),
    így a dashboard gyakran üresen maradt;
  * a megnyitott fájl-leíró sosem záródott be.
"""
from __future__ import annotations

import atexit
import logging
import threading

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

import config

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_initialized = False


def _rotate_if_needed() -> None:
    """A trace fájl méretének korlátozása (egyszerű, egy generációs rotáció)."""
    try:
        if config.TRACE_FAJL.exists() and config.TRACE_FAJL.stat().st_size > config.TRACE_MAX_BYTES:
            backup = config.TRACE_FAJL.with_suffix(".1.json")
            backup.unlink(missing_ok=True)
            config.TRACE_FAJL.replace(backup)
            logger.info("A trace fájl rotálva: %s", backup.name)
    except OSError as exc:
        logger.warning("A trace fájl rotációja sikertelen: %s", exc)


def init_opentelemetry() -> None:
    """Idempotens inicializálás: Streamlit rerun esetén sem duplikálódik."""
    global _initialized

    with _lock:
        if _initialized or isinstance(trace.get_tracer_provider(), TracerProvider):
            return

        _rotate_if_needed()

        provider = TracerProvider()
        # A fájlt a folyamat teljes életciklusára nyitva tartjuk; a lezárásról
        # és a puffer ürítéséről az atexit hook gondoskodik.
        fajl_folyam = open(config.TRACE_FAJL, "a", encoding="utf-8")  # noqa: SIM115
        processor = BatchSpanProcessor(ConsoleSpanExporter(out=fajl_folyam))
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

        def _shutdown() -> None:
            try:
                provider.shutdown()  # flush + exporter lezárása
            except Exception:  # noqa: BLE001
                pass
            finally:
                try:
                    fajl_folyam.close()
                except OSError:
                    pass

        atexit.register(_shutdown)
        _initialized = True
        logger.info("OpenTelemetry inicializálva: %s", config.TRACE_FAJL)


def flush_traces() -> None:
    """Kikényszeríti a pufferelt span-ek kiírását (a dashboard frissítéséhez)."""
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        try:
            provider.force_flush(timeout_millis=3000)
        except Exception as exc:  # noqa: BLE001
            logger.debug("force_flush sikertelen: %s", exc)
