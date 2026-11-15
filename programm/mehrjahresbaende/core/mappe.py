"""Die Übersicht als Exceldatei lesen und schreiben - in der Struktur von Hand.

Die Datei ist der **Rückfall**: fällt das Dashboard aus, soll die Übersicht
weiter dort liegen, wo sie seit Jahren liegt, und beim Öffnen genauso aussehen.
Deshalb wird sie nicht als Rohdatenblatt geschrieben, sondern mit dem Aufbau
der von Hand gepflegten Fassung:

======  ========================================================================
Zeile   Inhalt
======  ========================================================================
1       A leer (nur Rahmen), darüber je Aufgabenfeld eine verbundene Kopfzelle
2       Fachnamen, um 90 Grad gedreht
3..     je Jahrgang eine Zeile: Marken je Fach **oder** ein verbundener Hinweis
dann    die Legende, je Eintrag eine über die ganze Breite verbundene Zeile
zuletzt eine Zeile, die sagt, woraus die Übersicht erzeugt wurde
======  ========================================================================

Die Gestaltung wird **gerechnet**, nicht aus der alten Datei geklont: Spalten
kommen und gehen (ein neues Fach, ein Fach ohne Aufgabenfeld), und ein
geklonter Stil aus Spalte F passt dann an keiner Stelle mehr. Die Regeln sind
aus der vorhandenen Datei abgelesen: ungerade Zeilen grau hinterlegt, links
dick, zwischen den Fächern gestrichelt, am Anfang eines Aufgabenfelds mittel.

Kein Schloss, kein ``mtime``-Vergleich, kein Backup: das steht im Dashboard
(``app/mehrjahresbaende.py``), weil es dort schon für die Bestandsmappe steht.
Hier liegt nur, was eine Arbeitsmappe zur Übersicht macht.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from bestand.core import atomic_save_workbook

from .modelle import (
    FESTE_MARKEN,
    OHNE_AUFGABENFELD,
    Jahrgangszeile,
    Sonderfall,
    Spalte,
    Uebersicht,
    Zelle,
)

BLATT = "Tabelle1"

# Die Zeile, die im Dateikopf über der Jahrgangsspalte steht: nichts. Sie hat
# nur den Rahmen, damit die Tabelle oben links geschlossen aussieht.
_ERSTE_DATENZEILE = 3

_JAHRGANG = re.compile(r"^\s*Jahrgang\s+(\d+)\s*$")
_LEGENDE = re.compile(r"^\s*(?P<marke>\(frei\)|---|[A-Z])\s*=\s*(?P<text>.+?)\s*$")
_HERKUNFT = re.compile(
    r"^\s*Erzeugt am (?P<wann>[\d.]+|\?) aus den Bücherlisten (?P<alt>.+?)\s*→\s*(?P<neu>.+?)\s*$"
)

_FREI_ANZEIGE = "(frei)"

# Aus der vorhandenen Datei abgelesen: Calibri 11, Textfarbe Theme 1, graue
# Hinterlegung als Theme 0 mit Tönung -0,25.
_SCHRIFT = Font(name="Calibri", size=11)
_GRAU = PatternFill(fill_type="solid", start_color="FFD9D9D9", end_color="FFD9D9D9")
_LEER = PatternFill(fill_type=None)

_DICK = Side(style="thick")
_MITTEL = Side(style="medium")
_DUENN = Side(style="thin")
_STRICH = Side(style="dashed")

_MITTE = Alignment(horizontal="center", vertical="center")
_GEDREHT = Alignment(horizontal="center", vertical="center", text_rotation=90)

_BREITE_JAHRGANG = 10.71
_BREITE_FACH = 5.14
_HOEHE_FACHZEILE = 96.0


class MappeUnlesbar(ValueError):
    """Die Datei hat nicht den Aufbau einer Mehrjahresbände-Übersicht."""


# ── Lesen ────────────────────────────────────────────────────────────────────


def blatt(wb: Workbook) -> Worksheet:
    return wb[BLATT] if BLATT in wb.sheetnames else wb.worksheets[0]


def _breite(ws: Worksheet) -> int:
    """Wie viele Fachspalten das Blatt hat - nach den Namen in Zeile 2."""
    spalte = 2
    while ws.cell(2, spalte).value not in (None, ""):
        spalte += 1
    return spalte - 2


def _aufgabenfelder(ws: Worksheet, anzahl: int) -> dict[int, str]:
    """Spaltennummer → Aufgabenfeld, aufgelöst über die Zellverbünde in Zeile 1."""
    felder: dict[int, str] = {}
    for verbund in ws.merged_cells.ranges:
        if verbund.min_row != 1 or verbund.max_row != 1:
            continue
        wert = ws.cell(1, verbund.min_col).value
        if not wert:
            continue
        for spalte in range(verbund.min_col, verbund.max_col + 1):
            felder[spalte] = str(wert)
    for spalte in range(2, 2 + anzahl):
        wert = ws.cell(1, spalte).value
        if spalte not in felder and wert:
            felder[spalte] = str(wert)
    return felder


def _hinweiszeile(ws: Worksheet, zeile: int) -> str:
    """Der Text einer über die Fachspalten verbundenen Zeile - oder ""."""
    for verbund in ws.merged_cells.ranges:
        if verbund.min_row == zeile == verbund.max_row and verbund.min_col == 2:
            return str(ws.cell(zeile, 2).value or "")
    return ""


def lies_blatt(ws: Worksheet) -> Uebersicht:
    """Liest die Übersicht aus einem Blatt. Die Bücher je Zelle stehen nicht darin.

    Was die Datei nicht trägt, kann sie nicht zurückgeben: welche Titel hinter
    einer Marke stehen, weiß nur der Vergleich. Für die Sonderfälle steht es
    dafür ausgeschrieben in der Legende - die kommt vollständig mit.
    """
    anzahl = _breite(ws)
    if anzahl == 0:
        raise MappeUnlesbar("In Zeile 2 steht kein einziger Fachname.")
    felder = _aufgabenfelder(ws, anzahl)
    spalten = tuple(
        Spalte(fach=str(ws.cell(2, spalte).value),
               aufgabenfeld=felder.get(spalte) or OHNE_AUFGABENFELD)
        for spalte in range(2, 2 + anzahl)
    )

    zeilen: list[Jahrgangszeile] = []
    sonderfaelle: list[Sonderfall] = []
    alt = neu = ""
    erzeugt: date | None = None

    for nummer in range(_ERSTE_DATENZEILE, ws.max_row + 1):
        roh = ws.cell(nummer, 1).value
        text = str(roh).strip() if roh is not None else ""
        if not text:
            continue
        treffer = _JAHRGANG.match(text)
        if treffer:
            hinweis = _hinweiszeile(ws, nummer)
            if hinweis:
                zeilen.append(Jahrgangszeile(jahrgang=int(treffer.group(1)), hinweis=hinweis))
                continue
            zellen = tuple(
                Zelle(fach=spalten[versatz].fach,
                      marke=str(ws.cell(nummer, 2 + versatz).value or "").strip())
                for versatz in range(anzahl)
            )
            zeilen.append(Jahrgangszeile(jahrgang=int(treffer.group(1)), zellen=zellen))
            continue
        herkunft = _HERKUNFT.match(text)
        if herkunft:
            alt, neu = herkunft.group("alt"), herkunft.group("neu")
            try:
                erzeugt = datetime.strptime(herkunft.group("wann"), "%d.%m.%Y").date()
            except ValueError:
                erzeugt = None
            continue
        eintrag = _LEGENDE.match(text)
        if eintrag and eintrag.group("marke") not in (_FREI_ANZEIGE, "---", "X", "B"):
            sonderfaelle.append(
                Sonderfall(buchstabe=eintrag.group("marke"), text=eintrag.group("text"))
            )

    return Uebersicht(
        spalten=spalten, zeilen=tuple(zeilen), sonderfaelle=tuple(sonderfaelle),
        schuljahr_alt=alt, schuljahr_neu=neu, erzeugt=erzeugt,
    )


def lies_uebersicht(pfad: Path) -> Uebersicht:
    """Öffnet die Datei und liest ihr erstes (bzw. ``Tabelle1``) Blatt."""
    return lies_blatt(blatt(load_workbook(str(pfad), data_only=True)))


# ── Schreiben ────────────────────────────────────────────────────────────────


def _rahmen(*, links: Side | None, rechts: Side | None,
            oben: Side | None = _DUENN, unten: Side | None = _DUENN) -> Border:
    return Border(left=links, right=rechts, top=oben, bottom=unten)


def _setze(ws: Worksheet, zeile: int, spalte: int, wert: object, *,
           rahmen: Border, ausrichtung: Alignment | None = None) -> None:
    zelle = ws.cell(zeile, spalte)
    zelle.value = wert
    zelle.font = _SCHRIFT
    zelle.border = rahmen
    zelle.fill = _GRAU if zeile % 2 else _LEER
    if ausrichtung is not None:
        zelle.alignment = ausrichtung


def _leeren(ws: Worksheet) -> None:
    """Macht das Blatt leer, behält aber Name und Position in der Mappe."""
    for verbund in list(ws.merged_cells.ranges):
        ws.unmerge_cells(str(verbund))
    if ws.max_row:
        ws.delete_rows(1, ws.max_row)
    ws.column_dimensions.clear()
    ws.row_dimensions.clear()


def schreibe_blatt(ws: Worksheet, uebersicht: Uebersicht) -> None:
    """Schreibt die ganze Übersicht neu - Werte **und** Gestaltung.

    Bewusst das ganze Blatt und nicht nur die geänderten Zellen: die Spalten
    können sich verschoben haben, und ein halb aktualisiertes Blatt wäre die
    Fassung, der man am wenigsten ansieht, woran man ist.
    """
    _leeren(ws)
    spalten = uebersicht.spalten
    letzte = 1 + len(spalten)

    def rechts_von(versatz: int) -> Side:
        return _DICK if versatz == len(spalten) - 1 else _STRICH

    def links_von(versatz: int) -> Side:
        vorher = spalten[versatz - 1].aufgabenfeld if versatz else None
        return _STRICH if vorher == spalten[versatz].aufgabenfeld else _MITTEL

    # Zeile 1: die Ecke bleibt leer, darüber je Aufgabenfeld eine Kopfzelle.
    _setze(ws, 1, 1, None, rahmen=_rahmen(links=_DICK, rechts=None, oben=_DICK))
    versatz = 0
    while versatz < len(spalten):
        feld = spalten[versatz].aufgabenfeld
        ende = versatz
        while ende + 1 < len(spalten) and spalten[ende + 1].aufgabenfeld == feld:
            ende += 1
        for innen in range(versatz, ende + 1):
            _setze(ws, 1, 2 + innen, feld if innen == versatz else None,
                   rahmen=_rahmen(links=links_von(innen), rechts=rechts_von(innen), oben=_DICK),
                   ausrichtung=_MITTE)
        if ende > versatz:
            ws.merge_cells(start_row=1, start_column=2 + versatz, end_row=1, end_column=2 + ende)
        versatz = ende + 1

    # Zeile 2: die Fachnamen, gedreht wie in der Vorlage.
    _setze(ws, 2, 1, None, rahmen=_rahmen(links=_DICK, rechts=None))
    for versatz, spalte in enumerate(spalten):
        _setze(ws, 2, 2 + versatz, spalte.fach,
               rahmen=_rahmen(links=links_von(versatz), rechts=rechts_von(versatz)),
               ausrichtung=_GEDREHT)
    ws.row_dimensions[2].height = _HOEHE_FACHZEILE

    zeile = _ERSTE_DATENZEILE
    for eintrag in uebersicht.zeilen:
        _setze(ws, zeile, 1, eintrag.name, rahmen=_rahmen(links=_DICK, rechts=None))
        if eintrag.hinweis:
            for versatz in range(len(spalten)):
                _setze(ws, zeile, 2 + versatz, eintrag.hinweis if versatz == 0 else None,
                       rahmen=_rahmen(links=None, rechts=rechts_von(versatz)),
                       ausrichtung=_MITTE)
            if len(spalten) > 1:
                ws.merge_cells(start_row=zeile, start_column=2, end_row=zeile, end_column=letzte)
        else:
            for versatz, spalte in enumerate(spalten):
                zellwert = eintrag.zelle(spalte.fach)
                _setze(ws, zeile, 2 + versatz, (zellwert.marke or None) if zellwert else None,
                       rahmen=_rahmen(links=links_von(versatz), rechts=rechts_von(versatz)),
                       ausrichtung=_MITTE)
        zeile += 1

    texte = list(uebersicht.legende) + ([uebersicht.herkunft] if uebersicht.herkunft else [])
    for nummer, text in enumerate(texte):
        oben = _MITTEL if nummer == 0 else _DUENN
        unten = _DICK if nummer == len(texte) - 1 else _DUENN
        _setze(ws, zeile, 1, text,
               rahmen=_rahmen(links=_DICK, rechts=None, oben=oben, unten=unten),
               ausrichtung=_MITTE)
        for versatz in range(len(spalten)):
            _setze(ws, zeile, 2 + versatz, None,
                   rahmen=_rahmen(links=None, rechts=rechts_von(versatz), oben=oben, unten=unten))
        if letzte > 1:
            ws.merge_cells(start_row=zeile, start_column=1, end_row=zeile, end_column=letzte)
        zeile += 1

    ws.column_dimensions["A"].width = _BREITE_JAHRGANG
    for versatz in range(len(spalten)):
        ws.column_dimensions[get_column_letter(2 + versatz)].width = _BREITE_FACH


def setze_marke(ws: Worksheet, jahrgang: int, fach: str, marke: str) -> str:
    """Ändert genau eine Zelle. Gibt den Zellbezug zurück (für die Antwort).

    Sucht Zeile und Spalte über ihre Beschriftung, nicht über einen gemerkten
    Bezug: wer die Datei zwischendurch in Excel um eine Zeile verschoben hat,
    soll trotzdem die richtige Zelle treffen - oder gar keine.
    """
    anzahl = _breite(ws)
    faecher = [str(ws.cell(2, 2 + versatz).value) for versatz in range(anzahl)]
    if fach not in faecher:
        raise MappeUnlesbar(f"Die Übersicht hat keine Spalte „{fach}“.")
    spalte = 2 + faecher.index(fach)

    for nummer in range(_ERSTE_DATENZEILE, ws.max_row + 1):
        roh = ws.cell(nummer, 1).value
        treffer = _JAHRGANG.match(str(roh).strip()) if roh is not None else None
        if treffer and int(treffer.group(1)) == jahrgang:
            if _hinweiszeile(ws, nummer):
                raise MappeUnlesbar(
                    f"Jahrgang {jahrgang} leiht individuell aus; dort steht ein Hinweis "
                    "statt einzelner Marken."
                )
            zelle = ws.cell(nummer, spalte)
            zelle.value = marke or None
            return str(zelle.coordinate)
    raise MappeUnlesbar(f"Die Übersicht hat keine Zeile für Jahrgang {jahrgang}.")


def erlaubte_marken(uebersicht: Uebersicht) -> tuple[str, ...]:
    """Die festen Marken plus die Buchstaben, die in dieser Datei vergeben sind."""
    return FESTE_MARKEN + tuple(fall.buchstabe for fall in uebersicht.sonderfaelle)


def neue_mappe() -> Workbook:
    """Eine leere Mappe mit dem Blatt, das die Übersicht erwartet."""
    wb = Workbook()
    wb.worksheets[0].title = BLATT
    return wb


def schreibe_datei(pfad: Path, uebersicht: Uebersicht, *, backup_ordner: Path | None = None) -> Path | None:
    """Schreibt die Übersicht in ``pfad`` - atomar, mit optionaler Sicherung.

    Existiert die Datei, wird ihre Mappe geöffnet und ihr Blatt überschrieben
    (Blattname und alles, was sonst noch in der Mappe liegt, bleiben erhalten).
    Existiert sie nicht, entsteht sie neu.
    """
    if pfad.is_file():
        wb = load_workbook(str(pfad))
        ws = blatt(wb)
    else:
        wb = neue_mappe()
        ws = wb.worksheets[0]
    schreibe_blatt(ws, uebersicht)
    if not pfad.is_file():
        wb.save(str(pfad))
        return None
    return atomic_save_workbook(wb, pfad, backup_dir=backup_ordner)
