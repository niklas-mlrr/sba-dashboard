"""Die Datei (Soll) mit IServ (Ist) vergleichen - je Buch, über alle Fächer und Jahrgänge.

Seit 2026-09-25 zeigen die Bücherlisten-Seiten den Stand der Datei, nicht den
aus IServ. IServ wird live geholt und nur noch verglichen; was abweicht, wird
farbig markiert. Dieses Modul entscheidet, **was** abweicht - ohne HTTP, ohne
Vorlage, damit die Regel an einer Stelle steht und sich prüfen lässt.

Die Regel: ein Buch ist gleich, wenn

* seine ISBN in der Datei **und** in einer Bücherliste dieses Schuljahrs steht,
* Titel, Verlag, Neupreis und Leihgebühr übereinstimmen (Preise auf
  den Cent, Texte ohne Randleerzeichen - wie eine Korrektur in
  :mod:`~buecherlisten.planung.abgleich`), und
* die (Fach, Jahrgang)-Paare übereinstimmen: die aus IServ mit denen, in denen
  das Buch laut Datei **in diesem Schuljahr** geführt wird. Das ist
  :func:`~buecherlisten.planung.modelle.wirkt_im_schuljahr` - eingeführt in
  diesem Schuljahr oder vorher, ausgemustert nach diesem Schuljahr oder später.
* in jedem dieser Paare „leihbar“ übereinstimmt - in IServ je Jahrgangsliste,
  in der Datei je Zeile (seit 2026-10-10).

Ein Buch in zwei Fächern ist damit nur gleich, wenn es in beiden gleich ist,
ein Mehrjahresband nur, wenn jeder seiner Jahrgänge stimmt.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .modelle import (
    ISERV_FELD,
    OHNE_VERLAG,
    Buch,
    Buchplanung,
    wirkt_im_schuljahr,
)

BEIDE = "beide"
NUR_EXCEL = "nur_excel"
NUR_ISERV = "nur_iserv"

Paar = tuple[str, int]


@dataclass(frozen=True)
class IservBuch:
    """Ein Buch, wie es die Bücherlisten dieses Schuljahrs in IServ führen - roh,
    ohne die Korrekturen aus der Datei."""

    isbn: str
    titel: str
    verlag: str
    neupreis: float | None
    leihgebuehr: float | None
    leihbar: bool
    paare: frozenset[Paar]
    # Die Paare, in denen der Eintrag leihbar ist - ``borrowable`` steht in
    # IServ je Jahrgangsliste. ``None``: in allen Paaren wie ``leihbar``.
    leihbar_paare: frozenset[Paar] | None = None

    def leihbar_in(self, paar: Paar) -> bool:
        return self.leihbar if self.leihbar_paare is None else paar in self.leihbar_paare


@dataclass(frozen=True)
class Abweichung:
    """Was IServ zu einem Buch anders sagt als die Datei.

    ``felder`` nennt je abweichendem Feld den Wert **aus IServ**; der Wert der
    Datei ist der, der angezeigt wird. ``fehlt_in_iserv`` sind Paare, in denen
    das Buch laut Datei in diesem Schuljahr geführt wird, IServ es aber nicht
    listet, ``nur_in_iserv`` das Umgekehrte. ``leihbar_anders`` sind die Paare
    beider Seiten, in denen „leihbar“ abweicht, mit dem Wert aus IServ; ist es
    eines, steht auch ``leihbar`` in ``felder``.
    """

    isbn: str
    art: str
    felder: tuple[tuple[str, object], ...] = ()
    fehlt_in_iserv: tuple[Paar, ...] = ()
    nur_in_iserv: tuple[Paar, ...] = ()
    leihbar_anders: tuple[tuple[Paar, bool], ...] = ()

    @property
    def gleich(self) -> bool:
        return (self.art == BEIDE and not self.felder and not self.leihbar_anders
                and not self.fehlt_in_iserv and not self.nur_in_iserv)

    @property
    def iserv(self) -> dict[str, object]:
        return dict(self.felder)


def _sortiert(paare: set[Paar] | frozenset[Paar]) -> tuple[Paar, ...]:
    return tuple(sorted(paare, key=lambda paar: (paar[0].casefold(), paar[1])))


def aktive_paare(planung: Buchplanung, buch: Buch) -> frozenset[Paar]:
    """Die (Fach, Jahrgang)-Paare, in denen die Datei das Buch dieses Schuljahr führt."""
    return frozenset(
        (fach, jahrgang) for fach, jahrgang in planung.zeilen_des_buchs(buch)
        if any(wirkt_im_schuljahr(zeile, planung.schuljahr)
               for zeile in planung.zeilen_des_paars(buch.isbn, fach, jahrgang))
    )


def leihbar_im_schuljahr(planung: Buchplanung, isbn: str, paar: Paar) -> bool:
    """Ist das Buch in diesem Paar dieses Schuljahr leihbar - laut der Zeile, die wirkt?"""
    return any(zeile.leihbar for zeile in planung.zeilen_des_paars(isbn, *paar)
               if wirkt_im_schuljahr(zeile, planung.schuljahr))


def _gleich(a: object, b: object) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return round(float(a), 2) == round(float(b), 2)
    if isinstance(a, str) and isinstance(b, str):
        return a.strip() == b.strip()
    return a == b


def _verlag(name: str) -> str:
    return "" if name == OHNE_VERLAG else name


def vergleiche(planung: Buchplanung, iserv: Mapping[str, IservBuch]) -> dict[str, Abweichung]:
    """Je ISBN, die in diesem Schuljahr auf einer der beiden Seiten vorkommt, ihr Vergleich.

    Ein Buch, das in der Datei steht, dieses Schuljahr aber nirgends geführt
    wird (geplant, ausgemustert) und auch in IServ fehlt, kommt nicht vor: an
    ihm ist nichts zu vergleichen.
    """
    ergebnis: dict[str, Abweichung] = {}
    for buch in planung.buecher:
        soll = aktive_paare(planung, buch)
        ist = iserv.get(buch.isbn)
        if ist is None:
            if soll:
                ergebnis[buch.isbn] = Abweichung(buch.isbn, NUR_EXCEL,
                                                 fehlt_in_iserv=_sortiert(soll))
            continue
        if not soll:
            ergebnis[buch.isbn] = Abweichung(buch.isbn, NUR_ISERV,
                                             nur_in_iserv=_sortiert(ist.paare))
            continue
        felder = []
        for feld in ISERV_FELD:
            eigen, fremd = getattr(buch, feld), getattr(ist, feld)
            if feld == "verlag":
                eigen, fremd = _verlag(eigen), _verlag(fremd)
            if not _gleich(eigen, fremd):
                felder.append((feld, fremd))
        leihbar_anders = tuple(
            (paar, ist.leihbar_in(paar)) for paar in _sortiert(soll & ist.paare)
            if leihbar_im_schuljahr(planung, buch.isbn, paar) != ist.leihbar_in(paar)
        )
        if leihbar_anders:
            felder.append(("leihbar", leihbar_anders[0][1]))
        ergebnis[buch.isbn] = Abweichung(
            buch.isbn, BEIDE, felder=tuple(felder),
            fehlt_in_iserv=_sortiert(soll - ist.paare),
            nur_in_iserv=_sortiert(ist.paare - soll),
            leihbar_anders=leihbar_anders,
        )
    for isbn, ist in iserv.items():
        if isbn not in ergebnis:
            ergebnis[isbn] = Abweichung(isbn, NUR_ISERV, nur_in_iserv=_sortiert(ist.paare))
    return ergebnis
