"""Die Farben der Bücherlisten: die Planung in der Schrift, IServ als Markierung.

Entscheidung 2026-10-31 (ersetzt die vom 2026-10-30, am selben Tag
nachgeschärft): Jede Liste zeigt beides, die Planung und den Vergleich mit
IServ, und jedes Mittel hat eine Bedeutung. „Dieses Schuljahr“ ist das
ausgewählte, vorerst immer das laufende (``stand.schuljahr``).

* **Schrift = Planung**, je Wert (Jahrgang, in Verlag/Jahrgang später auch
  Fach): blau eine Einführung zu diesem Schuljahr oder später, rot eine
  Ausmusterung nach dem Vorjahr oder später. Durchgestrichen ist nur ein
  Wert, der nach dem Vorjahr ausgemustert wurde - er gilt nicht mehr.
* **Markierung = IServ**, je Wert (helle Hinterlegung, farbiger Strich
  darunter): blau, was in IServ noch fehlt, rot, was dort noch steht. Ein
  Jahrgang fehlt, wenn er in der Bücherliste fehlt (je Eintrag, mit
  „leihbar“) oder die Buchreihe ihm nicht zugewiesen ist; zu viele Jahrgänge
  an der Buchreihe schaden nicht. Verglichen wird nur, was in diesem
  Schuljahr gilt: eine Einführung „ab 2027/2028“ und eine Ausmusterung nach
  diesem Schuljahr oder später sind kein Grund für eine Markierung. Steht die
  ISBN nur auf einer Seite, ist die ganze Zeile markiert
  (:attr:`Markierung.zeile`). Gelb (Titel, Verlag, Preise) setzt die Vorlage
  aus ``Buch.iserv``.
* **Hintergrund** nur für Ganzes, über alle Fächer und nur über die gezeigten
  Einträge: die Zeile, wenn jeder Jahrgang des Buchs blau bzw. rot ist; eine
  Teilzeile, wenn jeder Jahrgang mit diesem „leihbar“ es ist.
* **„Leihbar“ hängt am Jahrgang.** Verglichen und gefärbt wird je Eintrag
  (Fach, Jahrgang, leihbar): ein Buch steht in einem Jahrgang als Leih- oder
  als Kaufbuch in der Liste, in zwei Teilzeilen. Ein Wechsel ist eine
  Ausmusterung in der einen und eine Einführung in der anderen Teilzeile; das
  Häkchen selbst wird nie gefärbt.
* **Der Strich vorn** zeigt den Schwerpunkt der Ansicht. In „Fach“ die
  Planung: ein gleich hoher Abschnitt je farbigem Wert, sortiert nach
  Jahrgang, Einführungs- bzw. Ausmusterungsjahr, rot vor blau
  (:attr:`Markierung.strich_planung`). Haben zwei Teilzeilen je genau eine,
  verschiedene Farbe, teilt er sich an ihrer Grenze. Weicht ein Feld ab
  (gelb), steht ein zweiter, gelber Strich daneben. In Verlag und Jahrgang
  später IServ (``strich("iserv")``).

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
    wirkt_im_schuljahr,
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
    Markierung). ``hinweis`` steht als Tooltip daran. ``jahrgang`` und
    ``jahr`` (Einführungs- bzw. Ausmusterungsjahr der Schriftfarbe) ordnen
    den Strich vorn.
    """

    text: str
    zusatz: str = ""
    plan: str = ""
    weg: bool = False
    iserv: str = ""
    hinweis: str = ""
    jahrgang: int = 0
    jahr: int = 0

    @property
    def durch(self) -> bool:
        """Durchgestrichen: nach dem Vorjahr ausgemustert - sonst nichts."""
        return self.weg

    @property
    def markierung(self) -> str:
        return MARKIERUNG.get(self.iserv, "")


@dataclass(frozen=True)
class Teilzeile:
    """Das Buch als Leih- oder als Kaufbuch: das Häkchen und seine Werte.

    ``ganz`` hinterlegt die Teilzeile: jeder Jahrgang des Buchs mit diesem
    „leihbar“ ist neu (``einfuehrung``) bzw. geht (``ausmusterung``).
    """

    leihbar: bool
    werte: tuple[Wert, ...]
    ganz: str = ""


def _strichfolge(wert: Wert) -> tuple[int, int, int]:
    return (wert.jahrgang, wert.jahr, 0 if wert.plan == AUSMUSTERUNG else 1)


def _prozent(zahl: float) -> str:
    return f"{round(zahl, 3):g}%"


