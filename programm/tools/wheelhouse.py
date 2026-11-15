"""Füllt ``wheels/`` mit allen Paketen, die ``START.bat`` ins venv installiert.

Die Schulrechner erreichen PyPI nicht direkt (der Proxy ist nur dem Browser
bekannt). ``START.bat`` installiert deshalb zuerst ohne Internet aus diesem
Ordner und geht erst ins Netz, wenn hier etwas fehlt. Gebaut wird für 64-Bit-
Windows auf x64 und auf ARM (``ZIELE``) und jede Python-Version, die dort
vorkommen kann, weil auf den Rechnern nicht festliegt, welches Python 3
installiert ist. Fehlt ein Rad, versucht pip zu kompilieren - und das
scheitert auf einem Rechner ohne Visual C++ immer (2026-11-15: ARM-Laptop mit
Python 3.15).

Dazu kommt ein Rad des IServ-Clients ``ausleihe-api``, gebaut aus dem
Geschwister-Repo. Der Programmordner auf dem Rechner der Lehrkraft ist nur
dieses Repo; einen Ordner ``ausleihe-api`` daneben gibt es dort nicht.

Nach jeder Änderung an ``requirements.txt`` neu ausführen::

    uv run python tools/wheelhouse.py

Nach einer Änderung nur an ``ausleihe-api`` genügt (ohne Download)::

    uv run python tools/wheelhouse.py --nur-ausleihe

``tests/test_wheelhouse.py`` prüft, dass der Ordner zur ``requirements.txt``
passt.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from packaging.requirements import Requirement

WURZEL = Path(__file__).resolve().parent.parent
ANFORDERUNGEN = WURZEL / "requirements.txt"
ZIEL = WURZEL / "wheels"
# programm/ -> Repo -> Sammelordner, in dem ausleihe-api als Geschwister liegt.
AUSLEIHE_QUELLE = WURZEL.parent.parent / "ausleihe-api"
AUSLEIHE_NAME = "iserv-ausleihe-api"
# Fester Zeitstempel fuer die Eintraege im Rad: so ist ein neu gebautes Rad aus
# unveraendertem Quellcode Byte fuer Byte gleich, und Git sieht keine Aenderung.
# START.bat vergleicht genau diese Bytes mit dem zuletzt installierten Rad.
REPRODUZIERBAR = "315532800"  # 1980-01-01, das Minimum fuer ZIP-Zeitstempel
PYTHON_VERSIONEN = ("3.10", "3.11", "3.12", "3.13", "3.14", "3.15")
# Plattform -> Python-Versionen. Windows auf ARM hat erst seit 3.11 offizielle
# Installer, und pydantic-core liefert für ARM erst ab 3.11 Räder.
ZIELE = {
    "win_amd64": PYTHON_VERSIONEN,
    "win_arm64": PYTHON_VERSIONEN[1:],
}
# Was START.bat neben requirements.txt braucht: pip fuer das Upgrade direkt nach
# dem Anlegen des venv. Rein Python, also fuer alle Versionen gleich.
# setuptools stand hier, bis ausleihe-api als fertiges Rad mitkam (2026-11-15):
# vorher baute START.bat den Client mit --no-build-isolation aus dem Quellbaum.
WERKZEUGE = ("pip",)


def windows_umgebung(python_version: str, plattform: str = "win_amd64") -> dict[str, str]:
    """Marker-Umgebung eines CPython unter 64-Bit-Windows."""
    return {
        "implementation_name": "cpython",
        "os_name": "nt",
        "platform_machine": "ARM64" if plattform == "win_arm64" else "AMD64",
        "platform_python_implementation": "CPython",
        "platform_system": "Windows",
        "python_full_version": f"{python_version}.0",
        "python_version": python_version,
        "sys_platform": "win32",
    }


def anforderungen(python_version: str, datei: Path = ANFORDERUNGEN,
                  plattform: str = "win_amd64") -> list[Requirement]:
    """Die Pins aus ``requirements.txt``, die für diese Python-Version gelten.

    Die Marker werden hier ausgewertet und nicht von pip: ``pip download``
    wertet sie gegen das Python aus, das es ausführt, nicht gegen das Ziel.
    """
    umgebung = windows_umgebung(python_version, plattform)
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
    for plattform, versionen in ZIELE.items():
        for version in versionen:
            pins = [str(a).split(";")[0].strip()
                    for a in anforderungen(version, plattform=plattform)]
            print(f"{plattform}, Python {version}: {len(pins)} Pakete", flush=True)
            subprocess.run(
                [
                    *_pip(), "download", "--quiet",
                    "--only-binary=:all:", "--no-deps",
                    "--platform", plattform,
                    "--python-version", version,
                    "--implementation", "cp",
                    "--dest", str(ziel),
                    *pins, *WERKZEUGE,
                ],
                check=True,
            )


def ausleihe_bauen(ziel: Path) -> Path:
    """Baut das Rad von ``ausleihe-api`` nach ``ziel`` und gibt seinen Pfad zurück.

    Rein Python, ein Rad für alle Versionen. Die ``.env`` im Quellbaum kommt
    nicht mit: setuptools packt nur das Paket ``ausleihe`` ein
    (``packages.find`` dort), geprüft in ``tests/test_wheelhouse.py``.
    """
    if not (AUSLEIHE_QUELLE / "pyproject.toml").is_file():
        sys.exit(f"ausleihe-api nicht gefunden: {AUSLEIHE_QUELLE}")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["uv", "build", "--wheel", "--quiet", "--out-dir", tmp, str(AUSLEIHE_QUELLE)],
            check=True,
            env={**os.environ, "SOURCE_DATE_EPOCH": REPRODUZIERBAR},
        )
        (rad,) = Path(tmp).glob("*.whl")
        return Path(shutil.copy2(rad, ziel / rad.name))


def ausleihe_raeder(ordner: Path = ZIEL) -> list[Path]:
    praefix = AUSLEIHE_NAME.replace("-", "_") + "-"
    return sorted(ordner.glob(praefix + "*.whl"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--nur-ausleihe", action="store_true",
        help="nur das Rad von ausleihe-api neu bauen, nichts herunterladen",
    )
    if parser.parse_args().nur_ausleihe:
        for alt in ausleihe_raeder():
            alt.unlink()
        print(f"Gebaut: {ausleihe_bauen(ZIEL).name}")
        return
    # In einen frischen Ordner laden und erst dann tauschen: so bleiben keine
    # Räder alter Pins liegen, und ein abgebrochener Lauf lässt wheels/ intakt.
    with tempfile.TemporaryDirectory(dir=WURZEL) as tmp:
        neu = Path(tmp) / "wheels"
        neu.mkdir()
        herunterladen(neu)
        ausleihe_bauen(neu)
        if ZIEL.exists():
            shutil.rmtree(ZIEL)
        neu.rename(ZIEL)
    groesse = sum(p.stat().st_size for p in ZIEL.iterdir()) / 1e6
    print(f"{len(list(ZIEL.iterdir()))} Dateien, {groesse:.1f} MB in {ZIEL}")


if __name__ == "__main__":
    main()
