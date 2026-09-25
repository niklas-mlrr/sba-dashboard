"""Bücherlisten-Daten aus der IServ-Ausleihe-API, nach Fach zusammengestellt.

Aus ``generate_booklists.py`` herausgelöst (2026-09-17), damit das Dashboard
dieselbe Zusammenstellung nutzen kann wie das Kommandozeilen-Skript - nach dem
Vorbild von ``bestand/core/``. Rein lesend, ohne Netz- oder Pfad-Seiteneffekte
beim Import.
"""
from __future__ import annotations

import copy
import re
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import isbnlib


class _Schuljahre(Protocol):
    def get_current(self) -> dict: ...
    def get_by_id(self, schoolyear_id: str) -> dict: ...
    def get_booklists(self, schoolyear_id: str) -> list[dict]: ...
    def get_booklist(self, schoolyear_id: str, booklist_id: int) -> dict: ...


class SchuljahreClient(Protocol):
    """Nur die Schuljahre - was zum Laden der Bücherlisten selbst reicht.

    Getrennt von :class:`BuecherlistenClient`, weil die Buchplanung genau das
    braucht und nicht auch noch Verwalter-Rechte (``admin``), die für die
    Schulanschrift nötig sind.
    """

    @property
    def schoolyears(self) -> Any: ...


class BuecherlistenClient(SchuljahreClient, Protocol):
    """Was von ``ausleihe.AusleiheClient`` gebraucht wird."""

    @property
    def admin(self) -> Any: ...


def format_isbn(isbn: str) -> str:
    try:
        masked = isbnlib.mask(isbn)
        return masked if masked else isbn
    except Exception:
        return isbn


def fmt_price(value: float | None) -> str:
    if value is None:
        return "–"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "–"
    if value == 0:
        return "–"
    return f"{value:.2f}".replace(".", ",") + " €"


def fmt_grades(grades: tuple[int, ...]) -> str:
    # Komma + Leerzeichen statt "/": erlaubt Zeilenumbruch in der schmalen
    # Klasse-Spalte, wenn ein Mehrjahresband viele Klassen abdeckt.
    return ", ".join(str(g) for g in grades)


Ansicht = Literal["fach", "verlag", "jahrgang"]
ANSICHTEN: tuple[Ansicht, ...] = ("fach", "verlag", "jahrgang")
OHNE_FACH = "(ohne Fach)"
OHNE_VERLAG = "(ohne Verlag)"

# (Jahrgang, Bücherlisten-ID, Detail) je Jahrgangsliste, aufsteigend nach Jahrgang.
Jahrgangslisten = list[tuple[int, int, dict]]


# Korrekturen an Buchreihen: ISBN -> {IServ-Feldname: Wert}. Die Felder
# heißen wie in ``series_data`` (``title``, ``publisher``, ``price``, ``fee``;
# die ISBN ist der Schlüssel und wird nicht korrigiert), damit dieses Modul
# nichts von der Buchplanung wissen muss, die sie
# festhält (``buecherlisten/planung/``).
Korrekturen = Mapping[str, Mapping[str, Any]]


def wende_korrekturen_an(detail: dict, korrekturen: Korrekturen | None) -> dict:
    """Ein Bücherlisten-Detail aus IServ, mit den korrigierten Angaben der Buchreihen.

    Die **eine** Stelle, an der Korrekturen wirken: alles, was danach aus den
    Listen gelesen wird - Seiten und PDF -, sieht nur noch die
    korrigierten Werte, auch beim Gruppieren nach Verlag. Das
    Original bleibt unverändert; zurück kommt eine Kopie, sobald es etwas zu
    ändern gibt.
    """
    if not korrekturen:
        return detail
    kopie = copy.deepcopy(detail)
    for section in kopie.get("sections") or []:
        for option in section.get("options") or []:
            option["items"] = [korrigiere_eintrag(item, korrekturen)
                               for item in option.get("items") or []]
    return kopie


