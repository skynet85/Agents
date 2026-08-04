# sprint_engine.py
"""A sprint állapotgépének Streamlit-független logikája.

Az `app.py` korábban egyetlen ~180 soros beágyazott függvényben keverte a
megjelenítést, az állapotátmeneteket és a védőkorlát-ellenőrzést. Ezt a részt
ide emeltük ki, hogy tesztelhető és átlátható legyen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import config

# Az IT ágenstől elvárt konfigurációs fájlok.
KOTELEZO_FE_FAJL = "package.json"
KOTELEZO_BE_FAJL = "pom.xml"

# Fájlnév-komment felismerése a kódblokk elején (// File:, -- Fájl:, # filepath: ...)
FAJLNEV_KOMMENT = re.compile(
    r"(?://|/\*|<!--|--|#).*?(?:File|Fájl|filepath|name)\s*.*?:", re.IGNORECASE
)

# Ennél rövidebb blokkoknál nem várunk el fájlnév-kommentet (pl. egysoros parancs).
MIN_BLOKK_HOSSZ = 20


@dataclass
class SprintAllapot:
    """A sprint szerializálható állapota (session_state-ben tárolva)."""

    kor: int = 0
    agens_idx: int = 0
    elozo_kimenet: str = ""
    valaszok: Dict[str, str] = field(default_factory=dict)
    # Ágens-azonosító -> hányadszor próbálkozik újra a védőkorlát miatt.
    ujraprobalkozasok: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, adat: Optional[Dict[str, Any]]) -> "SprintAllapot":
        adat = adat or {}
        return cls(
            kor=int(adat.get("kor", 0) or 0),
            agens_idx=int(adat.get("agens_idx", 0) or 0),
            elozo_kimenet=adat.get("elozo_kimenet", "") or "",
            valaszok=dict(adat.get("valaszok", {}) or {}),
            ujraprobalkozasok=dict(adat.get("ujraprobalkozasok", {}) or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kor": self.kor,
            "agens_idx": self.agens_idx,
            "elozo_kimenet": self.elozo_kimenet,
            "valaszok": self.valaszok,
            "ujraprobalkozasok": self.ujraprobalkozasok,
        }

    def kovetkezo_kor(self, elozo_kimenet: str) -> None:
        self.kor += 1
        self.agens_idx = 0
        self.valaszok = {}
        self.ujraprobalkozasok = {}
        self.elozo_kimenet = elozo_kimenet


def validate_it_valasz(kodblokkok: List[str]) -> List[str]:
    """Ellenőrzi az IT ágens kimenetét; a talált hibák listáját adja vissza.

    Üres lista = a válasz megfelel a védőkorlátnak.
    """
    hibak: List[str] = []

    if not kodblokkok:
        return ["Nincsenek kódblokkok"]

    blokkok_lower = [b.lower() for b in kodblokkok]

    has_package = any(KOTELEZO_FE_FAJL in b or '"dependencies"' in b for b in blokkok_lower)
    has_pom = any(KOTELEZO_BE_FAJL in b or "<project" in b for b in blokkok_lower)

    if not has_package:
        hibak.append(f"Hiányzik a {KOTELEZO_FE_FAJL}")
    if not has_pom:
        hibak.append(f"Hiányzik a {KOTELEZO_BE_FAJL}")

    hianyzo_nevek = [
        b for b in kodblokkok
        if len(b.strip()) > MIN_BLOKK_HOSSZ
        and not any(FAJLNEV_KOMMENT.search(sor) for sor in b.split("\n")[:3])
    ]
    if hianyzo_nevek:
        hibak.append(
            f"{len(hianyzo_nevek)} kódblokk elejéről hiányzik a fájlnév-komment "
            "(pl. // File: ...)"
        )

    return hibak


def validate_it_projekt(files: Dict[str, str]) -> List[str]:
    """A projekt FÁJLFÁJÁT ellenőrzi, nem az egyetlen ágensválaszt.

    Így az IT ágensnek nem kell minden körben újragenerálnia a teljes kódbázist
    ahhoz, hogy átmenjen a védőkorláton – elég, ha a projekt egésze rendben van.
    """
    hibak: List[str] = []
    if not files:
        return ["A projekt üres – nincs egyetlen legenerált fájl sem"]
    if f"frontend/{KOTELEZO_FE_FAJL}" not in files:
        hibak.append(f"Hiányzik a frontend/{KOTELEZO_FE_FAJL}")
    if f"backend/{KOTELEZO_BE_FAJL}" not in files:
        hibak.append(f"Hiányzik a backend/{KOTELEZO_BE_FAJL}")
    return hibak


def javito_prompt(
    eredeti_valasz: str,
    hibak: List[str],
    hatralevo_probalkozas: int,
    forditoi_kimenet: str = "",
) -> str:
    """Az ágensnek visszaküldött, keményebb újragenerálási utasítás.

    Ha van valódi fordítói kimenet (`forditoi_kimenet`), az élvez elsőbbséget:
    ez a gépi igazságforrás, nem egy másik LLM véleménye.
    """
    fej = f"{eredeti_valasz}\n\n[RENDSZER HIBA]: A MUNKÁD NEM FELELT MEG!\n"

    if forditoi_kimenet:
        return (
            f"{fej}{forditoi_kimenet}\n\n"
            "UTASÍTÁS: javítsd ki PONTOSAN ezeket a fordítási hibákat! "
            "Csak azokat a fájlokat írd ki újra kódblokkban, amelyeket ténylegesen "
            "módosítanod kell — a többit hagyd békén. Minden kódblokk első sora "
            "kommentben a fájl teljes útvonala legyen "
            "(pl. `// File: backend/src/main/java/com/app/MyClass.java`). "
            "Ha egy fájl feleslegessé vált, írd külön sorba: DELETE: <útvonal>\n"
            f"(Hátralévő próbálkozás: {hatralevo_probalkozas})"
        )

    return (
        f"{fej}Okok: {', '.join(hibak)}!\n"
        "Szigorúan minden kódblokk legelső sorába írd be kommentként a fájl nevét "
        "(pl. `// File: backend/src/main/java/com/app/MyClass.java`)! "
        "Java esetén a fájlnévnek kötelezően egyeznie kell a public class nevével, "
        "és a `package` deklarációnak a könyvtárral! Ha használsz Lombokot "
        "(@Data, @Slf4j), ne felejtsd el beletenni a pom.xml-be! Csináld újra!\n"
        f"(Hátralévő próbálkozás: {hatralevo_probalkozas})"
    )


def lezarast_kert(valasz: str) -> bool:
    """Igaz, ha a válaszban szerepel a sprintet lezáró kulcsszó."""
    return config.LEZARAS_KULCSSZO in (valasz or "")


def kell_ujraprobalni(allapot: SprintAllapot, agens_id: str, hibak: List[str]) -> bool:
    """Eldönti, hogy a védőkorlát visszadobja-e az ágenst.

    Ha a próbálkozások száma elérte a limitet, `False`-szal tér vissza – ez
    akadályozza meg a korábbi verzió végtelen IT-ciklusát.
    """
    if not hibak:
        return False
    eddigi = allapot.ujraprobalkozasok.get(agens_id, 0)
    return eddigi < config.MAX_AGENS_UJRAPROBALKOZAS
