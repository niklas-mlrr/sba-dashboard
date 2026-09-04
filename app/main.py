"""FastAPI-Anwendung des Dashboards.

Drei Wege durch dieselbe Mappe:

* **Lesen** - ``GET /`` und ``GET /api/rows`` laden die Datei frisch, parsen das
  Raster und rendern eine flache Tabelle.
* **Ändern** - ``POST /api/cell`` schreibt genau eine Zahl in genau eine Zelle,
  aufgelöst über den Zeilenschlüssel, nie über einen freien Zellbezug.
* **Abrufen** - ``POST /api/refresh`` holt den Stand aus IServ und schreibt ihn
  in die Mappe. Ein Hintergrundlauf, Fortschritt über ``/api/refresh/status``.

Der Server hört ausschließlich auf 127.0.0.1 - die Mappe enthält
personenbezogene Zahlen und hat im Schulnetz nichts verloren.
"""
from __future__ import annotations

from pathlib import Path

from bestand.core import parse_grid
from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import cache as cache_modul
from . import refresh as refresh_modul
from .excel import (
    SCHREIBBARE_SPALTEN,
    BlattFehlt,
    Dateizustand,
    ExcelFehlt,
    Gesperrt,
    Konflikt,
    UngueltigeAenderung,
    lade_mappe,
    raster_blatt,
    schreibe_zelle,
    sperr_benutzer,
    sperrdatei,
)
from .rows import baue_zeilen, zeile_aus_eintrag
from .settings import Einstellungen, EinstellungsFehler, speichere_excel_pfad

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


def _client_factory(request: Request):
    """Wie ein IServ-Client gebaut wird; im Test durch einen Fake ersetzt."""
    return getattr(request.app.state, "client_factory", None)


def _config_pfad(request: Request) -> Path:
    return getattr(request.app.state, "config_pfad", _WURZEL / "config.json")


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


