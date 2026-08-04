# telemetry_dashboard.py
"""Önálló Streamlit app az OpenTelemetry trace-ek elemzésére.

Indítás:  streamlit run telemetry_dashboard.py
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

import config

st.set_page_config(page_title="OpenTelemetry Elemző", page_icon="📊", layout="wide")

OSZLOPOK = ["Trace ID", "Ügynök", "Időtartam (s)", "Tokenek", "Prompt / Kérdés", "Eredeti Igény"]


def load_traces(filepath: Path) -> List[Dict[str, Any]]:
    """Robusztus parser a folyamatosan hozzáfűzött OTel JSON objektumokhoz."""
    if not filepath.exists():
        return []

    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        st.error(f"Hiba a fájl olvasásakor: {exc}")
        return []

    traces: List[Dict[str, Any]] = []
    decoder = json.JSONDecoder()
    idx, hossz = 0, len(content)

    while idx < hossz:
        while idx < hossz and content[idx].isspace():
            idx += 1
        if idx >= hossz:
            break
        try:
            obj, vege = decoder.raw_decode(content, idx)
        except json.JSONDecodeError:
            # Sérült/félbevágott rekord: átugrunk a következő sorkezdetre.
            kovetkezo = content.find("\n{", idx)
            if kovetkezo == -1:
                break
            idx = kovetkezo + 1
            continue
        if isinstance(obj, dict):
            traces.append(obj)
        idx = vege

    return traces


def _szam(ertek: Any, tipus, alap):
    try:
        return tipus(ertek)
    except (TypeError, ValueError):
        return alap


def traces_to_dataframe(traces: List[Dict[str, Any]]) -> pd.DataFrame:
    sorok = []
    for t in traces:
        attrs = t.get("attributes") or {}
        ctx = t.get("context") or {}
        trace_id = str(ctx.get("trace_id") or "N/A")
        sorok.append(
            {
                "Trace ID": trace_id[-8:],
                "Ügynök": attrs.get("llm.agent.name") or "Ismeretlen",
                "Időtartam (s)": _szam(attrs.get("llm.duration_seconds"), float, 0.0),
                "Tokenek": _szam(attrs.get("llm.usage.total_tokens"), int, 0),
                "Prompt / Kérdés": str(attrs.get("llm.task.query") or ""),
                "Eredeti Igény": str(attrs.get("llm.task.original_need") or ""),
            }
        )
    return pd.DataFrame(sorok, columns=OSZLOPOK)


def main() -> None:
    st.title("📊 Saját OpenTelemetry Dashboard")
    st.markdown(
        f"Ez a felület a `{config.TRACE_FAJL.name}` fájlba mentett nyomkövetési "
        "(Trace) adatokat elemzi."
    )

    if st.button("🔄 Adatok Frissítése", type="primary"):
        st.rerun()

    df = traces_to_dataframe(load_traces(config.TRACE_FAJL))

    if df.empty:
        st.warning(
            f"Még nem található adat a `{config.TRACE_FAJL.name}` fájlban. "
            "Futtass le egy ágenst a fő alkalmazásban!"
        )
        return

    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Összes Naplózott Futtatás", f"{len(df)} db")
    m2.metric("Összes Felhasznált Token", f"{int(df['Tokenek'].sum()):,}")
    m3.metric("Átlagos Válaszidő", f"{df['Időtartam (s)'].mean():.2f} s")
    m4.metric("Összes Számítási Idő", f"{df['Időtartam (s)'].sum():.1f} s")

    st.divider()
    st.subheader("📈 Erőforrás-felhasználás Ágensenként")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Összes Token Fogyasztás (Ügynökönként)**")
        st.bar_chart(
            df.groupby("Ügynök")["Tokenek"].sum().reset_index(), x="Ügynök", y="Tokenek", color="#10b981"
        )
    with c2:
        st.markdown("**Átlagos Válaszidő Másodpercben (Ügynökönként)**")
        st.bar_chart(
            df.groupby("Ügynök")["Időtartam (s)"].mean().reset_index(),
            x="Ügynök",
            y="Időtartam (s)",
            color="#3b82f6",
        )

    st.divider()
    st.subheader("📝 Részletes Trace Eseménynapló")

    search = st.text_input("🔍 Keresés a promptokban vagy ügynök nevében:")
    filtered_df = df
    if search:
        # regex=False: a felhasználó által beírt speciális karakterek ne dobjanak kivételt.
        maszk = df["Prompt / Kérdés"].str.contains(search, case=False, na=False, regex=False) | df[
            "Ügynök"
        ].str.contains(search, case=False, na=False, regex=False)
        filtered_df = df[maszk]

    if filtered_df.empty:
        st.info("Nincs a keresésre illeszkedő trace.")
        return

    st.dataframe(
        filtered_df[["Trace ID", "Ügynök", "Időtartam (s)", "Tokenek", "Prompt / Kérdés"]],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("🕵️ Mélyebb Elemzés (Kattints a részletekért)")
    # A megjelenítést limitáljuk: több ezer expander megfagyasztaná a böngészőt.
    LIMIT = 100
    if len(filtered_df) > LIMIT:
        st.caption(f"A legutóbbi {LIMIT} trace látszik a(z) {len(filtered_df)} találatból.")

    for _, row in filtered_df.tail(LIMIT).iloc[::-1].iterrows():
        cim = (
            f"{row['Ügynök']} futtatása ({row['Tokenek']} token, "
            f"{row['Időtartam (s)']:.1f} sec) - Trace: {row['Trace ID']}"
        )
        with st.expander(cim):
            st.markdown("**Kapott Eredeti Ügyféligény:**")
            st.info(row["Eredeti Igény"] or "(nincs adat)")
            st.markdown("**LLM-nek küldött pontos bemenet (Context + Prompt):**")
            st.code(row["Prompt / Kérdés"] or "(nincs adat)", language="text")


if __name__ == "__main__":
    main()
