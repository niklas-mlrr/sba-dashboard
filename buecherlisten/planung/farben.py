"""Die Farben der Bücherlisten: die Planung in der Schrift, IServ als Markierung.

Entscheidung 2026-10-31 (ersetzt die vom 2026-10-30, am selben Tag
nachgeschärft): Jede Liste zeigt beides, die Planung und den Vergleich mit
IServ, und jedes Mittel hat eine Bedeutung. „Dieses Schuljahr“ ist das
ausgewählte, vorerst immer das laufende (``stand.schuljahr``).

* **Schrift = Planung**, je Wert (Jahrgang, in Verlag/Jahrgang später auch
  Fach): blau eine Einführung zu diesem Schuljahr oder später, rot eine
  Ausmusterung nach dem Vorjahr oder später. Es färbt das zeitlich nächste
  Ereignis, bis IServ es umgesetzt hat (Entscheidung 2026-11-05): eine
  Einführung zu diesem Schuljahr mit Ausmusterung bleibt blau, bis IServ den
  Wert führt (Bücherliste und Buchreihe ohne Differenz), dann wird er rot;
  eine spätere Wiedereinführung färbt erst, wenn die Ausmusterung davor in
  IServ durch ist. Durchgestrichen ist nur ein Wert, der nach dem Vorjahr
  ausgemustert wurde - er gilt nicht mehr.
* **Markierung = IServ**, je Wert (helle Hinterlegung, farbiger Strich
  darunter): blau, was in IServ noch fehlt, rot, was dort noch steht. Ein
  Jahrgang fehlt, wenn er in der Bücherliste fehlt (je Eintrag, mit
  „leihbar“; Strich unten) oder die Buchreihe ihm nicht zugewiesen ist
  (Strich oben, Entscheidung 2026-11-04); zu viele Jahrgänge an der Buchreihe
  schaden nicht. Rot hat den Strich unten immer und oben dazu, wenn die
  Buchreihe ganz geht: kein Fach führt sie dieses Schuljahr, und keine
  Einführung ist offen oder genehmigt (Entscheidung 2026-11-05). Verglichen
  wird nur, was in diesem Schuljahr gilt: eine
  Einführung „ab 2027/2028“ und eine Ausmusterung nach diesem Schuljahr oder
  später sind kein Grund für eine Markierung. Markiert wird gegen den
  entschiedenen Stand (:func:`entschiedener_stand`, Entscheidung 2026-11-05):
  solange die Ausmusterung nach dem Vorjahr nicht genehmigt ist, läuft das
  Buch noch; solange die Einführung zu diesem Schuljahr nicht genehmigt ist,
  ist es noch nicht eingeführt. Steht die ISBN nur in IServ, ist
  die ganze Zeile rot markiert (:attr:`Markierung.zeile`); nur in der Datei
  blau nur dann, wenn die Buchreihe im Inventar fehlt - sonst zeigen die
  Jahrgänge, was fehlt. Gelb (Titel, Verlag, Preise) setzt die Vorlage aus
  ``Buch.iserv``.
* **Tooltips** je Jahrgang, eine Zeile je Aussage: erst was die Schrift sagt
  (:func:`_schrift_hinweis`), dann was in IServ zu tun ist
  (:func:`_iserv_hinweise`). Die Texte stehen im README des Pakets.
* **Hintergrund** nur für Ganzes, über alle Fächer und nur über die gezeigten
  Einträge: die Zeile, wenn jeder Jahrgang des Buchs blau bzw. rot ist; eine
  Teilzeile, wenn jeder Jahrgang mit diesem „leihbar“ es ist. Rot nur, wenn
  zu keiner Zahl danach im selben Fach und Jahrgang eine Einführung geplant ist
  (offen oder genehmigt) - für die Zeile jede, für die Teilzeile nur eine mit
  ihrem „leihbar“.
* **„Leihbar“ hängt am Jahrgang.** Verglichen und gefärbt wird je Eintrag
  (Fach, Jahrgang, leihbar): ein Buch steht in einem Jahrgang als Leih- oder
  als Kaufbuch in der Liste, in zwei Teilzeilen. Ein Wechsel ist eine
  Ausmusterung in der einen und eine Einführung in der anderen Teilzeile; das
  Häkchen selbst wird nie gefärbt.
* **Der Strich vorn** zeigt den Schwerpunkt der Ansicht. In „Fach“ die
  Planung: ein gleich hoher Abschnitt je vorkommender Farbe (blau, grau, rot),
  in der Reihenfolge, in der sie beim Lesen von Jahrgangszahl und Jahreszahlen
  auftauchen (:attr:`Markierung.strich_planung`). Grau ist ein abgelehnter
  Antrag. Weicht ein Feld ab (gelb), steht ein zweiter, gelber Strich daneben.
  In Verlag und Jahrgang später IServ (``strich("iserv")``).
* **Abgelehnte Anträge** gelten nicht: eine abgelehnte Ausmusterung lässt das
  Buch bleiben, eine abgelehnte Einführung zählt für Farbe und Vergleich nicht.
  Ihre Jahreszahl bleibt im Zusatz (grau, mit Kasten); gibt es das Buch nur
  wegen abgelehnter Einführungen nicht, ist die Zeile grau hinterlegt.

Vorerst nutzt nur die Fach-Ansicht dieses Modell. ``im`` und ``nach`` von
:func:`markierung` sind für Verlag und Jahrgang vorbereitet: dort wird nach
Jahrgang gefiltert bzw. gar nicht, und die Wertspalte ist das Fach.

Ohne Netz, ohne Excel, ohne HTTP - wie der Rest von ``buecherlisten.planung``.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

from .modelle import (
    ANTRAG_ABGELEHNT,
    ANTRAG_OFFEN,
    ART_AUSMUSTERUNG,
    ART_EINFUEHRUNG,
    PLANUNG_AUSGEMUSTERT,
    Buch,
    Buchplanung,
    Planungszeile,
    UngueltigesSchuljahr,
    planungs_status,
    schuljahr_zahl,
    wirkt_im_schuljahr,
    zeitfolge,
)
from .vergleich import NUR_EXCEL, NUR_ISERV, Abweichung, Eintrag, aktive_eintraege
from .zusatz import Zusatzzeile, zusatz_je_zeile

AUSMUSTERUNG = "ausmusterung"
AENDERUNG = "aenderung"
EINFUEHRUNG = "einfuehrung"
# Ein abgelehnter Antrag: die Jahreszahl ist grau, der Strich vorn auch, und
# hängt das Buch nur an abgelehnten Einführungen, ist die Zeile grau hinterlegt.
GRAU = "grau"
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
    ``jahr`` (Einführungs- bzw. Ausmusterungsjahr der Schriftfarbe) benennen
    den Wert.

    ``zusaetze`` ist hinter dem Jahrgang das Ergebnis je Planungszeile
    (:mod:`~buecherlisten.planung.zusatz`); ``grau``: das Buch gibt es hier
    nur wegen abgelehnter Einführungen, also gar nicht - die Zahl ist grau.

    Fehlt der Wert in IServ (``iserv`` = ``fehlt``), sagen ``reihe_fehlt``
    und ``liste_fehlt``, wo (Entscheidung 2026-11-04): der Buchreihe ist der
    Jahrgang nicht zugewiesen (Strich oben) bzw. die Buchreihe steht nicht in
    der Bücherliste des Jahrgangs (Strich unten). Steht er dort noch (rot),
    ist der Strich unten immer da, ``reihe_weg`` setzt den oben dazu: die
    Buchreihe geht ganz, der Jahrgang ist auch an ihr zu entfernen
    (Entscheidung 2026-11-05). ``hinweis`` hat je Aussage eine Zeile.
    """

    text: str
    zusaetze: tuple[Zusatzzeile, ...] = ()
    plan: str = ""
    weg: bool = False
    iserv: str = ""
    hinweis: str = ""
    jahrgang: int = 0
    jahr: int = 0
    grau: bool = False
    reihe_fehlt: bool = False
    liste_fehlt: bool = False
    reihe_weg: bool = False

    @property
    def striche(self) -> str:
        """Die Striche der Markierung für die Vorlage: ``oben-unten``, ``oben``
        oder leer (nur unten, wie jede andere Markierung). Blau nach
        ``reihe_fehlt``/``liste_fehlt``, rot nach ``reihe_weg``."""
        if self.markierung == AUSMUSTERUNG:
            return "oben-unten" if self.reihe_weg else ""
        if self.markierung != EINFUEHRUNG or not self.reihe_fehlt:
            return ""
        return "oben-unten" if self.liste_fehlt else "oben"

    @property
    def zusatz(self) -> str:
        """Die Ergebnisse der Planungszeilen als Text, mit „, “ getrennt."""
        return ", ".join(zeile.text for zeile in self.zusaetze)

    @property
    def durch(self) -> bool:
        """Durchgestrichen: nach dem Vorjahr ausgemustert - sonst nichts."""
        return self.weg

    @property
    def markierung(self) -> str:
        return MARKIERUNG.get(self.iserv, "")

    @property
    def lesefarben(self) -> tuple[str, ...]:
        """Die Schriftfarben des Werts in Lesefolge, jede einmal: erst die
        Jahrgangszahl (grau, wenn es das Buch hier nur wegen abgelehnter
        Einführungen gäbe), dann jede abgelehnte Jahreszahl des Zusatzes (grau)."""
        farben = [self.plan] if self.plan else [GRAU] if self.grau else []
        farben += [GRAU for zeile in self.zusaetze for teil in zeile.teile
                   if teil.antrag == ANTRAG_ABGELEHNT]
        return tuple(dict.fromkeys(farben))


