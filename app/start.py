"""Der Startvorgang: freien Port suchen, Server binden, Browser öffnen.

Das steht hier und nicht in START.bat, weil Batch für "nimm den nächsten freien
Port" keine brauchbaren Mittel hat und ein fehlgeschlagenes ``netstat``-Parsing
auf dem Schul-Laptop niemand debuggt.

Gebunden wird ausschließlich an 127.0.0.1. Die Mappe enthält personenbezogene
Zahlen; im Schulnetz erreichbar wäre sie ein Datenschutzvorfall, kein Feature.
"""
from __future__ import annotations

import argparse
import socket
import threading
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"
VERSUCHE = 11  # config.port bis config.port + 10


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


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    from . import __version__
    from .konfiguration import lade_einstellungen
    from .main import create_app

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
        help="Öffnet keinen Browser automatisch.",
    )
    argumente = parser.parse_args(argv)

    # None (kein --config) bedeutet Produktivmodus: ausgelieferter Standard
    # plus Benutzerkonfiguration im plattformabhängigen Ordner, siehe
    # lade_einstellungen. Erst mit explizitem --config PATH ist es der
    # Arbeitskopie-Modus ohne Overlay.
    config_pfad = argumente.config
    try:
        einstellungen = lade_einstellungen(config_pfad)
    except Exception as exc:  # noqa: BLE001 - Klartext statt Traceback
        print(f"Konfiguration ist unbrauchbar: {exc}")
        return 2

    # Jede gestartete Anwendung erhält ihre Konfiguration und ihren eigenen
    # Abrufzustand. So beeinflussen zwei gestartete Fenster einander nicht.
    app = create_app(einstellungen=einstellungen, config_pfad=config_pfad)

    port = freier_port(einstellungen.port)
    url = f"http://{HOST}:{port}/"

    print("=" * 58)
    print("  Schulbuchausleihe - Bestand und Nachbestellung")
    print(f"  Version {__version__}")
    print("=" * 58)
    print()
    print(f"  Die Seite laeuft unter:  {url}")
    print()
    print("  DIESES FENSTER NICHT SCHLIESSEN, solange Sie arbeiten.")
    print("  Zum Beenden: den Knopf 'Beenden' auf der Seite benutzen")
    print("  oder dieses Fenster schliessen.")
    print()

    server = uvicorn.Server(uvicorn.Config(
        app, host=HOST, port=port, log_level="warning", access_log=False,
    ))
    # Über diese Referenz beendet sich der Server aus /api/beenden selbst.
    app.state.server = server

    if not argumente.kein_browser:
        oeffne_browser(url)

    server.run()
    print("\nBeendet. Dieses Fenster kann geschlossen werden.")
    return 0


if __name__ == "__main__":  # pragma: no cover - Einstiegspunkt
    raise SystemExit(main())
