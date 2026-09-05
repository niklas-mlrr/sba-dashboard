@echo off
rem ==========================================================================
rem  Schulbuchausleihe - Bestand und Nachbestellung
rem
rem  Doppelklick genuegt. Was hier passiert und warum:
rem
rem  1. Python suchen (portabel -> py-Launcher -> PATH). Ohne Admin-Rechte.
rem  2. Die drei Quellordner vom Netzlaufwerk nach %LOCALAPPDATA% spiegeln.
rem     Ausgefuehrt wird lokal: ein venv auf einem SMB-Laufwerk ist quaelend
rem     langsam und geht bei Verbindungsabbruch kaputt.
rem  3. Beim ersten Start ein venv anlegen und die Pakete installieren.
rem     Die beiden Geschwister-Bibliotheken werden dabei richtig ins venv
rem     installiert, nicht ueber den PYTHONPATH untergeschoben: die laufende
rem     Anwendung haengt dann an keinem Ordner mehr, nur noch am venv.
rem  4. Server starten. Die Excel-Datei bleibt die ganze Zeit auf dem
rem     Netzlaufwerk - kopiert wird nur der Programmcode.
rem ==========================================================================
setlocal EnableExtensions
pushd "%~dp0"

set "ZIEL=%LOCALAPPDATA%\sba-dashboard"
set "CODE=%ZIEL%\app"
set "VENV=%ZIEL%\venv"
set "ANFORDERUNGEN=%CODE%\sba-dashboard\requirements.txt"
set "INSTALLSTAND=%VENV%\requirements.installed.txt"

echo ==========================================================
echo   Schulbuchausleihe - Bestand und Nachbestellung
echo ==========================================================
echo.
echo   Bitte NICHT als Administrator starten.
echo.

rem ── 1. Python finden ──────────────────────────────────────────────────────
set "PYEXE="
if exist "%~dp0python\python.exe" (
    set "PYEXE=%~dp0python\python.exe"
    goto :python_da
)
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYEXE=py -3"
    goto :python_da
)
python --version >nul 2>&1
if not errorlevel 1 (
    set "PYEXE=python"
    goto :python_da
)

echo   KEIN PYTHON GEFUNDEN.
echo.
echo   So bekommen Sie eines, ohne Administrator zu sein:
echo.
echo     1. python.org im Browser oeffnen, "Downloads"
echo     2. Den Installer fuer Windows herunterladen und starten
echo     3. Im Installer den Haken bei "Install for me only" setzen
echo        (dann wird kein Administrator verlangt)
echo     4. Danach diese Datei erneut doppelklicken
echo.
pause
popd
exit /b 1

:python_da
echo   Python gefunden: %PYEXE%

rem ── 2. Quellcode lokal spiegeln ───────────────────────────────────────────
rem robocopy /MIR spiegelt exakt; Rueckgabecodes 0-7 sind Erfolg, ab 8 Fehler.
echo   Programmdateien werden aktualisiert...
if not exist "%CODE%" mkdir "%CODE%" >nul 2>&1

rem Ausgeschlossen werden auch die Entwicklungsartefakte des Repo-Kopierers:
rem .mypy_cache allein sind tausende Dateien.
rem
rem *.xlsx gehoert seit 2026-09-05 in diese Liste: START.sh legt seine private
rem Arbeitskopie jetzt im Projektordner selbst ab (vorher in .local, das hier
rem einzeln ausgeschlossen war) und traegt denselben Dateinamen wie die Vorlage
rem in vorlage\ - ein Ausschluss nur nach Name traefe also beide oder keinen.
rem Beide zu nehmen ist richtig: die Vorlage braucht nur START.sh und die
rem Testsuite, im Produktivmodus liegt die echte Mappe auf dem Netzlaufwerk.
rem Dazu config.local.json (zeigt auf die Arbeitskopie) und die Nachbardateien,
rem die neben einer geoeffneten Mappe entstehen.
set "AUSSCHLUSS=/XD .git .venv __pycache__ .pytest_cache .ruff_cache .mypy_cache .claude htmlcov node_modules backups /XF *.pyc .coverage *.xlsx config.local.json *.dashboard-cache.json *.sba-dashboard.lock"
rem robocopy meldet mit Rueckgabecode 1 "es wurde etwas kopiert". Genau daran
rem haengt weiter unten die Frage, ob die beiden Bibliotheken neu installiert
rem werden muessen - sonst liefe nach einem Update weiter der alte Stand.
set "GESCHWISTER_NEU=0"
robocopy "%~dp0."          "%CODE%\sba-dashboard" /MIR /NJH /NJS /NDL /NP /R:1 /W:1 %AUSSCHLUSS% >nul
if errorlevel 8 goto :kopierfehler
robocopy "%~dp0..\sba-bestand"  "%CODE%\sba-bestand"  /MIR /NJH /NJS /NDL /NP /R:1 /W:1 %AUSSCHLUSS% >nul
if errorlevel 8 goto :kopierfehler
if errorlevel 1 set "GESCHWISTER_NEU=1"
robocopy "%~dp0..\ausleihe-api" "%CODE%\ausleihe-api" /MIR /NJH /NJS /NDL /NP /R:1 /W:1 %AUSSCHLUSS% /XF .env >nul
if errorlevel 8 goto :kopierfehler
if errorlevel 1 set "GESCHWISTER_NEU=1"
rem Die ausgelieferte config.json wird NICHT mehr hierher kopiert. Sie ist der
rem Standard; was die Lehrkraft auswaehlt, legt die Anwendung selbst in
rem "%ZIEL%\config.json" ab und legt nur die abweichenden Schluessel hinein.
rem Eine dort schon liegende Vollkopie aus einer aelteren Fassung wird beim
rem ersten Start bereinigt, die Auswahl bleibt erhalten.