def korrigiere_eintrag(item: dict, korrekturen: Korrekturen | None) -> dict:
    """Ein Eintrag einer Bücherliste mit den korrigierten Angaben seiner Buchreihe.

    Ohne Korrektur kommt derselbe Eintrag zurück, sonst eine Kopie.
    """
    sd = item.get("series_data") or {}
    isbn = sd.get("isbn") or item.get("series")
    felder = dict(korrekturen.get(isbn) or {}) if korrekturen and isbn else {}
    if not felder:
        return item
    # "Leihbar" gehört in IServ zum Eintrag der Liste, nicht zur Buchreihe.
    eintrag = {"borrowable": felder.pop("borrowable")} if "borrowable" in felder else {}
    return {**item, **eintrag, "series_data": {**sd, **felder}}


def hole_jahrgangslisten(
    client: SchuljahreClient, schoolyear_id: str, korrekturen: Korrekturen | None = None,
) -> Jahrgangslisten:
    """Alle Jahrgangs-Bücherlisten eines Schuljahrs, einmal geladen für alle Ansichten."""
    booklists = client.schoolyears.get_booklists(schoolyear_id)
    by_grade = {bl["grade"]: bl for bl in booklists if bl.get("grade") is not None}
    return [
        (grade, by_grade[grade]["id"], wende_korrekturen_an(
            client.schoolyears.get_booklist(schoolyear_id, by_grade[grade]["id"]), korrekturen))
        for grade in sorted(by_grade)
    ]


def _sammle(listen: Jahrgangslisten, gruppen_von: Callable[[dict], list[str]]) -> dict[tuple[str, str], dict]:
    entries: dict[tuple[str, str], dict] = {}
    for grade, _, bl in listen:
        for section in bl.get("sections", []):
            for option in section.get("options", []):
                for item in option.get("items", []):
                    sd = item.get("series_data", {}) or {}
                    isbn = sd.get("isbn") or item.get("series")
                    if not isbn:
                        continue
                    for gruppe in gruppen_von(sd):
                        entry = entries.setdefault(
                            (gruppe, isbn),
                            {
                                "title": sd.get("title", "?"),
                                "publisher": sd.get("publisher", ""),
                                "subjects": list(sd.get("subjectsFlat") or []),
                                "price": sd.get("price"),
                                "fee": sd.get("fee"),
                                "borrowable": bool(item.get("borrowable")),
                                "grades": set(),
                            },
                        )
                        entry["grades"].add(grade)
    return entries


def _faecher_von(sd: dict) -> list[str]:
    return sd.get("subjectsFlat") or [OHNE_FACH]


def _verlag_von(sd: dict) -> list[str]:
    return [sd.get("publisher") or OHNE_VERLAG]


# IServ-Schuljahre heißen "2026/2027". Das Vorjahr daraus abzuleiten ist die
# einzige Stelle, an der dieses Format ausgewertet wird - einen Endpunkt "alle
# Schuljahre" gibt es nicht (siehe ausleihe/schoolyears.py). Bis 2026-09-19
# stand das in ``mehrjahresbaende/core/laden.py``; es liegt jetzt hier, weil
# inzwischen drei Pakete die Schreibweise brauchen und keines das andere
# importieren soll. ``mehrjahresbaende.core.laden`` reicht beide Namen weiter.
_JAHRESPAAR = re.compile(r"^(\d{4})\s*/\s*(\d{4})$")


class UnbekanntesSchuljahr(ValueError):
    """Aus der Kennung des Schuljahrs lässt sich kein Vorjahr ableiten."""


