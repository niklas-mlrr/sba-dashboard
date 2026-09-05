"""Vertrag des Windows-Starters und der daraus erzeugten Abhaengigkeiten."""
from __future__ import annotations

import subprocess
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
START = WURZEL / "START.bat"
ANFORDERUNGEN = WURZEL / "requirements.txt"
UV_EXPORT = [
    "uv",
    "export",
    "--no-dev",
    "--no-hashes",
    "--no-emit-project",
    "--no-emit-package",
    "iserv-ausleihe-api",
    "--no-emit-package",
    "sba-bestand",
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
    Laufwerk jeden Start verlängern; ``.local`` und ``.claude`` gehören inhaltlich
    nicht auf einen Schul-Rechner. Die Ausschlussliste ist deshalb Teil des
    Vertrags und wird hier festgehalten, nicht nur beschrieben.
    """
    zeile = next(
        z for z in START.read_text(encoding="utf-8").splitlines()
        if z.startswith('set "AUSSCHLUSS=')
    )
    for name in (".mypy_cache", ".local", ".claude", "htmlcov"):
        assert name in zeile, name
    assert "/XF" in zeile and ".coverage" in zeile


def test_start_installiert_nur_bei_geaenderten_anforderungen():
    inhalt = START.read_text(encoding="utf-8")

    assert 'set "INSTALLSTAND=%VENV%\\requirements.installed.txt"' in inhalt
    assert 'fc /b "%ANFORDERUNGEN%" "%INSTALLSTAND%" >nul 2>&1' in inhalt
    assert "if not errorlevel 1 goto :pakete_fertig" in inhalt
    assert 'pip install -r "%ANFORDERUNGEN%" --quiet' in inhalt
    assert 'copy /y "%ANFORDERUNGEN%" "%INSTALLSTAND%" >nul' in inhalt
    assert inhalt.index('pip install -r "%ANFORDERUNGEN%" --quiet') < inhalt.index(
        'copy /y "%ANFORDERUNGEN%" "%INSTALLSTAND%" >nul'
    )


def test_start_entfernt_nur_eine_unvollstaendige_neue_umgebung():
    inhalt = START.read_text(encoding="utf-8")

    assert 'set "VENV_NEU=0"' in inhalt
    assert 'set "VENV_NEU=1"' in inhalt
    assert 'if "%VENV_NEU%"=="1" rmdir /s /q "%VENV%" >nul 2>&1' in inhalt


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


def test_start_installiert_die_geschwister_ins_venv_statt_pythonpath():
    """Die laufende Anwendung darf an keinem Ordner mehr hängen, nur am venv.

    Ein ``PYTHONPATH`` auf die Nachbarordner koppelt die *Laufzeit* an eine
    Ordnerstruktur: ein halb gespiegelter Baum oder ein Fenster mit altem
    ``PYTHONPATH`` bricht die Anwendung an einer Stelle, an der niemand sucht.
    Begründung und Rollback stehen in ``docs/verteilung.md``.
    """
    inhalt = START.read_text(encoding="utf-8")

    assert "set \"PYTHONPATH=" not in inhalt
    assert (
        '"%VENV%\\Scripts\\python.exe" -m pip install --no-build-isolation --no-deps '
        '--quiet "%CODE%\\ausleihe-api" "%CODE%\\sba-bestand"'
    ) in inhalt
    # setuptools muss im venv liegen, sonst hat --no-build-isolation kein Backend.
    assert "pip install --upgrade pip setuptools wheel --quiet" in inhalt


def test_start_installiert_die_geschwister_nur_bei_geaenderten_quellen():
    """Ein gewöhnlicher Start soll nichts bauen.

    ``robocopy`` meldet mit Rückgabecode 1 "es wurde etwas kopiert" - genau
    daran hängt die Frage, ob neu installiert werden muss.
    """
    inhalt = START.read_text(encoding="utf-8")

    assert 'set "GESCHWISTER_NEU=0"' in inhalt
    assert inhalt.count('if errorlevel 1 set "GESCHWISTER_NEU=1"') == 2
    assert 'if "%VENV_NEU%"=="1" set "GESCHWISTER_NEU=1"' in inhalt
    assert 'if "%GESCHWISTER_NEU%"=="0" goto :geschwister_fertig' in inhalt
    # Ein Kopierfehler bleibt ein Kopierfehler: die 8er-Pruefung steht davor.
    assert inhalt.index("if errorlevel 8 goto :kopierfehler") < inhalt.index(
        'if errorlevel 1 set "GESCHWISTER_NEU=1"'
    )


def test_jedes_start_label_wird_angesprungen_und_existiert_genau_einmal():
    """Ein Tippfehler in einem Label fällt in Batch erst beim Nutzer auf."""
    inhalt = START.read_text(encoding="utf-8")
    labels = [z[1:].strip() for z in inhalt.splitlines() if z.startswith(":")]

    assert len(labels) == len(set(labels)), f"doppeltes Label: {labels}"
    for label in labels:
        assert f"goto :{label}" in inhalt, f"Label {label!r} wird nie angesprungen"


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
