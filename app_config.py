# app_config.py

# --- File Paths ---
MEMORIA_FAJL = "szimulacio_memoria.json"

# --- LLM Settings ---
LLM_BASE_URL = "http://localhost:1234/v1"
LLM_API_KEY = "lm-studio"
LLM_TEMPERATURE_BASE = 0.7
LLM_TEMPERATURE_LOW = 0.1
LLM_TEMPERATURE_HIGH = 0.8

# --- Agent Definitions ---
AGENT_ROLES = {
    "PO": "Product Owner",
    "IT": "Informatikus",
    "SM": "Scrum Master"
}

# --- Streamlit / UI Constants ---
MAIN_TITLE = "🧠 Vektormentes Agilis Szimulátor"

# --- State Keys ---
STATE_KEYS = {
    "projekt_memoria": "projekt_memoria",
    "po_persona": "po_persona",
    "it_persona": "it_persona",
    "sm_persona": "sm_persona",
    "uzenetek": "uzenetek",
    "eredeti_feladat": "eredeti_feladat",
    "last_user_input": "last_user_input"
}

# --- Operational Constants ---
MINIMUM_KOROK = 5 