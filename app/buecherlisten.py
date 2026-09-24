"""Die Bücherlisten aus IServ, neu geordnet nach Verlag, Fach und Jahrgang.

IServ zeigt Bücherlisten nur je Jahrgang. Wer wissen will, welche Bücher eines
Verlags oder eines Fachs überhaupt im Umlauf sind, muss dort neun Listen
nebeneinanderlegen. Dieses Modul holt alle Listen des aktuellen Schuljahrs
einmal und stellt sie um - ohne FastAPI, damit es sich mit einem Fake-Client
prüfen lässt.

Das Zusammenführen folgt ``collect_entries`` in
``buecherlisten/generate_booklists.py``: ein Mehrjahresband
(z. B. "Elemente Chemie 5/6") steht in mehreren Jahrgangslisten und wird je
Gruppe **ein** Eintrag mit allen Jahrgängen, in denen er tatsächlich vorkommt -
nicht mit ``series_data.gradesFlat``, das ein Serienattribut ist und von den
Listen abweichen kann.

Nachgebaut statt importiert, weil ``buecherlisten/`` damals nicht ins venv des
Dashboards installiert wurde. Dieser Grund ist mit der Zusammenlegung am
2026-09-18 entfallen: das Paket liegt jetzt im selben Baum und wird von
``app/api/buecherliste.py`` schon importiert. Die Doppelung ist damit
auflösbar, aber nicht automatisch falsch - sie zusammenzulegen ist eine
Änderung am Verhalten zweier Seiten und steht als eigener Punkt in
``docs/roadmap.md``, nicht als Nebenwirkung eines Ordnerumzugs.

Geladen wird live bei jedem Seitenaufruf (Entscheidung 2026-09-17): die Seiten
sollen den Stand in IServ zeigen, nicht den des letzten Abrufs.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol

import isbnlib

from buecherlisten.core.daten import Korrekturen, korrigiere_eintrag

OHNE_FACH = "(ohne Fach)"
OHNE_VERLAG = "(ohne Verlag)"
# So heißt der Pflichtbereich einer Liste in der API; IServ zeigt ihn als "Grundpaket".
_GRUNDBEREICH = "default"


class _Schuljahre(Protocol):
    def get_current(self) -> dict: ...
    def get_booklists(self, schoolyear_id: str) -> list[dict]: ...
    def get_booklist(self, schoolyear_id: str, booklist_id: int) -> dict: ...


class BuecherlistenClient(Protocol):
    """Was von ``ausleihe.AusleiheClient`` hier gebraucht wird."""

    @property
    def schoolyears(self) -> _Schuljahre: ...


@dataclass(frozen=True)
class Buch:
    """Ein Titel, wie er in einer Gruppe (Fach, Verlag, Wahlbereich) erscheint."""

    isbn: str
    titel: str
    faecher: tuple[str, ...]
    verlag: str
    neupreis: float | None
    leihgebuehr: float | None
    leihbar: bool
    jahrgaenge: tuple[int, ...]
    # Ist an der Buchreihe etwas korrigiert (Buchplanung, Blatt "Buchreihen"),
    # stehen oben die korrigierten Werte und hier die IServ-Werte der
    # korrigierten Felder. Das Planungsmenü zeigt sie als „in IServ: …“.
    iserv: tuple[tuple[str, Any], ...] = ()

    @property
    def isbn_anzeige(self) -> str:
        return isbnlib.mask(self.isbn) or self.isbn

    @property
    def fach_anzeige(self) -> str:
        return ", ".join(self.faecher)

    @property
    def jahrgang_anzeige(self) -> str:
        return ", ".join(str(j) for j in self.jahrgaenge)


@dataclass(frozen=True)
class Option:
    """Eine Wahlmöglichkeit innerhalb eines Bereichs, z. B. "Religion"."""

    titel: str
    buecher: tuple[Buch, ...]


@dataclass(frozen=True)
class Bereich:
    """Grundpaket oder Wahlbereich einer Jahrgangsliste."""

    titel: str
    grundpaket: bool
    optionen: tuple[Option, ...]


@dataclass(frozen=True)
class Liste:
    """Eine Jahrgangs-Bücherliste mit den Kopfdaten der IServ-Übersicht."""

    id: int
    titel: str
    jahrgang: int | None
    paket: bool
    festpreis: float | None
    anmeldung_moeglich: bool
    beginn: date | None
    ende: date | None
    zahlungsfrist: date | None
    bank: str
    bereiche: tuple[Bereich, ...] = field(default=())

    @property
    def leihmodalitaet(self) -> str:
        return "Paket" if self.paket else "Individuell"

    @property
    def grundpaket(self) -> Bereich | None:
        return next((b for b in self.bereiche if b.grundpaket), None)

    @property
    def wahlbereiche(self) -> tuple[Bereich, ...]:
        return tuple(b for b in self.bereiche if not b.grundpaket)

    @property
    def alle_buecher(self) -> tuple[Buch, ...]:
        """Grundpaket, dann jede Wahlmöglichkeit - die Reihenfolge der Gesamtansicht."""
        bereiche = ((self.grundpaket,) if self.grundpaket else ()) + self.wahlbereiche
        return tuple(buch for bereich in bereiche for option in bereich.optionen
                     for buch in option.buecher)


@dataclass(frozen=True)
class Gruppe:
    """Eine Zeile der Übersicht nach Fach oder Verlag."""

    name: str
    buecher: tuple[Buch, ...]


@dataclass(frozen=True)
class Buecherlisten:
    """Die Listen eines Schuljahrs, mit **beiden** Bezeichnungen.

    ``schuljahr`` ist der Anzeigename ("Schuljahr 26/27"), ``kennung`` die ID,
    mit der IServ das Jahr adressiert ("2026/2027"). Die beiden sind nicht
    austauschbar: die Kennung ist der Schlüssel der Buchplanungs-Datei und
    lässt sich mit anderen Schuljahren vergleichen, der Name nicht.
    """

    schuljahr: str
    listen: tuple[Liste, ...]
    kennung: str = ""

    def liste_fuer_jahrgang(self, jahrgang: int) -> Liste | None:
        return next((liste for liste in self.listen if liste.jahrgang == jahrgang), None)


# ── Laden ────────────────────────────────────────────────────────────────────

def lade_buecherlisten(
    client: BuecherlistenClient, *, heute: date | None = None,
    korrekturen: Callable[[str], Korrekturen | None] | None = None,
) -> Buecherlisten:
    """Alle Listen des aktuellen Schuljahrs samt Büchern, sortiert nach Jahrgang.

    ``korrekturen`` liefert zur Kennung des Schuljahrs die korrigierten
    Angaben der Buchreihen (aus der Buchplanung). Eine Funktion statt der
    Werte, weil erst hier feststeht, welches Schuljahr das laufende ist.
    """
    heute = heute or date.today()
    schuljahr = client.schoolyears.get_current()
    schuljahr_id = schuljahr["id"]
    korrigiert = korrekturen(str(schuljahr_id)) if korrekturen else None
    listen = []
    for kopf in client.schoolyears.get_booklists(schuljahr_id):
        detail = client.schoolyears.get_booklist(schuljahr_id, kopf["id"])
        listen.append(_liste(kopf, detail, heute, korrigiert))
    listen.sort(key=lambda liste: (liste.jahrgang is None, liste.jahrgang or 0, liste.titel))
    return Buecherlisten(schuljahr=schuljahr.get("name") or schuljahr_id,
                         listen=tuple(listen), kennung=str(schuljahr_id))


def _datum(roh: Any) -> date | None:
    if not roh:
        return None
    try:
        return datetime.fromisoformat(str(roh).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _liste(kopf: dict, detail: dict, heute: date,
           korrekturen: Korrekturen | None = None) -> Liste:
    jahrgang = kopf.get("grade")
    beginn = _datum(kopf.get("e_begin") or kopf.get("enrollment_begin"))
    ende = _datum(kopf.get("e_end") or kopf.get("enrollment_end"))
    freigeschaltet = bool((kopf.get("Schoolyear") or {}).get("enrollment_enabled"))
    moeglich = (freigeschaltet and beginn is not None and ende is not None
                and beginn <= heute <= ende)
    bereiche = []
    for abschnitt in sorted(detail.get("sections") or [], key=lambda s: s.get("position") or 0):
        optionen = []
        for option in abschnitt.get("options") or []:
            buecher = [_buch(item, jahrgang, korrekturen) for item in option.get("items") or []]
            optionen.append(Option(
                titel=option.get("title") or "",
                buecher=tuple(b for b in buecher if b is not None),
            ))
        titel = abschnitt.get("title") or _GRUNDBEREICH
        bereiche.append(Bereich(
            titel="Grundpaket" if titel == _GRUNDBEREICH else titel,
            grundpaket=titel == _GRUNDBEREICH,
            optionen=tuple(optionen),
        ))
    return Liste(
        id=kopf["id"],
        titel=kopf.get("title") or "",
        jahrgang=jahrgang,
        paket=bool(kopf.get("package")),
        festpreis=kopf.get("package_fee"),
        anmeldung_moeglich=moeglich,
        beginn=beginn,
        ende=ende,
        zahlungsfrist=_datum(kopf.get("e_payment_deadline") or kopf.get("payment_deadline")),
        bank=(kopf.get("BankAccount") or {}).get("bank") or "",
        bereiche=tuple(bereiche),
    )


# Feldname in IServ -> Feldname hier.
_FELDER = {"title": "titel", "publisher": "verlag", "price": "neupreis", "fee": "leihgebuehr"}


def _buch(item: dict, jahrgang: int | None, korrekturen: Korrekturen | None = None) -> Buch | None:
    original = item.get("series_data") or {}
    daten = korrigiere_eintrag(item, korrekturen).get("series_data") or {}
    isbn = daten.get("isbn") or item.get("series")
    if not isbn:
        return None
    iserv = tuple(
        (_FELDER[name], original.get(name))
        for name in (korrekturen or {}).get(isbn) or {} if name in _FELDER
    )
    return Buch(
        iserv=iserv,
        isbn=isbn,
        titel=daten.get("title") or "?",
        faecher=tuple(daten.get("subjectsFlat") or ()),
        verlag=daten.get("publisher") or "",
        neupreis=daten.get("price"),
        leihgebuehr=daten.get("fee"),
        leihbar=bool(item.get("borrowable")),
        jahrgaenge=(jahrgang,) if jahrgang is not None else (),
    )


# ── Umordnen ─────────────────────────────────────────────────────────────────

def _alle_buecher(daten: Buecherlisten) -> list[Buch]:
    return [
        buch
        for liste in daten.listen
        for bereich in liste.bereiche
        for option in bereich.optionen
        for buch in option.buecher
    ]


def _gruppiere(buecher: list[Buch], schluessel: Any) -> tuple[Gruppe, ...]:
    """Fasst je (Gruppe, ISBN) zusammen und vereinigt die Jahrgänge."""
    gesammelt: dict[str, dict[str, Buch]] = {}
    for buch in buecher:
        for name in schluessel(buch):
            je_isbn = gesammelt.setdefault(name, {})
            vorhanden = je_isbn.get(buch.isbn)
            if vorhanden is None:
                je_isbn[buch.isbn] = buch
                continue
            je_isbn[buch.isbn] = Buch(
                isbn=vorhanden.isbn,
                titel=vorhanden.titel,
                faecher=vorhanden.faecher,
                verlag=vorhanden.verlag,
                neupreis=vorhanden.neupreis,
                leihgebuehr=vorhanden.leihgebuehr,
                # Leihbar, sobald es in irgendeiner Liste leihbar ist.
                leihbar=vorhanden.leihbar or buch.leihbar,
                jahrgaenge=tuple(sorted(set(vorhanden.jahrgaenge) | set(buch.jahrgaenge))),
                iserv=vorhanden.iserv,
            )
    return tuple(
        Gruppe(
            name=name,
            buecher=tuple(sorted(je_isbn.values(),
                                 key=lambda b: (b.jahrgaenge, b.titel.lower()))),
        )
        for name, je_isbn in sorted(gesammelt.items(), key=lambda e: e[0].lower())
    )


def gruppen_nach_fach(daten: Buecherlisten) -> tuple[Gruppe, ...]:
    """Eine Gruppe je Fach; ein Buch mit zwei Fächern steht in beiden."""
    return _gruppiere(_alle_buecher(daten), lambda b: b.faecher or (OHNE_FACH,))


def gruppen_nach_verlag(daten: Buecherlisten) -> tuple[Gruppe, ...]:
    return _gruppiere(_alle_buecher(daten), lambda b: (b.verlag or OHNE_VERLAG,))


def finde_gruppe(gruppen: tuple[Gruppe, ...], name: str) -> Gruppe | None:
    return next((g for g in gruppen if g.name == name), None)