@dataclass(frozen=True)
class Teilzeile:
    """Das Buch als Leih- oder als Kaufbuch: das Häkchen und seine Werte.

    ``ganz`` hinterlegt die Teilzeile: jeder Jahrgang des Buchs mit diesem
    „leihbar“ ist neu (``einfuehrung``) bzw. geht (``ausmusterung``).
    """

    leihbar: bool
    werte: tuple[Wert, ...]
    ganz: str = ""

    @property
    def jahrgaenge(self) -> tuple[int, ...]:
        """Die Jahrgänge dieser Teilzeile, aufsteigend, wie sie dastehen."""
        return tuple(wert.jahrgang for wert in self.werte)

    @property
    def hat_antrag(self) -> bool:
        """Hängt an einer ihrer Jahreszahlen ein Antragskasten?"""
        return any(teil.antrag for wert in self.werte
                   for zeile in wert.zusaetze for teil in zeile.teile)

    @property
    def farben(self) -> tuple[str, ...]:
        """Ihre Schriftfarben in Lesefolge, jede einmal (für den Strich vorn)."""
        farben: list[str] = []
        for wert in self.werte:
            for farbe in wert.lesefarben:
                if farbe not in farben:
                    farben.append(farbe)
        return tuple(farben)


def _prozent(zahl: float) -> str:
    return f"{round(zahl, 3):g}%"


