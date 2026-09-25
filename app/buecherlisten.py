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

Geladen wird live bei jedem Seitenaufruf (Entscheidung 2026-09-17). Seit
2026-09-25 zeigen die Seiten aber nicht mehr IServ, sondern den Stand der
Buchplanungs-Datei (das Soll), und IServ live dient als Vergleich: was
abweicht, wird markiert. Die Zeilen dafür baut der zweite Teil dieses Moduls
(:func:`vergleiche_mit_iserv` und folgende); welche Abweichung vorliegt,
entscheidet ``buecherlisten/planung/vergleich.py``. Ohne Datei zeigen die
Seiten IServ wie bisher.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any, Protocol

import isbnlib

from buecherlisten.core.daten import Korrekturen, korrigiere_eintrag
from buecherlisten.planung import (
    BEIDE,
    NUR_EXCEL,
    NUR_ISERV,
    PLANUNG_AUSGEMUSTERT,
    Abweichung,
    Buchplanung,
    IservBuch,
    aktive_paare,
    planungs_status,
    vergleiche,
)
from buecherlisten.planung import Buch as PlanBuch

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
    # Im Planungsmenü hinzugefügt und (noch) nicht in IServ - die Zeile kommt
    # aus der Buchplanung, nicht aus einer Bücherliste.
    von_hand: bool = False
    # Der Vergleich mit IServ, gerechnet für die Gruppe, in der die Zeile
    # steht. ``herkunft``: ``beide``; ``nur_excel`` - laut Datei gehört das Buch
    # in diese Gruppe, in IServ nicht; ``nur_iserv`` - umgekehrt. ``iserv``
    # trägt dann die abweichenden Werte aus IServ, ``paare_hier`` die
    # abweichenden (Fach, Jahrgang)-Paare dieser Gruppe und ``paare_sonst``
    # die übrigen, jeweils als Satz.
    herkunft: str = BEIDE
    paare_hier: tuple[str, ...] = ()
    paare_sonst: tuple[str, ...] = ()

    @property
    def abweichend(self) -> bool:
        return (self.herkunft != BEIDE or bool(self.iserv)
                or bool(self.paare_hier) or bool(self.paare_sonst))

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
_FELDER = {"title": "titel", "publisher": "verlag", "price": "neupreis", "fee": "leihgebuehr",
           "borrowable": "leihbar"}


def _buch(item: dict, jahrgang: int | None, korrekturen: Korrekturen | None = None) -> Buch | None:
    # "borrowable" steht am Eintrag, alles andere an der Buchreihe.
    original = {**(item.get("series_data") or {}), "borrowable": bool(item.get("borrowable"))}
    korrigiert = korrigiere_eintrag(item, korrekturen)
    daten = korrigiert.get("series_data") or {}
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
        leihbar=bool(korrigiert.get("borrowable")),
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


# ── Die Datei als Soll, IServ als Vergleich ──────────────────────────────────

Paar = tuple[str, int]


def iserv_je_isbn(daten: Buecherlisten) -> dict[str, IservBuch]:
    """Die Bücher der IServ-Listen je ISBN, mit allen (Fach, Jahrgang)-Paaren.

    ``daten`` muss **ohne** Korrekturen geladen sein: verglichen wird mit dem,
    was in IServ steht. Leihbar ist ein Buch, sobald es in einer Liste
    leihbar ist - wie in :func:`_gruppiere`.
    """
    werte: dict[str, Buch] = {}
    paare: dict[str, set[Paar]] = {}
    leihbar: dict[str, bool] = {}
    for liste in daten.listen:
        for buch in liste.alle_buecher:
            werte.setdefault(buch.isbn, buch)
            leihbar[buch.isbn] = leihbar.get(buch.isbn, False) or buch.leihbar
            if liste.jahrgang is not None:
                paare.setdefault(buch.isbn, set()).update(
                    (fach, liste.jahrgang) for fach in buch.faecher or (OHNE_FACH,))
    return {
        isbn: IservBuch(isbn=isbn, titel=buch.titel, verlag=buch.verlag,
                        neupreis=buch.neupreis, leihgebuehr=buch.leihgebuehr,
                        leihbar=leihbar[isbn], paare=frozenset(paare.get(isbn, ())))
        for isbn, buch in werte.items()
    }


@dataclass(frozen=True)
class Vergleich:
    """Die Datei, IServ und was je Buch voneinander abweicht."""

    planung: Buchplanung
    iserv: dict[str, IservBuch]
    ergebnis: dict[str, Abweichung]

    def aktiv(self, buch: PlanBuch) -> frozenset[Paar]:
        return aktive_paare(self.planung, buch)

    def nicht_ausgemustert(self, buch: PlanBuch) -> tuple[Paar, ...]:
        """Paare, die dieses Schuljahr gelten oder erst noch kommen."""
        return tuple(
            (fach, jahrgang) for fach, jahrgang in self.planung.zeilen_des_buchs(buch)
            if planungs_status(self.planung.planungszeile(buch.isbn, fach, jahrgang),
                               self.planung.schuljahr) != PLANUNG_AUSGEMUSTERT
        )

    @property
    def anzahl_abweichungen(self) -> int:
        return sum(1 for abweichung in self.ergebnis.values() if not abweichung.gleich)


