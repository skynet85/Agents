# app.py
import time
import re
import streamlit as st
import streamlit.components.v1 as components
import config
from memory_manager import load_memory, save_memory, clear_memory_file
from ui_components import SprintStatusManager, render_telemetry_dashboard
from agents import (
    get_lm_studio_models, 
    generate_base_profile, 
    refine_profile, 
    get_agent_chain, 
    update_project_memory, 
    format_recent_history
)

# --- INICIALIZÁLÁS ÉS ÁLLAPOTGÉP (STATE MACHINE) ---
st.set_page_config(page_title="Lokális AI Szimulátor", page_icon="🧠", layout="wide")

if "projekt_memoria" not in st.session_state:
    memoria, telemetria = load_memory()
    st.session_state.projekt_memoria = memoria
    st.session_state.telemetria = telemetria
if "uzenetek" not in st.session_state:
    st.session_state.uzenetek = []
if "eredeti_feladat" not in st.session_state:
    st.session_state.eredeti_feladat = "Nincs megadva."

# ÚJ RÉSZ: Mindkét fő folyamat kap egy állapotjelzőt
if "labor_folyamatban" not in st.session_state:
    st.session_state.labor_folyamatban = False
if "sprint_folyamatban" not in st.session_state:
    st.session_state.sprint_folyamatban = False
if "aktualis_feladat" not in st.session_state:
    st.session_state.aktualis_feladat = ""

# KÖZÖS ZÁR: Ha bármelyik True, a teljes felület inaktív lesz!
felulet_zarolva = st.session_state.labor_folyamatban or st.session_state.sprint_folyamatban

