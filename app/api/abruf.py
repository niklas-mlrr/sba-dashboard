"""Anmeldung, Start und Fortschritt des IServ-Abrufs.

Die Anmeldung passiert **synchron** in ihrer eigenen Route, bevor geantwortet
wird - nur so lässt sich "Passwort falsch" noch als 401 beantworten statt als
Feld in einem Statusobjekt, das niemand liest. Begründung in
``docs/architektur.md``.

Bis 2026-09-10 brachte **jeder** Abruf seine Zugangsdaten im Körper mit, und der
Browser fragte sie jedes Mal neu ab. Angemeldet wird jetzt einmal im
Programmfenster; ``POST /api/refresh`` nimmt deshalb keinen Körper mehr und holt
den angemeldeten Client aus ``app.state.anmeldung`` (siehe ``app/sitzung.py``).

Dass die Anmeldung eine **HTTP-Route** ist und kein Methodenaufruf, ist
Absicht: das Fenster ist damit ein Client wie der Browser, und die Testsuite
prüft das ganze Verhalten ohne eine Zeile tkinter.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..modelle import AnmeldeAnfrage
from ..refresh import fehlerabbildung
from .gemeinsam import aktuelle_einstellungen, keine_datei

router = APIRouter()


@router.post("/api/anmeldung")
def api_anmeldung(request: Request, anfrage: AnmeldeAnfrage) -> JSONResponse:
    """Meldet bei IServ an und behält die Anmeldung für die Laufzeit. 200 bei Erfolg."""
    einstellungen = aktuelle_einstellungen(request)
    anmeldung = request.app.state.anmeldung
    try:
        anmeldung.anmelden(
            einstellungen,
            anfrage.benutzer,
            anfrage.passwort,
            client_factory=request.app.state.client_factory,
        )
    except Exception as exc:  # noqa: BLE001 - jede Anmeldeausnahme wird abgebildet
        code, meldung = fehlerabbildung(exc)
        return JSONResponse({"fehler": meldung}, status_code=code)
    finally:
        # Das Passwort geht von hier ausschließlich in den IServ-Client, der es
        # für eine spätere Neuanmeldung selbst braucht (app/sitzung.py erklärt,
        # warum das unvermeidlich ist). Es geht nicht in app.state, nicht in ein
        # Log, nicht in eine Antwort, nicht in den Cache und nicht in die Mappe;
        # tests/test_refresh.py und tests/test_sitzung.py prüfen jede dieser
        # Stellen. Das ``del`` ist dabei ehrlicherweise eine Markierung und
        # keine Garantie - FastAPI hält das Modell bis zum Ende der Anfrage
        # ohnehin selbst. Es steht hier, damit ein späterer Zusatz unter dieser
        # Zeile das Passwort nicht versehentlich weiterreicht, sondern einen
        # NameError bekommt.
        del anfrage
    return JSONResponse(anmeldung.status())


@router.get("/api/anmeldung")
def api_anmeldung_status(request: Request) -> JSONResponse:
    """Wer angemeldet ist und wann die Anmeldung verfällt. Nie das Passwort.

    Zählt bewusst **nicht** als Benutzung: der Fenster-Timer ruft das alle paar
    Sekunden auf, und ein offenes Fenster ist keine Arbeit an der Mappe. Würde
    diese Route das Zeitschloss zurücksetzen, liefe es nie ab.
    """
    return JSONResponse(request.app.state.anmeldung.status())


@router.delete("/api/anmeldung")
def api_abmelden(request: Request) -> JSONResponse:
    """Verwirft die Anmeldung - der Knopf "Abmelden" im Programmfenster."""
    anmeldung = request.app.state.anmeldung
    anmeldung.abmelden()
    return JSONResponse(anmeldung.status())


@router.post("/api/refresh")
def api_refresh(request: Request) -> JSONResponse:
    """Startet den Hintergrundlauf mit der bestehenden Anmeldung. 202 bei Erfolg.

    Nimmt keinen Körper. Fehlt die Anmeldung oder ist sie verfallen, wirft
    ``Anmeldung.client()`` - und ``app/fehler.py`` macht daraus 401 samt dem
    Hinweis aufs Programmfenster.
    """
    einstellungen = aktuelle_einstellungen(request)
    if einstellungen.excel_pfad() is None:
        return keine_datei(einstellungen)

    manager = request.app.state.refresh_manager
    if manager.laeuft():
        return JSONResponse(
            {"fehler": "Es läuft bereits ein Abruf. Bitte warten, bis er fertig ist.",
             "status": manager.status()},
            status_code=409,
        )
    client = request.app.state.anmeldung.client()

    # LaeuftBereits kann trotz der Prüfung oben noch fliegen: zwei Anfragen
    # dicht hintereinander. app/fehler.py macht daraus 409 samt Status.
    job_id = manager.starte(einstellungen, client)
    return JSONResponse({"job_id": job_id, "status": manager.status()}, status_code=202)


@router.get("/api/refresh/status")
def api_refresh_status(request: Request) -> JSONResponse:
    """Der Stand des letzten Laufs. Immer 200 - eine Abfrage, kein zweiter Versuch.

    ``RefreshManager.status()`` liefert auch vor dem ersten Lauf ein
    vollständiges Dict (``Lauf.ohne_lauf()``). Die Unterscheidung "lief schon"
    gegen "noch nie gelaufen" ist Refresh-Domänenwissen und steht dort.
    """
    return JSONResponse(request.app.state.refresh_manager.status())
