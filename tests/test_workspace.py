# tests/test_workspace.py
"""A VirtualWorkspace tesztjei.

A kulcseset a valós futásból: két iteráció ugyanazt az osztályt két csomagba
tette (`com.malom.engine.MatchEngine` és `com.malom.service.MatchEngine`),
mindkettő `@Service` → ütköző Spring bean-név → a context el sem indul.

Futtatás:  python3 tests/test_workspace.py
"""
from __future__ import annotations

import json
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


class _GithubException(Exception):
    def __init__(self, status=500, data=None):
        super().__init__(str(status))
        self.status = status


_m = types.ModuleType("github")
_m.Github = object
_m.GithubException = _GithubException
_m.InputGitTreeElement = object
sys.modules["github"] = _m

from workspace import VirtualWorkspace, ellenoriz, workspace_from_messages  # noqa: E402

BT = chr(96) * 3
KOD_SZEREPEK = ["Informatikus", "IT", "UX", "Designer"]
HIBAK: list[str] = []


def check(feltetel: bool, uzenet: str) -> None:
    print(f"  {'✓' if feltetel else '✗'} {uzenet}")
    if not feltetel:
        HIBAK.append(uzenet)


def uzenet(szoveg: str, nev: str = "Informatikus") -> dict:
    return {"szerep": "assistant", "szerep_nev": nev, "szoveg": szoveg}


def blokk(nyelv: str, tartalom: str) -> str:
    return f"{BT}{nyelv}\n{tartalom}\n{BT}"


# ---------------------------------------------------------------------------
def test_alap_muveletek() -> None:
    print("\n[1] Alapműveletek és patch-szemantika")
    ws = VirtualWorkspace()

    java = "package com.malom.service;\n\n@Service\npublic class MatchEngine {\n  void a() {}\n}"
    ws.alkalmaz(uzenet(blokk("java", java)), KOD_SZEREPEK)
    check("backend/src/main/java/com/malom/service/MatchEngine.java" in ws, "az első írás létrehozza a fájlt")
    check(len(ws) == 1, "pontosan egy fájl van a fában")

    # Ugyanaz a tartalom újra -> nincs változás
    valtozasok = ws.alkalmaz(uzenet(blokk("java", java)), KOD_SZEREPEK)
    check(
        all(v.tipus == "valtozatlan" for v in valtozasok),
        "azonos tartalom újraküldése 'valtozatlan' (nem duplikál)",
    )
    check(len(ws) == 1, "a fájlszám nem nőtt")

    # Módosított tartalom -> 'modositott'
    java2 = java.replace("void a() {}", "void a() {}\n  void b() {}")
    valtozasok = ws.alkalmaz(uzenet(blokk("java", java2)), KOD_SZEREPEK)
    check(any(v.tipus == "modositott" for v in valtozasok), "megváltozott tartalom 'modositott'")
    check("void b()" in ws.get("backend/src/main/java/com/malom/service/MatchEngine.java"),
          "a friss tartalom felülírja a régit")


def test_bean_utkozes() -> None:
    print("\n[2] Spring bean-ütközés feloldása (a valós futás fő hibája)")
    ws = VirtualWorkspace()

    regi = "package com.malom.engine;\n\n@Service\npublic class MatchEngine {\n  void applyMove() {}\n}"
    uj = "package com.malom.service;\n\n@Service\npublic class MatchEngine {\n  void createSession() {}\n}"

    ws.alkalmaz(uzenet(blokk("java", regi)), KOD_SZEREPEK)
    check("backend/src/main/java/com/malom/engine/MatchEngine.java" in ws, "1. iteráció: engine csomag")

    valtozasok = ws.alkalmaz(uzenet(blokk("java", uj)), KOD_SZEREPEK)
    check("backend/src/main/java/com/malom/service/MatchEngine.java" in ws, "3. iteráció: service csomag")
    check(
        "backend/src/main/java/com/malom/engine/MatchEngine.java" not in ws,
        "a RÉGI, ütköző osztály eltávolítva (nem lesz ConflictingBeanDefinition)",
    )
    check(
        any(v.tipus == "lecserelt" and "bean" in v.indok for v in valtozasok),
        "a naplóban szerepel az ütközés indoka",
    )
    check(len([p for p in ws.files if p.endswith("MatchEngine.java")]) == 1, "pontosan egy MatchEngine maradt")


def test_direktivak() -> None:
    print("\n[3] DELETE / MOVE direktívák")
    ws = VirtualWorkspace()
    ws.files["frontend/src/components/Regi.jsx"] = "export default function Regi() {}"
    ws.files["frontend/src/components/Mozgo.jsx"] = "export default function Mozgo() {}"

    ws.alkalmaz(uzenet("Takarítás:\nDELETE: frontend/src/components/Regi.jsx"), KOD_SZEREPEK)
    check("frontend/src/components/Regi.jsx" not in ws, "a DELETE direktíva töröl")

    ws.alkalmaz(
        uzenet("// MOVE: frontend/src/components/Mozgo.jsx -> frontend/src/ui/Mozgo.jsx"), KOD_SZEREPEK
    )
    check("frontend/src/ui/Mozgo.jsx" in ws, "a MOVE direktíva áthelyez")
    check("frontend/src/components/Mozgo.jsx" not in ws, "a régi útvonal megszűnt")

    # Path traversal a direktívában sem mehet át
    ws.alkalmaz(uzenet("DELETE: ../../../etc/passwd"), KOD_SZEREPEK)
    check(True, "a veszélyes DELETE útvonal nem okoz kivételt")


