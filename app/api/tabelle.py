"""Die Tabelle als JSON und die Änderung einer einzelnen Zahl.

Beide Routen enthalten keine Fehlerabbildung mehr: was ``lies_tabelle`` und
``schreibe_zelle`` an Ausnahmen werfen, beantwortet ``app/fehler.py`` - einmal
für die ganze Anwendung.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import cache as cache_modul
from ..excel import schreibe_zelle, sperrdatei
from ..modelle import ZellAnfrage
from ..rows import lies_tabelle, zeile_aus_eintrag
from .gemeinsam import aktuelle_einstellungen, keine_datei

router = APIRouter()


@router.get("/api/rows")
def api_rows(request: Request) -> JSONResponse:
    """Dieselben Zeilen wie ``GET /``, nur ohne HTML - für Tests und Diagnose."""
    einstellungen = aktuelle_einstellungen(request)
    stand = lies_tabelle(einstellungen)
    if stand is None:
        return keine_datei(einstellungen)
    return JSONResponse({
        "datei": str(stand.pfad),
        "mtime": stand.zustand.mtime,
        "geaendert": stand.zustand.geaendert.isoformat(timespec="seconds"),
        "stand": stand.cache.stand.isoformat(timespec="seconds") if stand.cache.stand else None,
        "cache_leer": stand.cache.leer,
        "in_excel_geoeffnet": sperrdatei(stand.pfad) is not None,
        "zeilen": [z.als_dict() for z in stand.zeilen],
    })


@router.post("/api/cell")
def api_cell(request: Request, anfrage: ZellAnfrage) -> JSONResponse:
    """Setzt genau eine Zahl - Zeilenschlüssel statt Zellbezug, mtime als Pflicht.

    Die vier Schutzschichten dahinter stehen in ``docs/architektur.md``; hier
    steht nur noch die Übersetzung von HTTP nach ``schreibe_zelle`` und zurück.

    Die geänderte Zeile geht fertig gerechnet mit zurück. Das ist der Grund,
    warum ``app/static/app.js`` fast keine Logik mehr braucht: der Browser
    setzt die Antwort ein, statt "zu bestellen" selbst nachzurechnen.
    """
    einstellungen = aktuelle_einstellungen(request)
    pfad = einstellungen.excel_pfad()
    if pfad is None:
        return keine_datei(einstellungen)

    ergebnis = schreibe_zelle(
        pfad,
        einstellungen.blatt_raster,
        key=anfrage.key,
        spalte=anfrage.spalte,
        wert=anfrage.wert,
        mtime=anfrage.mtime,
        backups_behalten=einstellungen.backups_behalten,
    )
    zeile = zeile_aus_eintrag(ergebnis.ws, ergebnis.eintrag, cache_modul.laden(pfad))
    return JSONResponse({
        "ok": True,
        "ref": ergebnis.ref,
        "mtime": ergebnis.zustand.mtime,
        "geaendert": ergebnis.zustand.geaendert.isoformat(timespec="seconds"),
        "backup": ergebnis.backup.name if ergebnis.backup else None,
        "zeile": zeile.als_dict(),
    })
