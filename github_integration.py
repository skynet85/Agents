# github_integration.py
"""Az ágensek által generált kód kinyerése és publikálása GitHubra.

Főbb változások a korábbi verzióhoz képest:
  * a feltöltés EGYETLEN commitban történik a Git Data API-val (korábban
    fájlonként külön commit ment ki, ami lassú volt és teleszemetelte a
    history-t, ráadásul félbeszakadva inkonzisztens állapotot hagyott);
  * útvonal-normalizálás (`..`, abszolút útvonalak kiszűrése);
  * a DevOps ágens által generált Jenkinsfile élvez elsőbbséget a beépített
    sablonnal szemben.
"""
from __future__ import annotations

import logging
import posixpath
import re
from typing import Any, Dict, List, Optional, Tuple

from github import Github, GithubException, InputGitTreeElement

import code_analysis
import jenkins_repair
import project_doctor

logger = logging.getLogger(__name__)

BT = chr(96) * 3
KODBLOKK_MINTA = re.compile(rf"{BT}([a-zA-Z0-9+#-]*)\s*\n?(.*?){BT}", re.DOTALL)

FAJLNEV_MINTA = re.compile(
    r"(?://|/\*|<!--|--|#).*?(?:File|Fájl|filepath|name)\s*.*?:\s*([\w./-]+\.\w+)",
    re.IGNORECASE,
)
FAJLNEV_KOMMENT_SOR = re.compile(
    r"(?://|/\*|<!--|--|#).*?(?:File|Fájl|filepath|name)\s*.*?:", re.IGNORECASE
)

FRONTEND_KITERJESZTESEK = (".jsx", ".js", ".ts", ".tsx", ".html", ".css", ".json", ".vue", ".svelte")
BACKEND_KITERJESZTESEK = (".java", ".xml", ".kt", ".properties", ".yml", ".yaml")


# ---------------------------------------------------------------------------
# Parsing segédfüggvények
# ---------------------------------------------------------------------------
def get_filename_from_block(block: str, default_name: str = "") -> str:
    """Felismeri a fájlneveket a kódblokk elején lévő kommentből."""
    match = FAJLNEV_MINTA.search(block[:1000])
    return match.group(1).strip() if match else default_name


def clean_filename(fname: str) -> str:
    """Kijavítja az AI által félregépelt fájlneveket és biztonságossá teszi az útvonalat."""
    if not fname:
        return ""

    # Gyakori AI-hallucináció: mindenhova odabiggyeszti a .java kiterjesztést.
    for helyes in (".jsx", ".js", ".json", ".html", ".css", ".ts", ".tsx"):
        fname = fname.replace(f"{helyes}.java", helyes)

    # Az összevont "backend/src/.../frontend/..." útvonalakból a frontend részt tartjuk meg.
    if "frontend/" in fname and "backend/" in fname:
        fname = fname[fname.find("frontend/"):]

    # Path traversal és abszolút útvonal kiszűrése.
    fname = fname.replace("\\", "/").lstrip("/")
    reszek = [r for r in fname.split("/") if r not in ("", ".", "..")]
    tisztitott = posixpath.normpath("/".join(reszek)) if reszek else ""
    return "" if tisztitott in (".", "/", "") else tisztitott


def clean_block_content(block: str) -> str:
    """Eltávolítja az első sort, ha az fájlnév-komment (különben eltörne a JSON/XML parser)."""
    lines = block.split("\n")
    if lines and FAJLNEV_KOMMENT_SOR.search(lines[0]):
        return "\n".join(lines[1:]).strip()
    return block.strip()


def _match_role(msg: dict, roles: List[str]) -> bool:
    szerep_nev = str(msg.get("szerep_nev", "")).lower()
    szerep = str(msg.get("szerep", "")).lower()
    return any(r.lower() in szerep_nev or r.lower() in szerep for r in roles if r)


def extract_all_blocks(messages: List[dict], roles: List[str]) -> List[str]:
    """Kinyeri az összes kódblokkot a megadott szerepekhez tartozó üzenetekből."""
    blocks: List[str] = []
    for msg in messages or []:
        if not _match_role(msg, roles):
            continue
        for _nyelv, tartalom in KODBLOKK_MINTA.findall(str(msg.get("szoveg", ""))):
            if tartalom.strip():
                blocks.append(tartalom)
    return blocks


def extract_blocks_with_lang(messages: List[dict], roles: List[str]) -> List[Tuple[str, str]]:
    """Mint az `extract_all_blocks`, de a kódblokk nyelvét is visszaadja."""
    talalatok: List[Tuple[str, str]] = []
    for msg in messages or []:
        if not _match_role(msg, roles):
            continue
        for nyelv, tartalom in KODBLOKK_MINTA.findall(str(msg.get("szoveg", ""))):
            if tartalom.strip():
                talalatok.append((nyelv.lower(), tartalom))
    return talalatok


