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
