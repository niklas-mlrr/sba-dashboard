"""Plattformabhängige Ordner: Benutzerkonfiguration und lokaler Cache-Rückfallort.

Der ausgelieferte Standard (``config.json`` im Repo-Wurzelverzeichnis) wird nie
beschrieben - Anpassungen der Lehrkraft (aktuell: der geprüfte Excel-Pfad)
landen in einer separaten, kleinen Datei außerhalb des Programmordners. Der
Sidecar-Cache (``app/cache.py``) braucht aus einem anderen Grund einen
zweiten, rein lokalen Ort: das Gruppenlaufwerk, auf dem der eigentliche
Sidecar liegt, kann schreibgeschützt oder kurz nicht erreichbar sein. Beide
Fälle lösen dieselbe Frage - "welcher Ordner gehört auf dieser Plattform
diesem Rechner und diesem Benutzer allein" - nur für zwei verschiedene
Zwecke, und die XDG Base Directory Specification trennt Konfiguration und
Cache absichtlich (``XDG_CONFIG_HOME`` vs. ``XDG_CACHE_HOME``; unter
Windows/macOS landet der Cache zusätzlich in einer eigenen ``cache``-
Unterebene). Deshalb bleiben es zwei öffentliche Funktionen mit eigenem
Namen - aber ein gemeinsamer privater Kern (:func:`_plattformordner`) sorgt
dafür, dass beide dieselbe Plattformerkennung und denselben Ordnernamen
verwenden, statt wie bis 2026-09-05 zwei fast wortgleiche, aber leicht
unterschiedlich geschriebene Implementierungen zu pflegen (``app/cache.py``
benutzte ``platform.system()`` mit den Werten ``"Windows"``/``"Darwin"``,
diese Datei ``sys.platform`` mit ``"win32"``/``"darwin"`` - siehe Kommentar
bei ``_plattformordner`` unten für die Entscheidung).

Die Wahl des Ortes folgt je Plattform der dortigen Konvention für genau diesen
Zweck, damit ein Update des Programmcodes (Git-Pull, Neukopie durch
``START.bat``) die Anpassungen der Lehrkraft nicht überschreibt:

* **Windows** - ``%LOCALAPPDATA%``: der von Microsoft vorgesehene Ort für
  rechner- und benutzerspezifische Anwendungsdaten ohne Roaming-Overhead.
  ``START.bat`` spiegelt den Programmcode ohnehin dorthin, der Ordner ist auf
  dem Schul-Laptop also garantiert beschreibbar.
* **macOS** - ``~/Library/Application Support/``: der von Apple vorgesehene
  Ort für Anwendungsdaten, die kein Nutzer von Hand im Finder anfassen soll.
* **Linux** - die XDG Base Directory Specification sieht ``$XDG_CONFIG_HOME``
  (Vorgabe, falls nicht gesetzt: ``~/.config``) bzw. ``$XDG_CACHE_HOME``
  (Vorgabe: ``~/.cache``) für genau diesen Zweck vor.

Die Umgebungsvariablen ``SBA_CONFIG_DIR`` bzw. ``SBA_CACHE_DIR`` überschreiben
den jeweiligen Ordner **komplett** (nicht nur die plattformabhängige Wurzel)
auf jeder Plattform. Tests setzen sie immer, damit nichts im echten
Benutzerprofil landet; wer das Dashboard von einem Wechseldatenträger aus
benutzt, kann sie ebenso nutzen, um den Ordner mitzunehmen.

Diese Datei bleibt bewusst frei von FastAPI- und openpyxl-Importen: die
Pfadauflösung ist reine Plattformlogik und soll ohne den Rest der Anwendung
importierbar und testbar sein.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ORDNERNAME = "sba-dashboard"


def _plattformordner(
    *, override_env: str, xdg_env: str, xdg_vorgabe_name: str, unterordner: str | None,
) -> Path:
    """Gemeinsamer Kern für Konfigurations- und Cache-Ordner - nur die Details je Zweck sind Parameter.

    Plattformerkennung: ``sys.platform`` (Werte ``"win32"``/``"darwin"``/sonst),
    nicht ``platform.system()`` (Werte ``"Windows"``/``"Darwin"``/sonst) - beide
    Module beantworten dieselbe Frage, aber mit anderer Schreibweise der
    Ergebnisse. Vor der Zusammenlegung am 2026-09-05 benutzte diese Datei
    bereits ``sys.platform`` (und die bestehenden Tests in
    ``tests/test_benutzerkonfiguration.py`` patchen genau das, ``sys.platform``,
    nicht ``platform.system``), während ``app/cache.py`` unabhängig davon
    ``platform.system()`` verwendet hatte. Die Wahl fiel deshalb auf
    ``sys.platform``, um die bestehenden Tests unverändert zu lassen; eine
    künftige Suche nach ``platform.system() == "Windows"`` findet also nichts
    mehr in dieser Datei - das ist beabsichtigt und keine vergessene Stelle.

    ``unterordner`` hängt (falls gesetzt) unter Windows und macOS eine weitere
    Ebene an - der Cache braucht sie (``.../sba-dashboard/cache``), die
    Konfiguration nicht. Unter Linux/XDG braucht auch der Cache keine eigene
    Unterebene, weil ``XDG_CACHE_HOME``/``~/.cache`` selbst schon die
    Cache-Wurzel ist - dort unterscheiden sich Konfiguration und Cache allein
    durch die verwendete Umgebungsvariable.
    """
    override = os.environ.get(override_env)
    if override:
        return Path(override)

    if sys.platform == "win32":
        basis = os.environ.get("LOCALAPPDATA")
        if not basis:
            # Auf einem Laptop ohne die Variable (sehr alte Windows-Profile)
            # gilt derselbe Standardpfad, den Windows selbst dafür anlegt.
            basis = str(Path.home() / "AppData" / "Local")
        ordner = Path(basis) / _ORDNERNAME
        return ordner / unterordner if unterordner else ordner

    if sys.platform == "darwin":
        ordner = Path.home() / "Library" / "Application Support" / _ORDNERNAME
        return ordner / unterordner if unterordner else ordner

    # Linux und alles andere Unix-artige: XDG Base Directory Specification.
    xdg = os.environ.get(xdg_env)
    basis = Path(xdg) if xdg else Path.home() / xdg_vorgabe_name
    return basis / _ORDNERNAME


def benutzer_konfigurationsordner() -> Path:
    """Der Ordner für die Benutzerkonfiguration - muss nicht existieren."""
    return _plattformordner(
        override_env="SBA_CONFIG_DIR",
        xdg_env="XDG_CONFIG_HOME",
        xdg_vorgabe_name=".config",
        unterordner=None,
    )


def benutzer_konfigurationspfad() -> Path:
    """Der vollständige Pfad zur config.json der Benutzerkonfiguration."""
    return benutzer_konfigurationsordner() / "config.json"


def lokaler_cache_ordner() -> Path:
    """Rückfallort des Sidecar-Caches, falls das Gruppenlaufwerk nicht schreibbar ist.

    ``SBA_CACHE_DIR`` ersetzt den kompletten Ordner - nicht nur die Wurzel -,
    damit Tests gefahrlos in ein ``tmp_path``-Verzeichnis schreiben können,
    statt in das echte Benutzerprofil. Bis 2026-09-05 stand diese Funktion als
    ``_lokaler_cache_ordner`` in ``app/cache.py`` und benutzte dort
    ``platform.system()`` statt ``sys.platform`` - siehe die Begründung des
    Wechsels bei :func:`_plattformordner`.
    """
    return _plattformordner(
        override_env="SBA_CACHE_DIR",
        xdg_env="XDG_CACHE_HOME",
        xdg_vorgabe_name=".cache",
        unterordner="cache",
    )