def test_ellenorzes() -> None:
    print("\n[4] Statikus konzisztencia-ellenőrzés")
    ws = VirtualWorkspace()
    ws.files.update(
        {
            "backend/pom.xml": "<project/>",
            "frontend/package.json": "{}",
            # Szándékos hiba: a package deklaráció nem egyezik a könyvtárral
            "backend/src/main/java/com/rossz/Utils.java": "package com.malom.util;\npublic class Utils {}",
            "frontend/src/App.tsx": "import Hianyzo from './Hianyzo';\nexport default function App() {}",
        }
    )
    hibak = ellenoriz(ws)
    check(any("package deklaráció" in h for h in hibak), "felismeri a package/könyvtár eltérést")
    check(any("feloldatlan import" in h for h in hibak), "felismeri a feloldatlan relatív importot")

    ws2 = VirtualWorkspace(
        files={
            "backend/src/main/java/com/a/App.java": "package com.a;\n@SpringBootApplication\npublic class App {}",
            "backend/src/main/java/com/b/App2.java": "package com.b;\n@SpringBootApplication\npublic class App2 {}",
        }
    )
    check(
        any("@SpringBootApplication" in h for h in ellenoriz(ws2)),
        "felismeri a több belépési pontot",
    )

    # A `scripts` blokk kötelező: nélküle a Jenkins nem tud mit futtatni.
    tiszta = VirtualWorkspace(
        files={
            "frontend/package.json": '{"scripts": {"dev": "vite", "build": "vite build"}}',
            "frontend/src/App.tsx": "export default function App(){}",
        }
    )
    check(ellenoriz(tiszta) == [], f"hibátlan projektre üres hibalista ({ellenoriz(tiszta)})")

    # Script nélküli package.json viszont build-blokkoló.
    scripts_nelkul = VirtualWorkspace(files={"frontend/package.json": "{}"})
    check(
        any("scripts" in h for h in ellenoriz(scripts_nelkul)),
        "a `scripts` nélküli package.json build-blokkolóként jelenik meg",
    )


def test_perzisztencia_es_fajlfa() -> None:
    print("\n[5] Fájlfa-reprezentáció és perzisztencia")
    ws = VirtualWorkspace(files={"frontend/package.json": '{"name":"x"}', "backend/pom.xml": "<project/>"})

    fa = ws.fajlfa()
    check("frontend/package.json" in fa and "backend/pom.xml" in fa, "a fájlfa minden útvonalat felsorol")
    check("bájt" in fa, "a fájlfa méretet is mutat")
    check("üres" in VirtualWorkspace().fajlfa(), "üres projektre beszédes üzenet")

    nagy = VirtualWorkspace(files={f"src/f{i}.ts": "x" for i in range(120)})
    check("további" in nagy.fajlfa(max_sor=20), "nagy fánál csonkol (token-védelem)")

    vissza = VirtualWorkspace.from_dict(json.loads(json.dumps(ws.to_dict())))
    check(vissza.files == ws.files, "JSON oda-vissza veszteségmentes")
    check(VirtualWorkspace.from_dict(None).files == {}, "None-ra üres workspace")

    osszes = ws.osszefoglalo()
    check(osszes["frontend"] == 1 and osszes["backend"] == 1, "az összefoglaló helyesen számol")


def test_valos_futas() -> None:
    print("\n[6] Valós futás: chat-log → fájlfa")
    memoria = GYOKER / "szimulacio_memoria.json"
    if not memoria.exists():
        print("  – kihagyva (nincs szimulacio_memoria.json)")
        return

    runs = json.loads(memoria.read_text(encoding="utf-8")).get("runs", [])
    futas = next((r for r in reversed(runs) if len(r.get("uzenetek", [])) > 20), None)
    if not futas:
        print("  – kihagyva")
        return

    ws = workspace_from_messages(futas["uzenetek"], KOD_SZEREPEK)
    print(f"      {len(futas['uzenetek'])} üzenet → {len(ws)} fájl")

    matchengine = [p for p in ws.files if p.endswith("MatchEngine.java")]
    check(len(matchengine) <= 1, f"nincs duplikált MatchEngine ({matchengine})")

    beanek = [h for h in ellenoriz(ws) if "Ütköző Spring bean" in h]
    check(not beanek, f"nincs ütköző Spring bean-név ({beanek})")

    belepesi = [p for p, c in ws.files.items() if "@SpringBootApplication" in c]
    check(len(belepesi) <= 1, f"legfeljebb egy belépési pont ({len(belepesi)})")

    check(len(ws) < 40, f"a fájlfa kompakt maradt ({len(ws)} fájl)")
    check("backend/pom.xml" in ws and "frontend/package.json" in ws, "a build-leírók megvannak")


def main() -> int:
    print("=" * 68)
    print("VirtualWorkspace tesztek")
    print("=" * 68)
    test_alap_muveletek()
    test_bean_utkozes()
    test_direktivak()
    test_ellenorzes()
    test_perzisztencia_es_fajlfa()
    test_valos_futas()

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
