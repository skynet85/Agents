import streamlit as st
import requests
import json
import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# --- KONFIGURÁCIÓ ÉS FÁJLKEZELÉS ---
st.set_page_config(page_title="Lokális AI Szimulátor", page_icon="🧠", layout="wide")
MEMORIA_FAJL = "szimulacio_memoria.json"

def load_memory():
    """Betölti a projekt memóriát a fizikai JSON fájlból."""
    if os.path.exists(MEMORIA_FAJL):
        try:
            with open(MEMORIA_FAJL, "r", encoding="utf-8") as f:
                return json.load(f).get("memoria", "A projekt még nem kezdődött el.")
        except:
            return "A projekt még nem kezdődött el."
    return "A projekt még nem kezdődött el."

def save_memory(memoria_szoveg):
    """Kimenti a projekt memóriát a fizikai JSON fájlba."""
    with open(MEMORIA_FAJL, "w", encoding="utf-8") as f:
        json.dump({"memoria": memoria_szoveg}, f, ensure_ascii=False, indent=4)

def clear_memory_file():
    """Törli a mentett memóriát egy teljes reset esetén."""
    if os.path.exists(MEMORIA_FAJL):
        os.remove(MEMORIA_FAJL)

# --- LM STUDIO MODELL LISTA ---
def get_lm_studio_models():
    try:
        response = requests.get("http://localhost:1234/v1/models")
        if response.status_code == 200:
            return [model['id'] for model in response.json()['data']]
        return []
    except:
        return []

# --- OLDALSÁV (SIDEBAR) & BEÁLLÍTÁSOK ---
st.sidebar.title("⚙️ Rendszerbeállítások")
elerheto_modellek = get_lm_studio_models() or ["local-model"]
kivalasztott_modell = st.sidebar.selectbox("Általános AI Modell:", options=elerheto_modellek)

st.sidebar.markdown("### 1. Csapat Alapkarakterei")
po_def = st.sidebar.text_input("👔 PO típusa:", "Szigorú, határidő-orientált német menedzser")
it_def = st.sidebar.text_input("💻 IT típusa:", "Kissé kiégett, cinikus magyar senior fejlesztő")
sm_def = st.sidebar.text_input("⏱️ SM típusa:", "Tapasztalt, szigorú amerikai agilis coach")

st.sidebar.markdown("### 2. Viselkedéskutató Labor")
finomitas_korok = st.sidebar.slider("Finomítási körök (Mélyítés):", 1, 5, 2)

st.sidebar.markdown("### 3. Szimuláció & Szabályok")
vegtelen_mod = st.sidebar.toggle("Végtelen mód (Megegyezésig)", value=True)
korok_szama = 100 if vegtelen_mod else st.sidebar.slider("Maximum vitakörök:", 1, 15, 5)
minimum_korok = st.sidebar.slider("Min. KÖTELEZŐ iteráció (kód kikényszerítése):", 1, 5, 2)

if st.sidebar.button("🗑️ Teljes Rendszer Reset"):
    clear_memory_file()
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- ÁLLAPOTOK INICIALIZÁLÁSA ---
if "projekt_memoria" not in st.session_state:
    st.session_state.projekt_memoria = load_memory()
if "uzenetek" not in st.session_state:
    st.session_state.uzenetek = []
if "eredeti_feladat" not in st.session_state:
    st.session_state.eredeti_feladat = "Nincs megadva."

# --- VECTORLESS MEMÓRIA KEZELŐ (JEGYZŐKÖNYVVEZETŐ) ---
def update_project_memory(uj_uzenetek, jelenlegi_memoria):
    llm = ChatOpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio", model=kivalasztott_modell, temperature=0.1)
    prompt = PromptTemplate(
        input_variables=["jelenlegi_memoria", "uj_uzenetek"],
        template="""Te egy precíz szoftverfejlesztési adminisztrátor vagy. 
        Frissítsd a projekt dokumentációját az új események alapján. Csak a tényeket, meghozott technikai döntéseket és a leszállított kódot őrizd meg! A vitákat és érzelmeket hagyd ki.
        
        JELENLEGI DOKUMENTÁCIÓ:
        {jelenlegi_memoria}
        
        ÚJ ESEMÉNYEK:
        {uj_uzenetek}
        
        Írd meg a frissített, letisztult dokumentációt:"""
    )
    return (prompt | llm | StrOutputParser()).invoke({
        "jelenlegi_memoria": jelenlegi_memoria, 
        "uj_uzenetek": uj_uzenetek
    })

def format_recent_history(messages):
    """Csak az utolsó 3 üzenetet tartja meg a közvetlen kontextushoz."""
    return "".join([f"{msg['szerep_nev']}: {msg['szoveg']}\n" for msg in messages[-3:]])

