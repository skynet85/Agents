# ui_components.py
"""Minden Streamlit megjelenítési logika: sprint-státusz, telemetria, sidebar."""
from __future__ import annotations

import html
from typing import Any, Dict, List

import streamlit as st

import config


# ---------------------------------------------------------------------------
# Sprint állapotjelző
# ---------------------------------------------------------------------------
class SprintStatusManager:
    def __init__(self, max_rounds: int, min_rounds: int) -> None:
        self.max_rounds = max(1, int(max_rounds))
        self.min_rounds = max(1, int(min_rounds))
        self.progress_bar = st.progress(0.0, text="🚀 Sprint előkészítése...")
        self.active_agent_container = st.empty()

    def update_round(self, current_round: int) -> None:
        # A Streamlit kivételt dob, ha az arány kilóg a [0, 1] tartományból.
        szazalek = min(1.0, max(0.0, float(current_round) / float(self.max_rounds)))
        szoveg = (
            f"🏃‍♂️ Sprint Állapota: {current_round + 1}. iteráció / "
            f"Maximum {self.max_rounds} (Kötelező minimum: {self.min_rounds})"
        )
        self.progress_bar.progress(szazalek, text=szoveg)

    def set_active_agent(self, avatar: str, agent_name: str, status_text: str) -> None:
        self.active_agent_container.info(f"{avatar} **{agent_name}** {status_text}...")

    def set_system_action(self, action_text: str) -> None:
        self.active_agent_container.warning(f"⚙️ **Rendszer:** {action_text}...")

    def finish_success(self) -> None:
        self.progress_bar.progress(1.0, text="✅ Sprint sikeresen lezárva! Forráskód leszállítva.")
        self.active_agent_container.success("🎉 A feladat teljesítve és elmentve a JSON projekt memóriába!")

    def finish_timebox(self) -> None:
        self.progress_bar.progress(1.0, text="⚠️ Sprint időkerete (Timebox) lejárt!")
        self.active_agent_container.error("⌛ A csapat nem jutott dűlőre a megadott iterációk alatt.")

    def finish_error(self, uzenet: str) -> None:
        self.progress_bar.progress(1.0, text="❌ A sprint hiba miatt megszakadt.")
        self.active_agent_container.error(uzenet)

    def show_enforced_rule_warning(self, current_round: int) -> None:
        hatralevo = max(0, self.min_rounds - (current_round + 1))
        self.active_agent_container.error(
            "⚠️ Felülbírálat! A Scrum Master lezárta volna a ticketet, de még "
            f"{hatralevo} kötelező kód-review iteráció hátravan."
        )


# ---------------------------------------------------------------------------
# Telemetria dashboard
# ---------------------------------------------------------------------------
def _szin(agens_nev: str) -> str:
    return config.AGENS_SZINEK.get(agens_nev, config.ALAPERTELMEZETT_SZIN)


def _sav(szazalek: float, szin: str, cim: str) -> str:
    return (
        f'<div style="width: {szazalek:.4f}%; background-color: {szin}; height: 100%; '
        f'float: left;" title="{html.escape(cim, quote=True)}"></div>'
    )


def _jelmagyarazat(agens_nev: str, szin: str, meret: int) -> str:
    pont = meret
    return (
        f'<span style="margin-right: 12px; font-size: {meret + 3}px; white-space: nowrap;">'
        f'<span style="display: inline-block; width: {pont}px; height: {pont}px; '
        f'background-color: {szin}; border-radius: 50%; margin-right: 4px;"></span>'
        f"{html.escape(agens_nev)}</span>"
    )


def _saas_koltsegek(osszes_token: int) -> Dict[str, float]:
    return {nev: (osszes_token / 1_000_000) * ar for nev, ar in config.SAAS_ARAK.items()}


