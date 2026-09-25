"""Der Startvorgang: freien Port suchen, Server binden, Fenster öffnen.

Das steht hier und nicht in START.bat, weil Batch für "nimm den nächsten freien
Port" keine brauchbaren Mittel hat und ein fehlgeschlagenes ``netstat``-Parsing
auf dem Schul-Laptop niemand debuggt.

Gebunden wird ausschließlich an 127.0.0.1. Die Mappe enthält personenbezogene
Zahlen; im Schulnetz erreichbar wäre sie ein Datenschutzvorfall, kein Feature.

## Warum der Server im Nebenthread läuft

Tk **muss** auf dem Hauptthread laufen. Also läuft der Server in einem
Nebenthread und das Fenster im Hauptthread; geschlossen wird das Fenster, und
danach fährt der Server herunter.

uvicorn kommt damit von sich aus zurecht - es installiert seine Signalhandler
nur, wenn es auf dem Hauptthread läuft, und überspringt sie sonst. Strg+C in der
Konsole beendet den Prozess damit weiterhin, nur eben über die Ausnahme im
Hauptthread statt über den Handler.

## Warum das Fenster vor dem Server steht

Die Importe hinter dem Server (FastAPI, openpyxl, der IServ-Client) brauchen auf
einem Schul-Laptop mehrere Sekunden. In dieser Zeit wäre sonst nur das schwarze
Fenster zu sehen, und wer nichts sieht, klickt START.bat ein zweites Mal. Das
Fenster erscheint deshalb zuerst und sagt "Das Programm startet"; aufgebaut und
gestartet wird der Server derweil im Nebenthread (:func:`fenster.starte`).

Ohne Bildschirm (Entwicklungs-VPS, CI) oder mit ``--kein-fenster`` bleibt es beim
alten Ablauf: der Server läuft auf dem Hauptthread bis Strg+C.
"""
from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

from .fenster import tkinter_verfuegbar

HOST = "127.0.0.1"
VERSUCHE = 11  # config.port bis config.port + 10
SERVER_ZEITGRENZE = 30.0  # Sekunden, bis uvicorn lauschen muss


class Startfehler(RuntimeError):
    """Der Start scheiterte vor dem Server - mit Klartext für Konsole und Fenster."""


def freier_port(start: int, host: str = HOST, versuche: int = VERSUCHE) -> int:
    """Der erste freie Port ab ``start``.

    Ein belegter Port heißt meist: das Dashboard läuft schon in einem anderen
    Fenster. Deshalb wird ausgewichen statt abgebrochen - zwei Fenster sind
    harmlos, die Mappe schützt das optimistische Sperren.
    """
    for port in range(start, start + versuche):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as pruefer:
            pruefer.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                pruefer.bind((host, port))
            except OSError:
                continue
            return port
    raise SystemExit(
        f"Die Ports {start} bis {start + versuche - 1} sind alle belegt. "
        "Bitte alle anderen Fenster des Dashboards schließen und neu starten."
    )


def oeffne_browser(url: str, verzoegerung: float = 1.0) -> None:
    """Öffnet die Seite, sobald der Server voraussichtlich lauscht."""
    threading.Timer(verzoegerung, lambda: webbrowser.open(url)).start()


def baue_server(config_pfad: Path | None) -> tuple[Any, str]:
    """Konfiguration, Anwendung, Port und uvicorn-Server; gibt Server und Adresse zurück.

    Hier liegen die langsamen Importe. Mit Fenster läuft das deshalb im
    Nebenthread, während das Fenster schon steht.
    """
    import uvicorn

    from .konfiguration import lade_einstellungen
    from .main import create_app

    # None (kein --config) bedeutet Produktivmodus: ausgelieferter Standard
    # plus Benutzerkonfiguration im plattformabhängigen Ordner, siehe
    # lade_einstellungen. Erst mit explizitem --config PATH ist es der
    # Arbeitskopie-Modus ohne Overlay.
    try:
        einstellungen = lade_einstellungen(config_pfad)
    except Exception as exc:  # noqa: BLE001 - Klartext statt Traceback
        raise Startfehler(f"Konfiguration ist unbrauchbar: {exc}") from exc

    # Jede gestartete Anwendung erhält ihre Konfiguration und ihren eigenen
    # Abrufzustand. So beeinflussen zwei gestartete Fenster einander nicht.
    app = create_app(einstellungen=einstellungen, config_pfad=config_pfad)

    try:
        port = freier_port(einstellungen.port)
    except SystemExit as exc:
        raise Startfehler(str(exc)) from exc
    url = f"http://{HOST}:{port}/"

    server = uvicorn.Server(uvicorn.Config(
        app, host=HOST, port=port, log_level="warning", access_log=False,
    ))
    # Über diese Referenz beendet sich der Server aus /api/beenden selbst - der
    # Knopf im Fenster und der Knopf auf der Seite nehmen denselben Weg.
    app.state.server = server
    return server, url


