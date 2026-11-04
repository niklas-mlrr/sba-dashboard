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

from buecherlisten.core.daten import (
    Korrekturen,
    format_isbn,
    ist_platzhalter_isbn,
    korrigiere_eintrag,
)
from buecherlisten.planung import (
    BEIDE,
    NUR_EXCEL,
    NUR_ISERV,
    PLANUNG_AUSGEMUSTERT,
    Abweichung,
    Buchplanung,
    IservBuch,
    aktive_eintraege,
    aktive_paare,
    endet_mit_vorjahr,
    leihbar_im_schuljahr,
    planungs_status,
    vergleiche,
    wirkt_im_schuljahr,
)
from buecherlisten.planung import Buch as PlanBuch
from buecherlisten.planung.farben import (
    Markierung,
    im_fach,
    markierung,
    ohne_abgelehnte_ausmusterungen,
)

OHNE_FACH = "(ohne Fach)"
OHNE_VERLAG = "(ohne Verlag)"

# Die drei Arten einer Abweichung - zugleich die CSS-Klassen der Markierung.
AENDERUNG = "aenderung"        # ein anderer Wert (Titel, Verlag, Preis, leihbar je Paar)
EINFUEHRUNG = "einfuehrung"    # laut Datei in Fach/Jahrgang, in IServ noch nicht
AUSMUSTERUNG = "ausmusterung"  # in IServ noch in Fach/Jahrgang, laut Datei nicht mehr
_EINFUEHRUNG_TEXT = "Einführung, fehlt in IServ"
_AUSMUSTERUNG_TEXT = "Ausmusterung, in IServ noch"

