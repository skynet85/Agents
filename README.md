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
├── app.py                  # Belépési pont, nézetek, állapotgép-vezérlés
├── sprint_engine.py        # A sprint állapotgépe és a védőkorlát – Streamlit-független
├── agents.py               # LangChain láncok és promptok (nem importál Streamlitet)
├── ui_components.py        # MINDEN Streamlit UI: dashboard, sprint-státusz, sidebar
├── memory_manager.py       # Atomikus, JSON-alapú perzisztencia
├── github_integration.py   # Kód-kinyerés és publikálás GitHubra (egy commitban)
├── scaffold.py             # RÖGZÍTETT PROJEKTVÁZ – védett, verzió-pinnelt build-konfigok
├── workspace.py            # VirtualWorkspace: a projekt élő fájlfája (patch-szemantika)
├── sandbox.py              # Valódi build (Docker/lokális) — az igazságforrás
├── project_doctor.py       # Build-blokkolók diagnózisa és determinisztikus javítása
├── code_analysis.py        # Valódi fájlnév kikövetkeztetése a kód tartalmából
├── jenkins_repair.py       # Jenkinsfile validálás és automatikus javítás
├── telemetry_setup.py      # OpenTelemetry provider + flush/rotáció
├── telemetry_dashboard.py  # Önálló Streamlit app a trace-ek elemzésére
├── util.py                 # Drótváz-kinyerés, telemetriás ágensfuttatás
├── config.py               # Globális konfiguráció, útvonalak, alapértelmezett ágensek
├── requirements.txt        # Függőségek
└── tests/                  # Streamlit- és hálózatfüggetlen regressziós tesztek
```

Futásidőben generált (a `.gitignore` kizárja): `szimulacio_memoria.json`, `opentelemetry_traces.json`, `utolso_drotvaz.html`.

---

## 🤖 A 7 Ágensből Álló Pipeline

A szimulátor az **SDLC (Software Development Life Cycle)** folyamatot követi. Az iterációk során az ágensek egymás kimenetére építenek:

* **👔 Product Owner (PO)**: Üzleti igények felmérése, prioritások és célok meghatározása.
* **📋 Business Analyst (BA)**: Technikai bontás és **API-szerződés** (endpoint, mezők) — a FE és a BE ebből dolgozik. (A build-stacket NEM tervezi, az zárolt.)
* **🎨 UX/UI Designer**: HTML és Tailwind CSS alapú, futtatható drótvázak generálása, amelyeket a Streamlit valós időben lerenderel.
* **💻 Informatikus (IT)**: **Az alkalmazáskód** implementációja (komponensek, service-ek, controllerek). A build-konfigurációt a rögzített váz adja.
* **🔎 Manual QA**: Azt vizsgálja, hogy az alkalmazás **működik-e** — a frontend tényleg hívja-e a backendet, nem placeholder-e az `App.tsx`. (A build-configot nem kéri számon.)
* **🏗️ DevOps Engineer (DO)**: A deploy szöveges véleményezése. **A Jenkinsfile-t a rendszer determinisztikusan generálja**, nem az ágens.
* **⏱️ Scrum Master (SM)**: A folyamat moderálása, felülbírálások kezelése, minimális kötelező vitakörök kikényszerítése és a sprint lezárása.

Az ágensek a felületen menet közben hozzáadhatók és törölhetők. A szerepek a stabilitási stratégiához igazodnak (lásd a *Rögzített váz* és a *DOKUMENTACIO.md* fejezeteit).

---

## 📁 VirtualWorkspace — a projekt mint élő fájlfa

Korábban a „projekt" nem létezett önálló entitásként: a repó tartalma csak a GitHub-push pillanatában állt össze a chat-üzenetekből. Ennek két mért következménye volt:

* **Ütköző Spring bean.** Az 1. iteráció a `com.malom.engine.MatchEngine`, a 3. a `com.malom.service.MatchEngine` osztályt hozta létre — mindkettő `@Service`, mindkettőből `matchEngine` bean-név → `ConflictingBeanDefinitionException` → a context el sem indult.
* **117 duplikált kódblokk**, mert az IT ágens minden körben újragenerálta a teljes kódbázist — nem tudta, mit írt már meg.

Most a projekt egy élő `útvonal → tartalom` leképezés, amit minden ágensválasz **patchel**:

* az ágens promptjába bekerül az **aktuális fájlfa**, így csak a ténylegesen változó fájlt írja ki;
* `DELETE: <útvonal>` és `MOVE: <régi> -> <új>` direktívák;
* **automatikus névütközés-feloldás** — ha egy későbbi iteráció máshova teszi ugyanazt a `@Service` osztályt, a régi törlődik;
* **statikus konzisztencia-ellenőrzés** a fordítás előtt: package/könyvtár egyezés, több belépési pont, feloldatlan relatív importok, hiányzó build-leírók.

A felületen a *📁 Projekt fájlfa* panel mutatja az állapotot és a talált problémákat; minden ágenslépés után látszik a fájlváltozások listája.

> Valós futáson mérve: **48 chat-üzenet → 18 fájl**, ütköző bean nélkül.

---

## 🧱 Rögzített váz — a build-stabilitás alapja

**Ez a projekt legfontosabb tervezési döntése.**

Korábban az LLM nem csak az alkalmazáskódot írta, hanem a teljes build-infrastruktúrát is (`package.json`, `tsconfig.json`, `vite.config.ts`, `tailwind.config.js`, `index.html`, `pom.xml`, `Jenkinsfile`). Ez a rész minden futásban más lett, és minden futásban **máshol** tört el:

| Build | Hibaok |
|---|---|
| korábbi | `"@tailwindcss/vite": "^3.4.0"` — nem létező verzió → `npm install` ETARGET |
| #22 | `local max_retries=30` a health checkben → dash: `local: not in a function` |
| #24 | `@apply animate-in` a `tailwindcss-animate` plugin nélkül → PostCSS hiba |

A hibák egyenkénti javítása fogócska volt: minden folt után a modell máshol hallucinált. A megoldás nem újabb javítószabály, hanem hogy **elvesszük tőle ezt a felelősséget**.

### Hogyan működik

A `scaffold.py` egy verzió-pinnelt, ismerten működő vázat ad:

* **Frontend:** React 18 + Vite 5 + TypeScript + Tailwind 3 (a `tailwindcss-animate` pluginnal, ami a #24-et okozta)
* **Backend:** Spring Boot 3.2 + Java 17, alapcsomag `com.app`, CORS-konfiggal
* **CI/CD:** determinisztikusan generált Jenkinsfile

Ezek az útvonalak **védettek**. Ha az ágens ilyet generál, a rendszer eldobja és naplózza (`⛔` jelzéssel a fájlváltozásoknál). Az ágensek csak a „slotokba" dolgoznak: komponensek, oldalak, store-ok, controllerek, service-ek.

További védelmek:

* **Függőség-allowlist.** Új npm csomag csak `DEPENDENCY: <név>` direktívával kérhető, kizárólag engedélyezett listáról, **rögzített verzióval** — az ágens nem tud verziószámot kitalálni.
* **CSS `@apply` szűrés.** A Tailwind legtörékenyebb funkciója; egyetlen ismeretlen utility-név megállítja a buildet. Az ágensek a JSX `className`-be írják az utility osztályokat, ott érintetlen marad minden.
* **Egyetlen Spring belépési pont.** A második `@SpringBootApplication` osztály elutasításra kerül.

### Mérés

A `tests/test_scaffold.py` az összes korábbi valós bukást megpróbálja előidézni — egyik sem jut át. Egy „rosszul viselkedő" ágenst szimuláló teszt 3 iteráción át küld kitalált verziót, `@apply`-t, csonka `pom.xml`-t és `local`-os pipeline-t: a projekt végig build-képes marad, a valódi alkalmazáskód viszont bekerül.

> Az öt legutóbbi mentett futáson visszamérve: **0 build-blokkoló**, érvényes Jenkinsfile mindegyiknél.

---

## 🩺 Build-képesség — „építhető-e ebből a Jenkins?"

A Jenkinsfile javítása és a fordítási visszacsatolás nem segít, ha **maga a projekt** nem építhető. A valós futás elemzése öt olyan blokkolót mutatott ki, amely az `npm install` vagy a `tsc -b` első másodpercében megöli a buildet:

| Blokkoló | Mi történt | Javítás |
|---|---|---|
| **Nem létező függőség-verzió** | `"@tailwindcss/vite": "^3.4.0"` — ez a csomag csak 4.x-től létezik → `npm install` **ETARGET**, a frontend build el sem indul | eltávolítás a `package.json`-ból és a `vite.config`-ból |
| **Kevert Tailwind-setup** | egyszerre v4-es `@tailwindcss/vite` és v3-as `tailwindcss` + `postcss`, config viszont sehol | egységes v3 lánc: `tailwind.config.js` + `postcss.config.js` generálása |
| **Lógó tsconfig-hivatkozás** | `references: [{ "path": "./tsconfig.node.json" }]`, de a fájl nem létezik → `tsc -b` **error TS6053** | a hiányzó fájl létrehozása (vagy a hivatkozás eltávolítása) |
| **CI-t törő stílusszabály** | `noUnusedLocals` + `noUnusedParameters` — LLM-kódnál egyetlen felesleges import is piros build | kikapcsolás |
| **Port-eltérés** | a Vite proxy 8080-ra mutatott, a deploy 8081-en indított | egyetlen igazságforrás: az `application.properties` `server.port` értéke vezérli a deploy-t, a health checket és a proxyt is |

A `project_doctor` három ponton fut le:

* a **védőkorlátban** — az IT ágens még maga javíthatja;
* a **sandbox build előtt** — hogy ugyanazt fordítsuk, ami a Jenkinsbe kerül;
* a **GitHub push előtt** — a feltöltött projekt garantáltan mentes a felismert blokkolóktól.

A javítások determinisztikusak, idempotensek és naplózottak — a push utáni üzenet tételesen felsorolja, mihez nyúlt a rendszer, és mi az, amit nem tudott automatikusan orvosolni.

> A valós futáson: **3 blokkoló → 0**, 8 javítással.

---

## 🔨 Sandbox — a rendszer igazságforrása

Korábban minden ágenst egy **másik LLM véleménye** minősített: a QA elolvasta a kódot és prózában nyilatkozott róla. Ezért fordulhatott elő, hogy a frontend és a backend külön-külön hihetőnek tűnt, miközben a frontend **egyetlen API-hívást sem** intézett a backendhez — és ezt 15 futáson át senki nem vette észre.

A `sandbox.py` ezt a kört zárja be: a fájlfát kiírja egy ideiglenes könyvtárba, lefuttatja rajta a **valódi fordítót**, és a nyers hibaüzenetet adja vissza az IT ágensnek javításra.

```
IT válasz → VirtualWorkspace → sandbox
   frontend:  npm install → tsc --noEmit → npm run build
   backend:   mvn -B compile
   ↓
