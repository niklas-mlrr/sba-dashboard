"""Das Programmfenster: anmelden, Seite öffnen, beenden, einstellen.

## Warum es das gibt

Bis 2026-09-10 bestand die Bedienung aus einem Konsolenfenster und einem
Browser-Tab. Wer den Tab versehentlich schloss, hatte keinen bedienbaren Weg
mehr, den Server zu beenden - nur noch "das schwarze Fenster zuklappen", was auf
dem Schul-Laptop niemand als Beenden erkennt. Und sobald die Konsole gar nicht
mehr aufgeht (ein späterer Schritt, siehe ``docs/roadmap.md``), wäre überhaupt
kein Bedienelement übrig.

## Wie es mit dem Server redet: über HTTP, wie der Browser

Das Fenster fasst **keine** internen Objekte der Anwendung an - es stellt
dieselben HTTP-Anfragen an ``127.0.0.1``, die auch die Seite stellt. Das hat drei
Gründe, und der dritte ist der wichtigste:

1. Die Prüfungen und die deutschen Fehlertexte liegen damit weiter an genau einer
   Stelle (``app/api/``, ``app/fehler.py``) und nicht ein zweites Mal hier.
2. Der Server läuft in einem anderen Thread (siehe ``app/start.py``); ein
   Aufruf über HTTP braucht dafür keine Absprache.
3. Die Logik ist ohne tkinter prüfbar: :class:`Fenstersteuerung` kennt nur eine
   URL und gibt Texte zurück. ``tests/test_fenster.py`` hängt sie an einen
   ``TestClient`` und braucht keinen Bildschirm - auf dem Entwicklungsrechner
   gibt es keinen, und in der CI auch nicht.

Benutzt wird ``urllib.request`` aus der Standardbibliothek und nicht
``requests``. ``requests`` ist hier keine direkte Abhängigkeit (es kommt über die
Geschwister-Repos mit), und ``requirements.txt`` ist erzeugt und wird in der CI
gegen ``uv export`` geprüft - eine neue Laufzeitabhängigkeit für fünf POSTs wäre
der teuerste aller Wege.

## Das Passwort

Es geht vom Eingabefeld direkt in die Anfrage und wird danach im Feld **und** in
seiner ``StringVar`` überschrieben. Gehalten wird es einzig im IServ-Client im
Server-Prozess, der es für eine spätere Neuanmeldung braucht; warum das
unvermeidlich ist und was das Zeitschloss daran ändert, steht in
``app/sitzung.py``.
"""
from __future__ import annotations

import json
import queue
import threading
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from typing import Any, Callable

ZEITGRENZE = 30.0  # Sekunden. Die Anmeldung geht über IServ ins Netz.
STATUS_TAKT_MS = 15_000  # Wie oft die Statuszeile nachfragt.
START_TAKT_MS = 100  # Wie oft das Fenster beim Start nach dem Server sieht.


class FensterFehler(RuntimeError):
    """Eine Anfrage ans eigene Backend ist gescheitert - mit Klartext für die Zeile."""


@dataclass(frozen=True)
class Antwort:
    """Eine HTTP-Antwort, soweit das Fenster sie braucht."""

    status: int
    koerper: dict[str, Any]

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def fehlertext(self) -> str:
        """Der Klartext des Servers - oder ein eigener, wenn er keinen schickte.

        Jede Fehlerantwort des Dashboards hat die Form
        ``{"fehler": "<deutscher Klartext>"}`` (``app/fehler.py``). Dass dieses
        Feld fehlt, wäre ein Fehler im Server; die Zeile darf deswegen trotzdem
        nicht leer bleiben.
        """
        text = self.koerper.get("fehler")
        if isinstance(text, str) and text.strip():
            return text
        return f"Unerwartete Antwort des Servers (Status {self.status})."


def _anfrage(url: str, methode: str, koerper: dict[str, Any] | None) -> Antwort:
    """Eine JSON-Anfrage an die eigene Adresse. Wirft nur :class:`FensterFehler`."""
    daten = json.dumps(koerper).encode("utf-8") if koerper is not None else None
    anfrage = urllib.request.Request(url, data=daten, method=methode)
    if daten is not None:
        anfrage.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(anfrage, timeout=ZEITGRENZE) as antwort:
            roh = antwort.read()
            status = antwort.status
    except urllib.error.HTTPError as exc:
        # Eine Fehlerantwort ist keine Ausnahme, sondern die Auskunft selbst:
        # 401 "bitte anmelden", 400 "Ordner nicht gefunden". Der Körper steht
        # am HTTPError und wird hier genauso gelesen wie eine 200er-Antwort.
        roh = exc.read()
        status = exc.code
    except urllib.error.URLError as exc:
        raise FensterFehler(
            f"Der Server im Hintergrund antwortet nicht ({exc.reason}). "
            "Bitte das Programm beenden und neu starten."
        ) from exc
    except OSError as exc:
        raise FensterFehler(f"Verbindung zum Server im Hintergrund gestört: {exc}") from exc

    try:
        geparst = json.loads(roh.decode("utf-8")) if roh else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        geparst = {}
    return Antwort(status=status, koerper=geparst if isinstance(geparst, dict) else {})


