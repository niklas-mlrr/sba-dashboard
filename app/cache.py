"""Sidecar-Cache: Titel, ISBN und Preis der letzten IServ-Abfrage.

Die Arbeitsmappe kennt weder Titel noch ISBN einer Zeile - beides kommt aus
IServ. Damit die Tabelle auch ohne Abruf etwas anzeigt, legt der Refresh diese
Angaben neben die Mappe. Fehlt der Cache, bleiben die Spalten leer und die
Oberfläche sagt, dass sie erst nach dem ersten Abruf gefüllt sind.

Der Cache ist reine Anzeige. Keine Zahl der Tabelle wird je aus ihm gelesen.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CACHE_SUFFIX = ".dashboard-cache.json"


@dataclass(frozen=True)
class Eintrag:
    isbn: str | None = None
    titel: str | None = None
    preis: float | None = None


@dataclass(frozen=True)
class Cache:
    stand: datetime | None = None
    schuljahr: str | None = None
    eintraege: dict[str, Eintrag] = field(default_factory=dict)

    @property
    def leer(self) -> bool:
        return not self.eintraege

    def get(self, key: str) -> Eintrag:
        return self.eintraege.get(key, Eintrag())


def cache_pfad(excel_pfad: Path) -> Path:
    return excel_pfad.parent / f"{excel_pfad.stem}{CACHE_SUFFIX}"


def laden(excel_pfad: Path) -> Cache:
    """Liest den Sidecar-Cache; ein fehlender oder kaputter Cache ist kein Fehler."""
    pfad = cache_pfad(excel_pfad)
    try:
        with open(pfad, encoding="utf-8") as handle:
            roh = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return Cache()
    stand = roh.get("stand")
    return Cache(
        stand=datetime.fromisoformat(stand) if isinstance(stand, str) else None,
        schuljahr=roh.get("schuljahr"),
        eintraege={
            key: Eintrag(isbn=wert.get("isbn"), titel=wert.get("titel"), preis=wert.get("preis"))
            for key, wert in (roh.get("eintraege") or {}).items()
            if isinstance(wert, dict)
        },
    )


def speichern(excel_pfad: Path, cache: Cache) -> Path:
    pfad = cache_pfad(excel_pfad)
    inhalt = {
        "stand": cache.stand.isoformat() if cache.stand else None,
        "schuljahr": cache.schuljahr,
        "eintraege": {
            key: {"isbn": e.isbn, "titel": e.titel, "preis": e.preis}
            for key, e in cache.eintraege.items()
        },
    }
    pfad.write_text(json.dumps(inhalt, ensure_ascii=False, indent=2), encoding="utf-8")
    return pfad
