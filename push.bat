@echo off
REM ============================================================================
REM  push.bat  --  Az LLMOps Szimulator biztonsagos git-push folyamata
REM
REM  Mit csinal (sorrendben):
REM    1. Belep a sajat konyvtaraba (a repo gyokere).
REM    2. Lefuttatja mind a 7 teszt-suite-ot. HA BARMELYIK BUKIK, MEGALL.
REM    3. Stage-eli a valtozasokat (git add -A).
REM    4. Commitol (a commit uzenetet parameterkent vagy interaktivan keri be).
REM    5. Push origin main -- csak megerosites utan.
REM
REM  Hasznalat:
REM    push.bat                       -> bekeri a commit uzenetet
REM    push.bat "Rovid commit uzenet" -> ezt hasznalja
REM    push.bat /notest ...           -> kihagyja a teszteket (nem ajanlott)
REM ============================================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"

REM UTF-8 mod: kulonben a magyar Windows-konzol nem tudja kiirni a tesztek
REM ekezetes / szimbolum kimenetet, es a teszt UnicodeEncodeError-ral elszall.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
chcp 65001 >nul 2>&1

echo ============================================================
echo   LLMOps Szimulator - biztonsagos git push
echo   Repo: %CD%
echo ============================================================
echo.

REM --- Python parancs felismerese (python vagy py) ---
set "PY=python"
where python >nul 2>&1 || set "PY=py"

REM --- /notest kapcsolo kezelese ---
set "RUNTESTS=1"
if /I "%~1"=="/notest" (
    set "RUNTESTS=0"
    shift
)

REM ---------------------------------------------------------------------------
REM  1. TESZTEK
REM ---------------------------------------------------------------------------
if "%RUNTESTS%"=="1" (
    echo [1/4] Tesztek futtatasa...
    echo.
    set "FAILED="
    for %%f in (tests\test_*.py) do (
        %PY% "%%f" >nul 2>&1
        if errorlevel 1 (
            echo    [BUKAS]  %%f
            set "FAILED=%%f"
        ) else (
            echo    [OK]     %%f
        )
    )
    echo.
    if defined FAILED (
        echo ============================================================
        echo   MEGALLT: legalabb egy teszt elbukott.
        echo   A hibas kod nem kerul push-ra.
        echo ============================================================
        echo.
        echo   Az utolso bukott teszt reszletes kimenete:
        echo   ----------------------------------------------------------
        %PY% "!FAILED!"
        echo   ----------------------------------------------------------
        echo   Javitsd a hibat, majd futtasd ujra ezt a scriptet.
        pause
        exit /b 1
    )
    echo    Minden teszt zold.
) else (
    echo [1/4] Tesztek KIHAGYVA ^(/notest kapcsolo^).
)
echo.

REM ---------------------------------------------------------------------------
REM  2. STAGE
REM ---------------------------------------------------------------------------
echo [2/4] Valtozasok stage-elese ^(git add -A^)...
git add -A
if errorlevel 1 goto :giterror
echo.
echo    Stage-elt valtozasok:
git status --short
echo.

REM Ha nincs semmi stage-elve, nincs mit commitolni.
git diff --cached --quiet
if not errorlevel 1 (
    echo    Nincs uj valtozas a commithoz.
    echo    Ellenorzom, van-e mar push-olatlan commit...
    goto :maybepush
)

REM ---------------------------------------------------------------------------
REM  3. COMMIT
REM ---------------------------------------------------------------------------
echo [3/4] Commit...
set "MSG=%~1"
if "%MSG%"=="" (
    set /p "MSG=    Add meg a commit uzenetet: "
)
if "!MSG!"=="" (
    echo    Ures commit uzenet - megszakitva.
    pause
    exit /b 1
)
git commit -m "!MSG!"
if errorlevel 1 goto :giterror
echo.

REM ---------------------------------------------------------------------------
REM  4. PUSH
REM ---------------------------------------------------------------------------
:maybepush
echo [4/4] Push origin main
echo.
git log --oneline origin/main..HEAD 2>nul
echo.
set /p "CONFIRM=    Biztosan push-olsz az origin/main-re? [i/N]: "
if /I "!CONFIRM!"=="i" goto :dopush
echo    Push megszakitva. A commit helyben megmaradt.
pause
exit /b 0

:dopush
git push origin main
if errorlevel 1 goto :giterror

echo.
echo ============================================================
echo   KESZ. A valtozasok felkerultek az origin/main-re.
echo ============================================================
pause
exit /b 0

REM ---------------------------------------------------------------------------
:giterror
echo.
echo ============================================================
echo   GIT HIBA. Nezd meg a fenti uzenetet.
echo   Gyakori okok: nincs beallitva a hitelesites, halozati hiba,
echo   vagy a remote elorebb van ^(elobb: git pull^).
echo ============================================================
pause
exit /b 1
