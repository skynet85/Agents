# app.py
"""LLMOps Agilis Szimulátor – belépési pont, állapotgép és renderelés."""
from __future__ import annotations

import copy
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

import config
import project_doctor
import sandbox
import sprint_engine
from agents import (
    format_recent_history,
    generate_base_profile,
    get_agent_chain,
    get_lm_studio_models,
    refine_profile,
    update_project_memory,
)
from github_integration import push_to_github
from memory_manager import clear_memory_file, delete_run, load_all_runs, save_run
from sprint_engine import SprintAllapot
from telemetry_setup import init_opentelemetry
from workspace import VirtualWorkspace, ellenoriz, workspace_from_messages
from ui_components import SprintStatusManager, render_agent_configuration_ui
from util import (
    AgensFutasHiba,
    extract_wireframe_code,
    refresh_telemetry_ui,
    render_wireframe_ui,
    run_agent_with_telemetry,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

STICKY_CSS = """
<style>
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stMainBlockContainer"],
    .main .block-container,
    div[data-testid="stVerticalBlock"],
    div[data-testid="stVerticalBlockBorderWrapper"] {
        overflow: visible !important;
    }
    div[data-testid="stMainBlockContainer"] > div[data-testid="stVerticalBlock"] > div:has(#telemetry-anchor) {
        position: -webkit-sticky !important;
        position: sticky !important;
        top: 2.875rem !important;
        z-index: 99999 !important;
        background-color: var(--background-color) !important;
        opacity: 1 !important;
        margin-top: -1rem !important;
        padding-top: 1rem !important;
        padding-bottom: 12px !important;
        border-bottom: 1px solid var(--secondary-background-color) !important;
        box-shadow: 0px 10px 20px -10px rgba(0,0,0,0.3) !important;
    }
</style>
"""


# ---------------------------------------------------------------------------
# Állapotkezelés
# ---------------------------------------------------------------------------
def ures_telemetria() -> Dict[str, Any]:
    return {"osszes_ido": 0.0, "osszes_token": 0, "agensek": {}}


def init_session_state() -> None:
    if "dynamic_agents" not in st.session_state:
        st.session_state.dynamic_agents = copy.deepcopy(config.DEFAULT_AGENTS)

    defaults = {
        "menu_nezet": True,
        "run_id": None,
        "run_datum": None,
        "ertekelesek": {a["id"]: 0 for a in st.session_state.dynamic_agents},
        "ertekeles_aktiv": False,
        "projekt_memoria": config.URES_MEMORIA,
        "telemetria": ures_telemetria(),
        "uzenetek": [],
        "eredeti_feladat": "Nincs megadva.",
        "labor_folyamatban": False,
        "sprint_folyamatban": False,
        "agens_dolgozik": False,
        "sprint_allapot": SprintAllapot().to_dict(),
        "lepesenkenti_mod": False,
        "utolso_hiba": None,
        "munkaterulet": VirtualWorkspace.vazzal().to_dict(),
        "sandbox_aktiv": True,
        "utolso_build": None,
    }
    for key, val in defaults.items():
        st.session_state.setdefault(key, val)


# A kódot előállító ágensek – csak az ő válaszaik módosítják a fájlfát.
KOD_SZEREPEK = ["Informatikus", "IT", "Frontend", "FE", "Backend", "BE", "UX", "Designer"]


def get_workspace() -> VirtualWorkspace:
    return VirtualWorkspace.from_dict(st.session_state.munkaterulet)


def set_workspace(ws: VirtualWorkspace) -> None:
    st.session_state.munkaterulet = ws.to_dict()


def start_new_simulation() -> None:
    st.session_state.update(
        {
            "menu_nezet": False,
            "run_id": None,
            "run_datum": None,
            "projekt_memoria": config.URES_MEMORIA,
            "telemetria": ures_telemetria(),
            "uzenetek": [],
            "eredeti_feladat": "Nincs megadva.",
            "ertekelesek": {a["id"]: 0 for a in st.session_state.dynamic_agents},
            "ertekeles_aktiv": False,
            "sprint_folyamatban": False,
            "agens_dolgozik": False,
            "sprint_allapot": SprintAllapot().to_dict(),
            "utolso_hiba": None,
            "munkaterulet": VirtualWorkspace.vazzal().to_dict(),
        }
    )


def _mentes() -> None:
    """A jelenlegi állapot kiírása a JSON memóriába (hiba esetén figyelmeztet)."""
    if not st.session_state.run_id:
        return
    sikeres = save_run(
        st.session_state.run_id,
        st.session_state.run_datum,
        st.session_state.eredeti_feladat,
        st.session_state.projekt_memoria,
        st.session_state.uzenetek,
        st.session_state.telemetria,
        st.session_state.ertekelesek,
        st.session_state.munkaterulet,
    )
    if not sikeres:
        st.warning("⚠️ A futás mentése nem sikerült – ellenőrizd a lemez jogosultságokat!")


def _sprint_leallitas(uzenet: str) -> None:
    st.session_state.sprint_folyamatban = False
    st.session_state.agens_dolgozik = False
    st.session_state.utolso_hiba = uzenet


# ---------------------------------------------------------------------------
# Főmenü
# ---------------------------------------------------------------------------
def render_main_menu() -> None:
    st.title("📂 LLMOps Projekt Menedzser")
    st.markdown("Válassz egy korábbi szimulációt, vagy indíts egy teljesen újat!")

    if st.button("✨ Új Szimuláció Indítása", type="primary", use_container_width=True):
        start_new_simulation()
        st.rerun()

    st.divider()
    st.subheader("🕰️ Korábbi futások előzményei")

    runs = load_all_runs()
    if not runs:
        st.info("Még nem található mentett szimuláció az adatbázisban.")
        return

    for r in reversed(runs):
        run_id = r.get("run_id", "")
        feladat = str(r.get("feladat", "(nincs feladat)"))
        cim = f"📅 {r.get('datum', '?')} | 📝 {feladat[:80]}{'...' if len(feladat) > 80 else ''}"

        with st.expander(cim):
            ertekelesek = r.get("ertekelesek", {}) or {}
            if ertekelesek:
                cols = st.columns(min(len(ertekelesek), 8))
                for i, (agent, score) in enumerate(ertekelesek.items()):
                    try:
                        score_int = int(score)
                    except (TypeError, ValueError):
                        score_int = 0
                    cols[i % len(cols)].metric(
                        agent, f"{score_int} ⭐" if score_int > 0 else "Nincs értékelve"
                    )

            telemetria = r.get("telemetria", {}) or {}
            st.markdown(f"**Összes token:** {int(telemetria.get('osszes_token', 0) or 0):,}")

            c_load, c_del = st.columns([3, 1])
            if c_load.button("🚀 Eredmény Megtekintése / Folytatás", key=f"load_{run_id}"):
                uzenetek = r.get("uzenetek", []) or []
                # Régi futásoknál még nincs mentett fájlfa – a chat-logból építjük fel.
                mentett_ws = r.get("munkaterulet") or {}
                if not mentett_ws.get("files"):
                    mentett_ws = workspace_from_messages(uzenetek, KOD_SZEREPEK).to_dict()

                st.session_state.update(
                    {
                        "munkaterulet": mentett_ws,
                        "run_id": run_id,
                        "run_datum": r.get("datum", ""),
                        "projekt_memoria": r.get("memoria", config.URES_MEMORIA),
                        "uzenetek": r.get("uzenetek", []) or [],
                        "telemetria": telemetria or ures_telemetria(),
                        "ertekelesek": dict(ertekelesek),
                        "eredeti_feladat": feladat,
                        "menu_nezet": False,
                        "ertekeles_aktiv": False,
                        "sprint_folyamatban": False,
                        "agens_dolgozik": False,
                        "utolso_hiba": None,
                    }
                )
                st.rerun()

            if c_del.button("🗑️ Törlés", key=f"del_run_{run_id}"):
                delete_run(run_id)
                st.rerun()


# ---------------------------------------------------------------------------
# Labor (perszóna-generálás)
# ---------------------------------------------------------------------------
def run_labor(agent_configs: Dict[str, Any], finomitas_korok: int, placeholder: Any) -> None:
    with st.status("🧬 Viselkedéskutató labor dolgozik... (A felület lezárva!)", expanded=True) as status:
        try:
            for agens in st.session_state.dynamic_agents:
                ag_id = agens["id"]
                beallitas = agent_configs.get(ag_id)
                if not beallitas:
                    continue

                st.write(f"⏳ **{ag_id}** alapvázlatának generálása folyamatban...")
                chain_base = generate_base_profile(beallitas["modell"], beallitas["def"])
                profil = run_agent_with_telemetry("Viselkedéskutató Lab", chain_base, {}, placeholder)

                for i in range(finomitas_korok):
                    chain_refine = refine_profile(beallitas["modell"], profil, ag_id, i + 1)
                    profil = run_agent_with_telemetry(
                        "Viselkedéskutató Lab", chain_refine, {}, placeholder
                    )

                st.session_state[f"{ag_id}_persona"] = profil
                st.write(f"✓ {ag_id} profilja elkészült.")
            status.update(label="Minden profil készen áll! A felület feloldva.", state="complete")
        except AgensFutasHiba as exc:
            status.update(label="A labor megszakadt.", state="error")
            st.session_state.utolso_hiba = str(exc)
        finally:
            st.session_state.labor_folyamatban = False


# ---------------------------------------------------------------------------
# Sprint
# ---------------------------------------------------------------------------
def build_agent_queue(agent_configs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """A sprint ágens-sorrendje a jelenlegi konfigurációval."""
    sor = []
    for a in st.session_state.dynamic_agents:
        ag_id = a["id"]
        beallitas = agent_configs.get(ag_id)
        if not beallitas:
            continue
        sor.append(
            {
                "id": ag_id,
                "ikon": a["ikon"],
                "nev": a["nev"],
                "akcio": a["akcio"],
                "persona": st.session_state.get(f"{ag_id}_persona", a["leiras"]),
                "modell": beallitas["modell"],
                "szabaly": beallitas["szabaly"],
            }
        )
    return sor


def _futtat_agenst(agens: Dict[str, Any], allapot: SprintAllapot, placeholder: Any) -> Optional[str]:
    """Egy ágens futtatása és megjelenítése. Hiba esetén None."""
    recent_hist = format_recent_history(st.session_state.uzenetek)
    try:
        with st.chat_message("assistant", avatar=agens["ikon"]):
            with st.spinner(f"Gépel ({agens['modell']})..."):
                chain = get_agent_chain(
                    agens["modell"], agens["nev"], agens["persona"], agens["szabaly"]
                )
                valasz = run_agent_with_telemetry(
                    agens["id"],
                    chain,
                    {
                        "projekt_memoria": st.session_state.projekt_memoria,
                        "recent_history": recent_hist,
                        "kerdes": allapot.elozo_kimenet,
                        "eredeti_igeny": st.session_state.eredeti_feladat,
                        "fajlfa": get_workspace().fajlfa(),
                    },
                    placeholder,
                )
                st.markdown(f"**{agens['nev']}**\n\n{valasz}")
                if "UX" in agens["nev"] or agens["id"] == "UX":
                    html_kod = extract_wireframe_code(valasz)
                    if html_kod:
                        render_wireframe_ui(html_kod)
        return valasz
    except AgensFutasHiba as exc:
        _sprint_leallitas(str(exc))
        return None


def futtat_buildet(files: Dict[str, str]) -> sandbox.SandboxEredmeny:
    """Valódi fordítás a fájlfán, UI visszajelzéssel."""
    with st.spinner(f"🔨 Valódi build futtatása ({sandbox.motor_leirasa()})..."):
        eredmeny = sandbox.build(files)

    st.session_state.utolso_build = {
        "motor": eredmeny.motor,
        "sikeres": eredmeny.sikeres,
        "futott": eredmeny.futott,
        "reszek": [r.osszefoglalo for r in eredmeny.reszek],
        "hibak": eredmeny.hibak,
    }

    if not eredmeny.futott:
        st.info(f"🔨 Build kihagyva — {sandbox.motor_leirasa()}.")
    elif eredmeny.sikeres:
        st.success("🔨 " + " · ".join(r.osszefoglalo for r in eredmeny.reszek))
    else:
        with st.expander(
            "🔨 A build ELBUKOTT — " + " · ".join(r.osszefoglalo for r in eredmeny.reszek),
            expanded=True,
        ):
            for h in eredmeny.hibak[:15]:
                st.markdown(f"- `{h}`")
            for r in eredmeny.reszek:
                if not r.kihagyva and not r.sikeres and r.nyers_kimenet:
                    with st.expander(f"Nyers kimenet ({r.cel})", expanded=False):
                        st.code(r.nyers_kimenet, language="text")
    return eredmeny


def run_next_agent(agens: Dict[str, Any], allapot: SprintAllapot, placeholder: Any) -> None:
    """Egy sprint-lépés: ágens futtatása + védőkorlát + állapotátmenet."""
    valasz = _futtat_agenst(agens, allapot, placeholder)
    if valasz is None:
        return

    st.session_state.uzenetek.append(
        {
            "szerep": "assistant",
            "szerep_nev": agens["nev"],
            "avatar": agens["ikon"],
            "szoveg": valasz,
        }
    )
    allapot.valaszok[agens["id"]] = valasz

    # --- A válasz beolvasztása a projekt fájlfájába ---
    ws = get_workspace()
    valtozasok = [
        v
        for v in ws.alkalmaz(
            {"szerep": "assistant", "szerep_nev": agens["nev"], "szoveg": valasz}, KOD_SZEREPEK
        )
        if v.tipus != "valtozatlan"
    ]
    set_workspace(ws)

    if valtozasok:
        with st.expander(f"📁 Fájlváltozások ({len(valtozasok)})", expanded=False):
            for v in valtozasok:
                st.markdown(f"`{v}`")

    # --- VÉDŐKORLÁT: a PROJEKT EGÉSZE megfelel-e? ---
    # A korábbi verzió csak az aktuális válasz kódblokkjait nézte, ezért az IT
    # kénytelen volt minden körben újragenerálni mindent. Most a fájlfa számít.
    if agens["id"] == "IT":
        hibak = sprint_engine.validate_it_projekt(ws.files)
        hibak += ellenoriz(ws)

        # --- IGAZSÁGFORRÁS: valódi fordítás a generált kódon ---
        forditoi_kimenet = ""
        if not hibak and st.session_state.get("sandbox_aktiv", True):
            # A build-képességi javításokat a fordítás ELŐTT alkalmazzuk, hogy a
            # sandbox ugyanazt a projektet fordítsa, ami a Jenkinsbe kerül.
            javitott_fajlok, _ = project_doctor.javit(ws.files)
            build_eredmeny = futtat_buildet(javitott_fajlok)
            if build_eredmeny.futott and not build_eredmeny.sikeres:
                hibak = build_eredmeny.hibak or ["A fordítás ismeretlen hibával elbukott"]
                forditoi_kimenet = build_eredmeny.prompt_reszlet()

        if sprint_engine.kell_ujraprobalni(allapot, agens["id"], hibak):
            probalkozas = allapot.ujraprobalkozasok.get(agens["id"], 0) + 1
            allapot.ujraprobalkozasok[agens["id"]] = probalkozas
            hatra = config.MAX_AGENS_UJRAPROBALKOZAS - probalkozas

            cimke = "fordítási hiba" if forditoi_kimenet else "a válasz hibás"
            st.session_state.uzenetek.append(
                {
                    "szerep": "assistant",
                    "szerep_nev": "Rendszer (Védőkorlát)",
                    "avatar": "🛡️",
                    "szoveg": (
                        f"⚠️ **[Rendszer Védelem]** ({probalkozas}/"
                        f"{config.MAX_AGENS_UJRAPROBALKOZAS}. próbálkozás): {cimke}. "
                        f"Okok: {', '.join(hibak[:6])}"
                        f"{' …' if len(hibak) > 6 else ''}. Újra futtatjuk ezt a lépést!"
                    ),
                }
            )
            allapot.elozo_kimenet = sprint_engine.javito_prompt(
                valasz, hibak, hatra, forditoi_kimenet
            )
            # Az agens_idx szándékosan NEM nő: ugyanaz az ágens próbálkozik újra.
            st.session_state.sprint_allapot = allapot.to_dict()
            _mentes()
            return

        if hibak:
            # Kimerültek a próbálkozások – továbbengedjük, de jelezzük.
            st.session_state.uzenetek.append(
                {
                    "szerep": "assistant",
                    "szerep_nev": "Rendszer (Védőkorlát)",
                    "avatar": "🛡️",
                    "szoveg": (
                        f"⛔ Az Informatikus {config.MAX_AGENS_UJRAPROBALKOZAS} próbálkozás "
                        f"után sem teljesítette a követelményeket ({', '.join(hibak)}). "
                        "A sprint továbbhalad, a QA feladata a hiány jelzése."
                    ),
                }
            )

    # --- NORMÁL TOVÁBBLÉPÉS ---
    allapot.elozo_kimenet = valasz
    allapot.agens_idx += 1
    st.session_state.sprint_allapot = allapot.to_dict()
    _mentes()


def run_admin_konszolidacio(
    allapot: SprintAllapot,
    agent_configs: Dict[str, Any],
    status_manager: SprintStatusManager,
    korok_szama: int,
    minimum_korok: int,
    placeholder: Any,
) -> None:
    """Kör végi memóriafrissítés és a sprint folytatásáról szóló döntés."""
    with st.spinner("Memória frissítése..."):
        beszelgetes = "\n".join(f"{k}: {v}" for k, v in allapot.valaszok.items())
        try:
            chain_mem = update_project_memory(
                agent_configs["Admin"], beszelgetes, st.session_state.projekt_memoria
            )
            admin_valasz = run_agent_with_telemetry("Rendszer (Admin)", chain_mem, {}, placeholder)
        except AgensFutasHiba as exc:
            _sprint_leallitas(str(exc))
            status_manager.finish_error(str(exc))
            return

        prefix = (
            ""
            if st.session_state.projekt_memoria == config.URES_MEMORIA
            else f"{st.session_state.projekt_memoria}\n\n---\n"
        )
        st.session_state.projekt_memoria = f"{prefix}### {allapot.kor + 1}. Iteráció:\n{admin_valasz}"

        utolso_valasz = list(allapot.valaszok.values())[-1] if allapot.valaszok else ""

        if sprint_engine.lezarast_kert(utolso_valasz):
            if allapot.kor < minimum_korok - 1:
                status_manager.show_enforced_rule_warning(allapot.kor)
                allapot.kovetkezo_kor(
                    utolso_valasz
                    + "\n\nRENDSZER ÜZENET A PO-NAK: Felülbírálat! Követelj mélyebb tesztelést!"
                )
            else:
                st.session_state.sprint_folyamatban = False
                st.session_state.ertekeles_aktiv = True
                status_manager.finish_success()
        else:
            allapot.kovetkezo_kor(utolso_valasz)
            if allapot.kor >= korok_szama:
                st.session_state.sprint_folyamatban = False
                st.session_state.ertekeles_aktiv = True
                status_manager.finish_timebox()

        st.session_state.sprint_allapot = allapot.to_dict()
        _mentes()

    st.session_state.agens_dolgozik = False


def render_sprint(
    agent_configs: Dict[str, Any], korok_szama: int, minimum_korok: int, placeholder: Any
) -> None:
    status_manager = SprintStatusManager(korok_szama, minimum_korok)
    allapot = SprintAllapot.from_dict(st.session_state.sprint_allapot)
    status_manager.update_round(allapot.kor)

    sor = build_agent_queue(agent_configs)
    if not sor:
        _sprint_leallitas("Nincs egyetlen konfigurált sprint-ágens sem.")
        status_manager.finish_error("Nincs egyetlen konfigurált sprint-ágens sem.")
        return

    # Ha időközben töröltek egy ágenst, az index kilóghat a listából.
    if allapot.agens_idx > len(sor):
        allapot.agens_idx = len(sor)
        st.session_state.sprint_allapot = allapot.to_dict()

    # --- KÖR VÉGE: admin konszolidáció ---
    if allapot.agens_idx >= len(sor):
        st.info("🔄 **Kör vége.** Az Admin rendszer rendszerezi a memóriát...")
        if st.session_state.agens_dolgozik:
            run_admin_konszolidacio(
                allapot, agent_configs, status_manager, korok_szama, minimum_korok, placeholder
            )
            st.rerun()
        elif st.session_state.lepesenkenti_mod:
            st.button(
                "▶️ Admin mentés indítása",
                type="primary",
                on_click=lambda: st.session_state.update(agens_dolgozik=True),
            )
        else:
            st.session_state.agens_dolgozik = True
            st.rerun()
        return

    # --- SORON KÖVETKEZŐ ÁGENS ---
    agens = sor[allapot.agens_idx]
    status_manager.set_active_agent(agens["ikon"], agens["nev"], agens["akcio"])

    if st.session_state.lepesenkenti_mod and not st.session_state.agens_dolgozik:
        st.button(
            f"▶️ Tovább: {agens['nev']} indítása",
            type="primary",
            on_click=lambda: st.session_state.update(agens_dolgozik=True),
        )
        return

    st.session_state.agens_dolgozik = True
    run_next_agent(agens, allapot, placeholder)
    st.session_state.agens_dolgozik = False

    if st.session_state.sprint_folyamatban:
        st.rerun()
    else:
        status_manager.finish_error(st.session_state.utolso_hiba or "A sprint megszakadt.")


# ---------------------------------------------------------------------------
# Értékelés és export
# ---------------------------------------------------------------------------
def _push_engedelyezett(kihagyas: bool) -> bool:
    """Feltöltés előtti kapu: csak lefordítható projekt mehet fel a repóba.

    A #26-os Jenkins build azért bukott el, mert egy Java típushiba
    (`Object cannot be converted to Map<String,Object>`) csak a CI-ben derült ki.
    Ha van build motor, itt előbb lefordítjuk — így a hiba nem jut el a repóba.
    """
    if kihagyas:
        return True

    ws = get_workspace()
    if not ws.files:
        st.warning("A munkaterület üres – nincs mit feltölteni.")
        return False

    javitott, _ = project_doctor.javit(ws.files)
    eredmeny = futtat_buildet(javitott)

    if not eredmeny.futott:
        return True  # nincs motor: nem tudunk mit ellenőrizni
    if eredmeny.sikeres:
        return True

    st.error(
        "⛔ A feltöltés leállítva: a projekt NEM fordul le. "
        "A Jenkins ugyanezen a hibán bukna el.\n\n"
        "Futtass még egy sprint-iterációt a javításhoz, vagy pipáld be a "
        "„Feltöltés a fordítás sikere nélkül is” jelölőt."
    )
    return False


def render_projekt_fajlfa() -> None:
    """A projekt aktuális fájlfája és konzisztencia-állapota."""
    ws = get_workspace()
    if not ws.files:
        return

    osszes = ws.osszefoglalo()
    hibak = ellenoriz(ws)
    cim = f"📁 Projekt fájlfa ({osszes['osszes']} fájl)"
    if hibak:
        cim += f" — ⚠️ {len(hibak)} konzisztencia-probléma"

    with st.expander(cim, expanded=False):
        c1, c2, c3 = st.columns(3)
        c1.metric("Frontend", osszes["frontend"])
        c2.metric("Backend", osszes["backend"])
        c3.metric("Adatbázis", osszes["database"])

        if hibak:
            st.warning("A fordítás előtti statikus ellenőrzés talált hibákat:")
            for h in hibak:
                st.markdown(f"- {h}")
        else:
            st.success("A statikus konzisztencia-ellenőrzés nem talált hibát.")

        utolso = st.session_state.get("utolso_build")
        if utolso:
            if not utolso["futott"]:
                st.info("🔨 Valódi build: nem futott.")
            elif utolso["sikeres"]:
                st.success("🔨 Utolsó build: " + " · ".join(utolso["reszek"]))
            else:
                st.error("🔨 Utolsó build: " + " · ".join(utolso["reszek"]))
                for h in utolso["hibak"][:10]:
                    st.markdown(f"- `{h}`")

        diagnozisok = project_doctor.diagnosztizal(ws.files)
        if diagnozisok:
            st.markdown("**🩺 Build-képességi diagnózis** (Jenkins szemszögéből):")
            for d in diagnozisok:
                st.markdown(f"- {d}")
            _, javitasok = project_doctor.javit(ws.files)
            if javitasok:
                st.caption(
                    "A feltöltéskor ezek automatikusan javulnak: "
                    + "; ".join(javitasok[:4])
                    + (" …" if len(javitasok) > 4 else "")
                )

        c_build, _ = st.columns([1, 2])
        if c_build.button("🔨 Build futtatása most", disabled=not ws.files):
            javitott, _ = project_doctor.javit(ws.files)
            futtat_buildet(javitott)
            st.rerun()

        valasztott = st.selectbox("Fájl megtekintése:", options=[""] + sorted(ws.files))
        if valasztott:
            st.code(ws.get(valasztott), language=valasztott.rsplit(".", 1)[-1])


def render_ertekeles_es_export() -> None:
    st.markdown("### ⭐️ Sprint Áttekintés, Értékelés és Export")

    with st.form("ertekeles_form"):
        agensek = st.session_state.dynamic_agents
        cols = st.columns(min(len(agensek), 8)) if agensek else [st]
        uj_ertekelesek: Dict[str, int] = {}
        for i, agens in enumerate(agensek):
            ag_id = agens["id"]
            nyers = st.session_state.ertekelesek.get(ag_id, 0)
            try:
                alap = int(nyers)
            except (TypeError, ValueError):
                alap = 0
            alap = alap if 1 <= alap <= 5 else 3
            with cols[i % len(cols)]:
                uj_ertekelesek[ag_id] = st.slider(ag_id, 1, 5, alap, key=f"ert_{ag_id}")

        if st.form_submit_button("💾 Értékelések Mentése"):
            st.session_state.ertekelesek = uj_ertekelesek
            _mentes()
            st.success("Értékelések sikeresen mentve!")

    st.divider()
    with st.expander("🐙 Forráskód és README publikálása GitHubra", expanded=True):
        st.markdown("Töltsd fel a legenerált kódokat, drótvázakat és a README.md-t a repódba!")
        gh_repo = st.text_input("Repository (Formátum: felhasznalo/repo):", value="skynet85/AgileSim")
        gh_token = st.text_input("GitHub Personal Access Token (PAT):", type="password")

        motor = sandbox.elerheto_motor()
        if motor == "kihagyva":
            st.warning(
                "⚠️ Nincs elérhető build motor (Docker / npm / mvn), ezért a feltöltés "
                "előtti fordítás kimarad. A Jenkins ilyenkor fordítási hibán is elbukhat."
            )
            kihagyas = True
        else:
            kihagyas = st.checkbox(
                "Feltöltés a fordítás sikere nélkül is",
                help="Alapból csak lefordítható projektet engedünk fel a repóba.",
            )

        if st.button("🚀 Push GitHub-ra", type="primary"):
            if not gh_token:
                st.warning("Kérlek, add meg a GitHub Personal Access Tokent!")
            elif "/" not in gh_repo:
                st.warning("A repository formátuma: felhasznalo/repo")
            elif not _push_engedelyezett(kihagyas):
                pass  # a `_push_engedelyezett` már kiírta, mi a baj
            else:
                with st.spinner("Fájlok kinyerése és feltöltése a GitHubra..."):
                    sikeres, uzenet = push_to_github(
                        gh_token,
                        gh_repo.strip(),
                        st.session_state.uzenetek,
                        st.session_state.projekt_memoria,
                        st.session_state.eredeti_feladat,
                        munkateruleti_fajlok=get_workspace().files or None,
                    )
                (st.success if sikeres else st.error)(uzenet)

    st.divider()
    if st.button("⬅️ Vissza a Főmenübe és Új Sprint"):
        st.session_state.menu_nezet = True
        st.session_state.ertekeles_aktiv = False
        st.rerun()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def render_sidebar(rendszer_zarolva: bool) -> Tuple[Dict[str, Any], int, int, int]:
    st.sidebar.title("⚙️ Vezérlőpult")
    if st.sidebar.button("⬅️ Vissza a Főmenübe", disabled=rendszer_zarolva):
        st.session_state.menu_nezet = True
        st.rerun()

    st.sidebar.divider()
    st.session_state.lepesenkenti_mod = st.sidebar.toggle(
        "⏸️ Léptetéses mód", value=st.session_state.lepesenkenti_mod
    )

    motor = sandbox.elerheto_motor()
    st.session_state.sandbox_aktiv = st.sidebar.toggle(
        "🔨 Valódi build (igazságforrás)",
        value=st.session_state.sandbox_aktiv and motor != "kihagyva",
        disabled=(motor == "kihagyva") or rendszer_zarolva,
        help=(
            "Az IT ágens kódját ténylegesen lefordítja, és a fordítói hibát adja "
            "vissza javításra. Lassítja a sprintet, de ez az egyetlen valódi "
            "minőségi visszajelzés."
        ),
    )
    st.sidebar.caption(f"Build motor: {sandbox.motor_leirasa()}")
    if motor == "kihagyva":
        st.sidebar.caption("💡 Telepíts Dockert vagy npm/mvn-t a fordítási ellenőrzéshez.")

    st.sidebar.divider()

    elerheto_modellek = get_lm_studio_models()
    if not elerheto_modellek:
        st.sidebar.warning(
            f"Nem érhető el modell a(z) {config.API_BASE_URL} címen. "
            "Fut az LM Studio szerver?"
        )
        elerheto_modellek = ["local-model"]

    agent_configs = render_agent_configuration_ui(elerheto_modellek, rendszer_zarolva)

    st.sidebar.divider()
    finomitas_korok = st.sidebar.slider("Finomítási körök (Labor):", 1, 5, 2, disabled=rendszer_zarolva)
    vegtelen_mod = st.sidebar.toggle("Végtelen Sprint mód", value=True, disabled=rendszer_zarolva)
    korok_szama = (
        config.VEGTELEN_MOD_KOROK
        if vegtelen_mod
        else st.sidebar.slider("Maximum vitakörök:", 1, 15, 5, disabled=rendszer_zarolva)
    )
    minimum_korok = st.sidebar.slider("Min. KÖTELEZŐ iteráció:", 1, 5, 3, disabled=rendszer_zarolva)
    minimum_korok = min(minimum_korok, korok_szama)

    # Az ágensek promptjai a session_state-ben ragadnak (deepcopy + widget-kulcsok),
    # ezért a config.py frissítése önmagában NEM látszik meg a következő sprinten.
    # Ez a gomb újratölti őket – a projekt memória érintetlenül marad.
    if st.sidebar.button(
        "♻️ Ágens-szabályok újratöltése",
        disabled=rendszer_zarolva,
        help="Betölti a config.py aktuális ágens-promptjait. A mentett futások megmaradnak.",
    ):
        st.session_state.dynamic_agents = copy.deepcopy(config.DEFAULT_AGENTS)
        for kulcs in [k for k in st.session_state if k.startswith(("rule_", "def_"))]:
            del st.session_state[kulcs]
        st.success("Az ágens-szabályok frissítve a config.py-ból.")
        st.rerun()

    if st.sidebar.button("🗑️ Teljes Rendszer Reset", disabled=rendszer_zarolva):
        clear_memory_file()
        st.session_state.clear()
        st.rerun()

    if st.sidebar.button("🚀 Labor indítása (Profilok Építése)", disabled=rendszer_zarolva):
        st.session_state.labor_folyamatban = True
        st.session_state.utolso_hiba = None
        st.rerun()

    return agent_configs, finomitas_korok, korok_szama, minimum_korok


# ---------------------------------------------------------------------------
# Belépési pont
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Lokális AI Szimulátor", page_icon="🧠", layout="wide")

    try:
        init_opentelemetry()
    except Exception as exc:  # noqa: BLE001 – a telemetria sosem törheti el az appot
        logger.warning("Az OpenTelemetry inicializálása sikertelen: %s", exc)

    init_session_state()

    if st.session_state.menu_nezet:
        render_main_menu()
        return

    rendszer_zarolva = st.session_state.labor_folyamatban or st.session_state.sprint_folyamatban
    modell_dolgozik_zar = (
        st.session_state.labor_folyamatban
        or st.session_state.agens_dolgozik
        or (st.session_state.sprint_folyamatban and not st.session_state.lepesenkenti_mod)
    )

    agent_configs, finomitas_korok, korok_szama, minimum_korok = render_sidebar(rendszer_zarolva)

    st.title("🧠 LLMOps Agilis Szimulátor")
    st.markdown(STICKY_CSS, unsafe_allow_html=True)

    with st.container():
        st.markdown('<div id="telemetry-anchor"></div>', unsafe_allow_html=True)
        c_title, c_toggle = st.columns([3, 1])
        c_title.markdown("### 📊 Valós idejű LLMOps Telemetria")
        with c_toggle:
            st.toggle("🔍 Részletes nézet", value=False, key="telemetry_toggle", disabled=modell_dolgozik_zar)
        telemetry_placeholder = st.empty()

    refresh_telemetry_ui(telemetry_placeholder)

    if st.session_state.utolso_hiba:
        st.error(f"❌ {st.session_state.utolso_hiba}")
        if st.button("Hibaüzenet elrejtése"):
            st.session_state.utolso_hiba = None
            st.rerun()

    if st.session_state.labor_folyamatban:
        run_labor(agent_configs, finomitas_korok, telemetry_placeholder)
        st.rerun()

    elso_agens = st.session_state.dynamic_agents[0]["id"] if st.session_state.dynamic_agents else None
    labor_kesz = bool(elso_agens) and f"{elso_agens}_persona" in st.session_state
    futas_betoltve = st.session_state.run_id is not None

    if not labor_kesz and not futas_betoltve:
        st.info(
            "👈 Állítsd be a modelleket az oldalsávon, majd kattints a "
            "**🚀 Labor indítása** gombra a karakterek felépítéséhez!"
        )
        return

    with st.expander("👁️ Eredmény: A Viselkedéskutató által finomított mélyprofilok", expanded=False):
        cols = st.columns(2)
        for i, agens in enumerate(st.session_state.dynamic_agents):
            ag_id = agens["id"]
            persona = st.session_state.get(
                f"{ag_id}_persona",
                "*(A labor profilgenerálás átugorva – korábbi futás betöltve)*\n\n"
                f"Alapértelmezett személyiség: **{agens['leiras']}**",
            )
            cols[i % 2].markdown(f"**{agens['ikon']} {agens['nev']} ({ag_id})**\n{persona}\n\n---")

    with st.expander("📂 Aktuális Projekt Memória"):
        st.info(st.session_state.projekt_memoria)

    render_projekt_fajlfa()

    for uzenet in st.session_state.uzenetek:
        with st.chat_message(uzenet.get("szerep", "assistant"), avatar=uzenet.get("avatar")):
            st.markdown(f"**{uzenet.get('szerep_nev', '')}**\n\n{uzenet.get('szoveg', '')}")
            if uzenet.get("szerep") == "assistant" and "UX" in uzenet.get("szerep_nev", ""):
                html_kod = extract_wireframe_code(uzenet.get("szoveg", ""))
                if html_kod:
                    # Előzmény-renderelésnél nem írjuk felül a legutóbbi drótvázat.
                    render_wireframe_ui(html_kod, mentes=False)

    def submit_sprint() -> None:
        bemenet = (st.session_state.uzenet_bemenet or "").strip()
        if not bemenet:
            return
        st.session_state.sprint_folyamatban = True
        st.session_state.utolso_hiba = None
        st.session_state.eredeti_feladat = bemenet
        st.session_state.uzenetek.append(
            {"szerep": "user", "szerep_nev": "Ügyfél (Te)", "avatar": "👤", "szoveg": bemenet}
        )
        st.session_state.sprint_allapot = SprintAllapot(elozo_kimenet=bemenet).to_dict()
        if not st.session_state.run_id:
            most = datetime.now()
            st.session_state.run_id = most.strftime("%Y%m%d_%H%M%S")
            st.session_state.run_datum = most.strftime("%Y-%m-%d %H:%M:%S")

    st.chat_input(
        "Írd be a projekt ötletet...",
        key="uzenet_bemenet",
        on_submit=submit_sprint,
        disabled=rendszer_zarolva,
    )

    if st.session_state.sprint_folyamatban:
        render_sprint(agent_configs, korok_szama, minimum_korok, telemetry_placeholder)

    sprint_lezarva = st.session_state.ertekeles_aktiv or (
        st.session_state.run_id is not None
        and not st.session_state.sprint_folyamatban
        and len(st.session_state.uzenetek) > 0
    )
    if sprint_lezarva:
        render_ertekeles_es_export()


if __name__ == "__main__":
    main()
