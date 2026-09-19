"""Die Buchplanung als API: lesen, abgleichen und fünf Arten einzutragen.

Es gibt hier **keine eigene Seite**. Eingetragen wird dort, wo die Bücher
ohnehin stehen - in der Verlags- und der Fach-Ansicht der Bücherlisten
(``app/api/buecherliste.py``). Diese Routen sind das, was die Knöpfe dort
aufrufen.

Gelesen wird ohne Anmeldung: die Datei liegt lokal, und ihr Stand ist eine
Entscheidung, keine Abfrage. Erst der Abgleich holt zwei Schuljahre aus IServ
und braucht deshalb eine Anmeldung.

Die Fehlerabbildung steht wie überall in ``app/fehler.py``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from buchplanung.core import (
    Buchplanung,
    fach_status,
    planungs_status,
    preis_status,
)

from .. import buchplanung as domaene
from ..modelle import (
    AbgleichAnfrage,
    FachbestaetigungAnfrage,
    PlanungsAnfrage,
    PreisAnfrage,
    RuecklageAnfrage,
    VerlagspreisAnfrage,
)
from ..settings import EinstellungsFehler
from .gemeinsam import aktuelle_einstellungen

router = APIRouter()


def _als_dict(stand: Buchplanung) -> dict[str, Any]:
    """Der Stand als JSON - die Status gerechnet, nicht aus der Datei gelesen.

    Die Oberfläche bekommt genau das, was sie anzeigt, und rechnet selbst
    nichts: welcher Preis als bestätigt gilt, entscheidet eine Stelle
    (``buchplanung/core/modelle.py``), nicht zusätzlich noch ein Skript.
    """
    buecher = []
    for buch in stand.buecher:
        status, hinweis = preis_status(buch, stand.pruefung(buch.isbn))
        pruefung = stand.pruefung(buch.isbn)
        buecher.append({
            "isbn": buch.isbn,
            "titel": buch.titel,
            "verlag": buch.verlag,
            "faecher": list(buch.faecher),
            "jahrgaenge": list(buch.jahrgaenge),
            "jahrgaenge_vorjahr": list(buch.jahrgaenge_vorjahr),
            "jahrgaenge_aktuell": list(buch.jahrgaenge_aktuell),
            "leihbar": buch.leihbar,
            "neupreis": buch.neupreis,
            "preis_status": status,
            "preis_hinweis": hinweis,
            "geprueft": None if pruefung is None else {
                "preis": pruefung.preis,
                "kuerzel": pruefung.kuerzel,
                "datum": pruefung.datum.isoformat() if pruefung.datum else None,
                "bemerkung": pruefung.bemerkung,
            },
            "planung": [
                {
                    "jahrgang": jahrgang,
                    "eingefuehrt_ab": zeile.eingefuehrt_ab if zeile else "",
                    "ausgemustert_nach": zeile.ausgemustert_nach if zeile else "",
                    "beschluss": zeile.beschluss if zeile else "",
                    "bemerkung": zeile.bemerkung if zeile else "",
                    "herkunft": stand.herkunft(buch, jahrgang),
                    "status": planungs_status(zeile, stand.schuljahr),
                }
                for jahrgang in stand.jahrgaenge
                if jahrgang in buch.jahrgaenge or stand.planungszeile(buch.isbn, jahrgang)
                for zeile in (stand.planungszeile(buch.isbn, jahrgang),)
            ],
            "ruecklagen": [
                {
                    "fach": eintrag.fach,
                    "anzahl": eintrag.anzahl,
                    "status": eintrag.status,
                    "kuerzel": eintrag.kuerzel,
                    "datum": eintrag.datum.isoformat() if eintrag.datum else None,
                    "bemerkung": eintrag.bemerkung,
                }
                for eintrag in stand.ruecklagen if eintrag.isbn == buch.isbn
            ],
        })

    faecher = []
    for fach in stand.faecher:
        eintrag = stand.bestaetigung(fach)
        status, hinweis = fach_status(fach, stand.buecher_je_fach(fach), eintrag)
        faecher.append({
            "fach": fach,
            "status": status,
            "hinweis": hinweis,
            "kuerzel": eintrag.kuerzel if eintrag else "",
            "datum": eintrag.datum.isoformat() if eintrag and eintrag.datum else None,
            "bemerkung": eintrag.bemerkung if eintrag else "",
        })

    return {
        "schuljahr": stand.schuljahr,
        "vorjahr": stand.vorjahr,
        "stand": stand.stand.isoformat() if stand.stand else None,
        "buecher": buecher,
        "faecher": faecher,
        "verlage": list(stand.verlage),
        "warnungen": list(stand.warnungen),
    }


def _antwort(stand: domaene.Stand, **zusatz: object) -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "datei": str(stand.pfad),
        "mtime": stand.zustand.mtime,
        "geaendert": stand.zustand.geaendert.isoformat(timespec="seconds"),
        "planung": _als_dict(stand.planung),
        **zusatz,
    })


@router.get("/api/buchplanung")
def api_lesen(request: Request, schuljahr: str) -> JSONResponse:
    """Der gespeicherte Stand eines Schuljahrs; ohne Datei ``planung: null``."""
    stand = domaene.lies(aktuelle_einstellungen(request), schuljahr)
    if stand is None:
        return JSONResponse({"ok": True, "planung": None, "mtime": None, "datei": None})
    return _antwort(stand)


@router.post("/api/buchplanung/abgleich")
async def api_abgleich(request: Request, anfrage: AbgleichAnfrage) -> JSONResponse:
    """Holt beide Schuljahre aus IServ und schreibt die Datei neu.

    Läuft im Threadpool: zwei Schuljahre sind je ein Dutzend HTTP-Anfragen an
    IServ, dazu das Schreiben der Mappe - nichts davon darf die
    Ereignisschleife blockieren.
    """
    einstellungen = aktuelle_einstellungen(request)
    client = request.app.state.anmeldung.client()
    try:
        stand = await run_in_threadpool(
            lambda: domaene.gleiche_ab(client, einstellungen,
                                       schuljahr=anfrage.schuljahr, vorjahr=anfrage.vorjahr)
        )
    except (EinstellungsFehler, OSError):
        raise
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 - jeder Netz- oder API-Fehler wird zur Meldung
        return JSONResponse(
            {"fehler": f"Die Bücherlisten konnten nicht geladen werden: {exc}"},
            status_code=502,
        )
    return _antwort(stand)


@router.post("/api/buchplanung/preis")
def api_preis(request: Request, anfrage: PreisAnfrage) -> JSONResponse:
    """Der geprüfte Preis eines Buchs."""
    stand = domaene.schreibe_preis(
        aktuelle_einstellungen(request),
        schuljahr=anfrage.schuljahr, isbn=anfrage.isbn, preis=anfrage.preis,
        kuerzel=anfrage.kuerzel, datum=anfrage.datum, bemerkung=anfrage.bemerkung,
        mtime=anfrage.mtime,
    )
    return _antwort(stand)


@router.post("/api/buchplanung/preise")
def api_preise(request: Request, anfrage: VerlagspreisAnfrage) -> JSONResponse:
    """Alle Preise eines Verlags auf einmal - der Knopf neben dem Drucker."""
    stand, anzahl = domaene.schreibe_preise_des_verlags(
        aktuelle_einstellungen(request),
        schuljahr=anfrage.schuljahr, verlag=anfrage.verlag,
        kuerzel=anfrage.kuerzel, datum=anfrage.datum, mtime=anfrage.mtime,
    )
    return _antwort(stand, bestaetigt=anzahl)


@router.post("/api/buchplanung/fach")
def api_fach(request: Request, anfrage: FachbestaetigungAnfrage) -> JSONResponse:
    """Die Freigabe einer Fach-Bücherliste durch die Fachkonferenzleitung."""
    stand = domaene.schreibe_fachbestaetigung(
        aktuelle_einstellungen(request),
        schuljahr=anfrage.schuljahr, fach=anfrage.fach, kuerzel=anfrage.kuerzel,
        datum=anfrage.datum, bemerkung=anfrage.bemerkung, mtime=anfrage.mtime,
    )
    return _antwort(stand)


@router.post("/api/buchplanung/planung")
def api_planung(request: Request, anfrage: PlanungsAnfrage) -> JSONResponse:
    """Einführung und Ausmusterung eines Buchs in einem Jahrgang."""
    stand = domaene.schreibe_planung(
        aktuelle_einstellungen(request),
        schuljahr=anfrage.schuljahr, isbn=anfrage.isbn, jahrgang=anfrage.jahrgang,
        eingefuehrt_ab=anfrage.eingefuehrt_ab, ausgemustert_nach=anfrage.ausgemustert_nach,
        beschluss=anfrage.beschluss, bemerkung=anfrage.bemerkung, mtime=anfrage.mtime,
    )
    return _antwort(stand)


@router.post("/api/buchplanung/ruecklage")
def api_ruecklage(request: Request, anfrage: RuecklageAnfrage) -> JSONResponse:
    """Wie viele Exemplare eine Fachschaft behalten möchte."""
    stand = domaene.schreibe_ruecklage(
        aktuelle_einstellungen(request),
        schuljahr=anfrage.schuljahr, isbn=anfrage.isbn, fach=anfrage.fach,
        anzahl=anfrage.anzahl, status=anfrage.status, kuerzel=anfrage.kuerzel,
        datum=anfrage.datum, bemerkung=anfrage.bemerkung, mtime=anfrage.mtime,
    )
    return _antwort(stand)
