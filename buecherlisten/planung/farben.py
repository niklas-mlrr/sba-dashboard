"""Die Farben der Bücherlisten: die Planung in der Schrift, IServ als Markierung.

Entscheidung 2026-10-31 (ersetzt die vom 2026-10-30): Jede Liste zeigt beides,
die Planung und den Vergleich mit IServ, und jedes Mittel hat eine Bedeutung.

* **Schrift = Planung**, je Wert (Jahrgang, in Verlag/Jahrgang später auch
  Fach): blau eine Einführung zu diesem Schuljahr oder später, rot eine
  Ausmusterung nach dem Vorjahr oder später. Durchgestrichen ist ein Wert, der
  nach dem Vorjahr ausgemustert wurde - er gilt nicht mehr.
* **Markierung = IServ**, je Wert: blau, was in IServ noch fehlt, rot, was dort
  noch steht (der Wert ist dann durchgestrichen). Gelb (Titel, Verlag, Preise)
  setzt die Vorlage aus ``Buch.iserv``. IServ wird nur für das laufende
  Schuljahr verglichen: eine Einführung „ab 2027/2028“ hat keine Markierung.
* **Hintergrund** nur für Ganzes: die Zeile, wenn das Buch ganz neu ist (keine
  Zeile in irgendeinem Fach lief schon) oder es danach in keinem Fach und
  Jahrgang mehr gibt; eine Teilzeile, wenn das Buch als Leih- bzw. Kaufbuch
  ganz neu oder ganz weg ist.
* **„Leihbar“ hängt am Jahrgang.** Verglichen und gefärbt wird je Eintrag
  (Fach, Jahrgang, leihbar): ein Buch steht in einem Jahrgang als Leih- oder
  als Kaufbuch in der Liste, in zwei Teilzeilen. Ein Wechsel ist eine
  Ausmusterung in der einen und eine Einführung in der anderen Teilzeile; das
  Häkchen selbst wird nie gefärbt.
* **Der Strich vorn** zeigt den Schwerpunkt der Ansicht: in „Fach“ die Planung
  (:meth:`Markierung.strich`), in Verlag und Jahrgang später IServ.

Vorerst nutzt nur die Fach-Ansicht dieses Modell. ``im`` und ``nach`` von
:func:`markierung` sind für Verlag und Jahrgang vorbereitet: dort wird nach
Jahrgang gefiltert bzw. gar nicht, und die Wertspalte ist das Fach.

Ohne Netz, ohne Excel, ohne HTTP - wie der Rest von ``buecherlisten.planung``.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

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
from .vergleich import NUR_EXCEL, NUR_ISERV, Abweichung, Eintrag

AUSMUSTERUNG = "ausmusterung"
AENDERUNG = "aenderung"
EINFUEHRUNG = "einfuehrung"
REIHENFOLGE: tuple[str, ...] = (AUSMUSTERUNG, AENDERUNG, EINFUEHRUNG)

# Was IServ zu einem Wert sagt.
FEHLT = "fehlt"            # laut Datei dieses Schuljahr da, in IServ nicht
STEHT_NOCH = "steht_noch"  # in IServ da, laut Datei dieses Schuljahr nicht
# Die Farbe der Markierung dazu.
MARKIERUNG = {FEHLT: EINFUEHRUNG, STEHT_NOCH: AUSMUSTERUNG}

# Der Schwerpunkt einer Ansicht - er bestimmt den Strich vorn.
PLANUNG = "planung"
ISERV = "iserv"

JAHRGANG = "jahrgang"
FACH = "fach"


def geordnet(*mengen: Iterable[str]) -> tuple[str, ...]:
    """Die Farben aus allen ``mengen``, in der Reihenfolge rot, gelb, blau."""
    alle = {farbe for menge in mengen for farbe in menge}
    return tuple(farbe for farbe in REIHENFOLGE if farbe in alle)


@dataclass(frozen=True)
class Wert:
    """Ein Wert in einer Spalte (Jahrgang oder Fach) einer Teilzeile.

    ``plan`` ist die Farbe der Schrift, ``iserv`` was IServ dazu sagt (die
    Markierung). ``hinweis`` steht als Tooltip daran.
    """

    text: str
    zusatz: str = ""
    plan: str = ""
    weg: bool = False
    iserv: str = ""
    hinweis: str = ""

    @property
    def durch(self) -> bool:
        """Durchgestrichen: nach dem Vorjahr ausgemustert oder nur noch in IServ."""
        return self.weg or (self.iserv == STEHT_NOCH and not self.plan)

    @property
    def markierung(self) -> str:
        return MARKIERUNG.get(self.iserv, "")


@dataclass(frozen=True)
class Teilzeile:
    """Das Buch als Leih- oder als Kaufbuch: das Häkchen und seine Werte.

    ``ganz`` hinterlegt die Teilzeile: das Buch ist so ganz neu
    (``einfuehrung``) oder ganz weg (``ausmusterung``).
    """

    leihbar: bool
    werte: tuple[Wert, ...]
    ganz: str = ""


@dataclass(frozen=True)
class Markierung:
    """Wie ein Buch in einer Zeile einer Bücherliste aussieht.

    ``ganz`` hinterlegt die Zeile (Planung). ``iserv`` sagt, ob das Buch als
    Ganzes in IServ fehlt oder nur dort steht; ``felder_anders``, ob IServ
    Titel, Verlag oder Preise anders nennt - beides nur für den Strich einer
    Ansicht mit Schwerpunkt IServ. ``eintraege`` sind alle gezeigten Einträge.
    """

    teilzeilen: tuple[Teilzeile, ...] = ()
    ganz: str = ""
    iserv: str = ""
    felder_anders: bool = False
    eintraege: tuple[Eintrag, ...] = ()

    @property
    def werte(self) -> tuple[Wert, ...]:
        return tuple(wert for teil in self.teilzeilen for wert in teil.werte)

    @property
    def jahrgaenge(self) -> tuple[int, ...]:
        return tuple(sorted({jahrgang for _, jahrgang, _ in self.eintraege}))

    @property
    def leihbar(self) -> bool:
        return any(teil.leihbar for teil in self.teilzeilen)

    @property
    def leihbar_teilweise(self) -> bool:
        return len({teil.leihbar for teil in self.teilzeilen}) > 1

    def strich(self, schwerpunkt: str = PLANUNG) -> tuple[str, ...]:
        """Die Farben des Strichs vorn - die des Schwerpunkts der Ansicht."""
        if schwerpunkt == ISERV:
            return geordnet([MARKIERUNG.get(self.iserv, "")],
                            [wert.markierung for wert in self.werte],
                            [AENDERUNG] if self.felder_anders else [])
        return geordnet([self.ganz], [teil.ganz for teil in self.teilzeilen],
                        [wert.plan for wert in self.werte])

    def strich_klasse(self, schwerpunkt: str = PLANUNG, *zusaetzlich: str) -> str:
        """Die CSS-Klasse des Strichs vorn: ``strich-…`` - leer ohne Farbe."""
        farben = geordnet(self.strich(schwerpunkt), [f for f in zusaetzlich if f])
        return "strich-" + "-".join(farben) if farben else ""


def _jahr(angabe: str) -> int | None:
    try:
        return schuljahr_zahl(angabe)
    except UngueltigesSchuljahr:
        return None


@dataclass(frozen=True)
class _Plan:
    """Die Planung eines Eintrags: Farbe, ob er nach dem Vorjahr endete, Zusatz."""

    farbe: str
    weg: bool
    zusatz: str


def _planung_je_eintrag(stand: Buchplanung, buch: Buch, jetzt: int) -> dict[Eintrag, _Plan]:
    """Jeder Eintrag, der in diesem Schuljahr gilt, noch kommt oder nach dem
    Vorjahr endete - mit seiner Planung. Was früher endete, gehört nicht mehr
    in die Liste."""
    je_eintrag: dict[Eintrag, list[Planungszeile]] = {}
    for zeile in stand.planung:
        if zeile.isbn == buch.isbn:
            je_eintrag.setdefault((zeile.fach, zeile.jahrgang, zeile.leihbar), []).append(zeile)
    ergebnis: dict[Eintrag, _Plan] = {}
    for eintrag, zeilen in je_eintrag.items():
        laufend = any(planungs_status(z, stand.schuljahr) != PLANUNG_AUSGEMUSTERT for z in zeilen)
        eben_weg = any(z.ende == jetzt - 1 for z in zeilen)
        if not (laufend or eben_weg):
            continue
        neu = any(z.beginn is not None and z.beginn >= jetzt for z in zeilen)
        geht = any(z.ende is not None and z.ende >= jetzt - 1 for z in zeilen)
        fach, jahrgang, leihbar = eintrag
        massgeblich = stand.massgebliche_zeile(buch.isbn, fach, jahrgang, leihbar=leihbar)
        ergebnis[eintrag] = _Plan(
            # Wird eine Zeile im selben Jahr eingeführt und ausgemustert, gilt Rot.
            farbe=AUSMUSTERUNG if geht else EINFUEHRUNG if neu else "",
            weg=not laufend,
            zusatz=planungs_zusatz(massgeblich, stand.schuljahr),
        )
    return ergebnis


def _hinweis(plan: _Plan | None, iserv: str, leihbar: bool, stand: Buchplanung) -> str:
    als = "als Leihbuch" if leihbar else "als Kaufbuch"
    teile = []
    if plan is not None and plan.farbe == EINFUEHRUNG:
        teile.append(f"Planung: {als} eingeführt "
                     + (plan.zusatz if plan.zusatz.startswith("ab ") else f"zu {stand.schuljahr}"))
    elif plan is not None and plan.farbe == AUSMUSTERUNG:
        teile.append(f"Planung: {als} ausgemustert nach {stand.vorjahr}" if plan.weg
                     else f"Planung: {als} läuft aus ({plan.zusatz})" if plan.zusatz
                     else f"Planung: {als} läuft aus")
    if iserv == FEHLT:
        teile.append(f"IServ: {als} noch nicht eingetragen")
    elif iserv == STEHT_NOCH:
        teile.append(f"IServ: {als} noch eingetragen")
    return " · ".join(teile)


def _zusammen(werte: list[Wert]) -> Wert:
    """Ein Wert aus mehreren Einträgen (Verlagsansicht: ein Jahrgang über alle Fächer)."""
    if len(werte) == 1:
        return werte[0]
    plan = geordnet([w.plan for w in werte])
    iserv = [w.iserv for w in werte if w.iserv]
    zusaetze = {w.zusatz for w in werte}
    return Wert(
        text=werte[0].text,
        zusatz=zusaetze.pop() if len(zusaetze) == 1 else "",
        plan=plan[0] if plan else "",
        weg=all(w.weg for w in werte),
        iserv=STEHT_NOCH if STEHT_NOCH in iserv else iserv[0] if iserv else "",
        hinweis=" · ".join(dict.fromkeys(w.hinweis for w in werte if w.hinweis)),
    )


def _ganz(zeilen: list[Planungszeile], jetzt: int) -> str:
    """``einfuehrung``, wenn keine der Zeilen schon lief, ``ausmusterung``,
    wenn alle enden und eine davon nach dem Vorjahr oder später."""
    if not zeilen:
        return ""
    if all(z.beginn is not None and z.beginn >= jetzt for z in zeilen):
        return EINFUEHRUNG
    if all(z.ende is not None for z in zeilen) \
            and any(z.ende is not None and z.ende >= jetzt - 1 for z in zeilen):
        return AUSMUSTERUNG
    return ""


def markierung(stand: Buchplanung, buch: Buch, abweichung: Abweichung | None = None, *,
               im: Callable[[Eintrag], bool], nach: str = JAHRGANG) -> Markierung:
    """Die Farben eines Buchs in einer Zeile (Regeln: Modulkopf).

    ``im`` wählt die Einträge der Zeile (Fach-Ansicht: die des Fachs), ``nach``
    die Wertspalte: ``jahrgang`` oder ``fach``. ``abweichung`` ist der
    Vergleich mit IServ; ohne ihn bleibt jede Markierung weg.
    """
    jetzt = _jahr(stand.schuljahr)
    planung = _planung_je_eintrag(stand, buch, jetzt) if jetzt is not None else {}
    fehlt = set(abweichung.eintraege_fehlen) if abweichung else set()
    nur_iserv = set(abweichung.eintraege_nur_iserv) if abweichung else set()
    eintraege = sorted((e for e in set(planung) | nur_iserv if im(e)),
                       key=lambda e: (e[0].casefold(), e[1], not e[2]))

    alle = [z for z in stand.planung if z.isbn == buch.isbn]
    ganz = _ganz(alle, jetzt) if jetzt is not None else ""
    beide = len({z.leihbar for z in alle}) > 1

    teilzeilen = []
    for leihbar in (True, False):
        eigene = [e for e in eintraege if e[2] == leihbar]
        if not eigene:
            continue
        je_schluessel: dict[tuple[str, int], list[Wert]] = {}
        for eintrag in eigene:
            fach, jahrgang, _ = eintrag
            plan = planung.get(eintrag)
            iserv = FEHLT if eintrag in fehlt else STEHT_NOCH if eintrag in nur_iserv else ""
            schluessel = (fach.casefold(), 0) if nach == FACH else ("", jahrgang)
            je_schluessel.setdefault(schluessel, []).append(Wert(
                text=fach if nach == FACH else str(jahrgang),
                zusatz=plan.zusatz if plan else "",
                plan=plan.farbe if plan else "",
                weg=plan.weg if plan else False,
                iserv=iserv,
                hinweis=_hinweis(plan, iserv, leihbar, stand),
            ))
        werte = tuple(_zusammen(je_schluessel[k]) for k in sorted(je_schluessel))
        teil_ganz = ""
        if beide and not ganz and jetzt is not None:
            teil_ganz = _ganz([z for z in alle if z.leihbar == leihbar], jetzt)
        teilzeilen.append(Teilzeile(leihbar=leihbar, werte=werte, ganz=teil_ganz))

    art = abweichung.art if abweichung else ""
    return Markierung(
        teilzeilen=tuple(teilzeilen), ganz=ganz,
        iserv=FEHLT if art == NUR_EXCEL else STEHT_NOCH if art == NUR_ISERV else "",
        felder_anders=bool(abweichung and any(f != "leihbar" for f, _ in abweichung.felder)),
        eintraege=tuple(eintraege),
    )


def im_fach(fach: str) -> Callable[[Eintrag], bool]:
    """Die Einträge eines Fachs - der Filter der Fach-Ansicht."""
    return lambda eintrag: eintrag[0] == fach


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
    eigene = [z for z in stand.planung if (z.isbn, z.fach) == (buch.isbn, fach)]
    leihbar = [z for z in eigene if z.leihbar]
    if not leihbar or any(z.ende is None or z.ende > jetzt - 1 for z in leihbar):
        return False
    if max(z.ende for z in leihbar if z.ende is not None) != jetzt - 1:
        return False
    return not any(z.beginn is not None and z.beginn >= jetzt for z in eigene)
