"""Die App-Factory - reine Verdrahtung, sonst nichts.

``create_app`` baut eine vollständig eigenständige Anwendung: eigene
Konfiguration, eigener Abrufzustand, eigene Anmeldung, eigener Client. Zwei
gestartete Fenster und jeder Test bekommen damit ihre eigene Instanz, die keine
andere beeinflusst. Der exportierte Modulwert ``app`` bleibt für
``uvicorn app.main:app`` erhalten.

Was bewusst **nicht** hier steht, damit nicht jedes neue Feature diese Datei
anfassen muss:

* Routen → ``app/api/`` (je Aufgabe ein Router, siehe dort)
* ``lies_tabelle`` → ``app/rows.py`` (kein FastAPI darin)
* ``validiere_excel_mappe`` → ``app/excel.py`` (kein FastAPI darin)
* Ausnahme → HTTP → ``app/fehler.py`` (einmal statt je Route)
* ``lade_einstellungen`` → ``app/konfiguration.py``

Was hier steht, ist die **Reihenfolge**, in der das zusammengesteckt wird - und
die ist bei den Middlewares nicht beliebig, siehe unten.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import fehler
from .api import ROUTER
from .refresh import ClientFabrik, RefreshManager
from .settings import Einstellungen
from .sicherheit import HerkunftMiddleware, erlaubte_hosts
from .sitzung import Anmeldung

_HIER = Path(__file__).resolve().parent


def create_app(
    *,
    einstellungen: Einstellungen | None = None,
    config_pfad: Path | None = None,
    client_factory: ClientFabrik | None = None,
    refresh_manager: RefreshManager | None = None,
    anmeldung: Anmeldung | None = None,
) -> FastAPI:
    """Erstellt eine unabhängige Dashboard-Anwendung mit Dependency Injection."""
    application = FastAPI(title="Schulbuchausleihe — Bestand")
    application.mount("/static", StaticFiles(directory=_HIER / "static"), name="static")

    application.state.einstellungen = einstellungen
    # None bleibt None (statt auf config.json zu verfallen): das unterscheidet
    # den Arbeitskopie-Modus (--config PATH, kein Overlay) vom Produktivmodus,
    # der beim Nachladen über lade_einstellungen(None) den Overlay-Weg nimmt.
    application.state.config_pfad = config_pfad
    application.state.client_factory = client_factory
    application.state.refresh_manager = refresh_manager or RefreshManager()
    # Eine Anmeldung je Anwendung, wie der RefreshManager: zwei gestartete
    # Fenster melden sich unabhängig voneinander an. Einsetzbar, damit Tests das
    # Zeitschloss mit einer eigenen Zeitquelle prüfen können.
    application.state.anmeldung = anmeldung or Anmeldung()

    # Reihenfolge: Starlette baut den Stapel so, dass die ZULETZT hinzugefügte
    # Middleware AUSSEN liegt. Die Host-Prüfung soll ganz außen stehen - sie ist
    # die billigste und die grundlegendste (gegen DNS-Rebinding hilft der
    # Origin-Vergleich nicht, siehe app/sicherheit.py). Also: Herkunft zuerst
    # eintragen, Host danach.
    # Die Namen werden je Anwendung gelesen, nicht beim Import: so sieht ein
    # Test, der SBA_ZUSATZ_HOSTS setzt, sie in der App, die er danach baut.
    hosts = erlaubte_hosts()
    application.add_middleware(HerkunftMiddleware, hosts=hosts)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=list(hosts))

    fehler.registriere(application)
    for router in ROUTER:
        application.include_router(router)
    return application


# Kompatibel mit ``uvicorn app.main:app``; produktive Starts rufen ``create_app``
# mit der konkret geladenen Konfiguration auf.
app = create_app()
