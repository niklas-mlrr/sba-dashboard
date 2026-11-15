"""Vertrag des Windows-Starters und der daraus erzeugten Abhaengigkeiten."""
from __future__ import annotations

import subprocess
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
# START.bat liegt eine Ebene ueber programm/: im Programmordner der Lehrkraft
# soll ausser ihr nichts zu sehen sein.
START = WURZEL.parent / "START.bat"
ANFORDERUNGEN = WURZEL / "requirements.txt"
UV_EXPORT = [
    "uv",
    "export",
    "--no-dev",
    "--no-hashes",
    "--no-emit-project",
    "--no-emit-package",
    "iserv-ausleihe-api",
    "--format",
    "requirements-txt",
]


def _ab_erster_paketzeile(inhalt: str) -> str:
    """Lässt nur den von uv erzeugten Paketabschnitt, nicht Kopfkommentare."""
    zeilen = inhalt.splitlines()
    for nummer, zeile in enumerate(zeilen):
        if zeile and not zeile.startswith(("#", " ")):
            return "\n".join(zeilen[nummer:]) + "\n"
    raise AssertionError("Keine Paketzeile gefunden")


def test_start_spiegelt_keine_entwicklungsartefakte_mit():
    """``robocopy /MIR`` spiegelt alles, was nicht ausgeschlossen ist.

    ``.mypy_cache`` allein sind tausende Dateien und würden über das SMB-
    Laufwerk jeden Start verlängern; ``.claude`` gehört inhaltlich nicht auf
    einen Schul-Rechner. Die Ausschlussliste ist deshalb Teil des Vertrags und
    wird hier festgehalten, nicht nur beschrieben.
    """
    zeile = next(
        z for z in START.read_text(encoding="utf-8").splitlines()
        if z.startswith('set "AUSSCHLUSS=')
    )
    for name in (".mypy_cache", ".claude", "htmlcov", "backups"):
        assert name in zeile, name
    assert "/XF" in zeile and ".coverage" in zeile


def test_start_spiegelt_keine_arbeitsmappe_mit():
    """Die private Arbeitskopie darf auf keinen Schul-Rechner.

    Sie lag bis 2026-09-05 in ``.local`` und war darüber ausgeschlossen; seither
    legt ``START.sh`` sie im Projektordner selbst ab - unter demselben Namen wie
    die Vorlage in ``vorlage/``. Ein Ausschluss nach Dateiname trifft also beide,
    und das ist richtig so: im Produktivmodus liegt die echte Mappe auf dem
    Netzlaufwerk, gebraucht wird dort keine von beiden.
    """
    inhalt = START.read_text(encoding="utf-8")
    zeile = next(z for z in inhalt.splitlines() if z.startswith('set "AUSSCHLUSS='))
    for name in ("*.xlsx", "config.local.json", "*.dashboard-cache.json",
                 "*.sba-dashboard.lock"):
        assert name in zeile, name
    # Es gibt genau einen robocopy-Aufruf, und der traegt den Ausschluss. Bis
    # 2026-11-15 waren es zwei (dazu der Nachbarordner ausleihe-api), davor
    # drei, bis sba-bestand am 2026-09-18 in dieses Repo aufging.
    kopierzeilen = [z for z in inhalt.splitlines() if z.startswith("robocopy ")]
    assert len(kopierzeilen) == 1
    assert all("%AUSSCHLUSS%" in z for z in kopierzeilen)


def test_start_installiert_nur_bei_geaenderten_anforderungen():
    inhalt = START.read_text(encoding="utf-8")

    assert 'set "INSTALLSTAND=%VENV%\\requirements.installed.txt"' in inhalt
    assert 'fc /b "%ANFORDERUNGEN%" "%INSTALLSTAND%" >nul 2>&1' in inhalt
    assert "if not errorlevel 1 goto :pakete_fertig" in inhalt
    assert 'call :pip_install -r "%ANFORDERUNGEN%"' in inhalt
    assert 'copy /y "%ANFORDERUNGEN%" "%INSTALLSTAND%" >nul' in inhalt
    assert inhalt.index('call :pip_install -r "%ANFORDERUNGEN%"') < inhalt.index(
        'copy /y "%ANFORDERUNGEN%" "%INSTALLSTAND%" >nul'
    )


