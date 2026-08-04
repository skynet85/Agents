# code_analysis.py
"""A generált kódblokkok elemzése: valódi fájlnév és típus kikövetkeztetése.

MIÉRT KELL EZ
-------------
Az IT ágens gyakran elhagyja a `// File: ...` kommentet. A korábbi kód ilyenkor
`Class_16.java` / `Component_42.jsx` néven mentette a blokkot, aminek két
végzetes következménye volt:

1. **A Maven build garantáltan elbukott.** Java-ban a public osztály nevének
   egyeznie kell a fájlnévvel, a `package` deklarációnak pedig a könyvtárral.
   A `com/app/Class_16.java` tartalma viszont `package com.malom; public class
   MalomApplication` volt → `class MalomApplication is public, should be
   declared in a file named MalomApplication.java`.
2. **Duplikátumok.** Ha az ágens 16 iterációban válaszolt, ugyanaz az osztály
   7 különböző `Class_NN.java` néven került fel → több `@SpringBootApplication`
   → a Spring context sem indult el.

Ha a nevet a kód TARTALMÁBÓL vezetjük le, mindkét probléma megszűnik: a fordítás
helyes, a későbbi iteráció pedig felülírja a korábbit ugyanazon az útvonalon.
"""
from __future__ import annotations

import json
import re
from typing import Dict, Optional, Tuple

# --- Java ---
JAVA_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
JAVA_PUBLIC_TIPUS = re.compile(
    r"\bpublic\s+(?:final\s+|abstract\s+|sealed\s+|static\s+)*"
    r"(?:class|interface|enum|record|@interface)\s+(\w+)"
)
JAVA_BARMELY_TIPUS = re.compile(
    r"\b(?:class|interface|enum|record)\s+(\w+)"
)

# --- JavaScript / TypeScript ---
JS_EXPORT_DEFAULT_DEKL = re.compile(
    r"export\s+default\s+(?:async\s+)?(?:function|class)\s+(\w+)"
)
JS_EXPORT_DEFAULT_NEV = re.compile(r"export\s+default\s+(\w+)\s*;?\s*$", re.MULTILINE)
JS_NEVES_EXPORT = re.compile(
    r"export\s+(?:const|function|class)\s+([A-Z]\w*)"
)
# React hook-konvenció: `export const useAuthStore = create(...)`. A név KISBETŰVEL
# kezdődik, ezért a nagybetűs mintára nem illeszkedik – enélkül az összes Zustand
# store `Component_NN.jsx` néven landolt, iterációnként újra és újra.
JS_HOOK_EXPORT = re.compile(r"export\s+(?:const|function)\s+(use[A-Z]\w*)")
JS_KOMPONENS_DEKL = re.compile(
    r"(?:const|function|class)\s+([A-Z]\w*)\s*[=(:]"
)

# TypeScript-re utaló jelek (kiterjesztés eldöntéséhez)
TS_JELEK = (
    "interface ", "type ", ": React.FC", ": string", ": number", ": boolean",
    "as const", "<Props>", "implements ", "readonly ", "enum ",
    "!)",  # non-null assertion, pl. document.getElementById('root')!
    ": void", ": Promise<", "satisfies ",
)
JSX_JELEK = ("</", "/>", "React.Fragment", "<>")

# Fence-nyelv -> kiterjesztés
NYELV_KITERJESZTES: Dict[str, str] = {
    "java": ".java",
    "xml": ".xml",
    "pom": ".xml",
    "json": ".json",
    "sql": ".sql",
    "html": ".html",
    "css": ".css",
    "scss": ".scss",
    "js": ".js",
    "javascript": ".js",
    "jsx": ".jsx",
    "ts": ".ts",
    "typescript": ".ts",
    "tsx": ".tsx",
    "yaml": ".yml",
    "yml": ".yml",
    "properties": ".properties",
    "groovy": ".groovy",
    "python": ".py",
    "py": ".py",
}


def java_teljes_utvonal(kod: str) -> Optional[str]:
    """`backend/src/main/java/<package>/<Osztaly>.java` a kód tartalmából."""
    tipus = JAVA_PUBLIC_TIPUS.search(kod) or JAVA_BARMELY_TIPUS.search(kod)
    if not tipus:
        return None
    osztaly = tipus.group(1)

    pkg = JAVA_PACKAGE.search(kod)
    pkg_ut = pkg.group(1).replace(".", "/") if pkg else "com/app"
    return f"backend/src/main/java/{pkg_ut}/{osztaly}.java"