# --- PERSONA ARCHITECT FÁZIS ---
def generate_base_profile(role_description):
    llm = ChatOpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio", model=kivalasztott_modell)
    prompt = PromptTemplate(input_variables=["role"], template="Készíts 3 mondatos leírást a karakterről: '{role}'. Csak a leírást írd.")
    return (prompt | llm | StrOutputParser()).invoke({"role": role_description})

def refine_profile(current_profile, role_name, round_num):
    llm = ChatOpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio", model=kivalasztott_modell, temperature=0.8)
    prompt = PromptTemplate(
        input_variables=["role_name", "current_profile", "round_num"],
        template="""Te egy szociológus vagy. Finomítsd az alábbi profilt a {round_num}. iterációban. Szerep: {role_name}. Jelenlegi: {current_profile}. Adj hozzá kognitív torzításokat és rejtett motivációkat. Csak a profilt írd le!"""
    )
    return (prompt | llm | StrOutputParser()).invoke({"role_name": role_name, "current_profile": current_profile, "round_num": round_num})

if st.sidebar.button("🚀 Labor indítása (Profilok Építése)"):
    with st.status("🧬 Viselkedéskutató labor dolgozik...", expanded=True) as status:
        szereplok = [("PO", po_def, "po_persona"), ("IT", it_def, "it_persona"), ("SM", sm_def, "sm_persona")]
        for nev, definicio, state_key in szereplok:
            st.write(f"**{nev} felépítése...**")
            profil = generate_base_profile(definicio)
            for i in range(finomitas_korok):
                profil = refine_profile(profil, nev, i+1)
            st.session_state[state_key] = profil
        st.session_state.uzenetek = []
        status.update(label="Minden profil készen áll!", state="complete")

# --- AI KARAKTEREK LÉTREHOZÁSA (SZIMULÁCIÓHOZ) ---
def get_agent_chain(szerep, persona_profile):
    llm = ChatOpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio", model=kivalasztott_modell, temperature=0.7)
    
    base_template = f"Te az alábbi mélypszichológiai profillal rendelkezel. Éld bele magad a szerepbe:\n---\n{persona_profile}\n---\n"
    
    if szerep == "PO":
        task_template = """Feladatod: Product Owner (PO).
Eredeti ügyféligény: '{eredeti_igeny}'
SZABÁLY: A kód sosem tökéletes elsőre! Követelj forráskódot. Ne elégedj meg tervekkel!

[HIVATALOS PROJEKT DOKUMENTÁCIÓ]
{projekt_memoria}

[KÖZVETLEN ELŐZMÉNYEK]
{recent_history}

Legutóbbi üzenet: {kerdes}
A te válaszod (PO-ként):"""

    elif szerep == "IT":
        task_template = """Feladatod: Informatikus.
Eredeti ügyféligény: '{eredeti_igeny}'
SZABÁLY: Gépeld be a TÉNYLEGES FORRÁSKÓDOT! Ne csak beszélj róla.

[HIVATALOS PROJEKT DOKUMENTÁCIÓ]
{projekt_memoria}

[KÖZVETLEN ELŐZMÉNYEK]
{recent_history}

Legutóbbi üzenet: {kerdes}
A te válaszod (Informatikusként):"""

    else: # SM
        task_template = """Feladatod: Scrum Master (Moderátor).
Eredeti ügyféligény: '{eredeti_igeny}'
SZABÁLY: CSAK akkor írd be a [LEZÁRVA] szót, ha a letesztelt forráskód ténylegesen legépelve látszik a memóriában. Ha a munka még folyik, ne zárd le!

[HIVATALOS PROJEKT DOKUMENTÁCIÓ]
{projekt_memoria}

[KÖZVETLEN ELŐZMÉNYEK]
{recent_history}

A te moderálásod:"""

    prompt = PromptTemplate(input_variables=["projekt_memoria", "recent_history", "kerdes", "eredeti_igeny"], template=base_template + task_template)
    return prompt | llm | StrOutputParser()

# --- FELÜLET ÉS SZIMULÁCIÓ LOOP ---
st.title("🧠 Vektormentes Agilis Szimulátor")

if "po_persona" not in st.session_state:
    st.info("👈 Indítsd el a labort az oldalsávon a karakterek felépítéséhez!")
