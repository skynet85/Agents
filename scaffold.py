# scaffold.py
"""Rögzített, tesztelt projektváz — a build-stabilitás alapja.

MIÉRT VOLT INSTABIL A RENDSZER
-------------------------------
Az LLM eddig NEM CSAK az alkalmazáskódot írta, hanem a teljes build-infrastruktúrát
is: `package.json`, `tsconfig.json`, `vite.config.ts`, `tailwind.config.js`,
`index.html`, `pom.xml`, `Jenkinsfile`. Ez a rész minden futásban más lett, és
minden futásban MÁSHOL tört el:

* #20 körül: `"@tailwindcss/vite": "^3.4.0"` — nem létező verzió → `npm install` ETARGET
* #22: `local max_retries=30` a health checkben → dash: `local: not in a function`
* #24: `@apply animate-in` a `tailwindcss-animate` plugin nélkül → PostCSS hiba

A hibák javítgatása egyesével fogócska volt: minden folt után a modell máshol
hallucinált. A megoldás nem újabb javítószabály, hanem az, hogy **elvesszük tőle
ezt a felelősséget**.

A MODELL
--------
Ez a modul egy verzió-pinnelt, ismerten működő vázat ad (React 18 + Vite 5 +
TypeScript + Tailwind 3 + Spring Boot 3.2 / Java 17). Ezek a fájlok **védettek**:
ha az ágens ilyen útvonalra ír, a rendszer eldobja a válaszát és jelzi neki.
Az ágensek csak a „slotokba" dolgoznak — komponensek, oldalak, service-ek,
controllerek. Így a build kimenetele nem lottó: az egyetlen változó az
alkalmazáskód, amit a sandbox fordítója amúgy is ellenőriz.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Set, Tuple

# ---------------------------------------------------------------------------
# Verzió-pinnelt függőségek (mind létező, egymással kompatibilis kiadás)
# ---------------------------------------------------------------------------
FRONTEND_DEPS = {
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "react-router-dom": "6.26.2",
    "zustand": "4.5.5",
}

FRONTEND_DEV_DEPS = {
    "@types/react": "18.3.11",
    "@types/react-dom": "18.3.1",
    "@vitejs/plugin-react": "4.3.2",
    "autoprefixer": "10.4.20",
    "postcss": "8.4.47",
    "tailwindcss": "3.4.13",
    # Ez adja az `animate-in`, `fade-in`, `slide-in-from-*` osztályokat, amiktől
    # a #24-es build elhasalt. Alapból része a váznak.
    "tailwindcss-animate": "1.0.7",
    "typescript": "5.6.2",
    "vite": "5.4.8",
}

# Amit az ágens ezen felül kérhet (`DEPENDENCY: <nev>` direktívával).
ENGEDELYEZETT_EXTRA_DEPS = {
    "axios": "1.7.7",
    "clsx": "2.1.1",
    "date-fns": "4.1.0",
    "lucide-react": "0.446.0",
    "recharts": "2.12.7",
    "react-hook-form": "7.53.0",
    "zod": "3.23.8",
    "@tanstack/react-query": "5.59.0",
}

# FIGYELEM: NEM 8080! A Jenkins maga a 8080-on figyel a konténerében, ezért a
# Spring Boot ott nem tud bindolni ("Port 8080 was already in use"), és a backend
# némán elhal — miközben a health check a Jenkins saját weboldalát látja élőnek.
BACKEND_PORT = "8081"
FRONTEND_PORT = "3000"
JAVA_VERSION = "17"
SPRING_BOOT_VERSION = "3.2.10"
BASE_PACKAGE = "com.app"


# ---------------------------------------------------------------------------
# Váz-fájlok
# ---------------------------------------------------------------------------
def _package_json(extra: Dict[str, str] | None = None) -> str:
    deps = dict(FRONTEND_DEPS)
    deps.update(extra or {})
    return json.dumps(
        {
            "name": "app-frontend",
            "private": True,
            "version": "1.0.0",
            "type": "module",
            "scripts": {
                "dev": "vite",
                "build": "vite build",
                "preview": "vite preview",
                "typecheck": "tsc --noEmit",
            },
            "dependencies": dict(sorted(deps.items())),
            "devDependencies": dict(sorted(FRONTEND_DEV_DEPS.items())),
        },
        indent=2,
        ensure_ascii=False,
    ) + "\n"


VITE_CONFIG = f"""import {{ defineConfig }} from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({{
  plugins: [react()],
  resolve: {{
    alias: {{ '@': path.resolve(__dirname, './src') }},
  }},
  server: {{
    host: '0.0.0.0',
    port: {FRONTEND_PORT},
    proxy: {{
      '/api': {{ target: 'http://localhost:{BACKEND_PORT}', changeOrigin: true }},
    }},
  }},
  preview: {{ host: '0.0.0.0', port: {FRONTEND_PORT} }},
}});
"""

# FONTOS: `noUnusedLocals`/`noUnusedParameters` szándékosan KI van kapcsolva —
# stílushiba nem törhet CI buildet. A `strict` viszont bekapcsolva marad.
TSCONFIG = """{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "allowSyntheticDefaultImports": true,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src"]
}
"""

TAILWIND_CONFIG = """/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: { extend: {} },
  plugins: [require('tailwindcss-animate')],
}
"""

POSTCSS_CONFIG = """export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
"""

INDEX_HTML = """<!DOCTYPE html>
<html lang="hu">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Alkalmazás</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
"""

MAIN_TSX = """import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
"""

# A `@tailwind` direktívákon kívül SEMMI nincs itt: az egyedi stílusokat az
# ágensek utility osztályokkal írják a JSX-be, nem `@apply`-jal.
INDEX_CSS = """@tailwind base;
@tailwind components;
@tailwind utilities;
"""

# A placeholder gépi felismeréséhez. Enélkül előfordult, hogy az ágens megírta a
# komponenseket, de az App.tsx-hez hozzá sem nyúlt – így a build zöld lett, az
# alkalmazás helyén viszont ez a váz-oldal jelent meg a böngészőben.
PLACEHOLDER_JELZO = "SCAFFOLD_PLACEHOLDER_APP"

APP_TSX_ALAP = f"""// {PLACEHOLDER_JELZO} — ezt a fájlt KÖTELEZŐ lecserélni a valódi alkalmazásra!
export default function App() {{
  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <h1 className="text-2xl font-semibold text-slate-800">Alkalmazás</h1>
      <p className="mt-2 text-slate-600">A fejlesztés folyamatban.</p>
    </div>
  );
}}
"""


def _pom_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>{SPRING_BOOT_VERSION}</version>
    <relativePath/>
  </parent>
  <groupId>{BASE_PACKAGE}</groupId>
  <artifactId>app-backend</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>{JAVA_VERSION}</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <!-- A health check ebből tudja MEGBÍZHATÓAN eldönteni, hogy tényleg a mi
         alkalmazásunk fut-e a porton (nem elég egy tetszőleges HTTP válasz). -->
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
"""


