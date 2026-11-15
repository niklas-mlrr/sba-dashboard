@echo off
rem ==========================================================================
rem  Schulbuchausleihe - Bestand und Nachbestellung
rem
rem  Doppelklick genuegt. Im Programmordner liegt fuer die Lehrkraft mit
rem  Absicht nur diese Datei; alles andere steckt im Unterordner "programm".
rem  Was hier passiert und warum:
rem
rem  1. Python suchen (portabel -> py-Launcher -> PATH). Ohne Admin-Rechte.
rem  2. Den Ordner "programm" nach %LOCALAPPDATA% spiegeln. Ausgefuehrt wird
rem     von dort: der Programmordner darf verschoben, neu entpackt oder durch
rem     eine neuere Fassung ersetzt werden, ohne dass die eingerichtete
rem     Umgebung daran zerbricht.
rem  3. Beim ersten Start ein venv anlegen und die Pakete installieren, alle
rem     aus programm\wheels - auch den IServ-Client, der dort als fertiges Rad
rem     liegt. Die laufende Anwendung haengt danach an keinem Ordner mehr,
rem     nur noch am venv und am eigenen Quellbaum.
rem  4. Server starten. Die Excel-Datei bleibt die ganze Zeit auf dem
rem     Netzlaufwerk - kopiert wird nur der Programmcode.
rem ==========================================================================
setlocal EnableExtensions
pushd "%~dp0"

rem Fehlt "programm" neben dieser Datei, ist meist eine ZIP-Datei nicht
rem entpackt worden: Windows zeigt ihren Inhalt an und startet die Datei
rem daraus, ohne den Rest mitzunehmen.
set "PROGRAMM=%~dp0programm"
if not exist "%PROGRAMM%\app\" goto :programmordner_fehlt

set "ZIEL=%LOCALAPPDATA%\sba-dashboard"
set "CODE=%ZIEL%\app"
set "VENV=%ZIEL%\venv"
set "ANFORDERUNGEN=%CODE%\sba-dashboard\requirements.txt"
set "INSTALLSTAND=%VENV%\requirements.installed.txt"
rem Die mitgelieferten Pakete (programm\wheels\, erzeugt von
rem tools\wheelhouse.py) werden nicht gespiegelt: rund 60 MB, die nur bei
rem Einrichtung und Update gelesen werden. %CD% statt %~dp0, weil pushd einem
rem UNC-Pfad oben einen Laufwerksbuchstaben gegeben hat.
set "WHEELS=%CD%\programm\wheels"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"

echo ==========================================================
echo   Schulbuchausleihe - Bestand und Nachbestellung
echo ==========================================================
echo.
echo   Bitte NICHT als Administrator starten.
echo.

