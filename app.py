import streamlit as st
import requests
from app_config import MAIN_TITLE, STATE_KEYS, AGENT_ROLES, MINIMUM_KOROK
from storage import MemoryManager
from engine import SimulationEngine

# --- INITIALIZATION ---
st.set_page_config(page_title=MAIN_TITLE, page_icon="🧠", layout="wide")
storage = MemoryManager()

def get_models():
    try:
        return [m['id'] for m in requests.get("http://localhost:1234/v1/models").json()['data']]
    except: 
        return ["local-model"]

# --- SESSION STATE ---
if STATE_KEYS["projekt_memoria"] not in st.session_state: 
    st.session_state[STATE_KEYS["projekt_memoria"]] = storage.load_memory()
if STATE_KEYS["uzenetek"] not in st.session_state: 
    st.session_state[STATE_KEYS["uzenetek"]] = []
if "po_persona" not in st.session_state: st.session_state.po_persona = ""
if "it_persona" not in st.session_state: st.session_state.it_persona = ""
if "sm_persona" not in st.session_state: st.session_state.sm_persona = ""
if STATE_KEYS["eredeti_feladat"] not in st.session_state: 
    st.session_state[STATE_KEYS["eredeti_feladat"]] = "Nincs megadva."

# --- SIDEBAR ---
st.sidebar.title("⚙️ Rendszerbeállítások")
model_list = get_models()
selected_model = st.sidebar.selectbox("Általános AI Modell:", options=model_list)

st.sidebar.markdown("### 1. Csapat Alapkarakterei")
po_def = st.sidebar.text_input("👔 PO típusa:", "Szigorű, határidő-orientált német menedzser")
it_def = st.sidebar.text_input("💻 IT típusa:", "Kissé kiégett, cinikus magyar senior fejlesztő")
sm_def = st.sidebar.text_input("⏱️ SM típusa:", "Tapasztalt, szigorú amerikai agilis coach")

st.sidebar.markdown("### 2. Viselkedéskutató Labor")
finomitas_korok = st.sidebar.slider("Finomítási körök (Mélyítés):", 1, 5, 2)

st.sidebar.markdown("### 3. Szimuláció & Szabályok")
vegtelen_mod = st.sidebar.toggle("Végtelen mód (Megegyezésig)", value=True)
korok_szama = 100 if vegtelen_mod else st.sidebar.slider("Maximum vitakörök:", 1, 15, 5)
minimum_korok = st.sidebar.slider("Min. KÖTELEZŐ iteráció:", 1, 5, 2)

if st.sidebar.button("🗑️ Teljes Rendszer Reset"):
    storage.clear_memory()
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- PERSONA BUILDING LOGIC ---
if st.sidebar.button("🚀 Labor indítása (Profilok Építése)"):
    engine = SimulationEngine(selected_model)
    with st.status("🧬 Viselkelbeberészés...", expanded=True) as status:
        szereplok = [("PO", po_def, "po_persona"), ("IT", it_def, "it_persona"), ("SM", sm_def, "sm_persona")]
        for nev, definicio, state_key in szereplok:
            st.write(f"**{nev} felépítése...**")
            profil = engine.factory.generate_profile(definicio)
            for i in range(finomitas_korok):
                profil = engine.factory.refine_profile(profil, nev, i+1)
            st.session_state[state_key] = profil
        status.update(label="Minden profil készen áll!", state="complete")

# --- MAIN UI ---
st.title(MAIN_TITLE)

if "po_persona" not in st.session_state or not st.session_state.po_persona:
    st.info("👈 Indítsd el a labort az oldalsávon a karakterek felépítéséhez!")
else:
    # Memory & Persona Display
    with st.expander("📂 Aktuális Projekt Memória"):
        st.info(st.session_state[STATE_KEYS["projekt_memoria"]])

    with st.expander("👁️ Eredmény: Mélyprofilok"):
        st.markdown(f"**👔 PO:** {st.session_state.po_persona}")
        st.markdown(f"**💻 IT:** {st.session_state.it_persona}")
        st.markdown(f"**⏱️ SM:** {st.session_state.sm_persona}")

    # Chat Display
    for msg in st.session_state[STATE_KEYS["uzenetek"]]:
        with st.chat_message(msg["szerep"], avatar=msg["avatar"]):
            st.markdown(f"**{msg['szerep_nev']}**\n\n{msg['szoveg']}")

    # Chat Input
    if prompt := st.chat_input("Írd be a projekt ötletet a csapatnak..."):
        # 1. Show user message
        st.session_state[STATE_KEYS["eredeti_feladat"]] = prompt
        st.session_state.last_user_input = prompt # Needed by engine
        st.session_state[STATE_KEYS["uzenetek"]].append({
            "szerep": "user", "szerep_nev": "Ügyfél (Te)", "avatar": "👤", "szoveg": prompt
        })
        
        # 2. Run Simulation Engine
        engine = SimulationEngine(selected_model)
        
        # Simulation Loop
        for kor in range(korok_szama):
            st.toast(f"🔄 {kor+1}. vita kör...", icon="⏳")
            
            # Run the agent cycle (PO -> IT -> SM)
            sm_res = engine.run_iteration(kor, {"min_rounds": minimum_korok})
            
            # Check if SM finished the task
            if "[LEZÁRVA]" in sm_res:
                if kor < minimum_korok - 1:
                    st.warning(f"⚠️ A Scrum Master lezárta volna a ticketet, de a rendszer még {minimum_korok - (kor + 1)} kötelező iterációt megkövetel!")
                    # Inject a system message to force another round
                    st.session_state.last_user_input = sm_res + "\n\nRENDSZER ÜZENET: A feladat lezárása visszautasítva. Követelj validációt!"
                else:
                    st.success("🎉 **Feladat elkészült!**")
                    break
            else:
                # If not finished, the loop continues to next round (or waits for next user input if logic dictates)
                # For this simple version, we wait for the next user chat input to continue the loop
                break 
        
        st.rerun()