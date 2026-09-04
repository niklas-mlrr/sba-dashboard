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
rem  4. Server starten. Die Excel-Datei bleibt die Reihe auf dem Netzlaufwerk -
rem     kopiert wird nur der Programmcode.
rem ==========================================================================
setlocal EnableExtensions
pushd "%~dp0"

set "ZIEL=%LOCALAPPDATA%\sba-dashboard"
set "CODE=%ZIEL%\app"
set "VENV=%ZIEL%\venv"
set "KONFIG=%ZIEL%\config.json"
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

set "AUSSCHLUSS=/XD .git .venv __pycache__ .pytest_cache .ruff_cache node_modules backups /XF *.pyc"
robocopy "%~dp0."          "%CODE%\sba-dashboard" /MIR /NJH /NJS /NDL /NP /R:1 /W:1 %AUSSCHLUSS% >nul
if errorlevel 8 goto :kopierfehler
robocopy "%~dp0..\sba-bestand"  "%CODE%\sba-bestand"  /MIR /NJH /NJS /NDL /NP /R:1 /W:1 %AUSSCHLUSS% /XF *.xlsx >nul
if errorlevel 8 goto :kopierfehler
robocopy "%~dp0..\ausleihe-api" "%CODE%\ausleihe-api" /MIR /NJH /NJS /NDL /NP /R:1 /W:1 %AUSSCHLUSS% /XF .env >nul
if errorlevel 8 goto :kopierfehler
if not exist "%KONFIG%" copy /y "%CODE%\sba-dashboard\config.json" "%KONFIG%" >nul

rem ── 3. venv und Pakete ────────────────────────────────────────────────────
set "VENV_NEU=0"
if not exist "%VENV%\Scripts\python.exe" (
    echo   Erstmalige Einrichtung, das dauert ein paar Minuten...
    %PYEXE% -m venv "%VENV%"
    if errorlevel 1 goto :venvfehler
    set "VENV_NEU=1"
    "%VENV%\Scripts\python.exe" -m pip install --upgrade pip --quiet
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

rem ── 4. Starten ────────────────────────────────────────────────────────────
rem Die beiden Geschwister-Repos kommen ueber den PYTHONPATH statt ueber
rem "pip install -e": beide sind reines Python, und ein Editable-Install
rem braeuchte hier ein Build-Backend aus dem Netz.
set "PYTHONPATH=%CODE%\sba-bestand;%CODE%\ausleihe-api"
set "PYTHONUTF8=1"
echo.
cd /d "%CODE%\sba-dashboard"
"%VENV%\Scripts\python.exe" -m app.start --config "%KONFIG%"
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
