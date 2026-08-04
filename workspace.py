# workspace.py
"""Fájlfa-alapú projektállapot (VirtualWorkspace).

MIÉRT KELL EZ
-------------
Korábban a „projekt” nem létezett önálló entitásként: a repó tartalma csak a
GitHub-push pillanatában állt össze 48 chat-üzenetből. Ennek két mért
következménye volt egy valós futásban:

1. **Ütköző Spring bean.** Az 1. iteráció a `com.malom.engine.MatchEngine`,
   a 3. iteráció a `com.malom.service.MatchEngine` osztályt hozta létre.
   Mindkettő `@Service`, mindkettőből `matchEngine` bean-név származik →
   `ConflictingBeanDefinitionException` → a Spring context el sem indul.
   A chat-log alapú gyűjtés mindkettőt megtartotta, mert *különböző* útvonalak.

2. **117 duplikált kódblokk.** Az IT ágens minden körben újragenerálta a teljes
   kódbázist, mert nem tudta, mit írt már meg.

A `VirtualWorkspace` ezt úgy oldja meg, hogy a projekt egy élő `útvonal → tartalom`
leképezés, amit minden ágensválasz **patchel**. Az ágens promptjába bekerül az
aktuális fájlfa, így nem nulláról dolgozik, és a névütközések azonnal feloldódnak.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

import code_analysis
import github_integration as gi
import project_doctor
import scaffold

# Az ágens explicit fájlművelet-direktívái (kódblokkon kívül).
DELETE_MINTA = re.compile(r"^\s*(?://|#|--)?\s*DELETE\s*:\s*([\w./-]+)\s*$", re.MULTILINE | re.IGNORECASE)
MOVE_MINTA = re.compile(
    r"^\s*(?://|#|--)?\s*MOVE\s*:\s*([\w./-]+)\s*(?:->|=>)\s*([\w./-]+)\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# Spring bean-ütközést okozó annotációk.
SPRING_BEAN_ANNOTACIOK = ("@Service", "@Component", "@Repository", "@RestController", "@Controller")


@dataclass
class Valtozas:
    """Egyetlen fájlművelet naplóbejegyzése."""

    tipus: str  # 'uj' | 'modositott' | 'valtozatlan' | 'torolt' | 'lecserelt'
    utvonal: str
    regi_utvonal: Optional[str] = None
    indok: str = ""

    def __str__(self) -> str:
        jel = {
            "uj": "＋",
            "modositott": "~",
            "valtozatlan": "=",
            "torolt": "－",
            "lecserelt": "→",
            "elutasitott": "⛔",
        }.get(self.tipus, "?")
        if self.regi_utvonal:
            return f"{jel} {self.regi_utvonal} → {self.utvonal}" + (f"  ({self.indok})" if self.indok else "")
        return f"{jel} {self.utvonal}" + (f"  ({self.indok})" if self.indok else "")


@dataclass
class VirtualWorkspace:
    """A projekt aktuális fájlfája."""

    files: Dict[str, str] = field(default_factory=dict)
    naplo: List[Dict[str, Any]] = field(default_factory=list)
    # Az ágens által kért, allowlistán átment extra npm csomagok.
    extra_deps: Dict[str, str] = field(default_factory=dict)

    # -- váz ---------------------------------------------------------------
    @classmethod
    def vazzal(cls) -> "VirtualWorkspace":
        """Új munkaterület a rögzített, build-képes vázzal feltöltve."""
        ws = cls()
        ws.files.update(scaffold.vaz_fajlok())
        ws.files.update(scaffold.alap_alkalmazas())
        return ws

    def vaz_frissites(self) -> None:
        """Újragenerálja a védett váz-fájlokat (pl. új függőség után)."""
        self.files.update(scaffold.vaz_fajlok(self.extra_deps))

    # -- alapműveletek ----------------------------------------------------
    def __len__(self) -> int:
        return len(self.files)

    def __contains__(self, utvonal: str) -> bool:
        return utvonal in self.files

    def get(self, utvonal: str, alapertelmezett: str = "") -> str:
        return self.files.get(utvonal, alapertelmezett)

    def ir(self, utvonal: str, tartalom: str) -> Valtozas:
        """Egy fájl írása (patch-szemantika)."""
        if utvonal not in self.files:
            valtozas = Valtozas("uj", utvonal)
        elif self.files[utvonal].strip() == tartalom.strip():
            return Valtozas("valtozatlan", utvonal)
        else:
            valtozas = Valtozas("modositott", utvonal)
        self.files[utvonal] = tartalom
        return valtozas

    def torol(self, utvonal: str, indok: str = "") -> Optional[Valtozas]:
        if utvonal in self.files:
            del self.files[utvonal]
            return Valtozas("torolt", utvonal, indok=indok)
        return None

    def athelyez(self, regi: str, uj: str) -> Optional[Valtozas]:
        if regi not in self.files:
            return None
        self.files[uj] = self.files.pop(regi)
        return Valtozas("lecserelt", uj, regi_utvonal=regi, indok="MOVE direktíva")

    # -- névütközés-feloldás ---------------------------------------------
    @staticmethod
    def _java_osztalynev(utvonal: str) -> Optional[str]:
        return utvonal.rsplit("/", 1)[-1][:-5] if utvonal.endswith(".java") else None

    @staticmethod
    def _komponens_nev(utvonal: str) -> Optional[str]:
        nev = utvonal.rsplit("/", 1)[-1]
        return nev.rsplit(".", 1)[0] if nev.endswith((".jsx", ".tsx", ".ts", ".js")) else None

    def _utkozo_utvonalak(self, uj_utvonal: str, uj_tartalom: str) -> List[Tuple[str, str]]:
        """Megkeresi a más helyen lévő, azonos nevű entitásokat.

        Ez akadályozza meg, hogy egy későbbi iteráció `service/MatchEngine`-je
        MELLETT bent maradjon a korábbi `engine/MatchEngine` – amitől a Spring
        context indulásakor bean-névütközés keletkezne.
        """
        talalatok: List[Tuple[str, str]] = []

        osztaly = self._java_osztalynev(uj_utvonal)
        if osztaly:
            uj_bean = any(a in uj_tartalom for a in SPRING_BEAN_ANNOTACIOK)
            for utvonal, tartalom in self.files.items():
                if utvonal == uj_utvonal or self._java_osztalynev(utvonal) != osztaly:
                    continue
                regi_bean = any(a in tartalom for a in SPRING_BEAN_ANNOTACIOK)
                if uj_bean and regi_bean:
                    talalatok.append((utvonal, f"ütköző Spring bean-név: {osztaly}"))
                else:
                    talalatok.append((utvonal, f"azonos Java osztálynév: {osztaly}"))
            return talalatok

        komponens = self._komponens_nev(uj_utvonal)
        if komponens and komponens.lower() not in ("index", "main", "app"):
            for utvonal in self.files:
                if utvonal == uj_utvonal:
                    continue
                if self._komponens_nev(utvonal) == komponens:
                    talalatok.append((utvonal, f"azonos modulnév: {komponens}"))
        return talalatok

    # -- ágensválasz alkalmazása -----------------------------------------
    def alkalmaz(self, uzenet: Dict[str, Any], szerepek: Iterable[str]) -> List[Valtozas]:
        """Egy ágensválasz kódblokkjainak beolvasztása a fájlfába.

        A rögzített váz fájljait NEM engedi felülírni: azokat a rendszer
        garantálja build-képesnek, az ágens hallucinációja nem ronthatja el.
        """
        szoveg = str(uzenet.get("szoveg", ""))
        valtozasok: List[Valtozas] = []

        # 1. Függőség-kérések (allowlist ellen ellenőrizve)
        engedett, elutasitott = scaffold.kert_fuggosegek(szoveg)
        for nev, verzio in engedett.items():
            if nev not in self.extra_deps:
                self.extra_deps[nev] = verzio
                self.vaz_frissites()
                valtozasok.append(
                    Valtozas("uj", "frontend/package.json", indok=f"új függőség: {nev}@{verzio}")
                )
        for nev in elutasitott:
            valtozasok.append(
                Valtozas("elutasitott", nev, indok="nincs az engedélyezett csomagok listáján")
            )

        # 2. Explicit direktívák
        for utvonal in DELETE_MINTA.findall(szoveg):
            tiszta = gi.clean_filename(utvonal)
            if scaffold.vedett(tiszta):
                valtozasok.append(Valtozas("elutasitott", tiszta, indok="védett váz-fájl"))
                continue
            v = self.torol(tiszta, indok="DELETE direktíva")
            if v:
                valtozasok.append(v)
        for regi, uj in MOVE_MINTA.findall(szoveg):
            r, u = gi.clean_filename(regi), gi.clean_filename(uj)
            if scaffold.vedett(r) or scaffold.vedett(u):
                valtozasok.append(Valtozas("elutasitott", u, indok="védett váz-fájl"))
                continue
            v = self.athelyez(r, u)
            if v:
                valtozasok.append(v)

        # 3. Kódblokkok
        for i, (nyelv, blokk) in enumerate(gi.extract_blocks_with_lang([uzenet], list(szerepek))):
            tartalom = gi.clean_block_content(blokk)
            if not tartalom:
                continue

            fname = gi.clean_filename(gi.get_filename_from_block(blokk))
            tipus = gi._besorol(fname or gi._nyelv_alapjan_nev(nyelv), tartalom.lower())
            if not tipus:
                continue

            utvonal = gi._vegleges_utvonal(fname, tartalom, nyelv, tipus, i)
            if not utvonal:
                # Fájlnév-komment és felismerhető export nélküli töredék –
                # ezekből lettek korábban a `Component_NN.jsx` szemétfájlok.
                continue

            # A Spring belépési pont a vázé: egy második @SpringBootApplication
            # osztály `ConflictingBeanDefinition`-t / kétértelmű indulást okozna.
            if "@SpringBootApplication" in tartalom and any(
                "@SpringBootApplication" in self.files.get(p, "")
                for p in self.files
                if p != utvonal and p.endswith(".java")
            ):
                valtozasok.append(
                    Valtozas(
                        "elutasitott",
                        utvonal,
                        indok="a Spring belépési pontot a váz adja (com.app.Application)",
                    )
                )
                continue

            # A váz zárolt: a build-konfigurációt nem az LLM írja.
            if scaffold.vedett(utvonal):
                valtozasok.append(
                    Valtozas(
                        "elutasitott",
                        utvonal,
                        indok="védett váz-fájl – a build-konfigurációt a rendszer adja",
                    )
                )
                continue

            # CSS: az `@apply` a Tailwind legtörékenyebb pontja (lásd #24 build).
            if utvonal.endswith((".css", ".scss")):
                tartalom, eltavolitva = scaffold.tisztit_css(tartalom)
                if eltavolitva:
                    valtozasok.append(
                        Valtozas(
                            "modositott",
                            utvonal,
                            indok=f"{eltavolitva} db `@apply` sor eltávolítva (build-védelem)",
                        )
                    )
                if not tartalom.strip():
                    continue

            # Régi, azonos nevű entitás eltávolítása (bean-ütközés megelőzése).
            for regi_utvonal, indok in self._utkozo_utvonalak(utvonal, tartalom):
                del self.files[regi_utvonal]
                valtozasok.append(
                    Valtozas("lecserelt", utvonal, regi_utvonal=regi_utvonal, indok=indok)
                )

            valtozasok.append(self.ir(utvonal, tartalom))

        erdemi = [v for v in valtozasok if v.tipus != "valtozatlan"]
        if erdemi:
            self.naplo.append(
                {
                    "agens": uzenet.get("szerep_nev", "?"),
                    "valtozasok": [v.__dict__ for v in erdemi],
                }
            )
        return valtozasok

    # -- prompt-reprezentáció --------------------------------------------
    def fajlfa(self, max_sor: int = 60) -> str:
        """Az aktuális fájlfa tömör szövege az ágens promptjához."""
        if not self.files:
            return "(A projekt még üres – nincs egyetlen fájl sem.)"

        sorok = [f"{ut} ({len(self.files[ut])} bájt)" for ut in sorted(self.files)]
        if len(sorok) > max_sor:
            marad = len(sorok) - max_sor
            sorok = sorok[:max_sor] + [f"... és további {marad} fájl"]
        return "\n".join(sorok)

    def osszefoglalo(self) -> Dict[str, int]:
        return {
            "osszes": len(self.files),
            "frontend": sum(1 for p in self.files if p.startswith("frontend/")),
            "backend": sum(1 for p in self.files if p.startswith("backend/")),
            "database": sum(1 for p in self.files if p.startswith("database/")),
        }

    # -- perzisztencia ----------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {"files": self.files, "naplo": self.naplo, "extra_deps": self.extra_deps}

    @classmethod
    def from_dict(cls, adat: Optional[Dict[str, Any]]) -> "VirtualWorkspace":
        adat = adat or {}
        files = adat.get("files") or {}
        return cls(
            files={str(k): str(v) for k, v in files.items() if isinstance(k, str)},
            naplo=list(adat.get("naplo") or []),
            extra_deps=dict(adat.get("extra_deps") or {}),
        )


# ---------------------------------------------------------------------------
# Konzisztencia-ellenőrzés (a fordítás előtti olcsó szűrő)
# ---------------------------------------------------------------------------
def ellenoriz(ws: VirtualWorkspace) -> List[str]:
    """Olcsó, statikus konzisztencia-ellenőrzések a fájlfán.

    Nem helyettesíti a fordítást, de a leggyakoribb, biztosan build-törő
    hibákat még az iteráción belül kiszűri.
    """
    hibak: List[str] = []
    files = ws.files

    # 1. Java: package deklaráció vs. könyvtár
    for utvonal, tartalom in files.items():
        if not utvonal.endswith(".java"):
            continue
        pkg = code_analysis.JAVA_PACKAGE.search(tartalom)
        if pkg:
            vart = f"backend/src/main/java/{pkg.group(1).replace('.', '/')}/"
            if not utvonal.startswith(vart):
                hibak.append(f"{utvonal}: a package deklaráció ({pkg.group(1)}) nem egyezik a könyvtárral")

    # 2. Legfeljebb egy Spring belépési pont
    belepesi = [p for p, c in files.items() if "@SpringBootApplication" in c]
    if len(belepesi) > 1:
        hibak.append(f"Több @SpringBootApplication osztály: {', '.join(sorted(belepesi))}")

    # 3. Ütköző bean-nevek
    beanek: Dict[str, List[str]] = {}
    for utvonal, tartalom in files.items():
        if utvonal.endswith(".java") and any(a in tartalom for a in SPRING_BEAN_ANNOTACIOK):
            beanek.setdefault(utvonal.rsplit("/", 1)[-1][:-5], []).append(utvonal)
    for nev, helyek in beanek.items():
        if len(helyek) > 1:
            hibak.append(f"Ütköző Spring bean-név ({nev}): {', '.join(sorted(helyek))}")

    # 4. Feloldatlan relatív importok a frontendben
    import os

    for utvonal, tartalom in files.items():
        if not utvonal.startswith("frontend/src"):
            continue
        for imp in re.findall(r"""from\s+['"](\.[^'"]+)['"]""", tartalom):
            cel = os.path.normpath(os.path.join(os.path.dirname(utvonal), imp)).replace("\\", "/")
            if not any(f == cel or f.startswith(cel + ".") or f.startswith(cel + "/index.") for f in files):
                hibak.append(f"{utvonal}: feloldatlan import → {imp}")

    # 5. Build-leírók megléte
    if any(p.startswith("frontend/") for p in files) and "frontend/package.json" not in files:
        hibak.append("Van frontend kód, de hiányzik a frontend/package.json")
    if any(p.startswith("backend/") for p in files) and "backend/pom.xml" not in files:
        hibak.append("Van backend kód, de hiányzik a backend/pom.xml")

    # 6. Build-képességi blokkolók (nem létező függőség-verzió, lógó tsconfig
    #    hivatkozás stb.) – ezek a Jenkins buildet az első másodpercben megölnék.
    hibak.extend(project_doctor.blokkolo_hibak(files))

    # 6b. `Map.of(...)` null értékkel — a fordító ÁTENGEDI, futáskor viszont
    #     NullPointerExceptiont dob. Zöld build, majd 500-as hiba az első híváskor.
    for utvonal, tartalom in files.items():
        if not utvonal.endswith(".java") or "Map.of(" not in tartalom:
            continue
        for talalat in re.finditer(r"Map\.of\((.*?)\)\s*;", tartalom, re.DOTALL):
            if re.search(r"(?<![\w.])null(?![\w])", talalat.group(1)):
                hibak.append(
                    f"{utvonal}: `Map.of(...)` null értékkel — futáskor "
                    "NullPointerException (használj `HashMap`-et vagy hagyd ki a mezőt)"
                )
                break

    # 7. A váz placeholder-oldala még mindig ott van?
    #    Ez a legalattomosabb kimenet: a build ZÖLD, a health check átmegy, a
    #    böngészőben mégis a „A fejlesztés folyamatban" felirat fogadja a felhasználót.
    if scaffold.placeholder_maradt(files):
        sajat_komponensek = [
            p
            for p in files
            if p.startswith("frontend/src/") and p.endswith((".tsx", ".jsx"))
            and not p.startswith("frontend/src/App.")
            and p != "frontend/src/main.tsx"
        ]
        reszlet = (
            f" Már van {len(sajat_komponensek)} saját komponens "
            f"({', '.join(sorted(p.rsplit('/', 1)[-1] for p in sajat_komponensek)[:4])}) – "
            "ezeket az App.tsx-ből kell renderelni."
            if sajat_komponensek
            else ""
        )
        hibak.append(
            "A frontend/src/App.tsx MÉG A VÁZ PLACEHOLDERE – a felhasználó a valódi "
            "alkalmazás helyett a „A fejlesztés folyamatban” oldalt látná." + reszlet
        )

    return hibak


def workspace_from_messages(uzenetek: List[Dict[str, Any]], szerepek: Iterable[str]) -> VirtualWorkspace:
    """Visszamenőleges feltöltés: korábbi futás chat-logjából épít fájlfát.

    A rögzített vázból indul, mert a régi logokban lévő build-konfigurációk
    (kitalált verziók, lógó tsconfig-hivatkozás) épp azok, amiket zároltunk —
    így egy korábbi futás betöltése is build-képes projektet ad.
    """
    ws = VirtualWorkspace.vazzal()
    szerepek = list(szerepek)
    for uzenet in uzenetek or []:
        if uzenet.get("szerep") == "assistant":
            ws.alkalmaz(uzenet, szerepek)
    return ws
