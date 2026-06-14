# ui_components.py
import streamlit as st

class SprintStatusManager:
    def __init__(self, max_rounds, min_rounds):
        self.max_rounds = max_rounds
        self.min_rounds = min_rounds
        self.progress_bar = st.progress(0.0, text="🚀 Sprint előkészítése...")
        self.active_agent_container = st.empty()

    def update_round(self, current_round):
        szazalek = float(current_round) / float(self.max_rounds)
        szoveg = f"🏃‍♂️ Sprint Állapota: {current_round + 1}. iteráció / Maximum {self.max_rounds} (Kötelező minimum: {self.min_rounds})"
        self.progress_bar.progress(szazalek, text=szoveg)

    def set_active_agent(self, avatar, agent_name, status_text):
        self.active_agent_container.info(f"{avatar} **{agent_name}** {status_text}...")

    def set_system_action(self, action_text):
        self.active_agent_container.warning(f"⚙️ **Rendszer:** {action_text}...")

    def finish_success(self):
        self.progress_bar.progress(1.0, text="✅ Sprint sikeresen lezárva! Forráskód leszállítva.")
        self.active_agent_container.success("🎉 A feladat teljesítve és elmentve a JSON projekt memóriába!")

    def finish_timebox(self):
        self.progress_bar.progress(1.0, text="⚠️ Sprint időkerete (Timebox) lejárt!")
        self.active_agent_container.error("⌛ A csapat nem jutott dűlőre a megadott iterációk alatt.")
        
    def show_enforced_rule_warning(self, current_round):
        hatralevo = self.min_rounds - (current_round + 1)
        self.active_agent_container.error(f"⚠️ Felülbírálat! A Scrum Master lezárta volna a ticketet, de még {hatralevo} kötelező kód-review iteráció hátravan.")