def test_start_entfernt_nur_eine_unvollstaendige_neue_umgebung():
    inhalt = START.read_text(encoding="utf-8")

    assert 'set "VENV_NEU=0"' in inhalt
    assert 'set "VENV_NEU=1"' in inhalt
    assert 'if "%VENV_NEU%"=="1" rmdir /s /q "%VENV%" >nul 2>&1' in inhalt


def test_start_verwirft_ein_venv_ohne_pip():
    """Ein halbes venv galt sonst dauerhaft als fertige Einrichtung.

    Bricht die Ersteinrichtung nach ``python -m venv`` ab - geschlossenes
    Fenster, Virenscanner -, bleibt ``Scripts\\python.exe`` liegen, ``pip`` aber
    nicht. Eine Pruefung nur auf den Interpreter uebersprang die Einrichtung
    dann bei jedem weiteren Start, und jeder endete mit "No module named pip";
    von Hand half nur das Loeschen des Ordners. Geprueft wird deshalb beides.
    """
    inhalt = START.read_text(encoding="utf-8")

    pruefung = (
        'if exist "%VENV%\\Scripts\\python.exe" '
        'if not exist "%VENV%\\Scripts\\pip.exe" ('
    )
    assert pruefung in inhalt
    assert 'rmdir /s /q "%VENV%" >nul 2>&1' in inhalt
    # Die Pruefung steht vor der Ersteinrichtung, sonst laeuft der Torso weiter.
    assert inhalt.index(pruefung) < inhalt.index(
        'if not exist "%VENV%\\Scripts\\python.exe" (\n    echo   Erstmalige'
    )
    # Ein gescheitertes rmdir darf nicht stillschweigend weiterlaufen.
    assert (
        'if exist "%VENV%\\Scripts\\python.exe" goto :venvrestfehler' in inhalt
    )


def test_start_schreibt_die_ausgelieferte_konfiguration_nicht_fort():
    """Die ausgelieferte ``config.json`` ist der Standard, keine Arbeitsdatei.

    Eine Vollkopie nach ``%LOCALAPPDATA%`` wuerde jedes kuenftige Update des
    Standards maskieren. Der Produktivstart laeuft deshalb ohne ``--config``:
    die Anwendung legt selbst nur die abweichenden Schluessel ab.
    """
    inhalt = START.read_text(encoding="utf-8")

    assert "copy /y \"%CODE%\\sba-dashboard\\config.json\"" not in inhalt
    assert "%KONFIG%" not in inhalt
    assert '-m app.start --config' not in inhalt
    assert '"%VENV%\\Scripts\\python.exe" -m app.start' in inhalt


def test_start_spiegelt_nur_den_programmordner():
    """Oben im Programmordner liegt fuer die Lehrkraft nur START.bat.

    Alles andere steckt in ``programm``; gespiegelt wird genau dieser Ordner,
    an denselben Ort wie vor dem Umzug, damit ein eingerichteter Rechner
    seine Umgebung behaelt. Fehlt der Ordner (ZIP nur geoeffnet, nicht
    entpackt), sagt START.bat das, statt robocopy scheitern zu lassen.
    """
    inhalt = START.read_text(encoding="utf-8")

    assert 'set "PROGRAMM=%~dp0programm"' in inhalt
    pruefung = 'if not exist "%PROGRAMM%\\app\\" goto :programmordner_fehlt'
    assert pruefung in inhalt
    assert inhalt.index(pruefung) < inhalt.index("robocopy ")
    (kopie,) = [z for z in inhalt.splitlines() if z.startswith("robocopy ")]
    assert kopie.startswith('robocopy "%PROGRAMM%" "%CODE%\\sba-dashboard" /MIR')
    assert "ausleihe-api" not in kopie
    # Python sucht ein mitgebrachtes Python ebenfalls im Unterordner.
    assert 'call :pruefe_python "%PROGRAMM%\\python\\python.exe"' in inhalt


