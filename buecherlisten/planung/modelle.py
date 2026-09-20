"""Die Begriffe der Buchplanung - ohne Netz, ohne Excel, ohne HTTP.

Drei Dinge werden über ein Schuljahr hinweg festgehalten, und jedes hat seinen
eigenen Schlüssel - genau den seines Blatts in der Arbeitsmappe:

* **Preisprüfung** - der Beauftragte für die Schulbuchausleihe vergleicht die
  Preise in IServ mit den Verlagslisten. Schlüssel ist die ISBN; jedes Buch hat
  genau einen Verlag und genau eine Zeile auf dem Blatt ``Buchreihen``.
* **Planung und Bestätigung** - ab bzw. bis wann ein Buch in **einem Fach und
  einem Jahrgang** geführt wird, und wer das bestätigt hat. Schlüssel ist
  (ISBN, Fach, Jahrgang). Eine gestaffelte Einführung eines Mehrjahresbands
  (Jg. 7 ab 2027/28, Jg. 8 ab 2028/29) sind damit zwei Zeilen statt einer
  Bemerkung im Freitext, und die Fachkonferenzleitung bestätigt ihre eigenen
  Zeilen, nicht die eines anderen Fachs.
* **Rücklage** - eine Fachschaft möchte von einem Buch Exemplare behalten,
  statt sie wegzuwerfen. Schlüssel ist (ISBN, Fach): ein Buch kann zu mehreren
  Fächern gehören, und der Wunsch gehört der Fachschaft.

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

# ── Status der Preisprüfung ──────────────────────────────────────────────────

PREIS_OFFEN = "offen"
PREIS_BESTAETIGT = "bestätigt"
PREIS_ABWEICHEND = "abweichend"

# ── Status eines Fachs ───────────────────────────────────────────────────────
#
# Bestätigt wird je Zeile (Buch, Fach, Jahrgang); der Status des ganzen Fachs
# ist die Zusammenfassung seiner Zeilen. Ein Fach kann deshalb nicht
# "veralten": kommt ein Buch dazu, bringt es eine Zeile ohne Kürzel mit, und
# das Fach fällt von allein auf "teilweise" zurück.

FACH_OFFEN = "offen"
FACH_TEILWEISE = "teilweise"
FACH_BESTAETIGT = "bestätigt"

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
    (FACH_TEILWEISE,
     "einige Zeilen dieses Fachs tragen noch kein Kürzel der Fachkonferenzleitung"),
    (FACH_BESTAETIGT, "die Fachkonferenzleitung hat alle Zeilen dieses Fachs bestätigt"),
    (PLANUNG_GEPLANT, "wird hier erst in einem späteren Schuljahr eingeführt"),
    (PLANUNG_IM_EINSATZ, "wird hier geführt"),
    (PLANUNG_LAEUFT_AUS, "wird nach dem angegebenen Schuljahr ausgemustert"),
    (PLANUNG_AUSGEMUSTERT, "ist hier bereits ausgemustert"),
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
    ein Tippfehler in der Spalte "Einführung" darf nicht dazu führen, dass ein
    Buch als längst eingeführt gilt.
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
    """Ein Titel, wie ihn die Bücherlisten zeigen - eine Zeile auf ``Buchreihen``.

    ``kombinationen`` sind die (Fach, Jahrgang)-Paare, in denen das Buch
    tatsächlich vorkommt, und **nicht** das Kreuzprodukt aus Fächern und
    Jahrgängen: ein Band, der in Jahrgang 7 zum Fach Mathematik und in
    Jahrgang 8 zum Fach Informatik gehört, hat zwei Paare, nicht vier. Genau
    diese Paare sind die Zeilen des Blatts ``Fächer & Jahrgang``.
    """

    isbn: str
    titel: str
    verlag: str
    kombinationen: tuple[tuple[str, int], ...] = ()
    leihbar: bool = False
    neupreis: float | None = None
    leihgebuehr: float | None = None

    @property
    def faecher(self) -> tuple[str, ...]:
        return tuple(sorted({fach for fach, _ in self.kombinationen}, key=str.casefold))

    @property
    def jahrgaenge(self) -> tuple[int, ...]:
        return tuple(sorted({jahrgang for _, jahrgang in self.kombinationen}))

    @property
    def fach_anzeige(self) -> str:
        return ", ".join(self.faecher) if self.faecher else OHNE_FACH

    @property
    def jahrgang_anzeige(self) -> str:
        return ", ".join(str(jahrgang) for jahrgang in self.jahrgaenge)

    def jahrgaenge_im_fach(self, fach: str) -> tuple[int, ...]:
        return tuple(sorted(jahrgang for eigenes, jahrgang in self.kombinationen
                            if eigenes == fach))


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
class Planungszeile:
    """Ein Buch in **einem** Fach und **einem** Jahrgang.

    ``kuerzel`` und ``datum`` sind die Bestätigung der Fachkonferenzleitung für
    genau diese Zeile. Bis 2026-09-20 stand die Bestätigung je Fach auf einem
    eigenen Blatt und führte den bestätigten Stand als ISBN-Liste mit; seither
    ist sie dort, wo das Bestätigte steht, und eine neu dazugekommene Zeile ist
    von allein unbestätigt.
    """

    isbn: str
    fach: str
    jahrgang: int
    eingefuehrt_ab: str = ""
    ausgemustert_nach: str = ""
    kuerzel: str = ""
    datum: date | None = None
    bemerkung: str = ""

    @property
    def leer(self) -> bool:
        return not any((self.eingefuehrt_ab, self.ausgemustert_nach,
                        self.kuerzel, self.bemerkung)) and self.datum is None

    @property
    def bestaetigt(self) -> bool:
        return bool(self.kuerzel)


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


# ── Der ganze Stand ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Buchplanung:
    """Alles, was in der Arbeitsmappe steht."""

    schuljahr: str = ""
    vorjahr: str = ""
    stand: date | None = None
    buecher: tuple[Buch, ...] = ()
    preise: tuple[Preispruefung, ...] = ()
    planung: tuple[Planungszeile, ...] = ()
    ruecklagen: tuple[Ruecklage, ...] = ()
    warnungen: tuple[str, ...] = field(default_factory=tuple)

    # ── Nachschlagen ────────────────────────────────────────────────────────

    def buch(self, isbn: str) -> Buch | None:
        return next((b for b in self.buecher if b.isbn == isbn), None)

    def pruefung(self, isbn: str) -> Preispruefung | None:
        return next((p for p in self.preise if p.isbn == isbn), None)

    def planungszeile(self, isbn: str, fach: str, jahrgang: int) -> Planungszeile | None:
        return next((z for z in self.planung if z.isbn == isbn
                     and z.fach == fach and z.jahrgang == jahrgang), None)

    def planung_des_fachs(self, fach: str) -> tuple[Planungszeile, ...]:
        return tuple(z for z in self.planung if z.fach == fach)

    def ruecklage(self, isbn: str, fach: str) -> Ruecklage | None:
        return next((r for r in self.ruecklagen if r.isbn == isbn and r.fach == fach), None)

    # ── Die Achsen ──────────────────────────────────────────────────────────

    @property
    def verlage(self) -> tuple[str, ...]:
        return tuple(sorted({b.verlag or OHNE_VERLAG for b in self.buecher}, key=str.casefold))

    @property
    def faecher(self) -> tuple[str, ...]:
        """Die Fächer der Bücher **und** die, für die eine Rücklage vorliegt.

        Der zweite Teil ist kein Sonderfall, sondern der Normalfall nach einer
        Umbenennung: verschwindet ein Fach aus IServ, soll der Wunsch der
        Fachschaft trotzdem in der Datei bleiben, statt still wegzufallen.
        """
        aus_buechern = {fach for b in self.buecher for fach in (b.faecher or (OHNE_FACH,))}
        aus_planung = {z.fach for z in self.planung}
        return tuple(sorted(aus_buechern | aus_planung | {r.fach for r in self.ruecklagen},
                            key=str.casefold))

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
        return tuple(b for b in self.buecher if (b.verlag or OHNE_VERLAG) == verlag)

    def buecher_je_fach(self, fach: str) -> tuple[Buch, ...]:
        return tuple(b for b in self.buecher
                     if fach in (b.faecher or (OHNE_FACH,))
                     or self.ruecklage(b.isbn, fach) is not None
                     or any(z.isbn == b.isbn and z.fach == fach for z in self.planung))

    def buecher_je_jahrgang(self, jahrgang: int) -> tuple[Buch, ...]:
        return tuple(b for b in self.buecher
                     if jahrgang in b.jahrgaenge
                     or any(z.isbn == b.isbn and z.jahrgang == jahrgang for z in self.planung))

    def zeilen_des_buchs(self, buch: Buch) -> tuple[tuple[str, int], ...]:
        """Die (Fach, Jahrgang)-Paare eines Buchs: aus IServ **und** aus der Planung.

        Die zweite Hälfte ist der Grund, aus dem es diese Funktion gibt: „wird
        ab 2028/29 auch in Jahrgang 9 eingeführt" ist eine Zeile, die noch in
        keiner Bücherliste steht.
        """
        aus_planung = {(z.fach, z.jahrgang) for z in self.planung if z.isbn == buch.isbn}
        paare = set(buch.kombinationen) | aus_planung
        if not paare:
            return ()
        return tuple(sorted(paare, key=lambda paar: (paar[0].casefold(), paar[1])))


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
    stand: Buchplanung, fach: str,
) -> tuple[str, str]:
    """(Status, Klartext) der Freigabe eines Fachs, aus seinen Zeilen gerechnet.

    Gezählt werden die Zeilen, die dieses Fach heute hat - jede von ihnen ist
    ein Buch in einem Jahrgang. ``bestätigt`` heißt: jede trägt ein Kürzel.
    Kommt ein Buch dazu, ist seine Zeile unbestätigt, und das Fach fällt von
    allein zurück; einen Zustand "veraltet" braucht es dafür nicht.
    """
    offen: list[str] = []
    gesamt = 0
    for buch in stand.buecher_je_fach(fach):
        for eigenes, jahrgang in stand.zeilen_des_buchs(buch):
            if eigenes != fach:
                continue
            gesamt += 1
            zeile = stand.planungszeile(buch.isbn, fach, jahrgang)
            if zeile is None or not zeile.bestaetigt:
                offen.append(f"{buch.titel} (Jg. {jahrgang})")
    if gesamt == 0:
        return FACH_OFFEN, "Zu diesem Fach steht kein Buch in der Datei."
    if not offen:
        return FACH_BESTAETIGT, ""
    if len(offen) == gesamt:
        return FACH_OFFEN, "Noch nicht von der Fachkonferenzleitung bestätigt."
    namen = ", ".join(sorted(offen)[:5])
    mehr = "" if len(offen) <= 5 else f" und {len(offen) - 5} weitere"
    return FACH_TEILWEISE, f"Noch ohne Kürzel: {namen}{mehr}."


def fach_bestaetigung(stand: Buchplanung, fach: str) -> tuple[str, date | None]:
    """Kürzel und Datum des Fachs, sofern seine bestätigten Zeilen darin einig sind.

    Bestätigt wird je Zeile, angezeigt wird das Feld einmal über der Liste.
    Tragen die Zeilen verschiedene Kürzel - zwei Fachkonferenzen, zwei Termine -,
    kommt nichts zurück: ein herausgegriffenes davon wäre eine Behauptung über
    die anderen.
    """
    zeilen = [zeile for zeile in stand.planung_des_fachs(fach) if zeile.bestaetigt]
    kuerzel = {zeile.kuerzel for zeile in zeilen}
    daten = {zeile.datum for zeile in zeilen}
    return (
        next(iter(kuerzel)) if len(kuerzel) == 1 else "",
        next(iter(daten)) if len(daten) == 1 else None,
    )


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