@dataclass(frozen=True)
class Markierung:
    """Wie ein Buch in einer Zeile einer Bücherliste aussieht.

    ``ganz`` hinterlegt die Zeile (Planung). ``iserv`` sagt, ob das Buch als
    Ganzes in IServ fehlt oder nur dort steht - dann ist jedes Feld der Zeile
    markiert (:attr:`zeile`). ``felder_anders`` sagt, ob IServ Titel, Verlag
    oder Preise anders nennt (der gelbe Strich). ``eintraege`` sind alle
    gezeigten Einträge. ``einfuehrung_offen``: die Zeile ist rot, weil IServ
    die Buchreihe schon führt, die Datei sie aber nur mit offener Einführung
    zu diesem Schuljahr plant (der Tooltip sagt das).
    """

    teilzeilen: tuple[Teilzeile, ...] = ()
    ganz: str = ""
    iserv: str = ""
    felder_anders: bool = False
    eintraege: tuple[Eintrag, ...] = ()
    einfuehrung_offen: bool = False

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
        """Die Abschnitte des Strichs vorn, von oben: je vorkommender Farbe
        einer, in der Reihenfolge, in der die Farben beim Lesen der Jahrgänge
        auftauchen - Teilzeile für Teilzeile, links nach rechts, oben nach
        unten (Jahrgangszahl, dann Jahreszahlen). Grau ist ein abgelehnter
        Antrag."""
        farben: list[str] = []
        for teil in self.teilzeilen:
            for farbe in teil.farben:
                if farbe not in farben:
                    farben.append(farbe)
        return tuple(farben)

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
        """Der Hintergrund des Strichs vorn (Planung) als CSS-Wert - leer ohne Farbe."""
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
    """Die Planung eines Eintrags: Farbe, ob er nach dem Vorjahr endete, das Jahr
    der Einführung bzw. Ausmusterung, ob er dieses Schuljahr gilt, der Zusatz je
    Planungszeile und ob es ihn nur wegen abgelehnter Einführungen gibt.

    ``faerbend`` ist die Planungszeile, deren Einführung bzw. Ausmusterung die
    Farbe gibt, ``abgelehnt`` bei Grau die zeitlich nächste abgelehnte
    Einführung - beide nennt der Tooltip. ``kommt``: eine Einführung, die
    zählt, liegt in diesem Schuljahr oder später (offen oder genehmigt);
    ``beginne`` sind deren Jahre."""

    farbe: str
    weg: bool
    jahr: int = 0
    wirkt: bool = False
    zusaetze: tuple[Zusatzzeile, ...] = ()
    grau: bool = False
    faerbend: Planungszeile | None = None
    abgelehnt: Planungszeile | None = None
    kommt: bool = False
    beginne: tuple[int, ...] = ()

    @property
    def hintergrund(self) -> str:
        """Die Farbe, in der der Eintrag zur Zeile beiträgt (Schrift oder Grau)."""
        return self.farbe or (GRAU if self.grau else "")


def _einfuehrung_abgelehnt(zeile: Planungszeile) -> bool:
    return bool(zeile.eingefuehrt_ab) and zeile.antrag_einfuehrung.status == ANTRAG_ABGELEHNT


