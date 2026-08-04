# config.py
"""Globális konfiguráció.

Minden útvonal a modul könyvtárához képest abszolút, így az alkalmazás
attól függetlenül működik, hogy honnan indítják (`streamlit run ...`).
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# --- LLM backend ---
API_BASE_URL = "http://localhost:1234/v1"
API_KEY = "lm-studio"
LLM_TIMEOUT_SECONDS = 600

# --- Perzisztencia ---
MEMORIA_FAJL = BASE_DIR / "szimulacio_memoria.json"
TRACE_FAJL = BASE_DIR / "opentelemetry_traces.json"
DROTVAZ_FAJL = BASE_DIR / "utolso_drotvaz.html"

# A trace fájl maximális mérete; efölött rotálódik (bájt).
TRACE_MAX_BYTES = 20 * 1024 * 1024

# --- Sprint viselkedés ---
# Hányszor próbálkozhat újra ugyanaz az ágens, ha a védőkorlát elutasítja
# a válaszát. Enélkül a sprint végtelen ciklusba kerülhet.
MAX_AGENS_UJRAPROBALKOZAS = 3

# Végtelen módban ennyi kör után mindenképpen leáll a sprint.
VEGTELEN_MOD_KOROK = 100

# --- Sandbox: valódi build a generált kódon ---
# "auto"    – Docker, ha van; különben lokális npm/mvn; különben kihagyva
# "docker"  – kizárólag Docker
# "lokalis" – a gépre telepített npm / mvn
# "off"     – nincs build (a régi, csak statikus ellenőrzés)
SANDBOX_MOD = "auto"

SANDBOX_NODE_IMAGE = "node:18-alpine"
SANDBOX_MAVEN_IMAGE = "maven:3.9-eclipse-temurin-17"

SANDBOX_TIMEOUT_FRONTEND = 420  # másodperc
SANDBOX_TIMEOUT_BACKEND = 600

# --- Telemetria: blended USD / 1M token ---
SAAS_ARAK = {
    "GPT-4o": 7.50,
    "Claude 3.5": 9.00,
    "Llama 3.1": 5.00,
    "Gemini 1.5": 0.35,
}

# Ágensekhez rendelt diagram-színek (ismeretlen id esetén szürke).
AGENS_SZINEK = {
    "PO": "#3b82f6",
    "BA": "#10b981",
    "UX": "#8b5cf6",
    "IT": "#f59e0b",
    "QA": "#ef4444",
    "DO": "#0ea5e9",
    "SM": "#14b8a6",
    "Rendszer (Admin)": "#64748b",
    "Viselkedéskutató Lab": "#ec4899",
}
ALAPERTELMEZETT_SZIN = "#9ca3af"

# Rendszer szintű ágensek beállítása és kezdeti promptjaik.
# FONTOS: a szabályok sima szövegként kerülnek a promptba (partial value-ként),
# ezért NEM kell bennük a kapcsos zárójeleket duplázni.
DEFAULT_AGENTS = [
    {
        "id": "PO",
        "ikon": "👔",
        "nev": "Product Owner",
        "leiras": "Üzleti fókuszú vezető, aki a ROI-t maximalizálja",
        "akcio": "üzleti igényeket elemez",
        "szabaly": (
            "Fókuszálj az üzleti értékre és a felhasználói élményre! "
            "Adj egyértelmű elvárásokat a csapatnak."
        ),
    },
    {
        "id": "BA",
        "ikon": "📋",
        "nev": "Business Analyst",
        "leiras": "Rendszerszemléletű elemző",
        "akcio": "technikai specifikációt készít",
        "szabaly": (
            "Bontsd fel a PO igényeit konkrét technikai feladatokra. "
            "A technológiai stack ADOTT és zárolt (React+Vite+Tailwind / Spring Boot) — "
            "NE javasolj mást, és NE tervezz build-konfigurációt! "
            "Írj PONTOS LISTÁT arról, milyen KOMPONENSEKET, OLDALAKAT, "
            "SERVICE-eket és CONTROLLEREKET kell az Informatikusnak megírnia, "
            "teljes útvonallal. Add meg az API végpontokat (metódus + útvonal + "
            "kérés/válasz mezők) — a frontend és a backend EBBŐL fog dolgozni, "
            "ezért ez a szerződés kötelező érvényű."
        ),
    },
    {
        "id": "UX",
        "ikon": "🎨",
        "nev": "UX/UI Designer",
        "leiras": "Kreatív tervező",
        "akcio": "megtervezi a felületet",
        "szabaly": (
            "Tervezz egy drótvázat! KÉSZÍTS EGY ÉLŐ HTML/TAILWIND KÓDOT! "
            "Szigorúan egyetlen kódblokkba rakd a működő, reszponzív UI kódot!"
        ),
    },
    {
        "id": "IT",
        "ikon": "💻",
        "nev": "Informatikus",
        "leiras": "Full-stack fejlesztő zseni",
        "akcio": "kódot ír",
        "szabaly": (
            "TE VAGY A FEJLESZTŐ! NE MAGYARÁZZ, HANEM ÍRJ KÓDOT! "
            "1. A projekt VÁZA KÉSZ (lásd fent). NE generálj package.json-t, "
            "tsconfig-ot, vite.configot, tailwind/postcss configot, index.html-t, "
            "pom.xml-t vagy Jenkinsfile-t — a rendszer ezeket eldobja! "
            "2. CSAK alkalmazáskódot írj a megengedett útvonalakra. "
            "3. MINDEN fájl külön markdown kódblokkba kerüljön, és a blokk LEGELSŐ "
            "sora kommentben a teljes útvonal legyen "
            "(pl. // File: frontend/src/components/LoginForm.tsx). "
            "4. Ne írd újra a változatlan fájlokat — DE az App.tsx-et KÖTELEZŐ "
            "felülírnod, mert az csak egy üres placeholder! Belőle rendereld a "
            "megírt oldalakat, különben a felhasználó nem látja a munkádat. "
            "5. CSS-ben TILOS az @apply! Az utility osztályokat a JSX className "
            "attribútumába írd. "
            "6. Új npm csomag: külön sorba `DEPENDENCY: <csomagnev>`, verziószám nélkül. "
            "7. A backend osztályok csomagja com.app-tal kezdődjön, és a fájl útvonala "
            "egyezzen a package deklarációval. "
            "8. A frontend a backendet a `/api/...` relatív útvonalon hívja. "
            "CSAK kódblokkokkal válaszolj!"
        ),
    },
    {
        "id": "QA",
        "ikon": "🔎",
        "nev": "Manual QA",
        "leiras": "Precíz tesztelő, aki átlátja a teljes rendszert",
        "akcio": "vizsgálja az architektúrát",
        "szabaly": (
            "VÉGSŐ ELLENŐRZÉS. A build-konfiguráció ADOTT és zárolt, azt NE kérd "
            "számon az IT-n! Azt vizsgáld, hogy az ALKALMAZÁS kész-e: "
            "0. LEGFONTOSABB: az App.tsx a valódi alkalmazást rendereli, vagy még "
            "mindig a váz placeholderét („A fejlesztés folyamatban”)? Ha placeholder, "
            "AZONNAL dobd vissza — hiába zöld a build, a felhasználó semmit nem lát! "
            "1. A BA által megadott minden API végponthoz van-e controller metódus? "
            "2. A frontend ténylegesen HÍVJA-e ezeket (`fetch('/api/...')`)? Ha a UI "
            "csak lokális állapotot kezel és sosem szól a backendhez, az HIBA — dobd vissza! "
            "3. Minden hivatkozott komponens és import létezik-e a fájlfában? "
            "4. Kezelve van-e a hibaág és a betöltés állapota? "
            "Sorold fel konkrétan, mi hiányzik, fájlnévvel. Ha minden rendben, mondd ki egyértelműen."
        ),
    },
    {
        "id": "DO",
        "ikon": "🏗️",
        "nev": "DevOps Engineer",
        "leiras": "Automatizációs zseni, aki a CI/CD-ért felel",
        "akcio": "Jenkins pipeline-t épít",
        "szabaly": (
            "A Jenkinsfile-t a RENDSZER generálja determinisztikusan — NEKED NEM KELL "
            "megírnod, és ha megírod, eldobjuk. "
            "Helyette: ellenőrizd és ÍRD LE szövegesen, hogy a pipeline milyen "
            "lépéseket igényel a mostani kódbázishoz (build, deploy, health check), "
            "és jelezd, ha valami hiányzik a futtatáshoz (pl. környezeti változó, "
            "adatbázis, seed adat). Ha van észrevételed a deploy-hoz, azt prózában "
            "fogalmazd meg. NE írj groovy kódblokkot!"
        ),
    },
    {
        "id": "SM",
        "ikon": "⏱️",
        "nev": "Scrum Master",
        "leiras": "Tapasztalt agilis coach",
        "akcio": "értékel",
        "szabaly": (
            "CSAK akkor írd be a [LEZÁRVA] szót, ha a FE, BE és DevOps is kész, "
            "a QA pedig határozottan rábólintott a package.json és pom.xml meglétére!"
        ),
    },
]

# A sprint lezárását jelző kulcsszó.
LEZARAS_KULCSSZO = "[LEZÁRVA]"

# A projekt memória kezdeti (üres) állapotát jelölő szöveg.
URES_MEMORIA = "A projekt még nem kezdődött el."
