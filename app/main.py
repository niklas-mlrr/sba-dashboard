"""Die App-Factory - reine Verdrahtung, sonst nichts.

``create_app`` baut eine vollständig eigenständige Anwendung: eigene
Konfiguration, eigener Abrufzustand, eigener Client. Zwei gestartete Fenster
und jeder Test bekommen damit ihre eigene Instanz, die keine andere
beeinflusst. Der exportierte Modulwert ``app`` bleibt für
``uvicorn app.main:app`` erhalten.

Diese Datei hatte bis 2026-09-05 vier Aufgaben: Factory, sämtliche Routen, das
Domänenlesen (``lies_tabelle``) und die Mappenprüfung
(``validiere_excel_mappe``). Sie war damit die Datei, die jedes neue Feature
anfassen musste. Wo die drei anderen Aufgaben jetzt liegen:

* Routen → ``app/api/`` (vier Router, siehe dort)
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
from .sicherheit import ERLAUBTE_HOSTS, HerkunftMiddleware

_HIER = Path(__file__).resolve().parent


def create_app(
    *,
    einstellungen: Einstellungen | None = None,
    config_pfad: Path | None = None,
    client_factory: ClientFabrik | None = None,
    refresh_manager: RefreshManager | None = None,
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

    # Reihenfolge: Starlette baut den Stapel so, dass die ZULETZT hinzugefügte
    # Middleware AUSSEN liegt. Die Host-Prüfung soll ganz außen stehen - sie ist
    # die billigste und die grundlegendste (gegen DNS-Rebinding hilft der
    # Origin-Vergleich nicht, siehe app/sicherheit.py). Also: Herkunft zuerst
    # eintragen, Host danach.
    application.add_middleware(HerkunftMiddleware)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=list(ERLAUBTE_HOSTS))

    fehler.registriere(application)
    for router in ROUTER:
        application.include_router(router)
    return application


# Kompatibel mit ``uvicorn app.main:app``; produktive Starts rufen ``create_app``
# mit der konkret geladenen Konfiguration auf.
app = create_app()