@dataclass(frozen=True)
class _Zeilen:
    """Die Planungszeilen eines Eintrags: ``zaehlend`` sind die, die gelten
    (wirksamer Stand, ohne die mit abgelehnter Einführung), ``urspruenglich``
    alle, wie sie in der Datei stehen - aus ihnen kommt der Zusatz.
    ``nur_ausmusterung`` sind die mit abgelehnter Einführung und einer
    Ausmusterung: das Buch läuft dort nicht, aber die Ausmusterung färbt
    trotzdem (Entscheidung 2026-11-05, Unlogisches darf gefärbt werden)."""

    zaehlend: tuple[Planungszeile, ...]
    urspruenglich: tuple[Planungszeile, ...]
    einfuehrung_abgelehnt: bool
    nur_ausmusterung: tuple[Planungszeile, ...] = ()

    def wirkt(self, schuljahr: str) -> bool:
        return any(wirkt_im_schuljahr(z, schuljahr) for z in self.zaehlend)


def _zeilen_je_eintrag(stand: Buchplanung, original: Buchplanung,
                       buch: Buch) -> dict[Eintrag, _Zeilen]:
    """Die Zeilen des Buchs je Eintrag. ``stand`` ist der wirksame Stand (eine
    abgelehnte Ausmusterung ist weg), ``original`` der der Datei - beide haben
    dieselben Zeilen in derselben Reihenfolge."""
    paare = zip(stand.planung, original.planung, strict=True)
    gesammelt: dict[Eintrag, list[tuple[Planungszeile, Planungszeile]]] = {}
    for wirksam, ursprung in paare:
        if ursprung.isbn == buch.isbn:
            gesammelt.setdefault((ursprung.fach, ursprung.jahrgang, ursprung.leihbar),
                                 []).append((wirksam, ursprung))
    return {
        eintrag: _Zeilen(
            zaehlend=tuple(w for w, u in paare_ if not _einfuehrung_abgelehnt(u)),
            urspruenglich=tuple(sorted((u for _, u in paare_), key=zeitfolge)),
            einfuehrung_abgelehnt=any(_einfuehrung_abgelehnt(u) for _, u in paare_),
            nur_ausmusterung=tuple(w for w, u in paare_
                                   if _einfuehrung_abgelehnt(u) and w.ausgemustert_nach),
        )
        for eintrag, paare_ in gesammelt.items()
    }


def _plan_des_eintrags(stand: Buchplanung, jetzt: int, zeilen: _Zeilen, *,
                       offen: bool, in_iserv: bool) -> _Plan | None:
    """Die Planung eines Eintrags, der in diesem Schuljahr gilt, noch kommt, nach dem
    Vorjahr endete oder nur an abgelehnten Einführungen hängt - sonst ``None``.

    Es färbt das zeitlich nächste Ereignis, bis IServ es umgesetzt hat
    (Entscheidung 2026-11-05). Eine Einführung zu diesem Schuljahr mit
    Ausmusterung ist blau, solange IServ den Eintrag noch nicht führt
    (``offen``: Bücherliste oder Buchreihe weicht ab), erst danach rot; eine
    spätere Einführung nach einer Ausmusterung färbt erst, wenn die
    Ausmusterung durch ist. Ein Eintrag, der dieses Schuljahr nicht gilt und
    später kommt, ist blau. Nach dem Vorjahr ausgemustert ist er
    rot und durchgestrichen, solange IServ ihn noch führt - auch wenn er später
    wieder eingeführt wird; führt IServ ihn nicht mehr, ist er dann blau.
    Eine abgelehnte Einführung zählt nicht (der Eintrag läuft dort nicht),
    ihre Ausmusterung aber schon (``nur_ausmusterung``); eine abgelehnte
    Ausmusterung ist im wirksamen Stand schon weg. Was danach keinen Sinn
    mehr ergibt, färbt trotzdem - das richtet später das Mit-Ablehnen."""
    zaehlend = zeilen.zaehlend
    # Jede Zeile, deren Ausmusterung färben darf.
    mit_ende = zaehlend + zeilen.nur_ausmusterung
    laufend = any(planungs_status(z, stand.schuljahr) != PLANUNG_AUSGEMUSTERT for z in zaehlend)
    eben_weg = any(z.ende == jetzt - 1 for z in mit_ende)
    if not (laufend or eben_weg) and not zeilen.einfuehrung_abgelehnt:
        return None
    beginne = [z.beginn for z in zaehlend if z.beginn is not None and z.beginn >= jetzt]
    enden = [z.ende for z in mit_ende if z.ende is not None and z.ende >= jetzt - 1]
    wirkt = zeilen.wirkt(stand.schuljahr)
    weg = eben_weg and not wirkt and (in_iserv or not beginne)
    # Fehlt der Eintrag in IServ, hat Blau nur dann Vorrang vor einer
    # Ausmusterung, wenn die Einführung jetzt fällig ist.
    faellig = offen and bool(beginne) and min(beginne) == jetzt
    # Kommt eine Ausmusterung (ab diesem Schuljahr) noch vor der nächsten
    # Einführung, ist sie das Nächste - auch wenn der Eintrag gerade nicht läuft.
    vorher_weg = bool(beginne) and any(jetzt <= ende < min(beginne) for ende in enden)
    if weg:
        farbe, jahr = AUSMUSTERUNG, min(enden)
    elif beginne and (not enden or (not wirkt and not vorher_weg) or faellig):
        farbe, jahr = EINFUEHRUNG, min(beginne)
    elif enden:
        farbe, jahr = AUSMUSTERUNG, min(enden)
    else:
        farbe, jahr = "", 0
    if farbe == EINFUEHRUNG:
        faerbend = next(z for z in zaehlend if z.beginn == jahr)
    elif farbe == AUSMUSTERUNG:
        faerbend = next(z for z in mit_ende if z.ende == jahr)
    else:
        faerbend = None
    # Grau nur, wenn auch keine Ausmusterung färbt („läuft oder wird ausgemustert“).
    grau = zeilen.einfuehrung_abgelehnt and not (laufend or eben_weg) and not farbe
    return _Plan(
        farbe=farbe,
        weg=weg,
        jahr=jahr,
        wirkt=wirkt,
        zusaetze=zusatz_je_zeile(zeilen.urspruenglich, stand.schuljahr),
        grau=grau,
        faerbend=faerbend,
        abgelehnt=_naechste_abgelehnte(zeilen.urspruenglich, jetzt) if grau else None,
        kommt=bool(beginne),
        beginne=tuple(beginne),
    )