# ---------------------------------------------------------------------------
# Besorolás
# ---------------------------------------------------------------------------
def _besorol(fname: str, block_lower: str) -> str:
    """Visszaadja: 'fe', 'be', 'db' vagy '' (ismeretlen)."""
    if fname:
        if fname.endswith(FRONTEND_KITERJESZTESEK):
            return "fe"
        if fname.endswith(BACKEND_KITERJESZTESEK):
            return "be"
        if fname.endswith(".sql"):
            return "db"

    if any(
        jel in block_lower
        for jel in ("import react", "from 'react'", "npm start", "tailwind", "const [")
    ) or ('"dependencies"' in block_lower and "{" in block_lower):
        return "fe"
    if any(
        jel in block_lower
        for jel in ("import org.springframework", "<project xmlns", "<dependencies>", "package com.")
    ):
        return "be"
    if any(jel in block_lower for jel in ("create table", "insert into", "drop table")):
        return "db"
    return ""


def _fe_utvonal(fname: str, block_lower: str, idx: int) -> str:
    if not fname:
        if "{" in block_lower and '"name"' in block_lower:
            return "frontend/package.json"
        if "<html" in block_lower or "<body" in block_lower:
            return "frontend/index.html"
        return f"frontend/src/Component_{idx}.jsx"
    if fname.startswith("frontend/"):
        return fname
    if fname.startswith("src/"):
        return f"frontend/{fname}"
    if any(k in fname for k in ("package.json", "index.html", "tailwind.config", "vite.config")):
        return f"frontend/{fname.split('/')[-1]}"
    return f"frontend/src/{fname.split('/')[-1]}"


def _be_utvonal(fname: str, block_lower: str, idx: int) -> str:
    if not fname:
        if "<project" in block_lower:
            return "backend/pom.xml"
        return f"backend/src/main/java/com/app/Class_{idx}.java"
    if fname.startswith("backend/"):
        return fname
    if fname == "pom.xml":
        return "backend/pom.xml"
    if "src/main" in fname:
        return f"backend/{fname}"
    return f"backend/src/main/java/com/app/{fname.split('/')[-1]}"


def _db_utvonal(fname: str, idx: int) -> str:
    if not fname:
        return f"database/schema_{idx}.sql"
    if fname.startswith("database/"):
        return fname
    return f"database/{fname.split('/')[-1]}"


def generate_readme_content(feladat: str, memoria: str) -> str:
    return (
        "# LLMOps Szimuláció Eredménye\n\n"
        f"## 🎯 Legutóbbi Üzleti Igény\n> {feladat}\n\n"
        "## 🤖 A Csapat Munkája és a Működés\n"
        "Ez a kódbázis egy többágenses (Multi-Agent) agilis LLMOps szimuláció végterméke.\n\n"
        "## 📂 Projekt Memória (Záró állapot)\n\n"
        f"{memoria}\n"
    )


def _vegleges_utvonal(fname: str, cleaned: str, nyelv: str, tipus: str, idx: int) -> str:
    """A fájl végleges repó-útvonala.

    Elsőbbségi sorrend:
      1. a kód tartalmából származtatott útvonal (Java `package` + osztálynév,
         JS/TS export név) – ez teszi fordíthatóvá a backendet és ez
         deduplikálja a több iterációban újragenerált fájlokat;
      2. a `// File:` kommentből olvasott név;
      3. típus szerinti fallback.
    """
    szarmaztatott = code_analysis.szarmaztatott_utvonal(cleaned, nyelv)

    # A Java útvonalat MINDIG a kódból vesszük: ha a komment és a `package`
    # deklaráció ellentmond, a fordító a `package`-nek hisz.
    if szarmaztatott and (szarmaztatott.endswith(".java") or not fname):
        return szarmaztatott

    if fname:
        if tipus == "fe":
            return _fe_utvonal(fname, cleaned.lower(), idx)
        if tipus == "be":
            return _be_utvonal(fname, cleaned.lower(), idx)
        return _db_utvonal(fname, idx)

    if szarmaztatott:
        return szarmaztatott
    if tipus == "db":
        return code_analysis.sql_fajlnev(cleaned, idx)

    # Se fájlnév-komment, se felismerhető export/osztály: ez szinte biztosan
    # egy félbehagyott kódtöredék vagy magyarázó részlet, nem önálló fájl.
    # Korábban ezekből lettek a `Component_36.jsx` / `Class_16.java` szemétfájlok.
    return ""


