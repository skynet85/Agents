# app.py
import streamlit as st
from datetime import datetime
import config
from memory_manager import load_all_runs, save_run, clear_memory_file
from ui_components import SprintStatusManager
from agents import (
    get_lm_studio_models, generate_base_profile, refine_profile, 
    get_agent_chain, update_project_memory, format_recent_history
)
from util import extract_and_render_wireframe, run_agent_with_telemetry, refresh_telemetry_ui

# --- INICIALIZÁLÁS ÉS ÁLLAPOTGÉP ---
st.set_page_config(page_title="Lokális AI Szimulátor", page_icon="🧠", layout="wide")

# Állapotváltozók a menürendszerhez és értékeléshez
if "menu_nezet" not in st.session_state: st.session_state.menu_nezet = True
if "run_id" not in st.session_state: st.session_state.run_id = None
if "run_datum" not in st.session_state: st.session_state.run_datum = None
if "ertekelesek" not in st.session_state: st.session_state.ertekelesek = {"PO": 0, "BA": 0, "UX": 0, "IT": 0, "QA": 0, "SM": 0}
if "ertekeles_aktiv" not in st.session_state: st.session_state.ertekeles_aktiv = False

# Állapotváltozók a szimulációhoz
if "projekt_memoria" not in st.session_state: st.session_state.projekt_memoria = "A projekt még nem kezdődött el."
if "telemetria" not in st.session_state: st.session_state.telemetria = {'osszes_ido': 0.0, 'osszes_token': 0, 'agensek': {}}
if "uzenetek" not in st.session_state: st.session_state.uzenetek = []
if "eredeti_feladat" not in st.session_state: st.session_state.eredeti_feladat = "Nincs megadva."
if "labor_folyamatban" not in st.session_state: st.session_state.labor_folyamatban = False
if "sprint_folyamatban" not in st.session_state: st.session_state.sprint_folyamatban = False
if "agens_dolgozik" not in st.session_state: st.session_state.agens_dolgozik = False

if "sprint_allapot" not in st.session_state: 
    st.session_state.sprint_allapot = {"kor": 0, "agens_idx": 0, "elozo_kimenet": "", "valaszok": {}}

# --- KETTŐS ZÁROLÁSI RENDSZER ---
rendszer_zarolva = st.session_state.labor_folyamatban or st.session_state.sprint_folyamatban
modell_dolgozik_zar = st.session_state.labor_folyamatban or st.session_state.agens_dolgozik or (st.session_state.sprint_folyamatban and not st.session_state.get("lepesenkenti_mod", False))


# ==========================================
# 1. FŐMENÜ NÉZET
# ==========================================
if st.session_state.menu_nezet:
    st.title("📂 LLMOps Projekt Menedzser")
    st.markdown("Válassz egy korábbi szimulációt, vagy indíts egy teljesen újat!")
    
    if st.button("✨ Új Szimuláció Indítása", type="primary", use_container_width=True):
        st.session_state.menu_nezet = False
        st.session_state.run_id = None
        st.session_state.projekt_memoria = "A projekt még nem kezdődött el."
        st.session_state.telemetria = {'osszes_ido': 0.0, 'osszes_token': 0, 'agensek': {}}
        st.session_state.uzenetek = []
        st.session_state.ertekelesek = {"PO": 0, "BA": 0, "UX": 0, "IT": 0, "QA": 0, "SM": 0}
        st.session_state.ertekeles_aktiv = False
        st.session_state.sprint_folyamatban = False
        st.session_state.agens_dolgozik = False
        st.rerun()

    st.divider()
    st.subheader("🕰️ Korábbi futások előzményei")
    
    runs = load_all_runs()
    if not runs:
        st.info("Még nem található mentett szimuláció az adatbázisban.")
    else:
        for r in reversed(runs):
            with st.expander(f"📅 {r['datum']} | 📝 {r['feladat'][:80]}..."):
                st.markdown("**Ágensek értékelése (5-ös skálán):**")
                cols = st.columns(6)
                for i, (agent, score) in enumerate(r.get('ertekelesek', {}).items()):
                    cols[i].metric(agent, f"{score} ⭐" if score > 0 else "Nincs értékelve")
                
                st.markdown(f"**Összes token:** {r['telemetria'].get('osszes_token', 0):,}")
                
                if st.button("🚀 Eredmény Megtekintése / Folytatás", key=f"load_{r['run_id']}"):
                    st.session_state.run_id = r['run_id']
                    st.session_state.run_datum = r['datum']
                    st.session_state.projekt_memoria = r['memoria']
                    st.session_state.uzenetek = r['uzenetek']
                    st.session_state.telemetria = r['telemetria']
                    st.session_state.ertekelesek = r.get('ertekelesek', {"PO": 0, "BA": 0, "UX": 0, "IT": 0, "QA": 0, "SM": 0})
                    st.session_state.eredeti_feladat = r['feladat']
                    st.session_state.menu_nezet = False
                    st.session_state.ertekeles_aktiv = False
                    st.session_state.sprint_folyamatban = False
                    st.rerun()

