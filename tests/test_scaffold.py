# tests/test_scaffold.py
"""A rögzített váz tesztjei — „reprodukálható-e még a korábbi bukás?"

A tesztek az összes eddigi VALÓS Jenkins-bukást megpróbálják előidézni azzal,
hogy az ágens pontosan azt a hibás kimenetet adja, ami akkor bukott. A váz
zárolása miatt egyiknek sem szabad átjutnia a fájlfába.

Futtatás:  python3 tests/test_scaffold.py
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

import github_integration as gi  # noqa: E402
import jenkins_repair as jr  # noqa: E402
import project_doctor as pd  # noqa: E402
import scaffold  # noqa: E402
from workspace import VirtualWorkspace, ellenoriz  # noqa: E402

BT = chr(96) * 3
SZEREPEK = ["Informatikus", "IT", "UX", "Designer", "DevOps"]
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
def test_vaz_epsege() -> None:
    print("\n[1] A váz önmagában build-képes")
    ws = VirtualWorkspace.vazzal()

    check(len(ws) >= 13, f"a váz minden fájlja megvan ({len(ws)} db)")
    check(pd.blokkolo_hibak(ws.files) == [], "nincs build-blokkoló hiba")
    # A friss váz EGYETLEN kifogása a placeholder App.tsx – ez szándékos.
    hibak = ellenoriz(ws)
    check(len(hibak) == 1 and "PLACEHOLDER" in hibak[0], f"csak a placeholdert kifogásolja ({hibak})")

    pkg = json.loads(ws.get("frontend/package.json"))
    check("build" in pkg["scripts"] and "dev" in pkg["scripts"], "van build és dev script")
    check(
        all(not v.startswith("^") and not v.startswith("~") for v in pkg["dependencies"].values()),
        "a függőségek pontos verzióra pinneltek",
    )
    check("tailwindcss-animate" in pkg["devDependencies"], "a tailwindcss-animate benne van (#24 oka)")

    # A tsconfig ne hivatkozzon nem létező projektre (#20 oka)
    ts = json.loads(ws.get("frontend/tsconfig.json"))
    check("references" not in ts, "nincs lógó tsconfig `references` hivatkozás")
    check(ts["compilerOptions"]["noUnusedLocals"] is False, "a stílusszabályok nem törik a buildet")

    # Az index.css csak direktívákat tartalmaz — nincs @apply
    check("@apply" not in ws.get("frontend/src/index.css"), "az alap CSS-ben nincs @apply")

    info = jr.projekt_info(ws.files)
    check(info.keretrendszer == "vite", "a stack egyértelműen Vite")
    check(jr.ervenyes_pipeline(jr.generalt_jenkinsfile(info)), "a generált Jenkinsfile érvényes")


def test_backend_port_es_health() -> None:
    """A Jenkins konténerben a 8080 FOGLALT (maga a Jenkins figyel rajta).

    Ha a Spring Boot is a 8080-ra próbál bindolni, némán elhal
    („Port 8080 was already in use”), a health check pedig a Jenkins saját
    weboldalát fogadja el élő backendnek → zöld build, halott API.
    """
    print("\n[1b] Backend port és health check megbízhatósága")
    ws = VirtualWorkspace.vazzal()
    import re

    port = pd.backend_port(ws.files)
    check(port != "8080", f"a backend NEM a Jenkins portján fut ({port})")
    check(
        f"server.port={port}" in ws.get("backend/src/main/resources/application.properties"),
        "az application.properties ezt a portot rögzíti",
    )
    check(
        f"localhost:{port}" in ws.get("frontend/vite.config.ts"),
        "a Vite proxy ugyanerre a portra mutat",
    )
    check(
        "spring-boot-starter-actuator" in ws.get("backend/pom.xml"),
        "az actuator benne van (enélkül a health check 404-et kapna)",
    )

    jf = jr.generalt_jenkinsfile(jr.projekt_info(ws.files))
    check(set(re.findall(r"--server\.port=(\d+)", jf)) == {port}, "a deploy is ezen a porton indít")
    check('"status":"UP"' in jf, "a health check konkrét UP állapotot vár")
    check(
        "grep -qE '2|3|4'" not in jf,
        "nincs gyenge „bármilyen HTTP válasz jó” fallback (ez fogadta el a Jenkins UI-t)",
    )

    # #29: a BUILD_ID=dontKillMe miatt az előző build backendje még futott,
    # ezért a friss deploy nem tudott bindolni ("Port 8081 was already in use").
    stage_nevek = re.findall(r"stage\('([^']+)'\)", jf)
    check("Stop Previous" in stage_nevek, "van 'Stop Previous' stage a takarításhoz")
    check(
        stage_nevek.index("Stop Previous") < stage_nevek.index("Backend Deploy"),
        "a takarítás a deploy ELŐTT fut",
    )
    check("pkill -f 'spring-boot:run'" in jf, "leállítja a korábbi backend példányt")
    check("pkill -f 'npm run dev'" in jf, "leállítja a korábbi frontend példányt")


def test_vedett_utvonalak() -> None:
    print("\n[2] Az ágens NEM tudja elrontani a build-konfigurációt")
    ws = VirtualWorkspace.vazzal()
    eredeti_pkg = ws.get("frontend/package.json")
    eredeti_ts = ws.get("frontend/tsconfig.json")
    eredeti_pom = ws.get("backend/pom.xml")

    # A #20-as bukás: nem létező verzió a package.json-ban.
    tamadas = uzenet(
        blokk("json", '// File: frontend/package.json\n'
                      '{"dependencies": {"@tailwindcss/vite": "^3.4.0"}}')
        + "\n"
        + blokk("json", '// File: frontend/tsconfig.json\n'
                        '{"references": [{"path": "./nemletezik.json"}]}')
        + "\n"
        + blokk("xml", "<!-- File: backend/pom.xml -->\n<project>csonka</project>")
    )
    valtozasok = ws.alkalmaz(tamadas, SZEREPEK)

    check(ws.get("frontend/package.json") == eredeti_pkg, "a package.json érintetlen maradt")
    check(ws.get("frontend/tsconfig.json") == eredeti_ts, "a tsconfig.json érintetlen maradt")
    check(ws.get("backend/pom.xml") == eredeti_pom, "a pom.xml érintetlen maradt")
    check(
        sum(1 for v in valtozasok if v.tipus == "elutasitott") >= 3,
        "mindhárom kísérlet elutasítva és naplózva",
    )
    check(pd.blokkolo_hibak(ws.files) == [], "a projekt továbbra is build-képes")

    # DELETE direktívával sem lehet kilőni a vázat.
    ws.alkalmaz(uzenet("DELETE: frontend/package.json\nDELETE: backend/pom.xml"), SZEREPEK)
    check("frontend/package.json" in ws and "backend/pom.xml" in ws, "DELETE sem törli a vázat")


def test_css_vedelem() -> None:
    print("\n[3] A #24-es bukás (`@apply animate-in`) nem reprodukálható")
    ws = VirtualWorkspace.vazzal()

    tamadas = uzenet(
        blokk(
            "css",
            "/* File: frontend/src/styles/custom.css */\n"
            ".modal {\n"
            "  @apply animate-in fade-in slide-in-from-bottom-4;\n"
            "  color: red;\n"
            "}\n",
        )
    )
    valtozasok = ws.alkalmaz(tamadas, SZEREPEK)

    css_fajlok = [p for p in ws.files if p.endswith(".css")]
    osszes_css = "\n".join(ws.get(p) for p in css_fajlok)
    check("@apply" not in osszes_css, "egyetlen CSS fájlban sincs @apply direktíva")
    check("color: red" in osszes_css, "a valódi CSS szabályok megmaradtak")
    check(
        any("@apply" in v.indok for v in valtozasok),
        "a szűrés naplózva van (az ágens értesül róla)",
    )


def test_fuggoseg_allowlist() -> None:
    print("\n[4] Függőség csak allowlistáról, rögzített verzióval")
    ws = VirtualWorkspace.vazzal()

    ws.alkalmaz(
        uzenet("Szükségem lesz ezekre:\nDEPENDENCY: axios\nDEPENDENCY: kitalalt-csomag-xyz"),
        SZEREPEK,
    )
    pkg = json.loads(ws.get("frontend/package.json"))
    deps = pkg["dependencies"]

    check("axios" in deps, "az engedélyezett csomag bekerült")
    check(deps["axios"] == scaffold.ENGEDELYEZETT_EXTRA_DEPS["axios"], "rögzített verzióval")
    check("kitalalt-csomag-xyz" not in deps, "a kitalált csomag NEM került be")
    check(pd.blokkolo_hibak(ws.files) == [], "a package.json build-képes maradt")

    # A verziót az ágens nem tudja felülírni
    ws.alkalmaz(uzenet("DEPENDENCY: axios"), SZEREPEK)
    check(json.loads(ws.get("frontend/package.json"))["dependencies"]["axios"] == deps["axios"],
          "ismételt kérés nem változtat a verzión")


def test_alkalmazaskod_atmegy() -> None:
    print("\n[5] A valódi alkalmazáskód viszont átmegy")
    ws = VirtualWorkspace.vazzal()

    ws.alkalmaz(
        uzenet(
            blokk(
                "tsx",
                "// File: frontend/src/components/LoginForm.tsx\n"
                "export default function LoginForm() {\n"
                "  return <form className='animate-in fade-in p-4' />;\n"
                "}\n",
            )
            + "\n"
            + blokk(
                "java",
                "// File: backend/src/main/java/com/app/controller/AuthController.java\n"
                "package com.app.controller;\n"
                "import org.springframework.web.bind.annotation.*;\n"
                "@RestController\npublic class AuthController { }\n",
            )
        ),
        SZEREPEK,
    )

    check("frontend/src/components/LoginForm.tsx" in ws, "a React komponens bekerült")
    check(
        "backend/src/main/java/com/app/controller/AuthController.java" in ws,
        "a Spring controller bekerült a helyes csomagba",
    )
    check(
        "animate-in" in ws.get("frontend/src/components/LoginForm.tsx"),
        "a JSX-beli utility osztály érintetlen (csak a CSS @apply tilos)",
    )
    # Amíg az App.tsx placeholder, a védőkorlát jelez – ez a #26-os tanulság.
    check(
        any("PLACEHOLDER" in h for h in ellenoriz(ws)),
        "a placeholder App.tsx jelzésre kerül, hiába van már komponens",
    )

    ws.alkalmaz(
        uzenet(
            blokk(
                "tsx",
                "// File: frontend/src/App.tsx\n"
                "import LoginForm from './components/LoginForm';\n"
                "export default function App() { return <LoginForm />; }\n",
            )
        ),
        SZEREPEK,
    )
    check(ellenoriz(ws) == [], f"App.tsx lecserélése után tiszta ({ellenoriz(ws)})")


def test_jenkinsfile_determinisztikus() -> None:
    print("\n[6] A Jenkinsfile-t a rendszer adja, nem az ágens")
    ws = VirtualWorkspace.vazzal()

    # A #22-es bukás: `local` a health checkben, rossz deploy parancsok.
    agens_pipeline = blokk(
        "groovy",
        "pipeline { agent any\n stages {\n"
        "  stage('Health Check') { steps { sh 'local max_retries=30' } }\n"
        "  stage('Deploy') { steps { sh 'nohup java -jar x.jar -Dspring-boot.run.arguments=--server.port=9999' } }\n"
        " }\n}",
    )
    files, stat = gi.finalize_files(
        ws.files, "memória", "feladat", [uzenet(agens_pipeline, "DevOps Engineer")]
    )

    jf = files["Jenkinsfile"]
    check(stat["jenkins_forras"] == "generalt", "a Jenkinsfile determinisztikusan generált")
    check("local max_retries" not in jf, "az ágens `local` sora nem került be (#22 oka)")
    check("9999" not in jf, "az ágens kitalált portja nem került be")
    check("dir('frontend')" in jf and "dir('backend')" in jf, "minden parancs dir() blokkban fut")
    check("Health Check" in jf, "van health check stage")
    check(jr.ervenyes_pipeline(jf), "a pipeline szintaktikailag érvényes")

    nohup_sorok = [s for s in jf.splitlines() if "nohup" in s]
    check(
        nohup_sorok and all(s.rstrip().rstrip("'").rstrip().endswith("&") for s in nohup_sorok),
        "minden szerverindítás háttérben, naplóval",
    )
    check(stat["maradek_blokkolok"] == [], "a feltölthető projektben nincs blokkoló")


def test_teljes_sprint_szimulacio() -> None:
    print("\n[7] Teljes sprint szimulálása rossz viselkedésű ágenssel")
    ws = VirtualWorkspace.vazzal()

    # Minden korábbi hibatípus egyszerre, 3 iterációban.
    tamadasok = [
        blokk("json", '// File: frontend/package.json\n{"dependencies":{"nemletezo":"^99.0.0"}}'),
        blokk("css", "/* File: frontend/src/index.css */\n@apply animate-in;\nbody{margin:0}"),
        blokk("xml", "<!-- File: backend/pom.xml -->\n<broken"),
        blokk("groovy", "pipeline { sh 'local x=1' }"),
        blokk("tsx", "// File: frontend/src/App.tsx\nexport default function App(){return <div/>}"),
        blokk(
            "java",
            "// File: backend/src/main/java/com/app/service/UserService.java\n"
            "package com.app.service;\npublic class UserService {}",
        ),
    ]
    for i in range(3):
        for t in tamadasok:
            ws.alkalmaz(uzenet(t), SZEREPEK)

    check(pd.blokkolo_hibak(ws.files) == [], f"3 iteráció után sincs blokkoló ({pd.blokkolo_hibak(ws.files)})")
    check(ellenoriz(ws) == [], f"a statikus ellenőrzés tiszta ({ellenoriz(ws)})")
    check("@apply" not in ws.get("frontend/src/index.css"), "az index.css tiszta maradt")
    check(json.loads(ws.get("frontend/package.json")), "a package.json érvényes JSON maradt")
    check("nemletezo" not in ws.get("frontend/package.json"), "a kitalált csomag nem került be")
    check("frontend/src/App.tsx" in ws, "a valódi alkalmazáskód viszont bekerült")
    check(
        "backend/src/main/java/com/app/service/UserService.java" in ws,
        "a backend service is bekerült",
    )

    files, stat = gi.finalize_files(ws.files, "m", "f", [])
    check(stat["maradek_blokkolok"] == [], "a végtermék build-képes")
    check(jr.ervenyes_pipeline(files["Jenkinsfile"]), "a végleges Jenkinsfile érvényes")


def main() -> int:
    print("=" * 68)
    print("Rögzített váz — stabilitási tesztek")
    print("=" * 68)
    test_vaz_epsege()
    test_backend_port_es_health()
    test_vedett_utvonalak()
    test_css_vedelem()
    test_fuggoseg_allowlist()
    test_alkalmazaskod_atmegy()
    test_jenkinsfile_determinisztikus()
    test_teljes_sprint_szimulacio()

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