def vorjahr_kennung(kennung: str) -> str:
    """``"2026/2027"`` → ``"2025/2026"``.

    Wirft :class:`UnbekanntesSchuljahr`, wenn die Kennung nicht so aussieht -
    dann muss das Vorjahr von Hand angegeben werden, statt eine falsche
    Übersicht zu erzeugen.
    """
    treffer = _JAHRESPAAR.match(kennung.strip())
    if treffer is None:
        raise UnbekanntesSchuljahr(
            f"Aus dem Schuljahr {kennung!r} lässt sich das Vorjahr nicht ableiten. "
            "Erwartet wird die IServ-Schreibweise „2026/2027“."
        )
    erstes, zweites = (int(teil) for teil in treffer.groups())
    return f"{erstes - 1}/{zweites - 1}"


def sammle_je_isbn(listen: Jahrgangslisten) -> dict[str, dict]:
    """Alle Bücher eines Schuljahrs, je ISBN einmal, mit der Vereinigung der Jahrgänge.

    Dieselbe Zusammenführung wie :func:`collect_entries`, nur ohne Gruppierung:
    die Buchplanung braucht je Buch **eine** Zeile, keine je Fach.
    """
    return {isbn: eintrag for (_, isbn), eintrag in _sammle(listen, lambda sd: [""]).items()}


def sammle_je_fach_und_isbn(listen: Jahrgangslisten) -> dict[tuple[str, str], dict]:
    """Wie :func:`collect_entries`, nur über bereits geholte Jahrgangslisten.

    Die Planung braucht je (Fach, Jahrgang) eine Zeile und holt dieselben
    Listen schon für :func:`sammle_je_isbn`. Ein zweiter Abruf wäre ein Dutzend
    HTTP-Anfragen für Daten, die bereits im Speicher liegen.
    """
    return _sammle(listen, _faecher_von)


def collect_entries(client: BuecherlistenClient, schoolyear_id: str) -> dict[tuple[str, str], dict]:
    """Alle Bücherlisten-Items eines Schuljahrs, gruppiert nach (Fach, ISBN).

    Ein Buch, das in mehreren Jahrgangs-Bücherlisten desselben Fachs auftaucht
    (Mehrjahresband), wird zu einem Eintrag mit der Vereinigung der Klassen
    zusammengeführt — nicht anhand von series_data.gradesFlat (das ist ein
    globales Serien-Attribut und kann von den tatsächlichen Bücherlisten-
    Vorkommen abweichen, verifiziert 2026-08-18), sondern anhand der
    Bücherlisten-Jahrgänge, in denen das Item tatsächlich erscheint.
    """
    return sammle_je_fach_und_isbn(hole_jahrgangslisten(client, schoolyear_id))


def _zeile(isbn: str, e: dict, sort_key: tuple) -> dict:
    grades_sorted = tuple(sorted(e["grades"]))
    return {
        "sort_key": sort_key,
        "klasse": fmt_grades(grades_sorted),
        "titel": e["title"],
        "fach": ", ".join(e["subjects"]) or OHNE_FACH,
        "verlag": e["publisher"],
        "isbn": format_isbn(isbn),
        "neupreis": fmt_price(e["price"]),
        "leihgebuehr": fmt_price(e["fee"]),
    }


def build_subject_tables(entries: dict[tuple[str, str], dict]) -> dict[str, dict[str, list[dict]]]:
    """Gruppe -> {"leih": [Zeilen...], "kauf": [Zeilen...]}, jeweils fertig sortiert.

    Die Gruppe ist das Fach (``collect_entries``) oder der Verlag; sortiert
    wird in beiden Fällen nach Klassen, dann Titel.
    """
    by_subject: dict[str, dict[str, list[dict]]] = defaultdict(lambda: {"leih": [], "kauf": []})
    for (subject, isbn), e in entries.items():
        row = _zeile(isbn, e, (tuple(sorted(e["grades"])), e["title"].lower()))
        bucket = "leih" if e["borrowable"] else "kauf"
        by_subject[subject][bucket].append(row)

    for tables in by_subject.values():
        for bucket in ("leih", "kauf"):
            tables[bucket].sort(key=lambda r: r["sort_key"])
    return by_subject


def jahrgangsname(grade: int) -> str:
    return f"Jahrgang {grade}"