def collect_files(
    messages: List[dict], memoria: str, feladat: str
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Összegyűjti a feltöltendő fájlokat a chat-logból (legacy útvonal).

    A rögzített vázból indul, és a védett útvonalakat nem engedi felülírni —
    ugyanaz a szabály, mint a `VirtualWorkspace`-ben, hogy a régi futások
    újrapublikálása is build-képes projektet adjon.
    """
    import scaffold  # helyi import: elkerüli a körkörös függést

    files: Dict[str, str] = dict(scaffold.vaz_fajlok())
    files.update(scaffold.alap_alkalmazas())
    files["README.md"] = generate_readme_content(feladat, memoria)
    stat: Dict[str, Any] = {"fe": 0, "be": 0, "db": 0, "duplikatum": 0}

    it_roles = ["Frontend", "FE", "Backend", "BE", "Informatikus", "IT", "UX", "Designer"]
    for i, (nyelv, block) in enumerate(extract_blocks_with_lang(messages, it_roles)):
        cleaned = clean_block_content(block)
        if not cleaned:
            continue

        fname = clean_filename(get_filename_from_block(block))
        tipus = _besorol(fname or _nyelv_alapjan_nev(nyelv), cleaned.lower())
        if not tipus:
            continue

        utvonal = _vegleges_utvonal(fname, cleaned, nyelv, tipus, i)
        if not utvonal:
            continue  # felismerhetetlen töredék
        if scaffold.vedett(utvonal):
            continue  # a build-konfigurációt a váz adja, nem a chat-log

        if utvonal.endswith((".css", ".scss")):
            cleaned, _ = scaffold.tisztit_css(cleaned)
            if not cleaned.strip():
                continue

        if utvonal in files:
            # Egy későbbi iteráció felülírja a korábbit ugyanazon az útvonalon.
            stat["duplikatum"] += 1
        else:
            stat[tipus] += 1
        files[utvonal] = cleaned

    # --- Jenkinsfile: determinisztikusan generált (mint a finalize_files-nál) ---
    # Az ágens pipeline-ja nem kerül a repóba – minden korábbi build-bukás
    # (dash `local`, hiányzó `dir()`, rossz npm flag) onnan jött.
    files["Jenkinsfile"] = jenkins_repair.generalt_jenkinsfile(jenkins_repair.projekt_info(files))
    stat["jenkins_forras"] = "generalt"
    stat["jenkins_javitasok"] = []

    return files, stat


def _nyelv_alapjan_nev(nyelv: str) -> str:
    """Ál-fájlnév a fence-nyelvből, hogy a besorolás a kiterjesztést használhassa."""
    kit = code_analysis.NYELV_KITERJESZTES.get((nyelv or "").lower())
    return f"x{kit}" if kit else ""


# ---------------------------------------------------------------------------
# Feltöltés
# ---------------------------------------------------------------------------
def _push_single_commit(repo, files: Dict[str, str], commit_message: str) -> Optional[str]:
    """Egyetlen commitban tolja fel a fájlokat. `None`, ha nincs alap-commit."""
    branch = repo.default_branch or "main"
    try:
        ref = repo.get_git_ref(f"heads/{branch}")
    except GithubException:
        return None  # Üres repó – nincs mire ráfűzni a commitot.

    base_commit = repo.get_git_commit(ref.object.sha)
    elements = [
        InputGitTreeElement(path=path, mode="100644", type="blob", content=content)
        for path, content in files.items()
    ]
    tree = repo.create_git_tree(elements, base_commit.tree)
    commit = repo.create_git_commit(commit_message, tree, [base_commit])
    ref.edit(commit.sha)
    return commit.sha


def _push_file_by_file(repo, files: Dict[str, str], commit_message: str) -> None:
    """Fallback üres repóhoz: fájlonkénti create/update."""
    for path, content in files.items():
        try:
            meglevo = repo.get_contents(path)
            if isinstance(meglevo, list):  # könyvtár – nem írjuk felül
                continue
            repo.update_file(meglevo.path, commit_message, content, meglevo.sha)
        except GithubException as exc:
            if exc.status == 404:
                repo.create_file(path, commit_message, content)
            else:
                raise


def finalize_files(
    munkateruleti_fajlok: Dict[str, str], memoria: str, feladat: str, messages: List[dict]
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Kész fájlfához (VirtualWorkspace) illeszti a README-t és a Jenkinsfile-t.

    Előbb lefut a `project_doctor`, ami determinisztikusan build-képessé teszi a
    projektet (nem létező függőség-verziók, lógó tsconfig-hivatkozás, hiányzó
    Tailwind-konfiguráció, port-eltérés). Enélkül a Jenkins build már az
    `npm install`-nál elbukna.
    """
    files, doktor_naplo = project_doctor.javit(munkateruleti_fajlok)
    files["README.md"] = generate_readme_content(feladat, memoria)

    stat: Dict[str, Any] = {
        "fe": sum(1 for p in files if p.startswith("frontend/")),
        "be": sum(1 for p in files if p.startswith("backend/")),
        "db": sum(1 for p in files if p.startswith("database/")),
        "duplikatum": 0,
        "doktor_javitasok": doktor_naplo,
        "maradek_blokkolok": project_doctor.blokkolo_hibak(files),
    }

    # A Jenkinsfile determinisztikusan generálódik a TÉNYLEGES fájlfából.
    # Az ágens pipeline-ja nem kerül a repóba: minden korábbi build-bukás
    # (dash `local`, hiányzó `dir()`, rossz npm flag, néma háttérindítás) onnan jött.
    jenkinsfile = jenkins_repair.generalt_jenkinsfile(jenkins_repair.projekt_info(files))
    files["Jenkinsfile"] = jenkinsfile
    stat["jenkins_forras"] = "generalt"
    stat["jenkins_javitasok"] = []
    return files, stat


def push_to_github(
    token: str,
    repo_name: str,
    messages: List[dict],
    memoria: str,
    feladat: str,
    munkateruleti_fajlok: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str]:
    """Összegyűjti a fájlokat és feltölti a repóba. `(sikeres, üzenet)`.

    Ha `munkateruleti_fajlok` meg van adva (VirtualWorkspace), abból dolgozunk –
    ez a mérvadó projektállapot. Enélkül visszaesünk a chat-log alapú gyűjtésre
    (régi futások betöltése miatt kell).
    """
    if not token:
        return False, "Hiányzik a GitHub token."
    if not repo_name or "/" not in repo_name:
        return False, "A repository formátuma: felhasznalo/repo"

    if munkateruleti_fajlok:
        files, stat = finalize_files(munkateruleti_fajlok, memoria, feladat, messages)
    else:
        files, stat = collect_files(messages, memoria, feladat)

    # README + Jenkinsfile mindig van; ezeken felül kell tényleges forráskód.
    if stat["fe"] + stat["be"] + stat["db"] == 0:
        return False, "Nem találtam feltölthető forráskódot. Ellenőrizd az ágensek válaszait!"

    commit_message = f"🤖 Auto-commit: {str(feladat)[:60]}"

    try:
        repo = Github(token).get_repo(repo_name)
        if _push_single_commit(repo, files, commit_message) is None:
            _push_file_by_file(repo, files, commit_message)
    except GithubException as exc:
        if exc.status == 401:
            return False, "Hiba: Érvénytelen GitHub Token (Unauthorized)."
        if exc.status == 403:
            return False, "Hiba: A token nem rendelkezik írási joggal ehhez a repóhoz."
        if exc.status == 404:
            return False, f"Hiba: A repository ('{repo_name}') nem található vagy nincs hozzáférés."
        logger.exception("GitHub hiba")
        return False, f"GitHub hiba: {exc}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Váratlan hiba a feltöltés során")
        return False, f"Váratlan hiba történt: {exc}"

    uzenet = (
        f"Sikeres feltöltés egyetlen commitban! Összesen {len(files)} fájl "
        f"({stat['fe']} FE, {stat['be']} BE, {stat['db']} DB) frissült a repóban."
    )
    if stat.get("duplikatum"):
        uzenet += f" {stat['duplikatum']} duplikált blokk összevonva a valódi fájlnév alapján."

    forras_szoveg = {
        "agens-javitott": "a DevOps ágens Jenkinsfile-ja (automatikusan javítva)",
        "generalt": "determinisztikusan generált Jenkinsfile",
    }.get(stat.get("jenkins_forras", ""), "Jenkinsfile")
    uzenet += f"\n\n🔧 CI/CD: {forras_szoveg}."
    for javitas in stat.get("jenkins_javitasok", []):
        uzenet += f"\n   • {javitas}"

    if stat.get("doktor_javitasok"):
        uzenet += "\n\n🩺 Build-képességi javítások:"
        for javitas in stat["doktor_javitasok"]:
            uzenet += f"\n   • {javitas}"

    if stat.get("maradek_blokkolok"):
        uzenet += "\n\n⛔ FIGYELEM — automatikusan nem javítható build-blokkolók:"
        for hiba in stat["maradek_blokkolok"]:
            uzenet += f"\n   • {hiba}"

    return True, uzenet