def _einfuehrung_offen(zeile: Planungszeile, jetzt: int) -> bool:
    """Ist die Einführung dieser Zeile zu diesem Schuljahr noch nicht entschieden?"""
    return zeile.beginn == jetzt and zeile.antrag_einfuehrung.status == ANTRAG_OFFEN


def _ausmusterung_offen(zeile: Planungszeile, jetzt: int) -> bool:
    """Ist die Ausmusterung dieser Zeile nach dem Vorjahr noch nicht entschieden?"""
    return zeile.ende == jetzt - 1 and zeile.antrag_ausmusterung.status == ANTRAG_OFFEN


def entschiedener_stand(stand: Buchplanung) -> Buchplanung:
    """Der Stand, gegen den die Fach-Ansicht mit IServ vergleicht: nur was
    entschieden ist (Entscheidung 2026-11-05, ersetzt die vom 2026-11-04).

    Solange die Ausmusterung nach dem Vorjahr nicht genehmigt ist, läuft das
    Buch noch - die Zeile verliert ihre Ausmusterung. Solange die Einführung
    zu diesem Schuljahr nicht genehmigt ist, ist es noch nicht eingeführt; eine
    abgelehnte Einführung gilt nie - beide Zeilen fallen weg. Anträge zu
    anderen Schuljahren ändern nichts: frühere Zeilen gelten als entschieden,
    spätere werden noch nicht verglichen. ``stand`` ist der wirksame
    (:func:`ohne_abgelehnte_ausmusterungen`); die Schrift rechnet weiter mit ihm.
    """
    jetzt = _jahr(stand.schuljahr)
    if jetzt is None:
        return stand
    zeilen = tuple(
        replace(zeile, ausgemustert_nach="") if _ausmusterung_offen(zeile, jetzt) else zeile
        for zeile in stand.planung
        if not _einfuehrung_abgelehnt(zeile) and not _einfuehrung_offen(zeile, jetzt))
    return stand if zeilen == stand.planung else replace(stand, planung=zeilen)


def _naechste_abgelehnte(zeilen: tuple[Planungszeile, ...], jetzt: int) -> Planungszeile | None:
    """Die zeitlich nächste abgelehnte Einführung: die früheste ab diesem
    Schuljahr, sonst die letzte davor."""
    abgelehnt = sorted((z for z in zeilen if _einfuehrung_abgelehnt(z) and z.beginn is not None),
                       key=lambda z: z.beginn or 0)
    kommend = [z for z in abgelehnt if (z.beginn or 0) >= jetzt]
    if kommend:
        return kommend[0]
    return abgelehnt[-1] if abgelehnt else None


BUCHREIHE_ANLEGEN = "Buchreihe muss in IServ angelegt werden"


def _beantragt(zeile: Planungszeile, art: str) -> str:
    return " beantragt" if zeile.antrag(art).status == ANTRAG_OFFEN else ""


