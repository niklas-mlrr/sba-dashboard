"""Der gespeicherte Planungsstand, fertig für die Bücherlisten-Vorlagen - ohne HTTP.

Die Bücherlisten-Seiten (``app/api/buecherliste.py``) zeigen die
Buchplanungs-Datei und das Planungsmenü je Buch. Was die Vorlagen dafür
brauchen, entsteht hier aus einer :class:`Buchplanung`: je Buch und Fach die
Zeilen des Menüs, die Rücklagen, die Ausmusterungen zu diesem Schuljahr, die
Vorschläge für „+ Buch hinzufügen“ und der Status je Fach.

Die Status werden nicht aus der Datei gelesen, sondern hier gerechnet - mit
denselben Funktionen, mit denen auch die API sie rechnet
(``buecherlisten/planung/modelle.py``).

Der Kontext ist ein ``dict``, weil die Vorlagen ihn so lesen und
``_buchplanung.html`` Teile davon als JSON ausgibt.
"""
from __future__ import annotations

from typing import Any

from buecherlisten.core.daten import format_isbn
from buecherlisten.planung import (
    ART_AUSMUSTERUNG,
    ART_EINFUEHRUNG,
    OHNE_VERLAG,
    PLANUNG_AUSGEMUSTERT,
    Buchplanung,
    UngueltigesSchuljahr,
    alles_genehmigt,
    endet_mit_vorjahr,
    fach_bestaetigung,
    fach_status,
    planungs_status,
    planungs_zusatz,
    schuljahr_zahl,
    zum_schuljahr_ausgemustert,
)


def leerer_kontext(schuljahr: str, *, fehler: str | None = None) -> dict[str, Any]:
    """Der Kontext ohne Datei: die Seiten zeigen dann IServ und ggf. ``fehler``."""
    return {
        "schuljahr": schuljahr, "mtime": None, "fehler": fehler, "warnungen": [],
        "fach_je_name": {}, "planung_je_isbn_und_fach": {},
        "ruecklage_je_isbn": {}, "bemerkung_je_isbn": {}, "ausmusterungen_je_fach": {},
        "vorjahr": "", "planungsjahr": "", "leihbar_isbns": set(),
        "verlage": [], "buecher": [], "isbns": set(),
    }


def planungskontext(planung: Buchplanung, *, schuljahr: str, mtime: float) -> dict[str, Any]:
    """Alles, was die Bücherlisten-Vorlagen über den gespeicherten Stand wissen.

    ``schuljahr`` ist die IServ-**Kennung** ("2026/2027"), nicht der
    Anzeigename: sie ist der Schlüssel der Datei und geht von der Seite
    unverändert in jede Eintragung zurück. ``mtime`` geht ebenso zurück - an ihr
    erkennt der Server, ob jemand anderes die Datei inzwischen geändert hat.
    """
    bemerkungen = {b.isbn: b.bemerkung for b in planung.bemerkungen}
    return {
        "schuljahr": schuljahr,
        "mtime": mtime,
        "fehler": None,
        "warnungen": list(planung.warnungen),
        "fach_je_name": _faecher(planung),
        "planung_je_isbn_und_fach": _zeilen_je_isbn_und_fach(planung),
        "ruecklage_je_isbn": _ruecklagen(planung),
        # Die Spalte „Bemerkung“ auf „Buchreihen“ - eine je Buch.
        "bemerkung_je_isbn": bemerkungen,
        "ausmusterungen_je_fach": _ausmusterungen_je_fach(planung),
        "vorjahr": planung.vorjahr,
        # Das Schuljahr der Datei: das Menü führt damit eine neue Zeile ein,
        # wenn „leihbar“ an einer alten umgeschaltet wird.
        "planungsjahr": planung.schuljahr,
        # Bücher, für die es eine Rücklage geben kann (eine Zeile ist leihbar).
        "leihbar_isbns": {buch.isbn for buch in planung.buecher if planung.leihbar(buch.isbn)},
        "verlage": [v for v in planung.verlage if v != OHNE_VERLAG],
        "buecher": _vorschlaege(planung, bemerkungen),
        # Die Bücher der Datei: nur ihre Zeilen haben ein Planungsmenü.
        "isbns": {buch.isbn for buch in planung.buecher},
    }