rem ── 1. Python finden ──────────────────────────────────────────────────────
rem Ein Python zaehlt nur, wenn es venv und ensurepip mitbringt. Das
rem "embeddable"-Paket von python.org und manches Python, das ein anderes
rem Programm in den PATH legt, haben beides nicht; frueher wurde so eines
rem genommen, und die Einrichtung endete mit "No module named venv". Solche
rem Kandidaten werden uebersprungen und nur fuer die Fehlermeldung gemerkt.
rem
rem Gesucht wird nicht nur das erste "python" im PATH. Auf den Schulrechnern
rem liegt dort ein Python 2.7 (ohne venv), waehrend ein Python 3 ohne
rem py-Launcher daneben installiert ist. Deshalb: jeder Treffer im PATH, dann
rem die Registry (PEP 514, wo der Installer jedes Python 3 eintraegt), dann
rem die ueblichen Installationsordner. Der erste brauchbare gewinnt.
set "PYEXE="
set "PY_OHNE_VENV="
set "PY_OHNE_VENV_VERSION="
if exist "%PROGRAMM%\python\python.exe" call :pruefe_python "%PROGRAMM%\python\python.exe"
call :pruefe_python py -3
call :pruefe_python python3
for /f "delims=" %%P in ('where python 2^>nul') do call :pruefe_python "%%P"
for %%R in (HKCU\Software HKLM\SOFTWARE HKLM\SOFTWARE\WOW6432Node) do (
    for /f "tokens=2,*" %%A in ('reg query "%%R\Python\PythonCore" /s /v ExecutablePath 2^>nul ^| findstr /i "ExecutablePath"') do call :pruefe_python "%%B"
)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*" "%SystemDrive%\Python3*") do (
    if exist "%%D\python.exe" call :pruefe_python "%%D\python.exe"
)
if defined PYEXE goto :python_da
if defined PY_OHNE_VENV goto :python_unvollstaendig

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
rem .mypy_cache allein sind tausende Dateien. "python" ist ein mitgebrachtes
rem portables Python (siehe oben), das von seinem Platz aus laeuft.
rem
rem *.xlsx gehoert seit 2026-09-05 in diese Liste: START.sh legt seine private
rem Arbeitskopie jetzt im Projektordner selbst ab (vorher in .local, das hier
rem einzeln ausgeschlossen war) und traegt denselben Dateinamen wie die Vorlage
rem in vorlage\ - ein Ausschluss nur nach Name traefe also beide oder keinen.
rem Beide zu nehmen ist richtig: die Vorlage braucht nur START.sh und die
rem Testsuite, im Produktivmodus liegt die echte Mappe auf dem Netzlaufwerk.
rem Dazu config.local.json (zeigt auf die Arbeitskopie) und die Nachbardateien,
rem die neben einer geoeffneten Mappe entstehen.
set "AUSSCHLUSS=/XD .git .venv __pycache__ .pytest_cache .ruff_cache .mypy_cache .claude htmlcov node_modules backups wheels python /XF *.pyc .coverage *.xlsx config.local.json *.dashboard-cache.json *.sba-dashboard.lock"
rem Das Ziel heisst weiter "sba-dashboard", wie vor dem Umzug in "programm"
rem (2026-11-15): so bleibt ein schon eingerichteter Rechner, wie er ist.
robocopy "%PROGRAMM%" "%CODE%\sba-dashboard" /MIR /NJH /NJS /NDL /NP /R:1 /W:1 %AUSSCHLUSS% >nul
if errorlevel 8 goto :kopierfehler
rem Bis 2026-11-15 wurde hier zusaetzlich der Nachbarordner ..\ausleihe-api
rem gespiegelt und aus dem Spiegel installiert. Der Client kommt jetzt als Rad
rem aus programm\wheels (Schritt 3b); der alte Spiegel ist nur noch Ballast.
if exist "%CODE%\ausleihe-api\" rmdir /s /q "%CODE%\ausleihe-api" >nul 2>&1
rem Die ausgelieferte config.json wird NICHT mehr hierher kopiert. Sie ist der
rem Standard; was die Lehrkraft auswaehlt, legt die Anwendung selbst in
rem "%ZIEL%\config.json" ab und legt nur die abweichenden Schluessel hinein.
rem Eine dort schon liegende Vollkopie aus einer aelteren Fassung wird beim
rem ersten Start bereinigt, die Auswahl bleibt erhalten.