def _application_java() -> str:
    return f"""package {BASE_PACKAGE};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {{
    public static void main(String[] args) {{
        SpringApplication.run(Application.class, args);
    }}
}}
"""


def _cors_java() -> str:
    return f"""package {BASE_PACKAGE}.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {{
    @Override
    public void addCorsMappings(CorsRegistry registry) {{
        registry.addMapping("/api/**").allowedOriginPatterns("*").allowedMethods("*");
    }}
}}
"""


APPLICATION_PROPERTIES = f"""spring.application.name=app-backend
server.port={BACKEND_PORT}
management.endpoints.web.exposure.include=health
"""

GITIGNORE = """node_modules/
dist/
target/
*.log
.env
"""


# ---------------------------------------------------------------------------
# Váz összeállítása
# ---------------------------------------------------------------------------
def _java_ut(alkonyvtar: str, fajl: str) -> str:
    csomag = BASE_PACKAGE.replace(".", "/")
    kozep = f"/{alkonyvtar}" if alkonyvtar else ""
    return f"backend/src/main/java/{csomag}{kozep}/{fajl}"


def vaz_fajlok(extra_deps: Dict[str, str] | None = None) -> Dict[str, str]:
    """A teljes, build-képes projektváz."""
    return {
        # --- Frontend infrastruktúra ---
        "frontend/package.json": _package_json(extra_deps),
        "frontend/vite.config.ts": VITE_CONFIG,
        "frontend/tsconfig.json": TSCONFIG,
        "frontend/tailwind.config.js": TAILWIND_CONFIG,
        "frontend/postcss.config.js": POSTCSS_CONFIG,
        "frontend/index.html": INDEX_HTML,
        "frontend/src/main.tsx": MAIN_TSX,
        "frontend/src/index.css": INDEX_CSS,
        # --- Backend infrastruktúra ---
        "backend/pom.xml": _pom_xml(),
        _java_ut("", "Application.java"): _application_java(),
        _java_ut("config", "WebConfig.java"): _cors_java(),
        "backend/src/main/resources/application.properties": APPLICATION_PROPERTIES,
        # --- Egyéb ---
        ".gitignore": GITIGNORE,
    }