Paar = tuple[str, int]
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
    # Weicht IServ von der Datei ab, stehen oben die Werte der Datei und hier
    # die IServ-Werte der abweichenden Felder - live verglichen. Das
    # Planungsmenü zeigt sie als „in IServ: …“.
    iserv: tuple[tuple[str, Any], ...] = ()
    # Steht nicht in IServ - live gegen den Abruf geprüft. Meist ein im
    # Planungsmenü hinzugefügtes Buch; die Zeile kommt dann aus der
    # Buchplanung, nicht aus einer Bücherliste.
    von_hand: bool = False
    # Der Vergleich mit IServ, gerechnet für die Gruppe, in der die Zeile
    # steht. ``herkunft``: ``beide``; ``nur_excel`` - laut Datei gehört das Buch
    # in diese Gruppe, in IServ nicht; ``nur_iserv`` - umgekehrt. ``iserv``
    # trägt dann die abweichenden Werte aus IServ (gelb). ``neu`` sind die
    # (Fach, Jahrgang)-Paare dieser Gruppe, die nur die Datei führt - eine
    # Einführung (blau) -, ``weg`` die, die nur IServ noch führt - eine
    # Ausmusterung (rot). ``paare_sonst`` nennt die der übrigen Gruppen als
    # (Art, Satz). ``reihe`` ist ``neu`` bzw. ``weg``, wenn die ganze Buchreihe
    # eingeführt (in keiner IServ-Liste) oder ausgemustert (laut Datei in
    # keiner Liste mehr) wird; dann ist die ganze Zeile hinterlegt.
    herkunft: str = BEIDE
    neu: tuple[Paar, ...] = ()
    weg: tuple[Paar, ...] = ()
    paare_sonst: tuple[tuple[str, str], ...] = ()
    reihe: str = ""
    # „Leihbar“ gilt je (Fach, Jahrgang). Ist das Buch in den Paaren dieser
    # Zeile teils leihbar, teils nicht, ist ``leihbar`` wahr und
    # ``leihbar_teilweise`` auch - das Häkchen steht halb, ``leihbar_titel``
    # sagt wo. ``leihbar_iserv`` nennt die Paare, in denen IServ es anders
    # führt, mit dem Wert aus IServ.
    leihbar_teilweise: bool = False
    leihbar_titel: str = ""
    leihbar_iserv: tuple[tuple[Paar, bool], ...] = ()
    # Nur in der Fach-Ansicht (vorerst): die Farben aus Planung und IServ-Abgleich
    # (``buecherlisten/planung/farben.py``). Steht sie da, färbt die Vorlage
    # danach statt nach ``neu``/``weg``.
    farben: Markierung | None = None
    # Aus IServ: die Jahrgänge, denen die Buchreihe zugewiesen ist
    # (``series_data.gradesFlat``); ``None``, wenn IServ sie nicht mitschickt.
    buchreihe_jahrgaenge: tuple[int, ...] | None = None

    @property
    def abweichend(self) -> bool:
        return (self.herkunft != BEIDE or bool(self.iserv) or bool(self.neu)
                or bool(self.weg) or bool(self.paare_sonst))

    @property
    def art(self) -> str:
        """Die Farbe des Strichs vorn: Ausmusterung vor Einführung vor Änderung."""
        if self.herkunft == NUR_ISERV or self.weg:
            return AUSMUSTERUNG
        if self.herkunft == NUR_EXCEL or self.neu:
            return EINFUEHRUNG
        return AENDERUNG if self.iserv else ""

    def _nur_iserv(self, werte: set) -> frozenset:
        # Eine Zeile „nur in IServ“ zeigt die IServ-Werte: alle sind ausgemustert.
        return frozenset(werte - (set() if self.herkunft == NUR_ISERV
                                  else set(self.jahrgaenge) | set(self.faecher)))

    @property
    def neu_jahrgaenge(self) -> frozenset[int]:
        return frozenset(jahrgang for _, jahrgang in self.neu)

    @property
    def weg_jahrgaenge(self) -> frozenset[int]:
        """Die Jahrgänge, die nur IServ noch führt - sie stehen zusätzlich in der Zeile."""
        return self._nur_iserv({jahrgang for _, jahrgang in self.weg})

    @property
    def neu_faecher(self) -> frozenset[str]:
        return frozenset(fach for fach, _ in self.neu)

    @property
    def weg_faecher(self) -> frozenset[str]:
        return self._nur_iserv({fach for fach, _ in self.weg})

    @property
    def neu_text(self) -> str:
        return f"{_EINFUEHRUNG_TEXT}: {_paare_text(self.neu)}" if self.neu else ""

    @property
    def weg_text(self) -> str:
        return f"{_AUSMUSTERUNG_TEXT}: {_paare_text(self.weg)}" if self.weg else ""

    @property
    def isbn_anzeige(self) -> str:
        return format_isbn(self.isbn)

    @property
    def isbn_fehlt(self) -> bool:
        """Ein Buch, dessen ISBN noch niemand kennt: im Menü lässt sie sich nachtragen."""
        return ist_platzhalter_isbn(self.isbn)

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
    korrigiert = korrigiere_eintrag(item, korrekturen, jahrgang)
    daten = korrigiert.get("series_data") or {}
    isbn = daten.get("isbn") or item.get("series")
    if not isbn:
        return None
    felder = (korrekturen or {}).get(isbn) or {}
    iserv = tuple(
        (_FELDER[name], original.get(name))
        for name in felder if name in _FELDER
        # „Leihbar“ korrigiert die Datei je Jahrgang - nur wo sie einen Wert hat.
        and (name != "borrowable" or jahrgang in (felder.get(name) or {}))
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
        buchreihe_jahrgaenge=buchreihe_jahrgaenge(daten.get("gradesFlat")),
    )


def buchreihe_jahrgaenge(roh: Any) -> tuple[int, ...] | None:
    """Die Jahrgänge einer Buchreihe aus IServ (``gradesFlat``: ``[5, 6]``,
    ``grades``: ``[{"grade": 5}]``) - ``None``, wenn nichts Lesbares da ist."""
    if not isinstance(roh, list):
        return None
    jahrgaenge = set()
    for eintrag in roh:
        wert: Any = eintrag.get("grade") if isinstance(eintrag, dict) else eintrag
        try:
            jahrgaenge.add(int(wert))
        except (TypeError, ValueError):
            continue
    if roh and not jahrgaenge:
        return None
    return tuple(sorted(jahrgaenge))


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
                # Leihbar, sobald es in irgendeiner Liste leihbar ist - und
                # teilweise, wenn nicht in allen.
                leihbar=vorhanden.leihbar or buch.leihbar,
                leihbar_teilweise=vorhanden.leihbar_teilweise or buch.leihbar_teilweise
                or vorhanden.leihbar != buch.leihbar,
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