def vergleiche_mit_iserv(daten: Buecherlisten, planung: Buchplanung) -> Vergleich:
    iserv = iserv_je_isbn(daten)
    return Vergleich(planung=planung, iserv=iserv, ergebnis=vergleiche(planung, iserv))


def _paare_text(paare: tuple[Paar, ...] | list[Paar]) -> str:
    """(("Physik", 7), ("Physik", 8), ("Chemie", 9)) -> "Physik Jg. 7, 8; Chemie Jg. 9"."""
    je_fach: dict[str, list[int]] = {}
    for fach, jahrgang in paare:
        je_fach.setdefault(fach, []).append(jahrgang)
    return "; ".join(f"{fach} Jg. {', '.join(str(j) for j in sorted(jgs))}"
                     for fach, jgs in je_fach.items())


def _paarsaetze(abweichung: Abweichung | None,
                hier: Callable[[Paar], bool]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Die abweichenden Paare als Sätze: (die dieser Gruppe, die übrigen)."""
    if abweichung is None or abweichung.art != BEIDE:
        return (), ()
    innen: list[str] = []
    aussen: list[str] = []
    for text, paare in (("in IServ zusätzlich", abweichung.nur_in_iserv),
                        ("fehlt in IServ", abweichung.fehlt_in_iserv)):
        drin = [paar for paar in paare if hier(paar)]
        draussen = [paar for paar in paare if not hier(paar)]
        if drin:
            innen.append(f"{text}: {_paare_text(drin)}")
        if draussen:
            aussen.append(f"{text}: {_paare_text(draussen)}")
    return tuple(innen), tuple(aussen)


def _aus_datei(v: Vergleich, buch: PlanBuch, paare: tuple[Paar, ...] | frozenset[Paar],
               hier: Callable[[Paar], bool], herkunft: str,
               jahrgaenge: tuple[int, ...] | None = None) -> Buch:
    """Eine Zeile mit den Werten der Datei und dem Vergleich dazu."""
    abweichung = v.ergebnis.get(buch.isbn)
    innen, aussen = _paarsaetze(abweichung, hier)
    return Buch(
        isbn=buch.isbn, titel=buch.titel,
        faecher=tuple(sorted({fach for fach, _ in paare}, key=str.casefold)),
        verlag="" if buch.verlag == OHNE_VERLAG else buch.verlag,
        neupreis=buch.neupreis, leihgebuehr=buch.leihgebuehr, leihbar=buch.leihbar,
        jahrgaenge=jahrgaenge if jahrgaenge is not None
        else tuple(sorted({jahrgang for _, jahrgang in paare})),
        iserv=abweichung.felder if abweichung and abweichung.art == BEIDE else (),
        von_hand=buch.von_hand, herkunft=herkunft, paare_hier=innen, paare_sonst=aussen,
    )


def _aus_iserv(ist: IservBuch, paare: tuple[Paar, ...] | frozenset[Paar]) -> Buch:
    """Eine Zeile, die nur IServ in dieser Gruppe führt - mit den Werten aus IServ."""
    return Buch(
        isbn=ist.isbn, titel=ist.titel,
        faecher=tuple(sorted({fach for fach, _ in paare}, key=str.casefold)),
        verlag=ist.verlag, neupreis=ist.neupreis, leihgebuehr=ist.leihgebuehr,
        leihbar=ist.leihbar, jahrgaenge=tuple(sorted({jahrgang for _, jahrgang in paare})),
        herkunft=NUR_ISERV,
    )


def _sortiert(zeilen: list[Buch]) -> tuple[Buch, ...]:
    # Nur geplante Bücher (noch ohne Jahrgang in diesem Schuljahr) stehen am Ende.
    return tuple(sorted(zeilen, key=lambda b: (not b.jahrgaenge, b.jahrgaenge, b.titel.lower())))


def _im_fach(fach: str) -> Callable[[Paar], bool]:
    return lambda paar: paar[0] == fach


def gruppen_nach_fach_aus_datei(v: Vergleich) -> tuple[Gruppe, ...]:
    """Eine Gruppe je Fach, aus der Datei - und je Fach die Bücher, die nur IServ dort führt.

    Aus der Datei steht in einem Fach jedes Buch, das dort dieses Schuljahr
    geführt wird **oder** erst noch eingeführt wird: die geplante Einführung
    soll man in der Liste sehen und im Planungsmenü ändern können. Gezeigt
    werden die Jahrgänge, die dieses Schuljahr gelten; „(ab …)“ hängt die
    Vorlage an (``jahrgangsspalte``).
    """
    zeilen: dict[str, dict[str, Buch]] = {}
    for buch in v.planung.buecher:
        offen = v.nicht_ausgemustert(buch)
        aktiv = v.aktiv(buch)
        ist = v.iserv.get(buch.isbn)
        abweichung = v.ergebnis.get(buch.isbn)
        for fach in {fach for fach, _ in offen}:
            in_iserv = ist is not None and any(f == fach for f, _ in ist.paare)
            hier_aktiv = any(f == fach for f, _ in aktiv)
            if hier_aktiv and not in_iserv:
                herkunft = NUR_EXCEL
            elif in_iserv and abweichung is not None and abweichung.art == NUR_ISERV:
                # Nur geplant laut Datei, in IServ aber schon auf der Liste.
                herkunft = NUR_ISERV
            else:
                herkunft = BEIDE
            zeilen.setdefault(fach, {})[buch.isbn] = _aus_datei(
                v, buch, aktiv | {paar for paar in offen if paar[0] == fach},
                _im_fach(fach), herkunft,
                jahrgaenge=tuple(sorted(j for f, j in aktiv if f == fach)),
            )
    for isbn, ist in v.iserv.items():
        for fach in {fach for fach, _ in ist.paare}:
            if isbn not in zeilen.get(fach, {}):
                zeilen.setdefault(fach, {})[isbn] = _aus_iserv(
                    ist, frozenset(paar for paar in ist.paare if paar[0] == fach))
    return tuple(Gruppe(name=name, buecher=_sortiert(list(je_isbn.values())))
                 for name, je_isbn in sorted(zeilen.items(), key=lambda e: e[0].casefold()))


def gruppen_nach_verlag_aus_datei(v: Vergleich) -> tuple[Gruppe, ...]:
    """Eine Gruppe je Verlag: die Bücher, die laut Datei dieses Schuljahr geführt
    werden, unter dem Verlag der Datei; dazu die, die nur IServ führt."""
    zeilen: dict[str, list[Buch]] = {}
    for buch in v.planung.buecher:
        aktiv = v.aktiv(buch)
        if not aktiv:
            continue
        abweichung = v.ergebnis.get(buch.isbn)
        herkunft = NUR_EXCEL if abweichung and abweichung.art == NUR_EXCEL else BEIDE
        zeilen.setdefault(buch.verlag or OHNE_VERLAG, []).append(
            _aus_datei(v, buch, aktiv, lambda paar: True, herkunft))
    for isbn, abweichung in v.ergebnis.items():
        if abweichung.art == NUR_ISERV:
            ist = v.iserv[isbn]
            zeilen.setdefault(ist.verlag or OHNE_VERLAG, []).append(_aus_iserv(ist, ist.paare))
    return tuple(Gruppe(name=name, buecher=_sortiert(buecher))
                 for name, buecher in sorted(zeilen.items(), key=lambda e: e[0].casefold()))


def liste_aus_datei(v: Vergleich, liste: Liste) -> tuple[Liste, tuple[Buch, ...]]:
    """Die IServ-Liste eines Jahrgangs, jede Zeile mit den Werten der Datei.

    Grundpaket und Wahlbereiche gibt es nur in IServ; sie bleiben. Ein Buch,
    das die Datei dieses Schuljahr nirgends führt, bleibt mit den IServ-Werten
    stehen und ist „nur in IServ“. Zurück kommt dazu, was laut Datei in diesem
    Jahrgang steht, in der IServ-Liste aber fehlt.
    """
    jahrgang = liste.jahrgang

    def hier(paar: Paar) -> bool:
        return paar[1] == jahrgang

    def zeile(buch: Buch) -> Buch:
        eigenes = v.planung.buch(buch.isbn)
        aktiv = v.aktiv(eigenes) if eigenes else frozenset()
        if eigenes is None or not aktiv:
            ist = v.iserv[buch.isbn]
            return _aus_iserv(ist, frozenset(paar for paar in ist.paare if hier(paar)))
        return _aus_datei(v, eigenes, frozenset(paar for paar in aktiv if hier(paar)) or aktiv,
                          hier, BEIDE)

    bereiche = tuple(
        Bereich(titel=bereich.titel, grundpaket=bereich.grundpaket, optionen=tuple(
            Option(titel=option.titel, buecher=tuple(zeile(b) for b in option.buecher))
            for option in bereich.optionen))
        for bereich in liste.bereiche
    )
    in_liste = {buch.isbn for buch in liste.alle_buecher}
    fehlend = [
        _aus_datei(v, buch, paare, hier, NUR_EXCEL)
        for buch in v.planung.buecher if buch.isbn not in in_liste
        for paare in (frozenset(paar for paar in v.aktiv(buch) if hier(paar)),) if paare
    ]
    return replace(liste, bereiche=bereiche), _sortiert(fehlend)
