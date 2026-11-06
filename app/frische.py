"""HTML-Seiten nie aus dem Browser-Zwischenspeicher zeigen.

Ohne eigenen Kopf zeigt der Browser beim Zurückgehen ("Pfeil zurück") die
Fachseite so, wie sie beim ersten Aufruf aussah - auch wenn inzwischen ein
Abruf gelaufen oder eine Planung geändert worden ist. Bei Vor/Zurück prüft der
Browser seinen HTTP-Zwischenspeicher nämlich gar nicht erst nach, sondern nimmt
die gespeicherte Antwort, egal wie alt. ``Cache-Control: no-store`` verbietet
ihm, die Seite überhaupt abzulegen; Zurück lädt sie dann neu vom Server.

Das betrifft nur HTML. Statische Dateien dürfen weiter zwischengespeichert
werden, und die JSON-Routen holt ``fetch`` ohnehin jedes Mal neu ab.

Den zweiten Weg - den Back-Forward-Cache, der die ganze Seite samt Zustand im
Speicher einfriert - deckt ``app/static/kopf.js`` ab (``pageshow``): manche
Browser legen eine Seite trotz ``no-store`` dort ab.
"""
from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class KeinZwischenspeicherMiddleware:
    """Setzt ``Cache-Control: no-store`` auf jede HTML-Antwort.

    Reine ASGI-Middleware aus demselben Grund wie ``HerkunftMiddleware``
    (``app/sicherheit.py``): kein zweiter Task, der Ablauf beim Beenden bleibt
    unverändert.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def senden(nachricht: Message) -> None:
            if nachricht["type"] == "http.response.start":
                koepfe = MutableHeaders(scope=nachricht)
                if koepfe.get("content-type", "").startswith("text/html"):
                    koepfe["Cache-Control"] = "no-store"
            await send(nachricht)

        await self.app(scope, receive, senden)