else:
    # Memória megjelenítése a felületen
    with st.expander("📂 Aktuális Projekt Memória (JSON perzisztált)"):
        st.info(st.session_state.projekt_memoria)
    # Generált karakterek megjelenítése a felületen
    with st.expander("👁️ Eredmény: A Viselkedéskutató által finomított mélyprofilok"):
        st.markdown(f"**👔 PO profilja:**\n{st.session_state.po_persona}")
        st.markdown(f"**💻 IT profilja:**\n{st.session_state.it_persona}")
        st.markdown(f"**⏱️ SM profilja:**\n{st.session_state.sm_persona}")

    # Chat történet kirajzolása
    for uzenet in st.session_state.uzenetek:
        with st.chat_message(uzenet["szerep"], avatar=uzenet["avatar"]):
            st.markdown(f"**{uzenet['szerep_nev']}**\n\n{uzenet['szoveg']}")

    if felhasznalo_kerdese := st.chat_input("Írd be a projekt ötletet a csapatnak..."):
        
        # Ha a felhasználó ír, beállítjuk mint eredeti feladat
        st.session_state.eredeti_feladat = felhasznalo_kerdese
        st.session_state.uzenetek.append({"szerep": "user", "szerep_nev": "Ügyfél (Te)", "avatar": "👤", "szoveg": felhasznalo_kerdese})
        
        with st.chat_message("user", avatar="👤"):
            st.markdown(f"**Ügyfél (Te)**\n\n{felhasznalo_kerdese}")

        aktualis_bemenet = felhasznalo_kerdese
        
        for kor in range(korok_szama):
            st.toast(f"🔄 {kor+1}. vita kör...", icon="⏳")
            
            recent_hist = format_recent_history(st.session_state.uzenetek)
            mem = st.session_state.projekt_memoria
            igeny = st.session_state.eredeti_feladat

            # --- PO ---
            with st.chat_message("assistant", avatar="👔"):
                with st.spinner("A PO válaszol..."):
                    po_valasz = get_agent_chain("PO", st.session_state.po_persona).invoke(
                        {"projekt_memoria": mem, "recent_history": recent_hist, "kerdes": aktualis_bemenet, "eredeti_igeny": igeny}
                    )
                    st.markdown(f"**Product Owner**\n\n{po_valasz}")
            st.session_state.uzenetek.append({"szerep": "assistant", "szerep_nev": "Product Owner", "avatar": "👔", "szoveg": po_valasz})

            recent_hist = format_recent_history(st.session_state.uzenetek)

            # --- IT ---
            with st.chat_message("assistant", avatar="💻"):
                with st.spinner("Az Informatikus válaszol..."):
                    it_valasz = get_agent_chain("IT", st.session_state.it_persona).invoke(
                        {"projekt_memoria": mem, "recent_history": recent_hist, "kerdes": po_valasz, "eredeti_igeny": igeny}
                    )
                    st.markdown(f"**Informatikus**\n\n{it_valasz}")
            st.session_state.uzenetek.append({"szerep": "assistant", "szerep_nev": "Informatikus", "avatar": "💻", "szoveg": it_valasz})

            recent_hist = format_recent_history(st.session_state.uzenetek)

            # --- SM ---
            with st.chat_message("assistant", avatar="⏱️"):
                with st.spinner("A Scrum Master moderál..."):
                    sm_valasz = get_agent_chain("SM", st.session_state.sm_persona).invoke(
                        {"projekt_memoria": mem, "recent_history": recent_hist, "kerdes": "Értékeld a helyzetet!", "eredeti_igeny": igeny}
                    )
                    st.markdown(f"**Scrum Master**\n\n{sm_valasz}")
            st.session_state.uzenetek.append({"szerep": "assistant", "szerep_nev": "Scrum Master", "avatar": "⏱️", "szoveg": sm_valasz})

            # --- VECTORLESS MEMORY FRISSÍTÉSE ---
            with st.spinner("Projekt dokumentáció frissítése a háttérben..."):
                aktualis_kor_beszelgetes = f"PO mondta: {po_valasz}\nIT mondta: {it_valasz}\nSM mondta: {sm_valasz}"
                st.session_state.projekt_memoria = update_project_memory(aktualis_kor_beszelgetes, st.session_state.projekt_memoria)
                save_memory(st.session_state.projekt_memoria) # Perzisztálás SSD-re

            # --- CIKLUS VIZSGÁLATA (MINIMUM KÖRÖK) ---
            if "[LEZÁRVA]" in sm_valasz:
                if kor < minimum_korok - 1:
                    st.warning(f"⚠️ A Scrum Master lezárta volna a ticketet, de a rendszer még {minimum_korok - (kor + 1)} kötelező iterációt megkövetel a kód finomítására!")
                    aktualis_bemenet = sm_valasz + "\n\nRENDSZER ÜZENET A PO-NAK: A feladat lezárása visszautasítva. Követelj egy plusz validációt/tesztet az IT-stól!"
                else:
                    st.success("🎉 **A Scrum Master lezárta a sprintet, a feladat elkészült!** (Az eredmény mentve a JSON fájlba).")
                    break 
            else:
                aktualis_bemenet = sm_valasz