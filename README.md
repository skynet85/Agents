# 🧠 LLMOps Agilis Szimulátor

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-App-red.svg)
![LangChain](https://img.shields.io/badge/LangChain-Agents-green.svg)
![LLMOps](https://img.shields.io/badge/LLMOps-Telemetry-purple.svg)

Egy lokális, nagyvállalati szintű szoftverfejlesztési szimulációs környezet, amely **LLMOps** elvekre épülve modellezi egy agilis csapat működését. A rendszer képes üzleti igényekből specifikációt, működő UI/UX drótvázakat, forráskódot és tesztelési jegyzőkönyveket generálni, miközben valós időben monitorozza a lokális LLM (pl. Qwen 32B, Llama) erőforrás-felhasználását és megtakarításait.

---

## 🏗️ Architektúra és Fájlstruktúra

A projekt **Clean Architecture** elven alapul, ahol a felület, a memória, a logika és az analitika élesen el van különítve.

```text
/
├── app.py                  # Fő belépési pont, állapotgép, zárolások és a párhuzamos szimulációs ciklus
├── agents.py               # Ágens-logika, LangChain promptok, profil finomítás
├── memory_manager.py       # JSON-alapú memóriakezelés és telemetria nullázás
├── ui_components.py        # Lebegő (Sticky) LLMOps Dashboard és Sprint állapotjelzők
├── config.py               # Globális konfigurációk, alapértelmezett perszónák
└── szimulacio_memoria.json # Automatikusan generált, perzisztens adatbázis
```

---

## 🤖 A 6 Ágensből Álló Pipeline

A szimulátor az **SDLC (Software Development Life Cycle)** folyamatot követi. Az iterációk során az ágensek egymás kimenetére építenek, a tesztelési és tervezési fázisok pedig párhuzamosítva futhatnak:

* **👔 Product Owner (PO)**: Üzleti igények felmérése, prioritások és célok meghatározása.
* **📋 Business Analyst (BA)**: Technikai specifikáció, edge-case analízis és elfogadási kritériumok (Acceptance Criteria) kidolgozása.
* **🎨 UX/UI Designer**: HTML és Tailwind CSS alapú, futtatható drótvázak (Wireframes) generálása, amelyeket a Streamlit valós időben lerenderel.
* **💻 Informatikus (IT)**: Kód implementációja, szoftverarchitektúra tervezése és refaktorálás.
* **🔎 Manual QA**: A kód és a specifikáció összevetése, funkcionális- és hibatesztelés.
* **⏱️ Scrum Master (SM)**: A folyamat moderálása, felülbírálások kezelése, minimális kötelező vitakörök kikényszerítése és a sprint lezárása.

---

## 📊 Integrált LLMOps és Telemetria

A képernyő tetején rögzített (lebegő) dashboard valós idejű betekintést nyújt az erőforrás-menedzsmentbe.

* **Token- és Időmérés**: Ágensenkénti lebontás a számítási időkre és a felhasznált tokenekre.
* **SaaS Megtakarítás Kalkulátor**: A lokális futtatás költséghatékonyságának validálása. A rendszer automatikusan átszámolja a generált volument a legnépszerűbb felhős modellek (GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Flash, Llama 3.1 405B) aktuális blended API áraira.
* **Vizuális Sávdiagramok**: Kompakt és részletes (legacy) nézet a terheléseloszlás HTML/CSS alapú megjelenítéséhez.

---

## ⚙️ Fő Funkciók és Képességek

* **Párhuzamos Végrehajtás**: A `concurrent.futures` modul segítségével a rendszer képes aszinkron módon, párhuzamosan futtatni tesztelési vagy tervezési fázisokat, maximálisan kihasználva a rendelkezésre álló erőforrásokat.
* **Állapotgép (State Machine) és UI Zárolás**: A folyamat (Labor felépítése vagy Sprint futtatása) alatt a rendszer automatikusan inaktiválja a beviteli mezőket és gombokat (`felulet_zarolva` flag), így megakadályozza a véletlen kattintásokból eredő inkonzisztenciát és a memóriavesztést.
* **Intelligens Memóriakezelés**: Alkalmazás-újraindításkor a generált tudás és a projekt memória megmarad, de a telemetriai számlálók tiszta lappal (0-ról) indulnak.
* **Élő Drótváz Renderelés**: A Streamlit `components.html` integrációjának köszönhetően az AI által generált felülettervek azonnal interaktív formában jelennek meg az oldalon.

---

## 🚀 Telepítés és Futtatás

### Előfeltételek
* Python 3.10 vagy újabb.
* **LM Studio**: Egy lokálisan futó szerver (pl. Qwen 32B vagy Llama modellel) elindítva a `http://localhost:1234/v1` végponton.

### Lépések
1.  **Klónozd a tárolót**:
    ```bash
    git clone <repository_url>
    cd vas-simulator
    ```

2.  **Telepítsd a függőségeket**:
    ```bash
    pip install streamlit langchain-openai requests
    ```

3.  **Indítsd el a szimulátort**:
    ```bash
    streamlit run app.py
    ```

---

## 💡 Használati Útmutató
1.  Indítsd el a rendszert és válaszd ki a használni kívánt lokális modellt az oldalsávon.
2.  Nyomd meg a **Labor indítása** gombot, hogy a "Viselkedéskutató Lab" több iteráción keresztül felépítse és finomítsa a 6 ágens mélypszichológiai profilját.
3.  Miután a rendszer feloldotta a felületet, írd be a beviteli mezőbe az üzleti igényt (pl. *"Készítsünk egy bejelentkező képernyőt"*).
4.  Dőlj hátra, és figyeld, ahogy az ágensek lefolytatják a Sprintet, miközben a lebegő LLMOps panel méri a megtakarításaidat.

---
**Szerző:** Surányi Zsolt  
*Kifejlesztve lokális AI modellek (LM Studio) integrált, nagyvállalati szintű teszteléséhez és workflow automatizálásához.*
