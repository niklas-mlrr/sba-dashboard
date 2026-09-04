"""FastAPI-Anwendung des Dashboards.

In dieser Ausbaustufe nur der **Lesepfad**: Tabelle rendern, Zeilen als JSON
ausliefern, Gesundheitsprüfung. Schreiben und der IServ-Abruf kommen als eigene
Schritte dazu (siehe docs/PLAN.md, Abschnitte 5 und 7).

Der Server hört ausschließlich auf 127.0.0.1 - die Mappe enthält
personenbezogene Zahlen und hat im Schulnetz nichts verloren.
"""
from __future__ import annotations

from pathlib import Path

from bestand.core import parse_grid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import cache as cache_modul
from .excel import BlattFehlt, Dateizustand, lade_mappe, raster_blatt, sperrdatei
from .rows import baue_zeilen
from .settings import Einstellungen, EinstellungsFehler

_HIER = Path(__file__).parent
_WURZEL = _HIER.parent

app = FastAPI(title="Schulbuchausleihe — Bestand")
app.mount("/static", StaticFiles(directory=_HIER / "static"), name="static")
templates = Jinja2Templates(directory=str(_HIER / "templates"))


def lade_einstellungen(pfad: Path | None = None) -> Einstellungen:
    return Einstellungen.laden(pfad or _WURZEL / "config.json")


def _einstellungen(request: Request) -> Einstellungen:
    """Einstellungen aus dem App-Zustand; im Test überschreibbar."""
    vorhanden = getattr(request.app.state, "einstellungen", None)
    return vorhanden if vorhanden is not None else lade_einstellungen()


def lies_tabelle(einstellungen: Einstellungen):
    """Mappe frisch laden, Raster parsen, Zeilen bauen. Kein Zustand bleibt übrig."""
    pfad = einstellungen.excel_pfad()
    if pfad is None:
        return None, [], None, None
    wb = lade_mappe(pfad)
    ws = raster_blatt(wb, einstellungen.blatt_raster)
    grid = parse_grid(ws)
    cache = cache_modul.laden(pfad)
    return pfad, baue_zeilen(ws, grid, cache), Dateizustand.von(pfad), cache


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/rows")
def api_rows(request: Request) -> JSONResponse:
    try:
        einstellungen = _einstellungen(request)
    except EinstellungsFehler as exc:
        return JSONResponse({"fehler": str(exc)}, status_code=500)

    try:
        pfad, zeilen, zustand, cache = lies_tabelle(einstellungen)
    except BlattFehlt as exc:
        return JSONResponse({"fehler": str(exc)}, status_code=500)
    if pfad is None:
        return JSONResponse(
            {"fehler": "Keine der eingetragenen Excel-Dateien wurde gefunden.",
             "geprueft": [str(p) for p, _ in einstellungen.geprüfte_pfade()]},
            status_code=503,
        )
    return JSONResponse({
        "datei": str(pfad),
        "mtime": zustand.mtime,
        "geaendert": zustand.geaendert.isoformat(timespec="seconds"),
        "stand": cache.stand.isoformat(timespec="seconds") if cache.stand else None,
        "cache_leer": cache.leer,
        "in_excel_geoeffnet": sperrdatei(pfad) is not None,
        "zeilen": [z.als_dict() for z in zeilen],
    })


@app.get("/")
def index(request: Request):
    try:
        einstellungen = _einstellungen(request)
    except EinstellungsFehler as exc:
        return templates.TemplateResponse(
            request, "fehler.html", {"titel": "Konfiguration", "meldung": str(exc)},
            status_code=500,
        )

    try:
        pfad, zeilen, zustand, cache = lies_tabelle(einstellungen)
    except BlattFehlt as exc:
        return templates.TemplateResponse(
            request, "fehler.html",
            {"titel": "Tabellenblatt fehlt", "meldung": str(exc)}, status_code=500,
        )

    if pfad is None:
        return templates.TemplateResponse(
            request, "fehler.html",
            {"titel": "Excel-Datei nicht gefunden",
             "meldung": "Unter keinem der eingetragenen Pfade liegt die Bestandsliste. "
                        "Bitte den richtigen Pfad in config.json eintragen.",
             "pfade": einstellungen.geprüfte_pfade()},
            status_code=503,
        )

    return templates.TemplateResponse(request, "index.html", {
        "zeilen": zeilen,
        "datei": pfad,
        "zustand": zustand,
        "cache": cache,
        "in_excel_geoeffnet": sperrdatei(pfad) is not None,
        "bedarf_gesamt": sum(z.zu_bestellen or 0 for z in zeilen if z.bedarf),
    })