def _schrift_hinweis(plan: _Plan | None, jahrgang: int, jetzt: int) -> str:
    """Was die Schrift (Farbe, Durchstreichen) des Jahrgangs sagt - Entscheidung
    2026-11-04. Ein offener Antrag hängt „beantragt“ an; „für ESJ“ steht nur,
    wenn die Einführung nach dem ausgewählten Schuljahr liegt."""
    if plan is None:
        return ""
    jg = f"Jahrgang {jahrgang}"
    if plan.grau and plan.abgelehnt is not None:
        abgelehnt = plan.abgelehnt
        fuer = f" für {abgelehnt.eingefuehrt_ab}" if (abgelehnt.beginn or 0) > jetzt else ""
        antrag = abgelehnt.antrag_einfuehrung
        return "\n".join([f"Einführung der Buchreihe in {jg}{fuer} abgelehnt"]
                         + ([f"am {antrag.datum.strftime('%d.%m.%Y')}"] if antrag.datum else [])
                         + ([f"durch {antrag.signatur}"] if antrag.signatur else []))
    zeile = plan.faerbend
    if zeile is None:
        return ""
    if plan.farbe == EINFUEHRUNG:
        fuer = f" für {zeile.eingefuehrt_ab}" if plan.jahr > jetzt else ""
        return f"Einführung der Buchreihe in {jg}{fuer}{_beantragt(zeile, ART_EINFUEHRUNG)}"
    if plan.weg:
        return f"Ausmusterung der Buchreihe in {jg}{_beantragt(zeile, ART_AUSMUSTERUNG)}"
    return (f"Ausmusterung der Buchreihe in {jg} nach {zeile.ausgemustert_nach}"
            f"{_beantragt(zeile, ART_AUSMUSTERUNG)}")


def _iserv_hinweise(jahrgang: int, *, anlegen: bool, steht_noch: bool, reihe: bool,
                    liste: bool, wechsel_auf: bool | None, reihe_weg: bool = False) -> list[str]:
    """Was die Markierung des Jahrgangs in IServ zu tun sagt - Entscheidung
    2026-11-04. ``wechsel_auf``: der Jahrgang steht in der anderen Teilzeile
    mit der anderen Markierung, IServ muss nur „leihbar“ umstellen - dann
    gilt nur das. ``reihe_weg``: die Buchreihe geht ganz, der Jahrgang ist
    auch an ihr zu entfernen (Strich oben, Entscheidung 2026-11-05)."""
    jg = f"Jahrgang {jahrgang}"
    zeilen = [BUCHREIHE_ANLEGEN] if anlegen else []
    if wechsel_auf is not None:
        auf = "leihbar" if wechsel_auf else "nicht leihbar"
        zeilen.append(f"Buchreihe ist in Bücherliste für {jg} auf {auf} zu setzen")
        return zeilen
    if reihe:
        zeilen.append(f"{jg} ist der Buchreihe hinzuzufügen")
    if steht_noch:
        zeilen.append(f"Buchreihe ist aus Bücherliste für {jg} in IServ zu entfernen")
        if reihe_weg:
            zeilen.append(f"{jg} ist aus der Buchreihe zu entfernen")
    elif liste:
        zeilen.append(f"Buchreihe ist Bücherliste für {jg} hinzuzufügen")
    return zeilen


def _zusammen(werte: list[Wert]) -> Wert:
    """Ein Wert aus mehreren Einträgen (Verlagsansicht: ein Jahrgang über alle Fächer)."""
    if len(werte) == 1:
        return werte[0]
    plan = geordnet([w.plan for w in werte])
    iserv = [w.iserv for w in werte if w.iserv]
    zusaetze = {w.zusaetze for w in werte}
    jahre = [w.jahr for w in werte if plan and w.plan == plan[0]]
    return Wert(
        text=werte[0].text,
        zusaetze=zusaetze.pop() if len(zusaetze) == 1 else (),
        plan=plan[0] if plan else "",
        weg=all(w.weg for w in werte),
        iserv=STEHT_NOCH if STEHT_NOCH in iserv else iserv[0] if iserv else "",
        hinweis="\n".join(dict.fromkeys(w.hinweis for w in werte if w.hinweis)),
        jahrgang=werte[0].jahrgang,
        jahr=min(jahre) if jahre else 0,
        grau=all(w.grau for w in werte),
        reihe_fehlt=any(w.reihe_fehlt for w in werte),
        liste_fehlt=any(w.liste_fehlt for w in werte),
        reihe_weg=all(w.reihe_weg for w in werte),
    )


