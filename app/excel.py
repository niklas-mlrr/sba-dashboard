"""Zugriff auf die Arbeitsmappe - immer frisch laden, nie zwischen Anfragen halten.

Die Mappe liegt auf einem Netzlaufwerk und kann jederzeit in Excel geöffnet sein.
Ein im Speicher gehaltenes Workbook würde still veralten, deshalb lädt jede
Anfrage neu und merkt sich nur die Änderungszeit.

``data_only=False`` ist Pflicht: die Spalte "zu bestellen" enthält echte Formeln.
Mit ``data_only=True`` gelesen und wieder gespeichert wären sie unwiderruflich
durch ihren letzten berechneten Wert ersetzt.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook


class ExcelFehlt(FileNotFoundError):
    """Die Arbeitsmappe liegt unter keinem der eingetragenen Pfade."""


class BlattFehlt(KeyError):
    """Das erwartete Tabellenblatt fehlt in der Mappe."""


@dataclass(frozen=True)
class Dateizustand:
    pfad: Path
    mtime: float
    geaendert: datetime

    @classmethod
    def von(cls, pfad: Path) -> "Dateizustand":
        stat = pfad.stat()
        return cls(pfad=pfad, mtime=stat.st_mtime,
                   geaendert=datetime.fromtimestamp(stat.st_mtime))


def sperrdatei(pfad: Path) -> Path | None:
    """Die ``~$…``-Datei, die Excel beim Öffnen daneben legt - oder None."""
    kandidat = pfad.parent / f"~${pfad.name}"
    return kandidat if kandidat.exists() else None


def lade_mappe(pfad: Path):
    """Lädt die Mappe mit erhaltenen Formeln."""
    if not pfad.is_file():
        raise ExcelFehlt(f"Excel-Datei nicht gefunden: {pfad}")
    return load_workbook(str(pfad), data_only=False)


def raster_blatt(wb, blattname: str):
    if blattname not in wb.sheetnames:
        raise BlattFehlt(f"Tabellenblatt {blattname!r} fehlt in der Mappe.")
    return wb[blattname]
