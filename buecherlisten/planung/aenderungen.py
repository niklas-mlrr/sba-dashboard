"""Die Änderungsliste: jede Einführung und Ausmusterung als Antrag, geordnet zum Entscheiden.

Gerechnet aus dem gespeicherten Stand (:mod:`~buecherlisten.planung.modelle`),
ohne Netz, ohne Excel, ohne HTTP. Die Seite dazu ist ``GET
/buecherliste/aenderungen`` (``app/api/buecherliste.py``), ihr Raster baut
``app/aenderungsliste.py``; entschieden wird in
:func:`~buecherlisten.planung.abgleich.entscheide_antrag`.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .modelle import (
    ANTRAG_ABGELEHNT,
    ANTRAG_GENEHMIGT,
    ART_AUSMUSTERUNG,
    ART_EINFUEHRUNG,
    Antragsentscheidung,
    Buchplanung,
    Planungszeile,
    UngueltigesSchuljahr,
    schuljahr_zahl,
    wirkt_im_schuljahr,
)

# ── Die Änderungsliste ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Aenderung:
    """Ein Antrag auf der Änderungsliste: ein Buch, ein Fach, ein Jahrgang, eine Art."""

    isbn: str
    titel: str
    verlag: str
    fach: str
    jahrgang: int
    art: str
    schuljahr: str
    entscheidung: Antragsentscheidung
    begruendung: str = ""
    # Leihbar aus der Zeile, Neupreis und Leihgebühr aus der Buchreihe:
    # leihbare Bücher stehen in einem Abschnitt zuerst, und der Neupreis ist,
    # was eine Einführung kostet (je Exemplar).
    leihbar: bool = False
    neupreis: float | None = None
    leihgebuehr: float | None = None
    # Seit wann die Planungszeile das Buch führt - bei einer Ausmusterung, wie
    # lange es im Einsatz war. Leer für alles, was vor der Planung schon da war.
    eingefuehrt_ab: str = ""

    @property
    def status(self) -> str:
        return self.entscheidung.status

    @property
    def einfuehrung(self) -> bool:
        return self.art == ART_EINFUEHRUNG

    @property
    def wechsel(self) -> int:
        """Das Schuljahr (Jahresanfang), ab dem das Neue gilt.

        Eine Einführung „ab 2027/2028“ und eine Ausmusterung „nach 2026/2027“
        gehören beide zum Wechsel 2027 und stehen in einem Abschnitt.
        """
        jahr = schuljahr_zahl(self.schuljahr)
        return jahr if self.einfuehrung else jahr + 1


def zu_entscheidende_antraege(zeile: Planungszeile, schuljahr: str) -> tuple[str, ...]:
    """Die Anträge dieser Zeile, die auf der Änderungsliste stehen.

    Eine Einführung ab dem laufenden Schuljahr oder später, eine Ausmusterung
    nach dem Vorjahr oder später (:func:`aenderungen_im_schuljahr`). Eine
    längst vollzogene Einführung ist kein Antrag mehr - über sie entscheidet
    niemand, also hält sie auch nichts auf. Unlesbares zählt nicht.
    """
    try:
        jetzt = schuljahr_zahl(schuljahr)
    except UngueltigesSchuljahr:
        return ()
    arten: list[str] = []
    for art, ab_jahr in ((ART_EINFUEHRUNG, jetzt), (ART_AUSMUSTERUNG, jetzt - 1)):
        angabe = zeile.schuljahr_des_antrags(art)
        try:
            if angabe and schuljahr_zahl(angabe) >= ab_jahr:
                arten.append(art)
        except UngueltigesSchuljahr:
            continue
    return tuple(arten)


def alles_genehmigt(zeile: Planungszeile, schuljahr: str) -> bool:
    """Ist jeder Antrag dieser Zeile, über den zu entscheiden ist, genehmigt?

    Eine Zeile ohne einen solchen Antrag gilt als genehmigt: an ihr ist nichts
    mehr offen (Entscheidung 2026-10-10). Das Planungsmenü hinterlegt sie dann
    in der Farbe ihres Status.
    """
    return all(zeile.antrag(art).status == ANTRAG_GENEHMIGT
               for art in zu_entscheidende_antraege(zeile, schuljahr))


def aenderungen_im_schuljahr(stand: Buchplanung) -> tuple[Aenderung, ...]:
    """Alle Einführungen und Ausmusterungen, die dieses Schuljahr zu entscheiden sind.

    * **Einführungen** ab dem laufenden Schuljahr oder später - eine längst
      vollzogene Einführung ist keine Änderung mehr.
    * **Ausmusterungen** nach dem Vorjahr oder später: nach dem Vorjahr heißt,
      das Buch fehlt schon in der Liste dieses Schuljahrs.

    Eine Zeile mit beidem (ein Buch nur für ein Schuljahr) ergibt zwei
    Anträge. Eine unlesbare Schuljahresangabe wird übersprungen, wie in
    :func:`planungs_status`.

    Sortiert nach **Fach**, darin nach Buch (Titel, ISBN), dann Jahrgang und
    Einführung vor Ausmusterung. Ein Buch in zwei Fächern steht unter beiden,
    jeweils mit den Anträgen dieses Fachs. Die Seite ordnet die Anträge
    selbst noch einmal, in Abschnitten (:func:`aenderungsliste`).
    """
    try:
        schuljahr_zahl(stand.schuljahr)
    except UngueltigesSchuljahr:
        return ()
    heraus: list[Aenderung] = []
    for zeile in stand.planung:
        buch = stand.buch(zeile.isbn)
        for art in zu_entscheidende_antraege(zeile, stand.schuljahr):
            angabe = zeile.schuljahr_des_antrags(art)
            heraus.append(Aenderung(
                isbn=zeile.isbn,
                titel=buch.titel if buch else zeile.isbn,
                verlag=buch.verlag if buch else "",
                fach=zeile.fach, jahrgang=zeile.jahrgang, art=art, schuljahr=angabe,
                entscheidung=zeile.antrag(art), begruendung=zeile.begruendung,
                leihbar=zeile.leihbar,
                neupreis=buch.neupreis if buch else None,
                leihgebuehr=buch.leihgebuehr if buch else None,
                eingefuehrt_ab=zeile.eingefuehrt_ab,
            ))
    return tuple(sorted(heraus, key=lambda a: (
        a.fach.casefold(), a.titel.casefold(), a.isbn, a.jahrgang, a.art != ART_EINFUEHRUNG)))


@dataclass(frozen=True)
class Verbleib:
    """Ob ein Buch mit seinen Anträgen einer Art **ganz** kommt oder **ganz** geht - und warum.

    Die Änderungsliste färbt solche Bücher kräftiger. ``grund`` steht im
    Buchmenü und unter der Maus.
    """

    ganz: bool
    grund: str


def _paare_text(paare: Sequence[tuple[str, int]]) -> str:
    """``[("Musik", 8), ("Musik", 9), ("Chemie", 9)]`` → ``"Chemie 9; Musik 8, 9"``."""
    je_fach: dict[str, list[int]] = {}
    for fach, jahrgang in sorted(paare, key=lambda p: (p[0].casefold(), p[1])):
        je_fach.setdefault(fach, []).append(jahrgang)
    return "; ".join(f"{fach} {', '.join(map(str, jgs))}" for fach, jgs in je_fach.items())


def verbleib_der_buecher(stand: Buchplanung,
                         antraege: Sequence[Aenderung]) -> dict[tuple[str, str], Verbleib]:
    """Je (ISBN, Art) der Anträge: kommt das Buch ganz neu, geht es ganz weg?

    Es zählen alle Bücherlisten, jedes Fach. Gelistet ist ein Buch in einem
    Fach und Jahrgang, wenn es dort in diesem Schuljahr im Regal steht
    (:func:`wirkt_im_schuljahr`).

    * **Ganz neu** ist eine Einführung, wenn das Buch im Moment in keiner
      Bücherliste steht. Ein Jahrgang, in den es gerade (ab diesem Schuljahr)
      eingeführt wird, zählt nicht - der ist die Einführung selbst.
    * **Ganz weg** ist eine Ausmusterung, wenn für jeden Jahrgang, in dessen
      Liste das Buch steht, eine Ausmusterung beantragt ist und es keinen
      Antrag gibt, es irgendwo einzuführen. Abgelehnte Anträge zählen nicht:
      eine abgelehnte Ausmusterung lässt das Buch in seiner Liste, eine
      abgelehnte Einführung bringt es nirgends hin. Eine abgelehnte Einführung
      bleibt dagegen ganz neu - das Buch steht ja trotzdem in keiner Liste.
    """
    try:
        jetzt = schuljahr_zahl(stand.schuljahr)
    except UngueltigesSchuljahr:
        return {}
    zeilen: dict[str, dict[tuple[str, int], list[Planungszeile]]] = {}
    for zeile in stand.planung:
        zeilen.setdefault(zeile.isbn, {}).setdefault((zeile.fach, zeile.jahrgang), []).append(zeile)
    buecher = {buch.isbn: buch for buch in stand.buecher}
    je_buch: dict[str, list[Aenderung]] = {}
    for antrag in antraege:
        je_buch.setdefault(antrag.isbn, []).append(antrag)

    heraus: dict[tuple[str, str], Verbleib] = {}
    for isbn, eigene in je_buch.items():
        eigene_zeilen = zeilen.get(isbn, {})
        buch = buecher.get(isbn)
        paare = set(buch.kombinationen if buch else ()) | set(eigene_zeilen)
        gelistet = {p for p in paare
                    if any(wirkt_im_schuljahr(z, stand.schuljahr)
                           for z in eigene_zeilen.get(p) or (None,))}
        einfuehrungen = [a for a in eigene if a.einfuehrung]
        ausmusterungen = {(a.fach, a.jahrgang): a for a in eigene if not a.einfuehrung}
        # Geht in einem Paar eine Zeile und kommt zum selben Wechsel eine neue
        # (etwa als Kaufbuch statt als Leihbuch), bleibt das Buch dort stehen.
        weiter = {p for p, a in ausmusterungen.items()
                  if any((e.fach, e.jahrgang) == p and e.wechsel == a.wechsel
                         and e.status != ANTRAG_ABGELEHNT for e in einfuehrungen)}

        if einfuehrungen:
            schon = sorted(gelistet - {(a.fach, a.jahrgang) for a in einfuehrungen
                                       if a.wechsel == jetzt
                                       and (a.fach, a.jahrgang) not in weiter})
            heraus[(isbn, ART_EINFUEHRUNG)] = Verbleib(False, "steht schon in der Bücherliste "
                                                       + _paare_text(schon)) if schon \
                else Verbleib(True, "ganz neu, steht noch in keiner Bücherliste")

        if ausmusterungen:
            ohne_antrag = sorted(gelistet - set(ausmusterungen))
            abgelehnt = sorted(p for p, a in ausmusterungen.items() if a.status == ANTRAG_ABGELEHNT)
            if ohne_antrag:
                verbleib = Verbleib(False, f"bleibt in der Bücherliste {_paare_text(ohne_antrag)}"
                                           " (kein Antrag)")
            elif weiter:
                verbleib = Verbleib(False, f"bleibt in der Bücherliste {_paare_text(sorted(weiter))}"
                                           " (dort neu eingeführt)")
            elif abgelehnt:
                verbleib = Verbleib(False, f"bleibt in der Bücherliste {_paare_text(abgelehnt)}"
                                           " (Ausmusterung abgelehnt)")
            elif any(a.status != ANTRAG_ABGELEHNT for a in einfuehrungen):
                verbleib = Verbleib(False, "hat auch einen Antrag zur Einführung")
            else:
                verbleib = Verbleib(True, "ganz weg, steht danach in keiner Bücherliste mehr")
            heraus[(isbn, ART_AUSMUSTERUNG)] = verbleib
    return heraus


# ── Die Reihenfolge der Änderungsliste ───────────────────────────────────────
#
# Sortiert wird nach Fach und dann nach einer Rangfolge aus Jahrgang und
# Wechseljahr, die die Köpfe der Seite umstellen - wie bei den Bücherlisten:
# der erste Klick sortiert aufsteigend, jeder weitere auf dasselbe
# Kriterium dreht die Richtung um, und das zuletzt angeklickte geht vor.

RANG_JAHRGANG = "jg"
RANG_WECHSEL = "wechsel"

Rang = tuple[tuple[str, bool], ...]
"""(Kriterium, absteigend) in der Reihenfolge, in der sortiert wird."""

RANG_STANDARD: Rang = ((RANG_JAHRGANG, False), (RANG_WECHSEL, False))


def lies_rang(text: str | None) -> Rang:
    """``"wechsel-ab,jg"`` → ``(("wechsel", True), ("jg", False))``.

    So steht die Rangfolge in ``?sortierung=``. Fehlt ein Kriterium, wird es
    hinten aufsteigend angefügt; was die Seite nicht kennt oder doppelt
    kommt, ergibt die Standardreihenfolge.
    """
    rang: list[tuple[str, bool]] = []
    for teil in (text or "").split(","):
        name, _, richtung = teil.strip().partition("-")
        if name not in (RANG_JAHRGANG, RANG_WECHSEL) or richtung not in ("", "auf", "ab") \
                or any(name == vorhanden for vorhanden, _ in rang):
            return RANG_STANDARD
        rang.append((name, richtung == "ab"))
    for name, _ in RANG_STANDARD:
        if all(name != vorhanden for vorhanden, _ in rang):
            rang.append((name, False))
    return tuple(rang)


def rang_text(rang: Rang) -> str:
    """Die Umkehrung von :func:`lies_rang`."""
    return ",".join(name + ("-ab" if absteigend else "") for name, absteigend in rang)


def naechster_rang(rang: Rang, kriterium: str) -> Rang:
    """Die Rangfolge nach einem Klick auf ``kriterium``.

    Steht es schon vorn, dreht sich seine Richtung; sonst rückt es aufsteigend
    nach vorn, und die anderen behalten Reihenfolge und Richtung.
    """
    if rang[0][0] == kriterium:
        return ((kriterium, not rang[0][1]),) + rang[1:]
    return ((kriterium, False),) + tuple(eintrag for eintrag in rang if eintrag[0] != kriterium)


@dataclass(frozen=True)
class Abschnitt:
    """Was in **einem** Fach und Jahrgang zum **selben** Wechsel geht und kommt.

    Eine Ausmusterung nach 2026/27 und eine Einführung ab 2027/28 im selben
    Fach und Jahrgang stehen so auf gleicher Höhe: links die Ausmusterungen,
    rechts die Einführungen, je Seite in der Reihenfolge von
    :func:`aenderungsliste`. Fehlt eine Seite, kommt ein Buch ohne Vorgänger
    oder geht eines ohne Nachfolger. Jeder Antrag wird für sich entschieden.
    """

    fach: str
    jahrgang: int
    wechsel: int
    ausmusterungen: tuple[Aenderung, ...] = ()
    einfuehrungen: tuple[Aenderung, ...] = ()

    @property
    def antraege(self) -> tuple[Aenderung, ...]:
        return self.ausmusterungen + self.einfuehrungen

    @property
    def mit_partner(self) -> bool:
        return bool(self.ausmusterungen and self.einfuehrungen)

    def seite(self, art: str) -> tuple[Aenderung, ...]:
        return self.einfuehrungen if art == ART_EINFUEHRUNG else self.ausmusterungen

    def wert(self, kriterium: str) -> int:
        return self.jahrgang if kriterium == RANG_JAHRGANG else self.wechsel


def reichweite(antrag: Aenderung, alle: Sequence[Aenderung], *,
               jahrgang_absteigend: bool = False) -> tuple[int, int]:
    """Wohin das Buch eines Antrags über dessen Jahrgang hinaus reicht - als Sortierschlüssel.

    Gezählt werden die anderen Jahrgänge desselben Buchs im selben Fach und
    in derselben Art, jeweils der **nächstgelegene**: nach oben der Abstand
    zum nächsten früheren, nach unten zum nächsten späteren. Der kleinere
    Abstand entscheidet, bei Gleichstand der nach oben. Die Reihenfolge ist:
    oben mit Abstand 1, 2, 3 …, dann Bücher nur für diesen Jahrgang, dann
    unten mit dem größten Abstand zuerst und Abstand 1 zuletzt. So stehen die
    Kästen eines Buchs über Jahrgänge hinweg möglichst oft untereinander.

    Bei absteigendem Jahrgang steht der höhere oben; „oben“ ist dann er.
    """
    richtung = -1 if jahrgang_absteigend else 1
    andere = [(antrag.jahrgang - a.jahrgang) * richtung for a in alle
              if (a.fach, a.isbn, a.art) == (antrag.fach, antrag.isbn, antrag.art)
              and a.jahrgang != antrag.jahrgang]
    oben = min((d for d in andere if d > 0), default=None)
    unten = min((-d for d in andere if d < 0), default=None)
    if oben is None and unten is None:
        return (1, 0)
    if unten is None or (oben is not None and oben <= unten):
        return (0, oben or 0)
    return (2, -unten)


def aenderungsliste(stand: Buchplanung, rang: Rang = RANG_STANDARD) -> tuple[Abschnitt, ...]:
    """Die Änderungsliste dieses Schuljahrs in Abschnitten, in der Reihenfolge der Seite."""
    return ordne_aenderungen(aenderungen_im_schuljahr(stand), rang)


def ordne_aenderungen(alle: Sequence[Aenderung], rang: Rang = RANG_STANDARD) -> tuple[Abschnitt, ...]:
    """Anträge in Abschnitten und in der Reihenfolge der Seite.

    Jeder Antrag wird für sich einsortiert: nach Fach, dann nach ``rang`` (Jahrgang und Wechseljahr,
    jeweils auf- oder absteigend), und was dabei in Fach, Jahrgang und
    Wechsel gleich ist, bildet einen :class:`Abschnitt`. Innerhalb einer
    Seite eines Abschnitts nach :func:`reichweite`, dann Leihbuch vor
    Kaufbuch, dann Titel.
    """
    jahrgang_absteigend = dict(rang).get(RANG_JAHRGANG, False)
    sammlung: dict[tuple[str, int, int], dict[str, list[Aenderung]]] = {}
    for antrag in alle:
        seiten = sammlung.setdefault((antrag.fach, antrag.jahrgang, antrag.wechsel),
                                     {ART_EINFUEHRUNG: [], ART_AUSMUSTERUNG: []})
        seiten[antrag.art].append(antrag)

    def folge(antrag: Aenderung) -> tuple[tuple[int, int], bool, str, str]:
        return (reichweite(antrag, alle, jahrgang_absteigend=jahrgang_absteigend),
                not antrag.leihbar, antrag.titel.casefold(), antrag.isbn)

    abschnitte = [
        Abschnitt(fach=fach, jahrgang=jahrgang, wechsel=wechsel,
                  ausmusterungen=tuple(sorted(seiten[ART_AUSMUSTERUNG], key=folge)),
                  einfuehrungen=tuple(sorted(seiten[ART_EINFUEHRUNG], key=folge)))
        for (fach, jahrgang, wechsel), seiten in sammlung.items()
    ]

    def schluessel(abschnitt: Abschnitt) -> tuple:
        werte = [-abschnitt.wert(k) if absteigend else abschnitt.wert(k) for k, absteigend in rang]
        return (abschnitt.fach.casefold(), *werte)

    return tuple(sorted(abschnitte, key=schluessel))