def _zeilen_je_isbn_und_fach(planung: Buchplanung) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Die Zeilen des Planungsmenüs, je Buch und Fach.

    Je Fach eigene Zeilen: die Fach-Ansicht zeigt nur, was ihr Fach angeht, und
    die Fachkonferenzleitung bestätigt nur ihre eigenen.
    """
    try:
        jetzt = schuljahr_zahl(planung.schuljahr)
    except UngueltigesSchuljahr:
        jetzt = 0
    zeilen: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for buch in planung.buecher:
        je_fach: dict[str, list[dict[str, Any]]] = {}
        for fach, jahrgang in planung.zeilen_des_buchs(buch):
            massgeblich = planung.massgebliche_zeile(buch.isbn, fach, jahrgang)
            for zeile in planung.zeilen_des_paars(buch.isbn, fach, jahrgang):
                status = planungs_status(zeile, planung.schuljahr)
                je_fach.setdefault(fach, []).append({
                    "jahrgang": jahrgang,
                    # ``aktuell`` heißt: die Zeile hat keine Einführung. Das
                    # Buch ist dort schon eingeführt - so kommen die Paare aus
                    # den Bücherlisten dieses Schuljahrs und des Vorjahrs an;
                    # zu entscheiden ist nur noch die Ausmusterung. Ein
                    # geplanter Jahrgang trägt eine Einführung und lässt sich
                    # deshalb ganz ändern und entfernen.
                    "aktuell": not zeile.eingefuehrt_ab,
                    "leihbar": zeile.leihbar,
                    # Schaltet man „leihbar“ an einer Zeile um, die schon vor
                    # diesem Schuljahr galt, endet sie mit dem Vorjahr und eine
                    # neue beginnt (``static/buchplanung.js``). Eine
                    # ausgemusterte Zeile lässt sich nicht mehr umschalten.
                    "alt": zeile.beginn is None or zeile.beginn < jetzt,
                    "gesperrt": status == PLANUNG_AUSGEMUSTERT,
                    "eingefuehrt_ab": zeile.eingefuehrt_ab,
                    "ausgemustert_nach": zeile.ausgemustert_nach,
                    "kuerzel": zeile.kuerzel,
                    "datum": zeile.datum,
                    "bemerkung": zeile.bemerkung,
                    "status": status,
                    # Sind alle Anträge der Zeile genehmigt (oder gibt es
                    # keinen), hinterlegt das Menü sie in der Farbe des Status.
                    "genehmigt": alles_genehmigt(zeile, planung.schuljahr),
                    # Der Zusatz „(ab …)“/„(bis …)“ in der Bücherliste kommt von
                    # der Zeile, die für dieses Schuljahr spricht.
                    "zusatz": planungs_zusatz(zeile, planung.schuljahr)
                    if zeile is massgeblich else "",
                    # Die Entscheidungen der Änderungsliste - im Menü nur zum Lesen.
                    **{
                        f"antrag_{art}": {"status": antrag.status, "kuerzel": antrag.kuerzel,
                                          "datum": antrag.datum}
                        for art in (ART_EINFUEHRUNG, ART_AUSMUSTERUNG)
                        if zeile.schuljahr_des_antrags(art)
                        for antrag in (zeile.antrag(art),)
                    },
                    "begruendung": zeile.begruendung,
                })
        zeilen[buch.isbn] = je_fach
    return zeilen


def _ruecklagen(planung: Buchplanung) -> dict[str, dict[str, Any]]:
    """Die Rücklagen je Buch und Fach."""
    ruecklagen: dict[str, dict[str, Any]] = {}
    for wunsch in planung.ruecklagen:
        ruecklagen.setdefault(wunsch.isbn, {})[wunsch.fach] = {
            "anzahl": wunsch.anzahl, "status": wunsch.status,
            "kuerzel": wunsch.kuerzel, "datum": wunsch.datum,
            "bemerkung": wunsch.bemerkung,
        }
    return ruecklagen


def _ausmusterungen_je_fach(planung: Buchplanung) -> dict[str, list[dict[str, Any]]]:
    """Was mit dem Vorjahr endete: in diesem Schuljahr nicht mehr auf der Liste.

    Nur vollständig ausgemustert - in keinem Jahrgang dieses Fachs bleibt das
    Buch danach noch stehen; ein anderes Fach zählt nicht. Sonst steht es in
    der normalen Liste.

    Gezeigt wird nur, was die Schule dort verliehen hat - mindestens ein
    Jahrgang leihbar. Um die Ausmusterungen geht es wegen der Rücklagen und der
    Regale; ein reines Kaufbuch hat keine.
    """
    je_fach: dict[str, dict[str, dict[str, Any]]] = {}
    for zeile in planung.planung:
        altes = planung.buch(zeile.isbn)
        if altes is None or not endet_mit_vorjahr(zeile, planung.schuljahr) \
                or not zum_schuljahr_ausgemustert(planung, altes, zeile.fach):
            continue
        eintrag = je_fach.setdefault(zeile.fach, {}).setdefault(altes.isbn, {
            "titel": altes.titel, "verlag": altes.verlag, "isbn": altes.isbn,
            "isbn_anzeige": format_isbn(altes.isbn),
            "neupreis": altes.neupreis, "leihgebuehr": altes.leihgebuehr,
            "jahrgaenge": [], "ja": [], "nein": [],
        })
        if zeile.jahrgang not in eintrag["jahrgaenge"]:
            eintrag["jahrgaenge"].append(zeile.jahrgang)
        eintrag["ja" if zeile.leihbar else "nein"].append(zeile.jahrgang)

    ausgemustert: dict[str, list[dict[str, Any]]] = {}
    for fach, je_buch in je_fach.items():
        eintraege = sorted(je_buch.values(), key=lambda e: e["titel"].casefold())
        for eintrag in eintraege:
            eintrag["jahrgaenge"].sort()
            ja, nein = sorted(eintrag.pop("ja")), sorted(eintrag.pop("nein"))
            eintrag["leihbar"] = bool(ja)
            eintrag["leihbar_teilweise"] = bool(ja and nein)
            eintrag["leihbar_titel"] = (
                f"leihbar: Jg. {', '.join(map(str, ja))} · Kaufbuch: Jg. {', '.join(map(str, nein))}"
                if ja and nein else "")
        ausgemustert[fach] = [eintrag for eintrag in eintraege if eintrag["leihbar"]]
    return ausgemustert


def _vorschlaege(planung: Buchplanung, bemerkungen: dict[str, str]) -> list[dict[str, Any]]:
    """Die Vorschläge für „+ Buch hinzufügen“: jedes Buch der Datei.

    Mit dem, was das Menü bei einem Treffer übernimmt.
    """
    return [
        {"isbn": buch.isbn, "isbn_anzeige": format_isbn(buch.isbn), "titel": buch.titel,
         "verlag": "" if buch.verlag == OHNE_VERLAG else buch.verlag,
         "neupreis": buch.neupreis, "leihgebuehr": buch.leihgebuehr,
         "leihbar": planung.leihbar(buch.isbn),
         "bemerkung": bemerkungen.get(buch.isbn, ""),
         "faecher": sorted({fach for fach, _ in buch.kombinationen}
                           | {z.fach for z in planung.planung if z.isbn == buch.isbn},
                           key=str.casefold)}
        for buch in sorted(planung.buecher, key=lambda b: b.titel.casefold())
    ]


def _faecher(planung: Buchplanung) -> dict[str, dict[str, Any]]:
    """Status und Bestätigung der Fachkonferenzleitung je Fach."""
    faecher: dict[str, dict[str, Any]] = {}
    for fach in planung.faecher:
        status, hinweis = fach_status(planung, fach)
        kuerzel, datum = fach_bestaetigung(planung, fach)
        faecher[fach] = {
            "status": status, "hinweis": hinweis, "kuerzel": kuerzel, "datum": datum,
        }
    return faecher