def _ganz(plaene: Iterable[tuple[Eintrag, _Plan]]) -> str:
    """Die Farbe, die jeder der ``plaene`` hat (Schrift, oder Grau, wo es das
    Buch nur wegen abgelehnter Einführungen gäbe) - leer, wenn sie sich
    unterscheiden, einer keine hat oder es keine gibt. ``plaene`` sind die der
    ganzen Buchreihe oder die einer Teilzeile (ein „leihbar“), je über alle
    Fächer.

    Rot nur, wenn zu keiner Zahl nach ihrer Ausmusterung im selben Fach und
    Jahrgang eine Einführung unter den ``plaene`` geplant ist (offen oder
    genehmigt, Entscheidung 2026-11-05): die Buchreihe bzw. ihr Leih- oder
    Kaufbuch soll ganz gehen und nicht wiederkommen. Für die ganze Buchreihe
    zählt jede Einführung, für eine Teilzeile nur die mit ihrem „leihbar“ -
    beim Wechsel ist also das Leihbuch rot hinterlegt, die Zeile nicht."""
    alle = list(plaene)
    farben = {plan.hintergrund for _, plan in alle}
    if len(farben) != 1:
        return ""
    farbe = farben.pop()
    if farbe != AUSMUSTERUNG:
        return farbe
    beginne: dict[tuple[str, int], list[int]] = {}
    for (fach, jahrgang, _), plan in alle:
        beginne.setdefault((fach, jahrgang), []).extend(plan.beginne)
    if any(beginn > plan.jahr for (fach, jahrgang, _), plan in alle
           for beginn in beginne[(fach, jahrgang)]):
        return ""
    return farbe


