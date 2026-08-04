# tests/test_build_pipeline.py
"""Tesztek a „nem készült el az alkalmazás” hibacsoportra.

Minden eset a `szimulacio_memoria.json` valós futásaiból visszafejtett hibát
reprodukál.

Futtatás:  python3 tests/test_build_pipeline.py
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

import code_analysis as ca  # noqa: E402
import github_integration as gi  # noqa: E402
import jenkins_repair as jr  # noqa: E402

HIBAK: list[str] = []


def check(feltetel: bool, uzenet: str) -> None:
    print(f"  {'✓' if feltetel else '✗'} {uzenet}")
    if not feltetel:
        HIBAK.append(uzenet)


# ---------------------------------------------------------------------------
def test_java_utvonal() -> None:
    print("\n[1] Java útvonal a kódból (a Maven compile error gyökéroka)")

    kod = (
        "package com.malom.service;\n\n"
        "import org.springframework.stereotype.Service;\n\n"
        "@Service\npublic class MatchEngine {\n    public void start() {}\n}\n"
    )
    check(
        ca.java_teljes_utvonal(kod) == "backend/src/main/java/com/malom/service/MatchEngine.java",
        "a package + osztálynév adja az útvonalat",
    )

    # A régi kód `com/app/Class_16.java`-t csinált ebből -> javac hiba.
    regi = "backend/src/main/java/com/app/Class_16.java"
    check(ca.java_teljes_utvonal(kod) != regi, "NEM a régi, fordíthatatlan Class_NN.java útvonal")

    check(
        ca.java_teljes_utvonal("public interface GameRepository { }")
        == "backend/src/main/java/com/app/GameRepository.java",
        "package deklaráció nélkül is felismeri az interfészt",
    )
    check(ca.java_teljes_utvonal("csak szöveg") is None, "nem Java kódra None")


def test_frontend_utvonalak() -> None:
    print("\n[2] Frontend fájlok felismerése")

    esetek = [
        ("import { defineConfig } from 'vite';\nexport default defineConfig({ plugins: [] });",
         "vite.config", "vite.config felismerése (korábban Component_NN.jsx lett)"),
        ("import ReactDOM from 'react-dom/client';\nReactDOM.createRoot(document.getElementById('root')!).render(<App />);",
         "frontend/src/main", "React belépési pont felismerése"),
        ("@tailwind base;\n@tailwind components;\nbody { color: red; }",
         "frontend/src/index.css", "Tailwind stíluslap felismerése"),
    ]
    for kod, vart, uzenet in esetek:
        ut = ca.szarmaztatott_utvonal(kod)
        check(ut is not None and vart in ut, f"{uzenet} → {ut}")

    komponens = (
        "import React from 'react';\n"
        "interface Props { size: number }\n"
        "export default function GameBoard({ size }: Props) { return <div />; }\n"
    )
    check(
        ca.szarmaztatott_utvonal(komponens) == "frontend/src/components/GameBoard.tsx",
        "TSX komponens neve és kiterjesztése helyes",
    )


def test_npm_start_hiba() -> None:
    print("\n[3] A nem létező `npm start` script (a frontend soha nem indult el)")

    vite_pkg = json.dumps(
        {"name": "app", "scripts": {"dev": "vite", "build": "tsc -b && vite build", "preview": "vite preview"}}
    )
    scriptek = ca.package_json_scriptek(vite_pkg)
    check("start" not in scriptek, "a valós Vite package.json-ban tényleg NINCS `start`")

    parancs, port = ca.indito_parancs(scriptek)
    check("npm run dev" in parancs, f"a `dev` scriptre vált: {parancs}")
    check("--host 0.0.0.0" in parancs, "a Vite kívülről is elérhető lesz (--host)")
    check(port == "3000", "a port konzisztens a health checkkel")

    # CRA: a `start` script megmarad, de host/port környezeti változóval,
    # különben a dev szerver csak localhoston figyel a Jenkins agenten.
    cra = ca.indito_parancs({"start": "react-scripts start"})[0]
    check("npm start" in cra and "HOST=0.0.0.0" in cra, f"CRA-nál `npm start` + HOST/PORT: {cra}")

    # Keretrendszer nélkül a puszta `npm start` marad.
    check(ca.indito_parancs({"start": "node server.js"})[0] == "npm start", "ismeretlen keretnél `npm start`")
    check(ca.package_json_scriptek("{ ez nem json") == {}, "hibás JSON-ra üres dict, nem kivétel")


def test_jenkins_javitas() -> None:
    print("\n[4] Jenkinsfile auto-javítás")

    # Pontosan az a pipeline, ami a valós futásokban némán elbukott.
    romlott = """pipeline {
    agent any
    stages {
        stage('Frontend Install') {
            steps { sh 'cd frontend && npm ci' }
        }
        stage('Frontend Deploy') {
            steps { sh 'nohup npm start > frontend.log 2>&1 &' }
        }
        stage('Backend Deploy') {
            steps { sh 'JENKINS_NODE_COOKIE=dontKillMe nohup mvn spring-boot:run -Dserver.port=8081 > backend.log 2>&1 &' }
        }
    }
}"""
    files = {
        "frontend/package.json": json.dumps({"scripts": {"dev": "vite", "build": "vite build"}}),
        "backend/pom.xml": "<project><modelVersion>4.0.0</modelVersion></project>",
        # A deploy port innen származik – nem beégetett érték.
        "backend/src/main/resources/application.properties": "server.port=8081\n",
    }
    javitott, valtozasok, forras = jr.javit_jenkinsfile(romlott, files)

    # A fájl elején álló változásnapló (`// - ...`) idézi a régi parancsokat is,
    # ezért a tartalmi ellenőrzéseket a tényleges pipeline-törzsre szűkítjük.
    torzs = javitott[javitott.index("pipeline {"):]
    deploy_sorok = [s for s in torzs.splitlines() if "nohup" in s]

    check(forras == "agens-javitott", "az ágens pipeline-ját javítja, nem dobja el")
    check(
        deploy_sorok and all("cd frontend &&" in s or "cd backend &&" in s for s in deploy_sorok),
        "`cd frontend` / `cd backend` bekerült MINDEN deploy parancsba (ez volt a fő hibaok)",
    )
    check("npm ci" not in torzs, "`npm ci` eltűnt a pipeline-ból (package-lock nélkül mindig elbukott)")
    check("npm install" in torzs, "helyette `npm install` fut")
    check("npm run dev" in torzs, "a nem létező `npm start` létező scriptre cserélve")
    check(
        "-Dspring-boot.run.arguments=--server.port=8081" in torzs,
        "a Spring port app-argumentumként megy át (nem JVM property-ként)",
    )
    check("< /dev/null" in torzs, "a háttérfolyamat stdinje lezárva")
    check("BUILD_ID" in torzs, "BUILD_ID=dontKillMe beszúrva")
    check(
        all(sor.count("JENKINS_NODE_COOKIE") <= 1 for sor in torzs.splitlines()),
        "nincs duplikált JENKINS_NODE_COOKIE",
    )
    check("Health Check" in torzs, "Health Check stage beszúrva (néma deploy-hiba kimutatása)")
    check("Sanity Check" in torzs, "Sanity Check stage beszúrva (no-op zöld build ellen)")
    check(jr.ervenyes_pipeline(javitott), "a javított pipeline szintaktikailag ép")

    # Érvénytelen bemenet -> determinisztikus fallback
    _, _, forras2 = jr.javit_jenkinsfile("ez nem pipeline", files)
    check(forras2 == "generalt", "érvénytelen ágens-Jenkinsfile esetén generáltra vált")

    generalt = jr.generalt_jenkinsfile(jr.projekt_info(files))
    check(jr.ervenyes_pipeline(generalt), "a generált pipeline is érvényes")
    check("dir('frontend')" in generalt and "dir('backend')" in generalt, "a generált dir() blokkokat használ")

    # Üres projekt: ne legyen néma zöld build
    ures = jr.generalt_jenkinsfile(jr.projekt_info({}))
    check("error(" in ures, "build-fájl nélkül a pipeline hibára fut, nem lesz zöld")


def test_jenkins_22_regresszio() -> None:
    """A valós #22-es Jenkins build négy hibája (log: 2026-07-21).

    A build eljutott a Health Checkig, ott bukott el:
        script.sh.copy: 3: local: not in a function → exit 2
    """
    print("\n[6] Jenkins #22 build — valós hibák regressziója")

    # Next.js projekt `start` script NÉLKÜL, pontosan mint a #22-ben.
    files = {
        "frontend/package.json": json.dumps(
            {
                "name": "neobank-demo",
                "scripts": {"dev": "next dev", "build": "next build"},
                "dependencies": {"next": "14.2.35", "react": "^18"},
            }
        ),
        "backend/pom.xml": "<project><modelVersion>4.0.0</modelVersion></project>",
        "backend/src/main/resources/application.properties": "server.port=8081\n",
    }

    info = jr.projekt_info(files)
    check(info.keretrendszer == "next", f"felismeri a Next.js keretrendszert ({info.keretrendszer})")
    check("-H 0.0.0.0" in info.start_parancs, "Next.js `-H` kapcsolót kap, nem Vite-os `--host`-ot")
    check("--host" not in info.start_parancs, "nincs Vite-specifikus `--host` a Next.js parancsban")
    check("next start" in info.start_parancs, "`next build` után `next start` indul (nem `dev`)")

    # Vite-projektnél viszont maradjon a Vite-os alak.
    vite_files = {
        "frontend/package.json": json.dumps(
            {"scripts": {"dev": "vite", "build": "vite build"}, "devDependencies": {"vite": "^5"}}
        )
    }
    vite_info = jr.projekt_info(vite_files)
    check(vite_info.keretrendszer == "vite", "a Vite-projektet is helyesen ismeri fel")
    check("--host 0.0.0.0" in vite_info.start_parancs, "Vite-nál marad a `--host` alak")

    # A #22 pipeline hibás részletei
    romlott = """pipeline { agent any
  stages {
    stage('Deploy Backend') { steps {
      sh 'BUILD_ID=dontKillMe nohup java -jar target/app.jar -Dspring-boot.run.arguments=--server.port=8081'
    } }
    stage('Deploy Frontend') { steps {
      sh 'BUILD_ID=dontKillMe nohup npm start'
    } }
    stage('Health Check') { steps {
      sh '''
echo "indul"
local max_retries=30
'''
    } }
  }
}"""
    javitott, _, _ = jr.javit_jenkinsfile(romlott, files)
    torzs = javitott[javitott.index("pipeline {") :]

    check("local max_retries" not in torzs, "a `local` eltűnt (ez ölte meg a #22 buildet)")
    check("max_retries=30" in torzs, "a változó értékadása megmaradt")

    check(
        "-Dspring-boot.run.arguments" not in torzs,
        "`java -jar` mellől eltűnt a hibás Maven-property alak",
    )
    check("--server.port=8081" in torzs, "a port a jar után app-argumentumként megy")

    deploy_sorok = [s for s in torzs.splitlines() if "nohup" in s]
    check(
        deploy_sorok and all(s.rstrip().rstrip("'").rstrip().endswith("&") for s in deploy_sorok),
        "minden szerverindítás háttérbe került (`&`)",
    )
    check(
        all(".log" in s for s in deploy_sorok),
        "minden szerverindítás naplófájlba ír (különben nincs mit megnézni hibánál)",
    )
    check(
        any("cd backend &&" in s for s in deploy_sorok),
        "a `java -jar target/...` is megkapja a `cd backend`-et",
    )
    check(jr.ervenyes_pipeline(javitott), "a javított pipeline érvényes marad")


def test_valos_futas() -> None:
    print("\n[5] Valós futás végponttól végpontig")

    memoria = GYOKER / "szimulacio_memoria.json"
    if not memoria.exists():
        print("  – kihagyva (nincs szimulacio_memoria.json)")
        return

    runs = json.loads(memoria.read_text(encoding="utf-8")).get("runs", [])
    futas = next((r for r in reversed(runs) if len(r.get("uzenetek", [])) > 20), None)
    if not futas:
        print("  – kihagyva (nincs elég hosszú futás)")
        return

    files, stat = gi.collect_files(futas["uzenetek"], futas["memoria"], futas["feladat"])

    szemet = [p for p in files if "Component_" in p or "Class_" in p]
    check(not szemet, f"nincs névtelen szemétfájl (korábban 21 db Class_NN.java volt) – {len(szemet)}")

    # Ezek már a RÖGZÍTETT VÁZBÓL jönnek, nem a chat-logból.
    check("backend/pom.xml" in files, "a pom.xml a helyén van (vázból)")
    check("frontend/package.json" in files, "a package.json a helyén van (vázból)")

    java_fajlok = [p for p in files if p.endswith(".java")]
    for p in java_fajlok:
        pkg = ca.JAVA_PACKAGE.search(files[p])
        if pkg:
            vart = f"backend/src/main/java/{pkg.group(1).replace('.', '/')}/"
            check(p.startswith(vart), f"a package deklaráció egyezik a könyvtárral: {p}")

    springboot = [p for p in java_fajlok if "@SpringBootApplication" in files[p]]
    check(len(springboot) <= 1, f"legfeljebb egy @SpringBootApplication osztály ({len(springboot)} db)")

    check(stat["duplikatum"] >= 0, f"a deduplikáció naplózva ({stat['duplikatum']} összevont blokk)")
    check(jr.ervenyes_pipeline(files["Jenkinsfile"]), "a végleges Jenkinsfile érvényes")


def main() -> int:
    print("=" * 68)
    print("Build pipeline regressziós tesztek")
    print("=" * 68)
    test_java_utvonal()
    test_frontend_utvonalak()
    test_npm_start_hiba()
    test_jenkins_javitas()
    test_jenkins_22_regresszio()
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
