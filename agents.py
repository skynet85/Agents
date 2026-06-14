# agents.py
import requests
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from config import API_BASE_URL, API_KEY

def get_lm_studio_models():
    try:
        response = requests.get(f"{API_BASE_URL}/models")
        if response.status_code == 200:
            return [model['id'] for model in response.json()['data']]
        return []
    except Exception:
        return []

def format_recent_history(messages):
    return "".join([f"{msg['szerep_nev']}: {msg['szoveg']}\n" for msg in messages[-6:]])

def generate_base_profile(modell_nev, role_description):
    # Időtúllépés (timeout) 600-ra emelve a kifagyások ellen!
    llm = ChatOpenAI(base_url=API_BASE_URL, api_key=API_KEY, model=modell_nev, timeout=600)
    prompt = PromptTemplate(input_variables=["role"], template="Készíts 3 mondatos leírást a karakterről: '{role}'. Csak a leírást írd.")
    # KIVETTÜK A PARSERT, hogy a tokeneket mérni tudjuk:
    return prompt | llm 

def refine_profile(modell_nev, current_profile, role_name, round_num):
    llm = ChatOpenAI(base_url=API_BASE_URL, api_key=API_KEY, model=modell_nev, temperature=0.8, timeout=600)
    prompt = PromptTemplate(
        input_variables=["role_name", "current_profile", "round_num"],
        template="""Te egy szociológus vagy. Finomítsd az alábbi profilt a {round_num}. iterációban. Szerep: {role_name}. Jelenlegi: {current_profile}. Adj hozzá kognitív torzításokat és rejtett motivációkat. Csak a profilt írd le!"""
    )
    return prompt | llm

def update_project_memory(modell_nev, uj_uzenetek, jelenlegi_memoria):
    llm = ChatOpenAI(base_url=API_BASE_URL, api_key=API_KEY, model=modell_nev, temperature=0.1, timeout=600)
    prompt = PromptTemplate(
        input_variables=["jelenlegi_memoria", "uj_uzenetek"],
        template="""Te egy precíz szoftverfejlesztési adminisztrátor vagy. 
        Frissítsd a projekt dokumentációját az új események alapján. Csak a tényeket, meghozott technikai döntéseket, teszteredményeket és a leszállított kódot őrizd meg! A vitákat és érzelmeket hagyd ki.
        
        JELENLEGI DOKUMENTÁCIÓ:
        {jelenlegi_memoria}
        
        ÚJ ESEMÉNYEK:
        {uj_uzenetek}
        
        Írd meg a frissített, letisztult dokumentációt:"""
    )
    return prompt | llm

def get_agent_chain(modell_nev, szerep, persona_profile):
    llm = ChatOpenAI(base_url=API_BASE_URL, api_key=API_KEY, model=modell_nev, temperature=0.7, timeout=600)
    base_template = f"Te az alábbi mélypszichológiai profillal rendelkezel. Éld bele magad a szerepbe:\n---\n{persona_profile}\n---\n"
    
    if szerep == "PO":
        task_template = """Feladatod: Product Owner (PO).\nEredeti ügyféligény: '{eredeti_igeny}'\nSZABÁLY: Az üzleti értékre fókuszálj. Ne fogadj el fékmunkát.\n[DOKUMENTÁCIÓ]\n{projekt_memoria}\n[ELŐZMÉNYEK]\n{recent_history}\nLegutóbbi üzenet: {kerdes}\nA te válaszod:"""
    elif szerep == "BA":
        task_template = """Feladatod: IT Business Analyst (BA).\nEredeti ügyféligény: '{eredeti_igeny}'\nSZABÁLY: Elemezd a PO kérését, specifikálj és kérdezz rá a kivételekre!\n[DOKUMENTÁCIÓ]\n{projekt_memoria}\n[ELŐZMÉNYEK]\n{recent_history}\nLegutóbbi üzenet: {kerdes}\nA te válaszod:"""
    elif szerep == "UX":
        task_template = """Feladatod: UX/UI Designer.\nEredeti ügyféligény: '{eredeti_igeny}'\nSZABÁLY: Tervezd meg a BA specifikációja alapján a felületet. \n Készíts pixel-perfect mockupokat és figyelj az ergonómiára! \nKészíts egy vizuális drótvázat (Wireframe) egyetlen, futtatható HTML kód formájában, amely Tailwind CSS-t használ (CDN-en keresztül). \nA dizájn legyen modern, letisztult és mutassa be a kért funkciókat (gombok, beviteli mezők, elrendezés).\nNAGYON FONTOS: A HTML kódot szigorúan ```html és ``` tagek közé zárd, hogy a rendszer ki tudja nyerni! A kód köré írhatsz magyarázatot, de a kód csak ebben a blokkban legyen. \n[DOKUMENTÁCIÓ]\n{projekt_memoria}\n[ELŐZMÉNYEK]\n{recent_history}\nLegutóbbi üzenet: {kerdes} \nA te válaszod:"""
    elif szerep == "IT":
        task_template = """Feladatod: Informatikus.\nEredeti ügyféligény: '{eredeti_igeny}'\nSZABÁLY: Gépeld be a TÉNYLEGES FORRÁSKÓDOT! Javítsd a QA hibáit!\n[DOKUMENTÁCIÓ]\n{projekt_memoria}\n[ELŐZMÉNYEK]\n{recent_history}\nLegutóbbi üzenet: {kerdes}\nA te válaszod:"""
    elif szerep == "QA":
        task_template = """Feladatod: Manual QA.\nEredeti ügyféligény: '{eredeti_igeny}'\nSZABÁLY: Vizsgáld meg a kódot! HA HIBÁT TALÁLSZ, dobd vissza! Soha ne engedj át teszteletlen kódot.\n[DOKUMENTÁCIÓ]\n{projekt_memoria}\n[ELŐZMÉNYEK]\n{recent_history}\nLegutóbbi üzenet: {kerdes}\nA te válaszod:"""
    else: # SM
        task_template = """Feladatod: Scrum Master.\nEredeti ügyféligény: '{eredeti_igeny}'\nSZABÁLY: CSAK akkor írd be a [LEZÁRVA] szót, ha a kód kész ÉS a QA rábólintott!\n[DOKUMENTÁCIÓ]\n{projekt_memoria}\n[ELŐZMÉNYEK]\n{recent_history}\nA te moderálásod:"""

    prompt = PromptTemplate(input_variables=["projekt_memoria", "recent_history", "kerdes", "eredeti_igeny"], template=base_template + task_template)
    return prompt | llm