def alap_alkalmazas() -> Dict[str, str]:
    """Minimális, működő alkalmazás – az ágensek ezt KÖTELESEK felülírni."""
    return {"frontend/src/App.tsx": APP_TSX_ALAP}


# A sentinel bevezetése előtt mentett futásokhoz: a placeholder törzse alapján
# is felismerjük, hogy az App.tsx-hez nem nyúlt hozzá senki.
PLACEHOLDER_SZOVEG = "A fejlesztés folyamatban."


def placeholder_maradt(files: Dict[str, str]) -> bool:
    """Igaz, ha az App.tsx még mindig a váz üres placeholdere."""
    for utvonal, tartalom in files.items():
        if not utvonal.startswith("frontend/src/App."):
            continue
        if PLACEHOLDER_JELZO in tartalom:
            return True
        # Visszamenőleges felismerés: rövid fájl a placeholder szövegével.
        if PLACEHOLDER_SZOVEG in tartalom and len(tartalom) < 500:
            return True
    return False


# Az ágens NEM írhatja felül ezeket: a build stabilitása múlik rajtuk.
VEDETT_UTVONALAK: Set[str] = set(vaz_fajlok()) | {"Jenkinsfile"}

# Ezekre az útvonal-mintákra sem enged írni (bármilyen build-konfiguráció).
VEDETT_MINTAK = (
    re.compile(r"^frontend/(package(-lock)?\.json|tsconfig.*\.json|vite\.config\.[jt]s)$"),
    re.compile(r"^frontend/(tailwind|postcss|next)\.config\.[jt]s$"),
    re.compile(r"^frontend/index\.html$"),
    re.compile(r"^backend/pom\.xml$"),
    re.compile(r"^Jenkinsfile$"),
    re.compile(r"^\.gitignore$"),
)


def vedett(utvonal: str) -> bool:
    """Igaz, ha az útvonal a rögzített vázhoz tartozik."""
    if utvonal in VEDETT_UTVONALAK:
        return True
    return any(m.match(utvonal) for m in VEDETT_MINTAK)


# ---------------------------------------------------------------------------
# Függőség-kérés az ágenstől
# ---------------------------------------------------------------------------
DEPENDENCY_MINTA = re.compile(
    r"^\s*(?://|#|--)?\s*DEPENDENCY\s*:\s*([@\w./-]+)\s*$", re.MULTILINE | re.IGNORECASE
)