def iserv_je_isbn(daten: Buecherlisten) -> dict[str, IservBuch]:
    """Die Bücher der IServ-Listen je ISBN, mit allen (Fach, Jahrgang)-Paaren.

    ``daten`` muss **ohne** Korrekturen geladen sein: verglichen wird mit dem,
    was in IServ steht. Leihbar ist ein Buch je Jahrgangsliste; ``leihbar``
    heißt: in einer Liste leihbar - wie in :func:`_gruppiere`.
    """
    werte: dict[str, Buch] = {}
    paare: dict[str, set[Paar]] = {}
    leihbar_paare: dict[str, set[Paar]] = {}
    leihbar: dict[str, bool] = {}
    for liste in daten.listen:
        for buch in liste.alle_buecher:
            werte.setdefault(buch.isbn, buch)
            leihbar[buch.isbn] = leihbar.get(buch.isbn, False) or buch.leihbar
            if liste.jahrgang is not None:
                hier = {(fach, liste.jahrgang) for fach in buch.faecher or (OHNE_FACH,)}
                paare.setdefault(buch.isbn, set()).update(hier)
                if buch.leihbar:
                    leihbar_paare.setdefault(buch.isbn, set()).update(hier)
    return {
        isbn: IservBuch(isbn=isbn, titel=buch.titel, verlag=buch.verlag,
                        neupreis=buch.neupreis, leihgebuehr=buch.leihgebuehr,
                        leihbar=leihbar[isbn], paare=frozenset(paare.get(isbn, ())),
                        leihbar_paare=frozenset(leihbar_paare.get(isbn, ())),
                        buchreihe_jahrgaenge=None if buch.buchreihe_jahrgaenge is None
                        else frozenset(buch.buchreihe_jahrgaenge))
        for isbn, buch in werte.items()
    }


@dataclass(frozen=True)
class Vergleich:
    """Die Datei, IServ und was je Buch voneinander abweicht."""

    planung: Buchplanung
    iserv: dict[str, IservBuch]
    ergebnis: dict[str, Abweichung]
    # Der Stand der Datei, wenn ``planung`` der wirksame ist (ohne abgelehnte
    # Ausmusterungen, Fach-Ansicht); sonst ``None``.
    original: Buchplanung | None = None

    def aktiv(self, buch: PlanBuch) -> frozenset[Paar]:
        return aktive_paare(self.planung, buch)

    def gezeigte_paare(self, buch: PlanBuch) -> tuple[Paar, ...]:
        """Paare der Fach-Ansicht: die dieses Schuljahr gelten oder erst noch
        kommen, und die genau nach dem Vorjahr ausgemustert sind - rot und
        durchgestrichen, mit ihrem Antrag (Entscheidung 2026-11-04).

        Gerechnet mit dem wirksamen Stand: eine abgelehnte Ausmusterung ist
        darin schon weg. Was vor dem Vorjahr endete, steht nicht mehr da."""
        schuljahr = self.planung.schuljahr
        return tuple(
            (fach, jahrgang) for fach, jahrgang in self.planung.zeilen_des_buchs(buch)
            if any(planungs_status(zeile, schuljahr) != PLANUNG_AUSGEMUSTERT
                   or endet_mit_vorjahr(zeile, schuljahr)
                   for zeile in self.planung.zeilen_des_paars(buch.isbn, fach, jahrgang)
                   or [None])
        )

    @property
    def anzahl_abweichungen(self) -> int:
        return sum(1 for abweichung in self.ergebnis.values() if not abweichung.gleich)


