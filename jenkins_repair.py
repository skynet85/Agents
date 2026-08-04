# jenkins_repair.py
"""A DevOps ágens Jenkinsfile-jának validálása és automatikus javítása.

A `szimulacio_memoria.json`-ban lévő valós futásokból visszafejtett hibák,
amiért „a generált Jenkins fájlból nem készült el az alkalmazás”:

1. **Hiányzó könyvtárváltás a deploy lépésben.** Az ágens így írta:
       sh 'cd frontend && npm install'          <- jó
       sh 'nohup npm start > frontend.log &'    <- a REPÓ GYÖKERÉBŐL fut!
   A gyökérben nincs `package.json`, így az `npm` azonnal meghalt
   (`ENOENT: no such file or directory, open '.../package.json'`).
   Ugyanez a backendnél: `mvn spring-boot:run` POM nélküli könyvtárban.

2. **Nem létező npm script.** A pipeline `npm start`-ot hívott, de a generált
   Vite-es `package.json`-ban csak `dev`/`build`/`preview` volt
   → `npm ERR! Missing script: "start"`.

3. **Néma hiba.** A `nohup ... &` MINDIG 0 exit kóddal tér vissza, ezért a
   Jenkins ZÖLD buildet jelzett, miközben az alkalmazás el sem indult.
   Innen a „sikeres build, de nincs app” tünet.

4. **No-op zöld build.** Ha a `when { expression { fileExists(...) } }` őrök
   egyike sem teljesült, MINDEN stage kimaradt, és a pipeline sikeresen
   befejeződött – nulla elvégzett munkával.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import code_analysis
import project_doctor

FRONTEND_DIR = "frontend"
BACKEND_DIR = "backend"

SH_MINTA = re.compile(r"""(?P<elo>\bsh\s*\(?\s*)(?P<idezo>'''|\"\"\"|'|")(?P<parancs>.*?)(?P=idezo)""", re.DOTALL)
DIR_NYITAS = re.compile(r"""\bdir\s*\(\s*['"]([^'"]+)['"]\s*\)\s*\{""")

NPM_JEL = re.compile(r"\b(npm|npx|yarn|pnpm|node)\b")
# A `java -jar target/...` is backend-parancs: a lefordított jar a backend/target
# alatt van, tehát ugyanúgy könyvtárváltást igényel, mint a Maven hívások.
MVN_JEL = re.compile(r"\b(?:mvn|mvnw|gradle)\b|\bjava\s+.*-jar\s+target/")

# Olyan parancsok, amelyek NEM térnek vissza maguktól: háttérbe kell tenni őket,
# különben a Jenkins `sh` lépés örökre vár (vagy a folyamat a lépéssel együtt hal).
HOSSZAN_FUTO = re.compile(
    r"\b(?:"
    r"nohup"
    r"|java\s+.*-jar"
    r"|spring-boot:run"
    r"|next\s+(?:start|dev)"
    r"|npm\s+start"
    r"|npm\s+run\s+(?:dev|start|preview|serve)"
    r"|vite(?:\s+preview)?"
    r"|serve\s+-s"
    r")\b"
)


def _hosszan_futo(parancs: str) -> bool:
    """Igaz, ha a parancs egy szervert indít (nem tér vissza magától)."""
    return bool(HOSSZAN_FUTO.search(parancs))


@dataclass
class ProjektInfo:
    """A ténylegesen feltöltendő fájlokból kiolvasott build-kontextus."""

    van_frontend: bool = False
    van_backend: bool = False
    van_db: bool = False
    npm_scriptek: Dict[str, str] = field(default_factory=dict)
    npm_fuggosegek: Dict[str, str] = field(default_factory=dict)
    # A backend TÉNYLEGES portja az application.properties alapján – nem fix 8081.
    be_port: str = project_doctor.ALAP_BACKEND_PORT

    @property
    def keretrendszer(self) -> str:
        return code_analysis.framework_felismeres(self.npm_scriptek, self.npm_fuggosegek)

    @property
    def start_parancs(self) -> str:
        return code_analysis.indito_parancs(self.npm_scriptek, self.npm_fuggosegek)[0]

    @property
    def frontend_port(self) -> str:
        return code_analysis.indito_parancs(self.npm_scriptek, self.npm_fuggosegek)[1]

    @property
    def van_build(self) -> bool:
        return code_analysis.van_build_script(self.npm_scriptek)


def projekt_info(files: Dict[str, str]) -> ProjektInfo:
    info = ProjektInfo(
        van_frontend=f"{FRONTEND_DIR}/package.json" in files,
        van_backend=f"{BACKEND_DIR}/pom.xml" in files,
        van_db=any(p.startswith("database/") for p in files),
        be_port=project_doctor.backend_port(files),
    )
    csomag = files.get(f"{FRONTEND_DIR}/package.json")
    if csomag:
        info.npm_scriptek = code_analysis.package_json_scriptek(csomag)
        adat = project_doctor._json_betolt(csomag) or {}
        info.npm_fuggosegek = {
            **(adat.get("dependencies") or {}),
            **(adat.get("devDependencies") or {}),
        }
    return info


# ---------------------------------------------------------------------------
# dir() kontextus követése
# ---------------------------------------------------------------------------
def _dir_kontextus(szoveg: str, pozicio: int) -> Optional[str]:
    """Megmondja, melyik `dir('...')` blokkon belül van az adott pozíció."""
    stack: List[Tuple[str, int]] = []
    melyseg = 0
    i = 0
    while i < min(pozicio, len(szoveg)):
        talalat = DIR_NYITAS.match(szoveg, i)
        if talalat:
            melyseg += 1
            stack.append((talalat.group(1), melyseg))
            i = talalat.end()
            continue
        ch = szoveg[i]
        if ch == "{":
            melyseg += 1
        elif ch == "}":
            while stack and stack[-1][1] > melyseg:
                stack.pop()
            melyseg -= 1
            while stack and stack[-1][1] > melyseg:
                stack.pop()
        i += 1
    return stack[-1][0] if stack else None


def _mar_valt_konyvtarat(parancs: str, konyvtar: str) -> bool:
    return bool(re.search(rf"\bcd\s+\.?/?{re.escape(konyvtar)}\b", parancs))


# ---------------------------------------------------------------------------
# Egyedi parancs-javítások
# ---------------------------------------------------------------------------
def _javit_parancs(
    parancs: str, dir_kontextus: Optional[str], info: ProjektInfo, valtozasok: List[str]
) -> str:
    eredeti = parancs
    npm = bool(NPM_JEL.search(parancs))
    mvn = bool(MVN_JEL.search(parancs))

    # 1. npm ci -> npm install (package-lock.json nélkül az `npm ci` mindig elbukik)
    if re.search(r"\bnpm\s+ci\b", parancs):
        parancs = re.sub(r"\bnpm\s+ci\b", "npm install", parancs)
        valtozasok.append("`npm ci` → `npm install` (nincs package-lock.json)")

    # 2. Nem létező npm script cseréje létezőre
    if info.npm_scriptek:
        if re.search(r"\bnpm\s+start\b", parancs) and "start" not in info.npm_scriptek:
            parancs = re.sub(r"\bnpm\s+start\b", info.start_parancs, parancs)
            valtozasok.append(
                f"`npm start` → `{info.start_parancs}` "
                "(a package.json-ban nincs `start` script)"
            )
        if re.search(r"\bnpm\s+run\s+build\b", parancs) and not info.van_build:
            parancs = re.sub(r"\bnpm\s+run\s+build\b", "echo 'nincs build script – kihagyva'", parancs)
            valtozasok.append("`npm run build` kihagyva (nincs ilyen script)")

    # 2b. Keretrendszer-idegen kapcsolók. A Next.js a `-H` / `-p`, a Vite a
    #     `--host` / `--port` alakot érti; felcserélve azonnal kilépnek. Ez akkor is
    #     javítandó, ha a parancsot nem mi állítottuk elő (az ágens másolta be).
    if npm and info.keretrendszer == "next" and re.search(r"--(?:host|port)\b", parancs):
        parancs = re.sub(r"--host\b", "-H", parancs)
        parancs = re.sub(r"--port\b", "-p", parancs)
        valtozasok.append(
            "Next.js kapcsolók javítva (`--host/--port` → `-H/-p`) — a Next.js "
            "a Vite-os alakot nem érti és azonnal kilép"
        )
    elif npm and info.keretrendszer == "vite" and re.search(r"(?<!\w)-[Hp]\s+\S", parancs):
        parancs = re.sub(r"(?<!\w)-H\b", "--host", parancs)
        parancs = re.sub(r"(?<!\w)-p\b", "--port", parancs)
        valtozasok.append("Vite kapcsolók javítva (`-H/-p` → `--host/--port`)")

    # 3. Hiányzó könyvtárváltás – EZ a fő hibaok
    if npm and dir_kontextus != FRONTEND_DIR and not _mar_valt_konyvtarat(parancs, FRONTEND_DIR):
        parancs = f"cd {FRONTEND_DIR} && {parancs}"
        valtozasok.append(f"`cd {FRONTEND_DIR}` beszúrva egy npm parancs elé")
    elif mvn and dir_kontextus != BACKEND_DIR and not _mar_valt_konyvtarat(parancs, BACKEND_DIR):
        parancs = f"cd {BACKEND_DIR} && {parancs}"
        valtozasok.append(f"`cd {BACKEND_DIR}` beszúrva egy Maven parancs elé")

    # 4. A `spring-boot:run` nem veszi át a Maven `-D` property-ket app-argumentumként.
    #    A `-Dserver.port=8081` így a JVM-re vonatkozott, az app pedig maradt 8080-on.
    if "spring-boot:run" in parancs:
        ujj, db = re.subn(
            r"-Dserver\.port=(\d+)", r"-Dspring-boot.run.arguments=--server.port=\1", parancs
        )
        if db:
            parancs = ujj
            valtozasok.append(
                "`-Dserver.port=…` → `-Dspring-boot.run.arguments=--server.port=…` "
                "(különben az app a konfigurált porton indult, nem a megadotton)"
            )
        # A portnak egyeznie kell az application.properties-szel és a health checkkel.
        ujj, db = re.subn(
            r"(--server\.port=)(\d+)",
            lambda m: m.group(1) + info.be_port,
            parancs,
        )
        if db and ujj != parancs:
            parancs = ujj
            valtozasok.append(
                f"A deploy port {info.be_port}-ra igazítva (az application.properties szerint)"
            )

    # 5. `local` a függvényen kívül — a Jenkins `sh` lépés /bin/sh-t (dash) használ,
    #    ahol a `local` CSAK függvényen belül érvényes:
    #       script.sh.copy: 3: local: not in a function  → exit 2
    #    A bash-t megszokott modell rendszeresen beleírja a health checkbe.
    uj, db = re.subn(r"(?m)^(\s*)local\s+(\w+=)", r"\1\2", parancs)
    if db:
        parancs = uj
        valtozasok.append(
            "`local` eltávolítva a shell-szkriptből (a Jenkins `sh` dash-t használ, "
            "ahol ez függvényen kívül hibát dob)"
        )

    # 6. `java -jar` esetén a port NEM Maven-property. A `-Dspring-boot.run.arguments`
    #    a jar UTÁN egyszerű programargumentum, amit a Spring nem ért → az app a
    #    default porton indul. Helyesen: `--server.port=X` a jar után.
    if re.search(r"\bjava\s+.*-jar\b", parancs):
        uj, db = re.subn(
            r"-Dspring-boot\.run\.arguments=--server\.port=(\d+)", r"--server.port=\1", parancs
        )
        if db:
            parancs = uj
            valtozasok.append(
                "`java -jar` mellett `-Dspring-boot.run.arguments=…` → `--server.port=…` "
                "(különben az app a default porton indult)"
            )
        # A JVM-property alak csak a `-jar` ELŐTT működik – ha utána van, átalakítjuk.
        uj, db = re.subn(
            r"(-jar\s+\S+)(\s+)-Dserver\.port=(\d+)", r"\1\2--server.port=\3", parancs
        )
        if db:
            parancs = uj
            valtozasok.append("`-Dserver.port=…` a jar után `--server.port=…` alakra cserélve")

    # 7. Háttérfolyamat: stdin lezárása és BUILD_ID, hogy a Jenkins ne ölje meg
    if _hosszan_futo(parancs) and not parancs.rstrip().endswith("&"):
        naplo = "backend.log" if MVN_JEL.search(parancs) or "java" in parancs else "frontend.log"
        parancs = parancs.rstrip()
        if not re.search(r">\s*\S+\.log", parancs):
            parancs += f" > {naplo} 2>&1"
        parancs += " &"
        valtozasok.append(
            f"A szerverindítás háttérbe téve (`> {naplo} 2>&1 &`) — enélkül a Jenkins "
            "lépés a folyamatra várva blokkolna, és nem maradna napló"
        )

    if parancs.rstrip().endswith("&"):
        hianyzo = [
            v for v in ("BUILD_ID=dontKillMe", "JENKINS_NODE_COOKIE=dontKillMe")
            if v.split("=")[0] not in parancs
        ]
        if hianyzo:
            elotag = " ".join(hianyzo)
            if re.search(r"\bnohup\b", parancs):
                parancs = re.sub(r"\bnohup\b", f"{elotag} nohup", parancs, count=1)
            else:
                parancs = f"{elotag} nohup {parancs}"
            valtozasok.append(f"`{elotag}` hozzáadva a háttérfolyamathoz")
        if "< /dev/null" not in parancs and "</dev/null" not in parancs:
            parancs = parancs.rstrip()[:-1].rstrip() + " < /dev/null &"
            valtozasok.append("`< /dev/null` hozzáadva (különben az sh lépés blokkolhat)")

    return parancs if parancs != eredeti else eredeti


# ---------------------------------------------------------------------------
# Health-check és no-op védelem
# ---------------------------------------------------------------------------
def _healthcheck_stage(info: ProjektInfo) -> str:
    ellenorzesek = []
    if info.van_frontend:
        ellenorzesek.append(
            f"""                    echo '--- Frontend ellenőrzés (port {info.frontend_port}) ---'
                    ok=0
                    for i in $(seq 1 30); do
                      if curl -sf -o /dev/null http://localhost:{info.frontend_port}; then ok=1; break; fi
                      sleep 2
                    done
                    if [ "$ok" != "1" ]; then
                      echo 'A FRONTEND NEM INDULT EL. Napló:'
                      cat frontend/frontend.log 2>/dev/null || echo '(nincs napló)'
                      exit 1
                    fi
                    echo 'Frontend fut.'"""
        )
    if info.van_backend:
        ellenorzesek.append(
            f"""                    echo '--- Backend ellenőrzés (port {info.be_port}) ---'
                    # KIZÁRÓLAG az actuator health számít. A korábbi "bármilyen
                    # HTTP válasz jó" logika a Jenkins SAJÁT weboldalát fogadta el
                    # élő backendnek, ha a port ütközött – zöld build, halott app.
                    ok=0
                    for i in $(seq 1 45); do
                      if curl -sf http://localhost:{info.be_port}/actuator/health 2>/dev/null | grep -q '"status":"UP"'; then ok=1; break; fi
                      sleep 2
                    done
                    if [ "$ok" != "1" ]; then
                      echo 'A BACKEND NEM INDULT EL (nincs UP állapot az actuatoron). Napló:'
                      cat backend/backend.log 2>/dev/null || echo '(nincs napló)'
                      echo '--- Tipp: "Port already in use" esetén fut még egy korábbi példány.'
                      echo '    Kézzel:  pkill -f spring-boot:run   (a Jenkins konténerben) ---'
                      exit 1
                    fi
                    echo 'Backend fut.'"""
        )
    if not ellenorzesek:
        return ""

    torzs = "\n".join(ellenorzesek)
    return f"""
        stage('Health Check') {{
            steps {{
                sh '''
{torzs}
                '''
            }}
        }}"""


def _stop_previous_stage(info: ProjektInfo) -> str:
    """Leállítja az ELŐZŐ build által indított példányokat.

    A `BUILD_ID=dontKillMe` szándékosan túlélteti a folyamatokat a build végén —
    különben a Jenkins leölné a friss deploy-t. A mellékhatás viszont az, hogy a
    KÖVETKEZŐ build már nem tud bindolni:

        Web server failed to start. Port 8081 was already in use.

    Ezért minden deploy előtt takarítani kell. Ráadásul enélkül a böngészőben
    simán a korábbi build alkalmazása maradna, miközben a pipeline zöld.
    """
    elotag = " " * 20
    parancsok = []
    if info.van_backend:
        parancsok.append(f"{elotag}pkill -f 'spring-boot:run' 2>/dev/null || true")
        parancsok.append(f"{elotag}pkill -f 'app-backend.*\\.jar' 2>/dev/null || true")
    if info.van_frontend:
        parancsok.append(f"{elotag}pkill -f 'npm run dev' 2>/dev/null || true")
        parancsok.append(f"{elotag}pkill -f 'node.*vite' 2>/dev/null || true")
    if not parancsok:
        return ""

    torzs = "\n".join(parancsok)
    portok = " ".join(p for p in (info.frontend_port if info.van_frontend else "",
                                  info.be_port if info.van_backend else "") if p)
    return f"""
        stage('Stop Previous') {{
            steps {{
                sh '''
{torzs}
                    sleep 3
                    for port in {portok}; do
                      if ! curl -s -o /dev/null --max-time 2 http://localhost:$port; then
                        echo "A $port port szabad."
                        continue
                      fi
                      echo "FIGYELEM: a $port portot MÁS folyamat tartja. Ki az?"
                      # A Jenkins saját magát elárulja egy egyedi fejléccel.
                      if curl -sI --max-time 2 http://localhost:$port | grep -qi 'X-Jenkins'; then
                        echo "  >> MAGA A JENKINS figyel a $port porton!"
                        echo "  >> Változtasd meg a backend portját (scaffold.py: BACKEND_PORT)."
                      fi
                      curl -sI --max-time 2 http://localhost:$port | head -5 || true
                      if command -v ss >/dev/null 2>&1; then
                        ss -tlnp 2>/dev/null | grep ":$port" || true
                      elif command -v netstat >/dev/null 2>&1; then
                        netstat -tlnp 2>/dev/null | grep ":$port" || true
                      else
                        echo "  (nincs ss/netstat a konténerben)"
                      fi
                      ps -eo pid,args 2>/dev/null | grep -E 'java|node' | grep -v grep || true
                    done
                '''
            }}
        }}"""


def _noop_orszem() -> str:
    """Ha egyetlen build-fájl sincs a helyén, a pipeline BUKJON, ne legyen zöld."""
    return """
        stage('Sanity Check') {
            steps {
                script {
                    def fe = fileExists('frontend/package.json')
                    def be = fileExists('backend/pom.xml')
                    echo "frontend/package.json=${fe}  backend/pom.xml=${be}"
                    if (!fe && !be) {
                        error('Egyetlen build-leíró sincs a repóban – nincs mit építeni.')
                    }
                }
            }
        }"""


# ---------------------------------------------------------------------------
# Determinisztikus fallback pipeline
# ---------------------------------------------------------------------------
def generalt_jenkinsfile(info: ProjektInfo) -> str:
    """Biztosan működő pipeline a ténylegesen feltöltött fájlok alapján."""
    stages = [_noop_orszem(), _stop_previous_stage(info)]

    if info.van_frontend:
        # A `vite build` CSAK a belépési pontból elérhető kódot fordítja, ezért egy
        # nem importált, hibás komponens észrevétlen marad (lásd #26: hiányzó
        # `../lib/gameLogic` import egy soha nem renderelt oldalon). A `tsc --noEmit`
        # a tsconfig `include` alatti MINDEN fájlt ellenőrzi.
        tipus_lepes = (
            "                    sh 'npm run typecheck'\n"
            if "typecheck" in info.npm_scriptek
            else ""
        )
        build_lepes = tipus_lepes + (
            "                    sh 'npm run build'\n" if info.van_build else ""
        )
        stages.append(
            f"""
        stage('Frontend Build') {{
            when {{ expression {{ fileExists('frontend/package.json') }} }}
            tools {{ nodejs 'Node18' }}
            steps {{
                dir('frontend') {{
                    sh 'npm install'
{build_lepes}                }}
            }}
        }}
        stage('Frontend Deploy') {{
            when {{ expression {{ fileExists('frontend/package.json') }} }}
            tools {{ nodejs 'Node18' }}
            steps {{
                dir('frontend') {{
                    sh 'BUILD_ID=dontKillMe JENKINS_NODE_COOKIE=dontKillMe nohup {info.start_parancs} > frontend.log 2>&1 < /dev/null &'
                }}
            }}
        }}"""
        )

    if info.van_backend:
        stages.append(
            f"""
        stage('Backend Build') {{
            when {{ expression {{ fileExists('backend/pom.xml') }} }}
            tools {{ maven 'Maven3' }}
            steps {{
                dir('backend') {{
                    sh 'mvn -B clean package -DskipTests'
                }}
            }}
        }}
        stage('Backend Deploy') {{
            when {{ expression {{ fileExists('backend/pom.xml') }} }}
            tools {{ maven 'Maven3' }}
            steps {{
                dir('backend') {{
                    sh 'BUILD_ID=dontKillMe JENKINS_NODE_COOKIE=dontKillMe nohup mvn spring-boot:run -Dspring-boot.run.arguments=--server.port={info.be_port} > backend.log 2>&1 < /dev/null &'
                }}
            }}
        }}"""
        )

    stages.append(_healthcheck_stage(info))
    torzs = "".join(s for s in stages if s)

    return f"""// Determinisztikusan generálva a ténylegesen feltöltött fájlok alapján.
pipeline {{
    agent any
    options {{
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
    }}
    stages {{{torzs}
    }}
    post {{
        failure {{
            echo 'A pipeline elbukott – nézd meg a frontend.log / backend.log tartalmát.'
        }}
    }}
}}
"""


# ---------------------------------------------------------------------------
# Fő belépési pont
# ---------------------------------------------------------------------------
def ervenyes_pipeline(szoveg: str) -> bool:
    """Durva szintaktikai ellenőrzés: valódi declarative pipeline-e."""
    if not szoveg or "pipeline" not in szoveg:
        return False
    if "stages" not in szoveg or "steps" not in szoveg:
        return False
    # Kiegyensúlyozott kapcsos zárójelek (idézőjelen kívül).
    melyseg = 0
    for ch in szoveg:
        if ch == "{":
            melyseg += 1
        elif ch == "}":
            melyseg -= 1
            if melyseg < 0:
                return False
    return melyseg == 0


def javit_jenkinsfile(
    agens_szoveg: Optional[str], files: Dict[str, str]
) -> Tuple[str, List[str], str]:
    """Az ágens Jenkinsfile-jának javítása.

    Visszatérés: `(vegleges_tartalom, valtozasok, forras)`, ahol a `forras`
    értéke `"agens-javitott"` vagy `"generalt"`.
    """
    info = projekt_info(files)
    valtozasok: List[str] = []

    if not agens_szoveg or not ervenyes_pipeline(agens_szoveg):
        return generalt_jenkinsfile(info), ["Az ágens Jenkinsfile-ja hiányzott vagy érvénytelen"], "generalt"

    # Minden `sh` parancs javítása a saját dir() kontextusában.
    darabok: List[str] = []
    utolso_veg = 0
    for talalat in SH_MINTA.finditer(agens_szoveg):
        kontextus = _dir_kontextus(agens_szoveg, talalat.start())
        javitott = _javit_parancs(talalat.group("parancs"), kontextus, info, valtozasok)
        darabok.append(agens_szoveg[utolso_veg : talalat.start()])
        darabok.append(f"{talalat.group('elo')}{talalat.group('idezo')}{javitott}{talalat.group('idezo')}")
        utolso_veg = talalat.end()
    darabok.append(agens_szoveg[utolso_veg:])
    eredmeny = "".join(darabok)

    # Sanity + health check beszúrása a `stages {` blokk elejére / végére.
    if "Sanity Check" not in eredmeny:
        eredmeny = re.sub(r"(\bstages\s*\{)", r"\1" + _noop_orszem(), eredmeny, count=1)
        valtozasok.append("Sanity Check stage beszúrva (a néma, no-op zöld build ellen)")

    healthcheck = _healthcheck_stage(info)
    if healthcheck and "Health Check" not in eredmeny:
        # A `stages` blokk lezáró kapcsos zárójele elé illesztjük.
        pozicio = _stages_blokk_vege(eredmeny)
        if pozicio is not None:
            eredmeny = eredmeny[:pozicio] + healthcheck + "\n" + eredmeny[pozicio:]
            valtozasok.append("Health Check stage beszúrva (a néma deploy-hiba kimutatására)")

    if not ervenyes_pipeline(eredmeny):
        return generalt_jenkinsfile(info), valtozasok + ["A javítás után sem lett érvényes – generáltra váltva"], "generalt"

    fejlec = "// Az ágens által generált pipeline, automatikusan javítva.\n"
    if valtozasok:
        fejlec += "".join(f"//   - {v}\n" for v in dict.fromkeys(valtozasok))
    return fejlec + eredmeny, valtozasok, "agens-javitott"


def _stages_blokk_vege(szoveg: str) -> Optional[int]:
    """Megkeresi a `stages { ... }` blokk lezáró zárójelének pozícióját."""
    talalat = re.search(r"\bstages\s*\{", szoveg)
    if not talalat:
        return None
    melyseg = 0
    for i in range(talalat.end() - 1, len(szoveg)):
        if szoveg[i] == "{":
            melyseg += 1
        elif szoveg[i] == "}":
            melyseg -= 1
            if melyseg == 0:
                return i
    return None
