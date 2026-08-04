# tests/test_sandbox.py
"""A sandbox (valódi build) tesztjei.

A hibakinyerést valódi `tsc` / `mvn` / `npm` kimeneteken ellenőrizzük, a
futtatást pedig monkeypatch-eljük — így a teszt Docker és hálózat nélkül fut.

Futtatás:  python3 tests/test_sandbox.py
"""
from __future__ import annotations

import sys
from pathlib import Path

GYOKER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GYOKER))

# Windows-konzol UTF-8 vedelem: a ✓/✗/ékezetek ne dobjanak UnicodeEncodeError-t
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import config  # noqa: E402
import sandbox  # noqa: E402
import sprint_engine  # noqa: E402

HIBAK: list[str] = []


def check(feltetel: bool, uzenet: str) -> None:
    print(f"  {'✓' if feltetel else '✗'} {uzenet}")
    if not feltetel:
        HIBAK.append(uzenet)


# --- Valódi fordítói kimenetek ---------------------------------------------
TSC_KIMENET = """
src/components/GameBoard.tsx(42,18): error TS2322: Type 'string' is not assignable to type 'number'.
src/store/GameStore.ts(15,7): error TS2304: Cannot find name 'Player'.
src/App.tsx(8,23): error TS2307: Cannot find module './Hianyzo' or its corresponding type declarations.
"""

MVN_KIMENET = """
[INFO] Compiling 4 source files
[ERROR] /app/backend/src/main/java/com/malom/controller/GameController.java:[24,38] cannot find symbol
[ERROR]   symbol:   class MoveRequest
[ERROR] /app/backend/src/main/java/com/malom/service/MatchEngine.java:[80,12] incompatible types: int cannot be converted to String
[ERROR] -> [Help 1]
[ERROR] To see the full stack trace of the errors, re-run Maven with the -e switch.
"""

NPM_KIMENET = """
npm ERR! code ENOENT
npm ERR! syscall open
npm ERR! enoent Could not read package.json: Error: ENOENT: no such file or directory
npm ERR! A complete log of this run can be found in: /root/.npm/_logs/x.log
"""


def test_hibakinyeres() -> None:
    print("\n[1] Hibakinyerés valódi fordítói kimenetből")

    ts = sandbox.hibak_kinyerese(TSC_KIMENET, "frontend")
    check(len(ts) == 3, f"mindhárom TS hibát megtalálja ({len(ts)})")
    check(any("GameBoard.tsx:42" in h for h in ts), "fájl és sorszám benne van")
    check(any("TS2304" in h for h in ts), "a TS hibakód megmarad")

    mvn = sandbox.hibak_kinyerese(MVN_KIMENET, "backend")
    check(any("GameController.java:24" in h for h in mvn), "Java fájl:sor felismerve")
    check(any("cannot find symbol" in h for h in mvn), "a Maven hibaüzenet megmarad")
    check(not any("Help 1" in h for h in mvn), "a Maven zajt (-> [Help 1]) kiszűri")
    check(not any("re-run Maven" in h for h in mvn), "a 'To see the full…' sort kiszűri")

    npm = sandbox.hibak_kinyerese(NPM_KIMENET, "frontend")
    check(any("Could not read package.json" in h for h in npm), "npm hibát is felismer")
    check(not any("A complete log" in h for h in npm), "az npm log-sort kiszűri")

    check(sandbox.hibak_kinyerese("", "frontend") == [], "üres kimenetre üres lista")
    check(sandbox.hibak_kinyerese("minden rendben", "backend") == [], "hibamentes kimenetre üres lista")

    sok = "\n".join(f"src/f{i}.ts({i},1): error TS1000: hiba {i}" for i in range(50))
    check(len(sandbox.hibak_kinyerese(sok, "frontend")) <= sandbox.MAX_HIBA, "a hibalista limitált (token-védelem)")

    hosszu = "src/a.ts(1,1): error TS1: " + "x" * 2000
    check(
        all(len(h) <= sandbox.MAX_HIBA_HOSSZ + 1 for h in sandbox.hibak_kinyerese(hosszu, "frontend")),
        "a túl hosszú hibaüzenet csonkolva",
    )


def test_eredmeny_modell() -> None:
    print("\n[2] Eredmény-modell és prompt-részlet")

    bukott = sandbox.BuildEredmeny(
        cel="backend", sikeres=False, hibak=["A.java:1 — cannot find symbol"],
        nyers_kimenet=MVN_KIMENET, idotartam=12.3, parancs="mvn -B compile",
    )
    kihagyott = sandbox.BuildEredmeny(cel="frontend", sikeres=True, kihagyva=True, indok="nincs package.json")
    er = sandbox.SandboxEredmeny(motor="docker", reszek=[kihagyott, bukott])

    check(er.futott, "futottnak számít, ha legalább egy rész lefutott")
    check(not er.sikeres, "bukott résznél az összesítés is bukott")
    check(er.hibak and er.hibak[0].startswith("[backend]"), "a hibák cél szerint prefixáltak")

    reszlet = er.prompt_reszlet()
    check("A VALÓDI FORDÍTÁS ELBUKOTT" in reszlet, "a prompt-részlet egyértelmű fejlécet kap")
    check("cannot find symbol" in reszlet, "a konkrét hiba benne van")
    check("frontend" not in reszlet.lower().split("---")[0], "a kihagyott rész nem zajong a fejlécben")

    mind_jo = sandbox.SandboxEredmeny(
        motor="docker", reszek=[sandbox.BuildEredmeny(cel="backend", sikeres=True)]
    )
    check(mind_jo.sikeres and mind_jo.prompt_reszlet() == "", "sikeres buildnél nincs prompt-részlet")

    mind_kihagyva = sandbox.SandboxEredmeny(
        motor="kihagyva",
        reszek=[sandbox.BuildEredmeny(cel="backend", sikeres=True, kihagyva=True, indok="x")],
    )
    check(not mind_kihagyva.futott, "csupa kihagyott rész → nem futott")
    check(not mind_kihagyva.sikeres, "nem futott build nem számít sikeresnek")