def vergleiche_mit_iserv(daten: Buecherlisten, planung: Buchplanung,
                         buchreihen: Callable[[set[str]], dict[str, frozenset[int] | None] | None]
                         | None = None,
                         *, abgelehnte_gelten_nicht: bool = False) -> Vergleich:
    """Die Datei mit IServ vergleichen.

    ``buchreihen`` holt die Buchreihen aus dem IServ-Inventar mit ihren
    Jahrgängen, wenn die Bücherlisten sie für einige ISBNs nicht verraten (das
    Buch steht in keiner Liste, oder ``gradesFlat`` fehlt) - gerufen nur dann,
    mit diesen ISBNs. Eine angefragte ISBN, die darin fehlt, hat im Inventar
    keine Buchreihe; ``None`` heißt, das Inventar war nicht zu bekommen.

    ``abgelehnte_gelten_nicht``: eine abgelehnte Ausmusterung gilt nicht, das
    Buch bleibt (Fach-Ansicht, ``ohne_abgelehnte_ausmusterungen``). Der
    Vergleich rechnet dann mit diesem Stand; ``Vergleich.original`` hält den
    der Datei.
    """
    original = planung
    if abgelehnte_gelten_nicht:
        planung = ohne_abgelehnte_ausmusterungen(planung)
    iserv = iserv_je_isbn(daten)
    offen = {buch.isbn for buch in planung.buecher
             if aktive_eintraege(planung, buch)
             and (buch.isbn not in iserv or iserv[buch.isbn].buchreihe_jahrgaenge is None)}
    zusatz = buchreihen(offen) if buchreihen is not None and offen else None
    return Vergleich(planung=planung, iserv=iserv,
                     ergebnis=vergleiche(planung, iserv, zusatz),
                     original=original if abgelehnte_gelten_nicht else None)


def _paare_text(paare: tuple[Paar, ...] | list[Paar]) -> str:
    """(("Physik", 7), ("Physik", 8), ("Chemie", 9)) -> "Physik Jg. 7, 8; Chemie Jg. 9"."""
    je_fach: dict[str, list[int]] = {}
    for fach, jahrgang in paare:
        je_fach.setdefault(fach, []).append(jahrgang)
    return "; ".join(f"{fach} Jg. {', '.join(str(j) for j in sorted(jgs))}"
                     for fach, jgs in je_fach.items())


def _leihbar_laut_datei(planung: Buchplanung, isbn: str, paar: Paar) -> bool:
    """„Leihbar“ eines Paars: laut der Zeile, die dieses Schuljahr wirkt, sonst
    der maßgeblichen (einer geplanten oder ausgemusterten)."""
    zeilen = planung.zeilen_des_paars(isbn, *paar)
    if any(wirkt_im_schuljahr(zeile, planung.schuljahr) for zeile in zeilen):
        return leihbar_im_schuljahr(planung, isbn, paar)
    zeile = planung.massgebliche_zeile(isbn, *paar)
    return zeile.leihbar if zeile else False


def _leihbar(werte: dict[Paar, bool]) -> dict[str, Any]:
    """``leihbar``, ``leihbar_teilweise`` und ``leihbar_titel`` einer Zeile aus ihren Paaren."""
    ja = sorted((p for p, w in werte.items() if w), key=lambda p: (p[0].casefold(), p[1]))
    nein = sorted((p for p, w in werte.items() if not w), key=lambda p: (p[0].casefold(), p[1]))
    teilweise = bool(ja and nein)
    return {
        "leihbar": bool(ja), "leihbar_teilweise": teilweise,
        "leihbar_titel": f"leihbar: {_paare_text(ja)} · Kaufbuch: {_paare_text(nein)}"
        if teilweise else "",
    }


def _reihe(abweichung: Abweichung | None) -> str:
    if abweichung is None:
        return ""
    return {NUR_EXCEL: "neu", NUR_ISERV: "weg"}.get(abweichung.art, "")


