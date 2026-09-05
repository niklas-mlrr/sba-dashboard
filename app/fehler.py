"""Ausnahme → HTTP: einmal registriert statt in jeder Route wiederholt.

Bis 2026-09-05 bildete ``app/main.py`` dieselben Ausnahmen in jeder Route
erneut ab. Das waren rund sechzig Zeilen ``except``-Blöcke, und der Wortlaut
driftete von Route zu Route: ``BlattFehlt`` ergab im Lesepfad 500, im
Schreibpfad 503, und auf die Frage "welchen Code gibt eigentlich ``Gesperrt``?"
gab es je nach Datei eine andere Antwort. Die Tabelle unten ist jetzt die
einzige Antwort.

Warum das überhaupt geht: die Ausnahmen kommen aus ``app/excel.py``,
``app/refresh.py`` und ``app/settings.py`` - Modulen ohne jeden FastAPI-Import.
Sie beschreiben, *was* schiefging (die Mappe ist offen, der Stand ist veraltet),
nicht *wie* man darauf antwortet. Genau deshalb lässt sich das Wie einmal
zentral festlegen.

| Ausnahme              | Status | zusätzlich im Körper |
|-----------------------|--------|----------------------|
| ``MappeUngeeignet``   | 400    | -                    |
| ``UngueltigeAenderung``| 400   | -                    |
| ``RequestValidationError`` | 400 | -                 |
| ``Konflikt``          | 409    | ``mtime``            |
| ``LaeuftBereits``     | 409    | ``status``           |
| ``Gesperrt``          | 423    | ``benutzer``         |
| ``EinstellungsFehler``| 500    | -                    |
| ``BlattFehlt``        | 500    | -                    |
| ``ExcelFehlt``        | 503    | -                    |

Jede Antwort hat denselben Aufbau ``{"fehler": "<deutscher Klartext>"}``, weil
``app/static/app.js`` genau dieses Feld wörtlich anzeigt.

**Eine Ausnahme von der Ausnahmebehandlung:** ``GET /`` liefert HTML, kein
JSON. Eine Lehrkraft, die die Startseite aufruft, bekommt bei einem Konfigura-
tionsfehler eine Fehlerseite und nicht drei Zeilen JSON im Browserfenster.
Diese Route fängt ihre Fehler deshalb weiterhin selbst; sie ist der einzige
Ort, an dem das noch vorkommt, und das steht dort auch so.
"""
from __future__ import annotations

from typing import Any, Sequence

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .excel import (
    BlattFehlt,
    ExcelFehlt,
    Gesperrt,
    Konflikt,
    MappeUngeeignet,
    UngueltigeAenderung,
)
from .modelle import KOERPER_UNBRAUCHBAR, MELDUNGEN
from .refresh import LaeuftBereits
from .settings import EinstellungsFehler


def _text(exc: Exception) -> str:
    """Der Klartext einer Ausnahme - auch wenn sie von ``KeyError`` erbt.

    ``BlattFehlt`` ist ein ``KeyError``, und dessen ``__str__`` liefert das
    *repr* seines Arguments: aus der Meldung ``Tabellenblatt 'X' fehlt`` würde
    ohne diesen Umweg ``"Tabellenblatt 'X' fehlt"`` **mit** Anführungszeichen.
    """
    if isinstance(exc, KeyError) and exc.args:
        return str(exc.args[0])
    return str(exc)


def _antwort(exc: Exception, code: int, /, **zusatz: object) -> JSONResponse:
    """Die Standardantwort. ``zusatz`` sind die Felder, die eine Ausnahme mitbringt.

    Der Parameter heißt ``code`` und ist positionsgebunden (``/``), weil
    ``LaeuftBereits`` ein Feld namens ``status`` in den Körper legt - hieße der
    Parameter so, bekäme er beim Aufruf zwei Werte und die Route stürzte ab.
    Genau das ist hier passiert und mypy hat es gefunden, bevor es jemand am
    Schul-Laptop tat.
    """
    return JSONResponse({"fehler": _text(exc), **zusatz}, status_code=code)