def test_build_folyamat(monkey_kimenet: dict) -> None:
    print("\n[3] Build folyamat (futtatás monkeypatch-elve)")

    eredeti_futtat = sandbox._futtat
    eredeti_motor = sandbox.elerheto_motor
    hivasok: list[list[str]] = []

    def hamis_futtat(parancs, munkakonyvtar, timeout):
        hivasok.append(parancs)
        # A kiírt fájlfa tényleg a lemezen van-e?
        assert Path(munkakonyvtar).exists()
        return monkey_kimenet["kod"], monkey_kimenet["kimenet"]

    sandbox._futtat = hamis_futtat
    sandbox.elerheto_motor = lambda: "docker"
    try:
        files = {
            "frontend/package.json": '{"scripts":{"build":"vite build"}}',
            "frontend/src/App.tsx": "export default function App(){}",
            "backend/pom.xml": "<project/>",
            "backend/src/main/java/com/a/App.java": "package com.a;\npublic class App {}",
        }
        er = sandbox.build(files)
        check(er.motor == "docker", "a választott motor visszaköszön")
        check(len(er.reszek) == 2, "frontend és backend is lefutott")
        check(len(hivasok) == 2, "két parancs indult")
        check(any("node" in " ".join(h) for h in hivasok), "a Node image szerepel a parancsban")
        check(any("maven" in " ".join(h) for h in hivasok), "a Maven image szerepel a parancsban")
        check(not er.sikeres, "hibás kimenetnél a build bukott")

        # A tsc hibáját NEM szabad elnyelni – különben hamisan zöld a build.
        fe_parancs = " ".join(next(h for h in hivasok if "node" in " ".join(h)))
        check("tsc --noEmit" in fe_parancs, "a típusellenőrzés benne van a parancsban")
        check("|| true" not in fe_parancs, "nincs `|| true`, ami elnyelné a tsc hibáit")
        check("set -e" in fe_parancs, "a shell az első hibánál megáll (set -e)")

        # Csak frontend: a backend rész kihagyva
        er2 = sandbox.build({"frontend/package.json": "{}"})
        be = next(r for r in er2.reszek if r.cel == "backend")
        check(be.kihagyva and "pom.xml" in be.indok, "pom.xml hiányában a backend kihagyva")

        # Üres fájlfa nem omlik össze
        check(not sandbox.build({}).futott, "üres projektre nem fut build")
    finally:
        sandbox._futtat = eredeti_futtat
        sandbox.elerheto_motor = eredeti_motor


def test_kikapcsolt_sandbox() -> None:
    print("\n[4] Fokozatos degradáció")

    eredeti = config.SANDBOX_MOD
    try:
        config.SANDBOX_MOD = "off"
        check(sandbox.elerheto_motor() == "kihagyva", "SANDBOX_MOD='off' esetén kihagyva")
        er = sandbox.build({"backend/pom.xml": "<project/>"})
        check(not er.futott, "kikapcsolva nem fut build")
        check(er.prompt_reszlet() == "", "kikapcsolva nincs prompt-részlet")
    finally:
        config.SANDBOX_MOD = eredeti

    check(isinstance(sandbox.motor_leirasa(), str), "a motor leírása mindig szöveg")


def test_javito_prompt() -> None:
    print("\n[5] A fordítói hiba visszacsatolása a promptba")

    er = sandbox.SandboxEredmeny(
        motor="docker",
        reszek=[
            sandbox.BuildEredmeny(
                cel="backend", sikeres=False,
                hibak=["GameController.java:24 — cannot find symbol: class MoveRequest"],
                parancs="mvn -B compile",
            )
        ],
    )
    prompt = sprint_engine.javito_prompt("eredeti válasz", er.hibak, 2, er.prompt_reszlet())

    check("cannot find symbol" in prompt, "a konkrét fordítói hiba bekerül a promptba")
    check("VALÓDI FORDÍTÁS" in prompt, "a prompt jelzi, hogy gépi visszajelzésről van szó")
    check("DELETE:" in prompt, "a prompt említi a törlési direktívát")
    check("Hátralévő próbálkozás: 2" in prompt, "a maradék próbálkozás látszik")

    statikus = sprint_engine.javito_prompt("válasz", ["Hiányzik a pom.xml"], 1)
    check("Hiányzik a pom.xml" in statikus, "fordító nélkül a statikus hibák mennek")
    check("VALÓDI FORDÍTÁS" not in statikus, "ilyenkor nincs fordítói fejléc")


def main() -> int:
    print("=" * 68)
    print("Sandbox tesztek")
    print("=" * 68)
    test_hibakinyeres()
    test_eredmeny_modell()
    test_build_folyamat({"kod": 1, "kimenet": MVN_KIMENET})
    test_kikapcsolt_sandbox()
    test_javito_prompt()

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
