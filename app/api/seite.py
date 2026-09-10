"""Die HTML-Oberfläche und die Einstellungen, die das Programmfenster schreibt.

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
from ..modelle import EinstellungenAnfrage
from ..paths import benutzer_konfigurationspfad
from ..rows import lies_tabelle
from ..settings import (
    EinstellungsFehler,
    mappe_im_ordner,
    pruefe_domain,
    speichere_benutzerwerte,
)
from .gemeinsam import aktuelle_einstellungen, vorlagen

router = APIRouter()


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


@router.post("/api/einstellungen")
def api_einstellungen(request: Request, anfrage: EinstellungenAnfrage) -> JSONResponse:
    """Nimmt Server und Ordner aus dem Programmfenster an, prüft sie, speichert sie.

    Die Reihenfolge ist der Punkt: erst prüfen, dann speichern. Sonst könnte ein
    Ordner ohne brauchbare Mappe den funktionierenden Stand in der
    Benutzerkonfiguration verdrängen, und der Fehler fiele erst beim nächsten
    Seitenaufbau auf - ohne jeden Hinweis darauf, was ihn ausgelöst hat.

    Bis 2026-09-10 hieß diese Route ``POST /api/einrichtung``, nahm einen vollen
    Dateipfad und wurde von einer Browserseite bedient. Eingestellt wird jetzt
    der Ordner (siehe ``app.settings.mappe_im_ordner``), und zwar im
    Programmfenster - dort gibt es eine Ordnerauswahl, und ein UNC-Pfad von Hand
    eingetippt war die fehleranfälligste Stelle der Ersteinrichtung.
    """
    domain_fehler = pruefe_domain(anfrage.server)
    if domain_fehler:
        return JSONResponse({"fehler": domain_fehler}, status_code=400)

    ordner = Path(anfrage.ordner)
    if not ordner.is_dir():
        return JSONResponse(
            {"fehler": f"Der Ordner wurde nicht gefunden: {ordner}"}, status_code=400,
        )
    mappe = mappe_im_ordner(ordner)
    if mappe is None:
        return JSONResponse(
            {"fehler": f"In diesem Ordner liegt keine Excel-Datei (.xlsx): {ordner}"},
            status_code=400,
        )

    einstellungen = aktuelle_einstellungen(request)
    # Wirft MappeUngeeignet -> 400 samt Klartext (app/fehler.py).
    validiere_excel_mappe(mappe, einstellungen.blatt_raster)

    ziel = einstellungen
    if ziel.benutzer_config_pfad is None:
        # Einstellungen, die nicht über Einstellungen.laden() entstanden sind
        # (Dependency Injection in Tests), kennen ihren Zielpfad nicht von sich
        # aus. Dann gilt der config_pfad der App-Instanz (--config-Modus) und
        # sonst die Benutzerkonfiguration im plattformabhängigen Ordner.
        #
        # Hier stand bis 2026-09-10 als letzter Rückfall der ausgelieferte
        # Standard im Repo. Das war die einzige Stelle im Programm, die ihn
        # beschreiben konnte - gegen die Regel aus app/settings.py, und in der
        # Praxis hat genau das zugeschlagen: ein neuer Test ohne eigenen
        # config_pfad trug seinen tmp_path-Ordner in die versionierte
        # config.json ein. benutzer_konfigurationspfad() achtet auf
        # SBA_CONFIG_DIR und landet in Tests damit automatisch im tmp_path.
        ziel = replace(
            ziel,
            benutzer_config_pfad=(
                request.app.state.config_pfad or benutzer_konfigurationspfad()
            ),
        )
    try:
        request.app.state.einstellungen = speichere_benutzerwerte(
            ziel, iserv_domain=anfrage.server, excel_ordner=ordner,
        )
    except (OSError, ValueError) as exc:
        # Kein Fall für app/fehler.py: OSError und ValueError sind zu weit, um
        # sie anwendungsweit auf einen Status abzubilden. Hier ist die Bedeutung
        # dagegen eindeutig - die Eingabe ließ sich nicht ablegen.
        return JSONResponse(
            {"fehler": f"Die Einstellungen konnten nicht gespeichert werden: {exc}"},
            status_code=500,
        )
    return JSONResponse({"ok": True, "mappe": str(mappe)})


@router.get("/api/einstellungen")
def api_einstellungen_lesen(request: Request) -> JSONResponse:
    """Was im Fenster vorbelegt stehen soll - Server, Ordner und die gefundene Mappe.

    Das Fenster fragt hier und liest nicht selbst die Konfiguration: es soll
    denselben Stand sehen, mit dem der Server arbeitet, auch wenn der gerade
    durch ein zweites Fenster geändert wurde.
    """
    einstellungen = aktuelle_einstellungen(request)
    mappe = einstellungen.excel_pfad()
    return JSONResponse({
        "server": einstellungen.iserv_domain,
        "ordner": str(einstellungen.excel_ordner) if einstellungen.excel_ordner else None,
        "mappe": str(mappe) if mappe else None,
        "geprueft": [str(p) for p, _ in einstellungen.gepruefte_pfade()],
    })


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
            request, "einrichtung.html", {
                "pfade": einstellungen.gepruefte_pfade(),
                "ordner": einstellungen.excel_ordner,
            },
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
