"""Füllt ``wheels/`` mit allen Paketen, die ``START.bat`` ins venv installiert.

Die Schulrechner erreichen PyPI nicht direkt (der Proxy ist nur dem Browser
bekannt). ``START.bat`` installiert deshalb zuerst ohne Internet aus diesem
Ordner und geht erst ins Netz, wenn hier etwas fehlt. Gebaut wird für 64-Bit-
Windows und jede Python-Version von 3.10 bis 3.14, weil auf den Rechnern
nicht festliegt, welches Python 3 installiert ist.

Nach jeder Änderung an ``requirements.txt`` neu ausführen::

    uv run python tools/wheelhouse.py

``tests/test_wheelhouse.py`` prüft, dass der Ordner zur ``requirements.txt``
passt.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from packaging.requirements import Requirement

WURZEL = Path(__file__).resolve().parent.parent
ANFORDERUNGEN = WURZEL / "requirements.txt"
ZIEL = WURZEL / "wheels"
PYTHON_VERSIONEN = ("3.10", "3.11", "3.12", "3.13", "3.14")
PLATTFORM = "win_amd64"
# Was START.bat neben requirements.txt braucht: setuptools fuer den Install von
# ausleihe-api mit --no-build-isolation, dazu pip fuer das Upgrade direkt nach
# dem Anlegen des venv. Rein Python, also fuer alle Versionen gleich. "wheel"
# fehlt mit Absicht: setuptools baut seit 70.1 selbst Raeder, und wheel zoege
# "packaging" als weitere Abhaengigkeit nach.
WERKZEUGE = ("pip", "setuptools")


def windows_umgebung(python_version: str) -> dict[str, str]:
    """Marker-Umgebung eines CPython unter 64-Bit-Windows."""
    return {
        "implementation_name": "cpython",
        "os_name": "nt",
        "platform_machine": "AMD64",
        "platform_python_implementation": "CPython",
        "platform_system": "Windows",
        "python_full_version": f"{python_version}.0",
        "python_version": python_version,
        "sys_platform": "win32",
    }


def anforderungen(python_version: str, datei: Path = ANFORDERUNGEN) -> list[Requirement]:
    """Die Pins aus ``requirements.txt``, die für diese Python-Version gelten.

    Die Marker werden hier ausgewertet und nicht von pip: ``pip download``
    wertet sie gegen das Python aus, das es ausführt, nicht gegen das Ziel.
    """
    umgebung = windows_umgebung(python_version)
    ergebnis = []
    for zeile in datei.read_text(encoding="utf-8").splitlines():
        if not zeile or zeile.startswith(("#", " ")):
            continue
        anforderung = Requirement(zeile)
        if anforderung.marker is None or anforderung.marker.evaluate(umgebung):
            ergebnis.append(anforderung)
    return ergebnis


def _pip() -> list[str]:
    if importlib.util.find_spec("pip") is not None:
        return [sys.executable, "-m", "pip"]
    # Ein uv-venv hat kein pip; uvx holt sich eines.
    return ["uvx", "pip"]


def herunterladen(ziel: Path) -> None:
    for version in PYTHON_VERSIONEN:
        pins = [str(a).split(";")[0].strip() for a in anforderungen(version)]
        print(f"Python {version}: {len(pins)} Pakete", flush=True)
        subprocess.run(
            [
                *_pip(), "download", "--quiet",
                "--only-binary=:all:", "--no-deps",
                "--platform", PLATTFORM,
                "--python-version", version,
                "--implementation", "cp",
                "--dest", str(ziel),
                *pins, *WERKZEUGE,
            ],
            check=True,
        )


def main() -> None:
    # In einen frischen Ordner laden und erst dann tauschen: so bleiben keine
    # Räder alter Pins liegen, und ein abgebrochener Lauf lässt wheels/ intakt.
    with tempfile.TemporaryDirectory(dir=WURZEL) as tmp:
        neu = Path(tmp) / "wheels"
        neu.mkdir()
        herunterladen(neu)
        if ZIEL.exists():
            shutil.rmtree(ZIEL)
        neu.rename(ZIEL)
    groesse = sum(p.stat().st_size for p in ZIEL.iterdir()) / 1e6
    print(f"{len(list(ZIEL.iterdir()))} Dateien, {groesse:.1f} MB in {ZIEL}")


if __name__ == "__main__":
    main()
