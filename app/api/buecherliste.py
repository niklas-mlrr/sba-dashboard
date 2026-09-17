"""Die Bücherlisten-Seiten hinter dem Reiter "Bücherliste".

Wie ``GET /`` fangen diese Routen ihre Fehler selbst ab und liefern HTML: wer
im Menü auf "Fach" klickt und nicht angemeldet ist, soll einen Satz lesen, was
zu tun ist - kein JSON aus ``app/fehler.py``.
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Request
from starlette.responses import Response

from ..buecherlisten import (
    Buecherlisten,
    finde_gruppe,
    gruppen_nach_fach,
    gruppen_nach_verlag,
    lade_buecherlisten,
)
from ..sitzung import Abgelaufen, NichtAngemeldet
from .gemeinsam import vorlagen

router = APIRouter()

# Ansicht -> (Überschrift, Gruppierung). Jahrgang hat keine Gruppierung, weil
# seine Zeilen die IServ-Listen selbst sind.
_ANSICHTEN: dict[str, tuple[str, Callable[[Buecherlisten], Any] | None]] = {
    "fach": ("Fach", gruppen_nach_fach),
    "verlag": ("Verlag", gruppen_nach_verlag),
    "jahrgang": ("Jahrgang", None),
}


def _seite(request: Request, vorlage: str, werte: dict, status: int = 200) -> Response:
    return vorlagen.TemplateResponse(
        request, vorlage, {"reiter": "buecherliste", **werte}, status_code=status,
    )


def _hinweis(request: Request, titel: str, meldung: str, status: int) -> Response:
    return _seite(request, "fehler.html",
                  {"titel": titel, "meldung": meldung, "ueberschrift": "Bücherliste"}, status)


def _laden(request: Request) -> Buecherlisten | Response:
    try:
        client = request.app.state.anmeldung.client()
    except (NichtAngemeldet, Abgelaufen) as exc:
        return _hinweis(
            request, "Nicht angemeldet",
            f"{exc} Die Bücherlisten werden live aus IServ geladen; "
            "danach diese Seite neu laden.", 401,
        )
    try:
        return lade_buecherlisten(client)
    except Exception as exc:  # noqa: BLE001 - jeder Netz- oder API-Fehler wird zur Seite
        return _hinweis(
            request, "IServ nicht erreichbar",
            f"Die Bücherlisten konnten nicht geladen werden: {exc}", 502,
        )


def _unbekannte_ansicht(request: Request, ansicht: str) -> Response:
    return _hinweis(request, "Unbekannte Ansicht", f"Es gibt keine Ansicht „{ansicht}“.", 404)


@router.get("/buecherliste/{ansicht}")
def uebersicht(request: Request, ansicht: str) -> Response:
    if ansicht not in _ANSICHTEN:
        return _unbekannte_ansicht(request, ansicht)
    daten = _laden(request)
    if isinstance(daten, Response):
        return daten
    name, gruppierung = _ANSICHTEN[ansicht]
    return _seite(request, "buecherliste_uebersicht.html", {
        "ansicht": ansicht,
        "ansicht_name": name,
        "schuljahr": daten.schuljahr,
        "listen": daten.listen,
        "gruppen": gruppierung(daten) if gruppierung else (),
    })


@router.get("/buecherliste/{ansicht}/{name:path}")
def gruppe(request: Request, ansicht: str, name: str) -> Response:
    if ansicht not in _ANSICHTEN:
        return _unbekannte_ansicht(request, ansicht)
    daten = _laden(request)
    if isinstance(daten, Response):
        return daten
    ansicht_name, gruppierung = _ANSICHTEN[ansicht]
    werte: dict[str, Any] = {
        "ansicht": ansicht, "ansicht_name": ansicht_name, "schuljahr": daten.schuljahr,
    }
    if gruppierung is None:
        liste = daten.liste_fuer_jahrgang(int(name)) if name.isdigit() else None
        if liste is None:
            return _hinweis(request, "Nicht gefunden",
                            f"Für Jahrgang „{name}“ gibt es keine Bücherliste.", 404)
        return _seite(request, "buecherliste_gruppe.html",
                      {**werte, "titel": liste.titel, "liste": liste})
    gefunden = finde_gruppe(gruppierung(daten), name)
    if gefunden is None:
        return _hinweis(request, "Nicht gefunden",
                        f"„{name}“ kommt in keiner Bücherliste vor.", 404)
    return _seite(request, "buecherliste_gruppe.html",
                  {**werte, "titel": gefunden.name, "gruppe": gefunden})
