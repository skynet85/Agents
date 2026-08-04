# agents.py
"""Tiszta ágens-/LLM-logika.

Ez a modul szándékosan NEM importál Streamlitet: csak LangChain láncokat épít,
így önállóan tesztelhető és újrafelhasználható.

FONTOS TERVEZÉSI DÖNTÉS
-----------------------
A perszóna-profilokat és a szabályokat NEM f-stringgel fűzzük a sablonba,
hanem `PromptTemplate.partial_variables`-ként adjuk át. Így a modell által
generált profilokban (vagy a felhasználó által beírt szabályokban) előforduló
`{` és `}` karakterek nem törik el a prompt formázását
(`KeyError: '...'` / `Single '}' encountered`).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import requests
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

import config
import scaffold

logger = logging.getLogger(__name__)

# Hány korábbi üzenetet adunk át kontextusként.
HISTORY_ABLAK = 6


def get_lm_studio_models() -> List[str]:
    """Lekérdezi az LM Studio-ban betöltött modellek listáját.

    Hálózati hiba esetén üres listával tér vissza (a hívó dönt a fallbackről).
    """
    try:
        response = requests.get(f"{config.API_BASE_URL}/models", timeout=5)
        response.raise_for_status()
        return [m["id"] for m in response.json().get("data", []) if "id" in m]
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("Nem sikerült lekérni a modelleket: %s", exc)
        return []


def _create_llm_client(model_name: str, temperature: float = 0.7) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=config.API_BASE_URL,
        api_key=config.API_KEY,
        model=model_name,
        temperature=temperature,
        timeout=config.LLM_TIMEOUT_SECONDS,
    )


def format_recent_history(messages: List[Dict[str, str]]) -> str:
    """Az utolsó néhány üzenet szöveges összefűzése a prompt kontextusához."""
    if not messages:
        return "(Még nincs előzmény.)"
    return "".join(
        f"{msg.get('szerep_nev', '?')}: {msg.get('szoveg', '')}\n"
        for msg in messages[-HISTORY_ABLAK:]
    )


def generate_base_profile(model_name: str, role_description: str) -> Any:
    """Alapprofil-generáló lánc. A szerepleírás partial value-ként megy be."""
    llm = _create_llm_client(model_name, temperature=0.7)
    prompt = PromptTemplate(
        input_variables=[],
        partial_variables={"role": role_description or "(nincs megadva)"},
        template="Készíts 3 mondatos leírást a karakterről: '{role}'. Csak a leírást írd.",
    )
    return prompt | llm


def refine_profile(model_name: str, current_profile: str, role_name: str, round_num: int) -> Any:
    """Profilfinomító lánc.

    A `current_profile` LLM által generált szöveg, ezért partial value-ként
    kerül be – így a benne lévő kapcsos zárójelek nem okoznak formázási hibát.
    """
    llm = _create_llm_client(model_name, temperature=0.8)
    prompt = PromptTemplate(
        input_variables=[],
        partial_variables={
            "role_name": role_name,
            "current_profile": current_profile or "(üres)",
            "round_num": str(round_num),
        },
        template=(
            "Te egy szociológus vagy. Finomítsd az alábbi profilt a {round_num}. "
            "iterációban. Szerep: {role_name}. Jelenlegi: {current_profile}. "
            "Adj hozzá kognitív torzításokat és rejtett motivációkat. "
            "Csak a profilt írd le!"
        ),
    )
    return prompt | llm


def update_project_memory(model_name: str, uj_uzenetek: str, jelenlegi_memoria: str) -> Any:
    """Az adminisztrátor lánc, ami a projekt dokumentációját konszolidálja.

    A két szöveg partial value-ként megy be (kódrészleteket is tartalmazhatnak).
    """
    llm = _create_llm_client(model_name, temperature=0.1)
    prompt = PromptTemplate(
        input_variables=[],
        partial_variables={
            "jelenlegi_memoria": jelenlegi_memoria or config.URES_MEMORIA,
            "uj_uzenetek": uj_uzenetek or "(nincs új esemény)",
        },
        template=(
            "Te egy precíz szoftverfejlesztési adminisztrátor vagy.\n"
            "Frissítsd a projekt dokumentációját az új események alapján. Csak a "
            "tényeket, technikai döntéseket, teszteredményeket és a kódot őrizd "
            "meg! A vitákat hagyd ki.\n\n"
            "JELENLEGI DOKUMENTÁCIÓ:\n{jelenlegi_memoria}\n\n"
            "ÚJ ESEMÉNYEK:\n{uj_uzenetek}\n\n"
            "Írd meg a frissített dokumentációt:"
        ),
    )
    return prompt | llm


AGENS_SABLON = """Te az alábbi mélypszichológiai profillal rendelkezel. Éld bele magad a szerepbe:
---
{persona_profile}
---
Feladatod: {role_name}.
Eredeti ügyféligény: '{eredeti_igeny}'
SZABÁLY: {szabaly}
[A PROJEKT VÁZA — ZÁROLT]
{vaz_leiras}
[A PROJEKT JELENLEGI FÁJLJAI]
{fajlfa}
FONTOS: ezek a fájlok MÁR LÉTEZNEK. Ne generáld újra a változatlan fájlokat!
Csak azt a fájlt írd ki kódblokkban, amit ténylegesen létrehozol vagy módosítasz,
és mindig a MEGLÉVŐ útvonalat használd, ha egy fájlt frissítesz.
Fájl törléséhez írj külön sorba: DELETE: <útvonal>
Fájl áthelyezéséhez: MOVE: <régi útvonal> -> <új útvonal>
[DOKUMENTÁCIÓ]
{projekt_memoria}
[ELŐZMÉNYEK]
{recent_history}
Legutóbbi üzenet: {kerdes}
A te válaszod:"""


def get_agent_chain(model_name: str, role_name: str, persona_profile: str, rule: str) -> Any:
    """Egy sprint-ágens láncát építi fel.

    A `persona_profile` és a `rule` partial value-ként megy be, így tetszőleges
    karaktereket (pl. JSON/Groovy kódrészletet) tartalmazhatnak.
    """
    llm = _create_llm_client(model_name, temperature=0.7)
    prompt = PromptTemplate(
        input_variables=["projekt_memoria", "recent_history", "kerdes", "eredeti_igeny", "fajlfa"],
        partial_variables={
            "persona_profile": persona_profile or "(Nincs generált profil.)",
            "role_name": role_name,
            "szabaly": rule or "(Nincs külön szabály.)",
            "vaz_leiras": scaffold.vaz_leiras(),
        },
        template=AGENS_SABLON,
    )
    return prompt | llm
