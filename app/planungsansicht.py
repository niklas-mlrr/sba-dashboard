"""Der gespeicherte Planungsstand, fertig für die Bücherlisten-Vorlagen - ohne HTTP.

Die Bücherlisten-Seiten (``app/api/buecherliste.py``) zeigen die
Buchplanungs-Datei und das Planungsmenü je Buch. Was die Vorlagen dafür
brauchen, entsteht hier aus einer :class:`Buchplanung`: je Buch und Fach die
Zeilen des Menüs, die Rücklagen, die Vorschläge für „+ Buch hinzufügen“ und
der Status je Fach.

Die Status werden nicht aus der Datei gelesen, sondern hier gerechnet - mit
denselben Funktionen, mit denen auch die API sie rechnet
(``buecherlisten/planung/modelle.py``).

Der Kontext ist ein ``dict``, weil die Vorlagen ihn so lesen und
``_buchplanung.html`` Teile davon als JSON ausgibt.
"""
from __future__ import annotations

from typing import Any

from buecherlisten.core.daten import format_isbn, ist_platzhalter_isbn
from buecherlisten.planung import (
    ANTRAG_GENEHMIGT,
    ART_AUSMUSTERUNG,
    ART_EINFUEHRUNG,
    FACH_BESTAETIGT,
    OHNE_VERLAG,
    PLANUNG_AUSGEMUSTERT,
    Buchplanung,
    Planungszeile,
    UngueltigesSchuljahr,
    fach_bestaetigung,
    fach_status,
    planungs_status,
    planungs_zusatz,
    schuljahr_zahl,
    zu_entscheidende_antraege,
)


def leerer_kontext(schuljahr: str, *, fehler: str | None = None) -> dict[str, Any]:
    """Der Kontext ohne Datei: die Seiten zeigen dann IServ und ggf. ``fehler``."""
    return {
        "schuljahr": schuljahr, "mtime": None, "fehler": fehler, "warnungen": [],
        "fach_je_name": {}, "planung_je_isbn_und_fach": {},
        "ruecklage_je_isbn": {}, "bemerkung_je_isbn": {},
        "vorjahr": "", "planungsjahr": "", "leihbar_isbns": set(),
        "verlage": [], "buecher": [], "isbns": set(),
        "eintrag": lambda isbn, fach: None, "fachstand": lambda fach: None,
    }


# ── Was ein Menü beim Öffnen gesehen hat ─────────────────────────────────────
#
# Jedes Menü der Fach-Seite bekommt beim Rendern den Stand des Eintrags mit,
# den es ändert, und schickt ihn beim Speichern als ``vorher`` zurück. Der
# Server rechnet denselben Schnappschuss aus der Datei neu (``app/buchplanung.py``):
# ist er gleich, wird gespeichert - auch wenn sich an anderen Büchern etwas
# geändert hat; ist er anders, bekommt der Browser den neuen und legt beide
# nebeneinander (Entscheidung 2026-10-30). Deshalb steht er hier, an **einer**
# Stelle, und nur in JSON-Werten: Vorlage und Server müssen ihn gleich bauen.


def eintrag_stand(planung: Buchplanung, isbn: str, fach: str) -> dict[str, Any] | None:
    """Das Buchmenü eines Buchs in einem Fach als Schnappschuss - ``None`` ohne Buch.

    Die Zeilen sind nach „Jahrgang|Einführung“ geschlüsselt, so wie das Menü
    sie kennt (``data-bisher-jahrgang``/``data-bisher-ab``). ``ruecklage`` ist
    ``None`` bei einem Buch, für das es keine geben kann - dann hat das Menü
    keinen Block dafür.
    """
    buch = planung.buch(isbn)
    if buch is None:
        return None
    bemerkung = planung.bemerkung(isbn)
    ruecklage = planung.ruecklage(isbn, fach)
    return {
        "buchreihe": {
            "titel": buch.titel, "verlag": "" if buch.verlag == OHNE_VERLAG else buch.verlag,
            "neupreis": buch.neupreis, "leihgebuehr": buch.leihgebuehr,
            "bemerkung": bemerkung.bemerkung if bemerkung else "",
        },
        "zeilen": {
            f"{zeile.jahrgang}|{zeile.eingefuehrt_ab}": {
                "jahrgang": zeile.jahrgang, "eingefuehrt_ab": zeile.eingefuehrt_ab,
                "ausgemustert_nach": zeile.ausgemustert_nach, "leihbar": zeile.leihbar,
                "bemerkung": zeile.bemerkung,
            }
            for zeile in planung.planung if (zeile.isbn, zeile.fach) == (isbn, fach)
        },
        "ruecklage": {
            "anzahl": ruecklage.anzahl if ruecklage else None,
            "bemerkung": ruecklage.bemerkung if ruecklage else "",
        } if planung.leihbar(isbn) else None,
    }


