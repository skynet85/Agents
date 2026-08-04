# tests/test_core.py
"""Streamlit- és hálózatfüggetlen tesztek a javított logikára.

Futtatás:  python3 tests/test_core.py
(A külső csomagokat – streamlit, langchain, github – stubolja, hogy a tiszta
logika CI-ben, telepített LLM-stack nélkül is ellenőrizhető legyen.)
"""
from __future__ import annotations

import string
import sys
import types
from pathlib import Path

GYOKER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GYOKER))

# Windows-konzol UTF-8 vedelem: a ✓/✗/ékezetek ne dobjanak UnicodeEncodeError-t
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


# ---------------------------------------------------------------------------
# Stubok a nehéz külső függőségekhez
# ---------------------------------------------------------------------------
def _stub(nev: str, **attrs) -> None:
    modul = types.ModuleType(nev)
    for k, v in attrs.items():
        setattr(modul, k, v)
    sys.modules[nev] = modul


class _InputGitTreeElement:
    def __init__(self, path="", mode="", type="", content=""):
        self.path, self.mode, self.type, self.content = path, mode, type, content


class _GithubException(Exception):
    def __init__(self, status=500, data=None):
        super().__init__(f"status={status}")
        self.status = status


_stub("github", Github=object, GithubException=_GithubException, InputGitTreeElement=_InputGitTreeElement)

import config  # noqa: E402
import github_integration as gi  # noqa: E402
import memory_manager  # noqa: E402
import sprint_engine as se  # noqa: E402

HIBAK: list[str] = []


def check(feltetel: bool, uzenet: str) -> None:
    if feltetel:
        print(f"  ✓ {uzenet}")
    else:
        print(f"  ✗ {uzenet}")
        HIBAK.append(uzenet)


# ---------------------------------------------------------------------------
# 1. A prompt-formázási hiba (a legsúlyosabb eredeti bug)
# ---------------------------------------------------------------------------
def test_prompt_brace_bug() -> None:
    """A LangChain f-string PromptTemplate a `str.format` szemantikáját követi.

    Régi kód: a perszóna BELEÉGETT a sablonba -> a benne lévő `{` placeholderré
    vált -> KeyError. Új kód: a perszóna ÉRTÉKKÉNT megy be -> nem értelmeződik újra.
    """
    print("\n[1] Prompt kapcsos-zárójel kezelés")
    persona = 'A profil: {"kognitiv_torzitas": "horn-effektus"} és tools { maven "Maven3" }'

    # RÉGI viselkedés: a persona a sablon része
    regi_sablon = f"Profil:\n{persona}\nKérdés: {{kerdes}}"
    try:
        string.Formatter().vformat(regi_sablon, (), {"kerdes": "x"})
        check(False, "a régi (f-stringes) megoldásnak el KELLETT volna szállnia")
    except (KeyError, IndexError, ValueError):
        check(True, "a régi f-stringes sablon reprodukálhatóan elszáll (ez volt a bug)")

    # ÚJ viselkedés: a persona partial value
    uj_sablon = "Profil:\n{persona_profile}\nKérdés: {kerdes}"
    eredmeny = string.Formatter().vformat(uj_sablon, (), {"persona_profile": persona, "kerdes": "x"})
    check(persona in eredmeny, "az új megoldás sértetlenül átengedi a kapcsos zárójeleket")


# ---------------------------------------------------------------------------
# 2. Sprint állapotgép és védőkorlát
# ---------------------------------------------------------------------------
def test_sprint_engine() -> None:
    print("\n[2] Sprint állapotgép és védőkorlát")

    jo_blokkok = [
        '// File: frontend/package.json\n{"name": "app", "dependencies": {}}',
        "<!-- File: backend/pom.xml -->\n<project xmlns='...'></project>",
    ]
    check(se.validate_it_valasz(jo_blokkok) == [], "szabályos IT válasz átmegy a védőkorláton")
    check(se.validate_it_valasz([]) == ["Nincsenek kódblokkok"], "üres válasz elbukik")

    # Fájlnév-komment nélküli, érdemi hosszúságú blokk.
    hibak = se.validate_it_valasz(['{"name": "app", "version": "1.0.0", "dependencies": {}}'])
    check(any("pom.xml" in h for h in hibak), "hiányzó pom.xml-t felismeri")
    check(any("fájlnév-komment" in h for h in hibak), "hiányzó fájlnév-kommentet felismeri")

    # A nagyon rövid blokkoknál (pl. egysoros parancs) nem várunk el fájlnevet.
    rovid = se.validate_it_valasz(jo_blokkok + ["npm install"])
    check(rovid == [], "a rövid segédblokk nem bukik el fájlnév-komment hiányán")

    # A LÉNYEG: a retry nem lehet végtelen (ez fagyasztotta be a régi sprintet).
    allapot = se.SprintAllapot()
    engedelyezett = 0
    for _ in range(20):
        if not se.kell_ujraprobalni(allapot, "IT", ["Hiányzik a pom.xml"]):
            break
        allapot.ujraprobalkozasok["IT"] = allapot.ujraprobalkozasok.get("IT", 0) + 1
        engedelyezett += 1
    check(
        engedelyezett == config.MAX_AGENS_UJRAPROBALKOZAS,
        f"az újrapróbálkozás {config.MAX_AGENS_UJRAPROBALKOZAS} után leáll (nincs végtelen ciklus)",
    )
    check(not se.kell_ujraprobalni(se.SprintAllapot(), "IT", []), "hiba nélkül nincs újrapróbálkozás")

    # Szerializáció oda-vissza
    a = se.SprintAllapot(kor=2, agens_idx=3, elozo_kimenet="x", valaszok={"PO": "y"})
    check(se.SprintAllapot.from_dict(a.to_dict()) == a, "az állapot szerializálása veszteségmentes")

    a.kovetkezo_kor("uj")
    check(
        a.kor == 3 and a.agens_idx == 0 and a.valaszok == {} and a.ujraprobalkozasok == {},
        "a kör váltása nullázza az indexet, a válaszokat és a retry-számlálót",
    )
    check(se.lezarast_kert("minden kész [LEZÁRVA]"), "a lezáró kulcsszót felismeri")


