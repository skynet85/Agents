# 🧠 LLMOps Agilis Szimulátor — Teljes rendszerleírás és stratégia

> Ez a dokumentum a rendszer **teljes** működését és a mögötte álló mérnöki
> stratégiát írja le, feltételezve, hogy az olvasó még sosem látta a projektet.
> Két nagy részből áll: az első fele **mit csinál** a rendszer, a második fele
> **miért pont így épül fel** — vagyis a stratégia, amit egy sor valós build-bukás
> kényszerített ki és igazolt.

---

## 0. Egy mondatban

A szimulátor egy **lokálisan futó, több-ágenses szoftverfejlesztő csapatot** modellez:
egy üzleti igényből (pl. „kérek egy online malom játékot") hét LLM-ágens egy agilis
sprint keretében **valóban lefordítható, futtatható és Jenkinsből deployolható**
full-stack alkalmazást állít elő (React + Vite frontend, Spring Boot backend),
miközben a rendszer valós időben méri a lokális LLM erőforrás-felhasználását.

A kulcsszó a **„valóban"**. A projekt lényege nem az, hogy egy modell kódot ír —
hanem az a védelmi architektúra, amely garantálja, hogy a kimenet a gépen is
összeáll, nem csak a képernyőn néz ki jól.

---

## 1. Mi a probléma, amit megold?

### 1.1 A naiv megközelítés és a csődje

A „kérj meg egy LLM-et, hogy írjon egy alkalmazást" megközelítés demóban működik,
éles használatban viszont megbízhatatlan. Egy nyelvi modell:

- **kitalál** nem létező csomagverziókat (`"@tailwindcss/vite": "^3.4.0"` — ez a
  csomag csak 4.x-től létezik);
- **összekever** technológiai paradigmákat (v3-as és v4-es Tailwind egyszerre);
- **elfelejti** a saját korábbi kimenetét, és minden körben újragenerálja az egészet;
- **hihetőnek látszó, de fordíthatatlan** kódot ír (`Object`-et ad vissza ott, ahol
  `Map<String,Object>` kellene);
- **más hibát ejt minden futásban** — ezért az egyenkénti javítgatás sosem ér véget.

A legveszélyesebb az, amikor a hiba **néma**: a build zöld, a felhasználó mégis
hibaüzenetet vagy üres oldalt lát. Ez a rendszer ezeket a néma hibákat vadássza.

### 1.2 A megoldás filozófiája: igazságforrás (ground truth)

Egy valós fejlesztőcsapatban a visszajelzés **a gépből** jön: lefordul-e, lefut-e,
zöld-e a teszt. A régi szimulátorban viszont minden ágenst egy **másik LLM
véleménye** minősített — a QA elolvasta a kódot és prózában nyilatkozott róla.
Így két féltermék meggyőzően „késznek" tűnhetett, miközben soha nem beszéltek
egymással.

A teljes stratégia egyetlen elvre épül:

> **Minden minőségi döntést gépi igazságforrásra kell alapozni, nem LLM-véleményre.**

Ebből következik minden védelmi réteg, amit a 6. fejezet részletez.

---

## 2. A nagy kép — architektúra

A rendszer **Clean Architecture** elven épül: a felület, az üzleti logika, a
perzisztencia és az analitika élesen szét van választva. Egyetlen modul sem keveri
a Streamlit UI-t a tiszta logikával (ezért tesztelhető minden hálózat és LLM nélkül).

```
┌─────────────────────────────────────────────────────────────────┐
│                        FELHASZNÁLÓI FELÜLET                       │
│  app.py  ·  ui_components.py  ·  telemetry_dashboard.py           │
│  (Streamlit: nézetek, sidebar, sprint-vezérlés, dashboard)        │
└───────────────┬─────────────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────────────┐
│                        SPRINT-VEZÉRLÉS                            │
│  sprint_engine.py   (állapotgép, védőkorlát, retry-logika)        │
│  agents.py          (LangChain láncok, promptok — nincs Streamlit)│
└───────────────┬─────────────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────────────┐
│                   PROJEKTÁLLAPOT + VÉDELEM                        │
│  scaffold.py        (RÖGZÍTETT VÁZ — a build-stabilitás alapja)   │
│  workspace.py       (VirtualWorkspace: élő fájlfa, patch-elés)    │
│  code_analysis.py   (fájlnév-származtatás a kód tartalmából)      │
│  project_doctor.py  (build-blokkolók diagnózisa + javítása)       │
│  sandbox.py         (VALÓDI fordítás — az igazságforrás)          │
│  jenkins_repair.py  (determinisztikus Jenkinsfile-generálás)      │
│  github_integration.py (kód-kinyerés, egy-commit push)           │
└───────────────┬─────────────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────────────┐
│                  PERZISZTENCIA + TELEMETRIA                       │
│  memory_manager.py  (atomikus JSON-mentés)                        │
│  telemetry_setup.py (OpenTelemetry provider + flush)              │
│  config.py          (globális konfiguráció, ágensdefiníciók)      │
│  util.py            (telemetriás ágensfuttatás, drótváz-kinyerés) │
└─────────────────────────────────────────────────────────────────┘
```

**Modulméretek (kód sorokban):** `app.py` 928, `jenkins_repair.py` 581,
`github_integration.py` és `scaffold.py` 471, `project_doctor.py` 451,
`workspace.py` 426, `sandbox.py` 312, `code_analysis.py` 305 — összesen ~5300 sor
alkalmazáskód és ~1900 sor teszt (281 assert, 7 független teszt-suite).

---

## 3. A hét ágensből álló pipeline

A szimulátor a klasszikus **SDLC** (Software Development Life Cycle) folyamatot
követi. Minden ágens egy „mélypszichológiai profillal" rendelkezik, amit egy előzetes
„Viselkedéskutató Labor" fázis épít fel több iterációban — ez adja a szimuláció
emberi ízét. A sprint során az ágensek **egymás kimenetére építenek**:

| Ikon | ID | Szerep | Felelősség |
|------|----|--------|------------|
| 👔 | PO | Product Owner | Üzleti igény felmérése, prioritások, célok |
| 📋 | BA | Business Analyst | Technikai bontás + **API-szerződés** (endpoint, mezők) |
| 🎨 | UX | UX/UI Designer | Élő HTML/Tailwind drótváz generálása |
| 💻 | IT | Informatikus | **A tényleges alkalmazáskód** (komponensek, service-ek) |
| 🔎 | QA | Manual QA | Az alkalmazás működésének ellenőrzése (nem a build-configé) |
| 🏗️ | DO | DevOps Engineer | A deploy szöveges véleményezése |
| ⏱️ | SM | Scrum Master | Moderálás, a sprint lezárása (`[LEZÁRVA]` kulcsszó) |

Fontos, hogy a szerepek **átdefiniálódtak** a stratégiaváltással (lásd 5–6. fejezet):
a BA már nem build-konfigurációt tervez, hanem **API-szerződést** ad meg; a QA már
nem a `package.json` meglétét kéri számon, hanem azt vizsgálja, hogy a frontend
**tényleg hívja-e** a backendet és nem placeholder-e az `App.tsx`; a DevOps pedig
már **nem ír Jenkinsfile-t**, mert azt a rendszer determinisztikusan generálja.

Az ágensek a felületen menet közben hozzáadhatók, törölhetők, a promptjaik és a
hozzájuk rendelt modell szabadon állítható.

---

## 4. Egy sprint életciklusa lépésről lépésre

1. **Labor fázis.** A „Viselkedéskutató Labor" minden ágenshez legenerál egy
   alapprofilt, majd `finomítási körök`-ön át elmélyíti (kognitív torzítások,
   rejtett motivációk). Ez tölti fel a `<ID>_persona` kulcsokat a session state-ben.

2. **A projekt vázzal indul.** Amint elkezdődik egy szimuláció, a `VirtualWorkspace`
   **nem üres** — a `scaffold.vaz_fajlok()` már feltöltötte a teljes, build-képes
   vázzal (13 fájl: `package.json`, `tsconfig`, `vite.config`, `pom.xml`, belépési
   pontok stb.). Az ágensek ebbe „dolgoznak bele".

3. **Az ügyfél beírja az igényt** (pl. „online malom játék"). Elindul a sprint
   állapotgépe.

4. **Körökben futnak az ágensek.** Minden ágens megkapja a promptjában:
   - a saját mélyprofilját és szabályát,
   - a **rögzített váz leírását** (mit NEM szabad újraírnia),
   - **az aktuális fájlfát** (mit írt már meg — így nem generálja újra az egészet),
   - a projekt eddigi dokumentációját és az előzményeket.

5. **A válasz patch-elődik a fájlfába.** A `VirtualWorkspace.alkalmaz()` kinyeri a
   kódblokkokat, **valódi fájlnevet származtat** a tartalomból, és beírja a fájlfába —
   közben elutasítja a védett fájlokat és feloldja a névütközéseket.

6. **Az IT ágens után a védőkorlát mér** — három, egyre drágább szinten:
   struktúra → statikus konzisztencia → **valódi fordítás**. Ha bukik, a nyers
   fordítói hiba megy vissza az IT-nak javításra (max. 3 próbálkozás).

7. **Kör végén az Admin konszolidál.** Egy alacsony hőmérsékletű LLM-lánc frissíti
   a projekt dokumentációját a kör eseményeiből (a vitákat kihagyja, a tényeket és
   a kódot megtartja).

8. **Lezárás.** Ha a Scrum Master beírja a `[LEZÁRVA]` kulcsszót — és teljesült a
   kötelező minimum iterációszám —, a sprint értékelhető és GitHubra publikálható.

9. **Feltöltés előtti kapu.** A GitHub push **előtt** a rendszer lefordítja a
   projektet a sandboxban. Ha nem fordul le, alapból **nem enged pusholni** (van
   felülbírálás). Így a hiba nem jut el a Jenkinsig.

---

## 5. A stratégiai fordulópont — miért kellett minden átépíteni?

A projekt fejlesztése két korszakra oszlik.

**Első korszak: hibavadászat.** Minden Jenkins-bukás után befoltoztuk azt az egy
hibát, amit a log mutatott. Ez fogócska volt: minden folt után a modell máshol
hallucinált. A gyökérok az volt, hogy **az LLM írta a build-infrastruktúrát is** —
`package.json`, `tsconfig`, `vite.config`, `tailwind.config`, `pom.xml`, `Jenkinsfile`.
Ez a rész minden futásban más lett, és minden futásban máshol tört el.

**Második korszak: elvesszük tőle a felelősséget.** A megoldás nem újabb
javítószabály, hanem egy elvi váltás:

> Az LLM **csak alkalmazáskódot** írhat. A build-infrastruktúrát egy rögzített,
> verzió-pinnelt, tesztelt váz adja, amit az ágens nem módosíthat.

Ettől a build kimenetele többé nem lottó: az egyetlen változó az alkalmazáskód,
amit a sandbox fordítója amúgy is ellenőriz.

---

## 6. A védelmi rétegek — a stratégia lényege

A rendszer szíve hat, egymásra épülő védelmi réteg. Mindegyik egy konkrét, valós
hibaosztályt zár le véglegesen.

### 6.1 VirtualWorkspace — a projekt mint élő fájlfa

**Modul:** `workspace.py`

**A megoldott probléma.** Régen a „projekt" nem létezett önálló entitásként: a repó
tartalma csak a GitHub-push pillanatában állt össze a chat-üzenetekből. Ennek két
mért következménye volt egy valós futásban:

- **Ütköző Spring bean.** Az 1. iteráció a `com.malom.engine.MatchEngine`, a 3. a
  `com.malom.service.MatchEngine` osztályt hozta létre — mindkettő `@Service`,
  mindkettőből `matchEngine` bean-név → `ConflictingBeanDefinitionException` → a
  Spring context el sem indult.
- **117 duplikált kódblokk**, mert az IT minden körben újragenerálta az egészet.

**Hogyan működik.** A projekt egy élő `útvonal → tartalom` leképezés, amit minden
ágensválasz **patch-el**:

- Az ágens promptjába bekerül az aktuális fájlfa → csak a változó fájlt írja ki.
- `DELETE: <útvonal>` és `MOVE: <régi> -> <új>` direktívák.
- **Automatikus névütközés-feloldás:** ha egy későbbi iteráció máshova teszi
  ugyanazt a `@Service` osztályt, a régi törlődik.
- **Statikus konzisztencia-ellenőrzés** (`ellenoriz()`): package/könyvtár egyezés,
  egyetlen Spring belépési pont, feloldatlan relatív importok, hiányzó build-leírók,
  `Map.of(...)` null értékkel (futásidejű NPE), placeholder `App.tsx`.

> Valós futáson mérve: **48 chat-üzenet → 18 fájl**, ütköző bean nélkül.

### 6.2 Rögzített váz — a build-stabilitás alapja

**Modul:** `scaffold.py`

Ez a projekt **legfontosabb tervezési döntése**. A váz egy verzió-pinnelt, ismerten
működő projekt:

- **Frontend:** React 18.3.1 + Vite 5.4.8 + TypeScript 5.6.2 + Tailwind 3.4.13.
  A `tailwindcss-animate` plugin **eleve telepítve** van (ez okozta a #24-es bukást).
- **Backend:** Spring Boot 3.2.10 + Java 17, `com.app` alapcsomag, CORS-konfiggal és
  actuator health-endpointtal.
- **Portok:** frontend 3000, backend **8081** (nem 8080 — azon a Jenkins figyel).

**Védelmi mechanizmusok:**

| Védelem | Mit akadályoz meg |
|---------|-------------------|
| **Védett útvonalak** | Az ágens nem írhatja felül a 13 váz-fájlt + a `Jenkinsfile`-t. Ha megpróbálja, a rendszer eldobja és `⛔`-vel naplózza. |
| **Függőség-allowlist** | Új npm csomag csak `DEPENDENCY: <név>` direktívával, kizárólag 8 engedélyezett csomagból (`axios`, `zod`, `recharts`, `lucide-react` stb.), **rögzített verzióval**. Kitalált verzió lehetetlen. |
| **CSS `@apply` szűrés** | A Tailwind legtörékenyebb funkciója; egyetlen ismeretlen utility megállítja a buildet. A generált CSS-ből kiszűrjük — a JSX `className`-ben minden érintetlen marad. |
| **Placeholder-őr** | Az `App.tsx` sentinellel jelölt; ha az ágens hozzá sem nyúl, a védőkorlát jelzi, hogy a felhasználó a „fejlesztés folyamatban" oldalt látná. |
| **Egyetlen belépési pont** | A második `@SpringBootApplication` osztály elutasításra kerül. |

### 6.3 project_doctor — build-blokkolók diagnózisa és javítása

**Modul:** `project_doctor.py`

Ha egy régi futást töltünk be, vagy az ágens mégis becsempész valamit, ez a réteg
**determinisztikusan** helyrehozza a projektet. Öt konkrét, valós build-blokkolót
ismer fel és javít:

| Blokkoló | Tünet | Javítás |
|----------|-------|---------|
| Nem létező függőség-verzió | `npm install` ETARGET | eltávolítás a package.json-ból és a vite.configból |
| Kevert Tailwind-setup | v3+v4 együtt, config nélkül | egységes v3 lánc generálása |
| Lógó tsconfig-hivatkozás | `tsc -b` error TS6053 | a hiányzó fájl létrehozása |
| CI-t törő stílusszabály | `noUnusedLocals` piros build | kikapcsolás |
| Port-eltérés | proxy 8080, deploy 8081 | egyetlen igazságforrás: `application.properties` |

A javítások **idempotensek** (kétszer futtatva sem változtatnak semmit) és
naplózottak — a push utáni üzenet tételesen felsorolja, mihez nyúlt a rendszer.

### 6.4 sandbox — a rendszer igazságforrása

**Modul:** `sandbox.py`

Ez a réteg zárja be a kört: a fájlfát kiírja egy ideiglenes könyvtárba, és
**valódi fordítót futtat** rajta:

```
frontend:  npm install → tsc --noEmit → npm run build
backend:   mvn -B compile
   ↓
hiba? → a NYERS fordítói kimenet megy vissza promptként (max. 3 próbálkozás)
zöld?  → mehet a QA-hoz / a push-hoz
```

**Fokozatos degradáció:** Docker → lokális `npm`/`mvn` → kihagyva. A szimuláció
sosem áll meg attól, hogy nincs Docker; az oldalsáv mutatja, melyik motor aktív.
A Docker mód névvel ellátott köteteken cache-eli a `~/.npm` és `~/.m2` könyvtárat,
így csak az első build lassú.

A hibakinyerés **strukturált**: felismeri az `error TS2322`, a
`[ERROR] …java:[24,38] cannot find symbol` formákat, kiszűri a Maven zaját
(`-> [Help 1]`), és a promptba kerülő listát limitálja (max. 15 hiba), hogy a
fordító több száz soros kimenete ne egye meg a kontextust.

> **Kritikus részlet:** a frontend parancs `set -e; ...; if [ -f tsconfig.json ];
> then tsc --noEmit; fi` formát használ, NEM `|| true`-t — különben a `|| true`
> elnyelné a típushibákat, és a build hamisan sikeresnek látszana.

### 6.5 jenkins_repair — determinisztikus CI/CD

**Modul:** `jenkins_repair.py`

A Jenkinsfile-t a rendszer **generálja**, nem az ágens. A `generalt_jenkinsfile()`
a tényleges fájlfából épít fel egy garantáltan működő pipeline-t. A stage-sorrend:

```
Sanity Check → Stop Previous → Frontend Build → Frontend Deploy
             → Backend Build → Backend Deploy → Health Check
```

Minden egyes stage egy valós bukásra adott válasz:

- **Sanity Check** — ha nincs build-leíró, a pipeline hibára fut (nem lesz néma zöld).
- **Stop Previous** — leállítja az előző build folyamatait (`pkill -f spring-boot:run`
  stb.). A `BUILD_ID=dontKillMe` túlélteti a deploy-t, de a következő build így nem
  tudna bindolni (`Port 8081 was already in use`) — ezt oldja fel. Ha a port a
  takarítás után is foglalt, **megmondja, ki tartja** (külön kiemelve, ha a Jenkins az).
- **Frontend Build** — `npm install` → `npm run typecheck` → `npm run build`. A
  `typecheck` azért kell, mert a `vite build` csak az elérhető kódot fordítja; egy
  nem importált, hibás komponens észrevétlen maradna.
- **Deploy stage-ek** — `dir()` blokkban (a repó gyökeréből az npm/mvn azonnal meghal),
  keretrendszer-helyes indítóparanccsal (Next.js `-H`/`-p`, Vite `--host`/`--port`),
  `BUILD_ID=dontKillMe ... > app.log 2>&1 < /dev/null &` formában.
- **Health Check** — curl-lel megvárja a portokat. A backendnél **kizárólag** az
  `/actuator/health` `"status":"UP"` válaszát fogadja el (a korábbi „bármilyen HTTP
  válasz jó" logika a Jenkins saját weboldalát igazolta élő backendként).

A modul emellett **javítani** is tud egy ágens által írt pipeline-t (`javit_jenkinsfile`),
de a jelenlegi stratégiában mindig a generált verzió megy fel.

### 6.6 Push-védelem — a záró kapu

**Modul:** `app.py` (`_push_engedelyezett`)

A GitHub feltöltés előtt lefut a sandbox build. Ha a projekt nem fordul le, a
rendszer **leállítja a feltöltést** és kiírja a fordítói hibákat — hiszen a Jenkins
ugyanezen a hibán bukna el. Van felülbíráló jelölő, ha valaki tudatosan mégis fel
akar tolni egy félkész állapotot. Build motor hiányában a kapu automatikusan nyit
(nincs mivel ellenőrizni), de a felület figyelmeztet erre.

---

## 7. A build-lánc végponttól végpontig

Így néz ki egy sikeres út a felhasználói igénytől a böngészőben futó alkalmazásig:

```
Üzleti igény (chat)
      │
      ▼
Sprint: PO → BA(API-szerződés) → UX → IT(kód) → QA → SM
      │           │
      │           ▼
      │      VirtualWorkspace  ←── minden IT-válasz patch-eli
      │           │            (védett útvonalak, névütközés-feloldás)
      │           ▼
      │      Védőkorlát: struktúra → statikus → SANDBOX FORDÍTÁS
      │           │                                    │ hiba
      │           │◄───────────────────────────────────┘ (retry, max 3)
      ▼           ▼
Push-kapu: project_doctor.javit() → sandbox build → OK?
      │                                              │ nem
      │◄─────────────────────────────────────────────┘ (blokkol)
      ▼
GitHub (egyetlen commit): váz + alkalmazáskód + generált Jenkinsfile
      │
      ▼
Jenkins pipeline:
  Sanity → Stop Previous → FE build+typecheck → FE deploy
         → BE build → BE deploy → Health Check(/actuator/health = UP)
      │
      ▼
Böngésző: http://localhost:3000  (a /api hívásokat a Vite proxyzza a 8081-re)
```

---

## 8. LLMOps és telemetria

A képernyő tetején rögzített (lebegő) dashboard valós idejű betekintést ad az
erőforrás-menedzsmentbe:

- **Token- és időmérés** ágensenkénti lebontásban, HTML/CSS sávdiagramokkal.
- **SaaS-megtakarítás kalkulátor.** A `config.SAAS_ARAK` blended árai (GPT-4o 7,50 $,
  Claude 3.5 9,00 $, Llama 3.1 5,00 $, Gemini 1.5 0,35 $ / 1M token) alapján
  megmutatja, mennyibe kerülne ugyanez felhős API-n.
- **OpenTelemetry.** Minden ágensfutás külön span-ként naplózódik az
  `opentelemetry_traces.json` fájlba. A `telemetry_setup.py` gondoskodik a helyes
  `flush`-ról és a fájlrotációról (a korábbi verzióban a puffer sosem ürült ki, így
  a dashboard gyakran üres maradt). A `telemetry_dashboard.py` egy önálló Streamlit
  app, ami ezeket a trace-eket elemzi.

---

## 9. Perzisztencia és állapotkezelés

- **Atomikus mentés** (`memory_manager.py`). A futások egy `szimulacio_memoria.json`
  fájlba kerülnek, ideiglenes fájlon keresztül, `os.replace`-szel — így egy
  megszakadt mentés nem korruptálja a korábbi adatokat. Sérült fájl esetén a rendszer
  üres előzménnyel indul, nem omlik össze.
- **Fájlfa perzisztálása.** A `VirtualWorkspace` teljes állapota (fájlok, napló,
  extra függőségek) elmentődik, így egy futás betölthető és folytatható. Régi
  futásoknál, ahol még nincs mentett fájlfa, a rendszer visszamenőleg felépíti a
  chat-logból — a vázból indulva, hogy build-képes legyen.
- **Állapotgép és UI-zárolás.** A sprint alatt a rendszer inaktiválja a beviteli
  mezőket, hogy egy véletlen kattintás ne okozzon inkonzisztenciát. Van léptetéses
  mód is, ahol minden ágenslépés kézi jóváhagyással fut.

---

## 10. Modulreferencia

| Modul | Felelősség | Streamlit-függő? |
|-------|-----------|:---:|
| `app.py` | Belépési pont, nézetek, sprint-állapotgép vezérlése | igen |
| `ui_components.py` | Minden Streamlit UI: dashboard, sprint-státusz, sidebar | igen |
| `sprint_engine.py` | Sprint-állapotgép, védőkorlát, retry-logika | **nem** |
| `agents.py` | LangChain láncok és promptok | **nem** |
| `scaffold.py` | Rögzített, verzió-pinnelt projektváz + védelmi szabályok | **nem** |
| `workspace.py` | VirtualWorkspace: élő fájlfa, patch-elés, konzisztencia | **nem** |
| `code_analysis.py` | Valódi fájlnév kikövetkeztetése a kód tartalmából | **nem** |
| `project_doctor.py` | Build-blokkolók diagnózisa és determinisztikus javítása | **nem** |
| `sandbox.py` | Valódi build (Docker/lokális) — az igazságforrás | **nem** |
| `jenkins_repair.py` | Determinisztikus Jenkinsfile-generálás és -javítás | **nem** |
| `github_integration.py` | Kód-kinyerés, egy-commit GitHub push | **nem** |
| `memory_manager.py` | Atomikus JSON-perzisztencia | **nem** |
| `telemetry_setup.py` | OpenTelemetry provider, flush, rotáció | **nem** |
| `telemetry_dashboard.py` | Önálló trace-elemző Streamlit app | igen |
| `util.py` | Telemetriás ágensfuttatás, drótváz-kinyerés | igen |
| `config.py` | Globális konfiguráció, ágensdefiníciók, árak | **nem** |

A „nem Streamlit-függő" modulok stubok segítségével **telepített LLM-stack és
hálózat nélkül is tesztelhetők** — ez teszi lehetővé a 281 assertes teszt-készletet.

---

## 11. A tanulási történet — valós build-bukások kronológiája

A rendszer robusztussága nem elméletből, hanem **konkrét, sorszámozott Jenkins-build
bukásokból** épült fel. Mindegyik egy hibaosztályt tárt fel, és mindegyikre külön
regressziós teszt vigyáz.

| Build | Tünet a logban | Gyökérok | A rá adott válasz |
|:---:|---|---|---|
| korai | `npm install` ETARGET | kitalált csomagverzió | rögzített váz + allowlist |
| **#22** | `local: not in a function` → exit 2 | a health check `local`-t használt, de a Jenkins `sh` dash-t futtat | `local` eltávolítása; determinisztikus pipeline |
| **#24** | `[postcss] animate-in does not exist` | `@apply` telepítetlen plugin osztályára | `tailwindcss-animate` a vázba + `@apply` szűrés |
| **#26** | `Object cannot be converted to Map` | valódi Java típushiba az alkalmazáskódban | **push-védelem**: fordítás a feltöltés előtt |
| **#26b** | néma: build zöld, üres oldal | az `App.tsx` a placeholder maradt | placeholder-őr a védőkorlátban |
| **#29** | `Port 8081 was already in use` | az előző build backendje még futott | **Stop Previous** stage a deploy előtt |
| **#29b** | a health check azonnal zöld lett | az előző build frontendje válaszolt | actuator `"status":"UP"` — konkrét bizonyíték |

A tanulság: **minden „lokális javítás" egyben egy determinisztikus, tesztelt szabály**,
ami a következő futásban is hat. A rendszer nem foltokból áll, hanem egy növekvő,
tesztekkel körbebástyázott védelmi rétegből.

---

## 12. Tesztelési stratégia

Hét független teszt-suite, összesen **281 assert**, mind Streamlit- és
hálózatfüggetlen (a nehéz csomagokat stubok helyettesítik):

| Suite | Mit véd |
|-------|---------|
| `test_core.py` | Prompt-formázás (kapcsos zárójel bug), állapotgép, parsing, atomikus mentés |
| `test_workspace.py` | Fájlfa-patch-elés, bean-ütközés feloldása, konzisztencia |
| `test_build_pipeline.py` | Fájlnév-származtatás, Jenkinsfile-javítás, a #22 regresszió |
| `test_project_doctor.py` | Build-blokkolók, port-konzisztencia, idempotencia |
| `test_sandbox.py` | Fordítói hibakinyerés, build-folyamat, visszacsatolás |
| `test_scaffold.py` | A váz zárolása — az összes korábbi bukás reprodukálhatatlansága |
| `test_imports.py` | Minden modul importálható, a publikus API teljes |

A `test_scaffold.py` külön kiemelendő: egy „rosszul viselkedő" ágenst szimulál, aki
3 iteráción át küld kitalált verziót, `@apply`-t, csonka `pom.xml`-t és `local`-os
pipeline-t — a projekt végig build-képes marad, a valódi alkalmazáskód viszont
bekerül.

Futtatás:

```bash
python tests/test_core.py
python tests/test_workspace.py
python tests/test_build_pipeline.py
python tests/test_project_doctor.py
python tests/test_sandbox.py
python tests/test_scaffold.py
python tests/test_imports.py
```

---

## 13. Telepítés és futtatás

### Előfeltételek

- **Python 3.10+**
- **LM Studio** — lokálisan futó LLM-szerver (pl. Qwen 32B vagy Llama) a
  `http://localhost:1234/v1` végponton.
- *(Erősen ajánlott)* **Docker** — a valódi fordítási visszacsatoláshoz. Enélkül a
  rendszer a lokális `npm`/`mvn`-t használja, vagy kihagyja a buildet.

### Lépések

```bash
git clone <repository_url>
cd Agents

python -m venv venv
# Windows:  venv\Scripts\activate    |    Linux/macOS:  source venv/bin/activate
pip install -r requirements.txt

streamlit run app.py
# opcionálisan a telemetria-dashboard:
streamlit run telemetry_dashboard.py --server.port 8502
```

### A generált alkalmazás futtatása

A Jenkins pipeline maga elindítja és ellenőrzi az alkalmazást; a böngészőben a
`http://localhost:3000` a frontend, a `/api/...` hívásokat a Vite proxyzza a
backend 8081-es portjára. Jenkins nélkül, kézzel:

```bash
cd backend  && mvn spring-boot:run                    # → localhost:8081
cd frontend && npm install && npm run dev             # → localhost:3000
```

> **Fontos a Jenkinsnél:** a `tools { nodejs 'Node18' }` és `maven 'Maven3'`
> neveknek pontosan így kell szerepelniük a Jenkins Global Tool Configuration
> alatt, és a NodeJS plugin telepítve kell legyen — különben a pipeline a `tools`
> blokknál elszáll. A generált alkalmazás elérhetőségéhez a Jenkins-konténernek
> publikálnia kell a 3000-es és 8081-es portot.

---

## 14. Ismert korlátok és a következő lépések

**Amit a rendszer garantál:** a kimenet build-képes, a build-infrastruktúra
stabil, a néma hibák (üres oldal, portütközés, hamis zöld) kiszűrődnek.

**Amit továbbra is a modell minősége határoz meg:** hogy az alkalmazáskód
*értelmes és összefüggő* legyen — hogy a malom játék szabályai helyesek, a
frontend és a backend logikailag illeszkedjen. A rendszer azt garantálja, hogy ez
lefordul és elindul; azt nem, hogy a játéklogika hibátlan.

**A stack rögzített.** A jelenlegi váz React+Vite / Spring Boot. Ez az ára a
stabilitásnak — a modell nem választhat Next.js-t. Ha egy konkrét projekthez más
kell, a `scaffold.py`-ban egy helyen átírható.

**A roadmap következő logikus lépései** (a meglévő infrastruktúrára építve):

1. **QA → futtatható tesztek.** A sandbox már megvan; `mvn test` / `vitest run`
   kellene a `compile` helyett, és a QA verdiktje a teszteredmény lenne, nem a
   véleménye.
2. **OpenAPI szerződés + kontraktus-teszt.** A BA már API-szerződést ír; ezt
   formalizálni lehetne OpenAPI-ként, és teszttel ellenőrizni, hogy a frontend csak
   létező endpointot hív.
3. **Git-natív munkafolyamat.** Branch sprintenként, PR merge helyett, ágensenkénti
   beszédes commit — így a `git log` olvasható sprint-napló lenne.
4. **Regressziós benchmark.** 5–10 rögzített feladat, amin a rendszer minden
   prompt-változtatás után végigfut; metrika a *lefordul / teszt zöld / smoke zöld*
   arány. Enélkül a prompt-hangolás vakrepülés.

---

**Szerző:** Surányi Zsolt
*Kifejlesztve lokális AI modellek (LM Studio) integrált, nagyvállalati szintű
teszteléséhez és workflow-automatizálásához.*
