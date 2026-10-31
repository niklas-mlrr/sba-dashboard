"""Der Zusatz hinter dem Jahrgang der Fach-Ansicht: je Planungszeile ein Ergebnis.

Entscheidung 2026-10-31: Jede Planungszeile eines Eintrags (Fach, Jahrgang,
„leihbar“) prüft ihre Jahre gegen das ausgewählte Schuljahr (SJ; ESJ ist das
Einführungsjahr der Zeile, ASJ das Ausmusterungsjahr) und liefert genau eines:

========================  ==================
Bedingung                 Zusatz
========================  ==================
ESJ ≤ SJ ≤ ASJ            ``bis ASJ``
SJ < ESJ = ASJ            ``ESJ``
SJ < ESJ < ASJ            ``von ESJ bis ASJ``
SJ < ESJ, ohne ASJ        ``ab ESJ``
sonst                     nichts
========================  ==================

Eine Zeile ohne Einführung gilt als längst eingeführt (ESJ ≤ SJ). Die
Ergebnisse mehrerer Zeilen stehen mit „; “ getrennt in einer Klammer.

Drei Sonderfälle, damit jeder Antrag, über den noch zu entscheiden ist oder der
abgelehnt wurde, ein Jahr mit Kasten hat:

* Einführung und Ausmusterung im selben künftigen Jahr stehen als
  ``von ESJ bis ASJ``, bis **beide** Anträge genehmigt sind; erst danach gilt
  die Tabelle.
* ESJ = SJ (zum laufenden Schuljahr eingeführt), Einführung nicht genehmigt:
  ``von ESJ bis ASJ`` bzw. ``ab ESJ`` statt ``bis ASJ``.
* ASJ = SJ-1 (nach dem Vorjahr ausgemustert), Ausmusterung nicht genehmigt:
  ``bis ASJ`` statt nichts.

An jedem Jahr hängt, wenn über seinen Antrag noch nicht oder abschlägig
entschieden ist, ein Kasten „offen“ bzw. „abgelehnt“ (:attr:`Teil.antrag`).
Ohne Netz, ohne Excel, ohne HTTP - wie der Rest von ``buecherlisten.planung``.
"""
from __future__ import annotations

from dataclasses import dataclass

from .aenderungen import zu_entscheidende_antraege
from .modelle import (
    ANTRAG_GENEHMIGT,
    ART_AUSMUSTERUNG,
    ART_EINFUEHRUNG,
    Planungszeile,
    UngueltigesSchuljahr,
    schuljahr_zahl,
)


@dataclass(frozen=True)
class Teil:
    """Ein Stück des Zusatzes: Text („ab “) oder ein Jahr.

    ``art`` ist bei einem Jahr die Art des Antrags, dem es gehört
    (``einfuehrung`` oder ``ausmusterung``), sonst leer. ``antrag`` ist
    ``offen`` oder ``abgelehnt``, wenn an dem Jahr ein Kasten hängt - leer,
    wenn der Antrag genehmigt ist oder über ihn nicht entschieden wird.
    """

    text: str
    art: str = ""
    antrag: str = ""


@dataclass(frozen=True)
class Zusatzzeile:
    """Das Ergebnis einer Planungszeile, in Stücken."""

    teile: tuple[Teil, ...]

    @property
    def text(self) -> str:
        return "".join(teil.text for teil in self.teile)


def _jahr(angabe: str) -> int | None:
    try:
        return schuljahr_zahl(angabe) if angabe else None
    except UngueltigesSchuljahr:
        return None


def _jahr_teil(zeile: Planungszeile, art: str, entscheidbar: tuple[str, ...]) -> Teil:
    """Das Jahr der Einführung bzw. Ausmusterung der Zeile, mit Kasten, wenn nötig."""
    status = zeile.antrag(art).status
    kasten = status if art in entscheidbar and status != ANTRAG_GENEHMIGT else ""
    return Teil(zeile.schuljahr_des_antrags(art), art=art, antrag=kasten)


def zusatz_der_zeile(zeile: Planungszeile, schuljahr: str) -> Zusatzzeile | None:
    """Das Ergebnis dieser Zeile - ``None``, wenn keine Regel zutrifft."""
    jetzt = _jahr(schuljahr)
    if jetzt is None:
        return None
    esj, asj = zeile.beginn, zeile.ende
    entscheidbar = zu_entscheidende_antraege(zeile, schuljahr)

    def einfuehrung() -> Teil:
        return _jahr_teil(zeile, ART_EINFUEHRUNG, entscheidbar)

    def ausmusterung() -> Teil:
        return _jahr_teil(zeile, ART_AUSMUSTERUNG, entscheidbar)

    def offen(art: str) -> bool:
        """Ist über den Antrag zu entscheiden, und ist er nicht genehmigt?"""
        return art in entscheidbar and zeile.antrag(art).status != ANTRAG_GENEHMIGT

    laeuft = esj is None or esj <= jetzt
    if asj is not None and laeuft and jetzt <= asj:
        # Zum laufenden Schuljahr eingeführt, Antrag nicht genehmigt: auch die
        # Einführung steht da, damit ihr Kasten ein Jahr hat.
        if esj == jetzt and offen(ART_EINFUEHRUNG):
            return Zusatzzeile((Teil("von "), einfuehrung(), Teil(" bis "), ausmusterung()))
        return Zusatzzeile((Teil("bis "), ausmusterung()))
    if asj is not None and laeuft and asj == jetzt - 1 and offen(ART_AUSMUSTERUNG):
        # Nach dem Vorjahr ausgemustert, Antrag nicht genehmigt: das Jahr bleibt
        # mit seinem Kasten stehen.
        return Zusatzzeile((Teil("bis "), ausmusterung()))
    if esj is None:
        return None
    if esj == jetzt and asj is None and offen(ART_EINFUEHRUNG):
        return Zusatzzeile((Teil("ab "), einfuehrung()))
    if jetzt >= esj:
        return None
    if asj is None or asj < esj:
        return Zusatzzeile((Teil("ab "), einfuehrung()))
    if asj > esj:
        return Zusatzzeile((Teil("von "), einfuehrung(), Teil(" bis "), ausmusterung()))
    # Einführung und Ausmusterung im selben künftigen Jahr.
    if all(zeile.antrag(art).status == ANTRAG_GENEHMIGT
           for art in (ART_EINFUEHRUNG, ART_AUSMUSTERUNG)):
        return Zusatzzeile((einfuehrung(),))
    return Zusatzzeile((Teil("von "), einfuehrung(), Teil(" bis "), ausmusterung()))


def zusatz_je_zeile(zeilen: tuple[Planungszeile, ...], schuljahr: str) -> tuple[Zusatzzeile, ...]:
    """Die Ergebnisse der ``zeilen`` in ihrer Reihenfolge - ohne die ohne Ergebnis."""
    ergebnisse = (zusatz_der_zeile(zeile, schuljahr) for zeile in zeilen)
    return tuple(ergebnis for ergebnis in ergebnisse if ergebnis is not None)