# ---------------------------------------------------------------------------
# 3. GitHub parsing
# ---------------------------------------------------------------------------
def test_github_parsing() -> None:
    print("\n[3] GitHub kód-kinyerés")
    bt = chr(96) * 3

    uzenet = {
        "szerep": "assistant",
        "szerep_nev": "Informatikus",
        "szoveg": (
            f"{bt}tsx\n// File: frontend/src/components/Board.tsx\n"
            "export default function Board() { return <div/>; }\n" + bt + "\n"
            f"{bt}java\n// File: backend/src/main/java/com/app/controller/GameController.java\n"
            "package com.app.controller;\n@RestController\npublic class GameController {}\n{bt}".replace("{bt}", bt)
        ),
    }
    blokkok = gi.extract_all_blocks([uzenet], ["IT", "Informatikus"])
    check(len(blokkok) == 2, "mindkét kódblokkot megtalálja")

    check(
        gi.get_filename_from_block(blokkok[0]) == "frontend/src/components/Board.tsx",
        "kinyeri a fájlnevet a kommentből",
    )
    tiszta = gi.clean_block_content(blokkok[0])
    check(not tiszta.startswith("//"), "eltávolítja a fájlnév-kommentet a tartalomból")
    check("export default" in tiszta, "a megtisztított tartalom ép")

    # Útvonal-biztonság
    check(gi.clean_filename("../../../etc/passwd") == "etc/passwd", "kiszűri a path traversalt")
    check(gi.clean_filename("/abs/path/App.jsx") == "abs/path/App.jsx", "levágja az abszolút útvonalat")
    check(gi.clean_filename("App.jsx.java") == "App.jsx", "javítja a .java hallucinációt")

    # Nem szerep szerinti szűrés
    check(
        gi.extract_all_blocks([uzenet], ["Scrum Master"]) == [],
        "más szerep üzeneteiből nem szed ki kódot",
    )

    # Teljes gyűjtés + Jenkinsfile kezelés
    ervenyes_pipeline = (
        "pipeline {\n  agent any\n  stages {\n"
        "    stage('Build') { steps { sh 'cd frontend && npm install' } }\n"
        "  }\n}"
    )
    devops = {
        "szerep": "assistant",
        "szerep_nev": "DevOps Engineer",
        "szoveg": f"{bt}groovy\n{ervenyes_pipeline}\n{bt}",
    }
    files, stat = gi.collect_files([uzenet, devops], "memória", "feladat")
    check("frontend/src/components/Board.tsx" in files, "a komponens a helyére kerül")
    check(
        "backend/src/main/java/com/app/controller/GameController.java" in files,
        "a controller a package szerinti helyre kerül",
    )
    # Ezeket már a rögzített váz adja, nem a chat-log.
    check("frontend/package.json" in files, "a package.json a vázból jön")
    check("backend/pom.xml" in files, "a pom.xml a vázból jön")
    check("README.md" in files, "a README.md mindig generálódik")
    # A Jenkinsfile MINDIG determinisztikusan generált – az ágens pipeline-ja
    # nem kerül a repóba (a build-bukások onnan jöttek).
    check(
        stat["jenkins_forras"] == "generalt",
        "a Jenkinsfile determinisztikusan generált, nem az ágensé",
    )
    check("pipeline {" in files["Jenkinsfile"], "a generált Jenkinsfile érvényes")
    check(
        (stat["fe"], stat["be"], stat["db"]) == (1, 1, 0),
        f"a statisztika helyes: fe/be/db = {stat['fe']}/{stat['be']}/{stat['db']}",
    )

    # A védett konfigot a chat-logból NEM engedjük felülírni.
    tamado = {
        "szerep": "assistant",
        "szerep_nev": "Informatikus",
        "szoveg": f"{bt}json\n// File: frontend/package.json\n" + '{"dependencies":{"x":"^9.9.9"}}\n' + bt,
    }
    files_v, _ = gi.collect_files([tamado], "m", "f")
    check('"x"' not in files_v["frontend/package.json"], "a chat-logból jövő package.json elutasítva")

    # Az ágens pipeline-ja akkor sem kerül fel, ha érvénytelen – mindig generált.
    csonka = {
        "szerep": "assistant",
        "szerep_nev": "DevOps Engineer",
        "szoveg": f"{bt}groovy\npipeline {{ agent any }}\n{bt}",
    }
    _, stat_csonka = gi.collect_files([uzenet, csonka], "m", "f")
    check(
        stat_csonka["jenkins_forras"] == "generalt",
        "az ágens pipeline-ja sosem kerül fel – mindig a generált Jenkinsfile",
    )

    files2, stat2 = gi.collect_files([], "m", "f")
    check(
        stat2["fe"] + stat2["be"] + stat2["db"] == 0,
        "ágens-kód nélkül nincs saját forrásfájl (csak a váz)",
    )
    check("pipeline" in files2["Jenkinsfile"], "DevOps válasz nélkül is kerül fel érvényes Jenkinsfile")