def warte_auf_server(server: Any, lauf: threading.Thread,
                     zeitgrenze: float = SERVER_ZEITGRENZE) -> None:
    """Kehrt zurück, sobald uvicorn lauscht; wirft, wenn der Thread vorher endet.

    Erst danach darf das Fenster Einstellungen und Anmeldestand abfragen - sonst
    liefe seine erste Anfrage ins Leere und zeigte "Server antwortet nicht".
    """
    ende = time.monotonic() + zeitgrenze
    while not getattr(server, "started", False):
        if not lauf.is_alive():
            raise Startfehler(
                "Der Server ließ sich nicht starten. Die Ursache steht im "
                "schwarzen Fenster; bitte das Programm neu starten."
            )
        if time.monotonic() > ende:
            raise Startfehler(
                "Der Server startet nicht. Bitte das Programm beenden und neu starten."
            )
        time.sleep(0.05)


def _drucke_kopf(version: str) -> None:
    print("=" * 58)
    print("  Schulbuchausleihe - Bestand und Nachbestellung")
    print(f"  Version {version}")
    print("=" * 58)
    print()


def _drucke_hinweis(url: str, *, mit_fenster: bool, grund: str) -> None:
    print(f"  Die Seite laeuft unter:  {url}")
    print()
    if mit_fenster:
        print("  Bedient wird das Programm ueber sein eigenes Fenster:")
        print("  dort meldet man sich bei IServ an und beendet das Dashboard.")
    else:
        if grund:
            print(f"  Kein Programmfenster: {grund}")
        print("  Ohne Fenster gibt es keine Anmeldemaske - ein Abruf braucht")
        print("  dann ein POST auf /api/anmeldung. Zum Beenden: Strg+C.")
    print()


def main(argv: list[str] | None = None) -> int:
    from . import __version__

    parser = argparse.ArgumentParser(
        description="Startet das Schulbuchausleihe-Dashboard lokal."
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Pfad zu einer alternativen config.json, etwa für eine Arbeitskopie der Mappe.",
    )
    parser.add_argument(
        "--kein-browser",
        action="store_true",
        help="Öffnet keinen Browser automatisch (weder beim Start noch nach der Anmeldung).",
    )
    parser.add_argument(
        "--kein-fenster",
        action="store_true",
        help="Startet ohne Programmfenster; beendet wird dann mit Strg+C.",
    )
    argumente = parser.parse_args(argv)

    mit_fenster = not argumente.kein_fenster
    grund = ""
    if mit_fenster:
        mit_fenster, grund = tkinter_verfuegbar()

    _drucke_kopf(__version__)

    if not mit_fenster:
        try:
            server, url = baue_server(argumente.config)
        except Startfehler as exc:
            print(exc)
            return 2
        _drucke_hinweis(url, mit_fenster=False, grund=grund)
        # Ohne Fenster ist die Seite die einzige Oberfläche, also gleich auf.
        # Mit Fenster kommt zuerst die Anmeldung; die Seite öffnet das Fenster
        # nach der ersten erfolgreichen Anmeldung selbst (app/fenster.py).
        if not argumente.kein_browser:
            oeffne_browser(url)
        server.run()
        print("\nBeendet. Dieses Fenster kann geschlossen werden.")
        return 0

    from . import fenster

    # Was vom Start schon läuft, merkt sich ``gestartet``, damit das Aufräumen
    # unten es findet - auch wenn das Fenster mitten im Start zugeht.
    gestartet: dict[str, Any] = {}
    abgebrochen = threading.Event()

    def hochfahren() -> str:
        try:
            server, url = baue_server(argumente.config)
        except Startfehler as exc:
            gestartet["fehler"] = True
            print(exc)
            raise
        if abgebrochen.is_set():
            raise Startfehler("Der Start wurde abgebrochen.")
        _drucke_hinweis(url, mit_fenster=True, grund="")
        lauf = threading.Thread(target=server.run, name="sba-server", daemon=True)
        gestartet.update(server=server, lauf=lauf)
        lauf.start()
        warte_auf_server(server, lauf)
        return url

    try:
        fenster.starte(hochfahren, version=__version__,
                       seite_nach_anmeldung=not argumente.kein_browser)
    finally:
        # Auch wenn das Fenster mit einer Ausnahme endet: der Server darf den
        # Prozess nicht am Leben halten. Das Zuklappen des Fensters hat den
        # Server über /api/beenden meist schon angestoßen; dieses Setzen ist die
        # Absicherung für jeden anderen Weg hinaus.
        abgebrochen.set()
        if "server" in gestartet:
            gestartet["server"].should_exit = True
            gestartet["lauf"].join(timeout=10.0)
    print("\nBeendet. Dieses Fenster kann geschlossen werden.")
    return 2 if gestartet.get("fehler") else 0


if __name__ == "__main__":  # pragma: no cover - Einstiegspunkt
    raise SystemExit(main())