class Fenstersteuerung:
    """Alles, was das Fenster tut - ohne eine Zeile tkinter.

    ``anfrage`` ist einsetzbar, damit die Tests einen ``TestClient`` einhängen
    können statt einen echten Server zu starten.
    """

    def __init__(
        self,
        url: str,
        *,
        anfrage: Callable[[str, str, dict[str, Any] | None], Antwort] = _anfrage,
        browser_oeffnen: Callable[[str], Any] = webbrowser.open,
        seite_nach_anmeldung: bool = False,
    ) -> None:
        self.url = url.rstrip("/") + "/"
        self._anfrage = anfrage
        self._browser_oeffnen = browser_oeffnen
        self._seite_nach_anmeldung = seite_nach_anmeldung
        # Ob die Seite in diesem Lauf schon aufging, per Knopf oder nach der
        # Anmeldung. Eine Neuanmeldung nach dem Zeitschloss soll keinen zweiten
        # Tab neben den ersten legen.
        self.seite_geoeffnet = False

    def _ruf(self, pfad: str, methode: str = "GET",
             koerper: dict[str, Any] | None = None) -> Antwort:
        return self._anfrage(self.url + pfad.lstrip("/"), methode, koerper)

    # ── Anmeldung ────────────────────────────────────────────────────────────

    def anmelden(self, benutzer: str, passwort: str) -> str:
        """Meldet an. Gibt die Zeile zurück, die das Fenster anzeigt.

        Prüft die leeren Felder selbst, obwohl der Server das auch täte: ein
        Klick auf "Anmelden" mit leeren Feldern soll nicht erst eine Anfrage
        auslösen, deren Antwort dasselbe sagt.

        Mit ``seite_nach_anmeldung`` öffnet die erste erfolgreiche Anmeldung die
        Seite im Browser: beim Start kommt zuerst nur das Fenster, damit die
        Seite nicht vor der Anmeldung aufgeht und dort ein Abruf scheitert.
        """
        if not benutzer.strip() or not passwort:
            raise FensterFehler("Bitte IServ-Benutzername und Passwort eingeben.")
        antwort = self._ruf(
            "api/anmeldung", "POST", {"benutzer": benutzer.strip(), "passwort": passwort},
        )
        if not antwort.ok:
            raise FensterFehler(antwort.fehlertext)
        if self._seite_nach_anmeldung and not self.seite_geoeffnet:
            self.seite_oeffnen()
        return self.statuszeile(antwort.koerper)

    def abmelden(self) -> str:
        antwort = self._ruf("api/anmeldung", "DELETE")
        if not antwort.ok:
            raise FensterFehler(antwort.fehlertext)
        return self.statuszeile(antwort.koerper)

    def anmeldestatus(self) -> dict[str, Any]:
        antwort = self._ruf("api/anmeldung")
        if not antwort.ok:
            raise FensterFehler(antwort.fehlertext)
        return antwort.koerper

    @staticmethod
    def statuszeile(status: dict[str, Any]) -> str:
        """Der angezeigte Satz zum Anmeldestand.

        Die Restzeit wird in Minuten **aufgerundet** angezeigt: "verfällt in
        0 Minuten" wäre für 20 Sekunden Restzeit die unfreundlichste aller
        wahren Aussagen.
        """
        if not status.get("angemeldet"):
            return "Nicht angemeldet. Ein Abruf ist erst nach der Anmeldung möglich."
        benutzer = status.get("benutzer") or "unbekannt"
        rest = status.get("verfaellt_in")
        if not isinstance(rest, (int, float)):
            return f"Angemeldet als {benutzer}."
        minuten = max(1, -(-int(rest) // 60))
        return f"Angemeldet als {benutzer} — verfällt in {minuten} Minuten ohne Abruf."

    # ── Einstellungen ────────────────────────────────────────────────────────

    def einstellungen(self) -> dict[str, Any]:
        antwort = self._ruf("api/einstellungen")
        if not antwort.ok:
            raise FensterFehler(antwort.fehlertext)
        return antwort.koerper

    def speichere_einstellungen(self, server: str, ordner: str) -> str:
        """Speichert Server und Ordner. Gibt die Zeile mit der gefundenen Mappe zurück."""
        antwort = self._ruf(
            "api/einstellungen", "POST", {"server": server.strip(), "ordner": ordner.strip()},
        )
        if not antwort.ok:
            raise FensterFehler(antwort.fehlertext)
        mappe = antwort.koerper.get("mappe")
        return f"Gespeichert. Verwendet wird: {mappe}" if mappe else "Gespeichert."

    @staticmethod
    def mappenzeile(einstellungen: dict[str, Any]) -> str:
        """Welche Mappe gerade gilt - oder wo vergeblich gesucht wurde."""
        mappe = einstellungen.get("mappe")
        if isinstance(mappe, str) and mappe:
            return mappe
        geprueft = einstellungen.get("geprueft") or []
        if geprueft:
            return f"keine gefunden (geprüft: {', '.join(str(p) for p in geprueft)})"
        return "keine gefunden"

    # ── Seite und Beenden ────────────────────────────────────────────────────

    def seite_oeffnen(self) -> None:
        self._browser_oeffnen(self.url)
        self.seite_geoeffnet = True

    def beenden(self) -> str:
        """Fährt den Server herunter.

        Eine abgebrochene Verbindung ist hier **Erfolg**: der Server kann
        heruntergefahren sein, bevor er die Antwort noch losgeschickt hat. Die
        Oberfläche auf der Seite behandelt das genauso (``app/static/app.js``).
        """
        try:
            antwort = self._ruf("api/beenden", "POST")
        except FensterFehler:
            return "Das Dashboard wurde beendet."
        if not antwort.ok:
            raise FensterFehler(antwort.fehlertext)
        return "Das Dashboard wurde beendet."


class Startlauf:
    """Fährt den Server in einem Nebenthread hoch und hält das Ergebnis bereit.

    Ohne tkinter, damit die Übergabe zwischen den Threads prüfbar bleibt: das
    Fenster fragt :meth:`ergebnis` in seinem Takt ab, statt dass der Nebenthread
    selbst in Tk hineinruft.
    """

    def __init__(self, hochfahren: Callable[[], str]) -> None:
        self._ablage: queue.Queue[str | FensterFehler] = queue.Queue(maxsize=1)
        self._thread = threading.Thread(target=self._lauf, args=(hochfahren,),
                                        name="sba-start", daemon=True)
        self._thread.start()

    def _lauf(self, hochfahren: Callable[[], str]) -> None:
        try:
            self._ablage.put(hochfahren())
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - jeder Fehler wird zur Zeile
            text = str(exc).strip() or f"Unerwarteter Fehler beim Start ({type(exc).__name__})."
            self._ablage.put(FensterFehler(text))

    def ergebnis(self) -> str | FensterFehler | None:
        """Die Adresse, der Fehler - oder ``None``, solange der Start noch läuft."""
        try:
            return self._ablage.get_nowait()
        except queue.Empty:
            return None

    def warte(self, zeitgrenze: float | None = None) -> None:
        self._thread.join(zeitgrenze)


# ── Die Tk-Hülle ──────────────────────────────────────────────────────────────
#
# Ab hier beginnt der Teil, der einen Bildschirm braucht. Er enthält bewusst
# keine Entscheidung mehr, nur Widgets und Weiterleitungen an die Steuerung
# oben - was er anzeigt, steht dort und ist dort geprüft.

def tkinter_verfuegbar() -> tuple[bool, str]:
    """Ob ein Fenster gebaut werden kann, und wenn nicht: warum nicht.

    Zwei Gründe kommen vor. Auf einem Linux-Rechner ohne Bildschirm (dem
    Entwicklungs-VPS, der CI) fehlt ``DISPLAY``; auf einem Python ohne Tk-Bindung
    scheitert der Import. Beides ist kein Fehler, sondern der Fall
    "dann eben ohne Fenster" - ``app/start.py`` macht daraus einen Hinweis.
    """
    import os
    import sys

    try:
        import tkinter  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - auch ein ImportError im C-Teil zählt
        return False, f"tkinter ist in diesem Python nicht verfügbar ({exc})."
    if sys.platform not in ("win32", "darwin") and not os.environ.get("DISPLAY"):
        return False, "Kein Bildschirm gefunden (DISPLAY ist nicht gesetzt)."
    return True, ""


def starte(hochfahren: Callable[[], str], *, version: str = "",
           seite_nach_anmeldung: bool = True) -> None:
    """Baut das Fenster und gibt erst zurück, wenn es geschlossen wurde.

    Das Fenster steht sofort und zeigt "Das Programm startet", während
    ``hochfahren`` im Nebenthread den Server aufbaut; es gibt die Adresse des
    lauschenden Servers zurück oder wirft mit Klartext. Erst danach werden die
    Knöpfe bedienbar.

    Muss auf dem **Hauptthread** laufen (Tk-Vorgabe); der Server läuft deshalb
    im Nebenthread, siehe ``app/start.py``.
    """
    from ._fenster_tk import Hauptfenster

    fenster = Hauptfenster(version=version)
    start = Startlauf(hochfahren)

    # Tk darf nur vom Hauptthread aus angefasst werden. Der Nebenthread legt
    # sein Ergebnis deshalb nur ab, und das Fenster holt es im eigenen Takt.
    def _pruefe() -> None:
        ergebnis = start.ergebnis()
        if ergebnis is None:
            fenster.wurzel.after(START_TAKT_MS, _pruefe)
        elif isinstance(ergebnis, str):
            fenster.bereit(Fenstersteuerung(ergebnis, seite_nach_anmeldung=seite_nach_anmeldung))
        else:
            fenster.startfehler(str(ergebnis))

    fenster.wurzel.after(START_TAKT_MS, _pruefe)
    fenster.laufen()
