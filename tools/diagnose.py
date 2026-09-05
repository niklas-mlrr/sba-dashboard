#!/usr/bin/env python3
"""Sammelt auf dem Schul-Laptop die Messwerte, nach denen sonst geraten wird.

Das Werkzeug ist ausdrücklich für den Fall gebaut, dass die Person am Gerät
nicht sagen kann, *warum* etwas nicht geht - sondern nur, dass es nicht geht.
Es prüft die Kette vom Betriebssystem bis zur Arbeitsmappe der Reihe nach und
schreibt einen Bericht, den man weitergeben kann.

Zwei Regeln, aus dem Fehlschlag des früheren Testskripts gelernt:

* **Eine Ja/Nein-Frage an einen Menschen ist keine Messung.** Hier wird nichts
  gefragt; jede Zeile des Berichts ist ein gemessener Wert.
* **Ein übersprungener Schritt ist kein Fehlschlag.** Fehlt eine Voraussetzung,
  steht ``übersprungen`` da, nicht ``FEHLGESCHLAGEN`` - sonst liest jemand einen
  Fehler, wo keiner ist.

Das Werkzeug schreibt **nie** in die Arbeitsmappe und braucht keine
IServ-Zugangsdaten. Es fasst nichts an, es sieht nur nach.

    python tools/diagnose.py                 # Bericht auf dem Bildschirm
    python tools/diagnose.py --datei b.txt   # zusätzlich in eine Datei
"""
from __future__ import annotations

import argparse
import os
import platform
import socket
import sys
from datetime import datetime
from pathlib import Path

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

OK = "ok"
WARNUNG = "Warnung"
FEHLER = "FEHLER"
UEBERSPRUNGEN = "übersprungen"


class Bericht:
    """Sammelt Befunde und weiß am Ende, ob etwas Ernstes dabei war."""

    def __init__(self) -> None:
        self.zeilen: list[tuple[str, str, str]] = []

    def notiere(self, bereich: str, stand: str, text: str) -> None:
        self.zeilen.append((bereich, stand, text))
        print(f"  [{stand:^12}] {bereich}: {text}")

    @property
    def hat_fehler(self) -> bool:
        return any(stand == FEHLER for _, stand, _ in self.zeilen)

    def als_text(self) -> str:
        kopf = [
            "SBA Dashboard - Diagnosebericht",
            f"erstellt: {datetime.now().isoformat(timespec='seconds')}",
            "",
        ]
        breite = max((len(b) for b, _, _ in self.zeilen), default=10)
        koerper = [f"[{stand:^12}] {bereich:<{breite}}  {text}" for bereich, stand, text in self.zeilen]
        schluss = ["", "FEHLER gefunden." if self.hat_fehler else "Kein harter Fehler gefunden."]
        return "\n".join(kopf + koerper + schluss) + "\n"


def _pruefe_system(bericht: Bericht) -> None:
    bericht.notiere("System", OK, f"{platform.platform()}")
    bericht.notiere("Python", OK, f"{sys.version.split()[0]} aus {sys.executable}")
    if sys.version_info < (3, 10):
        bericht.notiere("Python", FEHLER,
                        "Das Dashboard braucht mindestens Python 3.10.")
    try:
        from app import __version__
    except ImportError as exc:
        # Der Bericht soll gerade dann entstehen, wenn etwas nicht geht - der
        # fehlende Programmimport fällt woanders auf (Pakete, Konfiguration)
        # und bricht hier nur die Version ab, nicht den ganzen Bericht.
        bericht.notiere("Dashboard", UEBERSPRUNKEN, f"Version nicht ermittelbar: {exc}")
    else:
        bericht.notiere("Dashboard", OK, f"Version {__version__}")
    bericht.notiere("Benutzerprofil", OK, str(Path.home()))
    lokal = os.environ.get("LOCALAPPDATA") or "(nicht gesetzt)"
    bericht.notiere("LOCALAPPDATA", OK if lokal != "(nicht gesetzt)" else WARNUNG, lokal)