def test_start_installiert_den_client_als_rad_statt_pythonpath():
    """Die laufende Anwendung darf an keinem Ordner mehr hängen, nur am venv.

    Ein ``PYTHONPATH`` auf Nachbarordner koppelt die *Laufzeit* an eine
    Ordnerstruktur. Seit 2026-11-15 gibt es auch keinen Nachbarordner mehr:
    der Programmordner auf dem Rechner der Lehrkraft ist nur dieses Repo, der
    IServ-Client liegt als fertiges Rad in ``programm/wheels``.
    """
    inhalt = START.read_text(encoding="utf-8")

    assert "set \"PYTHONPATH=" not in inhalt
    assert "--no-build-isolation" not in inhalt
    assert '"%~dp0..\\ausleihe-api"' not in inhalt
    assert (
        'for %%W in ("%WHEELS%\\iserv_ausleihe_api-*.whl") do set "AUSLEIHE_RAD=%%~fW"'
    ) in inhalt
    assert "if not defined AUSLEIHE_RAD goto :radfehler" in inhalt
    installieren = (
        '"%VENV%\\Scripts\\python.exe" -m pip install --no-index --no-deps '
        '--force-reinstall --quiet "%AUSLEIHE_RAD%"'
    )
    assert installieren in inhalt
    # Kein setuptools mehr: gebaut wird auf dem Schul-Rechner nichts.
    assert "call :pip_install --upgrade pip\n" in inhalt
    assert "setuptools" not in "\n".join(
        z for z in inhalt.splitlines() if not z.lstrip().startswith("rem")
    )


def test_start_installiert_den_client_nur_bei_geaendertem_rad():
    """Ein gewöhnlicher Start soll nichts installieren.

    Verglichen wird Byte fuer Byte mit einer Kopie des zuletzt installierten
    Rads - die Versionsnummer steigt nicht bei jeder Aenderung. Die Kopie
    entsteht erst nach erfolgreichem Install, und auch ein venv ohne Client
    (abgebrochener Start) wird erkannt.
    """
    inhalt = START.read_text(encoding="utf-8")

    vergleich = 'fc /b "%AUSLEIHE_RAD%" "%AUSLEIHE_STAND%" >nul 2>&1'
    assert vergleich in inhalt
    assert 'if not exist "%AUSLEIHE_STAND%" goto :client_installieren' in inhalt
    nachsehen = '"%VENV%\\Scripts\\python.exe" -c "import ausleihe" >nul 2>&1'
    assert nachsehen in inhalt
    assert inhalt.index(vergleich) < inhalt.index(nachsehen) < inhalt.index(
        "\n:client_installieren\n"
    )
    ablegen = 'copy /y "%AUSLEIHE_RAD%" "%AUSLEIHE_STAND%" >nul'
    assert inhalt.index("--force-reinstall") < inhalt.index(ablegen)
    # Der Client kommt nach den Paketen aus requirements.txt (seine
    # Abhaengigkeit requests steht dort).
    assert inhalt.index("\n:pakete_fertig\n") < inhalt.index("\n:client_installieren\n")


def test_jedes_start_label_wird_angesprungen_und_existiert_genau_einmal():
    """Ein Tippfehler in einem Label fällt in Batch erst beim Nutzer auf."""
    inhalt = START.read_text(encoding="utf-8")
    labels = [z[1:].strip() for z in inhalt.splitlines() if z.startswith(":")]

    assert len(labels) == len(set(labels)), f"doppeltes Label: {labels}"
    for label in labels:
        assert f"goto :{label}" in inhalt or f"call :{label}" in inhalt, (
            f"Label {label!r} wird nie angesprungen"
        )


