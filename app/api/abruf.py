"""Start und Fortschritt des IServ-Abrufs.

Die Anmeldung passiert **synchron**, bevor geantwortet wird - nur an dieser
Stelle lässt sich "Passwort falsch" noch als 401 beantworten statt als Feld in
einem Statusobjekt, das niemand liest. Begründung in ``docs/architektur.md``.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..modelle import AbrufAnfrage
from ..refresh import fehlerabbildung, melde_an
from .gemeinsam import aktuelle_einstellungen, keine_datei

router = APIRouter()


@router.post("/api/refresh")
def api_refresh(request: Request, anfrage: AbrufAnfrage) -> JSONResponse:
    """Prüft die Zugangsdaten und startet den Hintergrundlauf. 202 bei Erfolg."""
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
    try:
        client = melde_an(
            einstellungen.iserv_domain,
            anfrage.benutzer,
            anfrage.passwort,
            client_factory=request.app.state.client_factory,
        )
    except Exception as exc:  # noqa: BLE001 - jede Anmeldeausnahme wird abgebildet
        code, meldung = fehlerabbildung(exc)
        return JSONResponse({"fehler": meldung}, status_code=code)
    finally:
        # Das Passwort war nur für diese eine Anmeldung da: es geht weder in
        # app.state noch in ein Log, eine Antwort, den Cache oder die Mappe
        # (tests/test_refresh.py prüft jede dieser Stellen). Das ``del`` ist
        # dabei ehrlicherweise eine Markierung und keine Garantie - FastAPI
        # hält das Modell bis zum Ende der Anfrage ohnehin selbst. Es steht
        # hier, damit ein späterer Zusatz unter dieser Zeile das Passwort nicht
        # versehentlich weiterreicht, sondern einen NameError bekommt.
        del anfrage

    # LaeuftBereits kann trotz der Prüfung oben noch fliegen: zwischen ihr und
    # hier liegt die Anmeldung bei IServ, also eine knappe Sekunde Netz.
    # app/fehler.py macht daraus 409 samt Status.
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