def _pruefe_pakete(bericht: Bericht) -> None:
    """Prüft, ob die Bibliotheken wirklich im venv liegen - nicht nur irgendwo."""
    for name in ("fastapi", "uvicorn", "jinja2", "openpyxl", "ausleihe", "bestand"):
        try:
            modul = __import__(name)
        except ImportError as exc:
            bericht.notiere(f"Paket {name}", FEHLER, f"nicht importierbar: {exc}")
            continue
        ort = getattr(modul, "__file__", None) or "(eingebaut)"
        if name not in ("ausleihe", "bestand"):
            bericht.notiere(f"Paket {name}", OK, str(ort))
            continue
        # Bei den beiden Geschwister-Bibliotheken ist die interessante Frage
        # nicht, wo die Dateien liegen, sondern ob sie *installiert* sind. Ein
        # editable-Install in der Entwicklung zeigt zu Recht auf den Quellbaum;
        # was auf dem Schul-Laptop nicht sein soll, ist ein Paket, das nur über
        # den Suchpfad gefunden wird und in keiner Installation steht.
        from importlib.metadata import PackageNotFoundError, distribution
        verteilung = {"ausleihe": "iserv-ausleihe-api", "bestand": "sba-bestand"}[name]
        try:
            distribution(verteilung)
        except PackageNotFoundError:
            bericht.notiere(f"Paket {name}", WARNUNG,
                            f"nicht ins venv installiert, nur über den Suchpfad gefunden "
                            f"({ort}). Auf dem Schul-Laptop erledigt das START.bat.")
        else:
            bericht.notiere(f"Paket {name}", OK, f"{verteilung} installiert, aus {ort}")
    if os.environ.get("PYTHONPATH"):
        bericht.notiere("PYTHONPATH", WARNUNG,
                        f"gesetzt auf {os.environ['PYTHONPATH']!r} - seit 2026-09-04 "
                        "nicht mehr nötig und eine mögliche Fehlerquelle.")
    else:
        bericht.notiere("PYTHONPATH", OK, "nicht gesetzt (so soll es sein)")


def _pruefe_konfiguration(bericht: Bericht):
    from app.paths import benutzer_konfigurationspfad
    from app.settings import Einstellungen

    standard = _WURZEL / "config.json"
    benutzer = benutzer_konfigurationspfad()
    bericht.notiere("Standard-config", OK if standard.is_file() else FEHLER, str(standard))
    bericht.notiere("Benutzer-config",
                    OK if benutzer.is_file() else UEBERSPRUNGEN,
                    f"{benutzer}{'' if benutzer.is_file() else ' (noch keine Auswahl gespeichert)'}")
    if not standard.is_file():
        return None
    try:
        einstellungen, hinweis = Einstellungen.laden_mit_benutzerkonfiguration(standard)
    except Exception as exc:  # noqa: BLE001 - Klartext statt Traceback
        bericht.notiere("Konfiguration", FEHLER, f"unbrauchbar: {exc}")
        return None
    if hinweis:
        bericht.notiere("Konfiguration", WARNUNG, hinweis)
    bericht.notiere("IServ-Domain", OK, einstellungen.iserv_domain)
    bericht.notiere("Blatt", OK, einstellungen.blatt_raster)
    return einstellungen


