# 🗺️ Fejlesztési útiterv — az „igazi fejlesztőcsapat” felé

Ez a dokumentum nem általános jótanácsokat sorol, hanem a `szimulacio_memoria.json`
**15 valós futásából mért** hiányosságokra ad választ.

---

## 1. Diagnózis: mit mutatnak az adatok?

| Mérés | Eredmény | Következtetés |
|---|---|---|
| Frontend → backend API-hívások | **0 db** | A backend 3 endpointot expózol (`/api/game/reset`, `/{id}/move`, `/{id}/state`), a frontend **egyiket sem hívja** |
| `@Service class MatchEngine` | **2 db** (`com.malom.service` + `com.malom.engine`) | Azonos bean-név → `ConflictingBeanDefinitionException` → a Spring context **el sem indul** |
| QA visszadobás | 38-ból **34** (89%) | A QA mindig elutasít – ez rituálé, nem mérés |
| QA által írt futtatható teszt | 15 futásból **2**-ben volt teszt-szerű tartalom, a végtermékben **0 db teszt fájl** | A „tesztelés” szövegesen zajlik, ellenőrzés nélkül |
| Végrehajtott build a szimuláció alatt | **0** | Semmit nem fordít le, nem futtat le senki |

**Az összes tünet egyetlen okra vezethető vissza: a rendszerben nincs igazságforrás
(ground truth).** Minden ágenst egy másik LLM *véleménye* minősít, soha nem a fordító,
a teszt vagy a linter. Ezért lehet, hogy a „malom játék” frontendje és backendje
külön-külön hihetően néz ki, miközben soha nem beszélnek egymással – és ezt senki
nem veszi észre.

Egy valós csapatban a visszajelzés a gépből jön: lefordul, lefut, zöld a teszt.
Itt viszont a nyelvi modell saját magát értékeli.

---

## 2. P0 — Végrehajtási visszacsatolás (ez az egész lényege)

**Amit ma csinál:** az IT ágens válaszát regex nézi meg (van-e `package.json` string).
**Amit csinálnia kellene:** ténylegesen lefordítani, és a valódi fordítói hibát
visszaadni promptként.

```
IT válasz → VirtualWorkspace → Docker sandbox
   frontend:  npm install && npx tsc --noEmit && npm run build
   backend:   mvn -q -B compile
   ↓
hiba? → a NYERS fordítói kimenet megy vissza az IT ágensnek javításra
zöld?  → mehet a QA-hoz
```

- Ez teljesen kiváltja a jelenlegi regex-védőkorlátot: „van-e pom.xml?” helyett
  „lefordul-e?”.
- A `MAX_AGENS_UJRAPROBALKOZAS` már megvan, csak valós jelre kell kötni.
- Becsült hatás: **ez az egyetlen változtatás dönti el, hogy a kimenet vállalható-e**.

**Kockázat:** lassabb sprint (egy `npm install` 30–60 s). Enyhítés: node_modules és
`~/.m2` cache mountolása, valamint csak a változott oldal újrafordítása.

---

## 3. P0 — Projektállapot fájlfaként, ne chat-logként

**A jelenlegi hiba:** a projekt csak a push pillanatában áll össze 48 chat-üzenetből.
Ezért maradhatott bent egyszerre az 1. iteráció `engine/MatchEngine`-je és a 3. iteráció
`service/MatchEngine`-je → ütköző bean.

**Megoldás:** `VirtualWorkspace` (path → tartalom), amit minden IT-válasz **patchel**.

- Az IT ágens promptjába bekerül az **aktuális fájlfa** (útvonalak + méret), így tudja,
  mit írt már meg – nem generálja újra nulláról.
- Explicit `// DELETE: <path>` és `// MOVE: <régi> -> <új>` direktívák.
- A GitHub push innen olvas, nem a chat-előzményből.

Mellékhaszon: drasztikus token-megtakarítás, mert az IT nem írja újra a teljes kódbázist
minden körben (a 194807-es futásban 117 blokk volt duplikátum).

---

## 4. P1 — A QA kapjon igazi mérőeszközt

A QA ágens ma prózában vitatkozik. Adjunk neki fegyvert:

