"""JSON-Schnappschüsse für die Konflikterkennung der Buchplanung.

Vorlagen und Schreibpfad verwenden denselben Vertrag: Ein Menü schickt seinen
Stand als ``vorher`` zurück. Unter dem Mappenschloss wird er mit dem aktuellen
Eintrag verglichen, unabhängig von Änderungen an anderen Büchern.

Die Typen beschreiben die erzeugten Schnappschüsse; sie validieren keine
Eingaben und ändern weder die JSON-Darstellung noch die Vergleichsregeln.
"""
from __future__ import annotations

from typing import TypedDict

from buecherlisten.planung import (
    FACH_BESTAETIGT,
    OHNE_VERLAG,
    Buchplanung,
    fach_bestaetigung,
    fach_status,
)


class Buchreihenstand(TypedDict):
    titel: str
    verlag: str
    neupreis: float | None
    leihgebuehr: float | None
    bemerkung: str


class Zeilenstand(TypedDict):
    jahrgang: int
    eingefuehrt_ab: str
    ausgemustert_nach: str
    leihbar: bool
    bemerkung: str


class Ruecklagenstand(TypedDict):
    anzahl: int | None
    bemerkung: str


class EintragStand(TypedDict):
    buchreihe: Buchreihenstand
    zeilen: dict[str, Zeilenstand]
    ruecklage: Ruecklagenstand | None


class Fachbestaetigungsstand(TypedDict):
    kuerzel: str
    datum: str | None


class FachStand(TypedDict):
    fach: Fachbestaetigungsstand


def eintrag_stand(planung: Buchplanung, isbn: str, fach: str) -> EintragStand | None:
    """Das Buchmenü eines Buchs in einem Fach als Schnappschuss - ``None`` ohne Buch.

    Die Zeilen sind nach „Jahrgang|Einführung“ geschlüsselt, so wie das Menü
    sie kennt (``data-bisher-jahrgang``/``data-bisher-ab``). ``ruecklage`` ist
    ``None`` bei einem Buch, für das es keine geben kann - dann hat das Menü
    keinen Block dafür.
    """
    buch = planung.buch(isbn)
    if buch is None:
        return None
    bemerkung = planung.bemerkung(isbn)
    ruecklage = planung.ruecklage(isbn, fach)
    return {
        "buchreihe": {
            "titel": buch.titel, "verlag": "" if buch.verlag == OHNE_VERLAG else buch.verlag,
            "neupreis": buch.neupreis, "leihgebuehr": buch.leihgebuehr,
            "bemerkung": bemerkung.bemerkung if bemerkung else "",
        },
        "zeilen": {
            f"{zeile.jahrgang}|{zeile.eingefuehrt_ab}": {
                "jahrgang": zeile.jahrgang, "eingefuehrt_ab": zeile.eingefuehrt_ab,
                "ausgemustert_nach": zeile.ausgemustert_nach, "leihbar": zeile.leihbar,
                "bemerkung": zeile.bemerkung,
            }
            for zeile in planung.planung if (zeile.isbn, zeile.fach) == (isbn, fach)
        },
        "ruecklage": {
            "anzahl": ruecklage.anzahl if ruecklage else None,
            "bemerkung": ruecklage.bemerkung if ruecklage else "",
        } if planung.leihbar(isbn) else None,
    }


def fach_stand(planung: Buchplanung, fach: str) -> FachStand:
    """Die Bestätigung einer Fachliste als Schnappschuss - für die beiden Kopfmenüs."""
    kuerzel, datum = fach_bestaetigung(planung, fach)
    if fach_status(planung, fach).status != FACH_BESTAETIGT:
        kuerzel, datum = "", None
    return {"fach": {"kuerzel": kuerzel, "datum": datum.isoformat() if datum else None}}