def markierung(stand: Buchplanung, buch: Buch, abweichung: Abweichung | None = None, *,
               im: Callable[[Eintrag], bool], nach: str = JAHRGANG,
               original: Buchplanung | None = None) -> Markierung:
    """Die Farben eines Buchs in einer Zeile (Regeln: Modulkopf).

    ``im`` wählt die Einträge der Zeile (Fach-Ansicht: die des Fachs), ``nach``
    die Wertspalte: ``jahrgang`` oder ``fach``. ``abweichung`` ist der
    Vergleich mit IServ; ohne ihn bleibt jede Markierung weg.

    ``stand`` ist der wirksame Stand (eine abgelehnte Ausmusterung ist darin
    weg, ``ohne_abgelehnte_ausmusterungen``) - aus ihm kommt die Schrift.
    ``abweichung`` ist gegen den entschiedenen Stand gerechnet
    (:func:`entschiedener_stand`), und so wird markiert: eine nicht genehmigte
    Ausmusterung läuft noch, eine nicht genehmigte Einführung ist noch nicht
    eingeführt. ``original`` ist der Stand der Datei, aus dem Zusatz, Anträge
    und abgelehnte Einführungen kommen. Ohne ihn ist es derselbe.
    """
    jetzt = _jahr(stand.schuljahr)
    original = original or stand
    zeilen = _zeilen_je_eintrag(stand, original, buch) if jetzt is not None else {}
    soll: set[Eintrag] = set()
    fehlt: set[Eintrag] = set()
    nur_iserv: set[Eintrag] = set()
    ist: set[Eintrag] = set()
    fehlt_schrift: set[Eintrag] = set()
    if abweichung is not None:
        # Markiert wird, was der entschiedene Stand anders sagt als IServ
        # (Entscheidung 2026-11-05). Die Schrift rechnet mit dem wirksamen
        # Stand gegen das, was IServ führt (``ist``).
        soll = set(aktive_eintraege(entschiedener_stand(stand), buch))
        ist = (soll - set(abweichung.eintraege_fehlen)) | set(abweichung.eintraege_nur_iserv)
        fehlt, nur_iserv = soll - ist, ist - soll
        gilt = {e for e, z in zeilen.items() if z.wirkt(stand.schuljahr)}
        fehlt_schrift = gilt - ist
    buchreihe = set(abweichung.buchreihe_fehlt) if abweichung else set()
    planung: dict[Eintrag, _Plan] = {}
    if jetzt is not None:
        for eintrag, z in zeilen.items():
            plan = _plan_des_eintrags(
                stand, jetzt, z,
                offen=eintrag in fehlt_schrift or eintrag[1] in buchreihe,
                in_iserv=eintrag in ist)
            if plan is not None:
                planung[eintrag] = plan
    eintraege = sorted((e for e in set(planung) | nur_iserv if im(e)),
                       key=lambda e: (e[0].casefold(), e[1], not e[2]))

    # Der Hintergrund schaut auf alle Fächer, aber nur auf die gezeigten Einträge.
    ganz = _ganz(planung.items())
    # Die Buchreihe geht ganz (Entscheidung 2026-11-05): dieses Schuljahr führt
    # sie kein Fach, und keine Einführung kommt (offen oder genehmigt). Dann ist
    # jeder rot markierte Jahrgang auch an der Buchreihe zu entfernen (Strich oben).
    reihe_weg = abweichung is not None and not soll \
        and not any(plan.kommt for plan in planung.values())
    beide = len({leihbar for _, _, leihbar in planung}) > 1
    art = abweichung.art if abweichung else ""
    # Ganz blau markiert ist die Zeile nur, wenn die Buchreihe in IServ erst
    # angelegt werden muss (Entscheidung 2026-11-04); gibt es sie im Inventar
    # schon, zeigen die Jahrgänge, was fehlt. Ist das Inventar unbekannt, gilt
    # die Zeile als neu.
    anlegen = art == NUR_EXCEL and abweichung is not None \
        and abweichung.buchreihe_angelegt is not True
    nur_dort = art == NUR_ISERV
    # Ganz rot, weil die Einführung noch nicht genehmigt ist, IServ die
    # Buchreihe aber schon führt - das sagt dann der Tooltip.
    einfuehrung_offen = nur_dort and jetzt is not None and any(
        _einfuehrung_offen(zeile, jetzt) for z in zeilen.values() for zeile in z.urspruenglich)

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
            reihe = eintrag in soll and jahrgang in buchreihe
            # Steht der Jahrgang in der anderen Teilzeile andersherum markiert,
            # ist in IServ nur „leihbar“ umzustellen - auf den Wert der blauen.
            gegenueber = (fach, jahrgang, not leihbar)
            wechsel_auf = (leihbar if liste == FEHLT else not leihbar) if (
                (liste == FEHLT and gegenueber in nur_iserv)
                or (liste == STEHT_NOCH and gegenueber in fehlt)) else None
            schluessel = (fach.casefold(), 0) if nach == FACH else ("", jahrgang)
            hinweise = [_schrift_hinweis(plan, jahrgang, jetzt or 0)] + _iserv_hinweise(
                jahrgang, anlegen=anlegen and eintrag in fehlt, steht_noch=liste == STEHT_NOCH,
                reihe=reihe, liste=liste == FEHLT, wechsel_auf=wechsel_auf,
                reihe_weg=reihe_weg and liste == STEHT_NOCH)
            je_schluessel.setdefault(schluessel, []).append(Wert(
                text=fach if nach == FACH else str(jahrgang),
                zusaetze=plan.zusaetze if plan else (),
                plan=plan.farbe if plan else "",
                weg=plan.weg if plan else False,
                iserv=liste or (FEHLT if reihe else ""),
                hinweis="\n".join(hinweis for hinweis in hinweise if hinweis),
                jahrgang=jahrgang,
                jahr=plan.jahr if plan else 0,
                grau=plan.grau if plan else False,
                reihe_fehlt=reihe,
                liste_fehlt=liste == FEHLT,
                reihe_weg=reihe_weg and liste == STEHT_NOCH,
            ))
        werte = tuple(_zusammen(je_schluessel[k]) for k in sorted(je_schluessel))
        teil_ganz = ""
        if beide and not ganz:
            teil_ganz = _ganz((e, p) for e, p in planung.items() if e[2] == leihbar)
        teilzeilen.append(Teilzeile(leihbar=leihbar, werte=werte, ganz=teil_ganz))

    if nach == JAHRGANG:
        # Wie die Fach-Ansicht beim Laden sortiert ist (Jahrgang aufsteigend,
        # static/sortieren.js): die Teilzeile mit den kleineren Jahrgängen
        # zuerst - Jahrgang für Jahrgang, die kürzere Liste vor der längeren,
        # bei Gleichstand leihbar vor Kaufbuch.
        teilzeilen.sort(key=lambda teil: (teil.jahrgaenge, not teil.leihbar))
    return Markierung(
        teilzeilen=tuple(teilzeilen), ganz=ganz,
        iserv=FEHLT if anlegen else STEHT_NOCH if nur_dort else "",
        felder_anders=bool(abweichung and any(f != "leihbar" for f, _ in abweichung.felder)),
        eintraege=tuple(eintraege),
        einfuehrung_offen=einfuehrung_offen,
    )


def ohne_abgelehnte_ausmusterungen(stand: Buchplanung) -> Buchplanung:
    """Der Stand der Fach-Ansicht: eine abgelehnte Ausmusterung gilt nicht, das
    Buch bleibt. Gleiche Zeilen in gleicher Reihenfolge, nur ohne deren
    Ausmusterung - so rechnen der Vergleich mit IServ und die Liste damit."""
    zeilen = tuple(
        replace(zeile, ausgemustert_nach="")
        if zeile.ausgemustert_nach and zeile.antrag_ausmusterung.status == ANTRAG_ABGELEHNT
        else zeile
        for zeile in stand.planung)
    return stand if zeilen == stand.planung else replace(stand, planung=zeilen)


def im_fach(fach: str) -> Callable[[Eintrag], bool]:
    """Die Einträge eines Fachs - der Filter der Fach-Ansicht."""
    return lambda eintrag: eintrag[0] == fach