@dataclass(frozen=True)
class Markierung:
    """Wie ein Buch in einer Zeile einer Bücherliste aussieht.

    ``ganz`` hinterlegt die Zeile (Planung). ``iserv`` sagt, ob das Buch als
    Ganzes in IServ fehlt oder nur dort steht - dann ist jedes Feld der Zeile
    markiert (:attr:`zeile`). ``felder_anders`` sagt, ob IServ Titel, Verlag
    oder Preise anders nennt (der gelbe Strich). ``eintraege`` sind alle
    gezeigten Einträge.
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

    @property
    def zeile(self) -> str:
        """Die Markierung jedes Felds der Zeile: blau, wenn die ISBN in IServ
        fehlt, rot, wenn es sie nur dort gibt - sonst leer."""
        return MARKIERUNG.get(self.iserv, "")

    @property
    def strich_planung(self) -> tuple[str, ...]:
        """Die Abschnitte des Strichs vorn, von oben: je farbigem Wert seine
        Schriftfarbe, nach Jahrgang, Jahr der Einführung bzw. Ausmusterung und
        rot vor blau."""
        return tuple(wert.plan for wert in sorted(
            (wert for wert in self.werte if wert.plan), key=_strichfolge))

    @property
    def strich_teile(self) -> tuple[str, str] | None:
        """Die Farben oben und unten, wenn zwei Teilzeilen je genau eine,
        verschiedene Farbe haben: dann teilt sich der Strich an ihrer Grenze."""
        if len(self.teilzeilen) != 2:
            return None
        oben, unten = ({wert.plan for wert in teil.werte if wert.plan}
                       for teil in self.teilzeilen)
        if len(oben) == 1 and len(unten) == 1 and oben != unten:
            return next(iter(oben)), next(iter(unten))
        return None

    def strich(self, schwerpunkt: str = PLANUNG) -> tuple[str, ...]:
        """Die Farben des Strichs vorn - die des Schwerpunkts der Ansicht."""
        if schwerpunkt == ISERV:
            return geordnet([MARKIERUNG.get(self.iserv, "")],
                            [wert.markierung for wert in self.werte],
                            [AENDERUNG] if self.felder_anders else [])
        return self.strich_planung

    @property
    def strich_klassen(self) -> tuple[str, ...]:
        """Die CSS-Klassen der Striche vorn: ``strich`` (Planung, Farben in
        :meth:`strich_stil`) und ``strich-gelb`` (ein Feld weicht ab)."""
        return (("strich",) if self.strich_planung else ()) \
            + (("strich-gelb",) if self.felder_anders else ())

    def strich_stil(self) -> str:
        """Der Hintergrund des Strichs vorn (Planung) als CSS-Wert - leer ohne Farbe.

        Die Grenze zweier Teilzeilen steht in ``--teilung``; static/buchplanung.js
        setzt sie auf die wirkliche Höhe der oberen Teilzeile.
        """
        teile = self.strich_teile
        if teile is not None:
            oben, unten = teile
            return (f"linear-gradient(var(--{oben}-strich) 0 var(--teilung, 50%), "
                    f"var(--{unten}-strich) var(--teilung, 50%) 100%)")
        farben = self.strich_planung
        if not farben:
            return ""
        if len(set(farben)) == 1:
            return f"var(--{farben[0]}-strich)"
        anzahl = len(farben)
        return "linear-gradient(" + ", ".join(
            f"var(--{farbe}-strich) {_prozent(100 * i / anzahl)} {_prozent(100 * (i + 1) / anzahl)}"
            for i, farbe in enumerate(farben)) + ")"


def _jahr(angabe: str) -> int | None:
    try:
        return schuljahr_zahl(angabe)
    except UngueltigesSchuljahr:
        return None


@dataclass(frozen=True)
class _Plan:
    """Die Planung eines Eintrags: Farbe, ob er nach dem Vorjahr endete, Zusatz,
    das Jahr der Einführung bzw. Ausmusterung und ob er dieses Schuljahr gilt."""

    farbe: str
    weg: bool
    zusatz: str
    jahr: int = 0
    wirkt: bool = False


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
        beginne = [z.beginn for z in zeilen if z.beginn is not None and z.beginn >= jetzt]
        enden = [z.ende for z in zeilen if z.ende is not None and z.ende >= jetzt - 1]
        fach, jahrgang, leihbar = eintrag
        massgeblich = stand.massgebliche_zeile(buch.isbn, fach, jahrgang, leihbar=leihbar)
        # Wird eine Zeile im selben Jahr eingeführt und ausgemustert, gilt Rot.
        farbe = AUSMUSTERUNG if enden else EINFUEHRUNG if beginne else ""
        ergebnis[eintrag] = _Plan(
            farbe=farbe,
            weg=not laufend,
            zusatz=planungs_zusatz(massgeblich, stand.schuljahr),
            jahr=min(enden) if enden else min(beginne) if beginne else 0,
            wirkt=any(wirkt_im_schuljahr(z, stand.schuljahr) for z in zeilen),
        )
    return ergebnis


def _hinweis(plan: _Plan | None, liste: str, reihe: bool, jahrgang: int, leihbar: bool,
             stand: Buchplanung) -> str:
    als = "als Leihbuch" if leihbar else "als Kaufbuch"
    teile = []
    if plan is not None and plan.farbe == EINFUEHRUNG:
        teile.append(f"Planung: {als} eingeführt "
                     + (plan.zusatz if plan.zusatz.startswith("ab ") else f"zu {stand.schuljahr}"))
    elif plan is not None and plan.farbe == AUSMUSTERUNG:
        teile.append(f"Planung: {als} ausgemustert nach {stand.vorjahr}" if plan.weg
                     else f"Planung: {als} läuft aus ({plan.zusatz})" if plan.zusatz
                     else f"Planung: {als} läuft aus")
    if liste == FEHLT:
        teile.append(f"IServ-Bücherliste: {als} noch nicht eingetragen")
    elif liste == STEHT_NOCH:
        teile.append(f"IServ-Bücherliste: {als} noch eingetragen")
    if reihe:
        teile.append(f"IServ-Buchreihe: Jahrgang {jahrgang} noch nicht zugewiesen")
    return " · ".join(teile)


def _zusammen(werte: list[Wert]) -> Wert:
    """Ein Wert aus mehreren Einträgen (Verlagsansicht: ein Jahrgang über alle Fächer)."""
    if len(werte) == 1:
        return werte[0]
    plan = geordnet([w.plan for w in werte])
    iserv = [w.iserv for w in werte if w.iserv]
    zusaetze = {w.zusatz for w in werte}
    jahre = [w.jahr for w in werte if plan and w.plan == plan[0]]
    return Wert(
        text=werte[0].text,
        zusatz=zusaetze.pop() if len(zusaetze) == 1 else "",
        plan=plan[0] if plan else "",
        weg=all(w.weg for w in werte),
        iserv=STEHT_NOCH if STEHT_NOCH in iserv else iserv[0] if iserv else "",
        hinweis=" · ".join(dict.fromkeys(w.hinweis for w in werte if w.hinweis)),
        jahrgang=werte[0].jahrgang,
        jahr=min(jahre) if jahre else 0,
    )


def _ganz(plaene: Iterable[_Plan]) -> str:
    """Die Farbe, die jeder der ``plaene`` hat - leer, wenn sie sich
    unterscheiden, einer keine hat oder es keine gibt."""
    farben = {plan.farbe for plan in plaene}
    return farben.pop() if len(farben) == 1 else ""


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
    buchreihe = set(abweichung.buchreihe_fehlt) if abweichung else set()
    eintraege = sorted((e for e in set(planung) | nur_iserv if im(e)),
                       key=lambda e: (e[0].casefold(), e[1], not e[2]))

    # Der Hintergrund schaut auf alle Fächer, aber nur auf die gezeigten Einträge.
    ganz = _ganz(planung.values())
    beide = len({leihbar for _, _, leihbar in planung}) > 1

    teilzeilen = []
    for leihbar in (True, False):
        eigene = [e for e in eintraege if e[2] == leihbar]
        if not eigene:
            continue
        je_schluessel: dict[tuple[str, int], list[Wert]] = {}
        for eintrag in eigene:
            fach, jahrgang, _ = eintrag
            plan = planung.get(eintrag)
            liste = FEHLT if eintrag in fehlt else STEHT_NOCH if eintrag in nur_iserv else ""
            reihe = plan is not None and plan.wirkt and jahrgang in buchreihe
            schluessel = (fach.casefold(), 0) if nach == FACH else ("", jahrgang)
            je_schluessel.setdefault(schluessel, []).append(Wert(
                text=fach if nach == FACH else str(jahrgang),
                zusatz=plan.zusatz if plan else "",
                plan=plan.farbe if plan else "",
                weg=plan.weg if plan else False,
                iserv=liste or (FEHLT if reihe else ""),
                hinweis=_hinweis(plan, liste, reihe, jahrgang, leihbar, stand),
                jahrgang=jahrgang,
                jahr=plan.jahr if plan else 0,
            ))
        werte = tuple(_zusammen(je_schluessel[k]) for k in sorted(je_schluessel))
        teil_ganz = ""
        if beide and not ganz:
            teil_ganz = _ganz(p for e, p in planung.items() if e[2] == leihbar)
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
