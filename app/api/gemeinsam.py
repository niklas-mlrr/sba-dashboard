"""Was alle Router teilen: die Vorlagen, die Einstellungen, der Leerfall.

Bewusst drei kleine Dinge und kein "Utils"-Modul: alles andere gehört in die
Domänenmodule (``app/excel.py``, ``app/rows.py``, ``app/refresh.py``) oder in
genau einen Router.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from ..konfiguration import lade_einstellungen
from ..settings import Einstellungen

_APP = Path(__file__).resolve().parent.parent

# Eine Instanz für den ganzen Prozess: Jinja2Templates hält einen Cache der
# geparsten Vorlagen, und zwei App-Instanzen (zwei Fenster, jeder Test) sollen
# ihn sich teilen statt jede ihren eigenen aufzubauen.
vorlagen = Jinja2Templates(directory=str(_APP / "templates"))


def aktuelle_einstellungen(request: Request) -> Einstellungen:
    """Die Einstellungen dieser Anwendung - injiziert oder frisch geladen.

    ``app.state.einstellungen`` ist gesetzt, wenn ``create_app`` sie bekommen
    hat (Produktivstart, Tests). Bleibt es ``None``, wird bei jeder Anfrage
    nachgeladen - so wirkt eine von Hand geänderte ``config.json`` ohne
    Neustart.

    ``app.state.config_pfad`` bleibt dabei ``None``, wenn kein ``--config``
    angegeben wurde. Das unterscheidet den Arbeitskopie-Modus (genau eine
    Datei, kein Overlay) vom Produktivmodus (Standard + Benutzerkonfiguration)
    - ein Rückfall auf ``config.json`` an dieser Stelle würde das Overlay
    stillschweigend übergehen.
    """
    vorhanden = request.app.state.einstellungen
    if vorhanden is not None:
        return vorhanden
    return lade_einstellungen(request.app.state.config_pfad)


def keine_datei(einstellungen: Einstellungen) -> JSONResponse:
    """HTTP 503 samt der Liste der geprüften Pfade.

    Kein Fehlerfall im Sinne von ``app/fehler.py``, sondern der reguläre
    Zustand vor der Ersteinrichtung - deshalb eine Antwort und keine Ausnahme.
    Die geprüften Pfade gehören mit hinein: "keine Datei gefunden" ohne die
    Angabe, *wo* gesucht wurde, ist auf einem Netzlaufwerk nicht zu klären.
    """
    return JSONResponse(
        {"fehler": "Keine der eingetragenen Excel-Dateien wurde gefunden.",
         "geprueft": [str(p) for p, _ in einstellungen.gepruefte_pfade()]},
        status_code=503,
    )