def validierungsmeldung(fehlerliste: Sequence[Any]) -> str:
    """Pydantics Fehlerliste auf **einen** deutschen Satz abbilden.

    Es wird bewusst nur der erste zuordenbare Fehler gemeldet und nicht die
    ganze Liste: die Oberfläche hat für jede Anfrage genau eine Zeile Platz,
    und "Bitte IServ-Benutzername und Passwort eingeben." ist für beide
    fehlenden Felder derselbe richtige Satz.

    Was hier **nicht** hineinläuft: der eingegebene Wert. Pydantic legt ihn in
    jedem Fehlereintrag unter ``input`` ab - bei ``POST /api/refresh`` wäre das
    das Passwort. Es verlässt den Prozess nirgends (``tests/test_refresh.py``
    prüft das für jede Antwort), und dieser Handler ist genau die Stelle, an
    der es aus Versehen doch passieren könnte.
    """
    for fehler in fehlerliste:
        stelle = fehler.get("loc") or ()
        # loc ist ("body", "<feld>") - oder nur ("body",), wenn der Körper als
        # Ganzes unbrauchbar ist (kein JSON, ein Array statt eines Objekts).
        for teil in reversed(stelle):
            if isinstance(teil, str) and teil in MELDUNGEN:
                return MELDUNGEN[teil]
    return KOERPER_UNBRAUCHBAR


def registriere(application: FastAPI) -> None:
    """Hängt alle Handler an eine Anwendung. Aufgerufen von ``create_app``."""

    @application.exception_handler(MappeUngeeignet)
    async def _mappe_ungeeignet(request: Request, exc: MappeUngeeignet) -> JSONResponse:
        return _antwort(exc, 400)

    @application.exception_handler(UngueltigeAenderung)
    async def _ungueltige_aenderung(request: Request, exc: UngueltigeAenderung) -> JSONResponse:
        return _antwort(exc, 400)

    @application.exception_handler(RequestValidationError)
    async def _validierung(request: Request, exc: RequestValidationError) -> JSONResponse:
        # 400 statt FastAPIs 422: der handgeschriebene Vorgänger antwortete so,
        # die Oberfläche unterscheidet die beiden nicht, und ein einziger Code
        # für "die Anfrage taugt nicht" ist leichter zu erklären.
        return JSONResponse({"fehler": validierungsmeldung(exc.errors())}, status_code=400)

    @application.exception_handler(Konflikt)
    async def _konflikt(request: Request, exc: Konflikt) -> JSONResponse:
        # mtime mitgeben: der Browser kann damit ohne zweite Anfrage neu
        # aufsetzen (app.js lädt die Seite neu).
        return _antwort(exc, 409, mtime=exc.aktuelle_mtime)

    @application.exception_handler(LaeuftBereits)
    async def _laeuft_bereits(request: Request, exc: LaeuftBereits) -> JSONResponse:
        return _antwort(exc, 409, status=request.app.state.refresh_manager.status())

    @application.exception_handler(Gesperrt)
    async def _gesperrt(request: Request, exc: Gesperrt) -> JSONResponse:
        return _antwort(exc, 423, benutzer=exc.benutzer)

    @application.exception_handler(EinstellungsFehler)
    async def _einstellungsfehler(request: Request, exc: EinstellungsFehler) -> JSONResponse:
        return _antwort(exc, 500)

    @application.exception_handler(BlattFehlt)
    async def _blatt_fehlt(request: Request, exc: BlattFehlt) -> JSONResponse:
        return _antwort(exc, 500)

    @application.exception_handler(ExcelFehlt)
    async def _excel_fehlt(request: Request, exc: ExcelFehlt) -> JSONResponse:
        return _antwort(exc, 503)