# ==========================================
# 2. SZIMULÁTOR NÉZET
# ==========================================
else:
    # --- OLDALSÁV ---
    st.sidebar.title("⚙️ Vezérlőpult")
    if st.sidebar.button("⬅️ Vissza a Főmenübe", disabled=st.session_state.labor_folyamatban):
        st.session_state.menu_nezet = True
        st.rerun()
        
    st.sidebar.divider()
    
    st.session_state.lepesenkenti_mod = st.sidebar.toggle("⏸️ Léptetéses mód (Megállítás ágensenként)", value=st.session_state.get("lepesenkenti_mod", False))
    
    elerheto_modellek = get_lm_studio_models() or ["local-model"]
    kivalasztott_modell = st.sidebar.selectbox("Általános AI Modell:", options=elerheto_modellek, disabled=rendszer_zarolva)

    po_def = st.sidebar.text_input("👔 PO típusa:", config.DEFAULT_PO, disabled=rendszer_zarolva)
    ba_def = st.sidebar.text_input("📋 BA típusa:", config.DEFAULT_BA, disabled=rendszer_zarolva)
    ux_def = st.sidebar.text_input("🎨 UX típusa:", config.DEFAULT_UX, disabled=rendszer_zarolva)
    it_def = st.sidebar.text_input("💻 IT típusa:", config.DEFAULT_IT, disabled=rendszer_zarolva)
    qa_def = st.sidebar.text_input("🔎 QA típusa:", config.DEFAULT_QA, disabled=rendszer_zarolva)
    sm_def = st.sidebar.text_input("⏱️ SM típusa:", config.DEFAULT_SM, disabled=rendszer_zarolva)

    finomitas_korok = st.sidebar.slider("Finomítási körök:", 1, 5, 2, disabled=rendszer_zarolva)
    vegtelen_mod = st.sidebar.toggle("Végtelen mód", value=True, disabled=rendszer_zarolva)
    korok_szama = 100 if vegtelen_mod else st.sidebar.slider("Maximum vitakörök:", 1, 15, 5, disabled=rendszer_zarolva)
    minimum_korok = st.sidebar.slider("Min. KÖTELEZŐ iteráció:", 1, 5, 3, disabled=rendszer_zarolva)

    if st.sidebar.button("🗑️ Teljes Rendszer Reset (Törlés)", disabled=rendszer_zarolva):
        clear_memory_file()
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    if st.sidebar.button("🚀 Labor indítása (Profilok Építése)", disabled=rendszer_zarolva):
        st.session_state.labor_folyamatban = True
        st.rerun()