def fach_stand(planung: Buchplanung, fach: str) -> dict[str, Any]:
    """Die Bestätigung einer Fachliste als Schnappschuss - für die beiden Kopfmenüs."""
    kuerzel, datum = fach_bestaetigung(planung, fach)
    if fach_status(planung, fach).status != FACH_BESTAETIGT:
        kuerzel, datum = "", None
    return {"fach": {"kuerzel": kuerzel, "datum": datum.isoformat() if datum else None}}


def verkehrte_zeitraeume(planung: Buchplanung) -> str | None:
    """Die Meldung für Zeilen, die vor ihrer Einführung ausgemustert sind - aus
    Excel; im Menü lässt sich das nicht eintragen. Die Seite zeigt sie beim
    Laden im Fehlermenü, die Liste bleibt trotzdem nutzbar."""
    titel = {buch.isbn: buch.titel for buch in planung.buecher}
    stellen = [
        f"„{titel.get(z.isbn, z.isbn)}“ in {z.fach}, Jahrgang {z.jahrgang} "
        f"(ab {z.eingefuehrt_ab}, nach {z.ausgemustert_nach})"
        for z in planung.planung if z.verkehrt]
    if not stellen:
        return None
    return ("In der Datei ist die Ausmusterung vor der Einführung eingetragen: "
            + "; ".join(stellen) + ". Bitte im Buchmenü oder in Excel korrigieren.")


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
        "fehler": verkehrte_zeitraeume(planung),
        "warnungen": list(planung.warnungen),
        "fach_je_name": _faecher(planung),
        "planung_je_isbn_und_fach": _zeilen_je_isbn_und_fach(planung),
        "ruecklage_je_isbn": _ruecklagen(planung),
        # Die Spalte „Bemerkung“ auf „Buchreihen“ - eine je Buch.
        "bemerkung_je_isbn": bemerkungen,
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
        # Was die Menüs beim Öffnen gesehen haben (``vorher`` beim Speichern).
        "eintrag": lambda isbn, fach: eintrag_stand(planung, isbn, fach),
        "fachstand": lambda fach: fach_stand(planung, fach),
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
                    # Die beiden Hälften der Zeile im Menü: oben der Antrag auf
                    # Einführung, unten der auf Ausmusterung (``_haelften``).
                    "haelften": _haelften(zeile, planung.schuljahr),
                    # Der Zusatz „(ab …)“/„(bis …)“ in der Bücherliste kommt von
                    # der Zeile, die für dieses Schuljahr spricht.
                    "zusatz": planungs_zusatz(zeile, planung.schuljahr)
                    if zeile is massgeblich else "",
                    # Die Entscheidungen der Änderungsliste - im Menü nur zum Lesen.
                    **{
                        f"antrag_{art}": {"status": antrag.status, "signatur": antrag.signatur,
                                          "datum": antrag.datum,
                                          "begruendung": zeile.begruendung(art)}
                        for art in (ART_EINFUEHRUNG, ART_AUSMUSTERUNG)
                        if zeile.schuljahr_des_antrags(art)
                        for antrag in (zeile.antrag(art),)
                    },
                })
        zeilen[buch.isbn] = je_fach
    return zeilen


def _haelften(zeile: Planungszeile, schuljahr: str) -> tuple[str, str]:
    """Wie die obere und die untere Hälfte einer Zeile im Buchmenü aussehen.

    Oben richtet sich nach dem Antrag auf Einführung, unten nach dem auf
    Ausmusterung - je ``genehmigt`` (in der Farbe des Status hinterlegt),
    ``offen`` (weiß) oder ``abgelehnt`` (hinterlegt und grau überdeckt). Hat
    die Zeile nur einen Antrag, gilt er für beide Hälften; ohne einen ist an
    ihr nichts offen, und sie gilt als genehmigt (Entscheidung 2026-10-10).
    """
    antraege = [zeile.antrag(art).status
                for art in zu_entscheidende_antraege(zeile, schuljahr)]
    if not antraege:
        return ANTRAG_GENEHMIGT, ANTRAG_GENEHMIGT
    return antraege[0], antraege[-1]


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


def _vorschlaege(planung: Buchplanung, bemerkungen: dict[str, str]) -> list[dict[str, Any]]:
    """Die Vorschläge für „+ Buch hinzufügen“: jedes Buch der Datei.

    Mit dem, was das Menü bei einem Treffer übernimmt.
    """
    return [
        {"isbn": buch.isbn, "isbn_anzeige": format_isbn(buch.isbn), "titel": buch.titel,
         "platzhalter": ist_platzhalter_isbn(buch.isbn),
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
    """Status und Bestätigung der Fachkonferenzleitung je Fach.

    ``text`` steht im Label („2 Anträge ausstehend“), ``status`` wählt dessen Farbe.
    """
    faecher: dict[str, dict[str, Any]] = {}
    for fach in planung.faecher:
        status = fach_status(planung, fach)
        kuerzel, datum = fach_bestaetigung(planung, fach)
        faecher[fach] = {
            "status": status.status, "text": status.text, "ausstehend": status.ausstehend,
            "kuerzel": kuerzel, "datum": datum,
        }
    return faecher
