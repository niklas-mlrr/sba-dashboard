"""Die Begriffe der Buchplanung - ohne Netz, ohne Excel, ohne HTTP.

Drei Dinge werden über ein Schuljahr hinweg festgehalten, und jedes hat seinen
eigenen Schlüssel - genau den seines Blatts in der Arbeitsmappe:

* **Bemerkung zum Buch** - ein Freitext je Buch. Schlüssel ist die ISBN; jedes
  Buch hat genau eine Zeile auf dem Blatt ``Buchreihen``. Preise werden hier
  nicht bestätigt: der Preis gilt, wie er in IServ steht.
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
eingetragenen Werten gerechnet (:func:`fach_status`,
:func:`planungs_status`). Ein gespeicherter Status könnte den Werten
widersprechen, aus denen er stammt - und niemand wüsste, welcher der beiden
recht hat.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

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

# Die Felder einer Buchreihe, die sich im Planungsmenü korrigieren lassen -
# Name hier -> Name in IServ (``series_data``). Die ISBN gehört nicht dazu:
# sie ist der Schlüssel des Buchs und steht im Menü nur zum Lesen.
#
# ``leihbar`` ist in IServ kein Feld der Buchreihe, sondern des Eintrags einer
# Bücherliste (``borrowable``, neben ``series_data``). Korrigiert wird es
# trotzdem wie die anderen - ``korrigiere_eintrag`` in
# ``buecherlisten/core/daten.py`` legt es an die richtige Stelle.
ISERV_FELD: dict[str, str] = {
    "titel": "title", "verlag": "publisher", "neupreis": "price", "leihgebuehr": "fee",
    "leihbar": "borrowable",
}

# Die Legende, die im Blatt "Info" steht: Status → was er bedeutet. Sie steht
# in der Datei, weil die Datei ohne das Dashboard lesbar sein soll.
LEGENDE: tuple[tuple[str, str], ...] = (
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
    # Paare, die nur im Vorjahr vorkamen. Kein Dateiinhalt: der Abgleich macht
    # daraus Planungszeilen mit "Ausmusterung nach" = Vorjahr.
    ausgemustert: tuple[tuple[str, int], ...] = ()
    # Die im Planungsmenü korrigierten Felder, je Feld mit dem Wert, den IServ
    # nennt: (("titel", "Deutschbuch 5"), ("neupreis", 22.5)). ``titel``,
    # ``verlag``, ``neupreis`` und ``leihgebuehr`` oben tragen dann den
    # korrigierten Wert. In der Datei steht der IServ-Wert als Kommentar an
    # der Zelle - so erkennt der nächste Abgleich die Korrektur wieder.
    iserv: tuple[tuple[str, object], ...] = ()
    # Im Dashboard von Hand angelegt, nicht aus IServ: ein Buch, das an der
    # Schule erst eingeführt wird. Titel, Verlag und Preise sind dann keine
    # Korrektur, sondern die einzige Quelle. Der Abgleich behält das Buch,
    # solange es eine Planungszeile hat, und übergibt es an IServ, sobald die
    # ISBN dort auftaucht.
    von_hand: bool = False

    @property
    def korrigiert(self) -> dict[str, object]:
        """Korrigiertes Feld -> Wert in IServ."""
        return dict(self.iserv)

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
class Buchbemerkung:
    """Der Freitext zu einem Buch - die Spalte ``Bemerkung`` auf ``Buchreihen``."""

    isbn: str
    bemerkung: str = ""

    @property
    def leer(self) -> bool:
        return not self.bemerkung


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
    bemerkungen: tuple[Buchbemerkung, ...] = ()
    planung: tuple[Planungszeile, ...] = ()
    ruecklagen: tuple[Ruecklage, ...] = ()
    warnungen: tuple[str, ...] = field(default_factory=tuple)

    # ── Nachschlagen ────────────────────────────────────────────────────────

    def buch(self, isbn: str) -> Buch | None:
        return next((b for b in self.buecher if b.isbn == isbn), None)

    def korrekturen_fuer_iserv(self) -> dict[str, dict[str, object]]:
        """Die korrigierten Felder je ISBN, in den Feldnamen von IServ (``series_data``).

        So nimmt sie ``buecherlisten.core.daten.wende_korrekturen_an`` entgegen:
        der Kern der Bücherlisten kennt diese Datei nicht und soll es auch nicht.
        """
        return {
            buch.isbn: {ISERV_FELD[feld]: getattr(buch, feld) for feld in buch.korrigiert}
            for buch in self.buecher if buch.korrigiert
        }

    def bemerkung(self, isbn: str) -> Buchbemerkung | None:
        return next((b for b in self.bemerkungen if b.isbn == isbn), None)

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
    if ende is not None and ende < jetzt:
        return PLANUNG_AUSGEMUSTERT
    # Vor "läuft aus": ein Buch, das erst später kommt, ist jetzt nicht im
    # Regal - auch wenn schon feststeht, wann es wieder geht.
    beginn = jahr(zeile.eingefuehrt_ab)
    if beginn is not None and beginn > jetzt:
        return PLANUNG_GEPLANT
    return PLANUNG_LAEUFT_AUS if ende is not None else PLANUNG_IM_EINSATZ


def planungs_zusatz(zeile: Planungszeile | None, schuljahr: str) -> str:
    """Was in der Bücherliste in Klammern hinter dem Jahrgang steht.

    „ab …“, solange das Buch dort erst später eingeführt wird, „bis …“, wenn
    es ausläuft oder schon ausgemustert ist. Wird es im selben Schuljahr
    eingeführt und ausgemustert, steht nur dieses Schuljahr da - „ab 2028/2029“
    oder „bis 2028/2029“ allein wäre dann jeweils nur die halbe Wahrheit. Ist
    dieses eine Jahr das laufende Schuljahr, bleibt es bei „bis …“: das Buch
    ist jetzt im Regal, und wichtig ist nur noch, dass es danach geht.
    """
    if zeile is None:
        return ""
    status = planungs_status(zeile, schuljahr)
    try:
        ende: int | None = schuljahr_zahl(zeile.ausgemustert_nach)
        einjaehrig = schuljahr_zahl(zeile.eingefuehrt_ab) == ende
    except UngueltigesSchuljahr:
        ende, einjaehrig = None, False
    if status == PLANUNG_GEPLANT:
        return zeile.ausgemustert_nach if einjaehrig else f"ab {zeile.eingefuehrt_ab}"
    if status not in (PLANUNG_LAEUFT_AUS, PLANUNG_AUSGEMUSTERT):
        return ""
    if einjaehrig and ende != schuljahr_zahl(schuljahr):
        return zeile.ausgemustert_nach
    return f"bis {zeile.ausgemustert_nach}"


# Die beiden Status, bei denen das Buch in **diesem** Schuljahr im Regal steht.
# "läuft aus" gehört dazu: ausgemustert wird nach dem angegebenen Schuljahr,
# also ist es dieses Jahr noch da.
_ANWESEND = frozenset({PLANUNG_IM_EINSATZ, PLANUNG_LAEUFT_AUS})


def wirkt_im_schuljahr(zeile: Planungszeile | None, schuljahr: str) -> bool:
    """Steht das Buch in diesem Schuljahr in diesem Fach und Jahrgang im Regal?

    Das ist die Frage, an der die Bestätigung der Fachkonferenzleitung hängt:
    eine Änderung, die nur ein künftiges Schuljahr betrifft ("wird nach
    2029/2030 ausgemustert"), ändert nichts an der Liste, die bestätigt wurde -
    eine, die das laufende Schuljahr betrifft, schon. Welche der beiden
    vorliegt, entscheidet :func:`setze_buchplanung`
    (``buecherlisten/planung/abgleich.py``) mit genau dieser Funktion.
    """
    return planungs_status(zeile, schuljahr) in _ANWESEND


def endet_mit_vorjahr(zeile: Planungszeile | None, schuljahr: str) -> bool:
    """Wurde diese Zeile genau nach dem Vorjahr ausgemustert, also zu diesem Schuljahr?"""
    if zeile is None:
        return False
    try:
        return schuljahr_zahl(zeile.ausgemustert_nach) == schuljahr_zahl(schuljahr) - 1
    except UngueltigesSchuljahr:
        return False


def zum_schuljahr_ausgemustert(stand: Buchplanung, buch: Buch, fach: str) -> bool:
    """Ist das Buch in diesem Fach zu diesem Schuljahr ausgemustert - in keinem
    Jahrgang des Fachs mehr, und das zuletzt mit dem Vorjahr?

    Nur dann steht es auf der Fach-Seite allein unter „Ausmusterungen zu diesem
    Schuljahr“, egal ob es in einem anderen Fach weiterläuft. Läuft es im selben
    Fach in einem anderen Jahrgang weiter oder ist dort noch geplant, steht es
    in der normalen Liste, mit „(bis …)“ hinter dem auslaufenden Jahrgang.
    """
    zeilen = [stand.planungszeile(buch.isbn, f, jahrgang)
              for f, jahrgang in stand.zeilen_des_buchs(buch) if f == fach]
    return bool(zeilen) \
        and all(planungs_status(z, stand.schuljahr) == PLANUNG_AUSGEMUSTERT for z in zeilen) \
        and any(endet_mit_vorjahr(z, stand.schuljahr) for z in zeilen)