def js_komponens_nev(kod: str) -> Optional[str]:
    """A JS/TS modul „fő” exportjának neve."""
    for minta in (
        JS_EXPORT_DEFAULT_DEKL,
        JS_EXPORT_DEFAULT_NEV,
        JS_HOOK_EXPORT,
        JS_NEVES_EXPORT,
        JS_KOMPONENS_DEKL,
    ):
        talalat = minta.search(kod)
        if talalat:
            nev = talalat.group(1)
            if nev not in ("default", "React", "App0"):
                return nev
    return None


def js_kiterjesztes(kod: str, nyelv: str = "") -> str:
    """`.jsx` / `.tsx` / `.ts` / `.js` eldöntése a fence-nyelvből és a kódból."""
    nyelv = (nyelv or "").lower()
    if nyelv in ("tsx", "jsx", "ts", "js", "typescript", "javascript"):
        return NYELV_KITERJESZTES[nyelv]

    van_jsx = any(j in kod for j in JSX_JELEK) and "<" in kod
    van_ts = any(j in kod for j in TS_JELEK)
    if van_jsx:
        return ".tsx" if van_ts else ".jsx"
    return ".ts" if van_ts else ".js"


def szarmaztatott_utvonal(kod: str, nyelv: str = "") -> Optional[str]:
    """A kód tartalmából kikövetkeztetett teljes repó-útvonal (vagy None)."""
    nyelv = (nyelv or "").lower()
    kod_lower = kod.lower()

    # --- Backend: Java ---
    if nyelv == "java" or JAVA_PACKAGE.search(kod) or "public class" in kod and "import java" in kod:
        ut = java_teljes_utvonal(kod)
        if ut:
            return ut

    # --- Backend: Maven POM ---
    if "<project" in kod_lower and "modelversion" in kod_lower:
        return "backend/pom.xml"

    # --- Backend: Spring konfiguráció ---
    if nyelv in ("properties", "yaml", "yml") or "spring.datasource" in kod_lower or "server.port=" in kod_lower:
        kit = ".properties" if "=" in kod and ":" not in kod.split("=")[0] else ".yml"
        if nyelv == "properties":
            kit = ".properties"
        elif nyelv in ("yaml", "yml"):
            kit = ".yml"
        return f"backend/src/main/resources/application{kit}"

    # --- Adatbázis ---
    if nyelv == "sql" or any(k in kod_lower for k in ("create table", "insert into", "drop table")):
        return None  # a hívó dönt a séma-fájlnévről

    # --- Frontend: package.json ---
    if nyelv == "json" or kod.strip().startswith("{"):
        try:
            adat = json.loads(kod)
        except (json.JSONDecodeError, ValueError):
            adat = None
        if isinstance(adat, dict):
            if "dependencies" in adat or "scripts" in adat:
                if "compilerOptions" in adat:
                    return "frontend/tsconfig.json"
                return "frontend/package.json"
            if "compilerOptions" in adat:
                return "frontend/tsconfig.json"
        return None

    # --- Frontend: HTML ---
    if nyelv == "html" or "<!doctype html" in kod_lower or "<html" in kod_lower:
        return "frontend/index.html"

    # --- Frontend: stíluslap ---
    if nyelv in ("css", "scss", "less") or kod.lstrip().startswith("@tailwind"):
        if "@tailwind" in kod_lower or "index.css" in kod_lower:
            return "frontend/src/index.css"
        return f"frontend/src/styles{NYELV_KITERJESZTES.get(nyelv, '.css')}"

    # --- Frontend: build-konfigurációk (nincs bennük exportált komponensnév!) ---
    # Ezeket a névfelismerés előtt kell kezelni, különben `Component_NN.jsx`-ként
    # landolnak, és a Vite sosem találja meg a saját konfigurációját.
    # Next.js konfiguráció – a gyökérbe tartozik, nem a komponensek közé.
    if "nextconfig" in kod_lower or "import('next').nextconfig" in kod_lower:
        return "frontend/next.config.ts" if nyelv in ("ts", "typescript") else "frontend/next.config.js"

    if "defineconfig" in kod_lower and "vite" in kod_lower:
        return "frontend/vite.config.ts" if "ts" in nyelv or ": " in kod else "frontend/vite.config.js"
    if "module.exports" in kod and "content:" in kod and ("theme" in kod_lower or "tailwind" in kod_lower):
        return "frontend/tailwind.config.js"
    if "module.exports" in kod and "plugins" in kod_lower and "autoprefixer" in kod_lower:
        return "frontend/postcss.config.js"

    # --- Frontend: React belépési pont ---
    if "createroot" in kod_lower or "reactdom.render" in kod_lower:
        return f"frontend/src/main{js_kiterjesztes(kod, nyelv)}"

    # --- Frontend: JS/TS modul ---
    if nyelv in ("js", "jsx", "ts", "tsx", "javascript", "typescript") or "import react" in kod_lower:
        nev = js_komponens_nev(kod)
        if not nev:
            return None
        kit = js_kiterjesztes(kod, nyelv)
        if nev.lower() == "app":
            return f"frontend/src/App{kit}"
        if nev.endswith("Store") or ("create(" in kod and "zustand" in kod_lower):
            # A Zustand store-ok hook-névvel (`useAuthStore`) is ide tartoznak.
            return f"frontend/src/lib/store/{nev}{kit}"
        if nev.endswith(("Service", "Api", "Client", "Tracker")):
            return f"frontend/src/services/{nev}{kit}"
        if nev.isupper():  # pl. ADJACENCY, POSITIONS – ezek konstansok, nem komponensek
            return f"frontend/src/constants/{nev}{kit}"
        return f"frontend/src/components/{nev}{kit}"

    return None


