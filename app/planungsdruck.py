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

Die Spalte „Jahrgang“ darf mit Antragsinformationen umbrechen, aber nur an
Leerzeichen und nie zwischen Jahrgang und erster Jahreszahl oder zwischen
Präfix und Jahreszahl: dort stehen geschützte Leerzeichen (``\\xa0``), die
``buecherlisten.core.layout`` beim Messen wie reportlab beim Setzen als Teil
des Worts behandelt. Ein Jahrgang mit Jahreszusatz steht allein in seiner
Zeile bzw. seinen Zeilen: vor und hinter ihm ist der Umbruch erzwungen
(:data:`~buecherlisten.core.layout.ZEILENUMBRUCH`), das Komma bleibt am
Zeilenende; bricht sein Zusatz um, läuft er bündig unter „ab“/„bis“/„von“
weiter (:data:`~buecherlisten.core.layout.EINZUG`, Vorgabe vom 2026-11-10).

Die dritte Tabelle, „Leihbare nach vorigem Schuljahr ausgemusterte
Buchreihen“ (``ausgemustert``, Vorgabe vom 2026-11-10), hat die Buchreihen,
die in diesem Fach in jedem Jahrgang, in dem sie im Vorjahr leihbar waren,
nach dem Vorjahr genehmigt ausgemustert werden - mit und ohne
Antragsinformationen gleich, mit diesen Jahrgängen und ohne Zusatz. Wird die
Buchreihe im Fach ab diesem Schuljahr oder später wieder leihbar eingeführt
(und das nicht abgelehnt), geht sie nicht; sie fehlt dann hier. Ist sie in
anderen Fächern für dieses Schuljahr oder ein späteres genehmigt leihbar
(``weiter``: je Fach die Jahrgänge, mit Zusatz nur aus Genehmigtem, z. B.
„9 (ab 2027/2028)“; ein Jahrgang mit Zusatz steht allein in seinen Zeilen,
sein Umbruch läuft bündig unter „ab“/„bis“/„von“ weiter), trägt sie ein Sternchen, und unter der Tabelle steht
„weiterhin leihbar in“ mit diesen Fächern (``buecherlisten.core.layout``).

Leihbare Buchreihen beider Tabellen tragen die Rücklage ihrer Fachschaft
(``ruecklage``, die Anzahl; leer ohne). Hat mindestens eine Buchreihe einer
Tabelle eine, bekommt diese Tabelle die Spalte „Rücklagen“ als letzte (Vorgabe
vom 2026-11-10).

Anmerkungen zu Anträgen (Vorgabe vom 2026-11-12): Mit Antragsinformationen
und mindestens einem der Häkchen „Bearbeitungsdatum“, „Bearbeitender“,
„Begründung“ (:class:`Antragsdetails`) trägt jede Buchreihe aller drei
Tabellen ``anmerkungen``: je genehmigtem oder abgelehntem Antrag ihrer
Planungszeilen (Fach, ISBN, „leihbar“) eine Zeile mit den Zellen „Jahrgang 7“,
„Einführung“/„Ausmusterung“, ESJ/ASJ, „genehmigt“/„abgelehnt“, „am <Datum>“,
„durch <Signatur>“, „Begründung: <Text>“ - nur die angehakten der letzten
drei. Dazu zählt jede Ausmusterung nach dem Vorjahr oder später und jede
Einführung zu diesem Schuljahr oder später. Sortiert nach Jahrgang, dann
Schuljahr, bei Gleichstand die Einführung zuerst; der Jahrgang steht nur in
seiner ersten Zeile. Ein Antrag, bei dem alles Angehakte leer ist (etwa nur
„Begründung“ und keine da), fehlt. Hinter „Begründung: “ steht
:data:`~buecherlisten.core.layout.EINZUG`: bricht sie um, läuft sie bündig
unter ihrem Anfang weiter. Gesetzt werden sie in der Zeile der Buchreihe
unter deren Zellen, über alle Spalten (``buecherlisten.core.layout``).

Zurück kommen Tabellen im Format von
:func:`buecherlisten.core.daten.build_subject_tables`, je Zeile dazu
``klasse_teile`` (Text und Stil je Stück) und ``stil`` (der ganzen Zeile).
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace

from buecherlisten.core.daten import fmt_grades, fmt_price, format_isbn
from buecherlisten.core.layout import EINZUG, STIL_DURCH, STIL_GRAU, ZEILENUMBRUCH
from buecherlisten.planung import (
    ANTRAG_ABGELEHNT,
    ANTRAG_GENEHMIGT,
    ANTRAG_OFFEN,
    ART_AUSMUSTERUNG,
    ART_EINFUEHRUNG,
    OHNE_VERLAG,
    Antragsentscheidung,
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
class Antragsdetails:
    """Die Häkchen unter „Antragsinformationen“ im Druckmenü: was die
    Anmerkungen eines entschiedenen Antrags nennen (Vorgabe vom 2026-11-12)."""

    datum: bool = False
    bearbeiter: bool = False
    begruendung: bool = False

    @property
    def gewaehlt(self) -> bool:
        return self.datum or self.bearbeiter or self.begruendung


KEINE_DETAILS = Antragsdetails()

_ART_WORT = {ART_EINFUEHRUNG: "Einführung", ART_AUSMUSTERUNG: "Ausmusterung"}


def _anmerkungen(zeilen: Iterable[Planungszeile], jetzt: int,
                 details: Antragsdetails) -> tuple[tuple[str, ...], ...]:
    """Die Anmerkungen einer Buchreihe, je Antrag eine Zeile (Modulkopf)."""
    antraege: list[tuple[tuple[int, int, bool], tuple[str, ...]]] = []
    for zeile in zeilen:
        for art, jahr, ab in ((ART_EINFUEHRUNG, zeile.beginn, jetzt),
                              (ART_AUSMUSTERUNG, zeile.ende, jetzt - 1)):
            antrag = zeile.antrag(art)
            if jahr is None or jahr < ab or antrag.status not in (ANTRAG_GENEHMIGT,
                                                                   ANTRAG_ABGELEHNT):
                continue
            angaben: list[str] = []
            if details.datum:
                angaben.append(f"am {antrag.datum:%d.%m.%Y}" if antrag.datum else "")
            if details.bearbeiter:
                angaben.append(f"durch {antrag.signatur.strip()}" if antrag.signatur.strip()
                               else "")
            if details.begruendung:
                # Zeilenumbrüche der Begründung bleiben (ZEILENUMBRUCH ist "\n").
                text = zeile.begruendung(art).replace("\r\n", "\n").replace("\r", "\n").strip()
                angaben.append(f"Begründung: {EINZUG}{text}" if text else "")
            if not any(angaben):
                continue
            antraege.append(((zeile.jahrgang, jahr, art == ART_AUSMUSTERUNG),
                             (_ART_WORT[art], zeile.schuljahr_des_antrags(art).strip(),
                              antrag.status, *angaben)))
    antraege.sort(key=lambda a: a[0])
    ergebnis: list[tuple[str, ...]] = []
    for i, ((jahrgang, _, _), texte) in enumerate(antraege):
        erste = i == 0 or antraege[i - 1][0][0] != jahrgang
        ergebnis.append((f"Jahrgang{NBSP}{jahrgang}" if erste else "", *texte))
    return tuple(ergebnis)


@dataclass(frozen=True)
class _Wert:
    """Ein Jahrgang in der Spalte „Jahrgang“: die Stücke und der Stil der Zahl."""

    jahrgang: int
    stuecke: tuple[Stueck, ...]
    stil: str = ""

    @property
    def mit_zusatz(self) -> bool:
        return len(self.stuecke) > 1


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
            stil = _stile(wert.stil if wert.stil == werte[i - 1].stil else "")
            if wert.mit_zusatz or werte[i - 1].mit_zusatz:
                # Ein Jahrgang mit Zusatz steht allein in seinen Zeilen.
                teile += [(",", stil), (ZEILENUMBRUCH, ())]
            else:
                teile.append((", ", stil))
        if wert.mit_zusatz:
            # Bricht der Zusatz um, läuft er bündig unter seinem Anfang weiter.
            teile += [*wert.stuecke[:2], (EINZUG, ()), *wert.stuecke[2:]]
        else:
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


def _ausgemustert(planung: Buchplanung, jetzt: int) -> dict[tuple[str, str], list[_Wert]]:
    """(Fach, ISBN) -> Jahrgänge: Buchreihen, die im Fach als leihbare gehen.

    Jede leihbare Zeile, die im Vorjahr galt, endet genehmigt mit dem Vorjahr,
    und keine leihbare beginnt ab diesem Schuljahr (außer abgelehnt)."""
    je_paar: dict[tuple[str, str], list[Planungszeile]] = defaultdict(list)
    for zeile in planung.planung:
        if zeile.leihbar:
            je_paar[(zeile.fach, zeile.isbn)].append(zeile)
    vorjahr = jetzt - 1
    werte: dict[tuple[str, str], list[_Wert]] = {}
    for paar, zeilen in je_paar.items():
        im_vorjahr = [z for z in zeilen
                      if (z.beginn is None or z.beginn <= vorjahr)
                      and (z.ende is None or z.ende >= vorjahr)
                      and _einfuehrung(z, jetzt) == ANTRAG_GENEHMIGT]
        geht = all(z.ende == vorjahr and z.antrag_ausmusterung.status == ANTRAG_GENEHMIGT
                   for z in im_vorjahr)
        kommt = any(z.beginn is not None and z.beginn >= jetzt
                    and z.antrag_einfuehrung.status != ANTRAG_ABGELEHNT for z in zeilen)
        if im_vorjahr and geht and not kommt:
            werte[paar] = [_Wert(j, ()) for j in sorted({z.jahrgang for z in im_vorjahr})]
    return werte


def _gruppen(werte: list[_Wert]) -> tuple[tuple[str, str], ...]:
    """Die Jahrgänge als Gruppen (Kopf, Zusatz) für den Hinweis unter der
    Tabelle: Jahrgänge ohne Zusatz zusammen („5, 6,“, Zusatz leer), einer mit
    Zusatz allein - Kopf „7 (“, Zusatz „ab 2027/2028),“, damit dessen Umbruch
    bündig unter „ab“ weiterläuft. Das Komma steht am Ende jeder Gruppe außer
    der letzten (Vorgabe vom 2026-11-10)."""
    gruppen: list[tuple[str, str]] = []
    ohne: list[str] = []
    for wert in sorted(werte, key=lambda w: w.jahrgang):
        if not wert.mit_zusatz:
            ohne.append(str(wert.jahrgang))
            continue
        if ohne:
            gruppen.append((", ".join(ohne), ""))
            ohne = []
        (jahrgang, _), (klammer, _), *zusatz = wert.stuecke
        gruppen.append((jahrgang + klammer, "".join(text for text, _ in zusatz)))
    if ohne:
        gruppen.append((", ".join(ohne), ""))
    return tuple((kopf + ("," if i < len(gruppen) - 1 and not zusatz else ""),
                  zusatz + ("," if i < len(gruppen) - 1 and zusatz else ""))
                 for i, (kopf, zusatz) in enumerate(gruppen))


def _weiter(planung: Buchplanung, jetzt: int) -> dict[str, dict[str, tuple[tuple[str, str], ...]]]:
    """ISBN -> Fach -> Jahrgänge (als :func:`_gruppen`), in denen die
    Buchreihe für dieses Schuljahr oder ein späteres genehmigt leihbar ist.

    Genehmigt eingeführt (eine frühere Einführung gilt, außer abgelehnt) und
    nicht vor diesem Schuljahr genehmigt ausgemustert; der Zusatz kennt nur
    genehmigte Jahre - eine nicht genehmigte Ausmusterung zählt nicht."""
    genehmigt = Antragsentscheidung(ANTRAG_GENEHMIGT)
    je_eintrag: dict[tuple[str, str, int], list[Planungszeile]] = defaultdict(list)
    for zeile in planung.planung:
        if not zeile.leihbar or _einfuehrung(zeile, jetzt) != ANTRAG_GENEHMIGT:
            continue
        ausgemustert = zeile.antrag_ausmusterung.status == ANTRAG_GENEHMIGT
        if ausgemustert and zeile.ende is not None and zeile.ende < jetzt:
            continue
        je_eintrag[(zeile.isbn, zeile.fach, zeile.jahrgang)].append(replace(
            zeile, ausgemustert_nach=zeile.ausgemustert_nach if ausgemustert else "",
            antrag_einfuehrung=genehmigt, antrag_ausmusterung=genehmigt))
    je_fach: dict[tuple[str, str], list[_Wert]] = defaultdict(list)
    for (isbn, fach, jahrgang), zeilen in je_eintrag.items():
        je_fach[(isbn, fach)].append(_wert(jahrgang, zeilen, planung.schuljahr, ""))
    weiter: dict[str, dict[str, tuple[tuple[str, str], ...]]] = defaultdict(dict)
    for (isbn, fach), werte in je_fach.items():
        weiter[isbn][fach] = _gruppen(werte)
    return weiter


def _ruecklage(planung: Buchplanung, isbn: str, fach: str) -> str:
    ruecklage = planung.ruecklage(isbn, fach)
    return str(ruecklage.anzahl) if ruecklage and ruecklage.anzahl else ""


def fach_tabellen(planung: Buchplanung, *, antraege: bool,
                  details: Antragsdetails = KEINE_DETAILS) -> dict[str, dict[str, list[dict]]]:
    """Fach -> {"leih": [...], "kauf": [...], "ausgemustert": [...]}, sortiert
    nach Jahrgängen und Titel.

    Mit ``antraege`` und gewählten ``details`` trägt jede Zeile
    ``anmerkungen`` (Modulkopf); ohne ``antraege`` wirken ``details`` nicht.

    Die Fächer sind immer die der Datei mit Anträgen: so viele, wie das
    Druckmenü ohne IServ-Stand zur Wahl stellt. Ein Fach, das ohne
    Antragsinformationen nichts Genehmigtes hat (nur beantragt), bekommt leere
    Tabellen; eines, das es nur in IServ gibt, keine. Ein Fach, dessen
    Buchreihen alle ausgemustert sind, steht nur mit ``ausgemustert`` da.
    """
    jetzt = _jahr(planung.schuljahr)
    alle = _mit_antraegen(planung, jetzt) if jetzt is not None else _ohne_antraege(planung)
    if antraege and jetzt is not None:
        werte = alle
    else:
        antraege = False
        werte = _ohne_antraege(planung)
    def leer() -> dict[str, list[dict]]:
        return {"leih": [], "kauf": [], "ausgemustert": []}

    je_buchreihe: dict[tuple[str, str, bool], list[Planungszeile]] = defaultdict(list)
    if antraege and jetzt is not None and details.gewaehlt:
        for planungszeile in planung.planung:
            je_buchreihe[(planungszeile.fach, planungszeile.isbn,
                          planungszeile.leihbar)].append(planungszeile)

    def anmerken(zeile: dict, schluessel: tuple[str, str, bool]) -> dict:
        if jetzt is None or schluessel not in je_buchreihe:
            return zeile
        anmerkungen = _anmerkungen(je_buchreihe[schluessel], jetzt, details)
        return {**zeile, "anmerkungen": anmerkungen} if anmerkungen else zeile

    tabellen: dict[str, dict[str, list[dict]]] = {fach: leer() for fach, _, _ in alle}
    for (fach, isbn, leihbar), eintraege in werte.items():
        buch = planung.buch(isbn)
        if buch is None:
            continue
        zeile = anmerken(_zeile(buch, eintraege, antraege=antraege), (fach, isbn, leihbar))
        if leihbar:
            zeile["ruecklage"] = _ruecklage(planung, isbn, fach)
        tabellen.setdefault(fach, leer())["leih" if leihbar else "kauf"].append(zeile)
    ausgemustert = _ausgemustert(planung, jetzt) if jetzt is not None else {}
    weiter = _weiter(planung, jetzt) if ausgemustert and jetzt is not None else {}
    for (fach, isbn), eintraege in ausgemustert.items():
        buch = planung.buch(isbn)
        if buch is None:
            continue
        andere = sorted((f for f in weiter.get(isbn, {}) if f != fach), key=str.casefold)
        zeile = {**_zeile(buch, eintraege, antraege=False),
                 "ruecklage": _ruecklage(planung, isbn, fach),
                 "weiter": tuple((f, weiter[isbn][f]) for f in andere)}
        zeile = anmerken(zeile, (fach, isbn, True))
        tabellen.setdefault(fach, leer())["ausgemustert"].append(zeile)
    for tabelle in tabellen.values():
        for zeilen in tabelle.values():
            zeilen.sort(key=lambda z: z["sort_key"])
    return dict(sorted(tabellen.items(), key=lambda e: e[0].casefold()))