# ---------------------------------------------------------------------------
# 4. Atomikus perzisztencia
# ---------------------------------------------------------------------------
def test_memory_manager(tmp: Path) -> None:
    print("\n[4] Memóriakezelés")
    eredeti = config.MEMORIA_FAJL
    config.MEMORIA_FAJL = tmp / "teszt_memoria.json"
    try:
        check(memory_manager.load_all_runs() == [], "hiányzó fájl esetén üres lista")

        ok = memory_manager.save_run("r1", "2026-01-01", "feladat", "mem", [], {}, {"PO": 4})
        check(ok, "a mentés sikeres")
        check(len(memory_manager.load_all_runs()) == 1, "a mentett futás visszaolvasható")

        memory_manager.save_run("r1", "2026-01-01", "másik", "mem2", [], {}, {})
        runs = memory_manager.load_all_runs()
        check(len(runs) == 1 and runs[0]["feladat"] == "másik", "azonos run_id frissít, nem duplikál")

        memory_manager.save_run("r2", "2026-01-02", "b", "m", [], {}, {})
        check(len(memory_manager.load_all_runs()) == 2, "új run_id hozzáfűz")
        check(memory_manager.delete_run("r1") and len(memory_manager.load_all_runs()) == 1, "törlés működik")

        check(not memory_manager.save_run(None, "d", "f", "m", [], {}, {}), "run_id nélkül nem ment")

        # Sérült fájl nem dönti meg az appot
        config.MEMORIA_FAJL.write_text("{ ez nem json", encoding="utf-8")
        check(memory_manager.load_all_runs() == [], "sérült JSON esetén üres listát ad, nem dob kivételt")

        # Nem marad ott ideiglenes fájl
        memory_manager.save_run("r3", "d", "f", "m", [], {}, {})
        check(not list(tmp.glob(".memoria_*.tmp")), "a mentés nem hagy hátra .tmp fájlt")
    finally:
        config.MEMORIA_FAJL = eredeti


# ---------------------------------------------------------------------------
# 5. Konfiguráció épsége
# ---------------------------------------------------------------------------
def test_config() -> None:
    print("\n[5] Konfiguráció")
    idk = [a["id"] for a in config.DEFAULT_AGENTS]
    check(len(idk) == len(set(idk)), "nincs duplikált ágens-azonosító")
    check(
        all({"id", "ikon", "nev", "leiras", "akcio", "szabaly"} <= set(a) for a in config.DEFAULT_AGENTS),
        "minden ágensnek megvan az összes kötelező mezője",
    )
    check(
        all(a["id"] in config.AGENS_SZINEK for a in config.DEFAULT_AGENTS),
        "minden alapértelmezett ágenshez tartozik szín (a DO korábban hiányzott)",
    )
    check(config.BASE_DIR.is_absolute(), "az útvonalak abszolútak (cwd-független indítás)")
    check(config.MEMORIA_FAJL.is_absolute(), "a memóriafájl útvonala abszolút")


def main() -> int:
    print("=" * 68)
    print("LLMOps Szimulátor – regressziós tesztek")
    print("=" * 68)

    import tempfile

    test_prompt_brace_bug()
    test_sprint_engine()
    test_github_parsing()
    with tempfile.TemporaryDirectory() as d:
        test_memory_manager(Path(d))
    test_config()

    print("\n" + "=" * 68)
    if HIBAK:
        print(f"❌ {len(HIBAK)} teszt bukott el:")
        for h in HIBAK:
            print(f"   - {h}")
        return 1
    print("✅ Minden teszt sikeres.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
