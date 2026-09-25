"""Die Buchplanung als Exceldatei lesen und schreiben.

Die Datei ist der **Rückfall**: fällt das Dashboard aus - etwa nach einem
IServ-Update -, liegt der Stand weiter auf dem Gruppenlaufwerk und ist ohne
dieses Programm lesbar. Sie hat vier Blätter, und jedes trägt genau einen
Schlüssel:

======================  ==========================  =========================
Blatt                   Schlüssel                   eintragbar
======================  ==========================  =========================
``Buchreihen``          ISBN                        Bemerkung
``Fächer & Jahrgang``   (ISBN, Fach, Jahrgang)      Einführung, Ausmusterung,
                                                    Kürzel, Datum, Bemerkung
``Rücklage``            (ISBN, Fach)                Anzahl, Kürzel, Datum,
                                                    Status, Bemerkung
``Info``                -                           nichts
======================  ==========================  =========================

Bis 2026-09-20 standen die Bücher dreimal in der Mappe, einmal je Achse
(Verlag, Fach, Jahrgang), dazu ein eigenes Blatt für die Fachbestätigung. Die
Titel stehen jetzt **einmal**, auf ``Buchreihen``; die beiden anderen Blätter
tragen nur noch ihren Schlüssel und das, was dazu eingetragen wird. Die
Bestätigung der Fachkonferenzleitung steht als Kürzel und Datum in der Zeile,
die sie bestätigt.

Unverändert gilt die Regel, die die Mappe widerspruchsfrei hält:

    Aus jedem Blatt wird nur seine eigene Eintragungs-Spalte zurückgelesen;
    alles andere wird bei jedem Schreiben neu gesetzt.

Wer also auf ``Buchreihen`` einen Titel überschreibt, ändert nichts - beim
nächsten Abgleich steht dort wieder, was IServ sagt. Die eine Ausnahme sind
**Korrekturen** aus dem Planungsmenü (seit 2026-09-24): eine korrigierte Zelle
bei Titel, Verlag, Neupreis oder Leihpreis ist hell hinterlegt und trägt den
IServ-Wert als Kommentar („in IServ: 22,50 €“). Der Kommentar ist die
Markierung - eine Zelle mit ihm behält beim Abgleich ihren Wert, eine ohne ihn
bekommt den aus IServ. Ein eigenes Blatt dafür gab es nur für einen Tag; seit
die ISBN im Menü nicht mehr änderbar ist, hat jede Korrektur ihre Zeile
schon. Dieselbe Regel liegt
schon ``mehrjahresbaende/core/mappe.py`` zugrunde, das sein Blatt ebenfalls
immer vollständig neu schreibt, statt einzelne Zellen zu flicken.

Gelesen wird über die **Spaltenüberschriften** in Zeile 1, nicht über feste
Buchstaben: wer in Excel eine Spalte einfügt, soll danach nicht stillschweigend
die falsche Spalte beschrieben bekommen.

Kein Schloss, kein ``mtime``-Vergleich, kein Backup: das steht im Dashboard
(``app/buchplanung.py``), wie schon bei den beiden anderen Mappen.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from bestand.core import atomic_save_workbook

from .modelle import (
    LEGENDE,
    OHNE_FACH,
    OHNE_VERLAG,
    Buch,
    Buchbemerkung,
    Buchplanung,
    Planungszeile,
    Ruecklage,
)

BLATT_BUECHER = "Buchreihen"
BLATT_FACH_JAHRGANG = "Fächer & Jahrgang"
BLATT_RUECKLAGE = "Rücklage"
BLATT_INFO = "Info"

BLAETTER: tuple[str, ...] = (
    BLATT_BUECHER, BLATT_FACH_JAHRGANG, BLATT_RUECKLAGE, BLATT_INFO,
)

# Die Blätter des Aufbaus bis 2026-09-20. Sie werden beim Schreiben entfernt:
# eine Mappe, in der dieselben Bücher zusätzlich in einer alten Fassung stehen,
# ist schlimmer als eine ohne sie - man sähe ihr nicht an, welche gilt.
# "Korrekturen" gab es nur am 2026-09-24 für wenige Stunden; die Korrekturen
# stehen seither auf "Buchreihen" selbst.
_ALTE_BLAETTER: tuple[str, ...] = (
    "Preise je Verlag", "Bücher je Fach", "Bücher je Jahrgang", "Fachbestätigung",
    "Korrekturen",
)


class MappeUnlesbar(ValueError):
    """Die Datei hat nicht den Aufbau einer Buchplanungs-Mappe."""


# ── Die Spalten je Blatt ─────────────────────────────────────────────────────
#
# (Überschrift, Breite, eintragbar). "Eintragbar" färbt die Spalte hell ein und
# ist zugleich die Liste dessen, was beim Lesen zurückkommt.

SPALTE_EINFUEHRUNG = "Einführung"
SPALTE_AUSMUSTERUNG = "Ausmusterung nach Schuljahr"
# Steht dieses (Fach, Jahrgang) in einer Bücherliste aus IServ - oder ist es
# bloß geplant? Ohne diese Spalte wäre das nach einem Speichern nicht mehr zu
# unterscheiden: das Blatt trägt beide Arten von Zeile, und beim Lesen sähen
# sie gleich aus. Daran hängen zwei Dinge - das Menü lässt die Einführung eines
# laufenden Jahrgangs nicht ändern, und eine geleerte Planungszeile
# verschwindet wirklich, statt als leere Zeile wiederzukommen.
SPALTE_IN_LISTE = "in der Bücherliste"
# Auf "Buchreihen": steht das Buch in IServ, oder wurde es im Dashboard von
# Hand hinzugefügt ("nein")? Ohne diese Spalte verwürfe der nächste Abgleich
# ein von Hand angelegtes Buch als verschwunden. Eine Datei aus der Zeit davor
# hat sie nicht; dort stammt jedes Buch aus IServ.
SPALTE_IN_ISERV = "in IServ"

_SPALTEN: dict[str, tuple[tuple[str, float, bool], ...]] = {
    BLATT_BUECHER: (
        ("Titel", 44, False),
        ("Fach", 24, False),
        ("Jahrgang", 12, False),
        ("Verlag", 24, False),
        ("ISBN", 18, False),
        ("Neupreis", 12, False),
        ("Leihpreis", 12, False),
        ("leihbar", 9, False),
        (SPALTE_IN_ISERV, 10, False),
        ("Bemerkung", 30, True),
    ),
    BLATT_FACH_JAHRGANG: (
        ("ISBN", 18, False),
        ("Fach", 22, False),
        ("Jahrgang", 10, False),
        (SPALTE_IN_LISTE, 18, False),
        (SPALTE_EINFUEHRUNG, 13, True),
        (SPALTE_AUSMUSTERUNG, 24, True),
        ("Kürzel", 10, True),
        ("Datum", 12, True),
        ("Bemerkung", 30, True),
    ),
    BLATT_RUECKLAGE: (
        ("ISBN", 18, False),
        ("Fach", 22, False),
        ("Anzahl", 10, True),
        ("Kürzel", 10, True),
        ("Datum", 12, True),
        ("Status", 16, True),
        ("Bemerkung", 30, True),
    ),
}

# Aus der Mehrjahresbände-Mappe übernommen, damit die drei Dateien der
# Schulbuchausleihe gleich aussehen.
_SCHRIFT = Font(name="Calibri", size=11)
_FETT = Font(name="Calibri", size=11, bold=True)
_KOPF_FUELLUNG = PatternFill(fill_type="solid", start_color="FFD9D9D9", end_color="FFD9D9D9")
_EINTRAG_FUELLUNG = PatternFill(fill_type="solid", start_color="FFFFF6D5", end_color="FFFFF6D5")
_LEER = PatternFill(fill_type=None)

_DUENN = Side(style="thin")
_RAHMEN = Border(left=_DUENN, right=_DUENN, top=_DUENN, bottom=_DUENN)
_LINKS = Alignment(horizontal="left", vertical="center", wrap_text=False)
_MITTE = Alignment(horizontal="center", vertical="center")

_DATUMSFORMAT = "DD.MM.YYYY"
_EUROFORMAT = '#,##0.00\\ "€"'
_EUROSPALTEN = ("Neupreis", "Leihpreis")

_JA = "ja"
_NEIN = "nein"

# Korrekturen auf "Buchreihen": die Zelle trägt den korrigierten Wert, hell
# hinterlegt, und als Kommentar den Wert aus IServ. An diesem Kommentar
# erkennt der nächste Abgleich die Korrektur. Den Wert der Zelle behält der
# Abgleich so oder so (die Datei ist das Soll). Feld (``Buch``) -> Spalte.
_KORRIGIERBAR: dict[str, str] = {
    "titel": "Titel", "verlag": "Verlag", "neupreis": "Neupreis", "leihgebuehr": "Leihpreis",
    "leihbar": "leihbar",
}
_PREISFELDER = frozenset({"neupreis", "leihgebuehr"})
_JA_NEIN_FELDER = frozenset({"leihbar"})
_ISERV_MARKE = "in IServ:"
_OHNE_WERT = "–"
_KOMMENTARE = "_kommentare"
_KOMMENTAR_VON = "Dashboard"


# ── Kleine Umwandlungen ──────────────────────────────────────────────────────


def _text(roh: object) -> str:
    if roh is None:
        return ""
    if isinstance(roh, datetime):
        return roh.date().isoformat()
    return str(roh).strip()


def _zahl(roh: object) -> float | None:
    if roh is None or isinstance(roh, bool):
        return None
    if isinstance(roh, (int, float)):
        return float(roh)
    text = str(roh).strip().replace("€", "").replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _ganzzahl(roh: object) -> int | None:
    wert = _zahl(roh)
    if wert is None:
        return None
    return int(round(wert))


def _datum(roh: object) -> date | None:
    if isinstance(roh, datetime):
        return roh.date()
    if isinstance(roh, date):
        return roh
    text = _text(roh)
    if not text:
        return None
    for form in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
        try:
            return datetime.strptime(text, form).date()
        except ValueError:
            continue
    return None


# ── Lesen ────────────────────────────────────────────────────────────────────


def _kopf(ws: Worksheet) -> dict[str, int]:
    """Überschrift → Spaltennummer, aus Zeile 1."""
    kopf: dict[str, int] = {}
    for spalte in range(1, (ws.max_column or 0) + 1):
        name = _text(ws.cell(1, spalte).value)
        if name and name not in kopf:
            kopf[name] = spalte
    return kopf


def _zeilen(ws: Worksheet) -> list[dict[str, object]]:
    """Alle Datenzeilen als {Überschrift: Wert}; leere Zeilen fallen weg.

    Unter ``_KOMMENTARE`` stehen zusätzlich die Kommentare der Zeile
    ({Überschrift: Text}) - auf ``Buchreihen`` tragen sie die IServ-Werte
    korrigierter Zellen.
    """
    kopf = _kopf(ws)
    if not kopf:
        return []
    heraus: list[dict[str, object]] = []
    for nummer in range(2, (ws.max_row or 1) + 1):
        werte: dict[str, object] = {
            name: ws.cell(nummer, spalte).value for name, spalte in kopf.items()}
        if any(_text(wert) for wert in werte.values()):
            werte[_KOMMENTARE] = {
                name: zelle.comment.text for name, spalte in kopf.items()
                for zelle in (ws.cell(nummer, spalte),) if zelle.comment is not None
            }
            heraus.append(werte)
    return heraus


def _iserv_aus_kommentar(text: str, feld: str) -> object:
    """``"in IServ: 22,50 €"`` -> 22.5, ``"in IServ: nein"`` -> False. Excel setzt
    beim Bearbeiten den Namen davor; gelesen wird deshalb ab dem letzten „in IServ:“."""
    rest = text.rsplit(_ISERV_MARKE, 1)[-1].strip()
    if feld in _JA_NEIN_FELDER:
        return rest.casefold() == _JA
    preis = feld in _PREISFELDER
    if rest in ("", _OHNE_WERT):
        return None if preis else ""
    return _zahl(rest) if preis else rest


def _korrekturen(zeile: dict[str, object]) -> tuple[tuple[str, object], ...]:
    """Die korrigierten Felder einer Zeile auf ``Buchreihen``, mit ihrem IServ-Wert."""
    kommentare = zeile.get(_KOMMENTARE) or {}
    assert isinstance(kommentare, dict)
    return tuple(
        (feld, _iserv_aus_kommentar(kommentare[spalte], feld))
        for feld, spalte in _KORRIGIERBAR.items()
        if _ISERV_MARKE in str(kommentare.get(spalte) or "")
    )


def lies_mappe(wb: Workbook) -> Buchplanung:
    """Liest den ganzen Stand aus einer geöffneten Mappe.

    Die Bücher stehen auf ``Buchreihen``, ihre (Fach, Jahrgang)-Paare auf
    ``Fächer & Jahrgang``. Die Spalten ``Fach`` und ``Jahrgang`` auf
    ``Buchreihen`` sind nur die Zusammenfassung dieser Paare und werden nicht
    gelesen - sie stehen dort, damit ein Buch auch ohne das zweite Blatt
    einzuordnen ist.

    Zu den Paaren des Buchs (``kombinationen``) zählen nur die Zeilen, die
    ``in der Bücherliste`` mit "ja" führen: das Blatt trägt auch die bloß
    geplanten Jahrgänge, und die stehen gerade **nicht** in einer Liste.
    """
    fehlend = [name for name in BLAETTER if name not in wb.sheetnames]
    if fehlend:
        raise MappeUnlesbar(
            "Der Datei fehlen die Blätter: " + ", ".join(fehlend) + "."
        )

    buch_roh = _zeilen(wb[BLATT_BUECHER])
    planung_roh = _zeilen(wb[BLATT_FACH_JAHRGANG])
    ruecklage_roh = _zeilen(wb[BLATT_RUECKLAGE])

    kombinationen: dict[str, set[tuple[str, int]]] = {}
    planung: list[Planungszeile] = []
    for zeile in planung_roh:
        isbn = _text(zeile.get("ISBN"))
        fach = _text(zeile.get("Fach")) or OHNE_FACH
        jahrgang = _ganzzahl(zeile.get("Jahrgang"))
        if not isbn or jahrgang is None:
            continue
        # Eine Datei aus der Zeit vor dieser Spalte kennt den Unterschied
        # nicht; dort zählt wie früher jede Zeile als Vorkommen. Der nächste
        # Abgleich stellt die Wahrheit aus IServ ohnehin wieder her.
        if SPALTE_IN_LISTE not in zeile or _text(zeile.get(SPALTE_IN_LISTE)).casefold() == _JA:
            kombinationen.setdefault(isbn, set()).add((fach, jahrgang))
        eintrag = Planungszeile(
            isbn=isbn,
            fach=fach,
            jahrgang=jahrgang,
            eingefuehrt_ab=_text(zeile.get(SPALTE_EINFUEHRUNG)),
            ausgemustert_nach=_text(zeile.get(SPALTE_AUSMUSTERUNG)),
            kuerzel=_text(zeile.get("Kürzel")),
            datum=_datum(zeile.get("Datum")),
            bemerkung=_text(zeile.get("Bemerkung")),
        )
        if not eintrag.leer:
            planung.append(eintrag)

    buecher = tuple(
        Buch(
            isbn=isbn,
            titel=_text(zeile.get("Titel")),
            verlag=_text(zeile.get("Verlag")) or OHNE_VERLAG,
            kombinationen=tuple(sorted(kombinationen.get(isbn, set()),
                                       key=lambda paar: (paar[0].casefold(), paar[1]))),
            leihbar=_text(zeile.get("leihbar")).casefold() == _JA,
            neupreis=_zahl(zeile.get("Neupreis")),
            leihgebuehr=_zahl(zeile.get("Leihpreis")),
            iserv=_korrekturen(zeile),
            von_hand=_text(zeile.get(SPALTE_IN_ISERV)).casefold() == _NEIN,
        )
        for zeile in buch_roh
        for isbn in (_text(zeile.get("ISBN")),) if isbn
    )

    bemerkungen = tuple(
        eintrag for eintrag in (
            Buchbemerkung(
                isbn=_text(zeile.get("ISBN")),
                bemerkung=_text(zeile.get("Bemerkung")),
            )
            for zeile in buch_roh if _text(zeile.get("ISBN"))
        ) if not eintrag.leer
    )

    ruecklagen = tuple(
        eintrag for eintrag in (
            Ruecklage(
                isbn=_text(zeile.get("ISBN")),
                fach=_text(zeile.get("Fach")) or OHNE_FACH,
                anzahl=_ganzzahl(zeile.get("Anzahl")),
                status=_text(zeile.get("Status")),
                kuerzel=_text(zeile.get("Kürzel")),
                datum=_datum(zeile.get("Datum")),
                bemerkung=_text(zeile.get("Bemerkung")),
            )
            for zeile in ruecklage_roh if _text(zeile.get("ISBN"))
        ) if not eintrag.leer
    )

    schuljahr, vorjahr, stand = _lies_info(wb)
    return Buchplanung(
        schuljahr=schuljahr, vorjahr=vorjahr, stand=stand, buecher=buecher,
        bemerkungen=bemerkungen, planung=tuple(planung), ruecklagen=ruecklagen,
    )


def _lies_info(wb: Workbook) -> tuple[str, str, date | None]:
    """Schuljahr, Vorjahr und Stand aus dem Blatt ``Info`` (Schlüssel in Spalte A)."""
    ws = wb[BLATT_INFO]
    werte: dict[str, object] = {}
    for nummer in range(1, (ws.max_row or 1) + 1):
        schluessel = _text(ws.cell(nummer, 1).value)
        if schluessel:
            werte.setdefault(schluessel, ws.cell(nummer, 2).value)
    return (
        _text(werte.get("Schuljahr")),
        _text(werte.get("Vorjahr")),
        _datum(werte.get("Stand")),
    )


def lies_datei(pfad: Path) -> Buchplanung:
    """Öffnet die Datei und liest ihren Stand."""
    return lies_mappe(load_workbook(str(pfad), data_only=True))


# ── Schreiben ────────────────────────────────────────────────────────────────


def _leeren(ws: Worksheet) -> None:
    for verbund in list(ws.merged_cells.ranges):
        ws.unmerge_cells(str(verbund))
    if ws.max_row:
        ws.delete_rows(1, ws.max_row)
    ws.column_dimensions.clear()
    ws.row_dimensions.clear()
    ws.auto_filter.ref = None
    ws.freeze_panes = None


def _schreibe_kopf(ws: Worksheet, blatt: str) -> None:
    spalten = _SPALTEN[blatt]
    for nummer, (name, breite, _) in enumerate(spalten, start=1):
        zelle = ws.cell(1, nummer)
        zelle.value = name
        zelle.font = _FETT
        zelle.fill = _KOPF_FUELLUNG
        zelle.border = _RAHMEN
        zelle.alignment = _MITTE
        ws.column_dimensions[get_column_letter(nummer)].width = breite
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(spalten))}1"


def _schreibe_zeile(ws: Worksheet, blatt: str, nummer: int, werte: dict[str, object]) -> None:
    kommentare = werte.get(_KOMMENTARE) or {}
    assert isinstance(kommentare, dict)
    for spalte, (name, _, eintragbar) in enumerate(_SPALTEN[blatt], start=1):
        wert = werte.get(name)
        zelle = ws.cell(nummer, spalte)
        zelle.value = wert if wert != "" else None
        zelle.font = _SCHRIFT
        zelle.border = _RAHMEN
        # Eine korrigierte Zelle ist hell wie eine eintragbare - sie ist es auch.
        zelle.fill = _EINTRAG_FUELLUNG if eintragbar or name in kommentare else _LEER
        zelle.comment = (Comment(str(kommentare[name]), _KOMMENTAR_VON)
                         if name in kommentare else None)
        zelle.alignment = _LINKS
        if isinstance(wert, date):
            zelle.number_format = _DATUMSFORMAT
        elif name in _EUROSPALTEN and wert is not None:
            zelle.number_format = _EUROFORMAT


def _schreibe_blatt(ws: Worksheet, blatt: str, zeilen: list[dict[str, object]]) -> None:
    _leeren(ws)
    _schreibe_kopf(ws, blatt)
    for versatz, werte in enumerate(zeilen):
        _schreibe_zeile(ws, blatt, 2 + versatz, werte)


def _nach_titel(stand: Buchplanung) -> list[Buch]:
    return sorted(stand.buecher, key=lambda b: (b.titel.casefold(), b.isbn))


def _buchzeilen(stand: Buchplanung) -> list[dict[str, object]]:
    zeilen: list[dict[str, object]] = []
    for buch in _nach_titel(stand):
        eintrag = stand.bemerkung(buch.isbn)
        zeilen.append({
            "Titel": buch.titel,
            "Fach": buch.fach_anzeige,
            "Jahrgang": buch.jahrgang_anzeige,
            "Verlag": buch.verlag or OHNE_VERLAG,
            "ISBN": buch.isbn,
            "Neupreis": buch.neupreis,
            "Leihpreis": buch.leihgebuehr,
            "leihbar": _JA if buch.leihbar else _NEIN,
            SPALTE_IN_ISERV: _NEIN if buch.von_hand else _JA,
            "Bemerkung": eintrag.bemerkung if eintrag else "",
            _KOMMENTARE: {
                _KORRIGIERBAR[feld]: _iserv_kommentar(original, feld)
                for feld, original in buch.iserv if feld in _KORRIGIERBAR
            },
        })
    return zeilen


def _iserv_kommentar(original: object, feld: str) -> str:
    """Der Kommentar an einer korrigierten Zelle: was IServ dort nennt."""
    if feld in _JA_NEIN_FELDER:
        return f"{_ISERV_MARKE} {_JA if original else _NEIN}"
    if original is None or original == "":
        return f"{_ISERV_MARKE} {_OHNE_WERT}"
    if feld in _PREISFELDER and isinstance(original, (int, float)):
        return f"{_ISERV_MARKE} {original:.2f} €".replace(".", ",")
    return f"{_ISERV_MARKE} {original}"


def _planungszeilen(stand: Buchplanung) -> list[dict[str, object]]:
    """Je (Buch, Fach, Jahrgang) eine Zeile - sortiert nach Fach, Jahrgang, Titel."""
    zeilen: list[dict[str, object]] = []
    aufgestellt: list[tuple[str, int, str, str]] = []
    aus_liste: set[tuple[str, str, int]] = set()
    for buch in stand.buecher:
        for fach, jahrgang in stand.zeilen_des_buchs(buch):
            aufgestellt.append((fach, jahrgang, buch.titel.casefold(), buch.isbn))
        for fach, jahrgang in buch.kombinationen:
            aus_liste.add((buch.isbn, fach, jahrgang))
    for fach, jahrgang, _, isbn in sorted(
            aufgestellt, key=lambda e: (e[0].casefold(), e[1], e[2], e[3])):
        zeile = stand.planungszeile(isbn, fach, jahrgang)
        zeilen.append({
            "ISBN": isbn,
            "Fach": fach,
            "Jahrgang": jahrgang,
            SPALTE_IN_LISTE: _JA if (isbn, fach, jahrgang) in aus_liste else _NEIN,
            SPALTE_EINFUEHRUNG: zeile.eingefuehrt_ab if zeile else "",
            SPALTE_AUSMUSTERUNG: zeile.ausgemustert_nach if zeile else "",
            "Kürzel": zeile.kuerzel if zeile else "",
            "Datum": zeile.datum if zeile else None,
            "Bemerkung": zeile.bemerkung if zeile else "",
        })
    return zeilen


def _ruecklagenzeilen(stand: Buchplanung) -> list[dict[str, object]]:
    """Nur die Rücklagen, die es gibt - hier steht kein Buch ohne Wunsch.

    Das Blatt ist die Liste der Wünsche, nicht der Bücher: eine Zeile je Buch
    und Fach wäre dieselbe Aufstellung wie ``Fächer & Jahrgang``, nur mit einer
    leeren Spalte daneben.
    """
    titel = {buch.isbn: buch.titel.casefold() for buch in stand.buecher}
    zeilen: list[dict[str, object]] = []
    for eintrag in sorted(stand.ruecklagen,
                          key=lambda r: (r.fach.casefold(), titel.get(r.isbn, ""), r.isbn)):
        zeilen.append({
            "ISBN": eintrag.isbn,
            "Fach": eintrag.fach,
            "Anzahl": eintrag.anzahl,
            "Kürzel": eintrag.kuerzel,
            "Datum": eintrag.datum,
            "Status": eintrag.status,
            "Bemerkung": eintrag.bemerkung,
        })
    return zeilen


def _schreibe_info(ws: Worksheet, stand: Buchplanung) -> None:
    _leeren(ws)
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 80

    def zeile(nummer: int, schluessel: str, wert: object, fett: bool = False) -> None:
        links = ws.cell(nummer, 1)
        links.value = schluessel
        links.font = _FETT if fett else _SCHRIFT
        rechts = ws.cell(nummer, 2)
        rechts.value = wert
        rechts.font = _SCHRIFT
        rechts.alignment = _LINKS
        if isinstance(wert, date):
            rechts.number_format = _DATUMSFORMAT

    zeile(1, "Schulbuchausleihe", "Bücherlisten und Planung", fett=True)
    zeile(2, "Schuljahr", stand.schuljahr)
    zeile(3, "Vorjahr", stand.vorjahr)
    zeile(4, "Stand", stand.stand)
    zeile(6, "Eintragen", "Diese Datei ist das Soll: Titel, Verlag, Preise, leihbar, "
                          "Fächer und Jahrgänge bleiben beim Abgleich, wie sie hier "
                          "stehen; nur neue Bücher kommen aus IServ dazu.")
    zeile(7, "Bücher", "Aus dem laufenden Schuljahr alle, aus dem Vorjahr die "
                       "leihbaren - nur die liegen im Bestand der Schule.")
    zeile(8, "Abweichungen", "Steht in IServ ein anderer Wert als auf „Buchreihen“, "
                             "nennt ihn der Kommentar an der Zelle. IServ selbst "
                             "bleibt unverändert.")
    zeile(9, "Neue Bücher", "Im Planungsmenü hinzugefügte Bücher, die (noch) nicht in "
                            "IServ stehen, tragen auf „Buchreihen“ „in IServ: nein“. Sie "
                            "bleiben beim Abgleich, solange sie eine Planungszeile haben.")
    zeile(10, "Legende", "", fett=True)
    for versatz, (marke, text) in enumerate(LEGENDE):
        zeile(11 + versatz, marke, text)
    naechste = 11 + len(LEGENDE) + 1
    for versatz, warnung in enumerate(stand.warnungen):
        zeile(naechste + versatz, "Hinweis" if versatz == 0 else "", warnung)


def schreibe_mappe(wb: Workbook, stand: Buchplanung) -> None:
    """Schreibt alle vier Blätter neu - Werte und Gestaltung.

    Bewusst vollständig und nicht zellweise: die Bücher wechseln, Spalten
    können hinzukommen, und ein halb aktualisiertes Blatt wäre die Fassung,
    der man am wenigsten ansieht, woran man ist.
    """
    for name in BLAETTER:
        if name not in wb.sheetnames:
            wb.create_sheet(name)
    _schreibe_blatt(wb[BLATT_BUECHER], BLATT_BUECHER, _buchzeilen(stand))
    _schreibe_blatt(wb[BLATT_FACH_JAHRGANG], BLATT_FACH_JAHRGANG, _planungszeilen(stand))
    _schreibe_blatt(wb[BLATT_RUECKLAGE], BLATT_RUECKLAGE, _ruecklagenzeilen(stand))
    _schreibe_info(wb[BLATT_INFO], stand)
    for name in _ALTE_BLAETTER:
        if name in wb.sheetnames:
            wb.remove(wb[name])
    for versatz, name in enumerate(BLAETTER):
        wb.move_sheet(name, offset=versatz - wb.sheetnames.index(name))


def neue_mappe() -> Workbook:
    """Eine leere Mappe mit den vier Blättern in ihrer Reihenfolge."""
    wb = Workbook()
    wb.worksheets[0].title = BLAETTER[0]
    for name in BLAETTER[1:]:
        wb.create_sheet(name)
    return wb


def schreibe_datei(pfad: Path, stand: Buchplanung, *,
                   backup_ordner: Path | None = None) -> Path | None:
    """Schreibt den Stand nach ``pfad`` - atomar, mit optionaler Sicherung."""
    if pfad.is_file():
        wb = load_workbook(str(pfad))
        schreibe_mappe(wb, stand)
        return atomic_save_workbook(wb, pfad, backup_dir=backup_ordner)
    wb = neue_mappe()
    schreibe_mappe(wb, stand)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(pfad))
    return None
