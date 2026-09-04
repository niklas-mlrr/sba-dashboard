"""Der Startvorgang: freien Port suchen, Server binden, Browser öffnen.

Das steht hier und nicht in START.bat, weil Batch für "nimm den nächsten freien
Port" keine brauchbaren Mittel hat und ein fehlgeschlagenes ``netstat``-Parsing
auf dem Schul-Laptop niemand debuggt.

Gebunden wird ausschließlich an 127.0.0.1. Die Mappe enthält personenbezogene
Zahlen; im Schulnetz erreichbar wäre sie ein Datenschutzvorfall, kein Feature.
"""
from __future__ import annotations

import socket
import sys
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

    from .main import app, lade_einstellungen

    wurzel = Path(__file__).parent.parent
    try:
        einstellungen = lade_einstellungen(wurzel / "config.json")
    except Exception as exc:  # noqa: BLE001 - Klartext statt Traceback
        print(f"config.json ist unbrauchbar: {exc}")
        return 2

    port = freier_port(einstellungen.port)
    url = f"http://{HOST}:{port}/"

    print("=" * 58)
    print("  Schulbuchausleihe - Bestand und Nachbestellung")
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

    if "--kein-browser" not in (argv if argv is not None else sys.argv[1:]):
        oeffne_browser(url)

    server.run()
    print("\nBeendet. Dieses Fenster kann geschlossen werden.")
    return 0


if __name__ == "__main__":  # pragma: no cover - Einstiegspunkt
    raise SystemExit(main())
