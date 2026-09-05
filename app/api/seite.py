"""Die HTML-Oberfläche und das eine Formular, das sie einrichtet.

``GET /`` ist die einzige Route, die ihre Fehler noch selbst abfängt, und das
ist Absicht: sie liefert HTML. Eine Lehrkraft, die die Startseite aufruft,
bekommt bei einem Konfigurationsfehler eine lesbare Fehlerseite - drei Zeilen
JSON im Browserfenster wären für genau diese Person die schlechteste aller
Antworten. Alle übrigen Routen liefern JSON und überlassen die Abbildung
``app/fehler.py``.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from ..excel import BlattFehlt, ExcelFehlt, sperr_benutzer, sperrdatei, validiere_excel_mappe
from ..modelle import EinrichtungAnfrage
from ..rows import lies_tabelle
from ..settings import EinstellungsFehler, speichere_excel_pfad
from .gemeinsam import aktuelle_einstellungen, vorlagen

router = APIRouter()

_WURZEL = Path(__file__).resolve().parent.parent.parent


def _fehlerseite(request: Request, titel: str, meldung: str, status: int) -> Response:
    """Dieselbe Aussage wie ``app/fehler.py``, nur als Seite statt als JSON.

    Die Statuscodes sind absichtlich dieselben wie dort (500 für Konfiguration
    und fehlendes Blatt, 503 für die verschwundene Datei) - eine Seite, die
    anders antwortet als die API daneben, wäre genau die Drift, gegen die die
    zentrale Abbildung angetreten ist.
    """
    return vorlagen.TemplateResponse(
        request, "fehler.html", {"titel": titel, "meldung": meldung}, status_code=status,
    )


@router.post("/api/einrichtung")
def api_einrichtung(request: Request, anfrage: EinrichtungAnfrage) -> JSONResponse:
    """Nimmt den ausgewählten Pfad an, prüft die Mappe und schreibt ihn erst dann.

    Die Reihenfolge ist der Punkt: erst ``validiere_excel_mappe``, dann
    speichern. Sonst könnte eine beliebige ``.xlsx``-Datei den funktionierenden
    Pfad in der Benutzerkonfiguration verdrängen, und der Fehler fiele erst beim
    nächsten Seitenaufbau auf - ohne jeden Hinweis darauf, was ihn ausgelöst hat.
    """
    pfad = Path(anfrage.pfad)
    if pfad.suffix.lower() != ".xlsx" or not pfad.is_file():
        return JSONResponse(
            {"fehler": "Die Datei wurde nicht gefunden oder ist keine .xlsx-Datei."},
            status_code=400,
        )
    einstellungen = aktuelle_einstellungen(request)
    # Wirft MappeUngeeignet -> 400 samt Klartext (app/fehler.py).
    validiere_excel_mappe(pfad, einstellungen.blatt_raster)

    ziel = einstellungen
    if ziel.benutzer_config_pfad is None:
        # Einstellungen, die nicht über Einstellungen.laden() entstanden sind
        # (Dependency Injection in Tests), kennen ihren Zielpfad nicht von
        # sich aus - dann gilt der config_pfad der App-Instanz, wie schon vor
        # dem Overlay-Modell.
        ziel = replace(
            ziel,
            benutzer_config_pfad=request.app.state.config_pfad or _WURZEL / "config.json",
        )
    try:
        request.app.state.einstellungen = speichere_excel_pfad(ziel, pfad)
    except (OSError, ValueError) as exc:
        # Kein Fall für app/fehler.py: OSError und ValueError sind zu weit, um
        # sie anwendungsweit auf einen Status abzubilden. Hier ist die Bedeutung
        # dagegen eindeutig - der gewählte Pfad ließ sich nicht ablegen.
        return JSONResponse(
            {"fehler": f"Die Auswahl konnte nicht gespeichert werden: {exc}"}, status_code=500
        )
    return JSONResponse({"ok": True})


@router.get("/")
def index(request: Request) -> Response:
    """Die Tabelle als Seite - oder die Einrichtung, wenn es noch keine Mappe gibt."""
    try:
        einstellungen = aktuelle_einstellungen(request)
        stand = lies_tabelle(einstellungen)
    except EinstellungsFehler as exc:
        return _fehlerseite(request, "Konfiguration", str(exc), 500)
    except BlattFehlt as exc:
        # BlattFehlt erbt von KeyError, dessen __str__ das repr des Arguments
        # liefert - str(exc) stünde sonst in Anführungszeichen auf der Seite.
        return _fehlerseite(request, "Tabellenblatt fehlt", str(exc.args[0]), 500)
    except ExcelFehlt as exc:
        # Die Datei war beim Prüfen der Kandidaten noch da und beim Laden nicht
        # mehr: Netzlaufwerk weg, oder jemand hat sie verschoben.
        return _fehlerseite(request, "Excel-Datei", str(exc), 503)

    if stand is None:
        return vorlagen.TemplateResponse(
            request, "einrichtung.html", {"pfade": einstellungen.geprüfte_pfade()},
            status_code=503,
        )
    return vorlagen.TemplateResponse(request, "index.html", {
        "zeilen": stand.zeilen,
        "datei": stand.pfad,
        "zustand": stand.zustand,
        "cache": stand.cache,
        # iserv_domain stand hier bis 2026-09-05 als "domain" mit drin und wurde
        # von index.html nie benutzt. Ein Vorlagenwert, den keine Vorlage liest,
        # sieht bei der nächsten Änderung aus wie eine Zusage.
        "in_excel_geoeffnet": sperrdatei(stand.pfad) is not None,
        "sperr_benutzer": sperr_benutzer(stand.pfad),
        "bedarf_gesamt": stand.bedarf_gesamt,
    })
