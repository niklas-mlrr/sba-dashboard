"""Die Tabelle der Änderungsliste: Zeilen, Zellen, Einrückung - ohne HTTP und ohne Vorlage.

``aenderungsliste`` (buecherlisten/planung/modelle.py) liefert die Abschnitte
in der Reihenfolge der Seite. Hier wird daraus das Raster, das die Vorlage
nur noch ausgibt:

* Je Abschnitt (Fach, Jahrgang, Wechsel) stehen links die Ausmusterungen,
  rechts die Einführungen, Platz i neben Platz i. Je Platz gibt es eine
  **Titelzeile**, falls links oder rechts ein Buch dort zum ersten Mal in
  seiner Spalte des Fachs steht, und eine **Jahrgangszeile**. Den Titel trägt
  ein Buch nur an seiner obersten Stelle in der Spalte des Fachs; weiter
  unten steht nur die Jahrgangszeile. Wird ein Buch ausgemustert und
  eingeführt, hat es also links und rechts je einen Titel.
* Je Seite ist jedes Buch **eine** Zelle über seine Zeilen. Das letzte Buch
  einer Seite reicht bis zum Ende des Abschnitts (``gestreckt``); eine leere
  Seite ist eine Zelle über den ganzen Abschnitt.
* Ein Kasten hängt mit dem darüber zusammen (``anfang``/``ende`` falsch),
  wenn im Abschnitt davor auf derselben Seite dasselbe Buch zuletzt stand.
* **Einrückung** je Fach und Seite: die Stufe ist die Reihenfolge, in der ein
  Buch von oben nach unten zuerst auftaucht. Sie wirkt nur, wenn in dieser
  Fach-Seite ein Buch **getrennt** steht - eine Zelle ohne Titel, die nicht
  am Kasten darüber hängt -, sonst ist überall Stufe 0.
* Aufeinanderfolgende Abschnitte eines Fachs mit gleichem Wert im vorderen
  Kriterium der Rangfolge (Jahrgang oder Wechseljahr) bilden eine **Gruppe**.
  Ihre Mitte trägt den Wert einmal und je Abschnitt („Teil“) grau das andere
  Kriterium; bei nur einem Teil stehen beide als Paar untereinander.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from buecherlisten.planung import (
    ART_AUSMUSTERUNG,
    ART_EINFUEHRUNG,
    RANG_JAHRGANG,
    RANG_WECHSEL,
    Abschnitt,
    Aenderung,
)
from buecherlisten.planung.modelle import Rang

SEITEN = (ART_AUSMUSTERUNG, ART_EINFUEHRUNG)


@dataclass
class Zelle:
    """Ein Buch auf einer Seite eines Abschnitts - oder die leere Seite (``eintrag`` None)."""

    art: str
    rowspan: int
    eintrag: Any = None
    titel: bool = False
    stufe: int = 0
    anfang: bool = True
    ende: bool = True
    gestreckt: bool = False

    @property
    def leer(self) -> bool:
        return self.eintrag is None


@dataclass
class Mitte:
    """Die Mittelspalte einer Gruppe: fett der Gruppenwert, grau je Teil das andere Kriterium."""

    rowspan: int
    haupt: int
    neben: list[int]

    @property
    def paar(self) -> bool:
        return len(self.neben) == 1


@dataclass
class Zeile:
    teil: int
    unterabschnitt: bool = False
    aus: Zelle | None = None
    ein: Zelle | None = None
    mitte: Mitte | None = None


@dataclass
class Gruppe:
    zeilen: list[Zeile]
    mit_partner: bool


@dataclass
class FachBlock:
    fach: str
    gruppen: list[Gruppe] = field(default_factory=list)


@dataclass
class _Teil:
    """Ein Abschnitt, schon in Zeilen zerlegt - bevor die Gruppen entstehen."""

    abschnitt: Abschnitt
    zeilen: list[Zeile]
    zellen: dict[str, list[tuple[int, Zelle]]]


def _buch(antrag: Aenderung) -> str:
    return antrag.isbn


def baue_tabelle(abschnitte: Sequence[Abschnitt], rang: Rang,
                 eintrag: Callable[[Aenderung], Any] = lambda a: a) -> list[FachBlock]:
    """Das Raster der Seite; ``eintrag`` macht aus einem Antrag, was die Zelle trägt."""
    vorn = rang[0][0]
    hinten = RANG_WECHSEL if vorn == RANG_JAHRGANG else RANG_JAHRGANG
    bloecke: list[FachBlock] = []
    faecher: list[list[_Teil]] = []
    for abschnitt in abschnitte:
        if not bloecke or bloecke[-1].fach != abschnitt.fach:
            bloecke.append(FachBlock(abschnitt.fach))
            faecher.append([])
        faecher[-1].append(_Teil(abschnitt, [], {}))

    for block, teile in zip(bloecke, faecher):
        _zerlege(teile, eintrag)
        _gruppiere(block, teile, vorn, hinten)
    return bloecke


def _zerlege(teile: list[_Teil], eintrag: Callable[[Aenderung], Any]) -> None:
    """Zeilen und Zellen je Abschnitt, Stufen und Trennung je Seite des Fachs."""
    gesehen: dict[str, set[str]] = {art: set() for art in SEITEN}
    stufen: dict[str, dict[str, int]] = {art: {} for art in SEITEN}
    for teil in teile:
        ab = teil.abschnitt
        plaetze = max(len(ab.ausmusterungen), len(ab.einfuehrungen))
        reihen: list[int] = []        # je Zeile der Platz
        titel_bei: set[tuple[str, int]] = set()
        for platz in range(plaetze):
            neue = [art for art in SEITEN
                    if platz < len(ab.seite(art)) and _buch(ab.seite(art)[platz]) not in gesehen[art]]
            for art in SEITEN:
                if platz < len(ab.seite(art)):
                    stufen[art].setdefault(_buch(ab.seite(art)[platz]), len(stufen[art]))
            if neue:
                reihen.append(platz)  # Titelzeile
            reihen.append(platz)      # Jahrgangszeile
            for art in neue:
                gesehen[art].add(_buch(ab.seite(art)[platz]))
                titel_bei.add((art, platz))
        teil.zeilen = [Zeile(teil=0) for _ in reihen]
        for art in SEITEN:
            seite = ab.seite(art)
            if not seite:
                teil.zellen[art] = [(0, Zelle(art=art, rowspan=len(reihen)))]
                continue
            eigene: list[tuple[int, Zelle]] = []
            for platz, antrag in enumerate(seite):
                von = reihen.index(platz)
                eigenes_bis = len(reihen) - 1 - reihen[::-1].index(platz)
                bis = len(reihen) - 1 if platz == len(seite) - 1 else eigenes_bis
                eigene.append((von, Zelle(
                    art=art, rowspan=bis - von + 1, eintrag=eintrag(antrag),
                    titel=(art, platz) in titel_bei, stufe=stufen[art][_buch(antrag)],
                    gestreckt=bis > eigenes_bis,
                )))
            teil.zellen[art] = eigene

    # Zusammenhang über Abschnitte hinweg: steht auf derselben Seite unten im
    # einen und oben im nächsten Abschnitt dasselbe Buch, hängen die Kästen.
    for vorher, nachher in zip(teile, teile[1:]):
        for art in SEITEN:
            oben, unten = vorher.abschnitt.seite(art), nachher.abschnitt.seite(art)
            if oben and unten and _buch(oben[-1]) == _buch(unten[0]):
                vorher.zellen[art][-1][1].ende = False
                nachher.zellen[art][0][1].anfang = False

    # Eingerückt wird nur eine Seite des Fachs, in der ein Buch getrennt steht.
    for art in SEITEN:
        getrennt = any(not z.leer and not z.titel and z.anfang
                       for teil in teile for _, z in teil.zellen[art])
        if not getrennt:
            for teil in teile:
                for _, z in teil.zellen[art]:
                    z.stufe = 0


def _gruppiere(block: FachBlock, teile: list[_Teil], vorn: str, hinten: str) -> None:
    """Folgende Abschnitte mit gleichem Wert im vorderen Kriterium werden eine Gruppe."""
    i = 0
    while i < len(teile):
        gruppe = [teile[i]]
        while i + 1 < len(teile) and teile[i + 1].abschnitt.wert(vorn) == gruppe[0].abschnitt.wert(vorn):
            i += 1
            gruppe.append(teile[i])
        zeilen: list[Zeile] = []
        for nummer, teil in enumerate(gruppe):
            for r, zeile in enumerate(teil.zeilen):
                zeile.teil = nummer
                zeile.unterabschnitt = nummer > 0 and r == 0
            for art in SEITEN:
                for von, zelle in teil.zellen[art]:
                    setattr(teil.zeilen[von], "aus" if art == ART_AUSMUSTERUNG else "ein", zelle)
            zeilen.extend(teil.zeilen)
        zeilen[0].mitte = Mitte(rowspan=len(zeilen), haupt=gruppe[0].abschnitt.wert(vorn),
                                neben=[teil.abschnitt.wert(hinten) for teil in gruppe])
        block.gruppen.append(Gruppe(zeilen=zeilen,
                                    mit_partner=any(t.abschnitt.mit_partner for t in gruppe)))
        i += 1
