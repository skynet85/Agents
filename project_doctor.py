# project_doctor.py
"""A generált projekt build-képessé tétele — Jenkins-orientált diagnózis és javítás.

MIÉRT KELL EZ A JENKINSFILE-JAVÍTÁSON FELÜL
--------------------------------------------
A `jenkins_repair` a pipeline-t javítja, a `sandbox` pedig visszajelzést ad a
fordítótól. Egyik sem segít, ha MAGA A PROJEKT nem építhető. A valós futás
elemzése öt ilyen blokkolót mutatott ki — mindegyik a `npm install` vagy a
`tsc -b` első másodpercében megöli a Jenkins buildet:

1. **Nem létező függőség-verzió.** `"@tailwindcss/vite": "^3.4.0"` — ez a csomag
   csak 4.x-ben létezik (a Tailwind v4 Vite-pluginja). `npm install` →
   `ETARGET No matching version found` → a frontend build el sem indul.
2. **Inkoherens Tailwind-setup.** Egyszerre volt jelen a v4-es `@tailwindcss/vite`
   és a v3-as `tailwindcss` + `postcss` + `autoprefixer`, `tailwind.config.js` és
   `postcss.config.js` viszont sehol — így a `@tailwind base;` direktíva
   feldolgozatlan marad.
3. **Lógó tsconfig-hivatkozás.** A `tsconfig.json` hivatkozik a
   `./tsconfig.node.json` fájlra, ami nem létezik → `tsc -b` →
   `error TS6053: File 'tsconfig.node.json' not found`.
4. **CI-t törő stílusszabályok.** `noUnusedLocals` + `noUnusedParameters` mellett
   egyetlen elfelejtett import is piros buildet okoz. LLM által generált kódnál
   ez gyakorlatilag garantált bukás.
5. **Port-eltérés.** A Vite proxy a 8080-ra mutatott, a Jenkins deploy viszont a
   8081-en indította a backendet → a frontend nem érte el az API-t.

A javítások determinisztikusak és naplózottak: a felhasználó pontosan látja,
mihez nyúlt a rendszer.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Alapértelmezett backend port, ha az application.properties nem mond mást.
ALAP_BACKEND_PORT = "8080"

# Csomagok, ahol az LLM rendszeresen nem létező verziót hallucinál.
# (csomagnév -> legkisebb létező major verzió)
MINIMALIS_MAJOR = {
    "@tailwindcss/vite": 4,
    "@tailwindcss/postcss": 4,
}

TAILWIND_V3_POSTCSS = """export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
"""

TAILWIND_V3_CONFIG = """/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: { extend: {} },
  plugins: [],
}
"""

TSCONFIG_NODE = """{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
"""


@dataclass
class Diagnozis:
    """Egyetlen megállapítás a projektről."""

    kod: str
    uzenet: str
    blokkolo: bool  # True: a Jenkins build biztosan elbukik tőle
    javithato: bool = True

    def __str__(self) -> str:
        jel = "⛔" if self.blokkolo else "⚠️"
        return f"{jel} {self.uzenet}"


# ---------------------------------------------------------------------------
# Segédfüggvények
# ---------------------------------------------------------------------------
def _json_betolt(szoveg: str) -> Optional[dict]:
    """Hibatűrő JSON-olvasás (az LLM gyakran hagy trailing commát/kommentet)."""
    for jelolt in (szoveg, re.sub(r",(\s*[}\]])", r"\1", szoveg or "")):
        try:
            adat = json.loads(jelolt)
            if isinstance(adat, dict):
                return adat
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    # JSONC: sorvégi // kommentek eltávolítása
    try:
        tiszta = re.sub(r"^\s*//.*$", "", szoveg or "", flags=re.MULTILINE)
        adat = json.loads(re.sub(r",(\s*[}\]])", r"\1", tiszta))
        return adat if isinstance(adat, dict) else None
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def _major(verzio: str) -> Optional[int]:
    talalat = re.search(r"(\d+)", verzio or "")
    return int(talalat.group(1)) if talalat else None


def backend_port(files: Dict[str, str]) -> str:
    """A backend tényleges portja az application.properties/yml alapján."""
    for nev in ("application.properties", "application.yml", "application.yaml"):
        tartalom = files.get(f"backend/src/main/resources/{nev}")
        if not tartalom:
            continue
        talalat = re.search(r"^\s*server\.port\s*[=:]\s*(\d+)", tartalom, re.MULTILINE)
        if talalat:
            return talalat.group(1)
        talalat = re.search(r"^\s*port\s*:\s*(\d+)", tartalom, re.MULTILINE)
        if talalat:
            return talalat.group(1)
    return ALAP_BACKEND_PORT


# ---------------------------------------------------------------------------
# Diagnózis
# ---------------------------------------------------------------------------
def _diag_package_json(files: Dict[str, str], ki: List[Diagnozis]) -> None:
    nyers = files.get("frontend/package.json")
    if nyers is None:
        return
    pkg = _json_betolt(nyers)
    if pkg is None:
        ki.append(Diagnozis("pkg_json_hibas", "A frontend/package.json nem érvényes JSON", True, False))
        return

    fuggosegek = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

    for nev, min_major in MINIMALIS_MAJOR.items():
        if nev not in fuggosegek:
            continue
        major = _major(str(fuggosegek[nev]))
        if major is not None and major < min_major:
            ki.append(
                Diagnozis(
                    "nemletezo_verzio",
                    f"`{nev}: {fuggosegek[nev]}` — ez a csomag csak {min_major}.x-től létezik, "
                    "az `npm install` ETARGET hibával elbukik",
                    True,
                )
            )

    tw = fuggosegek.get("tailwindcss")
    if tw and "@tailwindcss/vite" in fuggosegek and (_major(str(tw)) or 4) < 4:
        ki.append(
            Diagnozis(
                "tailwind_keverek",
                "Kevert Tailwind-setup: v3-as `tailwindcss` és v4-es `@tailwindcss/vite` együtt",
                True,
            )
        )

    if tw and (_major(str(tw)) or 4) < 4:
        if "frontend/postcss.config.js" not in files and "frontend/postcss.config.cjs" not in files:
            ki.append(
                Diagnozis(
                    "hianyzo_postcss",
                    "Tailwind v3 van használatban, de nincs `postcss.config.js` — "
                    "a `@tailwind` direktívák feldolgozatlanok maradnak",
                    False,
                )
            )
        if not any(p.startswith("frontend/tailwind.config") for p in files):
            ki.append(
                Diagnozis("hianyzo_tailwind_config", "Hiányzik a `tailwind.config.js`", False)
            )

    if not pkg.get("scripts"):
        ki.append(Diagnozis("nincs_script", "A package.json-ban nincs egyetlen `scripts` bejegyzés sem", True))


def _diag_tsconfig(files: Dict[str, str], ki: List[Diagnozis]) -> None:
    nyers = files.get("frontend/tsconfig.json")
    if nyers is None:
        return
    ts = _json_betolt(nyers)
    if ts is None:
        ki.append(Diagnozis("tsconfig_hibas", "A frontend/tsconfig.json nem érvényes JSON", True, False))
        return

    for hivatkozas in ts.get("references", []) or []:
        utvonal = str(hivatkozas.get("path", "")).lstrip("./")
        if utvonal and f"frontend/{utvonal}" not in files:
            ki.append(
                Diagnozis(
                    "logo_tsconfig_ref",
                    f"A tsconfig hivatkozik a `{utvonal}` fájlra, ami nem létezik → "
                    "`tsc -b` error TS6053",
                    True,
                )
            )

    co = ts.get("compilerOptions", {}) or {}
    szigoru = [k for k in ("noUnusedLocals", "noUnusedParameters") if co.get(k)]
    if szigoru:
        ki.append(
            Diagnozis(
                "ci_toro_stilusszabaly",
                f"`{'`, `'.join(szigoru)}` bekapcsolva — egyetlen felesleges import is "
                "piros buildet okoz",
                False,
            )
        )

    # A Next.js natívan feloldja a tsconfig `paths` aliasait – ott ez nem hiba.
    pkg = _json_betolt(files.get("frontend/package.json", "")) or {}
    next_projekt = "next" in {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

    if (
        not next_projekt
        and co.get("paths")
        and "resolve" not in (files.get("frontend/vite.config.ts", "") + files.get("frontend/vite.config.js", ""))
    ):
        hasznal_aliast = any(
            re.search(r"""from\s+['"]@/""", tartalom)
            for utvonal, tartalom in files.items()
            if utvonal.startswith("frontend/src")
        )
        if hasznal_aliast:
            ki.append(
                Diagnozis(
                    "hianyzo_vite_alias",
                    "A tsconfig `paths` aliast definiál, a vite.config viszont nem — "
                    "a `tsc` átmegy, a `vite build` elbukik",
                    True,
                )
            )


def _diag_pom(files: Dict[str, str], ki: List[Diagnozis]) -> None:
    pom = files.get("backend/pom.xml")
    if pom is None:
        return
    try:
        ET.fromstring(pom)
    except ET.ParseError as exc:
        ki.append(Diagnozis("pom_hibas", f"A pom.xml nem érvényes XML: {exc}", True, False))
        return

    if "spring-boot-maven-plugin" not in pom and "spring-boot-starter" in pom:
        ki.append(
            Diagnozis(
                "nincs_bootplugin",
                "Hiányzik a `spring-boot-maven-plugin` — a `mvn spring-boot:run` deploy elbukik",
                True,
            )
        )
    if "<modelVersion>" not in pom:
        ki.append(Diagnozis("pom_csonka", "A pom.xml-ből hiányzik a `<modelVersion>`", True, False))


def _diag_port(files: Dict[str, str], ki: List[Diagnozis]) -> None:
    vite = files.get("frontend/vite.config.ts") or files.get("frontend/vite.config.js")
    if not vite:
        return
    talalat = re.search(r"target:\s*['\"]http://localhost:(\d+)", vite)
    if not talalat:
        return
    proxy_port = talalat.group(1)
    valodi = backend_port(files)
    if proxy_port != valodi:
        ki.append(
            Diagnozis(
                "port_elteres",
                f"A Vite proxy a {proxy_port}-as portra mutat, a backend viszont a "
                f"{valodi}-as porton indul — a frontend nem éri el az API-t",
                False,
            )
        )


def diagnosztizal(files: Dict[str, str]) -> List[Diagnozis]:
    """Végigfuttatja az összes build-képességi ellenőrzést."""
    ki: List[Diagnozis] = []
    if not files:
        return ki
    _diag_package_json(files, ki)
    _diag_tsconfig(files, ki)
    _diag_pom(files, ki)
    _diag_port(files, ki)
    return ki


# ---------------------------------------------------------------------------
# Javítás
# ---------------------------------------------------------------------------
def _javit_package_json(files: Dict[str, str], naplo: List[str]) -> None:
    nyers = files.get("frontend/package.json")
    if nyers is None:
        return
    pkg = _json_betolt(nyers)
    if pkg is None:
        return

    valtozott = False
    deps = pkg.setdefault("dependencies", {})
    devdeps = pkg.setdefault("devDependencies", {})
    egyben = {**deps, **devdeps}

    tw_major = _major(str(egyben.get("tailwindcss", ""))) if "tailwindcss" in egyben else None

    for nev, min_major in MINIMALIS_MAJOR.items():
        if nev not in egyben:
            continue
        major = _major(str(egyben[nev]))
        if major is None or major >= min_major:
            continue
        # A v3-as Tailwind-lánchoz a v4-es plugin nem kell: eltávolítjuk.
        deps.pop(nev, None)
        devdeps.pop(nev, None)
        naplo.append(f"`{nev}` eltávolítva a package.json-ból (nem létező {egyben[nev]} verzió)")
        valtozott = True

    if tw_major is not None and tw_major < 4:
        for szukseges, verzio in (("postcss", "^8.4.32"), ("autoprefixer", "^10.4.16")):
            if szukseges not in egyben:
                devdeps[szukseges] = verzio
                naplo.append(f"`{szukseges}` hozzáadva (Tailwind v3 PostCSS-lánc)")
                valtozott = True

    if not pkg.get("scripts"):
        pkg["scripts"] = {"dev": "vite", "build": "vite build", "preview": "vite preview"}
        naplo.append("Alapértelmezett `scripts` blokk beillesztve a package.json-ba")
        valtozott = True

    if valtozott:
        files["frontend/package.json"] = json.dumps(pkg, indent=2, ensure_ascii=False) + "\n"


def _javit_vite_config(files: Dict[str, str], naplo: List[str]) -> None:
    for nev in ("frontend/vite.config.ts", "frontend/vite.config.js"):
        vite = files.get(nev)
        if not vite:
            continue

        pkg = _json_betolt(files.get("frontend/package.json", "")) or {}
        egyben = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

        # A már eltávolított v4-es plugin importját és használatát is ki kell venni.
        if "@tailwindcss/vite" not in egyben and "@tailwindcss/vite" in vite:
            vite = re.sub(r"^\s*import\s+\w+\s+from\s+['\"]@tailwindcss/vite['\"];?\s*$\n?", "", vite, flags=re.MULTILINE)
            vite = re.sub(r",?\s*tailwindcss\(\)", "", vite)
            naplo.append("`@tailwindcss/vite` import és plugin-hívás eltávolítva a vite.configból")

        # Proxy port igazítása a backend tényleges portjához.
        # FIGYELEM: csak akkor naplózunk, ha a tartalom TÉNYLEGESEN változott —
        # a `subn` a találatot számolja, nem az eltérést (idempotencia).
        valodi = backend_port(files)
        uj = re.sub(r"(target:\s*['\"]http://localhost:)\d+", rf"\g<1>{valodi}", vite)
        if uj != vite:
            vite = uj
            naplo.append(f"A Vite proxy célportja {valodi}-ra igazítva (backend tényleges portja)")

        files[nev] = vite


def _javit_tsconfig(files: Dict[str, str], naplo: List[str]) -> None:
    nyers = files.get("frontend/tsconfig.json")
    if nyers is None:
        return
    ts = _json_betolt(nyers)
    if ts is None:
        return

    valtozott = False

    megmarado = []
    for hivatkozas in ts.get("references", []) or []:
        utvonal = str(hivatkozas.get("path", "")).lstrip("./")
        teljes = f"frontend/{utvonal}"
        if not utvonal or teljes in files:
            megmarado.append(hivatkozas)
            continue
        if utvonal == "tsconfig.node.json":
            files[teljes] = TSCONFIG_NODE
            megmarado.append(hivatkozas)
            naplo.append("Hiányzó `tsconfig.node.json` létrehozva (a `tsc -b` enélkül elbukik)")
        else:
            naplo.append(f"Lógó tsconfig-hivatkozás eltávolítva: `{utvonal}`")
        valtozott = True
    if valtozott:
        if megmarado:
            ts["references"] = megmarado
        else:
            ts.pop("references", None)

    co = ts.setdefault("compilerOptions", {})
    for kapcsolo in ("noUnusedLocals", "noUnusedParameters"):
        if co.get(kapcsolo):
            co[kapcsolo] = False
            naplo.append(f"`{kapcsolo}` kikapcsolva (stílushiba nem törhet buildet)")
            valtozott = True

    if valtozott:
        files["frontend/tsconfig.json"] = json.dumps(ts, indent=2, ensure_ascii=False) + "\n"


def _javit_tailwind_lanc(files: Dict[str, str], naplo: List[str]) -> None:
    pkg = _json_betolt(files.get("frontend/package.json", "")) or {}
    egyben = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    if "tailwindcss" not in egyben:
        return
    if (_major(str(egyben["tailwindcss"])) or 4) >= 4:
        return  # v4: nem kell külön config

    if not any(p.startswith("frontend/postcss.config") for p in files):
        files["frontend/postcss.config.js"] = TAILWIND_V3_POSTCSS
        naplo.append("`postcss.config.js` létrehozva (Tailwind v3 direktívák feldolgozásához)")
    if not any(p.startswith("frontend/tailwind.config") for p in files):
        files["frontend/tailwind.config.js"] = TAILWIND_V3_CONFIG
        naplo.append("`tailwind.config.js` létrehozva")


def javit(files: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    """Determinisztikusan build-képessé teszi a projektet.

    Nem módosítja a bemenetet: új szótárral és a változások naplójával tér vissza.
    """
    javitott = dict(files)
    naplo: List[str] = []
    if not javitott:
        return javitott, naplo

    _javit_package_json(javitott, naplo)
    _javit_vite_config(javitott, naplo)
    _javit_tsconfig(javitott, naplo)
    _javit_tailwind_lanc(javitott, naplo)
    return javitott, naplo


def blokkolo_hibak(files: Dict[str, str]) -> List[str]:
    """Csak a biztosan build-törő megállapítások, szövegesen."""
    return [d.uzenet for d in diagnosztizal(files) if d.blokkolo]
