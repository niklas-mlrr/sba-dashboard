"""Die Anmeldung als Zustand - der einzige Ort, an dem Zugangsdaten liegen.

Bis 2026-09-10 fragte der Abruf-Dialog im Browser bei **jedem** Abruf erneut
nach Benutzername und Passwort, und das Passwort überlebte die eine Anfrage
nicht. Seit es ein Programmfenster gibt, meldet man sich dort **einmal** an; die
Anmeldung hält, bis sie verfällt, abgemeldet oder das Programm beendet wird.

## Warum das Passwort dabei im Speicher bleibt

Es lässt sich nicht vermeiden. ``AusleiheClient`` hält das Passwort selbst
(``ausleihe/client.py``) und **braucht** es weiter: läuft die IServ-Sitzung ab,
meldet er sich bei einem 401 selbsttätig neu an. Einen angemeldeten Client ohne
Passwort gibt es also nicht - "nur die Sitzung halten" wäre eine Zusage, die
diese Klasse nicht einhalten könnte.

Was sie stattdessen zusagt, und was die Tests in ``tests/test_sitzung.py``
festhalten:

* **Genau ein Besitzer.** Das Passwort liegt im Client-Objekt und sonst
  nirgends - nicht in einem Feld dieser Klasse, nicht in ``app.state``, nicht
  im Fortschrittszustand des Abrufs, nicht in einer Antwort und nicht im Log.
* **Nie auf der Platte.** Anders als Server und Ordner (die in der
  Benutzerkonfiguration landen, siehe ``app/settings.py``) wird hiervon nichts
  gespeichert.
* **Ein Zeitschloss.** Nach :data:`ABLAUF_SEKUNDEN` ohne Abruf wird der Client
  verworfen. Das ist der einzige wirksame Hebel auf die Liegezeit: er verkürzt
  sie von "bis der Laptop abends zuklappt" auf die tatsächliche Arbeitsphase.

Was **nicht** zugesagt wird, und zwar bewusst nicht: dass das Passwort nach dem
Verwerfen aus dem Speicher verschwunden *ist*. Python-Strings sind
unveränderlich; sie lassen sich nicht überschreiben. ``abmelden`` macht sie
unerreichbar, mehr kann es nicht - und ein ``bytearray``-Umweg, der danach
aussieht, als könnte er mehr, wäre schlimmer als diese Zeile hier.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

from .refresh import AusleiheProtokoll, ClientFabrik, melde_an
from .settings import Einstellungen

# Dreißig Minuten ohne Abruf. Lang genug, dass eine Arbeitsphase nicht
# unterbrochen wird, kurz genug, dass ein vergessenes Fenster über Nacht kein
# Passwort mehr hält.
ABLAUF_SEKUNDEN = 30 * 60

# Nur für den Handtest auf einem echten Rechner (docs/schul-laptop-test.md):
# das Zeitschloss ist sonst nicht in vertretbarer Zeit zu beobachten. In den
# automatischen Tests wird stattdessen die Zeitquelle eingesetzt.
_UMGEBUNGSSCHLUESSEL = "SBA_ANMELDUNG_ABLAUF"


class NichtAngemeldet(RuntimeError):
    """Es wurde noch keine Anmeldung vorgenommen - führt zu HTTP 401."""


class Abgelaufen(RuntimeError):
    """Die Anmeldung ist verfallen - führt ebenfalls zu HTTP 401."""


def _ablauf_aus_umgebung() -> int:
    roh = os.environ.get(_UMGEBUNGSSCHLUESSEL)
    if roh is None:
        return ABLAUF_SEKUNDEN
    try:
        wert = int(roh)
    except ValueError:
        return ABLAUF_SEKUNDEN
    return wert if wert > 0 else ABLAUF_SEKUNDEN


class Anmeldung:
    """Die IServ-Anmeldung einer Dashboard-Instanz.

    Eine je Anwendung (``app.state.anmeldung``), wie ``RefreshManager`` - zwei
    gestartete Fenster und jeder Test haben damit ihre eigene, und keine sieht
    die andere.

    ``zeit`` ist einsetzbar, damit ``tests/test_sitzung.py`` das Zeitschloss
    ohne ``sleep`` prüfen kann; produktiv ist es ``time.monotonic``, das im
    Gegensatz zu ``time.time`` keine Zeitumstellung mitmacht.
    """

    def __init__(
        self,
        *,
        ablauf_sekunden: int | None = None,
        zeit: Callable[[], float] = time.monotonic,
    ) -> None:
        self._lock = threading.Lock()
        self._zeit = zeit
        self._ablauf = ablauf_sekunden if ablauf_sekunden is not None else _ablauf_aus_umgebung()
        self._client: AusleiheProtokoll | None = None
        self._benutzer: str | None = None
        self._zuletzt = 0.0

    # ── Anmelden und Abmelden ────────────────────────────────────────────────

    def anmelden(
        self,
        einstellungen: Einstellungen,
        benutzer: str,
        passwort: str,
        *,
        client_factory: ClientFabrik | None = None,
    ) -> None:
        """Meldet bei IServ an und behält den Client. Fehler fliegen durch.

        Die Anmeldung passiert **vor** dem Lock: sie geht ins Netz und dauert
        eine knappe Sekunde: währenddessen soll ``status()`` aus dem
        Fenster-Timer nicht blockieren. Schlägt sie fehl, bleibt eine
        bestehende Anmeldung unangetastet - ein Tippfehler im zweiten Versuch
        wirft niemanden aus einer laufenden Sitzung.
        """
        client = melde_an(
            einstellungen.iserv_domain, benutzer, passwort, client_factory=client_factory,
        )
        with self._lock:
            self._client = client
            self._benutzer = benutzer
            self._zuletzt = self._zeit()

    def abmelden(self) -> None:
        """Verwirft den Client - und damit den einzigen Besitzer des Passworts."""
        with self._lock:
            self._client = None
            self._benutzer = None
            self._zuletzt = 0.0

    # ── Benutzung ────────────────────────────────────────────────────────────

    def client(self) -> AusleiheProtokoll:
        """Der angemeldete Client, und setzt dabei das Zeitschloss zurück.

        Ein bereits laufender Abruf hält seine **eigene** Referenz auf den
        Client (``RefreshManager.starte`` bekommt ihn als Parameter). Verfällt
        die Anmeldung mitten in einem langen Lauf, wird ihm deshalb nichts
        entzogen - er läuft zu Ende, und erst der *nächste* Abruf verlangt eine
        neue Anmeldung. Das ist der Grund, warum hier kein Wächter gegen einen
        laufenden Abruf nötig ist.
        """
        with self._lock:
            if self._client is None:
                raise NichtAngemeldet(
                    "Nicht bei IServ angemeldet. Bitte im Programmfenster anmelden."
                )
            if self._verfallen():
                self._client = None
                self._benutzer = None
                raise Abgelaufen(
                    f"Die Anmeldung ist nach {self._ablauf // 60} Minuten ohne Abruf "
                    "abgelaufen. Bitte im Programmfenster erneut anmelden."
                )
            self._zuletzt = self._zeit()
            return self._client

    def status(self) -> dict[str, Any]:
        """Was das Fenster anzeigt. Enthält den Benutzernamen, nie das Passwort.

        Fragt **nicht** als Benutzung: der Fenster-Timer ruft das alle paar
        Sekunden auf, und ein offenes Fenster ist keine Arbeit an der Mappe.
        Würde ``status`` das Zeitschloss zurücksetzen, liefe es nie ab.
        """
        with self._lock:
            if self._client is not None and self._verfallen():
                self._client = None
                self._benutzer = None
            angemeldet = self._client is not None
            return {
                "angemeldet": angemeldet,
                "benutzer": self._benutzer,
                "verfaellt_in": (
                    max(0, round(self._zuletzt + self._ablauf - self._zeit()))
                    if angemeldet else None
                ),
                "ablauf_sekunden": self._ablauf,
            }

    def _verfallen(self) -> bool:
        """Nur unter gehaltenem Lock aufrufen."""
        return self._zeit() - self._zuletzt >= self._ablauf

    def __repr__(self) -> str:
        """Ohne den Client - sein ``repr`` zeigt je nach Fassung Attribute.

        ``tests/test_refresh.py`` prüft, dass das Passwort in keinem Zustand
        des Programms auftaucht; ein voreiliges ``repr`` des Clients wäre genau
        der Weg, auf dem es das eines Tages doch täte.
        """
        zustand = "angemeldet" if self._client is not None else "abgemeldet"
        return f"<Anmeldung {zustand} benutzer={self._benutzer!r}>"