def _pruefe_mappe(bericht: Bericht, einstellungen) -> None:
    from app.excel import lade_mappe, raster_blatt, sperr_benutzer, sperrdatei

    gefunden = None
    for pfad, vorhanden in einstellungen.gepruefte_pfade():
        bericht.notiere("Pfadkandidat", OK if vorhanden else WARNUNG,
                        f"{pfad} {'(gefunden)' if vorhanden else '(nicht da)'}")
        if vorhanden and gefunden is None:
            gefunden = pfad
    if gefunden is None:
        bericht.notiere("Arbeitsmappe", FEHLER,
                        "Keiner der eingetragenen Pfade existiert. Meist heißt das: "
                        "das Netzlaufwerk ist nicht verbunden.")
        return

    if sperrdatei(gefunden) is not None:
        wer = sperr_benutzer(gefunden)
        bericht.notiere("Excel-Sperrdatei", WARNUNG,
                        f"~$-Datei liegt daneben{f' (von {wer})' if wer else ''}. "
                        "Sie allein blockiert nichts, kann aber verwaist sein.")

    try:
        wb = lade_mappe(gefunden)
    except Exception as exc:  # noqa: BLE001
        bericht.notiere("Arbeitsmappe", FEHLER, f"lässt sich nicht öffnen: {exc}")
        return
    bericht.notiere("Arbeitsmappe", OK, f"{gefunden} ({gefunden.stat().st_size // 1024} KB)")
    bericht.notiere("Blätter", OK, ", ".join(wb.sheetnames))

    fehlend = [b for b in (einstellungen.blatt_raster, "bestellt", "zu Bestellen")
               if b not in wb.sheetnames]
    if fehlend:
        bericht.notiere("Blätter", FEHLER, f"fehlen: {', '.join(fehlend)}")
        return

    from bestand.core import parse_grid
    try:
        grid = parse_grid(raster_blatt(wb, einstellungen.blatt_raster))
    except Exception as exc:  # noqa: BLE001
        bericht.notiere("Raster", FEHLER, f"nicht lesbar: {exc}")
        return
    bericht.notiere("Raster", OK if grid.entries else FEHLER,
                    f"{len(grid.entries)} Zeilen, {len(grid.blocked)} Sperrflächen")

    # Schreibbarkeit ohne zu schreiben: der Ordner muss eine Datei aufnehmen.
    probe = gefunden.parent / f".sba-dashboard-schreibprobe-{os.getpid()}"
    try:
        probe.write_bytes(b"x")
        probe.unlink()
        bericht.notiere("Ordner beschreibbar", OK, str(gefunden.parent))
    except OSError as exc:
        bericht.notiere("Ordner beschreibbar", FEHLER,
                        f"{gefunden.parent}: {exc}. Änderungen ließen sich nicht speichern.")

    from app import cache as cache_modul
    sidecar = cache_modul.cache_pfad(gefunden)
    lokal = cache_modul.cache_pfad_lokal(gefunden)
    bericht.notiere("Cache (geteilt)", OK if sidecar.is_file() else UEBERSPRUNGEN, str(sidecar))
    bericht.notiere("Cache (lokal)", OK if lokal.is_file() else UEBERSPRUNGEN, str(lokal))
    geladen = cache_modul.laden(gefunden)
    bericht.notiere("Cache-Inhalt", OK if not geladen.leer else UEBERSPRUNGEN,
                    f"{len(geladen.eintraege)} Einträge, Stand {geladen.stand or 'unbekannt'}")

    backups = gefunden.parent / "backups"
    anzahl = len(list(backups.glob("*.xlsx"))) if backups.is_dir() else 0
    bericht.notiere("Backups", OK if backups.is_dir() else UEBERSPRUNGEN,
                    f"{anzahl} Stück in {backups}")


def _pruefe_port(bericht: Bericht, einstellungen) -> None:
    """Nur 127.0.0.1 - ein Bind auf 0.0.0.0 löst die Firewall-Abfrage aus."""
    from app.start import HOST, VERSUCHE

    start = einstellungen.port if einstellungen is not None else 8765
    for port in range(start, start + VERSUCHE):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as pruefer:
            pruefer.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                pruefer.bind((HOST, port))
            except OSError:
                continue
            bericht.notiere("Freier Port", OK, f"{HOST}:{port}")
            return
    bericht.notiere("Freier Port", FEHLER,
                    f"{start} bis {start + VERSUCHE - 1} sind alle belegt. "
                    "Vermutlich laufen noch andere Fenster des Dashboards.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prüft die Umgebung des SBA-Dashboards.")
    parser.add_argument("--datei", type=Path, help="Bericht zusätzlich hierhin schreiben.")
    argumente = parser.parse_args(argv)

    print("SBA Dashboard - Diagnose")
    print("=" * 58)
    bericht = Bericht()
    _pruefe_system(bericht)
    _pruefe_pakete(bericht)
    einstellungen = None
    try:
        einstellungen = _pruefe_konfiguration(bericht)
        if einstellungen is not None:
            _pruefe_mappe(bericht, einstellungen)
    except ImportError as exc:
        bericht.notiere("Anwendung", FEHLER,
                        f"lässt sich nicht importieren ({exc}). Die Prüfungen der "
                        "Arbeitsmappe wurden übersprungen.")
    _pruefe_port(bericht, einstellungen)

    print("=" * 58)
    print("FEHLER gefunden." if bericht.hat_fehler else "Kein harter Fehler gefunden.")
    if argumente.datei:
        argumente.datei.write_text(bericht.als_text(), encoding="utf-8")
        print(f"Bericht geschrieben: {argumente.datei}")
    return 1 if bericht.hat_fehler else 0


if __name__ == "__main__":  # pragma: no cover - Einstiegspunkt
    raise SystemExit(main())
