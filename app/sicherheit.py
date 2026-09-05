"""Herkunftsprüfung: was die Bindung an 127.0.0.1 allein nicht abdeckt.

``app/start.py`` bindet ausschließlich an die Loopback-Adresse. Das hält das
**Schulnetz** ab - es hält aber nicht den **Browser** ab, der auf demselben
Rechner läuft. Zwei Wege bleiben ohne Prüfung offen, und beide sind nicht
theoretisch:

**1. Zustandsändernde Anfragen von einer fremden Seite.** ``POST /api/beenden``
nimmt keinen Körper. Eine beliebige Seite, die die Lehrkraft während des
Betriebs im Nachbartab öffnet, kann sie also mit einem einfachen ``fetch``
(kein Preflight, weil kein besonderer Header und kein JSON-Content-Type nötig
ist) auslösen. Die *Antwort* bleibt dem Angreifer durch die Same-Origin-Policy
verborgen - die *Wirkung* nicht: das Dashboard ist zu.

**2. DNS-Rebinding.** Eine fremde Domain, deren DNS-Eintrag auf 127.0.0.1
zeigt, gilt dem Browser als eigene Herkunft. Ihre Seite darf ``GET /`` und
``GET /api/rows`` lesen **und die Antwort auswerten** - also genau die
Anmeldezahlen je Jahrgang, deren Offenlegung ``docs/architektur.md`` einen
Datenschutzvorfall nennt. Gegen diesen Weg hilft kein Origin-Vergleich (die
Herkunft *ist* dann dieselbe), sondern nur der ``Host``-Kopf: der trägt weiter
den Namen, den der Angreifer registriert hat, nicht ``127.0.0.1``.

Deshalb zwei Schichten, in dieser Reihenfolge:

* ``TrustedHostMiddleware`` (Starlette) gegen 2. - sie schneidet den Port selbst
  ab, sodass jeder von ``freier_port`` gewählte Port ohne Konfiguration passt.
* :class:`HerkunftMiddleware` gegen 1.

Was das **nicht** ist: eine Anmeldung. Wer am Rechner sitzt, darf alles - das
war und bleibt die Annahme (``docs/architektur.md``, "Warum 127.0.0.1").
Geprüft wird nur, dass die Anfrage tatsächlich vom Dashboard selbst kommt und
nicht von einer fremden Seite im selben Browser.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# Ein Browser erreicht das Dashboard über genau diese zwei Namen; uvicorn bindet
# an 127.0.0.1 (``app.start.HOST``). ``[::1]`` fehlt bewusst: an IPv6 wird gar
# nicht gebunden, eine Anfrage mit diesem Host käme also nie an - und Starlette
# schneidet den Port über ``split(":")[0]`` ab, was bei ``[::1]:8765`` ohnehin
# nur ``[`` übrig ließe.
ERLAUBTE_HOSTS = ("127.0.0.1", "localhost")

# GET, HEAD und OPTIONS ändern nichts. Sie brauchen den Origin-Vergleich nicht:
# gegen das Mitlesen einer fremden Seite schützt bereits die Same-Origin-Policy
# des Browsers (das Dashboard sendet keinen einzigen CORS-Kopf), und gegen
# DNS-Rebinding - den einen Fall, in dem sie nicht greift - schützt die
# Host-Prüfung eine Schicht darüber.
SICHERE_METHODEN = frozenset({"GET", "HEAD", "OPTIONS"})

_ABLEHNUNG = (
    "Diese Anfrage kam von einer fremden Internetseite und wurde deshalb "
    "abgelehnt. Das Dashboard nimmt Änderungen nur von seiner eigenen Seite "
    "entgegen (http://127.0.0.1)."
)


def herkunft_erlaubt(origin: str | None) -> bool:
    """Ob ein ``Origin``-Kopf zum Dashboard selbst gehört.

    ``None`` gilt als erlaubt, und das ist die eine Entscheidung hier, die
    Begründung braucht. Ein Browser setzt den Kopf bei **jeder**
    zustandsändernden Anfrage einer fremden Seite - bei ``fetch``/``XHR``
    ebenso wie beim abgeschickten ``<form>``. Genau der Angriff aus dem
    Modulkopf trägt ihn also immer. Ohne Kopf kommt die Anfrage entweder vom
    Dashboard selbst (gleiche Herkunft, ältere Browser lassen ihn dann weg)
    oder gar nicht aus einem Browser - etwa aus ``curl`` oder einem
    Diagnoseskript, das ohnehin schon auf diesem Rechner läuft und dort alles
    darf, was die Lehrkraft auch darf. Ein Pflicht-Origin würde diese Fälle
    ohne Sicherheitsgewinn brechen.

    Der Port bleibt absichtlich ungeprüft: ``app.start.freier_port`` weicht bei
    belegtem Port aus, ein zweites Fenster läuft also regulär unter einem
    anderen. Ein Angreifer gewinnt damit nichts - er müsste ohnehin schon
    einen Server auf der Loopback-Adresse dieses Rechners betreiben.
    """
    if origin is None:
        return True
    # urlsplit("null").hostname ist None - ein "Origin: null" (sandboxed
    # iframe, file://) fällt damit durch, ohne Sonderfall.
    return urlsplit(origin).hostname in ERLAUBTE_HOSTS


class HerkunftMiddleware:
    """Lehnt zustandsändernde Anfragen mit fremdem ``Origin`` ab.

    Reine ASGI-Middleware statt ``BaseHTTPMiddleware``: sie muss den Körper
    nicht anfassen, und ohne den Umweg über einen zweiten Task bleibt der
    Ablauf beim Beenden (``POST /api/beenden`` setzt ``server.should_exit``,
    während die Antwort noch läuft) genau so, wie er ohne Middleware war.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in SICHERE_METHODEN:
            await self.app(scope, receive, send)
            return
        origin = Headers(scope=scope).get("origin")
        if not herkunft_erlaubt(origin):
            antwort = JSONResponse({"fehler": _ABLEHNUNG}, status_code=403)
            await antwort(scope, receive, send)
            return
        await self.app(scope, receive, send)
