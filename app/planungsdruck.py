"""Die Fach-Bücherlisten im PDF aus der Planungsdatei (Vorgabe vom 2026-11-10).

Ohne „IServ-Stand benutzen“ druckt die Fach-PDF nur die Planungsdatei; IServ
liefert dann nur noch Schuljahr und Schulanschrift. Gibt es keine Datei, lässt
sich das Druckmenü der Fächer gar nicht öffnen (``app/api/buecherliste.py``).

* **Ohne Antragsinformationen** steht nur, was genehmigt ist und in diesem
  Schuljahr gilt - der entschiedene Stand, gegen den auch die Fach-Ansicht mit
  IServ vergleicht (:func:`~buecherlisten.planung.farben.entschiedener_stand`):
  eine offene oder abgelehnte Einführung fehlt, eine offene oder abgelehnte
  Ausmusterung nach dem Vorjahr lässt das Buch stehen. Genehmigte spätere
  Änderungen fehlen auch - ohne Jahreszahl sähen sie aus, als gälten sie schon.
* **Mit Antragsinformationen** stehen dieselben Einträge wie in der
  Fach-Ansicht, hinter jedem Jahrgang der Zusatz mit den Jahreszahlen
  (:mod:`~buecherlisten.planung.zusatz`, z. B. „7 (ab 2027/2028)“). Eine
  Jahreszahl mit offenem Antrag ist samt Präfix („ab“, „bis“, „von“) grau, mit
  abgelehntem durchgestrichen. Gibt es einen Jahrgang nur wegen offener
  Einführungen, ist der ganze Jahrgang grau, nur wegen abgelehnter
  durchgestrichen; gilt das für jeden Jahrgang der Zeile (neues Buch beantragt
  bzw. abgelehnt), die ganze Zeile. Eine genehmigte Ausmusterung nach dem
  Vorjahr steht nicht mehr da: durchgestrichen heißt im PDF „abgelehnt“.

Die Spalte „Klasse“ darf mit Antragsinformationen umbrechen, aber nur an
Leerzeichen und nie zwischen Jahrgang und erster Jahreszahl oder zwischen
Präfix und Jahreszahl: dort stehen geschützte Leerzeichen (``\\xa0``), die
``buecherlisten.core.layout`` beim Messen wie reportlab beim Setzen als Teil
des Worts behandelt.

Zurück kommen Tabellen im Format von
:func:`buecherlisten.core.daten.build_subject_tables`, je Zeile dazu
``klasse_teile`` (Text und Stil je Stück) und ``stil`` (der ganzen Zeile).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from buecherlisten.core.daten import fmt_grades, fmt_price, format_isbn
from buecherlisten.core.layout import STIL_DURCH, STIL_GRAU
from buecherlisten.planung import (
    ANTRAG_ABGELEHNT,
    ANTRAG_GENEHMIGT,
    ANTRAG_OFFEN,
    OHNE_VERLAG,
    Buch,
    Buchplanung,
    Planungszeile,
    UngueltigesSchuljahr,
    aktive_eintraege,
    schuljahr_zahl,
)
from buecherlisten.planung.farben import entschiedener_stand, ohne_abgelehnte_ausmusterungen
from buecherlisten.planung.modelle import zeitfolge
from buecherlisten.planung.zusatz import Teil, zusatz_je_zeile

NBSP = "\xa0"
# Der Stil, den ein Antrag seiner Jahreszahl gibt.
_ANTRAGSSTIL = {ANTRAG_OFFEN: STIL_GRAU, ANTRAG_ABGELEHNT: STIL_DURCH}

Eintrag = tuple[str, int, bool]
Stueck = tuple[str, tuple[str, ...]]


@dataclass(frozen=True)
class _Wert:
    """Ein Jahrgang in der Spalte „Klasse“: die Stücke und der Stil der Zahl."""

    jahrgang: int
    stuecke: tuple[Stueck, ...]
    stil: str = ""


def _jahr(angabe: str) -> int | None:
    try:
        return schuljahr_zahl(angabe)
    except UngueltigesSchuljahr:
        return None


def _stile(*stile: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(s for s in stile if s))


def _einfuehrung(zeile: Planungszeile, jetzt: int) -> str | None:
    """Der Stand der Einführung. ``genehmigt`` auch ohne Einführung und für eine
    vor diesem Schuljahr - über die entscheidet niemand mehr; eine solche, die
    abgelehnt wurde, gab es nie (``None``)."""
    beginn = zeile.beginn
    status = zeile.antrag_einfuehrung.status
    if not zeile.eingefuehrt_ab or beginn is None:
        return ANTRAG_GENEHMIGT
    if beginn < jetzt:
        return None if status == ANTRAG_ABGELEHNT else ANTRAG_GENEHMIGT
    return status


def _lebt(zeile: Planungszeile, jetzt: int) -> bool:
    """Gilt die Zeile dieses Schuljahr oder später? Eine abgelehnte Ausmusterung
    gilt nicht, eine offene nach dem Vorjahr hält das Buch noch."""
    ende = zeile.ende
    if ende is None or ende >= jetzt:
        return True
    status = zeile.antrag_ausmusterung.status
    return ende == jetzt - 1 and status != ANTRAG_GENEHMIGT


def _zahlstil(zeilen: list[Planungszeile], jetzt: int) -> str | None:
    """Der Stil des Jahrgangs - ``None``, wenn er nicht dasteht."""
    stande = {_einfuehrung(zeile, jetzt) for zeile in zeilen if _lebt(zeile, jetzt)} - {None}
    if not stande:
        return None
    if ANTRAG_GENEHMIGT in stande:
        return ""
    return STIL_GRAU if ANTRAG_OFFEN in stande else STIL_DURCH


def _zusatz_stuecke(teile: tuple[Teil, ...], stil: str) -> list[Stueck]:
    """Die Stücke eines Zusatzergebnisses („von 2026/2027 bis 2027/2028“).

    Ein Präfix („ab “, „bis “, „von “) gehört zur folgenden Jahreszahl: es
    hängt mit geschütztem Leerzeichen an ihr und trägt ihren Stil. Führende
    Leerzeichen und „, “ trennen; an ihnen darf umbrochen werden, und sie
    tragen nur den Stil des Jahrgangs.
    """
    stuecke: list[Stueck] = []
    praefix = ""
    for teil in teile:
        if teil.art:
            stuecke.append((praefix.replace(" ", NBSP) + teil.text,
                            _stile(stil, _ANTRAGSSTIL.get(teil.antrag, ""))))
            praefix = ""
            continue
        rest = teil.text
        if rest.startswith(","):
            stuecke.append((",", _stile(stil)))
            rest = rest[1:]
        kern = rest.lstrip(" ")
        if len(kern) < len(rest):
            stuecke.append((rest[:len(rest) - len(kern)], _stile(stil)))
        praefix += kern
    if praefix:
        stuecke.append((praefix, _stile(stil)))
    return stuecke


def _wert(jahrgang: int, zeilen: list[Planungszeile], schuljahr: str, stil: str) -> _Wert:
    """Ein Jahrgang mit Zusatz: „7 (ab 2027/2028)“. Zwischen Jahrgang und erster
    Jahreszahl steht kein gewöhnliches Leerzeichen, dort wird nie umbrochen."""
    stuecke: list[Stueck] = [(str(jahrgang), _stile(stil))]
    zusaetze = zusatz_je_zeile(tuple(sorted(zeilen, key=zeitfolge)), schuljahr)
    if zusaetze:
        stuecke.append((NBSP + "(", _stile(stil)))
        for i, zusatz in enumerate(zusaetze):
            if i:
                stuecke.append((", ", _stile(stil)))
            stuecke += _zusatz_stuecke(zusatz.teile, stil)
        stuecke.append((")", _stile(stil)))
    return _Wert(jahrgang, tuple(stuecke), stil)


def _zeile(buch: Buch, werte: list[_Wert], *, antraege: bool) -> dict:
    """Eine Tabellenzeile; mit ``antraege`` samt ``klasse_teile`` und ``stil``."""
    werte = sorted(werte, key=lambda w: w.jahrgang)
    jahrgaenge = tuple(w.jahrgang for w in werte)
    zeile = {
        "sort_key": (jahrgaenge, buch.titel.lower()),
        "klasse": fmt_grades(jahrgaenge),
        "titel": buch.titel,
        "fach": "",
        "verlag": "" if buch.verlag == OHNE_VERLAG else buch.verlag,
        "isbn": format_isbn(buch.isbn),
        "neupreis": fmt_price(buch.neupreis),
        "leihgebuehr": fmt_price(buch.leihgebuehr),
        "faecher": (),
        "jahrgang_anzahl": len(jahrgaenge),
    }
    if not antraege:
        return zeile
    teile: list[Stueck] = []
    for i, wert in enumerate(werte):
        if i:
            teile.append((", ", _stile(wert.stil if wert.stil == werte[i - 1].stil else "")))
        teile += wert.stuecke
    stile = {wert.stil for wert in werte}
    return {**zeile, "klasse": "".join(text for text, _ in teile), "klasse_teile": tuple(teile),
            # Jeder Jahrgang grau (bzw. durchgestrichen): die ganze Zeile.
            "stil": stile.pop() if len(stile) == 1 else ""}


def _ohne_antraege(planung: Buchplanung) -> dict[tuple[str, str, bool], list[_Wert]]:
    """(Fach, ISBN, leihbar) -> Jahrgänge: der genehmigte Stand dieses Schuljahrs."""
    stand = entschiedener_stand(ohne_abgelehnte_ausmusterungen(planung))
    werte: dict[tuple[str, str, bool], list[_Wert]] = defaultdict(list)
    for buch in stand.buecher:
        for fach, jahrgang, leihbar in aktive_eintraege(stand, buch):
            werte[(fach, buch.isbn, leihbar)].append(_Wert(jahrgang, ()))
    return werte


def _mit_antraegen(planung: Buchplanung, jetzt: int) -> dict[tuple[str, str, bool], list[_Wert]]:
    """(Fach, ISBN, leihbar) -> Jahrgänge mit Zusatz: alles, was dieses Schuljahr
    oder später gilt, beantragt oder abgelehnt ist."""
    je_eintrag: dict[tuple[str, Eintrag], list[Planungszeile]] = defaultdict(list)
    for zeile in planung.planung:
        je_eintrag[(zeile.isbn, (zeile.fach, zeile.jahrgang, zeile.leihbar))].append(zeile)
    werte: dict[tuple[str, str, bool], list[_Wert]] = defaultdict(list)
    for (isbn, (fach, jahrgang, leihbar)), zeilen in je_eintrag.items():
        stil = _zahlstil(zeilen, jetzt)
        if stil is None:
            continue
        werte[(fach, isbn, leihbar)].append(_wert(jahrgang, zeilen, planung.schuljahr, stil))
    return werte


def fach_tabellen(planung: Buchplanung, *, antraege: bool) -> dict[str, dict[str, list[dict]]]:
    """Fach -> {"leih": [...], "kauf": [...]}, sortiert nach Jahrgängen und Titel.

    Die Fächer sind immer die der Datei mit Anträgen: so viele, wie das
    Druckmenü ohne IServ-Stand zur Wahl stellt. Ein Fach, das ohne
    Antragsinformationen nichts Genehmigtes hat (nur beantragt), bekommt leere
    Tabellen; eines, das es nur in IServ gibt, keine.
    """
    jetzt = _jahr(planung.schuljahr)
    alle = _mit_antraegen(planung, jetzt) if jetzt is not None else _ohne_antraege(planung)
    if antraege and jetzt is not None:
        werte = alle
    else:
        antraege = False
        werte = _ohne_antraege(planung)
    tabellen: dict[str, dict[str, list[dict]]] = {
        fach: {"leih": [], "kauf": []} for fach, _, _ in alle}
    for (fach, isbn, leihbar), eintraege in werte.items():
        buch = planung.buch(isbn)
        if buch is None:
            continue
        tabelle = tabellen.setdefault(fach, {"leih": [], "kauf": []})
        tabelle["leih" if leihbar else "kauf"].append(_zeile(buch, eintraege, antraege=antraege))
    for tabelle in tabellen.values():
        for zeilen in tabelle.values():
            zeilen.sort(key=lambda z: z["sort_key"])
    return dict(sorted(tabellen.items(), key=lambda e: e[0].casefold()))