1. **Futtatható teszteket írjon** (JUnit 5 a backendre, Vitest + Testing Library a frontendre).
2. A teszteket a sandbox lefuttatja; a QA verdiktje **a teszteredmény**, nem a véleménye.
3. Lefedettségi kapu: `jacoco` / `vitest --coverage`, minimum küszöbbel.
4. A jelenlegi „mindig dobd vissza” szabályt le kell venni – ez tanította meg a QA-t
   arra, hogy 89%-ban elutasítson, függetlenül a tartalomtól.

---

## 5. P1 — Integrációs kapu (a 0 API-hívás ellen)

A frontend és a backend külön univerzumban él. Kell egy lépés, ami ezt kikényszeríti:

- **Szerződés-elsőség:** a BA ne prózát írjon, hanem **OpenAPI 3 specifikációt**.
  A FE és a BE is ebből dolgozik.
- **Kontraktus-teszt:** a sandbox ellenőrzi, hogy minden spec-beli endpointot
  implementál-e a backend, és hogy a frontend csak létező endpointot hív.
- **Smoke teszt:** felhúzza mindkét oldalt, és lefuttat egy valódi user-flow-t
  (Playwright: „új játék → lépés → állapot frissül”).

Ez az a lépés, ami után az eredmény tényleg *működő alkalmazás*, nem két féltermék.

---

## 6. P1 — Git-natív munkafolyamat (a „vállalhatóság” formai fele)

Ma minden egyetlen `🤖 Auto-commit` a default branchre. Egy valós csapatnál:

- **Branch sprintenként:** `sprint/20260626-malom`.
- **Commit ágensenként**, beszédes üzenettel (`feat(be): match engine`, `test(qa): …`),
  a szerző az ágens neve → a `git log` olvasható sprint-napló lesz.
- **Pull Request** merge helyett közvetlen push helyett, a PR leírásában a
  projekt memóriával és a telemetriával.
- A generált repóba kerüljön `.gitignore`, `LICENSE`, `CONTRIBUTING.md`.

---

## 7. P2 — Ne az LLM írja a boilerplate-et

A modell tokenek százait pazarolja `vite.config.ts` és `pom.xml` hallucinálására –
és pont ezekben hibázik (nem volt `start` script, ütköző pluginek).

**Váz generálása determinisztikusan**, a Spring Initializr / `npm create vite`
mintájára beépített sablonokból; az LLM **csak az üzleti logikát** írja.
Ez egyszerre gyorsabb, olcsóbb és megbízhatóbb.

---

## 8. P2 — Modell-útválasztás és költség

Ma minden ágens ugyanazt a modellt kapja. Racionálisabb:

| Ágens | Igény | Javaslat |
|---|---|---|
| PO, SM | rövid, sablonos szöveg | kis, gyors modell |
| BA, QA | strukturált gondolkodás | közepes |
| IT, DO | kódgenerálás | a legerősebb elérhető |

A telemetria már méri az ágensenkénti tokent – ebből kiszámolható a valós megtakarítás.

---

## 9. P2 — Megfigyelhetőség és értékelés

- **Sprint-diff nézet:** mi változott a fájlfában körönként (a chat-log helyett).
- **Regressziós benchmark:** 5–10 rögzített feladat, amin a rendszer minden
  prompt-változtatás után végigfut; metrika a *lefordul / teszt zöld / smoke zöld* arány.
  Enélkül a prompt-hangolás vakrepülés.
- A jelenlegi 1–5 csillagos kézi értékelés mellé automatikus pontszám.

---

## 10. Javasolt sorrend

| # | Lépés | Ráfordítás | Hatás |
|---|---|---|---|
| 1 | VirtualWorkspace (fájlfa-állapot) | közepes | 🔥🔥🔥 |
| 2 | Docker sandbox + fordítási visszacsatolás | nagy | 🔥🔥🔥 |
| 3 | QA → futtatható tesztek | közepes | 🔥🔥 |
| 4 | OpenAPI szerződés + kontraktus-teszt | közepes | 🔥🔥 |
| 5 | Git branch/PR munkafolyamat | kicsi | 🔥 |
| 6 | Determinisztikus projektváz | kicsi | 🔥🔥 |
| 7 | Modell-útválasztás | kicsi | 🔥 |
| 8 | Regressziós benchmark | közepes | 🔥🔥 |

**Az 1. és 2. lépés együtt adja a minőségi ugrást** – a többi erre épül.
Amíg nincs végrehajtás, a rendszer egy nagyon meggyőző szövegszimuláció marad.
