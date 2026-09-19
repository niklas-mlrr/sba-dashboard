"""Aus zwei Schuljahren die Marken rechnen - das Herzstück des Pakets.

Rein rechnend: kein Netz, keine Datei, keine Uhr außer dem übergebenen Datum.
Damit lässt sich jede Regel mit ein paar Zeilen Testdaten festnageln, statt sie
erst an einer echten IServ-Instanz zu bemerken.

## Die Frage, die eine Zelle beantwortet

Zeile „Jahrgang N" meint die Schülerinnen und Schüler, die im **abgelaufenen**
Schuljahr in N waren. Verglichen wird ihre Bücherliste mit der von **N+1** im
laufenden Schuljahr: Was dort wieder steht, ist ein Mehrjahresband und bleibt
bei ihnen; was nirgends mehr steht, ist ausgemustert und darf ebenfalls bleiben;
alles andere ist abzugeben.

Betrachtet werden nur **leihbare** Bücher. Ein Kaufbuch gehört den Schülern
ohnehin, es kann weder abgegeben noch ausgemustert werden.

## Warum "ausgemustert" über alle Jahrgänge geht

Ein Buch, das im neuen Schuljahr in *irgendeiner* Liste steht, wird weiter
gebraucht - sei es in einem anderen Jahrgang. Nur wenn es in **keiner** mehr
steht, ist die Reihe aus dem Verkehr, und dann lohnt das Einsammeln nicht mehr.
"""
from __future__ import annotations

from datetime import date

