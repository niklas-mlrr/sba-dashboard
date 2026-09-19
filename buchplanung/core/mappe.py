"""Die Buchplanung als Exceldatei lesen und schreiben.

Die Datei ist der **Rückfall**: fällt das Dashboard aus - etwa nach einem
IServ-Update -, liegt der Stand weiter auf dem Gruppenlaufwerk und ist ohne
dieses Programm lesbar. Deshalb ist sie kein Rohdatenblatt, sondern bildet die
drei Arbeitsschritte ab, und zwar je auf einem eigenen Blatt:

===========================  ================================================
Blatt                        Wer damit arbeitet
===========================  ================================================
``Preise je Verlag``         der Beauftragte für die Schulbuchausleihe
``Bücher je Fach``           die Fachkonferenzleitungen (Freigabe, Rücklagen)
``Bücher je Jahrgang``       die Ausleihe-Planung (Einführung, Ausmusterung)
``Fachbestätigung``          die Freigaben je Fach, auf einen Blick
``Info``                     Schuljahr, Stand und die Legende aller Status
===========================  ================================================

Dieselben Bücher stehen damit mehrfach in der Mappe. Das ist Absicht und
gefährdet nichts, solange **eine** Regel gilt:

    Aus jedem Blatt wird nur seine eigene Eintragungs-Spalte zurückgelesen;
    alles andere wird bei jedem Schreiben neu gesetzt.

Wer also auf dem Fach-Blatt einen Titel überschreibt, ändert nichts - beim
nächsten Schreiben steht dort wieder, was IServ sagt. Wer die Spalte
"geprüfter Preis" ausfüllt, ändert die Prüfung. Dieselbe Regel liegt schon
``mehrjahresbaende/core/mappe.py`` zugrunde, das sein Blatt ebenfalls immer
vollständig neu schreibt, statt einzelne Zellen zu flicken.

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
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from bestand.core import atomic_save_workbook

from .modelle import (
    AKTUELL,
    BEIDE,
    LEGENDE,
    NUR_PLANUNG,
    OHNE_FACH,
    OHNE_VERLAG,
    VORJAHR,
    Buch,
    Buchplanung,
    Fachbestaetigung,
    Planungszeile,
    Preispruefung,
    Ruecklage,
    fach_status,
    planungs_status,
    preis_status,
)

BLATT_PREISE = "Preise je Verlag"
BLATT_FACH = "Bücher je Fach"
BLATT_JAHRGANG = "Bücher je Jahrgang"
BLATT_BESTAETIGUNG = "Fachbestätigung"
BLATT_INFO = "Info"

BLAETTER: tuple[str, ...] = (
    BLATT_PREISE, BLATT_FACH, BLATT_JAHRGANG, BLATT_BESTAETIGUNG, BLATT_INFO,
)


class MappeUnlesbar(ValueError):
    """Die Datei hat nicht den Aufbau einer Buchplanungs-Mappe."""


# ── Die Spalten je Blatt ─────────────────────────────────────────────────────
#
# (Überschrift, Breite, eintragbar). "Eintragbar" färbt die Spalte hell ein und
# ist zugleich die Liste dessen, was beim Lesen zurückkommt.

_SPALTEN: dict[str, tuple[tuple[str, float, bool], ...]] = {
    BLATT_PREISE: (
        ("Verlag", 24, False),
        ("Titel", 44, False),
        ("ISBN", 18, False),
        ("Fächer", 24, False),
        ("Jahrgänge", 12, False),
        ("Neupreis IServ", 14, False),
        ("Leihgebühr", 12, False),
        ("geprüfter Preis", 15, True),
        ("Kürzel", 10, True),
        ("Datum", 12, True),
        ("Status", 13, False),
        ("Hinweis", 40, False),
        ("Bemerkung", 30, True),
    ),
    BLATT_FACH: (
        ("Fach", 22, False),
        ("Titel", 44, False),
        ("ISBN", 18, False),
        ("Verlag", 22, False),
        ("Jahrgänge", 12, False),
        ("Herkunft", 11, False),
        ("leihbar", 9, False),
        ("Preis", 13, False),
        ("Rücklage Anzahl", 16, True),
        ("Rücklage Status", 16, True),
        ("Kürzel", 10, True),
        ("Datum", 12, True),
        ("Bemerkung", 30, True),
    ),
    BLATT_JAHRGANG: (
        ("Jahrgang", 10, False),
        ("Titel", 44, False),
        ("ISBN", 18, False),
        ("Fächer", 24, False),
        ("Verlag", 22, False),
        ("Herkunft", 11, False),
        ("leihbar", 9, False),
        ("eingeführt ab", 15, True),
        ("ausgemustert nach", 18, True),
        ("Status", 14, False),
        ("Beschluss", 20, True),
        ("Bemerkung", 30, True),
    ),
    BLATT_BESTAETIGUNG: (
        ("Fach", 22, False),
        ("Bücher", 9, False),
        ("Status", 13, False),
        ("Kürzel", 10, True),
        ("Datum", 12, True),
        ("Bemerkung", 30, True),
        ("Hinweis", 50, False),
        ("bestätigter Stand", 60, False),
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

_JA = "ja"
_NEIN = "nein"

# Auf dem Fach-Blatt steht die Herkunft des ganzen Buchs, auf dem
# Jahrgangs-Blatt die der einzelnen Jahrgangszeile - dort ist sie feiner und
# trägt beim Lesen die Rekonstruktion der beiden Jahrgangslisten. "nur Planung"
# heißt: diese Zeile steht noch in keiner Bücherliste, sondern nur im Plan.
_HERKUNFT_WERTE = (VORJAHR, AKTUELL, BEIDE, NUR_PLANUNG)


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


def _isbn_liste(roh: object) -> tuple[str, ...]:
    return tuple(teil.strip() for teil in _text(roh).split(",") if teil.strip())


# ── Lesen ────────────────────────────────────────────────────────────────────


def _blatt(wb: Workbook, name: str) -> Worksheet | None:
    return wb[name] if name in wb.sheetnames else None


def _kopf(ws: Worksheet) -> dict[str, int]:
    """Überschrift → Spaltennummer, aus Zeile 1."""
    kopf: dict[str, int] = {}
    for spalte in range(1, (ws.max_column or 0) + 1):
        name = _text(ws.cell(1, spalte).value)
        if name and name not in kopf:
            kopf[name] = spalte
    return kopf


def _zeilen(ws: Worksheet) -> list[dict[str, object]]:
    """Alle Datenzeilen als {Überschrift: Wert}; leere Zeilen fallen weg."""
    kopf = _kopf(ws)
    if not kopf:
        return []
    heraus: list[dict[str, object]] = []
    for nummer in range(2, (ws.max_row or 1) + 1):
        werte = {name: ws.cell(nummer, spalte).value for name, spalte in kopf.items()}
        if any(_text(wert) for wert in werte.values()):
            heraus.append(werte)
    return heraus


def lies_mappe(wb: Workbook) -> Buchplanung:
    """Liest den ganzen Stand aus einer geöffneten Mappe.

    Die Bücher werden aus den drei Blättern zusammengesetzt: Fächer vom
    Fach-Blatt, Jahrgänge und ihre Herkunft vom Jahrgangs-Blatt, Preise vom
    Verlags-Blatt. Anders geht es nicht, und anders soll es auch nicht gehen -
    ein zusätzliches Rohdatenblatt wäre eine vierte Stelle, an der dieselben
    Titel stehen.
    """
    fehlend = [name for name in BLAETTER if name not in wb.sheetnames]
    if fehlend:
        raise MappeUnlesbar(
            "Der Datei fehlen die Blätter: " + ", ".join(fehlend) + "."
        )

    preise_roh = _zeilen(wb[BLATT_PREISE])
    fach_roh = _zeilen(wb[BLATT_FACH])
    jahrgang_roh = _zeilen(wb[BLATT_JAHRGANG])
    bestaetigung_roh = _zeilen(wb[BLATT_BESTAETIGUNG])

    buecher = _lies_buecher(preise_roh, fach_roh, jahrgang_roh)

    preise = tuple(
        eintrag for eintrag in (
            Preispruefung(
                isbn=_text(zeile.get("ISBN")),
                preis=_zahl(zeile.get("geprüfter Preis")),
                kuerzel=_text(zeile.get("Kürzel")),
                datum=_datum(zeile.get("Datum")),
                bemerkung=_text(zeile.get("Bemerkung")),
            )
            for zeile in preise_roh if _text(zeile.get("ISBN"))
        ) if not eintrag.leer
    )

    ruecklagen = tuple(
        eintrag for eintrag in (
            Ruecklage(
                isbn=_text(zeile.get("ISBN")),
                fach=_text(zeile.get("Fach")) or OHNE_FACH,
                anzahl=_ganzzahl(zeile.get("Rücklage Anzahl")),
                status=_text(zeile.get("Rücklage Status")),
                kuerzel=_text(zeile.get("Kürzel")),
                datum=_datum(zeile.get("Datum")),
                bemerkung=_text(zeile.get("Bemerkung")),
            )
            for zeile in fach_roh if _text(zeile.get("ISBN"))
        ) if not eintrag.leer
    )

    planung: list[Planungszeile] = []
    for zeile in jahrgang_roh:
        isbn = _text(zeile.get("ISBN"))
        jahrgang = _ganzzahl(zeile.get("Jahrgang"))
        if not isbn or jahrgang is None:
            continue
        eintrag = Planungszeile(
            isbn=isbn,
            jahrgang=jahrgang,
            eingefuehrt_ab=_text(zeile.get("eingeführt ab")),
            ausgemustert_nach=_text(zeile.get("ausgemustert nach")),
            beschluss=_text(zeile.get("Beschluss")),
            bemerkung=_text(zeile.get("Bemerkung")),
        )
        if not eintrag.leer:
            planung.append(eintrag)

    bestaetigungen = tuple(
        eintrag for eintrag in (
            Fachbestaetigung(
                fach=_text(zeile.get("Fach")),
                kuerzel=_text(zeile.get("Kürzel")),
                datum=_datum(zeile.get("Datum")),
                bemerkung=_text(zeile.get("Bemerkung")),
                bestaetigte_isbns=_isbn_liste(zeile.get("bestätigter Stand")),
            )
            for zeile in bestaetigung_roh if _text(zeile.get("Fach"))
        ) if not eintrag.leer
    )

    schuljahr, vorjahr, stand = _lies_info(wb)
    return Buchplanung(
        schuljahr=schuljahr, vorjahr=vorjahr, stand=stand,
        buecher=buecher, preise=preise, ruecklagen=ruecklagen,
        planung=tuple(planung), bestaetigungen=bestaetigungen,
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


def _lies_buecher(
    preise_roh: list[dict[str, object]],
    fach_roh: list[dict[str, object]],
    jahrgang_roh: list[dict[str, object]],
) -> tuple[Buch, ...]:
    """Setzt die Bücher aus den drei Blättern zusammen."""
    titel: dict[str, str] = {}
    verlag: dict[str, str] = {}
    leihbar: dict[str, bool] = {}
    faecher: dict[str, list[str]] = {}
    vorjahr: dict[str, set[int]] = {}
    aktuell: dict[str, set[int]] = {}
    neupreis: dict[str, float | None] = {}
    leihgebuehr: dict[str, float | None] = {}

    def merke(isbn: str, zeile: dict[str, object]) -> None:
        if isbn not in titel or not titel[isbn]:
            titel[isbn] = _text(zeile.get("Titel"))
        wert = _text(zeile.get("Verlag"))
        if wert and not verlag.get(isbn):
            verlag[isbn] = wert
        if "leihbar" in zeile:
            leihbar[isbn] = _text(zeile.get("leihbar")).casefold() == _JA

    for zeile in preise_roh:
        isbn = _text(zeile.get("ISBN"))
        if not isbn:
            continue
        merke(isbn, zeile)
        neupreis[isbn] = _zahl(zeile.get("Neupreis IServ"))
        leihgebuehr[isbn] = _zahl(zeile.get("Leihgebühr"))

    for zeile in fach_roh:
        isbn = _text(zeile.get("ISBN"))
        if not isbn:
            continue
        merke(isbn, zeile)
        fach = _text(zeile.get("Fach"))
        if fach and fach != OHNE_FACH and fach not in faecher.setdefault(isbn, []):
            faecher[isbn].append(fach)
        faecher.setdefault(isbn, [])

    for zeile in jahrgang_roh:
        isbn = _text(zeile.get("ISBN"))
        jahrgang = _ganzzahl(zeile.get("Jahrgang"))
        if not isbn or jahrgang is None:
            continue
        merke(isbn, zeile)
        herkunft = _text(zeile.get("Herkunft")) or AKTUELL
        if herkunft in (VORJAHR, BEIDE):
            vorjahr.setdefault(isbn, set()).add(jahrgang)
        if herkunft in (AKTUELL, BEIDE):
            aktuell.setdefault(isbn, set()).add(jahrgang)

    return tuple(
        Buch(
            isbn=isbn,
            titel=titel.get(isbn, ""),
            verlag=verlag.get(isbn, ""),
            faecher=tuple(faecher.get(isbn, ())),
            jahrgaenge_vorjahr=tuple(sorted(vorjahr.get(isbn, set()))),
            jahrgaenge_aktuell=tuple(sorted(aktuell.get(isbn, set()))),
            leihbar=leihbar.get(isbn, False),
            neupreis=neupreis.get(isbn),
            leihgebuehr=leihgebuehr.get(isbn),
        )
        for isbn in sorted(titel, key=lambda i: (titel.get(i, "").casefold(), i))
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
    for spalte, (name, _, eintragbar) in enumerate(_SPALTEN[blatt], start=1):
        wert = werte.get(name)
        zelle = ws.cell(nummer, spalte)
        zelle.value = wert if wert != "" else None
        zelle.font = _SCHRIFT
        zelle.border = _RAHMEN
        zelle.fill = _EINTRAG_FUELLUNG if eintragbar else _LEER
        zelle.alignment = _LINKS
        if isinstance(wert, date):
            zelle.number_format = _DATUMSFORMAT
        elif name in ("Neupreis IServ", "Leihgebühr", "geprüfter Preis") and wert is not None:
            zelle.number_format = _EUROFORMAT


def _schreibe_blatt(ws: Worksheet, blatt: str, zeilen: list[dict[str, object]]) -> None:
    _leeren(ws)
    _schreibe_kopf(ws, blatt)
    for versatz, werte in enumerate(zeilen):
        _schreibe_zeile(ws, blatt, 2 + versatz, werte)


def _preiszeilen(stand: Buchplanung) -> list[dict[str, object]]:
    zeilen: list[dict[str, object]] = []
    for verlag in stand.verlage:
        for buch in sorted(stand.buecher_je_verlag(verlag),
                           key=lambda b: (b.titel.casefold(), b.isbn)):
            pruefung = stand.pruefung(buch.isbn)
            status, hinweis = preis_status(buch, pruefung)
            zeilen.append({
                "Verlag": verlag,
                "Titel": buch.titel,
                "ISBN": buch.isbn,
                "Fächer": buch.fach_anzeige,
                "Jahrgänge": buch.jahrgang_anzeige,
                "Neupreis IServ": buch.neupreis,
                "Leihgebühr": buch.leihgebuehr,
                "geprüfter Preis": pruefung.preis if pruefung else None,
                "Kürzel": pruefung.kuerzel if pruefung else "",
                "Datum": pruefung.datum if pruefung else None,
                "Status": status,
                "Hinweis": hinweis,
                "Bemerkung": pruefung.bemerkung if pruefung else "",
            })
    return zeilen


def _fachzeilen(stand: Buchplanung) -> list[dict[str, object]]:
    zeilen: list[dict[str, object]] = []
    for fach in stand.faecher:
        for buch in sorted(stand.buecher_je_fach(fach),
                           key=lambda b: (b.titel.casefold(), b.isbn)):
            ruecklage = stand.ruecklage(buch.isbn, fach)
            preis, _ = preis_status(buch, stand.pruefung(buch.isbn))
            zeilen.append({
                "Fach": fach,
                "Titel": buch.titel,
                "ISBN": buch.isbn,
                "Verlag": buch.verlag or OHNE_VERLAG,
                "Jahrgänge": buch.jahrgang_anzeige,
                "Herkunft": buch.herkunft,
                "leihbar": _JA if buch.leihbar else _NEIN,
                "Preis": preis,
                "Rücklage Anzahl": ruecklage.anzahl if ruecklage else None,
                "Rücklage Status": ruecklage.status if ruecklage else "",
                "Kürzel": ruecklage.kuerzel if ruecklage else "",
                "Datum": ruecklage.datum if ruecklage else None,
                "Bemerkung": ruecklage.bemerkung if ruecklage else "",
            })
    return zeilen


def _jahrgangszeilen(stand: Buchplanung) -> list[dict[str, object]]:
    zeilen: list[dict[str, object]] = []
    for jahrgang in stand.jahrgaenge:
        for buch in sorted(stand.buecher_je_jahrgang(jahrgang),
                           key=lambda b: (b.titel.casefold(), b.isbn)):
            zeile = stand.planungszeile(buch.isbn, jahrgang)
            herkunft = stand.herkunft(buch, jahrgang)
            zeilen.append({
                "Jahrgang": jahrgang,
                "Titel": buch.titel,
                "ISBN": buch.isbn,
                "Fächer": buch.fach_anzeige,
                "Verlag": buch.verlag or OHNE_VERLAG,
                "Herkunft": herkunft,
                "leihbar": _JA if buch.leihbar else _NEIN,
                "eingeführt ab": zeile.eingefuehrt_ab if zeile else "",
                "ausgemustert nach": zeile.ausgemustert_nach if zeile else "",
                "Status": planungs_status(zeile, stand.schuljahr),
                "Beschluss": zeile.beschluss if zeile else "",
                "Bemerkung": zeile.bemerkung if zeile else "",
            })
    return zeilen


def _bestaetigungszeilen(stand: Buchplanung) -> list[dict[str, object]]:
    zeilen: list[dict[str, object]] = []
    for fach in stand.faecher:
        buecher = stand.buecher_je_fach(fach)
        eintrag = stand.bestaetigung(fach)
        status, hinweis = fach_status(fach, buecher, eintrag)
        zeilen.append({
            "Fach": fach,
            "Bücher": len([b for b in buecher if b.im_aktuellen_jahr]),
            "Status": status,
            "Kürzel": eintrag.kuerzel if eintrag else "",
            "Datum": eintrag.datum if eintrag else None,
            "Bemerkung": eintrag.bemerkung if eintrag else "",
            "Hinweis": hinweis,
            "bestätigter Stand": ", ".join(eintrag.bestaetigte_isbns) if eintrag else "",
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

    zeile(1, "Schulbuchausleihe", "Bücherlisten, Preisprüfung und Planung", fett=True)
    zeile(2, "Schuljahr", stand.schuljahr)
    zeile(3, "Vorjahr", stand.vorjahr)
    zeile(4, "Stand", stand.stand)
    zeile(6, "Eintragen", "Nur die hell hinterlegten Spalten werden gelesen; alle "
                          "anderen schreibt das Dashboard bei jedem Abgleich neu.")
    zeile(8, "Legende", "", fett=True)
    for versatz, (marke, text) in enumerate(LEGENDE):
        zeile(9 + versatz, marke, text)
    naechste = 9 + len(LEGENDE) + 1
    for versatz, warnung in enumerate(stand.warnungen):
        zeile(naechste + versatz, "Hinweis" if versatz == 0 else "", warnung)


def schreibe_mappe(wb: Workbook, stand: Buchplanung) -> None:
    """Schreibt alle fünf Blätter neu - Werte und Gestaltung.

    Bewusst vollständig und nicht zellweise: die Bücher wechseln, Spalten
    können hinzukommen, und ein halb aktualisiertes Blatt wäre die Fassung,
    der man am wenigsten ansieht, woran man ist.
    """
    for name in BLAETTER:
        if name not in wb.sheetnames:
            wb.create_sheet(name)
    _schreibe_blatt(wb[BLATT_PREISE], BLATT_PREISE, _preiszeilen(stand))
    _schreibe_blatt(wb[BLATT_FACH], BLATT_FACH, _fachzeilen(stand))
    _schreibe_blatt(wb[BLATT_JAHRGANG], BLATT_JAHRGANG, _jahrgangszeilen(stand))
    _schreibe_blatt(wb[BLATT_BESTAETIGUNG], BLATT_BESTAETIGUNG, _bestaetigungszeilen(stand))
    _schreibe_info(wb[BLATT_INFO], stand)
    for versatz, name in enumerate(BLAETTER):
        wb.move_sheet(name, offset=versatz - wb.sheetnames.index(name))


def neue_mappe() -> Workbook:
    """Eine leere Mappe mit den fünf Blättern in ihrer Reihenfolge."""
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
