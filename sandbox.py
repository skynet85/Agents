# sandbox.py
"""Valódi build futtatása a generált kódon — az „igazságforrás".

MIÉRT EZ A LEGFONTOSABB LÉPÉS
------------------------------
A szimulációban eddig minden ágenst egy MÁSIK LLM véleménye minősített: a QA
elolvasta a kódot és prózában nyilatkozott róla. Egy valós csapatban a
visszajelzés a gépből jön — lefordul, lefut, zöld a teszt.

Ez a modul teszi meg ezt a lépést: a `VirtualWorkspace` tartalmát kiírja egy
ideiglenes könyvtárba, lefuttatja rajta a valódi fordítót, és a NYERS
fordítói hibaüzenetet adja vissza, amit az IT ágens promptjába illesztünk.

Fokozatos degradáció: Docker → lokális eszközök → kihagyva. A szimuláció
soha nem áll meg attól, hogy nincs telepítve Docker.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import config

logger = logging.getLogger(__name__)

# Az LLM promptjába kerülő hibák maximális száma és hossza.
MAX_HIBA = 15
MAX_HIBA_HOSSZ = 300
MAX_NYERS_KIMENET = 4000


# ---------------------------------------------------------------------------
# Eredmény
# ---------------------------------------------------------------------------
@dataclass
class BuildEredmeny:
    """Egyetlen build kimenete."""

    cel: str  # 'frontend' | 'backend'
    sikeres: bool
    kihagyva: bool = False
    indok: str = ""
    hibak: List[str] = field(default_factory=list)
    nyers_kimenet: str = ""
    idotartam: float = 0.0
    parancs: str = ""

    @property
    def osszefoglalo(self) -> str:
        if self.kihagyva:
            return f"{self.cel}: kihagyva ({self.indok})"
        allapot = "✅ sikeres" if self.sikeres else f"❌ {len(self.hibak)} hiba"
        return f"{self.cel}: {allapot} ({self.idotartam:.1f}s)"


@dataclass
class SandboxEredmeny:
    """A teljes build ciklus eredménye."""

    motor: str = "kihagyva"  # 'docker' | 'lokalis' | 'kihagyva'
    reszek: List[BuildEredmeny] = field(default_factory=list)

    @property
    def futott(self) -> bool:
        return any(not r.kihagyva for r in self.reszek)

    @property
    def sikeres(self) -> bool:
        futottak = [r for r in self.reszek if not r.kihagyva]
        return bool(futottak) and all(r.sikeres for r in futottak)

    @property
    def hibak(self) -> List[str]:
        ki: List[str] = []
        for r in self.reszek:
            if not r.kihagyva and not r.sikeres:
                ki.extend(f"[{r.cel}] {h}" for h in r.hibak)
        return ki

    def prompt_reszlet(self) -> str:
        """A fordítói hibák tömör, LLM-nek adható formája."""
        if self.sikeres or not self.futott:
            return ""
        sorok = ["A VALÓDI FORDÍTÁS ELBUKOTT. Az alábbi hibákat a fordító adta:"]
        for r in self.reszek:
            if r.kihagyva or r.sikeres:
                continue
            sorok.append(f"\n--- {r.cel.upper()} ({r.parancs}) ---")
            if r.hibak:
                sorok.extend(f"  {h}" for h in r.hibak[:MAX_HIBA])
            else:
                sorok.append(f"  {r.nyers_kimenet[-1500:]}")
        return "\n".join(sorok)


# ---------------------------------------------------------------------------
# Motor felismerése
# ---------------------------------------------------------------------------
def docker_elerheto() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            timeout=10,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def elerheto_motor() -> str:
    """`'docker'`, `'lokalis'` vagy `'kihagyva'` — a konfiguráció és a gép alapján."""
    mod = getattr(config, "SANDBOX_MOD", "auto")
    if mod == "off":
        return "kihagyva"
    if mod in ("docker", "lokalis"):
        return mod
    if docker_elerheto():
        return "docker"
    if shutil.which("npm") or shutil.which("mvn"):
        return "lokalis"
    return "kihagyva"


def motor_leirasa() -> str:
    return {
        "docker": "Docker (izolált konténer)",
        "lokalis": "lokális npm / mvn",
        "kihagyva": "nincs elérhető build eszköz",
    }.get(elerheto_motor(), "ismeretlen")


# ---------------------------------------------------------------------------
# Hibakinyerés
# ---------------------------------------------------------------------------
TS_HIBA = re.compile(r"^(?P<fajl>[\w./\\-]+)\((?P<sor>\d+),(?P<oszlop>\d+)\):\s*(?P<uz>error TS\d+:.*)$", re.MULTILINE)
TS_HIBA_ALT = re.compile(r"^(?P<fajl>[\w./\\-]+):(?P<sor>\d+):(?P<oszlop>\d+)\s*-\s*(?P<uz>error TS\d+:.*)$", re.MULTILINE)
MVN_HIBA = re.compile(r"^\[ERROR\]\s+(?P<fajl>[^\s:]+\.java):\[(?P<sor>\d+),(?P<oszlop>\d+)\]\s*(?P<uz>.*)$", re.MULTILINE)
MVN_ALT = re.compile(r"^\[ERROR\]\s+(?P<uz>.+)$", re.MULTILINE)
VITE_HIBA = re.compile(r"^(?:error during build:|\[vite\]:?)\s*(?P<uz>.+)$", re.MULTILINE | re.IGNORECASE)
NPM_HIBA = re.compile(r"^npm ERR!\s+(?P<uz>.+)$", re.MULTILINE)


def _roviditett(szoveg: str) -> str:
    szoveg = " ".join(szoveg.split())
    return szoveg if len(szoveg) <= MAX_HIBA_HOSSZ else szoveg[:MAX_HIBA_HOSSZ] + "…"


def hibak_kinyerese(kimenet: str, cel: str) -> List[str]:
    """Strukturált hibalista a nyers fordítói kimenetből."""
    hibak: List[str] = []

    if cel == "frontend":
        for minta in (TS_HIBA, TS_HIBA_ALT):
            for m in minta.finditer(kimenet):
                hibak.append(_roviditett(f"{m.group('fajl')}:{m.group('sor')} — {m.group('uz')}"))
        if not hibak:
            hibak.extend(_roviditett(m.group("uz")) for m in VITE_HIBA.finditer(kimenet))
        if not hibak:
            npm = [_roviditett(m.group("uz")) for m in NPM_HIBA.finditer(kimenet)]
            hibak.extend(h for h in npm if not h.startswith(("A complete log", "code ")))
    else:
        for m in MVN_HIBA.finditer(kimenet):
            hibak.append(_roviditett(f"{m.group('fajl')}:{m.group('sor')} — {m.group('uz')}"))
        if not hibak:
            for m in MVN_ALT.finditer(kimenet):
                uz = m.group("uz").strip()
                if uz and not uz.startswith(("To see the full", "Re-run Maven", "For more information", "->", "[Help")):
                    hibak.append(_roviditett(uz))

    # Duplikátumok kiszűrése a sorrend megtartásával.
    return list(dict.fromkeys(hibak))[:MAX_HIBA]


# ---------------------------------------------------------------------------
# Futtatás
# ---------------------------------------------------------------------------
def _futtat(parancs: List[str], munkakonyvtar: Path, timeout: int) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            parancs,
            cwd=str(munkakonyvtar),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"A build túllépte a(z) {timeout} másodperces időkorlátot."
    except OSError as exc:
        return 127, f"A parancs nem futtatható: {exc}"


def _docker_parancs(gyoker: Path, cel: str) -> List[str]:
    kozos = ["docker", "run", "--rm", "-v", f"{gyoker}:/app"]
    if cel == "frontend":
        return kozos + [
            "-v", "llmops_npm_cache:/root/.npm",
            "-w", "/app/frontend",
            config.SANDBOX_NODE_IMAGE,
            "sh", "-lc",
            # FIGYELEM: itt NEM használhatunk `|| true`-t a tsc körül, mert az
            # elnyelné a típushibákat, és a build hamisan sikeresnek látszana.
            # Az `if`-es forma csak akkor hagyja ki a lépést, ha nincs tsconfig.
            "set -e; "
            "npm install --no-audit --no-fund --loglevel=error; "
            "if [ -f tsconfig.json ]; then npx --yes tsc --noEmit; fi; "
            "npm run build --if-present",
        ]
    return kozos + [
        "-v", "llmops_m2_cache:/root/.m2",
        "-w", "/app/backend",
        config.SANDBOX_MAVEN_IMAGE,
        "mvn", "-B", "-ntp", "compile",
    ]


def _lokalis_parancs(cel: str) -> Optional[List[str]]:
    if cel == "frontend":
        if not shutil.which("npm"):
            return None
        return ["npm", "install", "--no-audit", "--no-fund", "--loglevel=error"]
    if not shutil.which("mvn"):
        return None
    return ["mvn", "-B", "-ntp", "compile"]


def _ir_fajlfa(files: Dict[str, str], gyoker: Path) -> None:
    for utvonal, tartalom in files.items():
        cel = gyoker / utvonal
        cel.parent.mkdir(parents=True, exist_ok=True)
        cel.write_text(tartalom, encoding="utf-8")


def _build_resz(gyoker: Path, cel: str, motor: str, files: Dict[str, str]) -> BuildEredmeny:
    leiro = "frontend/package.json" if cel == "frontend" else "backend/pom.xml"
    if leiro not in files:
        return BuildEredmeny(cel=cel, sikeres=True, kihagyva=True, indok=f"nincs {leiro}")

    timeout = config.SANDBOX_TIMEOUT_FRONTEND if cel == "frontend" else config.SANDBOX_TIMEOUT_BACKEND

    if motor == "docker":
        parancs = _docker_parancs(gyoker, cel)
        munkakonyvtar = gyoker
    else:
        parancs = _lokalis_parancs(cel)
        if parancs is None:
            eszkoz = "npm" if cel == "frontend" else "mvn"
            return BuildEredmeny(cel=cel, sikeres=True, kihagyva=True, indok=f"nincs telepítve {eszkoz}")
        munkakonyvtar = gyoker / cel

    kezdet = time.time()
    kod, kimenet = _futtat(parancs, munkakonyvtar, timeout)
    eltelt = time.time() - kezdet

    # Lokális frontend módban az install után külön futtatjuk a típusellenőrzést.
    if motor == "lokalis" and cel == "frontend" and kod == 0 and "frontend/tsconfig.json" in files:
        kod2, kimenet2 = _futtat(["npx", "--yes", "tsc", "--noEmit"], munkakonyvtar, timeout)
        kimenet += "\n" + kimenet2
        kod = kod or kod2
        eltelt = time.time() - kezdet

    return BuildEredmeny(
        cel=cel,
        sikeres=(kod == 0),
        hibak=[] if kod == 0 else hibak_kinyerese(kimenet, cel),
        nyers_kimenet=kimenet[-MAX_NYERS_KIMENET:],
        idotartam=eltelt,
        parancs=" ".join(parancs[-3:]) if motor == "docker" else " ".join(parancs),
    )


def build(files: Dict[str, str], celok: Optional[List[str]] = None) -> SandboxEredmeny:
    """Lefuttatja a valódi buildet a fájlfán.

    Sosem dob kivételt: hiba esetén `kihagyva` státusszal tér vissza, hogy a
    szimuláció mindenképpen tovább tudjon menni.
    """
    motor = elerheto_motor()
    eredmeny = SandboxEredmeny(motor=motor)
    celok = celok or ["frontend", "backend"]

    if motor == "kihagyva" or not files:
        eredmeny.reszek = [
            BuildEredmeny(cel=c, sikeres=True, kihagyva=True, indok="nincs build motor") for c in celok
        ]
        return eredmeny

    try:
        with tempfile.TemporaryDirectory(prefix="llmops_build_") as tmp:
            gyoker = Path(tmp).resolve()
            _ir_fajlfa(files, gyoker)
            for cel in celok:
                eredmeny.reszek.append(_build_resz(gyoker, cel, motor, files))
    except OSError as exc:
        logger.exception("A sandbox build nem futtatható")
        eredmeny.reszek = [
            BuildEredmeny(cel=c, sikeres=True, kihagyva=True, indok=f"I/O hiba: {exc}") for c in celok
        ]

    return eredmeny
