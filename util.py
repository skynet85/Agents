# util.py
"""Segédfüggvények: drótváz-kinyerés, telemetria-mérés, hibatűrő LLM hívás."""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, Optional, Tuple

import streamlit as st
import streamlit.components.v1 as components
from opentelemetry import trace

import config
from ui_components import render_telemetry_dashboard

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Három backtick, kódból generálva – így a forrásfájl markdown-parserei
# nem esnek szét a mintákon.
BT = chr(96) * 3

_HTML_JELEK = ("<html", "<body", "<div", "<form", "<nav", "<button", "<style", "<script")


class AgensFutasHiba(RuntimeError):
    """Az LLM hívás sikertelen volt (pl. nem fut az LM Studio szerver)."""


def extract_wireframe_code(text: str) -> Optional[str]:
    """Kinyeri a HTML kódot a szövegből. Tiszta logika, UI beavatkozás nélkül."""
    if not text:
        return None

    # 1. Explicit HTML/Tailwind kódblokk
    pattern_explicit = rf"{BT}(?:html|xml|tailwind)\s*(.*?)\s*{BT}"
    explicit_matches = re.findall(pattern_explicit, text, re.DOTALL | re.IGNORECASE)
    if explicit_matches:
        return max(explicit_matches, key=len)

    # 2. Nyelv nélküli kódblokk, ami HTML-nek tűnik
    pattern_general = rf"{BT}[a-zA-Z0-9-]*\s*(.*?)\s*{BT}"
    general_matches = re.findall(pattern_general, text, re.DOTALL)
    jeloltek = [m for m in general_matches if any(tag in m.lower() for tag in _HTML_JELEK)]
    if jeloltek:
        return max(jeloltek, key=len)

    # 3. Fallback: nyers HTML kódblokk nélkül
    match = re.search(
        r"(<!DOCTYPE html>.*?</html>|<html.*?>.*?</html>|<div\b[^>]*>.*</div>)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    return match.group(1) if match else None


def render_wireframe_ui(html_code: str, mentes: bool = True) -> None:
    """Streamlit komponens a HTML kód megjelenítésére."""
    if not html_code:
        return

    with st.expander("🎨 UX/UI Drótváz Megtekintése", expanded=True):
        st.info("A UX Designer által generált élő drótváz:")
        components.html(html_code, height=600, scrolling=True)

    if not mentes:
        return
    try:
        config.DROTVAZ_FAJL.write_text(html_code, encoding="utf-8")
    except OSError as exc:
        logger.warning("A drótvázat nem sikerült lementeni: %s", exc)


def refresh_telemetry_ui(placeholder: Optional[Any]) -> None:
    """Frissíti a telemetria panelt."""
    if placeholder is None:
        return
    telemetria = st.session_state.get("telemetria") or {}
    with placeholder.container():
        render_telemetry_dashboard(telemetria, st.session_state.get("telemetry_toggle", False))


def _ures_telemetria() -> Dict[str, Any]:
    return {"osszes_ido": 0.0, "osszes_token": 0, "agensek": {}}


def _extract_valasz(response: Any) -> Tuple[str, int]:
    """Kinyeri a válaszszöveget és a token-számot a modell válaszából."""
    szoveg = getattr(response, "content", None)
    if szoveg is None:
        szoveg = str(response)
    elif isinstance(szoveg, list):
        # Néhány provider blokk-listát ad vissza.
        szoveg = "".join(
            blokk.get("text", "") if isinstance(blokk, dict) else str(blokk) for blokk in szoveg
        )

    metadata = getattr(response, "response_metadata", None) or {}
    usage = metadata.get("token_usage") or {}
    tokenek = usage.get("total_tokens")

    if tokenek is None:
        # LangChain egységesített mezője, ha a provider metadata hiányos.
        usage_metadata = getattr(response, "usage_metadata", None) or {}
        tokenek = usage_metadata.get("total_tokens", 0)

    try:
        tokenek = int(tokenek or 0)
    except (TypeError, ValueError):
        tokenek = 0

    return szoveg, tokenek


def _record_telemetry(agent_name: str, elapsed: float, tokenek: int) -> None:
    telemetria = st.session_state.get("telemetria")
    if not isinstance(telemetria, dict):
        telemetria = _ures_telemetria()
        st.session_state.telemetria = telemetria

    agensek = telemetria.setdefault("agensek", {})
    bejegyzes = agensek.setdefault(agent_name, {"ido": 0.0, "token": 0})
    bejegyzes["ido"] += elapsed
    bejegyzes["token"] += tokenek

    telemetria["osszes_ido"] = telemetria.get("osszes_ido", 0.0) + elapsed
    telemetria["osszes_token"] = telemetria.get("osszes_token", 0) + tokenek


def run_agent_with_telemetry(
    agent_name: str,
    chain: Any,
    invoke_args: Optional[Dict[str, Any]] = None,
    telemetry_placeholder: Optional[Any] = None,
) -> str:
    """Futtatja az ágenst, naplózza a telemetriát a UI-on és OpenTelemetry-vel.

    Hiba esetén `AgensFutasHiba` kivételt dob, de a addigi mérést rögzíti –
    így a hívó tud dönteni a sprint sorsáról ahelyett, hogy az egész
    Streamlit oldal összeomlana.
    """
    invoke_args = invoke_args or {}
    start_time = time.time()

    with tracer.start_as_current_span(f"AgentRun-{agent_name}") as span:
        span.set_attribute("llm.agent.name", agent_name)
        span.set_attribute("llm.task.query", str(invoke_args.get("kerdes", ""))[:4000])
        span.set_attribute("llm.task.original_need", str(invoke_args.get("eredeti_igeny", ""))[:2000])

        try:
            response = chain.invoke(invoke_args)
        except Exception as exc:  # noqa: BLE001 – bármilyen provider-hiba idetartozik
            elapsed_time = time.time() - start_time
            span.set_attribute("llm.duration_seconds", elapsed_time)
            span.set_attribute("llm.error", str(exc)[:2000])
            span.record_exception(exc)
            _record_telemetry(agent_name, elapsed_time, 0)
            logger.exception("Az ágens futása sikertelen: %s", agent_name)
            raise AgensFutasHiba(
                f"A(z) '{agent_name}' ágens hívása sikertelen: {exc}"
            ) from exc

        elapsed_time = time.time() - start_time
        valasz_szoveg, tokenek = _extract_valasz(response)

        span.set_attribute("llm.usage.total_tokens", tokenek)
        span.set_attribute("llm.duration_seconds", elapsed_time)
        span.add_event("Agent válasz sikeresen legenerálva")

    _record_telemetry(agent_name, elapsed_time, tokenek)

    if not st.session_state.get("menu_nezet", False):
        refresh_telemetry_ui(telemetry_placeholder)

    return valasz_szoveg
