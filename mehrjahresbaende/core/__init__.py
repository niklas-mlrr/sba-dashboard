"""Die Bibliothek hinter ``erzeuge_mehrjahresbaende.py`` und dem Reiter im Dashboard.

Nach dem Vorbild von ``bestand/core/`` und ``buecherlisten/core/``: das Skript
ist nur noch Kommandozeile, und ``app/`` importiert dieselben Funktionen.

* :mod:`.modelle` - die Begriffe: Marken, Zeilen, Spalten, Sonderfälle.
* :mod:`.laden` - ein Schuljahr aus der IServ-Ausleihe-API (nur GET).
* :mod:`.vergleich` - aus zwei Schuljahren die Marken rechnen. Ohne Netz.
* :mod:`.mappe` - dieselbe Übersicht als Exceldatei lesen und schreiben.
"""
from .laden import UnbekanntesSchuljahr, lade_schuljahr, vorjahr_kennung
from .mappe import (
    MappeUnlesbar,
    blatt,
    erlaubte_marken,
    lies_blatt,
    lies_uebersicht,
    schreibe_blatt,
    schreibe_datei,
    setze_marke,
)
from .modelle import (
    FESTE_MARKEN,
    Buchausgang,
    Buchvorkommen,
    Jahrgangsliste,
    Jahrgangszeile,
    Schuljahr,
    Sonderfall,
    Spalte,
    Uebersicht,
    Zelle,
)
from .vergleich import ZuVieleSonderfaelle, vergleiche

__all__ = [
    "FESTE_MARKEN",
    "Buchausgang",
    "Buchvorkommen",
    "Jahrgangsliste",
    "Jahrgangszeile",
    "MappeUnlesbar",
    "Schuljahr",
    "Sonderfall",
    "Spalte",
    "Uebersicht",
    "UnbekanntesSchuljahr",
    "Zelle",
    "ZuVieleSonderfaelle",
    "blatt",
    "erlaubte_marken",
    "lade_schuljahr",
    "lies_blatt",
    "lies_uebersicht",
    "schreibe_blatt",
    "schreibe_datei",
    "setze_marke",
    "vergleiche",
    "vorjahr_kennung",
]