def build_grade_tables(listen: Jahrgangslisten) -> dict[str, dict[str, list[dict]]]:
    """"Jahrgang N" -> {"leih", "kauf"} in der Reihenfolge der IServ-Liste.

    Grundpaket zuerst, dann die Wahlbereiche nach ``position`` - wie die
    IServ-Druckversion, nur ohne Zwischenüberschriften: Wahlbereiche stehen mit
    in derselben Tabelle. Ein Buch, das in zwei Optionen steht, erscheint einmal.
    """
    tabellen: dict[str, dict[str, list[dict]]] = {}
    for grade, _, bl in listen:
        tables: dict[str, list[dict]] = {"leih": [], "kauf": []}
        gesehen: set[str] = set()
        sections = sorted(bl.get("sections", []), key=lambda s: s.get("position") or 0)
        for section in sections:
            for option in section.get("options", []):
                for item in option.get("items", []):
                    sd = item.get("series_data", {}) or {}
                    isbn = sd.get("isbn") or item.get("series")
                    if not isbn or isbn in gesehen:
                        continue
                    gesehen.add(isbn)
                    e = {
                        "title": sd.get("title", "?"), "publisher": sd.get("publisher", ""),
                        "subjects": list(sd.get("subjectsFlat") or []),
                        "price": sd.get("price"), "fee": sd.get("fee"), "grades": {grade},
                    }
                    bucket = "leih" if item.get("borrowable") else "kauf"
                    tables[bucket].append(_zeile(isbn, e, (len(gesehen),)))
        tabellen[jahrgangsname(grade)] = tables
    return tabellen


# Kleiner Sicherheitszuschlag auf jede berechnete Inhaltsbreite: reportlabs
# Paragraph-Layout kann bei der Wortabstands-/Kerning-Behandlung minimal von
# unserer stringWidth-Schätzung abweichen. Ohne Puffer reicht das, um ein
# Wort exakt an der Kante nicht mehr passen zu lassen — mit splitLongWords=0
# (siehe CELL_STYLE) würde es dann zwar nicht mitten im Wort umgebrochen,


@dataclass(frozen=True)
class Buecherdaten:
    """Ein geladenes Schuljahr: Kennung, Anzeigename und die Tabellen je Gruppe.

    ``je_verlag``, ``je_jahrgang`` und ``listen_ids`` haben Voreinstellungen,
    damit Tests, die nur Fächer brauchen, sie weglassen können.
    """

    schuljahr_id: str
    schuljahr_name: str
    je_fach: dict[str, dict[str, list[dict]]]
    je_verlag: dict[str, dict[str, list[dict]]] = field(default_factory=dict)
    je_jahrgang: dict[str, dict[str, list[dict]]] = field(default_factory=dict)
    # "Jahrgang N" -> ID der IServ-Bücherliste (für deren Druckversion).
    listen_ids: dict[str, int] = field(default_factory=dict)
    # Schulname und Ort aus ``GET /school/address`` für die Fußzeile der PDFs;
    # ``None`` heißt: nicht abrufbar, die Fußzeile nimmt dann ihren Rückfall.
    schule_name: str | None = None
    schule_ort: str | None = None

    @property
    def faecher(self) -> list[str]:
        return sorted(self.je_fach, key=str.casefold)

    @property
    def verlage(self) -> list[str]:
        return sorted(self.je_verlag, key=str.casefold)

    @property
    def jahrgaenge(self) -> list[str]:
        return sorted(self.je_jahrgang, key=_jahrgang_zahl)

    def tabellen(self, ansicht: Ansicht) -> dict[str, dict[str, list[dict]]]:
        return {"fach": self.je_fach, "verlag": self.je_verlag, "jahrgang": self.je_jahrgang}[ansicht]

    def gruppen(self, ansicht: Ansicht) -> list[str]:
        """Die Gruppennamen einer Ansicht in ihrer natürlichen Reihenfolge."""
        return {"fach": self.faecher, "verlag": self.verlage, "jahrgang": self.jahrgaenge}[ansicht]


