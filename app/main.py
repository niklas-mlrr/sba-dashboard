"""FastAPI-Anwendung des Schulbuchausleihe-Dashboards.

``create_app`` baut eine vollständig eigenständige Anwendung. Der exportierte
Modulwert ``app`` bleibt für ``uvicorn app.main:app`` erhalten, während Tests
und der Windows-Start eigene Instanzen mit eigener Konfiguration und eigenem
Abrufzustand erstellen können.
"""
from __future__ import annotations

from pathlib import Path
from zipfile import BadZipFile

from bestand.core import parse_grid
from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openpyxl.utils.exceptions import InvalidFileException

from . import cache as cache_modul
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
from .refresh import LaeuftBereits, RefreshManager, fehlerabbildung, melde_an
from .rows import baue_zeilen, zeile_aus_eintrag
from .settings import Einstellungen, EinstellungsFehler, speichere_excel_pfad

_HIER = Path(__file__).parent
_WURZEL = _HIER.parent
_ERFORDERLICHE_ZUSATZBLAETTER = ("bestellt", "zu Bestellen")


def lade_einstellungen(pfad: Path | None = None) -> Einstellungen:
    """Lädt die Standardkonfiguration oder eine explizite Arbeitskopie."""
    return Einstellungen.laden(pfad or _WURZEL / "config.json")


def lies_tabelle(einstellungen: Einstellungen):
    """Mappe frisch laden, Raster parsen und Anzeigezeilen bauen."""
    pfad = einstellungen.excel_pfad()
    if pfad is None:
        return None, [], None, None
    wb = lade_mappe(pfad)
    ws = raster_blatt(wb, einstellungen.blatt_raster)
    grid = parse_grid(ws)
    cache = cache_modul.laden(pfad)
    return pfad, baue_zeilen(ws, grid, cache), Dateizustand.von(pfad), cache


def validiere_excel_mappe(pfad: Path, blatt_raster: str) -> None:
    """Öffnet eine neue Auswahl und prüft die für das Dashboard nötige Struktur.

    Diese Prüfung passiert vor dem Schreiben der Konfiguration. So kann keine
    beliebige ``.xlsx``-Datei den funktionierenden Pfad in ``config.json``
    verdrängen.
    """
    try:
        wb = lade_mappe(pfad)
        ws = raster_blatt(wb, blatt_raster)
        fehlend = [blatt for blatt in _ERFORDERLICHE_ZUSATZBLAETTER if blatt not in wb.sheetnames]
        if fehlend:
            raise BlattFehlt(f"Erforderliche Tabellenblätter fehlen: {', '.join(fehlend)}.")
        grid = parse_grid(ws)
        if not grid.entries:
            raise EinstellungsFehler(
                "Das Tabellenblatt enthält kein lesbares Bestandsraster."
            )
    except BlattFehlt:
        raise
    except EinstellungsFehler:
        raise
    except (BadZipFile, InvalidFileException, OSError, ValueError, KeyError, RuntimeError) as exc:
        raise EinstellungsFehler(f"Die Datei ist keine lesbare Excel-Arbeitsmappe: {exc}") from exc


def _keine_datei(einstellungen: Einstellungen) -> JSONResponse:
    return JSONResponse(
        {"fehler": "Keine der eingetragenen Excel-Dateien wurde gefunden.",
         "geprueft": [str(p) for p, _ in einstellungen.geprüfte_pfade()]},
        status_code=503,
    )


def _status_ohne_lauf() -> dict:
    return {
        "laeuft": False,
        "fertig": False,
        "phase": None,
        "text": "Noch kein Abruf in dieser Sitzung.",
        "fortschritt": 0,
        "fehler": None,
        "fehlercode": None,
        "diagnosen": [],
        "warnungen": [],
        "zusammenfassung": None,
    }


