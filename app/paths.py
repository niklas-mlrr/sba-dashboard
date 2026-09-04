"""Plattformabhängiger Ordner für die Benutzerkonfiguration.

Der ausgelieferte Standard (``config.json`` im Repo-Wurzelverzeichnis) wird nie
beschrieben - Anpassungen der Lehrkraft (aktuell: der geprüfte Excel-Pfad)
landen in einer separaten, kleinen Datei außerhalb des Programmordners. Die
Wahl des Ortes folgt je Plattform der dortigen Konvention für genau diesen
Zweck, damit ein Update des Programmcodes (Git-Pull, Neukopie durch
``START.bat``) die Anpassungen der Lehrkraft nicht überschreibt:

* **Windows** - ``%LOCALAPPDATA%``: der von Microsoft vorgesehene Ort für
  rechner- und benutzerspezifische Anwendungsdaten ohne Roaming-Overhead.
  ``START.bat`` spiegelt den Programmcode ohnehin dorthin, der Ordner ist auf
  dem Schul-Laptop also garantiert beschreibbar.
* **macOS** - ``~/Library/Application Support/``: der von Apple vorgesehene
  Ort für Anwendungsdaten, die kein Nutzer von Hand im Finder anfassen soll.
* **Linux** - die XDG Base Directory Specification sieht ``$XDG_CONFIG_HOME``
  (Vorgabe, falls nicht gesetzt: ``~/.config``) für genau diesen Zweck vor.

Die Umgebungsvariable ``SBA_CONFIG_DIR`` überschreibt den Ordner auf jeder
Plattform. Tests setzen sie immer, damit nichts im echten Benutzerprofil
landet; wer das Dashboard von einem Wechseldatenträger aus benutzt, kann sie
ebenso nutzen, um den Ordner mitzunehmen.

Diese Datei bleibt bewusst frei von FastAPI- und openpyxl-Importen: die
Pfadauflösung ist reine Plattformlogik und soll ohne den Rest der Anwendung
importierbar und testbar sein.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ORDNERNAME = "sba-dashboard"


def benutzer_konfigurationsordner() -> Path:
    """Der Ordner für die Benutzerkonfiguration - muss nicht existieren."""
    override = os.environ.get("SBA_CONFIG_DIR")
    if override:
        return Path(override)

    if sys.platform == "win32":
        basis = os.environ.get("LOCALAPPDATA")
        if not basis:
            # Auf einem Laptop ohne die Variable (sehr alte Windows-Profile)
            # gilt derselbe Standardpfad, den Windows selbst dafür anlegt.
            basis = str(Path.home() / "AppData" / "Local")
        return Path(basis) / _ORDNERNAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _ORDNERNAME

    # Linux und alles andere Unix-artige: XDG Base Directory Specification.
    xdg = os.environ.get("XDG_CONFIG_HOME")
    basis = Path(xdg) if xdg else Path.home() / ".config"
    return basis / _ORDNERNAME


def benutzer_konfigurationspfad() -> Path:
    """Der vollständige Pfad zur config.json der Benutzerkonfiguration."""
    return benutzer_konfigurationsordner() / "config.json"
