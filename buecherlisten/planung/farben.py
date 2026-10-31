"""Die Farben der Bücherliste eines Fachs - aus der Planung, nicht aus IServ.

Entscheidung 2026-10-30: In der Fach-Ansicht färben Einführung und
Ausmusterung nach den eingetragenen Schuljahren, nicht nach dem Vergleich mit
IServ (die Verlags- und Jahrgangsansicht vergleichen weiter mit IServ). Drei
Farben, immer in dieser Reihenfolge - im Strich vorn von oben nach unten, in
einer Zelle in waagerechten Bändern:

* **rot** - eine Ausmusterung nach dem Vorjahr oder später. Gibt es das Buch
  danach in keinem Fach und keinem Jahrgang mehr, ist die ganze Zeile rot,
  sonst nur die Zelle „Jahrgang“. Die Jahrgangszahl selbst ist rot und
  durchgestrichen, wenn nach dem Vorjahr ausgemustert wird.
* **gelb** - eine Änderung. Hier nur „leihbar“: ein Wechsel, also eine Zeile,
  die mit dem Vorjahr endet, und im selben Jahrgang eine, die danach mit dem
  anderen Häkchen beginnt. Er zählt nur gelb (Zelle „Leihbar“), nicht zugleich
  rot und blau. Titel, Verlag und Preise vergleicht weiter die Anwendung mit
  IServ - die Datei kennt keine alten Werte.
* **blau** - eine Einführung zum laufenden Schuljahr oder später. Wird das
  Buch zum ersten Mal überhaupt eingeführt (keine Zeile in irgendeinem Fach
  lief schon), ist die ganze Zeile blau, sonst nur die Zelle „Jahrgang“. Die
  Jahrgangszahl ist blau, wenn zum laufenden Schuljahr eingeführt wird.

Ohne Netz, ohne Excel, ohne HTTP - wie der Rest von ``buecherlisten.planung``.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .modelle import (
    PLANUNG_AUSGEMUSTERT,
    Buch,
    Buchplanung,
    Planungszeile,
    UngueltigesSchuljahr,
    planungs_status,
    planungs_zusatz,
    schuljahr_zahl,
)

AUSMUSTERUNG = "ausmusterung"
AENDERUNG = "aenderung"
EINFUEHRUNG = "einfuehrung"
REIHENFOLGE: tuple[str, ...] = (AUSMUSTERUNG, AENDERUNG, EINFUEHRUNG)


def geordnet(*mengen: Iterable[str]) -> tuple[str, ...]:
    """Die Farben aus allen ``mengen``, in der Reihenfolge rot, gelb, blau."""
    alle = {farbe for menge in mengen for farbe in menge}
    return tuple(farbe for farbe in REIHENFOLGE if farbe in alle)


@dataclass(frozen=True)
class Jahrgangswert:
    """Ein Jahrgang in der Spalte „Jahrgang“: die Zahl, ihr Zusatz, ihre Schriftfarbe."""

    jahrgang: int
    zusatz: str = ""
    farbe: str = ""


@dataclass(frozen=True)
class Markierung:
    """Wie ein Buch in der Bücherliste eines Fachs aussieht.

    ``ganz`` färbt die ganze Zeile, ``jahrgang`` und ``leihbar`` nur ihre
    Zelle; eine Zelle trägt die Farben der Zeile und ihre eigenen. Der Strich
    vorn hat jede Farbe, die irgendwo vorkommt.
    """

    ganz: frozenset[str] = frozenset()
    jahrgang: frozenset[str] = frozenset()
    leihbar: frozenset[str] = frozenset()
    jahrgaenge: tuple[Jahrgangswert, ...] = field(default_factory=tuple)

    @property
    def strich(self) -> tuple[str, ...]:
        return geordnet(self.ganz, self.jahrgang, self.leihbar)

    def zelle(self, art: str = "", *zusaetzlich: str) -> str:
        """Die CSS-Klasse einer Zelle: ``band-…`` aus den Farben der Zeile, der
        Zelle ``art`` (``jahrgang``/``leihbar``) und ``zusaetzlich`` - leer ohne Farbe."""
        eigene = {"jahrgang": self.jahrgang, "leihbar": self.leihbar}.get(art, frozenset())
        farben = geordnet(self.ganz, eigene, [farbe for farbe in zusaetzlich if farbe])
        return "band-" + "-".join(farben) if farben else ""

    def strich_klasse(self, *zusaetzlich: str) -> str:
        """Die CSS-Klasse des Strichs vorn: ``strich-…`` - leer ohne Farbe."""
        farben = geordnet(self.strich, [farbe for farbe in zusaetzlich if farbe])
        return "strich-" + "-".join(farben) if farben else ""


def _jahr(angabe: str) -> int | None:
    try:
        return schuljahr_zahl(angabe)
    except UngueltigesSchuljahr:
        return None


def _wechsel(zeilen: Iterable[Planungszeile]) -> set[tuple[int, object]]:
    """Die Zeilen eines Fachs, die zu einem Wechsel von „leihbar“ gehören.

    Als (Jahrgang, Einführung) - beide Hälften: die, die mit dem Jahr vor der
    Einführung endet, und die, die dann mit dem anderen Häkchen beginnt.
    """
    je_jahrgang: dict[int, list[Planungszeile]] = {}
    for zeile in zeilen:
        je_jahrgang.setdefault(zeile.jahrgang, []).append(zeile)
    teile: set[tuple[int, object]] = set()
    for eigene in je_jahrgang.values():
        for spaeter in eigene:
            beginn = spaeter.beginn
            if beginn is None:
                continue
            for frueher in eigene:
                if frueher.ende == beginn - 1 and frueher.leihbar != spaeter.leihbar:
                    teile.add((frueher.jahrgang, frueher.eingefuehrt_ab))
                    teile.add((spaeter.jahrgang, spaeter.eingefuehrt_ab))
    return teile


def _zeilen_im_fach(stand: Buchplanung, isbn: str, fach: str) -> list[Planungszeile]:
    return [z for z in stand.planung if (z.isbn, z.fach) == (isbn, fach)]


def gezeigte_jahrgaenge(stand: Buchplanung, buch: Buch, fach: str) -> tuple[Jahrgangswert, ...]:
    """Die Jahrgänge eines Buchs in der Liste eines Fachs, mit „(ab …)“/„(bis …)“.

    Gezeigt wird jeder Jahrgang, der in diesem Schuljahr gilt oder noch kommt,
    und jeder, der nach dem Vorjahr ausgemustert wurde - durchgestrichen. Was
    früher endete, gehört nicht mehr in die Liste. Die Schriftfarbe setzt
    :func:`markierung`.
    """
    jetzt = _jahr(stand.schuljahr)
    gezeigt: list[Jahrgangswert] = []
    for jahrgang in sorted({z.jahrgang for z in _zeilen_im_fach(stand, buch.isbn, fach)}):
        zeilen = stand.zeilen_des_paars(buch.isbn, fach, jahrgang)
        laufend = any(planungs_status(z, stand.schuljahr) != PLANUNG_AUSGEMUSTERT for z in zeilen)
        eben_weg = jetzt is not None and any(z.ende == jetzt - 1 for z in zeilen)
        if not (laufend or eben_weg):
            continue
        massgeblich = stand.massgebliche_zeile(buch.isbn, fach, jahrgang)
        gezeigt.append(Jahrgangswert(jahrgang, planungs_zusatz(massgeblich, stand.schuljahr)))
    return tuple(gezeigt)


def markierung(stand: Buchplanung, buch: Buch, fach: str) -> Markierung:
    """Die Farben eines Buchs in der Bücherliste eines Fachs (Regeln: Modulkopf)."""
    jetzt = _jahr(stand.schuljahr)
    jahrgaenge = gezeigte_jahrgaenge(stand, buch, fach)
    if jetzt is None:
        return Markierung(jahrgaenge=jahrgaenge)
    eigene = _zeilen_im_fach(stand, buch.isbn, fach)
    alle = [z for z in stand.planung if z.isbn == buch.isbn]
    wechsel = _wechsel(eigene)

    ganz_neu = bool(alle) and all(z.beginn is not None and z.beginn >= jetzt for z in alle)
    ganz_weg = bool(alle) and all(z.ende is not None for z in alle)

    ganz: set[str] = set()
    zelle: set[str] = set()
    leihbar: set[str] = set()
    schrift: dict[int, str] = {}
    for zeile in eigene:
        if (zeile.jahrgang, zeile.eingefuehrt_ab) in wechsel:
            if zeile.beginn is not None and zeile.beginn >= jetzt:
                leihbar.add(AENDERUNG)
            continue
        if zeile.beginn is not None and zeile.beginn >= jetzt:
            (ganz if ganz_neu else zelle).add(EINFUEHRUNG)
            if zeile.beginn == jetzt:
                schrift[zeile.jahrgang] = EINFUEHRUNG
        if zeile.ende is not None and zeile.ende >= jetzt - 1:
            (ganz if ganz_weg else zelle).add(AUSMUSTERUNG)
            if zeile.ende == jetzt - 1:
                schrift[zeile.jahrgang] = AUSMUSTERUNG
    return Markierung(
        ganz=frozenset(ganz), jahrgang=frozenset(zelle), leihbar=frozenset(leihbar),
        jahrgaenge=tuple(Jahrgangswert(j.jahrgang, j.zusatz, schrift.get(j.jahrgang, ""))
                         for j in jahrgaenge),
    )


def in_ausmusterungen(stand: Buchplanung, buch: Buch, fach: str) -> bool:
    """Steht das Buch unter „Ausmusterungen zu diesem Schuljahr“ des Fachs?

    Dort steht, was die Schule im Fach verliehen hat und nun aus den Regalen
    nimmt: jeder Jahrgang, in dem es leihbar war, ist spätestens nach dem
    Vorjahr ausgemustert - der letzte genau nach dem Vorjahr -, und im Fach
    wird es zu diesem oder einem späteren Schuljahr nicht wieder eingeführt.
    Läuft es als Kaufbuch in einem anderen Jahrgang weiter, steht es zusätzlich
    in der Liste darüber (Entscheidung 2026-10-30).
    """
    jetzt = _jahr(stand.schuljahr)
    if jetzt is None:
        return False
    eigene = _zeilen_im_fach(stand, buch.isbn, fach)
    leihbar = [z for z in eigene if z.leihbar]
    if not leihbar or any(z.ende is None or z.ende > jetzt - 1 for z in leihbar):
        return False
    if max(z.ende for z in leihbar if z.ende is not None) != jetzt - 1:
        return False
    return not any(z.beginn is not None and z.beginn >= jetzt for z in eigene)