def _keine_datei(einstellungen: Einstellungen) -> JSONResponse:
    return JSONResponse(
        {"fehler": "Keine der eingetragenen Excel-Dateien wurde gefunden.",
         "geprueft": [str(p) for p, _ in einstellungen.geprüfte_pfade()]},
        status_code=503,
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/einrichtung")
def api_einrichtung(request: Request, nutzlast: dict = Body(...)) -> JSONResponse:
    pfad_text = nutzlast.get("pfad")
    if not isinstance(pfad_text, str) or not pfad_text.strip():
        return JSONResponse({"fehler": "Bitte einen Pfad zur Excel-Datei eingeben."}, status_code=400)
    pfad = Path(pfad_text.strip())
    if pfad.suffix.lower() != ".xlsx" or not pfad.is_file():
        return JSONResponse(
            {"fehler": "Die Datei wurde nicht gefunden oder ist keine .xlsx-Datei."}, status_code=400
        )
    try:
        request.app.state.einstellungen = speichere_excel_pfad(_config_pfad(request), pfad)
    except OSError as exc:
        return JSONResponse(
            {"fehler": f"Die Auswahl konnte nicht gespeichert werden: {exc}"}, status_code=500
        )
    return JSONResponse({"ok": True})


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
        return _keine_datei(einstellungen)
    return JSONResponse({
        "datei": str(pfad),
        "mtime": zustand.mtime,
        "geaendert": zustand.geaendert.isoformat(timespec="seconds"),
        "stand": cache.stand.isoformat(timespec="seconds") if cache.stand else None,
        "cache_leer": cache.leer,
        "in_excel_geoeffnet": sperrdatei(pfad) is not None,
        "zeilen": [z.als_dict() for z in zeilen],
    })


# ── Schreiben ─────────────────────────────────────────────────────────────────

@app.post("/api/cell")
def api_cell(request: Request, nutzlast: dict = Body(...)) -> JSONResponse:
    """Setzt eine einzelne Zahl in Bestand oder Bestellt.

    Der Browser schickt ``key`` (Zeilenschlüssel aus dem Raster), ``spalte``,
    ``wert`` und die ``mtime``, die er beim Laden gesehen hat. Eine freie
    Zellreferenz nimmt diese Route bewusst nicht entgegen.
    """
    try:
        einstellungen = _einstellungen(request)
    except EinstellungsFehler as exc:
        return JSONResponse({"fehler": str(exc)}, status_code=500)

    pfad = einstellungen.excel_pfad()
    if pfad is None:
        return _keine_datei(einstellungen)

    key = nutzlast.get("key")
    spalte = nutzlast.get("spalte")
    if not isinstance(key, str) or not key:
        return JSONResponse({"fehler": "Es fehlt der Schlüssel der Zeile."}, status_code=400)
    if not isinstance(spalte, str):
        return JSONResponse(
            {"fehler": f"Erlaubt sind nur die Spalten {' und '.join(SCHREIBBARE_SPALTEN)}."},
            status_code=400,
        )
    mtime = nutzlast.get("mtime")
    if mtime is not None and not isinstance(mtime, (int, float)):
        return JSONResponse({"fehler": "Ungültige Änderungszeit."}, status_code=400)

    try:
        ergebnis = schreibe_zelle(
            pfad, einstellungen.blatt_raster,
            key=key, spalte=spalte, wert=nutzlast.get("wert"), mtime=mtime,
            backups_behalten=einstellungen.backups_behalten,
        )
    except UngueltigeAenderung as exc:
        return JSONResponse({"fehler": str(exc)}, status_code=400)
    except Konflikt as exc:
        return JSONResponse({"fehler": str(exc), "mtime": exc.aktuelle_mtime}, status_code=409)
    except Gesperrt as exc:
        return JSONResponse({"fehler": str(exc), "benutzer": exc.benutzer}, status_code=423)
    except (ExcelFehlt, BlattFehlt) as exc:
        return JSONResponse({"fehler": str(exc)}, status_code=503)

    zeile = zeile_aus_eintrag(ergebnis.ws, ergebnis.eintrag, cache_modul.laden(pfad))
    return JSONResponse({
        "ok": True,
        "ref": ergebnis.ref,
        "mtime": ergebnis.zustand.mtime,
        "geaendert": ergebnis.zustand.geaendert.isoformat(timespec="seconds"),
        "backup": ergebnis.backup.name if ergebnis.backup else None,
        "zeile": zeile.als_dict(),
    })


# ── Abruf aus IServ ───────────────────────────────────────────────────────────

@app.post("/api/refresh")
def api_refresh(request: Request, nutzlast: dict = Body(...)) -> JSONResponse:
    """Prüft die Zugangsdaten und startet den Hintergrundlauf.

    Die Anmeldung passiert synchron, damit "Passwort falsch" noch als 401
    beantwortet werden kann. Danach hält diese Funktion keine Zugangsdaten mehr.
    """
    try:
        einstellungen = _einstellungen(request)
    except EinstellungsFehler as exc:
        return JSONResponse({"fehler": str(exc)}, status_code=500)

    if einstellungen.excel_pfad() is None:
        return _keine_datei(einstellungen)

    benutzer = nutzlast.get("benutzer")
    passwort = nutzlast.get("passwort")
    if not isinstance(benutzer, str) or not benutzer.strip() or not isinstance(passwort, str) \
            or not passwort:
        return JSONResponse(
            {"fehler": "Bitte IServ-Benutzername und Passwort eingeben."}, status_code=400
        )

    if refresh_modul.laeuft():
        return JSONResponse(
            {"fehler": "Es läuft bereits ein Abruf. Bitte warten, bis er fertig ist.",
             "status": refresh_modul.status()},
            status_code=409,
        )

    try:
        client = refresh_modul.melde_an(
            einstellungen.iserv_domain, benutzer.strip(), passwort,
            client_factory=_client_factory(request),
        )
    except Exception as exc:  # noqa: BLE001 - jede Anmeldeausnahme wird abgebildet
        code, meldung = refresh_modul.fehlerabbildung(exc)
        return JSONResponse({"fehler": meldung}, status_code=code)
    finally:
        # Die Zugangsdaten haben ihren Zweck erfüllt; ab hier existieren sie in
        # dieser Funktion nicht mehr. Der Client trägt sie für die Sitzung.
        passwort = None
        nutzlast = {}

    try:
        job_id = refresh_modul.starte(einstellungen, client)
    except refresh_modul.LaeuftBereits as exc:
        return JSONResponse({"fehler": str(exc), "status": refresh_modul.status()},
                            status_code=409)
    return JSONResponse({"job_id": job_id, "status": refresh_modul.status()}, status_code=202)


@app.get("/api/refresh/status")
def api_refresh_status() -> JSONResponse:
    """Der Stand des laufenden oder zuletzt gelaufenen Abrufs.

    Antwortet immer mit 200: das ist eine Statusabfrage, kein zweiter Versuch.
    Ein gescheiterter Lauf steht als ``fehlercode`` im Körper - die Oberfläche
    liest den Klartext aus ``fehler``.
    """
    stand = refresh_modul.status()
    if stand is None:
        return JSONResponse({"laeuft": False, "fertig": False, "phase": None,
                             "text": "Noch kein Abruf in dieser Sitzung.",
                             "fortschritt": 0, "fehler": None, "fehlercode": None,
                             "diagnosen": [], "warnungen": [], "zusammenfassung": None})
    return JSONResponse(stand)


@app.post("/api/beenden")
def api_beenden(request: Request) -> JSONResponse:
    """Beendet den Server - der Knopf, der das schwarze Fenster schließt.

    Funktioniert nur, wenn ``app/start.py`` den Server gestartet hat; wer mit
    ``uvicorn app.main:app`` von Hand startet, beendet auch von Hand.
    """
    server = getattr(request.app.state, "server", None)
    if server is None:
        return JSONResponse(
            {"fehler": "Dieser Server wurde nicht über START.bat gestartet und "
                       "lässt sich nur im Fenster beenden (Strg+C)."},
            status_code=501,
        )
    server.should_exit = True
    return JSONResponse({"ok": True, "text": "Das Dashboard wird beendet. "
                                             "Sie können das Fenster schließen."})


# ── Oberfläche ────────────────────────────────────────────────────────────────

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
        return templates.TemplateResponse(request, "einrichtung.html", {
            "pfade": einstellungen.geprüfte_pfade()}, status_code=503)

    return templates.TemplateResponse(request, "index.html", {
        "zeilen": zeilen,
        "datei": pfad,
        "zustand": zustand,
        "cache": cache,
        "domain": einstellungen.iserv_domain,
        "in_excel_geoeffnet": sperrdatei(pfad) is not None,
        "sperr_benutzer": sperr_benutzer(pfad),
        "bedarf_gesamt": sum(z.zu_bestellen or 0 for z in zeilen if z.bedarf),
    })