def _aus_datei(v: Vergleich, buch: PlanBuch, paare: tuple[Paar, ...] | frozenset[Paar],
               hier: Callable[[Paar], bool], herkunft: str,
               jahrgaenge: tuple[int, ...] | None = None) -> Buch:
    """Eine Zeile mit den Werten der Datei und dem Vergleich dazu."""
    abweichung = v.ergebnis.get(buch.isbn)
    neu = abweichung.fehlt_in_iserv if abweichung else ()
    weg = abweichung.nur_in_iserv if abweichung else ()
    sonst: list[tuple[str, str]] = []
    # Bei einer ganz neuen oder ganz ausgemusterten Reihe sagt die hinterlegte
    # Zeile schon alles; die übrigen Gruppen werden dann nicht aufgezählt.
    if abweichung is not None and abweichung.art == BEIDE:
        for art, text, alle in ((EINFUEHRUNG, _EINFUEHRUNG_TEXT, neu),
                                (AUSMUSTERUNG, _AUSMUSTERUNG_TEXT, weg)):
            draussen = [paar for paar in alle if not hier(paar)]
            if draussen:
                sonst.append((art, f"{text}: {_paare_text(draussen)}"))
    # „Leihbar“ weicht je Paar ab; gelb ist es nur, wo es in dieser Gruppe abweicht.
    leihbar_iserv = tuple((paar, wert) for paar, wert in
                          (abweichung.leihbar_anders if abweichung else ()) if hier(paar))
    felder = abweichung.felder if abweichung and abweichung.art == BEIDE else ()
    return Buch(
        isbn=buch.isbn, titel=buch.titel,
        faecher=tuple(sorted({fach for fach, _ in paare}, key=str.casefold)),
        verlag="" if buch.verlag == OHNE_VERLAG else buch.verlag,
        neupreis=buch.neupreis, leihgebuehr=buch.leihgebuehr,
        **_leihbar({paar: _leihbar_laut_datei(v.planung, buch.isbn, paar)
                    for paar in paare if hier(paar)}),
        leihbar_iserv=leihbar_iserv,
        jahrgaenge=jahrgaenge if jahrgaenge is not None
        else tuple(sorted({jahrgang for _, jahrgang in paare})),
        iserv=tuple((feld, wert) for feld, wert in felder
                    if feld != "leihbar" or leihbar_iserv),
        von_hand=buch.isbn not in v.iserv, herkunft=herkunft,
        neu=tuple(paar for paar in neu if hier(paar)),
        weg=tuple(paar for paar in weg if hier(paar)),
        paare_sonst=tuple(sonst), reihe=_reihe(abweichung),
    )


def _aus_iserv(v: Vergleich, ist: IservBuch, paare: tuple[Paar, ...] | frozenset[Paar]) -> Buch:
    """Eine Zeile, die nur IServ in dieser Gruppe führt - mit den Werten aus IServ."""
    paare = tuple(sorted(paare, key=lambda paar: (paar[0].casefold(), paar[1])))
    return Buch(
        isbn=ist.isbn, titel=ist.titel,
        faecher=tuple(sorted({fach for fach, _ in paare}, key=str.casefold)),
        verlag=ist.verlag, neupreis=ist.neupreis, leihgebuehr=ist.leihgebuehr,
        **_leihbar({paar: ist.leihbar_in(paar) for paar in paare}),
        jahrgaenge=tuple(sorted({jahrgang for _, jahrgang in paare})),
        herkunft=NUR_ISERV, weg=paare, reihe=_reihe(v.ergebnis.get(ist.isbn)),
    )


def _sortiert(zeilen: list[Buch]) -> tuple[Buch, ...]:
    # Nur geplante Bücher (noch ohne Jahrgang in diesem Schuljahr) stehen am Ende.
    return tuple(sorted(zeilen, key=lambda b: (not b.jahrgaenge, b.jahrgaenge, b.titel.lower())))


def _fach_reihenfolge(buch: Buch) -> tuple[Any, ...]:
    """Die Anfangsreihenfolge der Fach-Ansicht: Jahrgang, dann ISBN, beide aufsteigend.

    Wie static/sortieren.js sie beim Laden herstellt: nach den Jahrgängen, die
    in der Zeile stehen (alle, egal was mit ihnen geplant ist), der kleinste
    zuerst, bei Gleichstand der zweitkleinste - wer keinen zweiten hat, steht
    vor einem mit zweitem -, dann die ISBN nach Zahl (ein „X“ am Ende zählt als
    10, wie ``sortierIsbn``), ein Platzhalter dahinter.
    """
    zahl = isbn_zahl(buch.isbn)
    return (buch.jahrgaenge, zahl is None, zahl or 0, buch.isbn)


