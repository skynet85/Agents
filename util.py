# util.py
import re
import time
import streamlit as st
import streamlit.components.v1 as components
from ui_components import render_telemetry_dashboard

def extract_and_render_wireframe(text):
    """Kikeresi a HTML/Tailwind blokkot a UX válaszából, robusztus fallback logikával."""
    html_code = None
    
    # 1. Próba: Bármilyen markdown kódblokk (```html, ```tailwind, vagy csak ```)
    matches = re.findall(r'```[a-zA-Z]*\s*(.*?)\s*```', text, re.DOTALL)
    
    if matches:
        for m in matches:
            if "<div" in m.lower() or "<form" in m.lower() or "<nav" in m.lower():
                html_code = m
                break
        if not html_code and matches:
            html_code = max(matches, key=len)
    else:
        # 2. Próba (Fallback): Az LLM elfelejtette a ``` jeleket, és nyersen generált HTML-t
        match = re.search(r'(<div\b[^>]*>.*</div>)', text, re.DOTALL | re.IGNORECASE)
        if match:
            html_code = match.group(1)

    # 3. Renderelés, ha találtunk valamilyen UI kódot
    if html_code:
        with st.expander("🎨 UX/UI Drótváz Megtekintése", expanded=True):
            st.info("A UX Designer által generált élő drótváz:")
            components.html(html_code, height=600, scrolling=True)
            
        with open("utolso_drotvaz.html", "w", encoding="utf-8") as f:
            f.write(html_code)

def refresh_telemetry_ui(placeholder):
    """Újrarajzolja a telemetriát a megadott Streamlit placeholderbe."""
    if placeholder is not None:
        with placeholder.container():
            is_detailed = st.session_state.get("telemetry_toggle", False)
            render_telemetry_dashboard(st.session_state.telemetria, is_detailed)

def run_agent_with_telemetry(agent_name, chain, invoke_args, telemetry_placeholder=None):
    """Mérőműszerrel ellátott ágens futtatás, mely automatikusan frissíti a UI-t."""
    start_time = time.time()
    response = chain.invoke(invoke_args)
    elapsed_time = time.time() - start_time
    valasz_szoveg = response.content
    
    tokenek = response.response_metadata.get('token_usage', {}).get('total_tokens', 0) if hasattr(response, 'response_metadata') else 0

    if 'agensek' not in st.session_state.telemetria:
        st.session_state.telemetria['agensek'] = {}
    if agent_name not in st.session_state.telemetria['agensek']:
        st.session_state.telemetria['agensek'][agent_name] = {'ido': 0.0, 'token': 0}
        
    st.session_state.telemetria['agensek'][agent_name]['ido'] += elapsed_time
    st.session_state.telemetria['agensek'][agent_name]['token'] += tokenek
    st.session_state.telemetria['osszes_ido'] = st.session_state.telemetria.get('osszes_ido', 0.0) + elapsed_time
    st.session_state.telemetria['osszes_token'] = st.session_state.telemetria.get('osszes_token', 0) + tokenek

    # Ha átadtak UI konténert és nem a főmenüben vagyunk, azonnal frissítjük a számokat!
    if not st.session_state.get("menu_nezet", False) and telemetry_placeholder is not None:
        refresh_telemetry_ui(telemetry_placeholder)
        
    return valasz_szoveg