from .modelle import (
    ABGEBEN,
    AUSGEMUSTERT,
    BEHALTEN,
    MARKE_ABGEBEN,
    MARKE_AUSGEMUSTERT,
    MARKE_BEHALTEN,
    MARKE_KEIN_BUCH,
    OHNE_AUFGABENFELD,
    SONDER_BUCHSTABEN,
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

# Reihenfolge der Spaltengruppen. Was die Schulwebsite sonst noch als
# Aufgabenfeld führt, kommt dahinter (alphabetisch), Fächer ohne Aufgabenfeld
# ganz zuletzt.
_FELDER_VORNE = ("Aufgabenfeld A", "Aufgabenfeld B", "Aufgabenfeld C")

_AUSGANG_MARKE = {
    ABGEBEN: MARKE_ABGEBEN,
    BEHALTEN: MARKE_BEHALTEN,
    AUSGEMUSTERT: MARKE_AUSGEMUSTERT,
}


class ZuVieleSonderfaelle(RuntimeError):
    """Mehr verschiedene Mischfälle, als es Buchstaben gibt."""


def _titelliste(titel: list[str]) -> str:
    """„A“, „A" und „B", „A", „B" und „C" - mit typografischen Anführungszeichen."""
    gesetzt = [f"„{einzeln}“" for einzeln in titel]
    if len(gesetzt) == 1:
        return gesetzt[0]
    return ", ".join(gesetzt[:-1]) + " und " + gesetzt[-1]


def _sonderfall_text(buecher: tuple[Buchausgang, ...]) -> str:
    """Der Legendensatz eines Mischfalls, mit den Titeln ausgeschrieben.

    Beispiel: ``nur „Deutschbuch 8" muss abgegeben werden; „Duden" ist bei
    erneuter Teilnahme nicht abzugegeben``.
    """
    je_ausgang: dict[str, list[str]] = {ABGEBEN: [], BEHALTEN: [], AUSGEMUSTERT: []}
    for buch in buecher:
        je_ausgang[buch.ausgang].append(buch.titel)

    teile: list[str] = []
    abzugeben = je_ausgang[ABGEBEN]
    if abzugeben:
        verb = "muss" if len(abzugeben) == 1 else "müssen"
        teile.append(f"nur {_titelliste(abzugeben)} {verb} abgegeben werden")
    else:
        teile.append("nichts muss abgegeben werden")
    if je_ausgang[BEHALTEN]:
        verb = "ist" if len(je_ausgang[BEHALTEN]) == 1 else "sind"
        teile.append(f"{_titelliste(je_ausgang[BEHALTEN])} {verb} bei erneuter "
                     "Teilnahme nicht abzugegeben")
    if je_ausgang[AUSGEMUSTERT]:
        verb = "darf" if len(je_ausgang[AUSGEMUSTERT]) == 1 else "dürfen"
        teile.append(f"{_titelliste(je_ausgang[AUSGEMUSTERT])} {verb} behalten werden, "
                     "da ausgemustert")
    return "; ".join(teile)


class _Sonderfaelle:
    """Vergibt die Buchstaben und hält fest, welcher Fall welchen bekam.

    Derselbe Fall - dieselben Titel mit denselben Ausgängen - bekommt **einen**
    Buchstaben, auch wenn er in mehreren Zellen steht: zwei Legendenzeilen mit
    demselben Wortlaut wären für die Lehrkraft eine Frage, keine Auskunft.
    """

    def __init__(self) -> None:
        self._je_schluessel: dict[tuple[tuple[str, str], ...], Sonderfall] = {}

    def buchstabe(self, buecher: tuple[Buchausgang, ...]) -> str:
        schluessel = tuple(sorted((buch.titel, buch.ausgang) for buch in buecher))
        vorhanden = self._je_schluessel.get(schluessel)
        if vorhanden is not None:
            return vorhanden.buchstabe
        if len(self._je_schluessel) >= len(SONDER_BUCHSTABEN):
            raise ZuVieleSonderfaelle(
                "Es gibt mehr Fächer mit gemischten Büchern, als die Übersicht "
                f"Buchstaben hat ({len(SONDER_BUCHSTABEN)}). Die Bücherlisten sind "
                "dafür zu uneinheitlich - bitte von Hand prüfen."
            )
        fall = Sonderfall(
            buchstabe=SONDER_BUCHSTABEN[len(self._je_schluessel)],
            text=_sonderfall_text(buecher),
        )
        self._je_schluessel[schluessel] = fall
        return fall.buchstabe

    def alle(self) -> tuple[Sonderfall, ...]:
        return tuple(self._je_schluessel.values())


def _fach_namen(buch: Buchvorkommen, aliase: dict[str, str]) -> tuple[str, ...]:
    return tuple(aliase.get(fach, fach) for fach in buch.faecher)


def _spalten(
    alt: Schuljahr,
    neu: Schuljahr,
    *,
    bestehende: tuple[Spalte, ...],
    aufgabenfelder: dict[str, str],
    aliase: dict[str, str],
) -> tuple[Spalte, ...]:
    """Alle Fächer, nach Aufgabenfeld gruppiert, bestehende Spalten zuerst.

    Die bestehende Reihenfolge gewinnt innerhalb eines Aufgabenfelds: wer die
    Datei kennt, soll seine Spalten wiederfinden. Neue Fächer kommen alphabetisch
    dahinter, Fächer ohne Aufgabenfeld alphabetisch ganz ans Ende.
    """
    feld_je_fach = {spalte.fach: spalte.aufgabenfeld for spalte in bestehende}
    for fach, feld in aufgabenfelder.items():
        # Die Website ist die führende Quelle; die Datei nur der Rückfall.
        feld_je_fach[aliase.get(fach, fach)] = feld

    # Absichtlich alle Bücher, nicht nur die leihbaren: ein Fach, in dem es nur
    # Kaufbücher gibt, soll seine Spalte behalten und dort "---" zeigen - genau
    # das sagt die Legende ("kein (physisches)/(ausleihbares) Buch in diesem
    # Fach"). Eine fehlende Spalte wäre stattdessen die Behauptung, das Fach
    # werde nicht unterrichtet.
    aus_listen = {
        fach
        for schuljahr in (alt, neu)
        for liste in schuljahr.listen
        for buch in liste.buecher
        for fach in _fach_namen(buch, aliase)
    }
    alle = [spalte.fach for spalte in bestehende]
    alle += sorted(fach for fach in aus_listen if fach not in set(alle))

    reihenfolge = {fach: nummer for nummer, fach in enumerate(spalte.fach for spalte in bestehende)}

    def gruppe(fach: str) -> tuple[int, str]:
        feld = feld_je_fach.get(fach) or OHNE_AUFGABENFELD
        if feld in _FELDER_VORNE:
            return (_FELDER_VORNE.index(feld), feld)
        return (len(_FELDER_VORNE) + (1 if feld == OHNE_AUFGABENFELD else 0), feld)

    def schluessel(fach: str) -> tuple[tuple[int, str], int, str]:
        # Bestehende Spalten behalten ihren Platz (0..n), neue kommen danach
        # und werden alphabetisch einsortiert.
        return (gruppe(fach), reihenfolge.get(fach, len(reihenfolge)), fach.casefold())

    return tuple(
        Spalte(fach=fach, aufgabenfeld=feld_je_fach.get(fach) or OHNE_AUFGABENFELD)
        for fach in sorted(dict.fromkeys(alle), key=schluessel)
    )


def _ausgaenge(
    liste: Jahrgangsliste,
    *,
    fach: str,
    aliase: dict[str, str],
    naechste: Jahrgangsliste | None,
    noch_im_umlauf: set[str],
) -> tuple[Buchausgang, ...]:
    """Die leihbaren Bücher eines Fachs in dieser Liste - und was mit ihnen geschieht."""
    weiter = {buch.isbn for buch in naechste.leihbare} if naechste else set()
    ergebnis: list[Buchausgang] = []
    for buch in liste.leihbare:
        if fach not in _fach_namen(buch, aliase):
            continue
        if buch.isbn not in noch_im_umlauf:
            ausgang = AUSGEMUSTERT
        elif buch.isbn in weiter:
            ausgang = BEHALTEN
        else:
            ausgang = ABGEBEN
        ergebnis.append(Buchausgang(isbn=buch.isbn, titel=buch.titel, ausgang=ausgang))
    return tuple(ergebnis)


def _hinweis(buecher: tuple[Buchausgang, ...], schuljahr: str) -> str:
    """Der Satz für einen Jahrgang mit individueller Ausleihe.

    Dort gibt es keine Pakete, sondern eine Anmeldung je Buch - welche Bücher
    jemand behalten darf, hängt also an seiner eigenen Anmeldung und nicht am
    Jahrgang. Fest steht nur die Ausnahme: ausgemusterte Reihen sammelt niemand
    mehr ein, und die lassen sich benennen.
    """
    satz = (f"Alle Bücher, für die im Schuljahr {schuljahr} keine erneute Anmeldung "
            "besteht, sind abzugeben.")
    ausgemustert = sorted({buch.titel for buch in buecher if buch.ausgang == AUSGEMUSTERT})
    if ausgemustert:
        verb = "darf" if len(ausgemustert) == 1 else "dürfen"
        satz += (f" Ausgenommen: {_titelliste(ausgemustert)} {verb} behalten werden, "
                 "da ausgemustert.")
    return satz


def vergleiche(
    alt: Schuljahr,
    neu: Schuljahr,
    *,
    bestehende_spalten: tuple[Spalte, ...] = (),
    aufgabenfelder: dict[str, str] | None = None,
    aliase: dict[str, str] | None = None,
    warnungen: tuple[str, ...] = (),
    heute: date | None = None,
) -> Uebersicht:
    """Die fertige Übersicht aus dem abgelaufenen (``alt``) und dem neuen Jahr.

    ``bestehende_spalten`` sind die Fachspalten, die schon in der Datei stehen -
    sie halten deren Reihenfolge. ``aufgabenfelder`` ordnet Fach → Aufgabenfeld
    (von der Schulwebsite, siehe ``buecherlisten.trg_web``), ``aliase`` bildet
    IServ-Fachnamen auf die Spaltennamen der Datei ab.
    """
    aufgabenfelder = dict(aufgabenfelder or {})
    aliase = dict(aliase or {})
    spalten = _spalten(alt, neu, bestehende=bestehende_spalten,
                       aufgabenfelder=aufgabenfelder, aliase=aliase)

    # Ein Buch ist ausgemustert, wenn es in **keiner** Liste des neuen Jahres
    # mehr leihbar vorkommt - egal in welchem Jahrgang.
    noch_im_umlauf = {
        buch.isbn for liste in neu.listen for buch in liste.leihbare
    }
    sonderfaelle = _Sonderfaelle()

    zeilen: list[Jahrgangszeile] = []
    for liste in sorted(alt.listen, key=lambda liste: liste.jahrgang):
        naechste = neu.liste(liste.jahrgang + 1)
        # Der letzte Jahrgang zuerst: dort gibt es kein "nächstes Jahr" mehr, in
        # das ein Buch mitwandern könnte - auch dann nicht, wenn dieser Jahrgang
        # individuell ausleiht.
        letzter = naechste is None
        alle_ausgaenge = tuple(
            ausgang
            for spalte in spalten
            for ausgang in _ausgaenge(liste, fach=spalte.fach, aliase=aliase,
                                      naechste=naechste, noch_im_umlauf=noch_im_umlauf)
        )
        if not letzter and not liste.paket:
            zeilen.append(Jahrgangszeile(jahrgang=liste.jahrgang,
                                         hinweis=_hinweis(alle_ausgaenge, neu.name)))
            continue

        zellen: list[Zelle] = []
        for spalte in spalten:
            buecher = _ausgaenge(liste, fach=spalte.fach, aliase=aliase,
                                 naechste=naechste, noch_im_umlauf=noch_im_umlauf)
            if not buecher:
                marke = MARKE_KEIN_BUCH
            else:
                ausgaenge = {buch.ausgang for buch in buecher}
                marke = (_AUSGANG_MARKE[ausgaenge.pop()] if len(ausgaenge) == 1
                         else sonderfaelle.buchstabe(buecher))
            zellen.append(Zelle(fach=spalte.fach, marke=marke, buecher=buecher))
        zeilen.append(Jahrgangszeile(jahrgang=liste.jahrgang, zellen=tuple(zellen)))

    return Uebersicht(
        spalten=spalten,
        zeilen=tuple(zeilen),
        sonderfaelle=sonderfaelle.alle(),
        schuljahr_alt=alt.name,
        schuljahr_neu=neu.name,
        erzeugt=heute or date.today(),
        warnungen=tuple(warnungen),
    )