def kert_fuggosegek(szoveg: str) -> Tuple[Dict[str, str], List[str]]:
    """Feldolgozza a `DEPENDENCY: <csomag>` direktívákat.

    Csak az allowlistán szereplő csomagok engedélyezettek, rögzített verzióval —
    így az ágens nem tud kitalált verziószámot becsempészni.
    """
    engedett: Dict[str, str] = {}
    elutasitott: List[str] = []
    for nev in DEPENDENCY_MINTA.findall(szoveg or ""):
        if nev in ENGEDELYEZETT_EXTRA_DEPS:
            engedett[nev] = ENGEDELYEZETT_EXTRA_DEPS[nev]
        elif nev in FRONTEND_DEPS or nev in FRONTEND_DEV_DEPS:
            continue  # már a vázban van
        else:
            elutasitott.append(nev)
    return engedett, elutasitott


# ---------------------------------------------------------------------------
# CSS védelem
# ---------------------------------------------------------------------------
APPLY_MINTA = re.compile(r"^\s*@apply\b[^;]*;?\s*$", re.MULTILINE)


def tisztit_css(tartalom: str) -> Tuple[str, int]:
    """Eltávolítja az `@apply` sorokat a generált CSS-ből.

    A #24-es buildet pontosan ez ölte meg: `@apply animate-in` egy telepítetlen
    plugin osztályára hivatkozott, és a PostCSS az egész buildet megállította.
    Az `@apply` a Tailwind legtörékenyebb funkciója — egyetlen ismeretlen
    utility-név elég hozzá. Az ágensek a JSX-ben úgyis utility osztályokat
    használnak, ezért itt nincs rá szükség.
    """
    tisztitott, db = APPLY_MINTA.subn("", tartalom)
    return tisztitott, db


# ---------------------------------------------------------------------------
# Prompt-reprezentáció
# ---------------------------------------------------------------------------
def vaz_leiras() -> str:
    """Az ágens promptjába kerülő összefoglaló a rögzített vázról."""
    return f"""A projekt VÁZA KÉSZ ÉS ZÁROLT. Ezeket a fájlokat NE generáld újra,
mert a rendszer eldobja őket:
  frontend/package.json, tsconfig.json, vite.config.ts,
  tailwind.config.js, postcss.config.js, index.html, src/main.tsx, src/index.css
  backend/pom.xml, {BASE_PACKAGE}.Application, {BASE_PACKAGE}.config.WebConfig,
  application.properties, Jenkinsfile, .gitignore

ADOTT STACK (ne javasolj mást):
  Frontend: React 18 + Vite 5 + TypeScript + Tailwind 3 (a tailwindcss-animate
            plugin telepítve), belépési pont: src/main.tsx → src/App.tsx
  Backend:  Spring Boot {SPRING_BOOT_VERSION} + Java {JAVA_VERSION}, alapcsomag: {BASE_PACKAGE}
  A frontend a /api útvonalon proxyzik a backendre (port {BACKEND_PORT}).

TE EZEKET ÍRHATOD:
  frontend/src/App.tsx, frontend/src/components/*.tsx,
  frontend/src/pages/*.tsx, frontend/src/lib/*.ts, frontend/src/store/*.ts
  backend/src/main/java/{BASE_PACKAGE.replace('.', '/')}/controller|service|model|dto/*.java

⚠️ KÖTELEZŐ: a frontend/src/App.tsx jelenleg csak egy ÜRES PLACEHOLDER
   („A fejlesztés folyamatban”). EZT MINDIG ÍRD FELÜL, és rendereld belőle a
   megírt oldalakat/komponenseket – különben a felhasználó a kész alkalmazás
   helyett a placeholder oldalt látja a böngészőben.

SZABÁLYOK:
  1. CSS: NE használj @apply direktívát! Az utility osztályokat közvetlenül a
     JSX className attribútumába írd.
  2. Új npm csomag: írj külön sorba `DEPENDENCY: <csomagnev>`. Csak ezek
     engedélyezettek: {', '.join(sorted(ENGEDELYEZETT_EXTRA_DEPS))}.
     Verziószámot NE adj meg, azt a rendszer kezeli.
  3. A backend osztályok csomagja kötelezően {BASE_PACKAGE}-tal kezdődjön.
  4. A frontend a backendet a `/api/...` relatív útvonalon hívja (a proxy elintézi).
"""
