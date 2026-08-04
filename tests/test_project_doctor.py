# tests/test_project_doctor.py
"""Build-képességi tesztek — „építhető-e a Jenkins ebből?"

Minden eset a valós futásból visszafejtett, konkrét build-blokkoló.

Futtatás:  python3 tests/test_project_doctor.py
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

HIBAK: list[str] = []


def check(feltetel: bool, uzenet: str) -> None:
    print(f"  {'✓' if feltetel else '✗'} {uzenet}")
    if not feltetel:
        HIBAK.append(uzenet)


# A valós futásból származó, hibás frontend-konfiguráció.
ROMLOTT_PKG = json.dumps(
    {
        "name": "malom-game-frontend",
        "type": "module",
        "scripts": {"dev": "vite", "build": "tsc -b && vite build", "preview": "vite preview"},
        "dependencies": {"react": "^18.2.0", "react-dom": "^18.2.0", "zustand": "^4.5.0",
                         "@tailwindcss/vite": "^3.4.0"},
        "devDependencies": {"tailwindcss": "^3.4.0", "vite": "^5.0.8", "typescript": "^5.3.3"},
    },
    indent=2,
)

ROMLOTT_TSCONFIG = json.dumps(
    {
        "compilerOptions": {"strict": True, "noUnusedLocals": True, "noUnusedParameters": True,
                            "noEmit": True, "jsx": "react-jsx"},
        "include": ["src"],
        "references": [{"path": "./tsconfig.node.json"}],
    },
    indent=2,
)

ROMLOTT_VITE = """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/api': { target: 'http://localhost:9999', changeOrigin: true } } },
});
"""

PROPERTIES = "spring.application.name=malom\nserver.port=8080\n"


def romlott_projekt() -> dict:
    return {
        "frontend/package.json": ROMLOTT_PKG,
        "frontend/tsconfig.json": ROMLOTT_TSCONFIG,
        "frontend/vite.config.ts": ROMLOTT_VITE,
        "frontend/src/index.css": "@tailwind base;\n@tailwind components;\n",
        "frontend/src/App.tsx": "export default function App(){ return <div/>; }",
        "backend/pom.xml": (
            "<project><modelVersion>4.0.0</modelVersion>"
            "<dependencies><dependency><artifactId>spring-boot-starter-web</artifactId></dependency></dependencies>"
            "<build><plugins><plugin><artifactId>spring-boot-maven-plugin</artifactId></plugin></plugins></build>"
            "</project>"
        ),
        "backend/src/main/resources/application.properties": PROPERTIES,
    }


# ---------------------------------------------------------------------------
def test_diagnozis() -> None:
    print("\n[1] Diagnózis — felismeri-e a valós blokkolókat?")
    d = pd.diagnosztizal(romlott_projekt())
    kodok = {x.kod for x in d}

    check("nemletezo_verzio" in kodok, "felismeri a nem létező @tailwindcss/vite@^3.4.0 verziót")
    check("tailwind_keverek" in kodok, "felismeri a kevert v3/v4 Tailwind-setupot")
    check("logo_tsconfig_ref" in kodok, "felismeri a lógó tsconfig.node.json hivatkozást")
    check("ci_toro_stilusszabaly" in kodok, "felismeri a noUnusedLocals CI-törő hatását")
    check("hianyzo_postcss" in kodok, "felismeri a hiányzó postcss.config.js-t")
    check("port_elteres" in kodok, "felismeri a Vite proxy / backend port eltérést")

    blokkolok = [x for x in d if x.blokkolo]
    check(len(blokkolok) >= 3, f"a build-törő hibák blokkolóként vannak jelölve ({len(blokkolok)})")
    check(pd.diagnosztizal({}) == [], "üres projektre nincs diagnózis")


def test_javitas() -> None:
    print("\n[2] Javítás — build-képes lesz-e?")
    javitott, naplo = pd.javit(romlott_projekt())

    check(naplo, f"a javítás naplózott ({len(naplo)} bejegyzés)")
    check(pd.blokkolo_hibak(javitott) == [], "javítás után NINCS build-blokkoló hiba")

    pkg = json.loads(javitott["frontend/package.json"])
    egyben = {**pkg["dependencies"], **pkg["devDependencies"]}
    check("@tailwindcss/vite" not in egyben, "a nem létező csomag eltávolítva")
    check("postcss" in egyben and "autoprefixer" in egyben, "a v3 PostCSS-lánc kiegészítve")
    check("react" in egyben, "a valódi függőségek megmaradtak")

    vite = javitott["frontend/vite.config.ts"]
    check("@tailwindcss/vite" not in vite, "a vite.configból is kikerült az import")
    check("tailwindcss()" not in vite, "a plugin-hívás is eltűnt")
    check("react()" in vite, "a React plugin megmaradt")
    check("localhost:8080" in vite, "a proxy a backend tényleges portjára mutat")

    ts = json.loads(javitott["frontend/tsconfig.json"])
    check(ts["compilerOptions"]["noUnusedLocals"] is False, "noUnusedLocals kikapcsolva")
    check("frontend/tsconfig.node.json" in javitott, "a hiányzó tsconfig.node.json létrejött")
    check(json.loads(javitott["frontend/tsconfig.node.json"]), "a létrehozott tsconfig.node.json érvényes JSON")

    check("frontend/postcss.config.js" in javitott, "postcss.config.js létrejött")
    check("frontend/tailwind.config.js" in javitott, "tailwind.config.js létrejött")

    # Idempotencia: a második futás már ne csináljon semmit
    _, naplo2 = pd.javit(javitott)
    check(not naplo2, "a javítás idempotens (második futáson nincs változás)")

    # A bemenetet nem módosítja
    eredeti = romlott_projekt()
    masolat = dict(eredeti)
    pd.javit(eredeti)
    check(eredeti == masolat, "a javítás nem módosítja a bemeneti szótárat")


def test_port_egyseg() -> None:
    print("\n[3] Port-konzisztencia a teljes láncban")
    files = romlott_projekt()
    check(pd.backend_port(files) == "8080", "a portot az application.properties-ből olvassa")

    files2 = dict(files)
    files2["backend/src/main/resources/application.properties"] = "server.port=9090\n"
    check(pd.backend_port(files2) == "9090", "más portot is helyesen olvas ki")
    check(pd.backend_port({}) == pd.ALAP_BACKEND_PORT, "hiányzó properties esetén alapérték")

    info = jr.projekt_info(files2)
    check(info.be_port == "9090", "a Jenkins pipeline is ezt a portot kapja")

    generalt = jr.generalt_jenkinsfile(info)
    check("--server.port=9090" in generalt, "a deploy a helyes porton indít")
    check("localhost:9090" in generalt, "a health check a helyes portot figyeli")
    check("8081" not in generalt, "nincs beégetett 8081-es port")

    javitott, _ = pd.javit(files2)
    check("localhost:9090" in javitott["frontend/vite.config.ts"], "a Vite proxy is követi a portot")


def test_veg_pont_valos_futas() -> None:
    print("\n[4] Valós futás végponttól végpontig")
    memoria = GYOKER / "szimulacio_memoria.json"
    if not memoria.exists():
        print("  – kihagyva")
        return

    from workspace import workspace_from_messages

    runs = json.loads(memoria.read_text(encoding="utf-8")).get("runs", [])
    futas = next((r for r in reversed(runs) if len(r.get("uzenetek", [])) > 20), None)
    if not futas:
        print("  – kihagyva")
        return

    ws = workspace_from_messages(futas["uzenetek"], ["Informatikus", "IT", "UX", "Designer"])
    elotte = pd.blokkolo_hibak(ws.files)
    print(f"      build-blokkolók javítás előtt: {len(elotte)}")

    files, stat = gi.finalize_files(ws.files, futas["memoria"], futas["feladat"], futas["uzenetek"])
    check(
        stat["maradek_blokkolok"] == [],
        f"a feltöltött projektben nincs blokkoló ({stat['maradek_blokkolok']})",
    )
    # Ha a projekt eleve tiszta volt, nincs mit javítani – az is helyes kimenet.
    check(
        len(elotte) == 0 or bool(stat["doktor_javitasok"]),
        f"minden induló blokkolóhoz tartozik javítás ({len(elotte)} → {len(stat['doktor_javitasok'])})",
    )

    # A kulcsfájlok érvényesek maradtak
    for utvonal in ("frontend/package.json", "frontend/tsconfig.json"):
        try:
            json.loads(files[utvonal])
            check(True, f"{utvonal} érvényes JSON a javítás után")
        except (json.JSONDecodeError, KeyError) as exc:
            check(False, f"{utvonal} elromlott: {exc}")

    check(jr.ervenyes_pipeline(files["Jenkinsfile"]), "a Jenkinsfile érvényes")

    # Port-konzisztencia a végtermékben (keretrendszer-függetlenül)
    import re

    jf_portok = set(re.findall(r"--server\.port=(\d+)", files["Jenkinsfile"]))
    proxy_fajl = next(
        (p for p in ("frontend/vite.config.ts", "frontend/vite.config.js", "frontend/next.config.js")
         if p in files),
        None,
    )
    if proxy_fajl and "localhost:" in files[proxy_fajl]:
        proxy_portok = set(re.findall(r"localhost:(\d+)", files[proxy_fajl]))
        check(
            jf_portok == proxy_portok,
            f"a deploy és a frontend proxy ugyanazt a portot használja "
            f"({jf_portok} / {proxy_portok} — {proxy_fajl})",
        )
    else:
        check(bool(jf_portok), f"a deploy portja meg van adva a Jenkinsfile-ban ({jf_portok})")


def test_hibaturés() -> None:
    print("\n[5] Hibatűrés")
    check(pd.javit({})[0] == {}, "üres projektre nem omlik össze")

    romlott = {"frontend/package.json": "{ ez nem json", "frontend/tsconfig.json": "///"}
    d = pd.diagnosztizal(romlott)
    check(any(x.kod == "pkg_json_hibas" for x in d), "hibás JSON-t jelez")
    check(not any(x.javithato for x in d if x.kod == "pkg_json_hibas"), "hibás JSON-t nem próbálja javítani")
    javitott, _ = pd.javit(romlott)
    check(javitott["frontend/package.json"] == "{ ez nem json", "a javíthatatlan fájlt békén hagyja")

    # Trailing comma tolerancia
    tolerans = {"frontend/package.json": '{"dependencies": {"react": "^18.0.0",},}'}
    check(pd._json_betolt(tolerans["frontend/package.json"]) is not None, "trailing commát tolerál")


def main() -> int:
    print("=" * 68)
    print("Build-képességi (project_doctor) tesztek")
    print("=" * 68)
    test_diagnozis()
    test_javitas()
    test_port_egyseg()
    test_veg_pont_valos_futas()
    test_hibaturés()

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