def create_app(
    *,
    einstellungen: Einstellungen | None = None,
    config_pfad: Path | None = None,
    client_factory=None,
    refresh_manager: RefreshManager | None = None,
) -> FastAPI:
    """Erstellt eine unabhängige Dashboard-Anwendung mit Dependency Injection."""
    application = FastAPI(title="Schulbuchausleihe — Bestand")
    application.mount("/static", StaticFiles(directory=_HIER / "static"), name="static")
    templates = Jinja2Templates(directory=str(_HIER / "templates"))
    application.state.einstellungen = einstellungen
    application.state.config_pfad = config_pfad or _WURZEL / "config.json"
    application.state.client_factory = client_factory
    application.state.refresh_manager = refresh_manager or RefreshManager()

    def app_einstellungen(request: Request) -> Einstellungen:
        vorhanden = request.app.state.einstellungen
        return vorhanden if vorhanden is not None else lade_einstellungen(request.app.state.config_pfad)

    @application.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @application.post("/api/einrichtung")
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
            aktuelle_einstellungen = app_einstellungen(request)
            validiere_excel_mappe(pfad, aktuelle_einstellungen.blatt_raster)
        except (EinstellungsFehler, BlattFehlt) as exc:
            return JSONResponse({"fehler": str(exc)}, status_code=400)
        try:
            request.app.state.einstellungen = speichere_excel_pfad(request.app.state.config_pfad, pfad)
        except (OSError, ValueError) as exc:
            return JSONResponse(
                {"fehler": f"Die Auswahl konnte nicht gespeichert werden: {exc}"}, status_code=500
            )
        return JSONResponse({"ok": True})

    @application.get("/api/rows")
    def api_rows(request: Request) -> JSONResponse:
        try:
            aktuelle_einstellungen = app_einstellungen(request)
            pfad, zeilen, zustand, cache = lies_tabelle(aktuelle_einstellungen)
        except (EinstellungsFehler, BlattFehlt) as exc:
            return JSONResponse({"fehler": str(exc)}, status_code=500)
        if pfad is None:
            return _keine_datei(aktuelle_einstellungen)
        return JSONResponse({
            "datei": str(pfad),
            "mtime": zustand.mtime,
            "geaendert": zustand.geaendert.isoformat(timespec="seconds"),
            "stand": cache.stand.isoformat(timespec="seconds") if cache.stand else None,
            "cache_leer": cache.leer,
            "in_excel_geoeffnet": sperrdatei(pfad) is not None,
            "zeilen": [z.als_dict() for z in zeilen],
        })

    @application.post("/api/cell")
    def api_cell(request: Request, nutzlast: dict = Body(...)) -> JSONResponse:
        try:
            aktuelle_einstellungen = app_einstellungen(request)
        except EinstellungsFehler as exc:
            return JSONResponse({"fehler": str(exc)}, status_code=500)
        pfad = aktuelle_einstellungen.excel_pfad()
        if pfad is None:
            return _keine_datei(aktuelle_einstellungen)

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
        if not isinstance(mtime, (int, float)) or isinstance(mtime, bool):
            return JSONResponse({"fehler": "Es fehlt eine gültige Änderungszeit."}, status_code=400)

        try:
            ergebnis = schreibe_zelle(
                pfad,
                aktuelle_einstellungen.blatt_raster,
                key=key,
                spalte=spalte,
                wert=nutzlast.get("wert"),
                mtime=mtime,
                backups_behalten=aktuelle_einstellungen.backups_behalten,
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

    @application.post("/api/refresh")
    def api_refresh(request: Request, nutzlast: dict = Body(...)) -> JSONResponse:
        try:
            aktuelle_einstellungen = app_einstellungen(request)
        except EinstellungsFehler as exc:
            return JSONResponse({"fehler": str(exc)}, status_code=500)
        if aktuelle_einstellungen.excel_pfad() is None:
            return _keine_datei(aktuelle_einstellungen)

        benutzer = nutzlast.get("benutzer")
        passwort = nutzlast.get("passwort")
        if not isinstance(benutzer, str) or not benutzer.strip() or not isinstance(passwort, str) \
                or not passwort:
            return JSONResponse(
                {"fehler": "Bitte IServ-Benutzername und Passwort eingeben."}, status_code=400
            )

        manager = request.app.state.refresh_manager
        if manager.laeuft():
            return JSONResponse(
                {"fehler": "Es läuft bereits ein Abruf. Bitte warten, bis er fertig ist.",
                 "status": manager.status()},
                status_code=409,
            )
        try:
            client = melde_an(
                aktuelle_einstellungen.iserv_domain,
                benutzer.strip(),
                passwort,
                client_factory=request.app.state.client_factory,
            )
        except Exception as exc:  # noqa: BLE001 - jede Anmeldeausnahme wird abgebildet
            code, meldung = fehlerabbildung(exc)
            return JSONResponse({"fehler": meldung}, status_code=code)
        finally:
            passwort = None
            nutzlast = {}

        try:
            job_id = manager.starte(aktuelle_einstellungen, client)
        except LaeuftBereits as exc:
            return JSONResponse({"fehler": str(exc), "status": manager.status()}, status_code=409)
        return JSONResponse({"job_id": job_id, "status": manager.status()}, status_code=202)

    @application.get("/api/refresh/status")
    def api_refresh_status(request: Request) -> JSONResponse:
        return JSONResponse(request.app.state.refresh_manager.status() or _status_ohne_lauf())

    @application.post("/api/beenden")
    def api_beenden(request: Request) -> JSONResponse:
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

    @application.get("/")
    def index(request: Request):
        try:
            aktuelle_einstellungen = app_einstellungen(request)
            pfad, zeilen, zustand, cache = lies_tabelle(aktuelle_einstellungen)
        except EinstellungsFehler as exc:
            return templates.TemplateResponse(
                request, "fehler.html", {"titel": "Konfiguration", "meldung": str(exc)},
                status_code=500,
            )
        except BlattFehlt as exc:
            return templates.TemplateResponse(
                request, "fehler.html", {"titel": "Tabellenblatt fehlt", "meldung": str(exc)},
                status_code=500,
            )
        if pfad is None:
            return templates.TemplateResponse(
                request, "einrichtung.html", {"pfade": aktuelle_einstellungen.geprüfte_pfade()},
                status_code=503,
            )
        return templates.TemplateResponse(request, "index.html", {
            "zeilen": zeilen,
            "datei": pfad,
            "zustand": zustand,
            "cache": cache,
            "domain": aktuelle_einstellungen.iserv_domain,
            "in_excel_geoeffnet": sperrdatei(pfad) is not None,
            "sperr_benutzer": sperr_benutzer(pfad),
            "bedarf_gesamt": sum(z.zu_bestellen or 0 for z in zeilen if z.bedarf),
        })

    return application


# Kompatibel mit ``uvicorn app.main:app``; produktive Starts rufen ``create_app``
# mit der konkret geladenen Konfiguration auf.
app = create_app()