def _jahrgang_zahl(name: str) -> int:
    return int(name.rsplit(" ", 1)[-1])


def hole_schulanschrift(client: BuecherlistenClient) -> tuple[str | None, str | None]:
    """(Schulname, Ort) aus der Ausleihe-API; scheitert nie, liefert dann
    ``(None, None)``. Die Bücherlisten sollen auch ohne Verwalter-Rechte oder
    bei einem Netzfehler entstehen — die Fußzeile nimmt dann ihren Rückfall."""
    try:
        anschrift = client.admin.get_school_address() or {}
    except Exception:
        return None, None
    name = (anschrift.get("name") or "").strip() or None
    ort = (anschrift.get("city") or "").strip() or None
    return name, ort


def lade_buecherdaten(
    client: BuecherlistenClient, schuljahr: str | None = None,
    korrekturen: Callable[[str], Korrekturen | None] | None = None,
) -> Buecherdaten:
    """Lädt ein Schuljahr (Default: das laufende). ``NotFoundError`` fliegt durch.

    ``korrekturen`` liefert zur Kennung des Schuljahrs die in der Buchplanung
    korrigierten Angaben der Buchreihen (:func:`wende_korrekturen_an`) - eine
    Funktion, weil ohne ``schuljahr`` erst hier feststeht, welches gilt.
    """
    if schuljahr:
        name = client.schoolyears.get_by_id(schuljahr)["name"]
        schuljahr_id = schuljahr
    else:
        aktuell = client.schoolyears.get_current()
        schuljahr_id, name = aktuell["id"], aktuell.get("name") or aktuell["id"]
    listen = hole_jahrgangslisten(
        client, schuljahr_id, korrekturen(str(schuljahr_id)) if korrekturen else None)
    schule_name, schule_ort = hole_schulanschrift(client)
    return Buecherdaten(
        schuljahr_id=schuljahr_id,
        schuljahr_name=name,
        je_fach=dict(build_subject_tables(_sammle(listen, _faecher_von))),
        je_verlag=dict(build_subject_tables(_sammle(listen, _verlag_von))),
        je_jahrgang=build_grade_tables(listen),
        listen_ids={jahrgangsname(grade): bl_id for grade, bl_id, _ in listen},
        schule_name=schule_name,
        schule_ort=schule_ort,
    )


def waehle_gruppen(
    daten: Buecherdaten, ansicht: Ansicht, gewuenscht: list[str],
) -> tuple[list[str], list[str]]:
    """Wie :func:`waehle_faecher`, für jede Ansicht; Jahrgänge auch als bloße Zahl ("5").

    Gefundene kommen in der Reihenfolge von ``daten.gruppen(ansicht)``.
    """
    verfuegbar = daten.gruppen(ansicht)
    if ansicht == "jahrgang":
        gewuenscht = [jahrgangsname(int(g)) if g.strip().isdigit() else g for g in gewuenscht]
    gefunden, unbekannt = waehle_faecher(verfuegbar, gewuenscht)
    return sorted(gefunden, key=verfuegbar.index), unbekannt


def waehle_faecher(verfuegbar: list[str], gewuenscht: list[str]) -> tuple[list[str], list[str]]:
    """Ordnet gewünschte Fachnamen ohne Rücksicht auf Groß-/Kleinschreibung zu.

    Gibt (gefundene, alphabetisch; unbekannte, in Eingabereihenfolge) zurück.
    """
    je_casefold = {s.casefold(): s for s in verfuegbar}
    gefunden: list[str] = []
    unbekannt: list[str] = []
    for wunsch in gewuenscht:
        treffer = je_casefold.get(wunsch.casefold())
        if treffer is None:
            unbekannt.append(wunsch)
        elif treffer not in gefunden:
            gefunden.append(treffer)
    return sorted(gefunden, key=str.casefold), unbekannt