def package_json_scriptek(tartalom: str) -> Dict[str, str]:
    """Kiolvassa a package.json `scripts` blokkját (hibatűrően)."""
    try:
        adat = json.loads(tartalom)
    except (json.JSONDecodeError, ValueError):
        # Az LLM néha trailing commát hagy – egy egyszerű javítási kísérlet.
        try:
            adat = json.loads(re.sub(r",(\s*[}\]])", r"\1", tartalom))
        except (json.JSONDecodeError, ValueError):
            return {}
    scriptek = adat.get("scripts") if isinstance(adat, dict) else None
    return {str(k): str(v) for k, v in scriptek.items()} if isinstance(scriptek, dict) else {}


def framework_felismeres(scriptek: Dict[str, str], fuggosegek: Optional[Dict[str, str]] = None) -> str:
    """`'next'` | `'vite'` | `'cra'` | `'ismeretlen'`.

    A keretrendszer eldönti, milyen kapcsolókkal indul a dev/prod szerver —
    és ezek NEM cserélhetők fel. A Next.js `-H` / `-p` kapcsolót vár; ha
    Vite-stílusú `--host` / `--port` megy neki, azonnal hibával kilép.
    """
    fuggosegek = fuggosegek or {}
    minden = " ".join(scriptek.values()).lower()

    if "next" in fuggosegek or "next " in minden or minden.strip().startswith("next"):
        return "next"
    if "vite" in fuggosegek or "vite" in minden:
        return "vite"
    if "react-scripts" in fuggosegek or "react-scripts" in minden:
        return "cra"
    return "ismeretlen"


def indito_parancs(
    scriptek: Dict[str, str], fuggosegek: Optional[Dict[str, str]] = None
) -> Tuple[str, str]:
    """A ténylegesen létező, keretrendszer-helyes indítóparancs és a portja.

    Két külön hibát kerül el:
      * a régi Jenkinsfile fixen `npm start`-ot hívott, de a Vite-projekt
        `package.json`-jában csak `dev`/`build`/`preview` volt
        → `npm ERR! Missing script: start`;
      * a `--host 0.0.0.0 --port 3000` kapcsolópár Vite-specifikus — egy
        Next.js appot azonnal megöl (`next` a `-H` / `-p` alakot érti).
    """
    port = "3000"
    keret = framework_felismeres(scriptek, fuggosegek)

    if keret == "next":
        # `next build` után a `next start` a helyes produkciós indítás.
        if "start" in scriptek:
            return f"npm start -- -H 0.0.0.0 -p {port}", port
        return f"npx --yes next start -H 0.0.0.0 -p {port}", port

    if keret == "cra":
        # A CRA környezeti változókból veszi a hostot és a portot.
        return f"HOST=0.0.0.0 PORT={port} npm start", port

    if keret == "vite":
        # Szándékosan a `dev` az elsődleges: a `vite preview` csak akkor indul el,
        # ha a `dist/` már létezik – egy kimaradt build stage azonnal megölné.
        if "dev" in scriptek:
            return f"npm run dev -- --host 0.0.0.0 --port {port}", port
        if "preview" in scriptek:
            return f"npm run preview -- --host 0.0.0.0 --port {port}", port

    if "start" in scriptek:
        return "npm start", port
    if "dev" in scriptek:
        return f"npm run dev -- --host 0.0.0.0 --port {port}", port
    if "serve" in scriptek:
        return "npm run serve", port
    return f"npx --yes serve -s dist -l {port}", port


def van_build_script(scriptek: Dict[str, str]) -> bool:
    return "build" in scriptek


def sql_fajlnev(kod: str, index: int) -> str:
    """Beszédes séma-fájlnév a SQL tartalom alapján."""
    tabla = re.search(r"create\s+table\s+(?:if\s+not\s+exists\s+)?[`\"']?(\w+)", kod, re.IGNORECASE)
    if tabla:
        return f"database/{index:03d}__{tabla.group(1).lower()}.sql"
    return f"database/schema_{index}.sql"