rem ── 3. venv und Pakete ────────────────────────────────────────────────────
rem Geprueft wird nicht nur der Interpreter, sondern auch pip. Eine
rem abgebrochene Ersteinrichtung - geschlossenes Fenster, Virenscanner - laesst
rem ein venv mit python.exe, aber ohne pip zurueck. Ohne die zweite Pruefung
rem galt dieser Torso dauerhaft als fertig: jeder weitere Start uebersprang die
rem Einrichtung und endete erneut mit "No module named pip". Ein halbes venv
rem ist nichts wert, es wird darum verworfen und neu angelegt.
set "VENV_NEU=0"
if exist "%VENV%\Scripts\python.exe" if not exist "%VENV%\Scripts\pip.exe" (
    echo   Die vorhandene Umgebung ist unvollstaendig und wird neu angelegt...
    rmdir /s /q "%VENV%" >nul 2>&1
    if exist "%VENV%\Scripts\python.exe" goto :venvrestfehler
)
if not exist "%VENV%\Scripts\python.exe" (
    echo   Erstmalige Einrichtung, das dauert ein paar Minuten...
    %PYEXE% -m venv "%VENV%"
    if errorlevel 1 goto :venvfehler
    set "VENV_NEU=1"
    rem setuptools kam hier bis 2026-11-15 mit, fuer den Bau des IServ-Clients
    rem aus dem Quellbaum. Er kommt jetzt fertig als Rad, gebaut wird nichts.
    call :pip_install --upgrade pip
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
call :pip_install -r "%ANFORDERUNGEN%"
if errorlevel 1 goto :pipfehler
copy /y "%ANFORDERUNGEN%" "%INSTALLSTAND%" >nul
if errorlevel 1 goto :installstandfehler
if "%VENV_NEU%"=="1" echo   Einrichtung fertig.

:pakete_fertig

rem ── 3b. Der IServ-Client ins venv ─────────────────────────────────────────
rem Er liegt als fertiges Rad in programm\wheels, gebaut von
rem tools\wheelhouse.py aus dem Geschwister-Repo ausleihe-api. Bis 2026-11-15
rem wurde er hier aus dem gespiegelten Nachbarordner ..\ausleihe-api gebaut;
rem den gibt es im Programmordner auf dem Rechner der Lehrkraft aber nicht.
rem --no-deps, weil requirements.txt die einzige Quelle fuer Paketversionen
rem bleibt; --force-reinstall, weil die Versionsnummer nicht bei jeder
rem Aenderung steigt und pip ein "schon installiert" sonst glaubt.
rem
rem Neu installiert wird, wenn sich das Rad von dem zuletzt installierten
rem unterscheidet (Byte fuer Byte, wie bei requirements.txt oben) oder wenn
rem das venv den Client nicht hat: ein Start, der nach dem Anlegen des venv
rem abbrach, endete sonst im Anmeldefenster mit "No module named 'ausleihe'".
rem Die Kopie wird erst nach erfolgreichem Install abgelegt.
set "AUSLEIHE_RAD="
for %%W in ("%WHEELS%\iserv_ausleihe_api-*.whl") do set "AUSLEIHE_RAD=%%~fW"
if not defined AUSLEIHE_RAD goto :radfehler
set "AUSLEIHE_STAND=%VENV%\ausleihe-api.installed.whl"
if not exist "%AUSLEIHE_STAND%" goto :client_installieren
fc /b "%AUSLEIHE_RAD%" "%AUSLEIHE_STAND%" >nul 2>&1
if errorlevel 1 goto :client_installieren
"%VENV%\Scripts\python.exe" -c "import ausleihe" >nul 2>&1
if not errorlevel 1 goto :client_fertig
:client_installieren
echo   Bibliothek wird eingerichtet...
"%VENV%\Scripts\python.exe" -m pip install --no-index --no-deps --force-reinstall --quiet "%AUSLEIHE_RAD%"
if errorlevel 1 goto :clientfehler
copy /y "%AUSLEIHE_RAD%" "%AUSLEIHE_STAND%" >nul
if errorlevel 1 goto :installstandfehler
:client_fertig

rem ── 4. Starten ────────────────────────────────────────────────────────────
set "PYTHONUTF8=1"
echo.
cd /d "%CODE%\sba-dashboard"
rem Ohne --config laeuft der Produktivmodus: ausgelieferte config.json plus
rem Benutzerkonfiguration aus %LOCALAPPDATA%. Ein ausdruecklicher --config-Pfad
rem waere der Arbeitskopie-Modus und wuerde genau diese Trennung aufheben.
"%VENV%\Scripts\python.exe" -m app.start
goto :ende

rem Prueft einen Python-Kandidaten (Befehl samt Argumenten in %*). Ohne
rem Klammerblock, weil ein Pfad wie "Program Files (x86)" ihn aufbraeche.
rem Verlangt Python 3.10+ mit venv und ensurepip; Python 2 scheitert schon am
rem Import. Ist schon eines gefunden, wird nichts mehr geprueft.
:pruefe_python
if defined PYEXE exit /b 0
%* --version >nul 2>&1
if errorlevel 1 exit /b 0
%* -c "import sys, venv, ensurepip; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 goto :pruefe_python_ohne_venv
set "PYEXE=%*"
exit /b 0
:pruefe_python_ohne_venv
if defined PY_OHNE_VENV exit /b 0
set "PY_OHNE_VENV=%*"
rem Python 2 schreibt seine Version nach stderr, daher 2^>^&1.
for /f "delims=" %%V in ('%* --version 2^>^&1') do set "PY_OHNE_VENV_VERSION=%%V"
exit /b 0

rem Installiert Pakete ins venv (Argumente in %*). Zuerst ohne Internet aus
rem wheels\: die Schulrechner erreichen PyPI nicht direkt. Nur wenn das
rem scheitert - Ordner fehlt, Paket fehlt, unbekannte Python-Version -, geht es
rem ueber das Internet, mit dem Proxy, den Windows dafuer nennt.
rem "exit /b" ohne Zahl gibt den Rueckgabecode des letzten pip weiter.
:pip_install
if not exist "%WHEELS%\" goto :pip_install_online
"%VENV%\Scripts\python.exe" -m pip install --no-index --find-links "%WHEELS%" --quiet %* >nul 2>&1
if not errorlevel 1 exit /b 0
echo   Mitgelieferte Pakete reichen nicht, versuche es ueber das Internet...
:pip_install_online
if not defined PROXY_GEPRUEFT call :proxy_ermitteln
"%VENV%\Scripts\python.exe" -m pip install --quiet %*
exit /b

rem Python liest einen fest eingetragenen Proxy selbst aus der Registry, eine
rem automatische Konfiguration (PAC/WPAD, wie in Schulnetzen ueblich) aber
rem nicht. Windows wertet sie aus und nennt den Proxy fuer pypi.org; pip
rem nimmt ihn aus PIP_PROXY. Antwortet PowerShell nicht (gesperrt), bleibt
rem es beim direkten Weg.
:proxy_ermitteln
set "PROXY_GEPRUEFT=1"
if defined PIP_PROXY exit /b 0
if defined HTTPS_PROXY exit /b 0
for /f "usebackq delims=" %%X in (`powershell -NoProfile -NonInteractive -Command "$u=[uri]'https://pypi.org/simple/'; $p=[Net.WebRequest]::GetSystemWebProxy().GetProxy($u); if ($p -and $p.Authority -ne $u.Authority) { $p.AbsoluteUri }" 2^>nul`) do set "PIP_PROXY=%%X"
if defined PIP_PROXY echo   Proxy: %PIP_PROXY%
exit /b 0

:python_unvollstaendig
echo   KEIN PASSENDES PYTHON GEFUNDEN.
echo.
echo   Gefunden wurde nur: %PY_OHNE_VENV% (%PY_OHNE_VENV_VERSION%)
echo   Gebraucht wird Python 3.10 oder neuer mit dem Modul "venv".
echo   Python 2 hat es nicht, ebenso wenig das "embeddable"-Paket oder
echo   ein Python, das ein anderes Programm mitbringt.
echo.
echo   So bekommen Sie ein vollstaendiges, ohne Administrator zu sein:
echo.
echo     1. python.org im Browser oeffnen, "Downloads"
echo     2. Den normalen Installer fuer Windows herunterladen und starten
echo        (nicht das "embeddable package")
echo     3. Im Installer den Haken bei "Install for me only" setzen
echo     4. Danach diese Datei erneut doppelklicken
echo.
pause
popd
exit /b 1

:programmordner_fehlt
echo   DER ORDNER "programm" FEHLT.
echo.
echo   Er muss im selben Ordner liegen wie diese Datei. Meist heisst das:
echo   die ZIP-Datei wurde nur geoeffnet, nicht entpackt.
echo.
echo     1. Rechtsklick auf die ZIP-Datei, "Alle extrahieren..."
echo     2. Im entpackten Ordner diese Datei erneut doppelklicken
echo.
pause
popd
exit /b 1

:kopierfehler
echo.
echo   Die Programmdateien liessen sich nicht kopieren nach:
echo     %CODE%
echo   Bitte alle Fenster des Programms schliessen und es erneut versuchen.
echo   Klappt es dann immer noch nicht, Niklas Bescheid geben.
echo.
pause
popd
exit /b 1

:venvrestfehler
echo.
echo   Die unvollstaendige Python-Umgebung liess sich nicht entfernen.
echo   Meist haelt noch ein offenes Fenster des Programms sie fest.
echo   Bitte alle Fenster schliessen und diesen Ordner von Hand loeschen:
echo     %VENV%
echo   Danach diese Datei erneut doppelklicken.
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
echo   Weder die mitgelieferten Pakete (Ordner "programm\wheels")
echo   noch das Internet haben gereicht. Bitte Niklas Bescheid geben.
echo.
if "%VENV_NEU%"=="1" rmdir /s /q "%VENV%" >nul 2>&1
pause
popd
exit /b 1

:radfehler
echo.
echo   Im Ordner "programm\wheels" fehlt die IServ-Bibliothek
echo   (iserv_ausleihe_api-....whl). Der Programmordner ist unvollstaendig.
echo   Bitte ihn neu herunterladen bzw. entpacken; hilft das nicht,
echo   Niklas Bescheid geben.
echo.
pause
popd
exit /b 1

:clientfehler
echo.
echo   Die mitgelieferte Bibliothek liess sich nicht einrichten.
echo   Bitte es erneut versuchen und, falls es wieder passiert,
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