def render_telemetry_dashboard(telemetria, reszletes_nezet=False):
    """Telemetria megjelenítése a kapott nézet-paraméter alapján."""
    if not telemetria:
        st.info("📊 Még nincsenek telemetriai adatok. Indítsd el a folyamatot!")
        return

    osszes_ido = max(0.001, telemetria.get('osszes_ido', 0.0))
    osszes_token = max(1, telemetria.get('osszes_token', 0))
    
    # Blended árak kiszámítása (USD)
    gpt_usd = (osszes_token / 1_000_000) * 7.50
    claude_usd = (osszes_token / 1_000_000) * 9.00
    llama_usd = (osszes_token / 1_000_000) * 5.00
    gemini_usd = (osszes_token / 1_000_000) * 0.35

    agensek = telemetria.get('agensek', {})
    szinek = {
        "PO": "#3b82f6", "BA": "#10b981", "UX": "#8b5cf6", "IT": "#f59e0b",
        "QA": "#ef4444", "SM": "#14b8a6", "Rendszer (Admin)": "#64748b", "Viselkedéskutató Lab": "#ec4899"
    }

    if not reszletes_nezet:
        # ==========================================
        # 1. KOMPAKT (LEBEGŐ) NÉZET
        # ==========================================
        c_ido, c_tok, c_gpt, c_claude, c_llama, c_gemini = st.columns(6)
        
        c_ido.metric("⏱️ Idő", f"{osszes_ido:.1f} s")
        c_tok.metric("🪙 Fogyasztás", f"{osszes_token:,}")
        c_gpt.metric("💰 GPT-4o", f"${gpt_usd:.4f}")
        c_claude.metric("💰 Claude 3.5", f"${claude_usd:.4f}")
        c_llama.metric("💰 Llama 3.1", f"${llama_usd:.4f}")
        c_gemini.metric("💸 Gemini 1.5", f"${gemini_usd:.4f}")

        if agensek:
            token_bars = ""
            legend = ""
            for agens_nev, adatok in agensek.items():
                szin = szinek.get(agens_nev, "#9ca3af")
                t_pct = (adatok['token'] / osszes_token) * 100
                if t_pct > 0:
                    token_bars += f'<div style="width: {t_pct}%; background-color: {szin}; height: 100%; float: left;" title="{agens_nev}: {t_pct:.1f}% ({adatok["token"]} tkn)"></div>'
                legend += f'<span style="margin-right: 12px; font-size: 11px; white-space: nowrap;"><span style="display: inline-block; width: 8px; height: 8px; background-color: {szin}; border-radius: 50%; margin-right: 4px;"></span>{agens_nev}</span>'
            
            st.markdown(f"""
            <div style="width: 100%; height: 8px; background-color: #f3f4f6; border-radius: 4px; overflow: hidden; display: flex; margin-bottom: 4px; margin-top: -10px;">
                {token_bars}
            </div>
            <div style='display: flex; flex-wrap: wrap; margin-bottom: 0px;'>{legend}</div>
            """, unsafe_allow_html=True)

    else:
        # ==========================================
        # 2. LEGACY (RÉSZLETES) NÉZET
        # ==========================================
        col1, col2 = st.columns(2)
        col1.metric("Összes Számítási Idő", f"{osszes_ido:.1f} másodperc")
        col2.metric("Összes Felhasznált Token", f"{osszes_token:,} db")
        
        st.markdown("#### 💵 Becsült Felhős API Költségek (SaaS alternatívák)")
        c_gpt, c_claude, c_llama, c_gemini = st.columns(4)
        
        c_gpt.metric("GPT-4o (OpenAI)", f"${gpt_usd:.4f}", f"{gpt_usd * 365:.2f} Ft")
        c_claude.metric("Claude 3.5 Sonnet", f"${claude_usd:.4f}", f"{claude_usd * 365:.2f} Ft")
        c_llama.metric("Llama 3.1 405B", f"${llama_usd:.4f}", f"{llama_usd * 365:.2f} Ft")
        c_gemini.metric("Gemini 1.5 Flash", f"${gemini_usd:.4f}", f"{gemini_usd * 365:.2f} Ft")

        if agensek:
            token_bars = ""
            ido_bars = ""
            legend = ""

            for agens_nev, adatok in agensek.items():
                szin = szinek.get(agens_nev, "#9ca3af")
                t_pct = (adatok['token'] / osszes_token) * 100
                i_pct = (adatok['ido'] / osszes_ido) * 100

                if t_pct > 0:
                    token_bars += f'<div style="width: {t_pct}%; background-color: {szin}; height: 100%; float: left;" title="{agens_nev}: {t_pct:.1f}% ({adatok["token"]} tkn)"></div>'
                if i_pct > 0:
                    ido_bars += f'<div style="width: {i_pct}%; background-color: {szin}; height: 100%; float: left;" title="{agens_nev}: {i_pct:.1f}% ({adatok["ido"]:.1f}s)"></div>'
                
                legend += f'<span style="margin-right: 15px; font-size: 14px; white-space: nowrap;"><span style="display: inline-block; width: 12px; height: 12px; background-color: {szin}; border-radius: 50%; margin-right: 5px; transform: translateY(1px);"></span>{agens_nev}</span>'

            st.markdown("#### 📈 Erőforrás-eloszlás aránya")
            st.markdown(f"<div style='margin-bottom: 10px; display: flex; flex-wrap: wrap;'>{legend}</div>", unsafe_allow_html=True)
            
            st.markdown(f"""
            <div style="margin-bottom: 4px; font-size: 14px; color: #4b5563;"><strong>Token felhasználás (%):</strong></div>
            <div style="width: 100%; height: 24px; background-color: #f3f4f6; border-radius: 6px; overflow: hidden; display: flex; border: 1px solid #e5e7eb; box-shadow: inset 0 1px 2px rgba(0,0,0,0.05);">
                {token_bars}
            </div>
            """, unsafe_allow_html=True)

            st.markdown(f"""
            <div style="margin-top: 12px; margin-bottom: 4px; font-size: 14px; color: #4b5563;"><strong>Számítási idő (%):</strong></div>
            <div style="width: 100%; height: 24px; background-color: #f3f4f6; border-radius: 6px; overflow: hidden; display: flex; border: 1px solid #e5e7eb; box-shadow: inset 0 1px 2px rgba(0,0,0,0.05);">
                {ido_bars}
            </div>
            <br>
            """, unsafe_allow_html=True)

            st.markdown("**🤖 Részletes bontás ágensenként:**")
            cols_per_row = 4
            agensek_listaja = list(agensek.items())
            
            for i in range(0, len(agensek_listaja), cols_per_row):
                sor_agensek = agensek_listaja[i:i+cols_per_row]
                cols = st.columns(len(sor_agensek))
                for j, (agens_nev, adatok) in enumerate(sor_agensek):
                    cols[j].metric(agens_nev, f"{adatok['token']} tkn", f"{adatok['ido']:.1f}s", delta_color="off")