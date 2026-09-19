"""Der Reiter „Mehrjahresbände": eine Seite und drei API-Routen.

Die Seite (``GET /mehrjahresbaende``) liest die Exceldatei und braucht **keine**
Anmeldung - sie zeigt eine Entscheidung, die längst getroffen ist. Erst das
Erzeugen holt zwei Schuljahre aus IServ und braucht deshalb eine.

Wie ``GET /`` fängt die Seite ihre Fehler selbst ab und liefert HTML; die drei
API-Routen überlassen das ``app/fehler.py`` wie alle anderen auch.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from mehrjahresbaende.core import Uebersicht

from .. import mehrjahresbaende as domaene
from ..excel import UngueltigeAenderung, sperrdatei
from ..modelle import ErzeugenAnfrage, MarkenAnfrage
from ..settings import EinstellungsFehler
from .gemeinsam import aktuelle_einstellungen, vorlagen

router = APIRouter()


def _als_dict(uebersicht: Uebersicht) -> dict[str, Any]:
    """Die Übersicht als JSON - dieselben Namen wie in den Dataclasses."""
    return {
        "spalten": [
            {"fach": spalte.fach, "aufgabenfeld": spalte.aufgabenfeld}
            for spalte in uebersicht.spalten
        ],
        "zeilen": [
            {
                "jahrgang": zeile.jahrgang,
                "name": zeile.name,
                "hinweis": zeile.hinweis,
                "zellen": [
                    {
                        "fach": zelle.fach,
                        "marke": zelle.marke,
                        "buecher": [
                            {"isbn": buch.isbn, "titel": buch.titel, "ausgang": buch.ausgang}
                            for buch in zelle.buecher
                        ],
                    }
                    for zelle in zeile.zellen
                ],
            }
            for zeile in uebersicht.zeilen
        ],
        "legende": list(uebersicht.legende),
        "marken": list(uebersicht.erlaubte_marken),
        "herkunft": uebersicht.herkunft,
        "warnungen": list(uebersicht.warnungen),
    }


def _antwort(stand: domaene.Stand, **zusatz: object) -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "datei": str(stand.pfad),
        "mtime": stand.zustand.mtime,
        "geaendert": stand.zustand.geaendert.isoformat(timespec="seconds"),
        "uebersicht": _als_dict(stand.uebersicht),
        **zusatz,
    })


@router.get("/mehrjahresbaende")
def seite(request: Request) -> Response:
    """Die Matrix als Seite - oder der Hinweis, dass es sie noch nicht gibt."""
    werte: dict[str, Any] = {"reiter": "mehrjahresbaende"}
    try:
        einstellungen = aktuelle_einstellungen(request)
        stand = domaene.lies(einstellungen)
    except EinstellungsFehler as exc:
        return vorlagen.TemplateResponse(
            request, "fehler.html",
            {**werte, "titel": "Konfiguration", "meldung": str(exc),
             "ueberschrift": "Mehrjahresbände"},
            status_code=500,
        )
    except Exception as exc:  # noqa: BLE001 - eine kaputte Datei soll die Seite nicht abwürgen
        return vorlagen.TemplateResponse(
            request, "fehler.html",
            {**werte, "titel": "Datei nicht lesbar",
             "meldung": f"Die Mehrjahresbände-Datei ließ sich nicht lesen: {exc}",
             "ueberschrift": "Mehrjahresbände"},
            status_code=500,
        )

    pfad = einstellungen.mehrjahresbaende_pfad()
    return vorlagen.TemplateResponse(request, "mehrjahresbaende.html", {
        **werte,
        "uebersicht": stand.uebersicht if stand else None,
        "datei": stand.pfad if stand else pfad,
        "mtime": stand.zustand.mtime if stand else None,
        "in_excel_geoeffnet": bool(stand and sperrdatei(stand.pfad)),
    })


@router.get("/api/mehrjahresbaende")
def api_lesen(request: Request) -> JSONResponse:
    """Dieselbe Übersicht als JSON - für Tests und für die Seite nach dem Erzeugen."""
    stand = domaene.lies(aktuelle_einstellungen(request))
    if stand is None:
        return JSONResponse({"ok": True, "uebersicht": None, "mtime": None,
                             "fehler": None}, status_code=200)
    return _antwort(stand)


@router.post("/api/mehrjahresbaende/erzeugen")
async def api_erzeugen(request: Request, anfrage: ErzeugenAnfrage) -> JSONResponse:
    """Vergleicht zwei Schuljahre und schreibt die Datei neu.

    Läuft im Threadpool: beide Schuljahre sind je ein Dutzend HTTP-Anfragen an
    IServ, dazu die Aufgabenfelder von der Schulwebsite und das Schreiben der
    Mappe - nichts davon darf die Ereignisschleife blockieren.
    """
    einstellungen = aktuelle_einstellungen(request)
    client = request.app.state.anmeldung.client()
    try:
        stand = await run_in_threadpool(
            lambda: domaene.erzeuge(client, einstellungen,
                                    schuljahr=anfrage.schuljahr, vorjahr=anfrage.vorjahr)
        )
    except ValueError as exc:
        # Unbekanntes Schuljahr, unlesbare Datei, zu viele Sonderfälle: alles
        # Eingaben bzw. Zustände, an denen die Lehrkraft etwas ändern kann.
        raise UngueltigeAenderung(str(exc)) from exc
    except (EinstellungsFehler, OSError):
        raise
    except Exception as exc:  # noqa: BLE001 - jeder Netz- oder API-Fehler wird zur Meldung
        return JSONResponse(
            {"fehler": f"Die Bücherlisten konnten nicht geladen werden: {exc}"},
            status_code=502,
        )
    return _antwort(stand)


@router.post("/api/mehrjahresbaende/marke")
def api_marke(request: Request, anfrage: MarkenAnfrage) -> JSONResponse:
    """Setzt genau eine Zelle - mit dem beim Laden gesehenen Versionsstand."""
    einstellungen = aktuelle_einstellungen(request)
    stand, ref = domaene.schreibe_marke(
        einstellungen,
        jahrgang=anfrage.jahrgang,
        fach=anfrage.fach,
        marke=anfrage.marke.strip(),
        mtime=anfrage.mtime,
    )
    return _antwort(stand, ref=ref)