hiba? → a NYERS fordítói kimenet megy vissza promptként (max. 3 próbálkozás)
zöld?  → mehet a QA-hoz
```

**Fokozatos degradáció:** Docker → lokális `npm`/`mvn` → kihagyva. A szimuláció soha nem áll meg attól, hogy nincs telepítve Docker; az oldalsáv mutatja, melyik motor aktív, és a build ki is kapcsolható.

Beállítások a `config.py`-ban: `SANDBOX_MOD` (`auto`/`docker`/`lokalis`/`off`), image-nevek, időkorlátok. A Docker mód névvel ellátott köteteken cache-eli a `~/.npm` és `~/.m2` könyvtárat, így csak az első build lassú.

A hibakinyerés strukturált (`error TS2322`, `[ERROR] …java:[24,38]`), a promptba kerülő lista limitált — a fordító több száz soros kimenete nem eszi meg a kontextust.

---

## 🛡️ Védőkorlát (Guardrail)

Az IT ágens után a rendszer három szinten ellenőriz, egyre drágábban:

1. **Struktúra** — megvan-e a `frontend/package.json` és a `backend/pom.xml`?
2. **Statikus konzisztencia** — package/könyvtár egyezés, egyetlen belépési pont, feloldatlan importok (olcsó, azonnali).
3. **Valódi fordítás** — a sandbox lefordítja a kódot (lassú, de ez a döntő).

Bukás esetén a lépés újrafut egy keményebb prompttal — de **legfeljebb `MAX_AGENS_UJRAPROBALKOZAS` alkalommal** (alapértelmezés: 3). A limit után a sprint továbbhalad, és a hiányt a QA-ra bízza.

---

## 🏭 Miért nem készült el korábban az alkalmazás?

A generált repóból a Jenkins build rendszeresen **zölden futott le anélkül, hogy bármi elindult volna**. A valós futások elemzéséből négy ok derült ki — mind javítva:

| Tünet | Gyökérok | Javítás |
|---|---|---|
| `npm ERR! enoent … package.json` | A deploy `sh` parancs a repó **gyökeréből** futott (`cd frontend` csak a build lépésben volt) | `jenkins_repair` minden npm/mvn parancsot a helyes könyvtárba tesz |
| `npm ERR! Missing script: "start"` | A pipeline `npm start`-ot hívott, de a Vite `package.json`-ban csak `dev`/`build`/`preview` van | A ténylegesen létező scriptre cserél (`npm run dev -- --host 0.0.0.0`) |
| A build zöld, de nincs app | A `nohup … &` **mindig 0 exit kóddal** tér vissza | Beszúrt **Health Check** stage: curl-lel megvárja a portot, naplót ír, hibára fut |
| A backend a 8080-on indul | `-Dserver.port` Maven JVM property, nem app-argumentum | `-Dspring-boot.run.arguments=--server.port=…` |
| `class X is public, should be declared in a file named X.java` | A fájlnév-komment nélküli blokkok `com/app/Class_16.java` néven mentődtek | `code_analysis` a `package` + osztálynévből építi az útvonalat |

A fájlnév-származtatás mellékhatásaként a **deduplikáció is megoldódott**: egy valós futásnál 78 fájl → 21, és a 7 duplikált `@SpringBootApplication` osztályból 1 maradt.

Az ágens Jenkinsfile-ja megmarad, de validáláson és auto-javításon megy át; ha javíthatatlan, determinisztikusan generált pipeline kerül fel. A feltöltés utáni üzenet felsorolja az elvégzett javításokat.

---

## 📊 Integrált LLMOps és Telemetria

A képernyő tetején rögzített (lebegő) dashboard valós idejű betekintést nyújt az erőforrás-menedzsmentbe.

* **Token- és Időmérés**: Ágensenkénti lebontás a számítási időkre és a felhasznált tokenekre.
* **SaaS Megtakarítás Kalkulátor**: A `config.SAAS_ARAK` blended árai alapján számol (GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Flash, Llama 3.1 405B).
* **OpenTelemetry**: Minden ágensfutás külön span-ként naplózódik a `opentelemetry_traces.json` fájlba. A trace-eket a `telemetry_dashboard.py` elemzi.

> A trace fájl automatikusan rotálódik, ha meghaladja a `config.TRACE_MAX_BYTES` méretet.

---

## ⚙️ Fő Funkciók és Képességek

* **Állapotgép és UI Zárolás**: A folyamat alatt a rendszer inaktiválja a beviteli mezőket és gombokat, így megakadályozza a véletlen kattintásokból eredő inkonzisztenciát.
* **Léptetéses mód**: Ágensenként, kézi jóváhagyással is végigvihető a sprint.
* **Hibatűrés**: Ha a lokális LLM nem elérhető, a sprint kontrolláltan leáll és hibaüzenetet mutat — az addigi eredmények mentve maradnak.
* **Atomikus mentés**: A projekt memória ideiglenes fájlon keresztül, `os.replace`-szel íródik, így egy megszakadt mentés nem korruptálja az adatbázist.
* **Élő Drótváz Renderelés**: Az AI által generált felülettervek azonnal interaktív formában jelennek meg az oldalon.
* **GitHub Publikálás**: A generált fájlok besorolása (`frontend/`, `backend/`, `database/`) és feltöltése **egyetlen commitban**, path-traversal védelemmel.

---

## 🚀 Telepítés és Futtatás

### Előfeltételek
* Python 3.10 vagy újabb.
* **LM Studio**: Egy lokálisan futó szerver (pl. Qwen 32B vagy Llama modellel) elindítva a `http://localhost:1234/v1` végponton.
* *(Opcionális, de erősen ajánlott)* **Docker** — a valódi fordítási visszacsatoláshoz. Enélkül a rendszer a lokálisan telepített `npm`/`mvn`-t használja, vagy kihagyja a buildet.

