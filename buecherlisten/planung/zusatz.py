"""Der Zusatz hinter dem Jahrgang der Fach-Ansicht: je Planungszeile ein Ergebnis.

Entscheidung 2026-11-06 (ersetzt die Tabelle vom 2026-10-31, im Ergebnis
gleich bis auf eine Ausmusterung vor der Einführung): Jede Planungszeile eines
Eintrags (Fach, Jahrgang, „leihbar“) legt ihre Ereignisse auf eine Zeitachse,
gemessen am ausgewählten Schuljahr SJ (ESJ: Einführung zum Schuljahr, ASJ:
Ausmusterung nach dem Schuljahr):

    Ausmusterung nach SJ-1 (nur offen oder abgelehnt), Einführung zu SJ (nur
    offen oder abgelehnt), Ausmusterung nach SJ, Einführung zu SJ+1,
    Ausmusterung nach SJ+1, …

Früheres zählt nie. Aus den Ereignissen, die bleiben, der Reihe nach:

==========================================================  ======================
Ereignisse                                                  Zusatz
==========================================================  ======================
ESJ, dann ASJ, ESJ = ASJ, beide genehmigt                   ``ESJ``
ESJ, dann ASJ, sonst                                        ``von ESJ bis ASJ``
ein ESJ                                                     ``ab ESJ``
ein ASJ                                                     ``bis ASJ``
==========================================================  ======================

Eine Zeile ohne Einführung gilt als längst eingeführt. Steht die Ausmusterung
vor der Einführung (nur aus Excel möglich), ergibt das ``bis ASJ, ab ESJ``.
Die Ergebnisse mehrerer Zeilen stehen mit „, “ getrennt in einer Klammer (bis
2026-11-04 mit „; “). So hat jeder Antrag, über den noch zu entscheiden ist
oder der abgelehnt wurde, ein Jahr mit Kasten.

An jedem Jahr hängt, wenn über seinen Antrag noch nicht oder abschlägig
entschieden ist, ein Kasten „offen“ bzw. „abgelehnt“ (:attr:`Teil.antrag`).
Ohne Netz, ohne Excel, ohne HTTP - wie der Rest von ``buecherlisten.planung``.
"""
from __future__ import annotations

from dataclasses import dataclass

from .aenderungen import zu_entscheidende_antraege
from .modelle import (
    ANTRAG_ABGELEHNT,
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

    ``hinweis`` ist der Tooltip eines entschiedenen Antrags (Entscheidung
    2026-11-04): „Einführung der Buchreihe in Jahrgang 7 genehmigt“, darunter
    „am …“ und „durch …“, soweit bekannt. Ein offener Antrag hat keinen - sein
    Kasten sagt schon alles, Datum und Signatur gibt es nicht.
    """

    text: str
    art: str = ""
    antrag: str = ""
    hinweis: str = ""


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


def entscheidungs_hinweis(zeile: Planungszeile, art: str) -> str:
    """„<Einführung/Ausmusterung> der Buchreihe in Jahrgang N <genehmigt/abgelehnt>“,
    darunter Datum, Signatur und Begründung des Antrags (seit 2026-11-06),
    soweit bekannt - leer, solange der Antrag offen ist."""
    antrag = zeile.antrag(art)
    if antrag.status not in (ANTRAG_GENEHMIGT, ANTRAG_ABGELEHNT):
        return ""
    wort = "Einführung" if art == ART_EINFUEHRUNG else "Ausmusterung"
    zeilen = [f"{wort} der Buchreihe in Jahrgang {zeile.jahrgang} {antrag.status}"]
    if antrag.datum is not None:
        zeilen.append(f"am {antrag.datum.strftime('%d.%m.%Y')}")
    if antrag.signatur:
        zeilen.append(f"durch {antrag.signatur}")
    if zeile.begruendung(art):
        zeilen.append(f"Begründung: {zeile.begruendung(art)}")
    return "\n".join(zeilen)


def _jahr_teil(zeile: Planungszeile, art: str, entscheidbar: tuple[str, ...]) -> Teil:
    """Das Jahr der Einführung bzw. Ausmusterung der Zeile, mit Kasten, wenn nötig."""
    status = zeile.antrag(art).status
    kasten = status if art in entscheidbar and status != ANTRAG_GENEHMIGT else ""
    return Teil(zeile.schuljahr_des_antrags(art), art=art, antrag=kasten,
                hinweis=entscheidungs_hinweis(zeile, art))


def zusatz_der_zeile(zeile: Planungszeile, schuljahr: str) -> Zusatzzeile | None:
    """Das Ergebnis dieser Zeile - ``None``, wenn kein Ereignis bleibt (Modulkopf)."""
    jetzt = _jahr(schuljahr)
    if jetzt is None:
        return None
    esj, asj = zeile.beginn, zeile.ende
    entscheidbar = zu_entscheidende_antraege(zeile, schuljahr)

    def offen(art: str) -> bool:
        """Ist über den Antrag zu entscheiden, und ist er nicht genehmigt?"""
        return art in entscheidbar and zeile.antrag(art).status != ANTRAG_GENEHMIGT

    # Die Zeitachse: eine Einführung zu einem Schuljahr (2·Jahr) kommt vor der
    # Ausmusterung nach demselben (2·Jahr+1).
    ereignisse: list[tuple[int, str]] = []
    if esj is not None and (esj > jetzt or (esj == jetzt and offen(ART_EINFUEHRUNG))):
        ereignisse.append((2 * esj, ART_EINFUEHRUNG))
    if asj is not None and (asj >= jetzt or (asj == jetzt - 1 and offen(ART_AUSMUSTERUNG))):
        ereignisse.append((2 * asj + 1, ART_AUSMUSTERUNG))
    folge = [art for _, art in sorted(ereignisse)]
    if not folge:
        return None

    def jahr(art: str) -> Teil:
        return _jahr_teil(zeile, art, entscheidbar)

    teile: list[Teil] = []
    if folge == [ART_EINFUEHRUNG, ART_AUSMUSTERUNG]:
        if esj == asj and all(zeile.antrag(art).status == ANTRAG_GENEHMIGT for art in folge):
            teile = [jahr(ART_EINFUEHRUNG)]
        else:
            teile = [Teil("von "), jahr(ART_EINFUEHRUNG), Teil(" bis "), jahr(ART_AUSMUSTERUNG)]
    else:
        for art in folge:
            if teile:
                teile.append(Teil(", "))
            teile += [Teil("ab " if art == ART_EINFUEHRUNG else "bis "), jahr(art)]
    return Zusatzzeile(tuple(teile))


def zusatz_je_zeile(zeilen: tuple[Planungszeile, ...], schuljahr: str) -> tuple[Zusatzzeile, ...]:
    """Die Ergebnisse der ``zeilen`` in ihrer Reihenfolge - ohne die ohne Ergebnis."""
    ergebnisse = (zusatz_der_zeile(zeile, schuljahr) for zeile in zeilen)
    return tuple(ergebnis for ergebnis in ergebnisse if ergebnis is not None)
