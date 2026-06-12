from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app_config import (
    LLM_BASE_URL, 
    LLM_API_KEY, 
    LLM_TEMPERATURE_BASE, 
    LLM_TEMPERATURE_LOW, 
    LLM_TEMPERATURE_HIGH)

class AgentFactory:
    def __init__(self, model_name):
        self.model_name = model_name

    def _get_llm(self, temperature=LLM_TEMPERATURE_BASE):
        return ChatOpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, model=self.model_name, temperature=temperature)

    def generate_profile(self, role_description):
        llm = self._get_llm(LLM_TEMPERATURE_LOW)
        prompt = PromptTemplate(input_variables=["role"], template="Készíts 3 mondatos leírást a karakterről: '{role}'. Csak a leírást írd.")
        return (prompt | llm | StrOutputParser()).invoke({"role": role_description})

    def refine_profile(self, current_profile, role_name, round_num):
        llm = self._get_llm(LLM_TEMPERATURE_HIGH)
        prompt = PromptTemplate(
            input_variables=["role_name", "current_profile", "round_num"],
            template="Te egy szociológus vagy. Finomítsd az alábbi profilt a {round_num}. iterációban. Szerep: {role_name}. Jelenlegi: {current_profile}. Adj hozzá kognitív torzításokat és rejtett motivációkat. Csak a profilt írd le!"
        )
        return (prompt | llm | StrOutputParser()).invoke({"role_name": role_name, "current_profile": current_profile, "round_num": round_num})

    def get_agent_chain(self, role_key, persona_profile):
        llm = self._get_llm(LLM_TEMPERATURE_BASE)
        base_template = f"Te az alábbi mélypszichológiai profillal rendelkezel. Éld bele magad a szerepbe:\n---\n{persona_profile}\n---\n"
        
        templates = {
            "PO": """Feladatod: Product Owner (PO).
Eredeti ügyféligény: '{eredeti_igeny}'
SZABÁLY: A kód sosem tökéletes elsőre! Követelj forráskódot. Ne elégedj meg tervekkel!
[HIVATALOS PROJEKT DOKUMENTÁCIÓ]: {projekt_memoria}
[KÖZVETLEN ELŐZMÉNYEK]: {recent_history}
Legutóbbi üzenet: {kerdes}
A te válaszod (PO-ként):""",
            "IT": """Feladatod: Informatikus.
Eredeti ügyféligény: '{eredeti_igeny}'
SZABÁLY: Gépeld be a TÉNYLEGES FORRÁSKÓDOT! Ne csak beszélj róla.
[HIVATALOS PROJEKT DOKUMENTÁCIÓ]: {projekt_memoria}
[KÖZVETLEN ELŐZMÉNYEK]: {recent_history}
Legutóbbi üzenet: {kerdes}
A te válaszod (Informatikusként):""",
            "SM": """Feladatod: Scrum Master (Moderátor).
Eredeti ügyféligény: '{eredeti_igeny}'
SZABÁBY: CSAK akkor írd be a [LEZÁRVA] szót, ha a letesztelt forráskód ténylegesen legépelve látszik a memóriában.
[HIVATALOS PROJEKT DOKUMENTÁCIÓ]: {projekt_memoria}
[KÖZVETLEN ELŐZMÉNYEK]: {recent_history}
A te moderálásod:"""
        }
        
        prompt = PromptTemplate(
            input_variables=["projekt_memoria", "recent_history", "kerdes", "eredeti_igeny"], 
            template=base_template + templates[role_key]
        )
        return prompt | llm | StrOutputParser()

    def update_memory_doc(self, current_doc, new_events):
        llm = self._get_llm(LLM_TEMPERATURE_LOW)
        prompt = PromptTemplate(
            input_variables=["jelenlegi_memoria", "uj_uzenetek"],
            template="""Te egy precíz szoftverfejlesztési adminisztrátor vagy. 
Frissítsd a projekt dokumentációját az új események alapján. Csak a tényeket, meghozott technikai döntéseket és a leszállított kódot őrizd meg!
JELENLEGI DOKUMENTÁCIÓ: {jelenlegi_memoria}
ÚJ ESEMÉNYEK: {uj_uzenetek}
Írd meg a frissített, letisztult dokumentációt:"""
        )
        return (prompt | llm | StrOutputParser()).invoke({"jelenlegi_memoria": current_doc, "uj_uzenetek": new_events})