# --- LEBEGŐ TELEMETRIA ---
    st.title("🧠 LLMOps Agilis Szimulátor")

    # A "Sziklaszilárd" CSS struktúra, ami áttöri a Streamlit belső konténer-hierarchiáját
    st.markdown(
        """
        <style>
            /* 1. Felszabadítjuk az összes létező szülő konténert az overflow korlátozás alól */
            [data-testid="stAppViewContainer"],
            [data-testid="stMain"],
            [data-testid="stMainBlockContainer"],
            .main .block-container,
            div[data-testid="stVerticalBlock"],
            div[data-testid="stVerticalBlockBorderWrapper"] {
                overflow: visible !important;
            }

            /* 2. CÉLZOTT LEBEGTETÉS 100%-OS TAKARÁSSAL */
            div[data-testid="stMainBlockContainer"] > div[data-testid="stVerticalBlock"] > div:has(#telemetry-anchor) {
                position: -webkit-sticky !important; /* Safari támogatás */
                position: sticky !important;
                top: 2.875rem !important; /* Pontosan a Streamlit felső sávja alá igazítva */
                z-index: 99999 !important; /* Minden ágens beszélgetés felett marad */
                
                background-color: #ffffff !important; /* Kőkemény, tömör fehér háttér */
                opacity: 1 !important; /* Zavaró átütés/átlátszóság teljes tiltása */
                
                margin-top: -1rem !important;
                padding-top: 1rem !important;
                padding-bottom: 12px !important;
                border-bottom: 1px solid #e5e7eb !important;
                box-shadow: 0px 15px 25px -10px rgba(0,0,0,0.15) !important; /* Erősebb elválasztó árnyék */
            }
            
            /* Sötét mód esetén 100%-os tömör sötétszürke/fekete */
            @media (prefers-color-scheme: dark) {
                div[data-testid="stMainBlockContainer"] > div[data-testid="stVerticalBlock"] > div:has(#telemetry-anchor) {
                    background-color: #0e1117 !important; /* Tömör sötét háttér */
                    border-bottom: 1px solid #374151 !important;
                    box-shadow: 0px 15px 25px -10px rgba(0,0,0,0.8) !important;
                }
            }
        </style>
        """,
        unsafe_allow_html=True
    )

    telemetry_container = st.container()

    with telemetry_container:
        st.markdown('<div id="telemetry-anchor"></div>', unsafe_allow_html=True) 
        c_title, c_toggle = st.columns([3, 1])
        with c_title: st.markdown("### 📊 Valós idejű LLMOps Telemetria")
        with c_toggle: st.toggle("🔍 Részletes nézet", value=False, key="telemetry_toggle", disabled=modell_dolgozik_zar)
        telemetry_placeholder = st.empty()

    refresh_telemetry_ui(telemetry_placeholder)

    # --- LABOR FOLYAMAT ---
    if st.session_state.labor_folyamatban:
        with st.status("🧬 Viselkedéskutató labor dolgozik... (A felület lezárva!)", expanded=True) as status:
            szereplok = [("PO", po_def, "po_persona"), ("BA", ba_def, "ba_persona"), ("UX", ux_def, "ux_persona"),
                         ("IT", it_def, "it_persona"), ("QA", qa_def, "qa_persona"), ("SM", sm_def, "sm_persona")]
            for nev, definicio, state_key in szereplok:
                st.write(f"⏳ **{nev}** alapvázlatának generálása folyamatban...")
                chain_base = generate_base_profile(kivalasztott_modell, definicio)
                profil = run_agent_with_telemetry("Viselkedéskutató Lab", chain_base, {"role": definicio}, telemetry_placeholder=telemetry_placeholder)
                
                for i in range(finomitas_korok):
                    chain_refine = refine_profile(kivalasztott_modell, profil, nev, i+1)
                    profil = run_agent_with_telemetry("Viselkedéskutató Lab", chain_refine, {"role_name": nev, "current_profile": profil, "round_num": i+1}, telemetry_placeholder=telemetry_placeholder)
                    
                st.session_state[state_key] = profil
                st.write(f"✓ {nev} profilja elkészült.")
                
            status.update(label="Minden profil készen áll! A felület feloldva.", state="complete")
        st.session_state.labor_folyamatban = False
        st.rerun()

    # --- SPRINT MEGJELENÍTÉS ÉS FUTTATÁS ---
    if not st.session_state.labor_folyamatban:
        if "po_persona" not in st.session_state:
            st.info("👈 Indítsd el a labort az oldalsávon a karakterek felépítéséhez!")
        else:
            with st.expander("👁️ Eredmény: A Viselkedéskutató által finomított mélyprofilok", expanded=False):
                c1, c2 = st.columns(2)
                c1.markdown(f"**👔 PO:**\n{st.session_state.po_persona}\n\n**📋 BA:**\n{st.session_state.ba_persona}\n\n**🎨 UX:**\n{st.session_state.ux_persona}")
                c2.markdown(f"**💻 IT:**\n{st.session_state.it_persona}\n\n**🔎 QA:**\n{st.session_state.qa_persona}\n\n**⏱️ SM:**\n{st.session_state.sm_persona}")

            with st.expander("📂 Aktuális Projekt Memória (Wikipédia)"):
                st.info(st.session_state.projekt_memoria)

            for uzenet in st.session_state.uzenetek:
                with st.chat_message(uzenet["szerep"], avatar=uzenet["avatar"]):
                    st.markdown(f"**{uzenet['szerep_nev']}**\n\n{uzenet['szoveg']}")

            def inditsd_a_sprintet():
                if st.session_state.uzenet_bemenet:
                    st.session_state.sprint_folyamatban = True
                    st.session_state.eredeti_feladat = st.session_state.uzenet_bemenet
                    st.session_state.uzenetek.append({"szerep": "user", "szerep_nev": "Ügyfél (Te)", "avatar": "👤", "szoveg": st.session_state.uzenet_bemenet})
                    
                    st.session_state.sprint_allapot = {"kor": 0, "agens_idx": 0, "elozo_kimenet": st.session_state.uzenet_bemenet, "valaszok": {}}
                    
                    if not st.session_state.run_id:
                        st.session_state.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                        st.session_state.run_datum = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    save_run(st.session_state.run_id, st.session_state.run_datum, st.session_state.eredeti_feladat, st.session_state.projekt_memoria, st.session_state.uzenetek, st.session_state.telemetria, st.session_state.ertekelesek)

            st.chat_input("Írd be a projekt ötletet a csapatnak...", key="uzenet_bemenet", on_submit=inditsd_a_sprintet, disabled=rendszer_zarolva)

            if st.session_state.sprint_folyamatban:
                status_manager = SprintStatusManager(korok_szama, minimum_korok)
                
                kor = st.session_state.sprint_allapot["kor"]
                idx = st.session_state.sprint_allapot["agens_idx"]
                
                status_manager.update_round(kor)

                agensek_sorrendje = [
                    ("👔", "Product Owner", "üzleti igényeket elemez", "PO", st.session_state.po_persona),
                    ("📋", "Business Analyst", "technikai specifikációt készít", "BA", st.session_state.ba_persona),
                    ("🎨", "UX/UI Designer", "megtervezi a felületet", "UX", st.session_state.ux_persona),
                    ("💻", "Informatikus", "kódot ír", "IT", st.session_state.it_persona),
                    ("🔎", "Manual QA", "vizsgálja a kódot", "QA", st.session_state.qa_persona),
                    ("⏱️", "Scrum Master", "értékel", "SM", st.session_state.sm_persona)
                ]

                # 1. KÖR VÉGE LOGIKA
                if idx == len(agensek_sorrendje):
                    st.info("🔄 **Kör vége.** Az Admin rendszer rendszerezi az eddigi vitát a memóriában...")
                    if st.session_state.get("agens_dolgozik", False):
                        st.button(f"⏳ Rendszerezés folyamatban...", disabled=True, key=f"btn_wait_admin_{kor}")
                        status_manager.set_system_action("Adatbázis és telemetria mentése")
                        with st.spinner("Memória frissítése (Admin ágens dolgozik)..."):
                            valaszok = st.session_state.sprint_allapot["valaszok"]
                            aktualis_kor_beszelgetes = f"PO: {valaszok.get('PO')}\nBA: {valaszok.get('BA')}\nUX: {valaszok.get('UX')}\nIT: {valaszok.get('IT')}\nQA: {valaszok.get('QA')}\nSM: {valaszok.get('SM')}"
                            
                            chain_mem = update_project_memory(kivalasztott_modell, aktualis_kor_beszelgetes, st.session_state.projekt_memoria)
                            admin_valasz = run_agent_with_telemetry("Rendszer (Admin)", chain_mem, {"jelenlegi_memoria": st.session_state.projekt_memoria, "uj_uzenetek": aktualis_kor_beszelgetes}, telemetry_placeholder=telemetry_placeholder)
                            
                            if st.session_state.projekt_memoria == "A projekt még nem kezdődött el.":
                                st.session_state.projekt_memoria = f"### {kor + 1}. Iteráció (Sprint log):\n{admin_valasz}"
                            else:
                                st.session_state.projekt_memoria += f"\n\n---\n### {kor + 1}. Iteráció (Sprint log):\n{admin_valasz}"
                            
                            sm_valasz = valaszok.get('SM', '')
                            
                            if "[LEZÁRVA]" in sm_valasz:
                                if kor < minimum_korok - 1:
                                    status_manager.show_enforced_rule_warning(kor)
                                    st.session_state.sprint_allapot["elozo_kimenet"] = sm_valasz + "\n\nRENDSZER ÜZENET A PO-NAK: Felülbírálat! Követelj mélyebb tesztelést!"
                                    st.session_state.sprint_allapot["kor"] += 1
                                    st.session_state.sprint_allapot["agens_idx"] = 0
                                    st.session_state.sprint_allapot["valaszok"] = {}
                                else:
                                    st.session_state.sprint_folyamatban = False
                                    st.session_state.ertekeles_aktiv = True
                                    status_manager.finish_success()
                            else:
                                st.session_state.sprint_allapot["elozo_kimenet"] = sm_valasz
                                st.session_state.sprint_allapot["kor"] += 1
                                st.session_state.sprint_allapot["agens_idx"] = 0
                                st.session_state.sprint_allapot["valaszok"] = {}
                                
                            save_run(st.session_state.run_id, st.session_state.run_datum, st.session_state.eredeti_feladat, st.session_state.projekt_memoria, st.session_state.uzenetek, st.session_state.telemetria, st.session_state.ertekelesek)
                            
                            if st.session_state.sprint_allapot["kor"] >= korok_szama and st.session_state.sprint_folyamatban:
                                st.session_state.sprint_folyamatban = False
                                st.session_state.ertekeles_aktiv = True
                                status_manager.finish_timebox()
                        
                        st.session_state.agens_dolgozik = False
                        st.rerun()
                    else:
                        def admin_kattintas(): st.session_state.agens_dolgozik = True
                        if st.session_state.lepesenkenti_mod:
                            st.button(f"▶️ Tovább: Admin mentés indítása", type="primary", key=f"btn_active_admin_{kor}", on_click=admin_kattintas)
                        else:
                            st.session_state.agens_dolgozik = True
                            st.rerun()

                # 2. ÁGENS FUTTATÁSA LOGIKA
                elif idx < len(agensek_sorrendje):
                    avatar, nev, akcio, rovid_nev, persona = agensek_sorrendje[idx]
                    status_manager.set_active_agent(avatar, nev, akcio)
                    
                    def futtas_kovetkezo_agenst():
                        recent_hist = format_recent_history(st.session_state.uzenetek)
                        with st.chat_message("assistant", avatar=avatar):
                            with st.spinner("Gépel..."):
                                chain = get_agent_chain(kivalasztott_modell, rovid_nev, persona)
                                valasz = run_agent_with_telemetry(rovid_nev, chain, {"projekt_memoria": st.session_state.projekt_memoria, "recent_history": recent_hist, "kerdes": st.session_state.sprint_allapot["elozo_kimenet"], "eredeti_igeny": st.session_state.eredeti_feladat}, telemetry_placeholder=telemetry_placeholder)
                                st.markdown(f"**{nev}**\n\n{valasz}")
                                if rovid_nev == "UX": extract_and_render_wireframe(valasz)
                        
                        st.session_state.uzenetek.append({"szerep": "assistant", "szerep_nev": nev, "avatar": avatar, "szoveg": valasz})
                        st.session_state.sprint_allapot["valaszok"][rovid_nev] = valasz
                        st.session_state.sprint_allapot["elozo_kimenet"] = valasz
                        st.session_state.sprint_allapot["agens_idx"] += 1
                        
                        save_run(st.session_state.run_id, st.session_state.run_datum, st.session_state.eredeti_feladat, st.session_state.projekt_memoria, st.session_state.uzenetek, st.session_state.telemetria, st.session_state.ertekelesek)

                    if st.session_state.lepesenkenti_mod:
                        st.info(f"⏸️ **Szimuláció várakozik.** A következő lépés: **{nev}** ({akcio}).")
                        
                        if st.session_state.get("agens_dolgozik", False):
                            st.button(f"⏳ {nev} dolgozik...", disabled=True, key=f"btn_wait_{kor}_{idx}")
                            futtas_kovetkezo_agenst()
                            st.session_state.agens_dolgozik = False
                            st.rerun()
                        else:
                            def inditas_kattintas(): st.session_state.agens_dolgozik = True
                            st.button(f"▶️ Tovább: {nev} indítása", type="primary", key=f"btn_active_{kor}_{idx}", on_click=inditas_kattintas)
                            
                    else:
                        st.session_state.agens_dolgozik = True
                        futtas_kovetkezo_agenst()
                        st.session_state.agens_dolgozik = False
                        st.rerun()

            # --- ÉRTÉKELŐ RENDSZER ---
            if st.session_state.ertekeles_aktiv and not st.session_state.sprint_folyamatban:
                st.markdown("---")
                st.markdown("### ⭐️ Sprint Lezárva: Ágensek Értékelése")
                st.info("Kérlek, értékeld 1-től 5-ig az egyes ágensek teljesítményét az aktuális feladat megoldásában!")
                
                with st.form("ertekeles_form"):
                    c1, c2, c3, c4, c5, c6 = st.columns(6)
                    agensek_szotar = {"PO": c1, "BA": c2, "UX": c3, "IT": c4, "QA": c5, "SM": c6}
                    uj_ertekelesek = {}
                    
                    for agens, col in agensek_szotar.items():
                        with col:
                            uj_ertekelesek[agens] = st.slider(agens, 1, 5, st.session_state.ertekelesek.get(agens) if st.session_state.ertekelesek.get(agens) > 0 else 3)
                    
                    submit = st.form_submit_button("💾 Értékelések Mentése és Vissza a Főmenübe")
                    
                    if submit:
                        st.session_state.ertekelesek = uj_ertekelesek
                        save_run(st.session_state.run_id, st.session_state.run_datum, st.session_state.eredeti_feladat, st.session_state.projekt_memoria, st.session_state.uzenetek, st.session_state.telemetria, st.session_state.ertekelesek)
                        st.session_state.menu_nezet = True
                        st.session_state.ertekeles_aktiv = False
                        st.rerun()