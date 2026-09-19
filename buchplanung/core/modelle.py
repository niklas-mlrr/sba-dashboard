"""Die Begriffe der Buchplanung - ohne Netz, ohne Excel, ohne HTTP.

Drei Dinge werden über ein Schuljahr hinweg festgehalten, und jedes gehört
einer anderen Person:

* **Preisprüfung** - der Beauftragte für die Schulbuchausleihe vergleicht die
  Preise in IServ mit den Verlagslisten. Schlüssel ist die ISBN; jedes Buch hat
  genau einen Verlag.
* **Rücklage** - eine Fachschaft möchte von einem Buch Exemplare behalten,
  statt sie wegzuwerfen. Schlüssel ist (ISBN, Fach): ein Buch kann zu mehreren
  Fächern gehören, und der Wunsch gehört der Fachschaft.
* **Planung** - ab bzw. bis wann ein Buch in einem Jahrgang geführt wird.
  Schlüssel ist (ISBN, Jahrgang), mit **zwei** Schuljahresangaben. Eine
  gestaffelte Einführung eines Mehrjahresbands (Jg. 7 ab 2027/28, Jg. 8 ab
  2028/29) sind damit zwei Zeilen statt einer Bemerkung im Freitext.

Dazu die **Fachbestätigung**: die Fachkonferenzleitung bestätigt die Liste
ihres Fachs als Ganzes, mit Kürzel und Datum.

Was hier **nicht** steht, ist ein Feld ``status``. Jeder Status wird aus den
eingetragenen Werten gerechnet (:func:`preis_status`, :func:`fach_status`,
:func:`planungs_status`). Ein gespeicherter Status könnte den Werten
widersprechen, aus denen er stammt - und niemand wüsste, welcher der beiden
recht hat.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

# ── Herkunft einer Zeile ─────────────────────────────────────────────────────

VORJAHR = "Vorjahr"
AKTUELL = "aktuell"
BEIDE = "beide"
# Eine Zeile, die es nur gibt, weil jemand für dieses Buch und diesen Jahrgang
# etwas geplant hat: die Einführung in einen Jahrgang, der das Buch heute noch
# gar nicht führt. Ohne diesen Wert hätte die Planung keinen Platz in der Datei.
NUR_PLANUNG = "nur Planung"

# ── Status der Preisprüfung ──────────────────────────────────────────────────

PREIS_OFFEN = "offen"
PREIS_BESTAETIGT = "bestätigt"
PREIS_ABWEICHEND = "abweichend"

# ── Status der Fachbestätigung ───────────────────────────────────────────────

FACH_OFFEN = "offen"
FACH_BESTAETIGT = "bestätigt"
FACH_VERALTET = "veraltet"

# ── Status einer Planungszeile ───────────────────────────────────────────────

PLANUNG_GEPLANT = "geplant"
PLANUNG_IM_EINSATZ = "im Einsatz"
PLANUNG_LAEUFT_AUS = "läuft aus"
PLANUNG_AUSGEMUSTERT = "ausgemustert"

# ── Status eines Rücklage-Wunsches ───────────────────────────────────────────

RUECKLAGE_GEWUENSCHT = "gewünscht"
RUECKLAGE_ZUGESAGT = "zugesagt"
RUECKLAGE_ZURUECKGELEGT = "zurückgelegt"

RUECKLAGE_STATUS: tuple[str, ...] = (
    RUECKLAGE_GEWUENSCHT,
    RUECKLAGE_ZUGESAGT,
    RUECKLAGE_ZURUECKGELEGT,
)

OHNE_FACH = "(ohne Fach)"
OHNE_VERLAG = "(ohne Verlag)"

# Die Legende, die im Blatt "Info" steht: Status → was er bedeutet. Sie steht
# in der Datei, weil die Datei ohne das Dashboard lesbar sein soll.
LEGENDE: tuple[tuple[str, str], ...] = (
    (PREIS_OFFEN, "Preis noch nicht gegen die Verlagsliste geprüft"),
    (PREIS_BESTAETIGT, "geprüfter Preis stimmt mit dem Preis in IServ überein"),
    (PREIS_ABWEICHEND,
     "der geprüfte Preis weicht vom Preis in IServ ab - in IServ nachziehen"),
    (FACH_BESTAETIGT, "die Fachkonferenzleitung hat die Liste dieses Fachs bestätigt"),
    (FACH_VERALTET,
     "die Liste hat sich nach der Bestätigung geändert - erneut bestätigen"),
    (PLANUNG_GEPLANT, "wird in diesem Jahrgang erst in einem späteren Schuljahr eingeführt"),
    (PLANUNG_IM_EINSATZ, "wird in diesem Jahrgang geführt"),
    (PLANUNG_LAEUFT_AUS, "wird in diesem Jahrgang nach dem angegebenen Schuljahr ausgemustert"),
    (PLANUNG_AUSGEMUSTERT, "ist in diesem Jahrgang bereits ausgemustert"),
    (RUECKLAGE_GEWUENSCHT, "die Fachschaft hat Exemplare zum Zurücklegen erbeten"),
    (RUECKLAGE_ZUGESAGT, "die Rücklage ist zugesagt, aber noch nicht erfolgt"),
    (RUECKLAGE_ZURUECKGELEGT, "die Exemplare liegen bei der Fachschaft"),
)

# IServ schreibt Schuljahre als "2026/2027". Nur der Jahresanfang wird
# verglichen; das reicht, um "früher als" zu entscheiden.
_JAHRESPAAR = re.compile(r"^\s*(\d{4})\s*/\s*(\d{2,4})\s*$")


class UngueltigesSchuljahr(ValueError):
    """Eine Schuljahresangabe hat nicht die Form ``2026/2027``."""


def schuljahr_zahl(kennung: str) -> int:
    """``"2026/2027"`` → ``2026``. Für den Vergleich zweier Schuljahre.

    Wirft :class:`UngueltigesSchuljahr`, statt stillschweigend 0 zu liefern:
    ein Tippfehler in der Spalte "eingeführt ab" darf nicht dazu führen, dass
    ein Buch als längst eingeführt gilt.
    """
    treffer = _JAHRESPAAR.match(kennung or "")
    if treffer is None:
        raise UngueltigesSchuljahr(
            f"„{kennung}“ ist keine Schuljahresangabe. Erwartet wird die "
            "IServ-Schreibweise „2026/2027“."
        )
    return int(treffer.group(1))


# ── Was aus IServ kommt ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Buch:
    """Ein Titel, wie ihn die Bücherlisten zweier Schuljahre zeigen.

    ``jahrgaenge_vorjahr`` und ``jahrgaenge_aktuell`` stehen getrennt, weil
    genau ihr Unterschied die Ausmusterung bzw. die Neueinführung ist.
    """

    isbn: str
    titel: str
    verlag: str
    faecher: tuple[str, ...] = ()
    jahrgaenge_vorjahr: tuple[int, ...] = ()
    jahrgaenge_aktuell: tuple[int, ...] = ()
    leihbar: bool = False
    neupreis: float | None = None
    leihgebuehr: float | None = None

    @property
    def jahrgaenge(self) -> tuple[int, ...]:
        return tuple(sorted(set(self.jahrgaenge_vorjahr) | set(self.jahrgaenge_aktuell)))

    @property
    def herkunft(self) -> str:
        if self.jahrgaenge_vorjahr and self.jahrgaenge_aktuell:
            return BEIDE
        return VORJAHR if self.jahrgaenge_vorjahr else AKTUELL

    @property
    def im_aktuellen_jahr(self) -> bool:
        return bool(self.jahrgaenge_aktuell)

    @property
    def fach_anzeige(self) -> str:
        return ", ".join(self.faecher) if self.faecher else OHNE_FACH

    @property
    def jahrgang_anzeige(self) -> str:
        return ", ".join(str(jahrgang) for jahrgang in self.jahrgaenge)


# ── Was von Hand eingetragen wird ────────────────────────────────────────────


@dataclass(frozen=True)
class Preispruefung:
    """Der gegen die Verlagsliste geprüfte Preis eines Buchs.

    Gespeichert wird der **Betrag**, nicht nur ein Haken: nur so fällt auf,
    wenn sich der Preis in IServ danach ändert.
    """

    isbn: str
    preis: float | None = None
    kuerzel: str = ""
    datum: date | None = None
    bemerkung: str = ""

    @property
    def leer(self) -> bool:
        return self.preis is None and not self.kuerzel and not self.bemerkung


@dataclass(frozen=True)
class Ruecklage:
    """Der Wunsch einer Fachschaft, Exemplare zu behalten."""

    isbn: str
    fach: str
    anzahl: int | None = None
    status: str = ""
    kuerzel: str = ""
    datum: date | None = None
    bemerkung: str = ""

    @property
    def leer(self) -> bool:
        return self.anzahl is None and not self.status and not self.bemerkung


@dataclass(frozen=True)
class Planungszeile:
    """Ab bzw. bis wann ein Buch in **einem** Jahrgang geführt wird."""

    isbn: str
    jahrgang: int
    eingefuehrt_ab: str = ""
    ausgemustert_nach: str = ""
    beschluss: str = ""
    bemerkung: str = ""

    @property
    def leer(self) -> bool:
        return not any((self.eingefuehrt_ab, self.ausgemustert_nach,
                        self.beschluss, self.bemerkung))


@dataclass(frozen=True)
class Fachbestaetigung:
    """Die Freigabe einer Fach-Bücherliste durch die Fachkonferenzleitung.

    ``bestaetigte_isbns`` ist der Stand, der bestätigt wurde - ausgeschrieben
    und nicht als Prüfsumme, damit auch ohne das Dashboard nachvollziehbar
    bleibt, *was* bestätigt wurde.
    """

    fach: str
    kuerzel: str = ""
    datum: date | None = None
    bemerkung: str = ""
    bestaetigte_isbns: tuple[str, ...] = ()

    @property
    def leer(self) -> bool:
        return not self.kuerzel and not self.bemerkung and not self.bestaetigte_isbns


# ── Der ganze Stand ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Buchplanung:
    """Alles, was in der Arbeitsmappe steht."""

    schuljahr: str = ""
    vorjahr: str = ""
    stand: date | None = None
    buecher: tuple[Buch, ...] = ()
    preise: tuple[Preispruefung, ...] = ()
    ruecklagen: tuple[Ruecklage, ...] = ()
    planung: tuple[Planungszeile, ...] = ()
    bestaetigungen: tuple[Fachbestaetigung, ...] = ()
    warnungen: tuple[str, ...] = field(default_factory=tuple)

    # ── Nachschlagen ────────────────────────────────────────────────────────

    def buch(self, isbn: str) -> Buch | None:
        return next((b for b in self.buecher if b.isbn == isbn), None)

    def pruefung(self, isbn: str) -> Preispruefung | None:
        return next((p for p in self.preise if p.isbn == isbn), None)

    def ruecklage(self, isbn: str, fach: str) -> Ruecklage | None:
        return next((r for r in self.ruecklagen if r.isbn == isbn and r.fach == fach), None)

    def planungszeile(self, isbn: str, jahrgang: int) -> Planungszeile | None:
        return next((z for z in self.planung
                     if z.isbn == isbn and z.jahrgang == jahrgang), None)

    def bestaetigung(self, fach: str) -> Fachbestaetigung | None:
        return next((b for b in self.bestaetigungen if b.fach == fach), None)

    # ── Die drei Achsen ─────────────────────────────────────────────────────

    @property
    def verlage(self) -> tuple[str, ...]:
        """Die Verlage des **aktuellen** Schuljahrs; nur deren Preise werden geprüft."""
        return tuple(sorted({b.verlag or OHNE_VERLAG for b in self.buecher
                             if b.im_aktuellen_jahr}, key=str.casefold))

    @property
    def faecher(self) -> tuple[str, ...]:
        """Die Fächer der Bücher **und** die, für die eine Rücklage vorliegt.

        Der zweite Teil ist kein Sonderfall, sondern der Normalfall nach einer
        Umbenennung: verschwindet ein Fach aus IServ, soll der Wunsch der
        Fachschaft trotzdem in der Datei bleiben, statt still wegzufallen.
        """
        aus_buechern = {fach for b in self.buecher for fach in (b.faecher or (OHNE_FACH,))}
        return tuple(sorted(aus_buechern | {r.fach for r in self.ruecklagen}, key=str.casefold))

    @property
    def jahrgaenge(self) -> tuple[int, ...]:
        """Die Jahrgänge der Bücherlisten **und** die, für die etwas geplant ist.

        Eine Einführung in Jahrgang 9 ab 2028/29 steht in der Datei, bevor das
        Buch dort in einer Bücherliste auftaucht - sonst ließe sie sich nicht
        eintragen.
        """
        aus_buechern = {j for b in self.buecher for j in b.jahrgaenge}
        return tuple(sorted(aus_buechern | {z.jahrgang for z in self.planung}))

    def buecher_je_verlag(self, verlag: str) -> tuple[Buch, ...]:
        return tuple(b for b in self.buecher
                     if b.im_aktuellen_jahr and (b.verlag or OHNE_VERLAG) == verlag)

    def buecher_je_fach(self, fach: str) -> tuple[Buch, ...]:
        return tuple(b for b in self.buecher
                     if fach in (b.faecher or (OHNE_FACH,))
                     or self.ruecklage(b.isbn, fach) is not None)

    def buecher_je_jahrgang(self, jahrgang: int) -> tuple[Buch, ...]:
        return tuple(b for b in self.buecher
                     if jahrgang in b.jahrgaenge
                     or self.planungszeile(b.isbn, jahrgang) is not None)

    def herkunft(self, buch: Buch, jahrgang: int) -> str:
        """Woher die Zeile (Buch, Jahrgang) des Jahrgangsblatts stammt."""
        im_vorjahr = jahrgang in buch.jahrgaenge_vorjahr
        im_jetzt = jahrgang in buch.jahrgaenge_aktuell
        if im_vorjahr and im_jetzt:
            return BEIDE
        if im_vorjahr:
            return VORJAHR
        return AKTUELL if im_jetzt else NUR_PLANUNG


# ── Die gerechneten Status ───────────────────────────────────────────────────


def _betraege_gleich(einer: float | None, anderer: float | None) -> bool:
    """Zwei Preise auf den Cent genau vergleichen - Fließkomma sonst nirgends."""
    if einer is None or anderer is None:
        return einer is None and anderer is None
    return round(float(einer), 2) == round(float(anderer), 2)


def preis_status(buch: Buch, pruefung: Preispruefung | None) -> tuple[str, str]:
    """(Status, Klartext) der Preisprüfung eines Buchs.

    Ohne geprüften Preis ist der Status ``offen`` - auch für ein Buch, das
    erst nach der letzten Prüfrunde dazugekommen ist. Genau das ist die
    Antwort auf "bei Neueinführungen müssen die Preise erneut geprüft werden":
    niemand muss daran denken, das neue Buch steht von allein auf offen.
    """
    if pruefung is None or pruefung.preis is None:
        return PREIS_OFFEN, "Noch nicht gegen die Verlagsliste geprüft."
    if _betraege_gleich(pruefung.preis, buch.neupreis):
        return PREIS_BESTAETIGT, ""
    return PREIS_ABWEICHEND, (
        f"Geprüft wurden {_euro(pruefung.preis)}, in IServ stehen "
        f"{_euro(buch.neupreis)}."
    )


def _euro(wert: float | None) -> str:
    if wert is None:
        return "kein Preis"
    return f"{wert:.2f}".replace(".", ",") + " €"


def fach_status(
    fach: str, buecher: tuple[Buch, ...], bestaetigung: Fachbestaetigung | None,
) -> tuple[str, str]:
    """(Status, Klartext) der Fachbestätigung.

    Verglichen wird gegen die Bücher des **aktuellen** Schuljahrs: bestätigt
    wird die Liste, die gedruckt und ausgegeben wird, nicht die des Vorjahres.
    """
    aktuell = {b.isbn for b in buecher if b.im_aktuellen_jahr}
    if bestaetigung is None or not bestaetigung.kuerzel:
        return FACH_OFFEN, "Noch nicht von der Fachkonferenzleitung bestätigt."
    bestaetigt = set(bestaetigung.bestaetigte_isbns)
    if bestaetigt == aktuell:
        return FACH_BESTAETIGT, ""
    titel = {b.isbn: b.titel for b in buecher}
    neu = sorted(titel.get(isbn, isbn) for isbn in aktuell - bestaetigt)
    entfallen = sorted(titel.get(isbn, isbn) for isbn in bestaetigt - aktuell)
    teile = []
    if neu:
        teile.append("hinzugekommen: " + ", ".join(neu))
    if entfallen:
        teile.append("entfallen: " + ", ".join(entfallen))
    return FACH_VERALTET, "Seit der Bestätigung geändert - " + "; ".join(teile) + "."


def planungs_status(zeile: Planungszeile | None, schuljahr: str) -> str:
    """Der Status einer Planungszeile, gerechnet gegen das Schuljahr der Datei.

    Ohne Zeile und ohne verwertbares Schuljahr gilt das, was die Bücherliste
    sagt: das Buch ist im Einsatz. Eine unlesbare Schuljahresangabe wird nicht
    geraten - sie führt zurück auf ``im Einsatz``, und die Zelle fällt beim
    Lesen auf, weil dort etwas anderes als ein Schuljahr steht.
    """
    if zeile is None:
        return PLANUNG_IM_EINSATZ
    try:
        jetzt = schuljahr_zahl(schuljahr)
    except UngueltigesSchuljahr:
        return PLANUNG_IM_EINSATZ

    def jahr(angabe: str) -> int | None:
        try:
            return schuljahr_zahl(angabe)
        except UngueltigesSchuljahr:
            return None

    ende = jahr(zeile.ausgemustert_nach)
    if ende is not None:
        return PLANUNG_AUSGEMUSTERT if ende < jetzt else PLANUNG_LAEUFT_AUS
    beginn = jahr(zeile.eingefuehrt_ab)
    if beginn is not None and beginn > jetzt:
        return PLANUNG_GEPLANT
    return PLANUNG_IM_EINSATZ