def isbn_zahl(isbn: str) -> int | None:
    """Die ISBN als Zahl zum Sortieren - ``None`` für einen Platzhalter."""
    ziffern = isbn.replace("-", "").replace(" ", "").upper()
    if ziffern.endswith("X") and ziffern[:-1].isdigit():
        return int(ziffern[:-1]) * 10 + 10
    return int(ziffern) if ziffern.isdigit() else None


def _im_fach(fach: str) -> Callable[[Paar], bool]:
    return lambda paar: paar[0] == fach


def gruppen_nach_fach_aus_datei(v: Vergleich) -> tuple[Gruppe, ...]:
    """Eine Gruppe je Fach, aus der Datei - gefärbt nach Planung und IServ.

    In einem Fach steht jedes Buch, das dort dieses Schuljahr geführt wird,
    erst noch eingeführt wird **oder** genau nach dem Vorjahr ausgemustert ist
    (``Vergleich.gezeigte_paare``): die geplante Einführung und die
    Ausmusterung zu diesem Schuljahr soll man in der Liste sehen und im
    Planungsmenü ändern können, samt Rücklage. Eine eigene Tabelle
    „Ausmusterungen zu diesem Schuljahr“ gibt es seit 2026-11-04 nicht mehr.

    Seit 2026-10-31 färbt die Fach-Ansicht nach der Planung (Schrift) und nach
    IServ (Markierung) zugleich (``farben``, Regeln in
    buecherlisten/planung/farben.py). Bücher, die nur IServ im Fach führt,
    stehen wieder darin (die Entscheidung vom 2026-10-30 ist damit
    aufgehoben): rot markiert sind ihre Jahrgänge, und steht die ISBN dieses
    Schuljahr nur in IServ, jedes Feld. Ein Planungsmenü haben sie nicht.
    """
    zeilen: dict[str, dict[str, Buch]] = {}
    gezeigt: set[tuple[str, str]] = set()
    for buch in v.planung.buecher:
        abweichung = v.ergebnis.get(buch.isbn)
        paare = v.gezeigte_paare(buch)
        for fach in {fach for fach, _ in paare}:
            farben = markierung(v.planung, buch, abweichung, im=im_fach(fach),
                                original=v.original)
            zeilen.setdefault(fach, {})[buch.isbn] = replace(_aus_datei(
                v, buch, tuple(paar for paar in paare if paar[0] == fach),
                _im_fach(fach), BEIDE, jahrgaenge=farben.jahrgaenge,
            ), farben=farben)
            gezeigt.add((fach, buch.isbn))
    # Was nur IServ in einem Fach führt und sonst nirgends auf der Seite steht.
    for isbn, abweichung in v.ergebnis.items():
        for fach in sorted({fach for fach, _, _ in abweichung.eintraege_nur_iserv}):
            if (fach, isbn) in gezeigt:
                continue
            ist = v.iserv[isbn]
            eigenes = v.planung.buch(isbn) or PlanBuch(isbn=isbn, titel=ist.titel,
                                                       verlag=ist.verlag)
            farben = markierung(v.planung, eigenes, abweichung, im=im_fach(fach),
                                original=v.original)
            zeilen.setdefault(fach, {})[isbn] = replace(_aus_iserv(
                v, ist, frozenset(paar for paar in ist.paare if paar[0] == fach),
            ), farben=farben)
    return tuple(Gruppe(name=name, buecher=tuple(sorted(je_isbn.values(), key=_fach_reihenfolge)))
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
            zeilen.setdefault(ist.verlag or OHNE_VERLAG, []).append(_aus_iserv(v, ist, ist.paare))
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
        ist = v.iserv[buch.isbn]
        hier_ist = frozenset(paar for paar in ist.paare if hier(paar))
        if eigenes is None or not aktiv:
            return _aus_iserv(v, ist, hier_ist)
        hier_aktiv = frozenset(paar for paar in aktiv if hier(paar))
        if not hier_aktiv:
            # Die Datei führt das Buch, nur nicht mehr in diesem Jahrgang.
            return _aus_datei(v, eigenes, hier_ist, hier, NUR_ISERV)
        return _aus_datei(v, eigenes, hier_aktiv, hier, BEIDE)

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