def test_start_nimmt_nur_ein_python_mit_venv():
    """Ein Python ohne venv endete erst bei der Einrichtung mit "No module named venv".

    Das embeddable-Paket von python.org und manches mitgebrachte Python haben
    weder ``venv`` noch ``ensurepip``. Jeder Kandidat wird deshalb darauf
    geprueft, bevor er genommen wird; einer ohne bekommt eine eigene Meldung.
    """
    inhalt = START.read_text(encoding="utf-8")

    assert (
        '%* -c "import sys, venv, ensurepip; '
        'sys.exit(sys.version_info < (3, 10))" >nul 2>&1'
    ) in inhalt
    for kandidat in ('"%PROGRAMM%\\python\\python.exe"', "py -3", "python3"):
        assert f"call :pruefe_python {kandidat}" in inhalt, kandidat
    assert "if defined PY_OHNE_VENV goto :python_unvollstaendig" in inhalt
    # Ein gefundenes Python wird von spaeteren Kandidaten nicht ueberschrieben.
    assert ":pruefe_python\nif defined PYEXE exit /b 0" in inhalt


def test_start_sucht_python_3_auch_hinter_einem_python_2():
    """Auf den Schulrechnern ist "python" im PATH ein Python 2.7.

    Ein Python 3 liegt daneben, aber ohne py-Launcher. Die Suche nur nach dem
    ersten "python" fand deshalb immer das 2.7 und brach ab. Gesucht wird
    jetzt in jedem PATH-Treffer, in der Registry und in den Standardordnern.
    """
    inhalt = START.read_text(encoding="utf-8")

    assert "('where python 2^>nul') do call :pruefe_python \"%%P\"" in inhalt
    assert 'reg query "%%R\\Python\\PythonCore" /s /v ExecutablePath' in inhalt
    for ort in ("HKCU\\Software", "HKLM\\SOFTWARE", "HKLM\\SOFTWARE\\WOW6432Node"):
        assert ort in inhalt, ort
    assert '"%LOCALAPPDATA%\\Programs\\Python\\Python3*"' in inhalt
    assert '"%ProgramFiles%\\Python3*"' in inhalt
    # Die Pruefung muss vor dem ersten venv-Aufruf entschieden sein.
    assert inhalt.index("goto :python_unvollstaendig") < inhalt.index(
        '%PYEXE% -m venv "%VENV%"'
    )


def test_start_installiert_zuerst_ohne_internet():
    """Die Schulrechner erreichen PyPI nicht direkt (WinError 10061).

    Jeder pip-Install geht deshalb zuerst gegen ``programm/wheels/``, ohne
    Index. Erst wenn das scheitert, geht es ins Netz, mit dem Proxy, den
    Windows fuer pypi.org nennt. ``wheels/`` wird nicht nach %LOCALAPPDATA%
    gespiegelt.
    """
    inhalt = START.read_text(encoding="utf-8")

    assert 'set "WHEELS=%CD%\\programm\\wheels"' in inhalt
    offline = (
        '"%VENV%\\Scripts\\python.exe" -m pip install --no-index '
        '--find-links "%WHEELS%" --quiet %*'
    )
    online = '"%VENV%\\Scripts\\python.exe" -m pip install --quiet %*'
    assert offline in inhalt and online in inhalt
    assert inhalt.index(offline) < inhalt.index(online)
    assert "if not defined PROXY_GEPRUEFT call :proxy_ermitteln" in inhalt
    assert "GetSystemWebProxy().GetProxy($u)" in inhalt
    assert 'do set "PIP_PROXY=%%X"' in inhalt
    # Ausser dem Unterprogramm und dem Client-Install ruft niemand pip direkt.
    direkt = [z for z in inhalt.splitlines() if "-m pip install" in z]
    assert len(direkt) == 3, direkt
    zeile = next(z for z in inhalt.splitlines() if z.startswith('set "AUSSCHLUSS='))
    assert " wheels " in zeile.split("/XF")[0]


def test_requirements_entsprechen_dem_uv_export():
    export = subprocess.run(
        UV_EXPORT,
        cwd=WURZEL,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert _ab_erster_paketzeile(ANFORDERUNGEN.read_text(encoding="utf-8")) == _ab_erster_paketzeile(
        export
    )
