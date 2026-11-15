"""Die Begriffe der Mehrjahresbände-Übersicht - ohne Netz, ohne Excel, ohne HTTP.

Zwei Gruppen von Dataclasses stehen hier:

* **Eingabe** (:class:`Buchvorkommen`, :class:`Jahrgangsliste`,
  :class:`Schuljahr`) - das, was von einem Schuljahr in IServ gebraucht wird,
  und sonst nichts. Bewusst nicht ``app.buecherlisten.Buecherlisten``: dieses
  Paket liegt neben ``app/`` und darf nicht davon abhängen. Gefüllt wird es von
  :mod:`mehrjahresbaende.core.laden`.
* **Ergebnis** (:class:`Zelle`, :class:`Jahrgangszeile`, :class:`Spalte`,
  :class:`Sonderfall`, :class:`Uebersicht`) - genau das, was in der Exceldatei
  und auf der Seite steht.

Die vier festen Marken sind die der bisherigen, von Hand gepflegten Datei; ihr
Wortlaut in der Legende ist übernommen und nicht neu formuliert, damit die
erzeugte Datei neben der alten liegen kann, ohne dass jemand zweimal lesen muss.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# ── Eingabe ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Buchvorkommen:
    """Ein Buch, wie es in genau einer Jahrgangs-Bücherliste steht."""

    isbn: str
    titel: str
    faecher: tuple[str, ...]
    leihbar: bool


@dataclass(frozen=True)
class Jahrgangsliste:
    """Die Bücherliste eines Jahrgangs samt ihrer Leihmodalität."""

    jahrgang: int
    paket: bool
    buecher: tuple[Buchvorkommen, ...]

    @property
    def leihbare(self) -> tuple[Buchvorkommen, ...]:
        return tuple(buch for buch in self.buecher if buch.leihbar)


@dataclass(frozen=True)
class Schuljahr:
    """Alle Jahrgangslisten eines Schuljahrs. ``kennung`` ist die IServ-ID."""

    kennung: str
    name: str
    listen: tuple[Jahrgangsliste, ...]

    def liste(self, jahrgang: int) -> Jahrgangsliste | None:
        return next((liste for liste in self.listen if liste.jahrgang == jahrgang), None)


# ── Ergebnis ─────────────────────────────────────────────────────────────────

ABGEBEN = "abgeben"
BEHALTEN = "behalten"
AUSGEMUSTERT = "ausgemustert"

MARKE_ABGEBEN = "X"
MARKE_BEHALTEN = ""
MARKE_KEIN_BUCH = "---"
MARKE_AUSGEMUSTERT = "B"

# Reihenfolge = Reihenfolge in der Legende.
FESTE_LEGENDE: tuple[tuple[str, str], ...] = (
    (MARKE_ABGEBEN, "muss abgegeben werden"),
    (MARKE_BEHALTEN,
     "ist bei erneuter Teilnahme an der Schulbuchausleihe im nächsten Schuljahr "
     "nicht abzugegeben"),
    (MARKE_KEIN_BUCH,
     "hat diesen Unterricht noch nicht, bzw. kein (physisches)/(ausleihbares) Buch "
     "in diesem Fach"),
    (MARKE_AUSGEMUSTERT,
     "darf das Buch behalten & muss es nicht abgeben, da er einer der letzten "
     "Jahrgänge mit diesem Buch ist"),
)

FESTE_MARKEN: tuple[str, ...] = tuple(marke for marke, _ in FESTE_LEGENDE)

# Die Buchstaben für die Sonderfälle: alles außer B und X, die schon vergeben
# sind. Reicht für 24 verschiedene Fälle - kommt mehr zusammen, ist die Datei
# ohnehin nicht mehr die richtige Darstellung.
SONDER_BUCHSTABEN = tuple(
    buchstabe for buchstabe in "ACDEFGHIJKLMNOPQRSTUVWYZ"
)

OHNE_AUFGABENFELD = "(ohne Aufgabenfeld)"


@dataclass(frozen=True)
class Buchausgang:
    """Ein leihbares Buch des Vorjahres und was damit geschieht."""

    isbn: str
    titel: str
    ausgang: str  # ABGEBEN | BEHALTEN | AUSGEMUSTERT


@dataclass(frozen=True)
class Spalte:
    fach: str
    aufgabenfeld: str


@dataclass(frozen=True)
class Zelle:
    """Eine Zelle der Matrix: die Marke und die Bücher, aus denen sie stammt."""

    fach: str
    marke: str
    buecher: tuple[Buchausgang, ...] = ()


@dataclass(frozen=True)
class Jahrgangszeile:
    """Eine Zeile: entweder Marken je Fach **oder** ein durchgehender Hinweis.

    Der Hinweis ist der Fall der individuellen Ausleihe; in der Datei steht er
    als eine über alle Fachspalten verbundene Zelle, so wie ihn die von Hand
    gepflegte Fassung für Jahrgang 12 hatte.
    """

    jahrgang: int
    zellen: tuple[Zelle, ...] = ()
    hinweis: str = ""

    @property
    def name(self) -> str:
        return f"Jahrgang {self.jahrgang}"

    def zelle(self, fach: str) -> Zelle | None:
        return next((z for z in self.zellen if z.fach == fach), None)


@dataclass(frozen=True)
class Sonderfall:
    """Ein Buchstabe für ein Fach mit mehreren, unterschiedlich endenden Büchern."""

    buchstabe: str
    text: str

    @property
    def legende(self) -> str:
        return f"{self.buchstabe} = {self.text}"


@dataclass(frozen=True)
class Uebersicht:
    """Die ganze Übersicht - das, was in der Datei steht und auf der Seite."""

    spalten: tuple[Spalte, ...]
    zeilen: tuple[Jahrgangszeile, ...]
    sonderfaelle: tuple[Sonderfall, ...] = ()
    schuljahr_alt: str = ""
    schuljahr_neu: str = ""
    erzeugt: date | None = None
    warnungen: tuple[str, ...] = field(default_factory=tuple)

    @property
    def faecher(self) -> tuple[str, ...]:
        return tuple(spalte.fach for spalte in self.spalten)

    @property
    def erlaubte_marken(self) -> tuple[str, ...]:
        """Was in einer Zelle stehen darf - die festen Marken plus die Sonderfälle."""
        return FESTE_MARKEN + tuple(fall.buchstabe for fall in self.sonderfaelle)

    @property
    def legende(self) -> tuple[str, ...]:
        """Die Legendenzeilen in Dateireihenfolge, Sonderfälle zuletzt."""
        fest = [
            f"{marke if marke else '(frei)'} = {text}" for marke, text in FESTE_LEGENDE
        ]
        return tuple(fest + [fall.legende for fall in self.sonderfaelle])

    @property
    def herkunft(self) -> str:
        """Die letzte Zeile der Datei: woher die Übersicht stammt."""
        if not (self.schuljahr_alt and self.schuljahr_neu):
            return ""
        wann = self.erzeugt.strftime("%d.%m.%Y") if self.erzeugt else "?"
        return (f"Erzeugt am {wann} aus den Bücherlisten "
                f"{self.schuljahr_alt} → {self.schuljahr_neu}")

    def zeile(self, jahrgang: int) -> Jahrgangszeile | None:
        return next((z for z in self.zeilen if z.jahrgang == jahrgang), None)
