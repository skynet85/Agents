# tests/test_imports.py
"""Smoke teszt: minden modul importálható és a hivatkozott nevek léteznek.

A nehéz külső csomagokat (streamlit, langchain, opentelemetry, github)
minimál-stubokkal helyettesítjük, így a teszt telepített LLM-stack nélkül is
kiszűri az elgépelt import- és függvényneveket.

Futtatás:  python3 tests/test_imports.py
"""
from __future__ import annotations

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

HIBAK: list[str] = []


def check(feltetel: bool, uzenet: str) -> None:
    print(f"  {'✓' if feltetel else '✗'} {uzenet}")
    if not feltetel:
        HIBAK.append(uzenet)


class _Barmi:
    """Mindent elnyelő stub: hívható, indexelhető, context manager."""

    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        return _Barmi()

    def __getattr__(self, _n):
        return _Barmi()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter([_Barmi(), _Barmi()])

    def __getitem__(self, _i):
        return _Barmi()


def _stub_modul(nev: str, **attrs) -> types.ModuleType:
    modul = types.ModuleType(nev)
    modul.__getattr__ = lambda _n: _Barmi()  # type: ignore[attr-defined]
    for k, v in attrs.items():
        setattr(modul, k, v)
    sys.modules[nev] = modul
    return modul


def telepit_stubok() -> None:
    st = _stub_modul("streamlit")
    st.session_state = {}  # type: ignore[attr-defined]
    _stub_modul("streamlit.components")
    _stub_modul("streamlit.components.v1")
    st.components = sys.modules["streamlit.components"]  # type: ignore[attr-defined]

    _stub_modul("langchain_core")
    _stub_modul("langchain_core.prompts", PromptTemplate=_Barmi)
    _stub_modul("langchain_openai", ChatOpenAI=_Barmi)

    _stub_modul("opentelemetry", trace=_Barmi())
    _stub_modul("opentelemetry.sdk")
    _stub_modul("opentelemetry.sdk.trace", TracerProvider=_Barmi)
    _stub_modul(
        "opentelemetry.sdk.trace.export",
        BatchSpanProcessor=_Barmi,
        ConsoleSpanExporter=_Barmi,
    )

    class _GithubException(Exception):
        def __init__(self, status=500, data=None):
            super().__init__(str(status))
            self.status = status

    _stub_modul("github", Github=_Barmi, GithubException=_GithubException, InputGitTreeElement=_Barmi)


def main() -> int:
    print("=" * 68)
    print("Import smoke teszt")
    print("=" * 68 + "\n")
    telepit_stubok()

    modulok = [
        "config",
        "memory_manager",
        "sprint_engine",
        "code_analysis",
        "jenkins_repair",
        "project_doctor",
        "sandbox",
        "agents",
        "github_integration",
        "workspace",
        "ui_components",
        "util",
        "app",
    ]
    betoltott = {}
    for nev in modulok:
        try:
            betoltott[nev] = __import__(nev)
            check(True, f"{nev} importálható")
        except Exception as exc:  # noqa: BLE001
            check(False, f"{nev} importálható – {type(exc).__name__}: {exc}")

    print("\n  -- Publikus API ellenőrzése --")
    elvart = {
        "agents": ["get_lm_studio_models", "get_agent_chain", "refine_profile",
                   "generate_base_profile", "update_project_memory", "format_recent_history"],
        "util": ["extract_wireframe_code", "render_wireframe_ui", "refresh_telemetry_ui",
                 "run_agent_with_telemetry", "AgensFutasHiba"],
        "ui_components": ["SprintStatusManager", "render_telemetry_dashboard",
                          "render_agent_configuration_ui"],
        "memory_manager": ["load_all_runs", "save_run", "delete_run", "clear_memory_file"],
        "github_integration": ["push_to_github", "extract_all_blocks", "collect_files"],
        "sprint_engine": ["SprintAllapot", "validate_it_valasz", "kell_ujraprobalni",
                          "lezarast_kert", "javito_prompt"],
        "app": ["main", "init_session_state", "render_sprint", "run_next_agent",
                "build_agent_queue", "render_main_menu", "get_workspace", "set_workspace",
                "render_projekt_fajlfa", "futtat_buildet"],
        "workspace": ["VirtualWorkspace", "ellenoriz", "workspace_from_messages"],
        "sandbox": ["build", "elerheto_motor", "motor_leirasa", "hibak_kinyerese",
                    "SandboxEredmeny", "BuildEredmeny"],
        "project_doctor": ["diagnosztizal", "javit", "blokkolo_hibak", "backend_port",
                           "Diagnozis"],
        "code_analysis": ["szarmaztatott_utvonal", "java_teljes_utvonal", "indito_parancs",
                          "package_json_scriptek"],
        "jenkins_repair": ["javit_jenkinsfile", "generalt_jenkinsfile", "ervenyes_pipeline",
                           "projekt_info"],
    }
    for modul_nev, nevek in elvart.items():
        modul = betoltott.get(modul_nev)
        if modul is None:
            check(False, f"{modul_nev} nem töltődött be, API nem ellenőrizhető")
            continue
        hianyzo = [n for n in nevek if not hasattr(modul, n)]
        check(not hianyzo, f"{modul_nev} API teljes" + (f" (hiányzik: {hianyzo})" if hianyzo else ""))

    print("\n  -- Drótváz-kinyerés (tiszta logika) --")
    util = betoltott.get("util")
    if util:
        bt = chr(96) * 3
        check(
            util.extract_wireframe_code(f"{bt}html\n<div class='x'>Hello</div>\n{bt}") is not None,
            "explicit html kódblokkot felismer",
        )
        check(
            util.extract_wireframe_code(f"{bt}\n<body><nav>menu</nav></body>\n{bt}") is not None,
            "nyelv nélküli HTML-blokkot felismer",
        )
        check(util.extract_wireframe_code("csak sima szöveg") is None, "nem HTML esetén None")
        check(util.extract_wireframe_code("") is None, "üres bemenetre None (nem dob kivételt)")

    print("\n" + "=" * 68)
    if HIBAK:
        print(f"❌ {len(HIBAK)} ellenőrzés bukott el.")
        return 1
    print("✅ Minden modul rendben.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