rem ── 3. venv und Pakete ────────────────────────────────────────────────────
set "VENV_NEU=0"
if not exist "%VENV%\Scripts\python.exe" (
    echo   Erstmalige Einrichtung, das dauert ein paar Minuten...
    %PYEXE% -m venv "%VENV%"
    if errorlevel 1 goto :venvfehler
    set "VENV_NEU=1"
    rem setuptools und wheel gehoeren mit ins venv: nur dann laesst sich das
    rem Geschwister-Paket unten mit --no-build-isolation installieren, also
    rem auch dann noch, wenn der Laptop gerade kein Internet hat.
    "%VENV%\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel --quiet
    if errorlevel 1 goto :pipfehler
)

rem Die gespeicherte Kopie wird erst nach erfolgreichem pip-Install ersetzt.
rem Damit wird nach einem abgebrochenen Update beim naechsten Start erneut
rem installiert, statt eine unvollstaendige Umgebung als aktuell zu behandeln.
if exist "%INSTALLSTAND%" (
    fc /b "%ANFORDERUNGEN%" "%INSTALLSTAND%" >nul 2>&1
    if not errorlevel 1 goto :pakete_fertig
)

if "%VENV_NEU%"=="1" (
    echo   Pakete werden installiert, das dauert ein paar Minuten...
) else (
    echo   Abhaengigkeiten haben sich geaendert und werden aktualisiert...
)
"%VENV%\Scripts\python.exe" -m pip install -r "%ANFORDERUNGEN%" --quiet
if errorlevel 1 goto :pipfehler
copy /y "%ANFORDERUNGEN%" "%INSTALLSTAND%" >nul
if errorlevel 1 goto :installstandfehler
if "%VENV_NEU%"=="1" echo   Einrichtung fertig.

:pakete_fertig

rem ── 3b. Die beiden Bibliotheken ins venv ──────────────────────────────────
rem Nicht editable und nicht ueber den PYTHONPATH, sondern ein gewoehnlicher
rem Install aus dem gespiegelten Quellbaum. Damit haengt die laufende Anwendung
rem an nichts ausser dem venv; ein halb geloeschter Spiegelordner oder ein
rem vergessenes PYTHONPATH-Fenster kann sie nicht mehr auf halbem Weg brechen.
rem --no-build-isolation nutzt das oben installierte setuptools statt eines
rem frisch heruntergeladenen; --no-deps, weil requirements.txt die einzige
rem Quelle fuer Paketversionen bleibt.
if "%VENV_NEU%"=="1" set "GESCHWISTER_NEU=1"
if "%GESCHWISTER_NEU%"=="0" goto :geschwister_fertig
echo   Bibliotheken werden eingerichtet...
"%VENV%\Scripts\python.exe" -m pip install --no-build-isolation --no-deps --quiet "%CODE%\ausleihe-api" "%CODE%\sba-bestand"
if errorlevel 1 goto :geschwisterfehler
:geschwister_fertig

rem ── 4. Starten ────────────────────────────────────────────────────────────
set "PYTHONUTF8=1"
echo.
cd /d "%CODE%\sba-dashboard"
rem Ohne --config laeuft der Produktivmodus: ausgelieferte config.json plus
rem Benutzerkonfiguration aus %LOCALAPPDATA%. Ein ausdruecklicher --config-Pfad
rem waere der Arbeitskopie-Modus und wuerde genau diese Trennung aufheben.
"%VENV%\Scripts\python.exe" -m app.start
goto :ende

:kopierfehler
echo.
echo   Die Programmdateien liessen sich nicht kopieren.
echo   Meist heisst das: das Netzlaufwerk ist gerade nicht verbunden.
echo   Bitte im Explorer pruefen, ob der Ordner "Buchausleihe Admins"
echo   zu oeffnen ist, und es dann erneut versuchen.
echo.
pause
popd
exit /b 1

:venvfehler
echo.
echo   Die Python-Umgebung liess sich nicht anlegen.
echo   Bitte diese Meldung an Niklas weitergeben.
echo.
pause
popd
exit /b 1

:pipfehler
echo.
echo   Die benoetigten Pakete liessen sich nicht installieren.
echo   Meist fehlt dafuer der Internetzugang. Bitte Niklas Bescheid geben.
echo.
if "%VENV_NEU%"=="1" rmdir /s /q "%VENV%" >nul 2>&1
pause
popd
exit /b 1

:geschwisterfehler
echo.
echo   Die mitgelieferten Bibliotheken liessen sich nicht einrichten.
echo   Meist heisst das: das Netzlaufwerk war beim Kopieren nicht vollstaendig
echo   verbunden. Bitte es erneut versuchen und, falls es wieder passiert,
echo   Niklas Bescheid geben.
echo.
if "%VENV_NEU%"=="1" rmdir /s /q "%VENV%" >nul 2>&1
pause
popd
exit /b 1

:installstandfehler
echo.
echo   Der Installationsstand konnte nicht gespeichert werden.
echo   Bitte Niklas Bescheid geben und das Programm erneut starten.
echo.
pause
popd
exit /b 1

:ende
echo.
pause
popd