### Lépések
1.  **Klónozd a tárolót**:
    ```bash
    git clone <repository_url>
    cd Agents
    ```

2.  **Telepítsd a függőségeket**:
    ```bash
    python -m venv venv
    # Windows: venv\Scripts\activate   |   Linux/macOS: source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Indítsd el a szimulátort**:
    ```bash
    streamlit run app.py
    ```

4.  **(Opcionális) Telemetria dashboard**:
    ```bash
    streamlit run telemetry_dashboard.py
    ```

---

## 🧪 Tesztek

A tesztek stubolják a Streamlitet és a LangChaint, így telepített LLM-stack nélkül is futnak:

```bash
python tests/test_core.py            # prompt-formázás, állapotgép, parsing, perzisztencia
python tests/test_imports.py         # import smoke teszt + publikus API ellenőrzés
python tests/test_build_pipeline.py  # fájlnév-származtatás, Jenkinsfile-javítás, valós futás
python tests/test_workspace.py       # fájlfa-patchelés, bean-ütközés, konzisztencia
python tests/test_sandbox.py         # fordítói hibakinyerés, build folyamat, visszacsatolás
python tests/test_project_doctor.py  # build-blokkolók, port-konzisztencia, idempotencia
python tests/test_scaffold.py        # a váz zárolása – a korábbi bukások reprodukálhatatlansága
```

---

## 💡 Használati Útmutató
1.  Indítsd el a rendszert és válaszd ki a használni kívánt lokális modellt az oldalsávon.
2.  Nyomd meg a **Labor indítása** gombot, hogy a "Viselkedéskutató Lab" több iteráción keresztül felépítse és finomítsa az ágensek mélypszichológiai profilját.
3.  Miután a rendszer feloldotta a felületet, írd be a beviteli mezőbe az üzleti igényt (pl. *"Készítsünk egy bejelentkező képernyőt"*).
4.  Dőlj hátra, és figyeld, ahogy az ágensek lefolytatják a Sprintet, miközben a lebegő LLMOps panel méri a megtakarításaidat.

---
**Szerző:** Surányi Zsolt
*Kifejlesztve lokális AI modellek (LM Studio) integrált, nagyvállalati szintű teszteléséhez és workflow automatizálásához.*