def render_telemetry_dashboard(telemetria: Dict[str, Any], reszletes_nezet: bool = False) -> None:
    """Telemetria megjelenítése a kapott nézet-paraméter alapján."""
    if not telemetria or not telemetria.get("agensek"):
        st.info("📊 Még nincsenek telemetriai adatok. Indítsd el a folyamatot!")
        return

    # Nullosztás elleni védelem; a megjelenített értékek a nyers adatból jönnek.
    osszes_ido_nyers = float(telemetria.get("osszes_ido", 0.0) or 0.0)
    osszes_token_nyers = int(telemetria.get("osszes_token", 0) or 0)
    ido_oszto = max(0.001, osszes_ido_nyers)
    token_oszto = max(1, osszes_token_nyers)

    koltsegek = _saas_koltsegek(osszes_token_nyers)
    agensek = telemetria.get("agensek", {}) or {}

    if not reszletes_nezet:
        # ---------------- KOMPAKT (LEBEGŐ) NÉZET ----------------
        oszlopok = st.columns(2 + len(koltsegek))
        oszlopok[0].metric("⏱️ Idő", f"{osszes_ido_nyers:.1f} s")
        oszlopok[1].metric("🪙 Fogyasztás", f"{osszes_token_nyers:,}")
        for oszlop, (nev, usd) in zip(oszlopok[2:], koltsegek.items()):
            oszlop.metric(f"💰 {nev}", f"${usd:.4f}")

        token_bars, legend = "", ""
        for agens_nev, adatok in agensek.items():
            szin = _szin(agens_nev)
            token = int(adatok.get("token", 0) or 0)
            t_pct = (token / token_oszto) * 100
            if t_pct > 0:
                token_bars += _sav(t_pct, szin, f"{agens_nev}: {t_pct:.1f}% ({token} tkn)")
            legend += _jelmagyarazat(agens_nev, szin, 8)

        st.markdown(
            f"""
            <div style="width: 100%; height: 8px; background-color: #f3f4f6; border-radius: 4px;
                        overflow: hidden; display: flex; margin-bottom: 4px; margin-top: -10px;">
                {token_bars}
            </div>
            <div style='display: flex; flex-wrap: wrap; margin-bottom: 0px;'>{legend}</div>
            """,
            unsafe_allow_html=True,
        )
        return

    # ---------------- RÉSZLETES NÉZET ----------------
    col1, col2 = st.columns(2)
    col1.metric("Összes Számítási Idő", f"{osszes_ido_nyers:.1f} másodperc")
    col2.metric("Összes Felhasznált Token", f"{osszes_token_nyers:,} db")

    st.markdown("#### 💵 Becsült Felhős API Költségek (SaaS alternatívák)")
    ar_oszlopok = st.columns(len(koltsegek))
    for oszlop, (nev, usd) in zip(ar_oszlopok, koltsegek.items()):
        oszlop.metric(nev, f"${usd:.4f}")

    token_bars, ido_bars, legend = "", "", ""
    for agens_nev, adatok in agensek.items():
        szin = _szin(agens_nev)
        token = int(adatok.get("token", 0) or 0)
        ido = float(adatok.get("ido", 0.0) or 0.0)
        t_pct = (token / token_oszto) * 100
        i_pct = (ido / ido_oszto) * 100
        if t_pct > 0:
            token_bars += _sav(t_pct, szin, f"{agens_nev}: {t_pct:.1f}% ({token} tkn)")
        if i_pct > 0:
            ido_bars += _sav(i_pct, szin, f"{agens_nev}: {i_pct:.1f}% ({ido:.1f}s)")
        legend += _jelmagyarazat(agens_nev, szin, 11)

    st.markdown("#### 📈 Erőforrás-eloszlás aránya")
    st.markdown(
        f"<div style='margin-bottom: 10px; display: flex; flex-wrap: wrap;'>{legend}</div>",
        unsafe_allow_html=True,
    )
    for cim, savok in (("Token felhasználás (%)", token_bars), ("Számítási idő (%)", ido_bars)):
        st.markdown(
            f"""
            <div style="margin-top: 8px; margin-bottom: 4px; font-size: 14px; color: #4b5563;">
                <strong>{cim}:</strong></div>
            <div style="width: 100%; height: 24px; background-color: #f3f4f6; border-radius: 6px;
                        overflow: hidden; display: flex; border: 1px solid #e5e7eb;
                        box-shadow: inset 0 1px 2px rgba(0,0,0,0.05);">{savok}</div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("**🤖 Részletes bontás ágensenként:**")
    cols_per_row = 4
    agensek_listaja = list(agensek.items())
    for i in range(0, len(agensek_listaja), cols_per_row):
        sor = agensek_listaja[i : i + cols_per_row]
        cols = st.columns(len(sor))
        for j, (agens_nev, adatok) in enumerate(sor):
            cols[j].metric(
                agens_nev,
                f"{int(adatok.get('token', 0) or 0)} tkn",
                f"{float(adatok.get('ido', 0.0) or 0.0):.1f}s",
                delta_color="off",
            )


# ---------------------------------------------------------------------------
# Sidebar: ágens- és modellkonfiguráció
# ---------------------------------------------------------------------------
def _valid_index(ertek: str, opciok: List[str]) -> int:
    try:
        return opciok.index(ertek)
    except ValueError:
        return 0


def render_agent_configuration_ui(
    available_models: List[str], disabled_state: bool
) -> Dict[str, Any]:
    """Kirajzolja az ágens-konfigurációs sidebart és visszaadja a beállításokat."""
    st.sidebar.subheader("🤖 Ágensek és Modellek")

    if not available_models:
        available_models = ["local-model"]

    st.session_state.setdefault("utolso_fo_modell", "")

    # A widget-kulcsokat még a widgetek létrehozása ELŐTT normalizáljuk, hogy
    # egy korábban mentett, ma már nem elérhető modellnév ne dobjon kivételt.
    for kulcs in ["mod_Admin"] + [f"mod_{a['id']}" for a in st.session_state.dynamic_agents]:
        if st.session_state.get(kulcs) not in available_models:
            st.session_state[kulcs] = available_models[0]

    global_options = [""] + available_models
    fo_modell = st.sidebar.selectbox(
        "🌍 Fő Modell (Minden ágens örökli):",
        options=global_options,
        index=0,
        disabled=disabled_state,
        key="fo_modell_valaszto",
    )

    if fo_modell and fo_modell != st.session_state.utolso_fo_modell:
        st.session_state["mod_Admin"] = fo_modell
        for agens in st.session_state.dynamic_agents:
            st.session_state[f"mod_{agens['id']}"] = fo_modell
        st.session_state.utolso_fo_modell = fo_modell

    st.sidebar.divider()

    admin_modell = st.sidebar.selectbox(
        "⚙️ Viselkedéskutató / Admin (Nem törölhető):",
        options=available_models,
        key="mod_Admin",
        disabled=disabled_state,
    )
    beallitasok: Dict[str, Any] = {"Admin": admin_modell}

    st.sidebar.divider()
    st.sidebar.markdown("**🏃‍♂️ Sprint Résztvevők**")

    agents_to_remove = None
    for i, agens in enumerate(st.session_state.dynamic_agents):
        ag_id = agens["id"]
        with st.sidebar.expander(f"{agens['ikon']} {agens['nev']} ({ag_id})", expanded=False):
            mod = st.selectbox(
                "LLM Modell:", options=available_models, key=f"mod_{ag_id}", disabled=disabled_state
            )
            leiras = st.text_input(
                "Személyiség:", agens["leiras"], key=f"def_{ag_id}", disabled=disabled_state
            )
            szabaly = st.text_area(
                "Szabály (Prompt):", agens["szabaly"], key=f"rule_{ag_id}", disabled=disabled_state
            )
            beallitasok[ag_id] = {"modell": mod, "def": leiras, "szabaly": szabaly}

            if st.button(f"🗑️ {ag_id} Törlése", key=f"del_{ag_id}", disabled=disabled_state):
                agents_to_remove = i

    if agents_to_remove is not None:
        torolt = st.session_state.dynamic_agents.pop(agents_to_remove)
        st.session_state.ertekelesek.pop(torolt["id"], None)
        # A törölt ágenshez tartozó widget-állapotokat is takarítjuk.
        for prefix in ("mod_", "def_", "rule_", "del_"):
            st.session_state.pop(f"{prefix}{torolt['id']}", None)
        st.session_state.pop(f"{torolt['id']}_persona", None)
        st.rerun()

    st.sidebar.divider()

    with st.sidebar.expander("➕ Új Ágens Hozzáadása", expanded=False):
        with st.form("uj_agens_form", clear_on_submit=True):
            uj_id = st.text_input("Rövid ID (pl. SEC, DBA):")
            uj_ikon = st.text_input("Ikon (emoji):", "👤")
            uj_nev = st.text_input("Szerepkör (pl. Security Expert):")
            uj_leiras = st.text_input("Személyiség/Profil:")
            uj_akcio = st.text_input("Akció leírása (pl. kódot auditál):")
            uj_szabaly = st.text_area("Szabály (Prompt utasítás):")

            if st.form_submit_button("Hozzáadás", disabled=disabled_state):
                uj_id_upper = (uj_id or "").strip().upper()
                letezo_idk = {a["id"] for a in st.session_state.dynamic_agents}
                if not uj_id_upper or not uj_nev.strip():
                    st.warning("Az ID és a Szerepkör megadása kötelező!")
                elif uj_id_upper in letezo_idk or uj_id_upper == "ADMIN":
                    st.warning(f"A(z) '{uj_id_upper}' azonosító már foglalt!")
                else:
                    st.session_state.dynamic_agents.append(
                        {
                            "id": uj_id_upper,
                            "ikon": uj_ikon or "👤",
                            "nev": uj_nev.strip(),
                            "leiras": uj_leiras,
                            "akcio": uj_akcio or "dolgozik",
                            "szabaly": uj_szabaly,
                        }
                    )
                    st.session_state.ertekelesek[uj_id_upper] = 0
                    st.rerun()

    return beallitasok