# --- SEGÉDFÜGGVÉNYEK ---
def extract_and_render_wireframe(text):
    """Kikeresi a ```html ``` blokkot a UX válaszából, és kirajzolja."""
    match = re.search(r'```html\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
    if match:
        html_code = match.group(1)
        with st.expander("🎨 UX/UI Drótváz Megtekintése", expanded=True):
            st.info("A UX Designer által generált élő drótváz:")
            components.html(html_code, height=500, scrolling=True)
        with open("utolso_drotvaz.html", "w", encoding="utf-8") as f:
            f.write(html_code)

def run_agent_with_telemetry(agent_name, chain, invoke_args):
    """Mérőműszerrel ellátott ágens futtatás."""
    start_time = time.time()
    response = chain.invoke(invoke_args)
    elapsed_time = time.time() - start_time
    valasz_szoveg = response.content
    
    tokenek = 0
    if hasattr(response, 'response_metadata'):
        tokenek = response.response_metadata.get('token_usage', {}).get('total_tokens', 0)

    if 'agensek' not in st.session_state.telemetria:
        st.session_state.telemetria['agensek'] = {}
    if agent_name not in st.session_state.telemetria['agensek']:
        st.session_state.telemetria['agensek'][agent_name] = {'ido': 0.0, 'token': 0}
        
    st.session_state.telemetria['agensek'][agent_name]['ido'] += elapsed_time
    st.session_state.telemetria['agensek'][agent_name]['token'] += tokenek
    st.session_state.telemetria['osszes_ido'] = st.session_state.telemetria.get('osszes_ido', 0.0) + elapsed_time
    st.session_state.telemetria['osszes_token'] = st.session_state.telemetria.get('osszes_token', 0) + tokenek

    refresh_telemetry_ui()
    return valasz_szoveg

# --- FŐKÉPERNYŐ ÉS ÉLŐ TELEMETRIA KONTÉNER ---
st.title("🧠 LLMOps Agilis Szimulátor (6 Ágens)")

st.markdown(
    """
    <style>
        .floating-telemetry {
            position: sticky;
            top: 2.875rem;
            z-index: 999;
            background-color: white;
            padding-bottom: 10px;
            border-bottom: 1px solid #e5e7eb;
            margin-bottom: 20px;
        }
        @media (prefers-color-scheme: dark) {
            .floating-telemetry {
                background-color: #0e1117;
                border-bottom: 1px solid #374151;
            }
        }
    </style>
    """,
    unsafe_allow_html=True
)

telemetry_container = st.container()
st.markdown('<div class="floating-telemetry"></div>', unsafe_allow_html=True) 

with telemetry_container:
    c_title, c_toggle = st.columns([3, 1])
    with c_title:
        st.markdown("### 📊 Valós idejű LLMOps Telemetria")
    with c_toggle:
        # LETILTJUK a kapcsolót, ha a felület zárolva van!
        st.toggle(
            "🔍 Részletes nézet", 
            value=False, 
            key="telemetry_toggle", 
            disabled=felulet_zarolva
        )
    telemetry_placeholder = st.empty()

def refresh_telemetry_ui():
    """Valós időben újrarajzolja a telemetriát."""
    with telemetry_placeholder.container():
        is_detailed = st.session_state.get("telemetry_toggle", False)
        render_telemetry_dashboard(st.session_state.telemetria, is_detailed)

refresh_telemetry_ui()

# --- OLDALSÁV (SIDEBAR) Minden elem zárolva futás alatt! ---
st.sidebar.title("⚙️ Rendszerbeállítások")
elerheto_modellek = get_lm_studio_models() or ["local-model"]
kivalasztott_modell = st.sidebar.selectbox("Általános AI Modell:", options=elerheto_modellek, disabled=felulet_zarolva)

po_def = st.sidebar.text_input("👔 PO típusa:", config.DEFAULT_PO, disabled=felulet_zarolva)
ba_def = st.sidebar.text_input("📋 BA típusa:", config.DEFAULT_BA, disabled=felulet_zarolva)
ux_def = st.sidebar.text_input("🎨 UX típusa:", config.DEFAULT_UX, disabled=felulet_zarolva)
it_def = st.sidebar.text_input("💻 IT típusa:", config.DEFAULT_IT, disabled=felulet_zarolva)
qa_def = st.sidebar.text_input("🔎 QA típusa:", config.DEFAULT_QA, disabled=felulet_zarolva)
sm_def = st.sidebar.text_input("⏱️ SM típusa:", config.DEFAULT_SM, disabled=felulet_zarolva)

finomitas_korok = st.sidebar.slider("Finomítási körök:", 1, 5, 2, disabled=felulet_zarolva)
vegtelen_mod = st.sidebar.toggle("Végtelen mód", value=True, disabled=felulet_zarolva)
korok_szama = 100 if vegtelen_mod else st.sidebar.slider("Maximum vitakörök:", 1, 15, 5, disabled=felulet_zarolva)
minimum_korok = st.sidebar.slider("Min. KÖTELEZŐ iteráció:", 1, 5, 3, disabled=felulet_zarolva)

if st.sidebar.button("🗑️ Teljes Rendszer Reset", disabled=felulet_zarolva):
    clear_memory_file()
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- LABOR INDÍTÁSA (Zárolt folyamat) ---
if st.sidebar.button("🚀 Labor indítása (Profilok Építése)", disabled=felulet_zarolva):
    st.session_state.telemetria = {'osszes_ido': 0.0, 'osszes_token': 0, 'agensek': {}}
    st.session_state.labor_folyamatban = True
    st.rerun()

if st.session_state.labor_folyamatban:
    with st.status("🧬 Viselkedéskutató labor dolgozik... (A felület lezárva!)", expanded=True) as status:
        szereplok = [("PO", po_def, "po_persona"), ("BA", ba_def, "ba_persona"), ("UX", ux_def, "ux_persona"),
                     ("IT", it_def, "it_persona"), ("QA", qa_def, "qa_persona"), ("SM", sm_def, "sm_persona")]
        for nev, definicio, state_key in szereplok:
            st.write(f"⏳ **{nev}** alapvázlatának generálása folyamatban...")
            chain_base = generate_base_profile(kivalasztott_modell, definicio)
            profil = run_agent_with_telemetry("Viselkedéskutató Lab", chain_base, {"role": definicio})
            st.success(f"✓ {nev} alapvázlat kész.")
            
            for i in range(finomitas_korok):
                st.write(f"🔄 **{nev}** - Szociológiai elemzés: {i+1}. kör...")
                chain_refine = refine_profile(kivalasztott_modell, profil, nev, i+1)
                profil = run_agent_with_telemetry("Viselkedéskutató Lab", chain_refine, {"role_name": nev, "current_profile": profil, "round_num": i+1})
                st.success(f"✓ {nev} - {i+1}. iteráció befejezve.")
                
            st.session_state[state_key] = profil
            st.write("---")
            
        st.session_state.uzenetek = []
        status.update(label="Minden profil készen áll! A felület feloldva.", state="complete")
        save_memory(st.session_state.projekt_memoria, st.session_state.telemetria)
    
    st.session_state.labor_folyamatban = False
    st.rerun()

# --- SZIMULÁCIÓS FELÜLET ÉS CIKLUS ---
if not st.session_state.labor_folyamatban:
    if "po_persona" not in st.session_state:
        st.info("👈 Indítsd el a labort az oldalsávon a karakterek felépítéséhez!")
    else:
        with st.expander("📂 Aktuális Projekt Memória (JSON perzisztált)"):
            st.info(st.session_state.projekt_memoria)

        with st.expander("👁️ Eredmény: A Viselkedéskutató által finomított mélyprofilok", expanded=False):
            c1, c2 = st.columns(2)
            c1.markdown(f"**👔 PO:**\n{st.session_state.po_persona}\n\n**📋 BA:**\n{st.session_state.ba_persona}\n\n**🎨 UX:**\n{st.session_state.ux_persona}")
            c2.markdown(f"**💻 IT:**\n{st.session_state.it_persona}\n\n**🔎 QA:**\n{st.session_state.qa_persona}\n\n**⏱️ SM:**\n{st.session_state.sm_persona}")

        # Korábbi üzenetek kirajzolása
        for uzenet in st.session_state.uzenetek:
            with st.chat_message(uzenet["szerep"], avatar=uzenet["avatar"]):
                st.markdown(f"**{uzenet['szerep_nev']}**\n\n{uzenet['szoveg']}")

        # ÚJ RÉSZ: Callback függvény a bemenethez (ez aktiválja a zárat)
        def inditsd_a_sprintet():
            if st.session_state.uzenet_bemenet:
                st.session_state.sprint_folyamatban = True
                st.session_state.aktualis_feladat = st.session_state.uzenet_bemenet
                st.session_state.telemetria = {'osszes_ido': 0.0, 'osszes_token': 0, 'agensek': {}}
                st.session_state.eredeti_feladat = st.session_state.uzenet_bemenet
                # Azonnal hozzáadjuk az ügyfél üzenetét a memóriához
                st.session_state.uzenetek.append({"szerep": "user", "szerep_nev": "Ügyfél (Te)", "avatar": "👤", "szoveg": st.session_state.uzenet_bemenet})

        # A chat input most már letiltódik, ha zárolva van a felület
        st.chat_input("Írd be a projekt ötletet a csapatnak...", key="uzenet_bemenet", on_submit=inditsd_a_sprintet, disabled=felulet_zarolva)

        # Ha a callback aktiválta a sprintet, elindul a hurok
        if st.session_state.sprint_folyamatban:
            aktualis_bemenet = st.session_state.aktualis_feladat
            status_manager = SprintStatusManager(korok_szama, minimum_korok)
            
            for kor in range(korok_szama):
                status_manager.update_round(kor)
                mem = st.session_state.projekt_memoria
                igeny = st.session_state.eredeti_feladat

                # --- PO ---
                recent_hist = format_recent_history(st.session_state.uzenetek)
                status_manager.set_active_agent("👔", "Product Owner", "üzleti igényeket elemez és válaszol")
                with st.chat_message("assistant", avatar="👔"):
                    with st.spinner("Gépel..."):
                        chain = get_agent_chain(kivalasztott_modell, "PO", st.session_state.po_persona)
                        po_valasz = run_agent_with_telemetry("PO", chain, {"projekt_memoria": mem, "recent_history": recent_hist, "kerdes": aktualis_bemenet, "eredeti_igeny": igeny})
                        st.markdown(f"**Product Owner**\n\n{po_valasz}")
                st.session_state.uzenetek.append({"szerep": "assistant", "szerep_nev": "Product Owner", "avatar": "👔", "szoveg": po_valasz})

                # --- BA ---
                recent_hist = format_recent_history(st.session_state.uzenetek)
                status_manager.set_active_agent("📋", "Business Analyst", "technikai specifikációt készít")
                with st.chat_message("assistant", avatar="📋"):
                    with st.spinner("Gépel..."):
                        chain = get_agent_chain(kivalasztott_modell, "BA", st.session_state.ba_persona)
                        ba_valasz = run_agent_with_telemetry("BA", chain, {"projekt_memoria": mem, "recent_history": recent_hist, "kerdes": po_valasz, "eredeti_igeny": igeny})
                        st.markdown(f"**Business Analyst**\n\n{ba_valasz}")
                st.session_state.uzenetek.append({"szerep": "assistant", "szerep_nev": "Business Analyst", "avatar": "📋", "szoveg": ba_valasz})

                # --- UX/UI ---
                recent_hist = format_recent_history(st.session_state.uzenetek)
                status_manager.set_active_agent("🎨", "UX/UI Designer", "megtervezi a felületet")
                with st.chat_message("assistant", avatar="🎨"):
                    with st.spinner("Gépel..."):
                        chain = get_agent_chain(kivalasztott_modell, "UX", st.session_state.ux_persona)
                        ux_valasz = run_agent_with_telemetry("UX", chain, {"projekt_memoria": mem, "recent_history": recent_hist, "kerdes": ba_valasz, "eredeti_igeny": igeny})
                        st.markdown(f"**UX/UI Designer**\n\n{ux_valasz}")
                        extract_and_render_wireframe(ux_valasz)
                st.session_state.uzenetek.append({"szerep": "assistant", "szerep_nev": "UX/UI Designer", "avatar": "🎨", "szoveg": ux_valasz})

                # --- IT ---
                recent_hist = format_recent_history(st.session_state.uzenetek)
                status_manager.set_active_agent("💻", "Informatikus", "kódot ír")
                with st.chat_message("assistant", avatar="💻"):
                    with st.spinner("Gépel..."):
                        chain = get_agent_chain(kivalasztott_modell, "IT", st.session_state.it_persona)
                        it_valasz = run_agent_with_telemetry("IT", chain, {"projekt_memoria": mem, "recent_history": recent_hist, "kerdes": ux_valasz, "eredeti_igeny": igeny})
                        st.markdown(f"**Informatikus**\n\n{it_valasz}")
                st.session_state.uzenetek.append({"szerep": "assistant", "szerep_nev": "Informatikus", "avatar": "💻", "szoveg": it_valasz})

                # --- QA ---
                recent_hist = format_recent_history(st.session_state.uzenetek)
                status_manager.set_active_agent("🔎", "Manual QA", "vizsgálja a kódot")
                with st.chat_message("assistant", avatar="🔎"):
                    with st.spinner("Gépel..."):
                        chain = get_agent_chain(kivalasztott_modell, "QA", st.session_state.qa_persona)
                        qa_valasz = run_agent_with_telemetry("QA", chain, {"projekt_memoria": mem, "recent_history": recent_hist, "kerdes": it_valasz, "eredeti_igeny": igeny})
                        st.markdown(f"**Manual QA**\n\n{qa_valasz}")
                st.session_state.uzenetek.append({"szerep": "assistant", "szerep_nev": "Manual QA", "avatar": "🔎", "szoveg": qa_valasz})

                # --- SM ---
                recent_hist = format_recent_history(st.session_state.uzenetek)
                status_manager.set_active_agent("⏱️", "Scrum Master", "értékel")
                with st.chat_message("assistant", avatar="⏱️"):
                    with st.spinner("Gépel..."):
                        chain = get_agent_chain(kivalasztott_modell, "SM", st.session_state.sm_persona)
                        sm_valasz = run_agent_with_telemetry("SM", chain, {"projekt_memoria": mem, "recent_history": recent_hist, "kerdes": qa_valasz, "eredeti_igeny": igeny})
                        st.markdown(f"**Scrum Master**\n\n{sm_valasz}")
                st.session_state.uzenetek.append({"szerep": "assistant", "szerep_nev": "Scrum Master", "avatar": "⏱️", "szoveg": sm_valasz})

                # --- MEMÓRIA FRISSÍTÉSE ---
                status_manager.set_system_action("Adatbázis és telemetria mentése")
                with st.spinner("Memória frissítése..."):
                    aktualis_kor_beszelgetes = f"PO: {po_valasz}\nBA: {ba_valasz}\nUX: {ux_valasz}\nIT: {it_valasz}\nQA: {qa_valasz}\nSM: {sm_valasz}"
                    chain_mem = update_project_memory(kivalasztott_modell, aktualis_kor_beszelgetes, st.session_state.projekt_memoria)
                    st.session_state.projekt_memoria = run_agent_with_telemetry("Rendszer (Admin)", chain_mem, {"jelenlegi_memoria": st.session_state.projekt_memoria, "uj_uzenetek": aktualis_kor_beszelgetes})
                    save_memory(st.session_state.projekt_memoria, st.session_state.telemetria)

                # --- CIKLUS VIZSGÁLATA ---
                if "[LEZÁRVA]" in sm_valasz:
                    if kor < minimum_korok - 1:
                        status_manager.show_enforced_rule_warning(kor)
                        aktualis_bemenet = sm_valasz + "\n\nRENDSZER ÜZENET A PO-NAK: Felülbírálat! Követelj mélyebb tesztelést!"
                    else:
                        status_manager.finish_success()
                        break 
                else:
                    aktualis_bemenet = sm_valasz
                
                if kor == korok_szama - 1:
                    status_manager.finish_timebox()

            # A teljes futás végén levesszük a zárat és frissítjük az oldalt!
            st.session_state.sprint_folyamatban = False
            st.rerun()