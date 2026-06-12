import streamlit as st
from app_config import STATE_KEYS
from storage import MemoryManager
from agents import AgentFactory

class SimulationEngine:
    def __init__(self, model_name):
        self.factory = AgentFactory(model_name)
        self.storage = MemoryManager()

    def run_iteration(self, current_round, config_params):
        """Runs one full cycle: PO -> IT -> SM"""
        mem = st.session_state.projekt_memoria
        igeny = st.session_state.eredeti_feladat
        history_str = self._format_history()

        # 1. PO Step
        po_chain = self.factory.get_agent_chain("PO", st.session_state.po_persona)
        po_res = po_chain.invoke({"projekt_memoria": mem, "recent_history": history_str, "kerdes": st.session_state.last_user_input, "eredeti_igeny": igeny})
        self._log_message("PO", "Product Owner", "👔", po_res)

        # 2. IT Step
        it_chain = self.factory.get_agent_chain("IT", st.session_state.it_persona)
        it_res = it_chain.invoke({"projekt_memoria": mem, "recent_history": self._format_history(), "kerdes": po_res, "eredeti_igeny": igeny})
        self._log_message("IT", "Informatikus", "💻", it_res)

        # 3. SM Step
        sm_chain = self.factory.get_agent_chain("SM", st.session_state.sm_persona)
        sm_res = sm_chain.invoke({"projekt_memoria": mem, "recent_history": self._format_history(), "kerdes": "Értékeld a helyzetet!", "eredeti_igeny": igeny})
        self._log_message("SM", "Scrum Master", "⏱️", sm_res)

        # 4. Update Memory
        new_events = f"PO: {po_res}\nIT: {it_res}\nSM: {sm_res}"
        st.session_state.projekt_memoria = self.factory.update_memory_doc(mem, new_events)
        self.storage.save_memory(st.session_state.projekt_memoria)

        return sm_res

    def _log_message(self, role_key, name, avatar, text):
        st.session_state.uzenetek.append({"szerep": role_key, "szerep_nev": name, "avatar": avatar, "szoveg": text})

    def _format_history(self):
        return "".join([f"{m['szerep_nev']}: {m['szoveg']}\n" for m in st.session_state.uzenetek[-3:]])