"""Den Stand aus IServ mit dem zusammenführen, was von Hand eingetragen wurde -
und die einzelnen Eintragungen vornehmen.

Der Abgleich ist die Stelle, an der die beiden Wahrheiten aufeinandertreffen:

* **Die Datei** ist das Soll: welche Bücher es gibt, in welchen Fächern und
  Jahrgängen, zu welchem Preis, und was bemerkt, bestätigt, geplant und
  zurückgelegt wurde. Das überlebt jeden Abgleich.
* **IServ** liefert beim Abgleich nur, was die Datei noch nicht kennt: neue
  Bücher. Was IServ anders sagt als die Datei, markieren die
  Bücherlisten-Seiten farbig - live, bei jedem Öffnen.

Alle Funktionen hier geben einen **neuen**
:class:`~buecherlisten.planung.modelle.Buchplanung`-Wert zurück; nichts wird an
Ort und Stelle verändert. Das Speichern (Schloss, ``mtime``, Sicherung) steht im
Dashboard.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from math import isfinite
from typing import Any, TypeVar

import isbnlib

from .laden import Schnappschuss
from .modelle import (
    ANTRAG_ERGEBNISSE,
    ART_AUSMUSTERUNG,
    ART_EINFUEHRUNG,
    OHNE_FACH,
    RUECKLAGE_GEWUENSCHT,
    RUECKLAGE_STATUS,
    Antragsentscheidung,
    Buch,
    Buchbemerkung,
    Buchplanung,
    Planungszeile,
    Ruecklage,
    UngueltigesSchuljahr,
    schuljahr_zahl,
    wirkt_im_schuljahr,
    zeitfolge,
)

# Ein Jahrgang, den es an einer Schule geben kann. Die Grenzen sind bewusst
# weit: geprüft wird nur gegen Tippfehler wie "20" oder "0".
_JAHRGANG_VON = 1
_JAHRGANG_BIS = 13


class UnbekanntesBuch(ValueError):
    """Zu dieser ISBN steht in der Datei kein Buch."""


class UngueltigeEingabe(ValueError):
    """Der eingetragene Wert passt nicht zu dem, was die Spalte trägt."""


# ── Zusammenführen ───────────────────────────────────────────────────────────


def zusammenfuehren(vorher: Buchplanung | None, schnappschuss: Schnappschuss) -> Buchplanung:
    """Nimmt neue Bücher aus IServ auf und lässt alles, was schon in der Datei steht.

    Die Datei ist das **Soll** (Entscheidung 2026-09-25): was sie zu einem Buch
    sagt - Titel, Verlag, Preise, Fächer und Jahrgänge, leihbar je Zeile -, bleibt beim
    Abgleich stehen. Weicht IServ davon ab, zeigen das die Bücherlisten-Seiten
    (``buecherlisten/planung/vergleich.py``) bei jedem Öffnen; die Datei selbst
    nennt den IServ-Wert nicht. Bis dahin zog der Abgleich die Datei auf IServ
    nach; danach war jede Abweichung verschwunden, bevor sie jemand gesehen
    hatte.

    Aus IServ übernommen wird deshalb nur, was die Datei noch nicht kennt: ein
    neues Buch, samt der Paare, in denen es im Vorjahr stand und heuer nicht
    mehr (Ausmusterung nach dem Vorjahr). Verschwindet ein Buch aus IServ,
    bleibt es in der Datei - das ist gerade eine Abweichung, kein Aufräumen.

    Ein Buch, das nicht in IServ steht, bleibt, solange es einen Jahrgang hat.
    Taucht die ISBN eines im Menü angelegten Buchs in IServ auf, bleiben seine
    Werte und seine Planung trotzdem die der Datei.
    """
    alt = vorher or Buchplanung()
    aus_iserv = {buch.isbn: buch for buch in schnappschuss.buecher}

    buecher = [altes for altes in alt.buecher
               if altes.isbn in aus_iserv or alt.zeilen_des_buchs(altes)]
    bekannt = {buch.isbn for buch in buecher}
    neue = [buch for buch in schnappschuss.buecher if buch.isbn not in bekannt]
    buecher.extend(neue)

    # Ein neues Buch bekommt je Paar eine Zeile, leihbar wie in IServ. Was im
    # Vorjahr in einer Liste stand und heuer nicht mehr, ist nach dem Vorjahr
    # ausgemustert. Ein von Hand eingetragener Wert bleibt.
    planung = list(alt.planung)
    for buch in neue:
        leihbar = set(buch.leihbar_paare)
        for fach, jahrgang in buch.kombinationen:
            nach = schnappschuss.vorjahr if (fach, jahrgang) in buch.ausgemustert else ""
            bisher = next((i for i, z in enumerate(planung)
                           if (z.isbn, z.fach, z.jahrgang) == (buch.isbn, fach, jahrgang)
                           and not z.eingefuehrt_ab), None)
            if bisher is None:
                planung.append(Planungszeile(isbn=buch.isbn, fach=fach, jahrgang=jahrgang,
                                             leihbar=(fach, jahrgang) in leihbar,
                                             ausgemustert_nach=nach))
            elif nach and not planung[bisher].ausgemustert_nach:
                planung[bisher] = replace(planung[bisher], ausgemustert_nach=nach)

    return Buchplanung(
        schuljahr=schnappschuss.schuljahr,
        vorjahr=schnappschuss.vorjahr,
        stand=schnappschuss.stand,
        buecher=tuple(buecher),
        bemerkungen=alt.bemerkungen,
        planung=tuple(planung),
        ruecklagen=alt.ruecklagen,
        warnungen=tuple(schnappschuss.warnungen),
    )


# ── Einzelne Eintragungen ────────────────────────────────────────────────────


_Eintrag = TypeVar("_Eintrag")


def _ersetze(
    eintraege: tuple[_Eintrag, ...],
    passt: Callable[[_Eintrag], bool],
    neuer: _Eintrag | None,
) -> tuple[_Eintrag, ...]:
    """Tauscht den passenden Eintrag aus, hängt an oder entfernt ihn (``None``)."""
    ohne = tuple(eintrag for eintrag in eintraege if not passt(eintrag))
    return ohne if neuer is None else ohne + (neuer,)


def _geprueftes_buch(stand: Buchplanung, isbn: str) -> Buch:
    buch = stand.buch(isbn)
    if buch is None:
        raise UnbekanntesBuch(
            f"Zu der ISBN {isbn} steht in dieser Datei kein Buch. Bitte zuerst "
            "„Aus IServ aktualisieren“."
        )
    return buch


def _geprueftes_fach(stand: Buchplanung, buch: Buch, fach: str) -> None:
    """Gehört das Buch zu diesem Fach - heute oder laut Planung oder Rücklage?"""
    erlaubt = set(buch.faecher or (OHNE_FACH,))
    erlaubt |= {zeile.fach for zeile in stand.planung if zeile.isbn == buch.isbn}
    erlaubt |= {eintrag.fach for eintrag in stand.ruecklagen if eintrag.isbn == buch.isbn}
    if fach not in erlaubt:
        raise UngueltigeEingabe(
            f"„{buch.titel}“ gehört nicht zum Fach „{fach}“. Möglich sind: "
            + ", ".join(sorted(erlaubt)) + "."
        )


def setze_planung(
    stand: Buchplanung, *, isbn: str, fach: str, jahrgang: int, eingefuehrt_ab: str = "",
    ausgemustert_nach: str = "", kuerzel: str = "", datum: date | None = None,
    bemerkung: str = "", antrag_einfuehrung: Antragsentscheidung | None = None,
    antrag_ausmusterung: Antragsentscheidung | None = None, begruendung: str | None = None,
    leihbar: bool | None = None, bisher_ab: str | None = None,
) -> Buchplanung:
    """Trägt für **ein** Buch in **einem** Fach und Jahrgang die Zeile ein.

    Der Jahrgang muss nicht der eines heutigen Vorkommens sein: "wird ab
    2028/29 auch in Jahrgang 9 eingeführt" ist genau der Fall, für den es
    diese Zeile gibt. Ist alles leer, verschwindet die Zeile wieder - außer
    sie ist die eingeführte Zeile des Paars: die trägt ``leihbar``.

    Welche Zeile des Paars gemeint ist, sagt ``bisher_ab`` (ihre Einführung
    vor dieser Eintragung); fehlt es, die mit derselben Einführung, sonst die
    einzige Zeile des Paars (:func:`_finde_bisher`). ``leihbar`` ``None``
    lässt den Wert der Zeile stehen.

    Einführung und Ausmusterung gelten für **jedes** Buch, auch für ein
    Kaufbuch. Bis 2026-09-20 wies die Ausmusterung ein Kaufbuch ab - aus dem
    Regal der Schule sei nichts zu entfernen. Das verwechselte zwei Dinge:
    ausgemustert wird eine **Bücherliste**, nicht ein Bestand. Auch ein Buch,
    das die Familien selbst kaufen, steht bis zu einem Schuljahr auf der Liste
    und danach nicht mehr - und genau das hält diese Spalte fest. Was sich
    wirklich auf den Bestand der Schule bezieht, ist die Rücklage
    (:func:`setze_ruecklage`); dort gilt die Einschränkung weiter.
    """
    buch = _geprueftes_buch(stand, isbn)
    _geprueftes_fach(stand, buch, fach)
    return _setze_zeile(stand, isbn=isbn, fach=fach, jahrgang=jahrgang,
                        eingefuehrt_ab=eingefuehrt_ab, ausgemustert_nach=ausgemustert_nach,
                        kuerzel=kuerzel, datum=datum, bemerkung=bemerkung,
                        antrag_einfuehrung=antrag_einfuehrung,
                        antrag_ausmusterung=antrag_ausmusterung, begruendung=begruendung,
                        leihbar=leihbar, bisher_ab=bisher_ab)


def _gleiches_schuljahr(eins: str, anderes: str) -> bool:
    """"2027/2028" und "2027/28" sind dasselbe Schuljahr; sonst zählt der Text."""
    try:
        return schuljahr_zahl(eins) == schuljahr_zahl(anderes)
    except UngueltigesSchuljahr:
        return eins.strip() == anderes.strip()


def _finde_bisher(
    stand: Buchplanung, isbn: str, fach: str, jahrgang: int, eingefuehrt_ab: str,
    bisher_ab: str | None, vergeben: set[tuple[str, str, int, object]] | None = None,
) -> Planungszeile | None:
    """Die Zeile, die eine Eintragung ändert - oder ``None`` für eine neue.

    ``bisher_ab`` ist die Einführung, mit der die Zeile im Menü stand; mit ihm
    ist die Zeile eindeutig. Ohne gilt die Zeile mit derselben Einführung und,
    gibt es keine, die einzige noch nicht ``vergeben``e Zeile des Paars - so
    ändert eine Eintragung ohne ``bisher_ab`` die Einführung einer Zeile, wie
    vor 2026-10-10, als ein Paar nur eine Zeile hatte.
    """
    if bisher_ab is not None:
        return stand.planungszeile(isbn, fach, jahrgang, bisher_ab)
    gleich = stand.planungszeile(isbn, fach, jahrgang, eingefuehrt_ab)
    if gleich is not None:
        return gleich
    frei = [z for z in stand.zeilen_des_paars(isbn, fach, jahrgang)
            if z.schluessel not in (vergeben or set())]
    return frei[0] if len(frei) == 1 else None


def _neue_zeile(
    bisher: Planungszeile | None, *, isbn: str, fach: str, jahrgang: int,
    eingefuehrt_ab: str = "", ausgemustert_nach: str = "", kuerzel: str = "",
    datum: date | None = None, bemerkung: str = "",
    antrag_einfuehrung: Antragsentscheidung | None = None,
    antrag_ausmusterung: Antragsentscheidung | None = None, begruendung: str | None = None,
    leihbar: bool | None = None,
) -> Planungszeile:
    """Die Zeile nach einer Eintragung - geprüft, mit dem, was von ``bisher`` bleibt.

    Die Entscheidungen über die Anträge, die Begründung und ``leihbar`` kommen,
    wenn sie nicht mitgegeben werden (``None``), aus der bisherigen Zeile - so
    behält jede Eintragung sie, ohne sie zu kennen: das Planungsmenü, „Liste
    bestätigen“, der Abgleich. Eine Entscheidung gilt aber nur dem Schuljahr,
    über das entschieden wurde. Ändert es sich, fällt sie weg: über das neue
    hat niemand entschieden.
    """
    if not _JAHRGANG_VON <= jahrgang <= _JAHRGANG_BIS:
        raise UngueltigeEingabe(
            f"„{jahrgang}“ ist kein Jahrgang. Erwartet wird eine Zahl zwischen "
            f"{_JAHRGANG_VON} und {_JAHRGANG_BIS}."
        )
    ab, nach = eingefuehrt_ab.strip(), ausgemustert_nach.strip()
    for feld, wert in (("Einführung", ab), ("Ausmusterung nach Schuljahr", nach)):
        if wert:
            try:
                schuljahr_zahl(wert)
            except UngueltigesSchuljahr as exc:
                raise UngueltigeEingabe(f"Feld „{feld}“: {exc}") from exc
    if ab and nach and schuljahr_zahl(nach) < schuljahr_zahl(ab):
        raise UngueltigeEingabe(
            f"Das Buch kann nicht nach {nach} ausgemustert werden, wenn es erst "
            f"ab {ab} eingeführt wird."
        )

    def behalten(art: str, neues_schuljahr: str) -> Antragsentscheidung:
        if bisher is None or not _gleiches_schuljahr(
                bisher.schuljahr_des_antrags(art), neues_schuljahr):
            return Antragsentscheidung()
        return bisher.antrag(art)

    return Planungszeile(
        isbn=isbn, fach=fach, jahrgang=jahrgang, eingefuehrt_ab=ab,
        ausgemustert_nach=nach, kuerzel=kuerzel.strip(), datum=datum,
        bemerkung=bemerkung.strip(),
        leihbar=(bisher.leihbar if bisher else False) if leihbar is None else leihbar,
        antrag_einfuehrung=behalten(ART_EINFUEHRUNG, ab)
        if antrag_einfuehrung is None else antrag_einfuehrung,
        antrag_ausmusterung=behalten(ART_AUSMUSTERUNG, nach)
        if antrag_ausmusterung is None else antrag_ausmusterung,
        begruendung=(bisher.begruendung if bisher else "")
        if begruendung is None else begruendung.strip(),
    )


def _mit_planung(stand: Buchplanung, isbn: str,
                 planung: Sequence[Planungszeile]) -> Buchplanung:
    """Der Stand mit neuen Planungszeilen - und den eingeführten Paaren des Buchs dazu.

    Eingeführt ist ein Paar, wenn es eine Zeile ohne Einführung hat. Bekommt
    die eingeführte Zeile eine Einführung oder verschwindet sie, ist das Paar
    nicht mehr eingeführt; ohne diesen Abgleich käme sie als leere Zeile zurück
    (``Buchplanung.__post_init__``).
    """
    paare = tuple(sorted({(z.fach, z.jahrgang) for z in planung
                          if z.isbn == isbn and not z.eingefuehrt_ab},
                         key=lambda paar: (paar[0].casefold(), paar[1])))
    return _ersetzt(
        stand, planung=tuple(planung),
        buecher=tuple(replace(b, kombinationen=paare) if b.isbn == isbn else b
                      for b in stand.buecher),
    )


def _pruefe_zeitraeume(zeilen: Sequence[Planungszeile]) -> None:
    """Je Jahrgang höchstens eine Zeile je Einführung, und keine zwei zur selben Zeit.

    So wechselt ``leihbar``: die alte Zeile endet mit dem Vorjahr, die neue
    beginnt mit dem Schuljahr. Eine Zeile ohne Einführung gilt seit jeher,
    eine ohne Ausmusterung für immer.
    """
    je_jahrgang: dict[int, list[Planungszeile]] = {}
    for zeile in zeilen:
        je_jahrgang.setdefault(zeile.jahrgang, []).append(zeile)
    for jahrgang, eigene in je_jahrgang.items():
        schluessel = [z.schluessel for z in eigene]
        if len(set(schluessel)) < len(schluessel):
            raise UngueltigeEingabe(
                f"Jahrgang {jahrgang} steht zweimal in der Liste. Jeder Jahrgang darf "
                "nur einmal vorkommen - außer nacheinander, mit Ausmusterung und Einführung."
            )
        eigene.sort(key=zeitfolge)
        for frueher, spaeter in zip(eigene, eigene[1:]):
            ende, beginn = frueher.ende, spaeter.beginn
            if ende is None or beginn is None or ende >= beginn:
                raise UngueltigeEingabe(
                    f"Die Zeilen von Jahrgang {jahrgang} überschneiden sich "
                    f"({frueher.eingefuehrt_ab or 'eingeführt'} und ab "
                    f"{spaeter.eingefuehrt_ab}). Bitte bei der früheren die Ausmusterung "
                    "vor der Einführung der späteren eintragen."
                )


def _setze_zeile(
    stand: Buchplanung, *, isbn: str, fach: str, jahrgang: int, eingefuehrt_ab: str = "",
    ausgemustert_nach: str = "", kuerzel: str = "", datum: date | None = None,
    bemerkung: str = "", antrag_einfuehrung: Antragsentscheidung | None = None,
    antrag_ausmusterung: Antragsentscheidung | None = None, begruendung: str | None = None,
    leihbar: bool | None = None, bisher_ab: str | None = None,
) -> Buchplanung:
    """:func:`setze_planung` ohne die Frage, ob das Buch zum Fach gehört.

    Die stellt :func:`fuege_buch_hinzu` gerade andersherum: dort kommt das Buch
    mit dieser Zeile überhaupt erst in das Fach.
    """
    bisher = _finde_bisher(stand, isbn, fach, jahrgang, eingefuehrt_ab.strip(), bisher_ab)
    zeile = _neue_zeile(
        bisher, isbn=isbn, fach=fach, jahrgang=jahrgang, eingefuehrt_ab=eingefuehrt_ab,
        ausgemustert_nach=ausgemustert_nach, kuerzel=kuerzel, datum=datum,
        bemerkung=bemerkung, antrag_einfuehrung=antrag_einfuehrung,
        antrag_ausmusterung=antrag_ausmusterung, begruendung=begruendung, leihbar=leihbar,
    )
    andere = tuple(z for z in stand.planung if z is not bisher)
    if any(z.schluessel == zeile.schluessel for z in andere):
        raise UngueltigeEingabe(
            f"Für Jahrgang {jahrgang} gibt es schon eine Zeile mit dieser Einführung."
        )
    buch = stand.buch(isbn)
    # Die eingeführte Zeile bleibt, auch leer: sie trägt ``leihbar``.
    eingefuehrt = (not zeile.eingefuehrt_ab and buch is not None
                   and (fach, jahrgang) in buch.kombinationen)
    if zeile.leer and not eingefuehrt:
        return _mit_planung(stand, isbn, andere)
    _pruefe_zeitraeume([z for z in andere if (z.isbn, z.fach) == (isbn, fach)] + [zeile])
    return _mit_planung(stand, isbn, andere + (zeile,))


@dataclass(frozen=True)
class Jahrgangseingabe:
    """Eine Zeile des Planungsmenüs: ein Jahrgang mit seinen beiden Schuljahren.

    Ohne ``kuerzel`` und ``datum``: bestätigt wird nicht je Zeile, sondern die
    Liste als Ganzes über :func:`bestaetige_fach` (der Knopf „Liste bestätigen“
    oben auf der Fach-Seite).

    ``bisher_ab`` ist die Einführung, mit der die Zeile im Menü stand, ``neu``
    sagt, dass es sie noch nicht gab: ein Jahrgang kann mehrere Zeilen haben,
    und erst damit ist klar, welche geändert wird. Ohne beides gilt
    :func:`_finde_bisher`. ``leihbar`` ``None`` lässt den Wert der Zeile
    stehen (eine neue ist dann nicht leihbar).
    """

    jahrgang: int
    eingefuehrt_ab: str = ""
    ausgemustert_nach: str = ""
    bemerkung: str = ""
    leihbar: bool | None = None
    bisher_ab: str | None = None
    neu: bool = False


@dataclass(frozen=True)
class Ruecklageneingabe:
    """Der Rücklage-Block desselben Menüs: wie viele Exemplare, und wozu.

    Ohne ``status``: die Fachschaft äußert einen Wunsch, sie sagt ihn sich
    nicht selbst zu. Der Stand einer Rücklage (``gewünscht`` → ``zugesagt`` →
    ``zurückgelegt``) gehört dem, der die Bücher tatsächlich zurücklegt, und
    wird in der Datei geführt, nicht im Menü gesetzt. Ein schon eingetragener
    Stand bleibt beim Speichern deshalb stehen.
    """

    anzahl: int | None = None
    bemerkung: str = ""


def setze_buchplanung(
    stand: Buchplanung, *, isbn: str, fach: str,
    zeilen: Sequence[Jahrgangseingabe], ruecklage: Ruecklageneingabe | None = None,
) -> Buchplanung:
    """Alles, was das Planungsmenü eines Buchs in einem Fach einträgt - in einem Zug.

    Das Menü speichert auf einen Knopfdruck: mehrere Jahrgänge und die
    Rücklage. Nacheinander abgeschickte Einzelanfragen würden am
    ``mtime``-Vergleich scheitern (``app/buchplanung.py``), denn schon die
    erste schreibt die Datei neu. Deshalb eine Funktion, die alle Zeilen dieses
    (ISBN, Fach) auf den übergebenen Stand bringt - **auch durch Entfernen**:
    was nicht mitgeschickt wird, hat der Benutzer im Menü gelöscht. Eine
    eingeführte Zeile lässt sich nicht löschen; fehlt sie, steht sie danach
    leer da (``leihbar`` bleibt).

    Ein Jahrgang kann mehrere Zeilen haben - so wechselt ``leihbar`` (das Menü
    teilt die Zeile beim Umschalten, ``static/buchplanung.js``). Ihre
    Zeiträume dürfen sich nicht überschneiden (:func:`_pruefe_zeitraeume`).

    ``kuerzel`` und ``datum`` der Fachkonferenzleitung kommen nicht aus dem
    Menü, gehen aber auch nicht verloren. Sie bleiben genau dann stehen, wenn
    die Änderung das **laufende** Schuljahr nicht berührt
    (:func:`~buecherlisten.planung.modelle.wirkt_im_schuljahr`): eine
    Ausmusterung, die erst in drei Jahren greift, ändert nichts an der Liste,
    die bestätigt wurde. Wird ein Buch dagegen ab sofort eingeführt oder ist es
    ab sofort weg, fällt die Bestätigung dieser Zeile - und damit das Fach auf
    "teilweise". Eine neue Zeile ist unbestätigt.
    """
    buch = _geprueftes_buch(stand, isbn)
    _geprueftes_fach(stand, buch, fach)

    vergeben: set[tuple[str, str, int, object]] = set()
    neue: list[Planungszeile] = []
    for eingabe in zeilen:
        ab = eingabe.eingefuehrt_ab.strip()
        bisher = None if eingabe.neu else _finde_bisher(
            stand, isbn, fach, eingabe.jahrgang, ab, eingabe.bisher_ab, vergeben)
        if bisher is not None:
            if bisher.schluessel in vergeben:
                raise UngueltigeEingabe(
                    f"Jahrgang {eingabe.jahrgang} steht zweimal in der Liste. Jeder "
                    "Jahrgang darf nur einmal vorkommen."
                )
            vergeben.add(bisher.schluessel)
        # Ein Jahrgang ohne Einführung gilt als schon eingeführt. Ein geplanter
        # würde durch ein geleertes Feld also still zu einem eingeführten.
        if not ab and (fach, eingabe.jahrgang) not in buch.kombinationen:
            raise UngueltigeEingabe(
                f"Bitte für Jahrgang {eingabe.jahrgang} das Schuljahr der Einführung "
                "eintragen."
            )
        zeile = _neue_zeile(
            bisher, isbn=isbn, fach=fach, jahrgang=eingabe.jahrgang, eingefuehrt_ab=ab,
            ausgemustert_nach=eingabe.ausgemustert_nach,
            kuerzel=bisher.kuerzel if bisher else "", datum=bisher.datum if bisher else None,
            bemerkung=eingabe.bemerkung, leihbar=eingabe.leihbar,
        )
        if bisher is not None and bisher.bestaetigt and (
                wirkt_im_schuljahr(bisher, stand.schuljahr)
                != wirkt_im_schuljahr(zeile, stand.schuljahr)):
            zeile = replace(zeile, kuerzel="", datum=None)
        neue.append(zeile)

    for alte in stand.planung:
        if ((alte.isbn, alte.fach) == (isbn, fach) and alte.schluessel not in vergeben
                and not alte.eingefuehrt_ab and (fach, alte.jahrgang) in buch.kombinationen):
            # Eingeführt und nicht mitgeschickt: leer, aber mit ``leihbar``.
            neue.append(Planungszeile(isbn=isbn, fach=fach, jahrgang=alte.jahrgang,
                                      leihbar=alte.leihbar))
    _pruefe_zeitraeume(neue)

    neu = _mit_planung(stand, isbn, tuple(
        z for z in stand.planung if (z.isbn, z.fach) != (isbn, fach)) + tuple(neue))

    if ruecklage is not None:
        vorher_r = stand.ruecklage(isbn, fach)
        neu = setze_ruecklage(
            neu, isbn=isbn, fach=fach, anzahl=ruecklage.anzahl,
            status=vorher_r.status if vorher_r else "",
            kuerzel=vorher_r.kuerzel if vorher_r else "",
            datum=vorher_r.datum if vorher_r else None,
            bemerkung=ruecklage.bemerkung,
        )
    return _ohne_verwaiste(neu, isbn)


def _ohne_verwaiste(stand: Buchplanung, isbn: str) -> Buchplanung:
    """Ein Buch ohne jeden Jahrgang fällt aus der Datei.

    Es gehört zu keinem Fach mehr und wäre nur noch eine Zeile, die niemand
    mehr öffnen kann. Das trifft praktisch nur ein von Hand angelegtes Buch:
    die eingeführten Jahrgänge eines Buchs aus IServ lassen sich im Menü nicht
    entfernen. Der Abgleich verwirft ein solches Buch aus demselben Grund
    (:func:`zusammenfuehren`).
    """
    buch = stand.buch(isbn)
    if buch is None or stand.zeilen_des_buchs(buch):
        return stand
    return _ersetzt(
        stand,
        buecher=tuple(b for b in stand.buecher if b.isbn != isbn),
        bemerkungen=tuple(b for b in stand.bemerkungen if b.isbn != isbn),
        ruecklagen=tuple(r for r in stand.ruecklagen if r.isbn != isbn),
    )


@dataclass(frozen=True)
class Buchreiheneingabe:
    """Der Block „Buchreihe“ des Planungsmenüs - die änderbaren Felder.

    Ohne ISBN: sie ist der Schlüssel des Buchs und steht im Menü nur zum
    Lesen. Ein leerer Preis ist leer. „Leihbar“ steht seit 2026-10-10 nicht
    mehr hier, sondern je Jahrgang (:class:`Jahrgangseingabe`).
    """

    titel: str
    verlag: str
    neupreis: float | None = None
    leihgebuehr: float | None = None
    # Die Spalte ``Bemerkung`` auf ``Buchreihen`` - eine je Buch, für alle
    # Fächer. ``None`` heißt: bleibt, wie es dasteht.
    bemerkung: str | None = None


# Ein Preis, den es für ein Schulbuch geben kann. Geprüft wird wie beim
# Jahrgang nur gegen Tippfehler.
_PREIS_BIS = 10_000.0


def _gepruefte_buchreihe(eingabe: Buchreiheneingabe) -> tuple[str, str]:
    """Titel und Verlag, beschnitten - nach den Pflichtfeldern des IServ-Dialogs."""
    titel, verlag = eingabe.titel.strip(), eingabe.verlag.strip()
    if not titel:
        raise UngueltigeEingabe("Bitte einen Titel eintragen.")
    if not verlag:
        raise UngueltigeEingabe("Bitte einen Verlag eintragen.")
    for name, betrag in (("Neupreis", eingabe.neupreis), ("Leihgebühr", eingabe.leihgebuehr)):
        if betrag is not None and not (isfinite(betrag) and 0 <= betrag <= _PREIS_BIS):
            raise UngueltigeEingabe(
                f"„{betrag}“ ist kein gültiger {name}. Erwartet wird ein Betrag "
                f"zwischen 0 und {_PREIS_BIS:.0f} €."
            )
    return titel, verlag


def _cent(betrag: float | None) -> float | None:
    return None if betrag is None else round(betrag, 2)


def _mit_bemerkung(stand: Buchplanung, isbn: str, bemerkung: str | None) -> Buchplanung:
    """Setzt die Bemerkung eines Buchs; eine leere fällt aus der Liste."""
    if bemerkung is None:
        return stand
    andere = tuple(b for b in stand.bemerkungen if b.isbn != isbn)
    text = bemerkung.strip()
    return _ersetzt(
        stand, bemerkungen=andere + ((Buchbemerkung(isbn=isbn, bemerkung=text),) if text else ()),
    )


def setze_buchreihe(stand: Buchplanung, *, isbn: str, eingabe: Buchreiheneingabe) -> Buchplanung:
    """Ändert Titel, Verlag, Preise und Bemerkung eines Buchs - in der Datei, nicht in IServ.

    Die Datei ist das Soll: die Eingabe gilt, wie sie ist, und ein leerer Preis
    ist leer. Was IServ davon abweichend nennt, zeigt der Vergleich auf den
    Seiten. Bis 2026-09-25 merkte sich die Datei zu jedem geänderten Feld den
    IServ-Wert als Kommentar, und ein leerer Preis hieß „wie in IServ“.
    """
    buch = _geprueftes_buch(stand, isbn)
    titel, verlag = _gepruefte_buchreihe(eingabe)
    neues_buch = replace(
        buch, titel=titel, verlag=verlag,
        neupreis=_cent(eingabe.neupreis), leihgebuehr=_cent(eingabe.leihgebuehr),
    )
    neu = _ersetzt(
        stand, buecher=tuple(neues_buch if b.isbn == isbn else b for b in stand.buecher),
    )
    return _mit_bemerkung(neu, isbn, eingabe.bemerkung)


def _gepruefte_isbn(stand: Buchplanung, eingabe: str) -> str:
    """Die ISBN, so wie die Datei sie führt - oder als ISBN-13, wenn sie neu ist.

    Verglichen wird ohne Bindestriche und Leerzeichen: „978-3-06-000000-5“ ist
    dasselbe Buch wie „9783060000005“. Eine neue ISBN muss eine gültige sein -
    ein Zahlendreher ergäbe sonst ein zweites Buch neben dem richtigen.
    """
    if not (eingabe or "").strip():
        raise UngueltigeEingabe("Bitte die ISBN eintragen.")
    # Nicht isbnlib.canonical: das gibt bei einer zu kurzen Eingabe "" zurück,
    # und der Satz hieße dann „bitte eintragen“ statt „ungültig“.
    roh = re.sub(r"[^0-9X]", "", eingabe.upper())
    for buch in stand.buecher:
        if re.sub(r"[^0-9X]", "", buch.isbn.upper()) in (roh, isbnlib.to_isbn13(roh) or roh):
            return buch.isbn
    if isbnlib.is_isbn10(roh):
        return isbnlib.to_isbn13(roh)
    if isbnlib.is_isbn13(roh):
        return roh
    raise UngueltigeEingabe(
        f"„{eingabe.strip()}“ ist keine gültige ISBN. Bitte die 13 (oder 10) Ziffern "
        "vom Buchrücken prüfen."
    )


def fuege_buch_hinzu(
    stand: Buchplanung, *, isbn: str, fach: str, buchreihe: Buchreiheneingabe,
    zeilen: Sequence[Jahrgangseingabe],
) -> Buchplanung:
    """Nimmt ein Buch in die Bücherliste eines Fachs auf, in dem es noch nicht steht.

    Zwei Fälle, ein Menü:

    * Die ISBN steht schon in der Datei - das Buch gehört zu einem anderen Fach
      oder stand im Vorjahr auf einer Liste. Titel, Verlag und Preise sind dann
      die bekannten; was davon abweicht, gilt wie im Bearbeiten-Menü
      (:func:`setze_buchreihe`).
    * Die ISBN ist neu. Das Buch steht dann nur in der Datei und bleibt beim
      Abgleich, solange es einen Jahrgang hat.

    In das Fach kommt es über seine Jahrgänge. Jeder braucht deshalb ein
    Schuljahr der Einführung: eine Zeile, auf der nichts eingetragen ist,
    verschwindet in :func:`setze_planung` - und mit ihr das Buch aus dem Fach.
    """
    isbn = _gepruefte_isbn(stand, isbn)
    titel, verlag = _gepruefte_buchreihe(buchreihe)
    if not zeilen:
        raise UngueltigeEingabe(
            "Bitte mindestens einen Jahrgang eintragen, in dem das Buch eingeführt wird."
        )
    neue: list[Planungszeile] = []
    for eingabe in zeilen:
        if not eingabe.eingefuehrt_ab.strip():
            raise UngueltigeEingabe(
                f"Bitte für Jahrgang {eingabe.jahrgang} das Schuljahr der Einführung "
                "eintragen."
            )
        neue.append(_neue_zeile(
            None, isbn=isbn, fach=fach, jahrgang=eingabe.jahrgang,
            eingefuehrt_ab=eingabe.eingefuehrt_ab, ausgemustert_nach=eingabe.ausgemustert_nach,
            bemerkung=eingabe.bemerkung, leihbar=bool(eingabe.leihbar),
        ))
    _pruefe_zeitraeume(neue)

    buch = stand.buch(isbn)
    if buch is None:
        neu = _ersetzt(stand, buecher=stand.buecher + (Buch(
            isbn=isbn, titel=titel, verlag=verlag,
            neupreis=_cent(buchreihe.neupreis), leihgebuehr=_cent(buchreihe.leihgebuehr),
        ),))
        neu = _mit_bemerkung(neu, isbn, buchreihe.bemerkung)
    else:
        if fach in buch.faecher or any(
                z.isbn == isbn and z.fach == fach for z in stand.planung):
            raise UngueltigeEingabe(
                f"„{buch.titel}“ gehört schon zum Fach {fach} - in der Bücherliste oder "
                "unter den Ausmusterungen. Bitte dort in seiner Zeile bearbeiten."
            )
        neu = setze_buchreihe(stand, isbn=isbn, eingabe=buchreihe)

    return _mit_planung(neu, isbn, neu.planung + tuple(neue))


def bestaetige_fach(
    stand: Buchplanung, *, fach: str, kuerzel: str, datum: date | None,
) -> tuple[Buchplanung, int]:
    """Setzt Kürzel und Datum in **alle** Zeilen eines Fachs.

    Die Fachkonferenzleitung gibt ihre Liste als Ganzes frei. Bestätigt
    wird aber je Zeile, und genau deshalb braucht es keinen zweiten Zustand
    "bestätigter Stand": kommt später ein Buch dazu, ist seine Zeile leer, und
    das Fach ist wieder nur teilweise bestätigt.

    Ein leeres Kürzel nimmt die Bestätigung des ganzen Fachs zurück.
    """
    if fach not in stand.faecher:
        raise UngueltigeEingabe(f"„{fach}“ kommt in dieser Datei als Fach nicht vor.")
    isbns = {buch.isbn for buch in stand.buecher_je_fach(fach)}
    geaendert = 0
    planung: list[Planungszeile] = []
    for zeile in stand.planung:
        if zeile.fach == fach and zeile.isbn in isbns:
            zeile = replace(zeile, kuerzel=kuerzel.strip(), datum=datum)
            geaendert += 1
        planung.append(zeile)
    return _ersetzt(stand, planung=tuple(planung)), geaendert


def entscheide_antrag(
    stand: Buchplanung, *, isbn: str, fach: str, jahrgang: int, art: str,
    ergebnis: str | None, kuerzel: str = "", datum: date | None = None,
    begruendung: str | None = None, heute: date | None = None,
    eingefuehrt_ab: str | None = None,
) -> Buchplanung:
    """Genehmigt oder lehnt den Antrag auf Einführung oder Ausmusterung einer Zeile ab.

    ``eingefuehrt_ab`` wählt die Zeile, wenn der Jahrgang mehrere hat (nach
    einem Wechsel von „leihbar“); ohne gilt die erste mit einem Antrag dieser Art.

    ``ergebnis`` ist ``genehmigt``, ``abgelehnt`` oder leer - leer setzt den
    Antrag zurück auf offen. ``None`` lässt die Entscheidung stehen; so
    speichert die Änderungsliste auch nur die Begründung. ``begruendung``
    ``None`` lässt sie ebenso stehen.

    Entschieden wird mit Kürzel; ein fehlendes Datum ist heute. Alles andere an
    der Zeile - Schuljahre, Bestätigung der Fachkonferenzleitung, Bemerkung -
    bleibt, wie es ist.
    """
    if art not in (ART_EINFUEHRUNG, ART_AUSMUSTERUNG):
        raise UngueltigeEingabe(
            f"„{art}“ ist keine Art von Antrag. Möglich sind: Einführung, Ausmusterung."
        )
    buch = _geprueftes_buch(stand, isbn)
    if eingefuehrt_ab is not None:
        zeile = stand.planungszeile(isbn, fach, jahrgang, eingefuehrt_ab)
    else:
        zeile = next((z for z in stand.zeilen_des_paars(isbn, fach, jahrgang)
                      if z.schuljahr_des_antrags(art)), None)
    wort = "Einführung" if art == ART_EINFUEHRUNG else "Ausmusterung"
    if zeile is None or not zeile.schuljahr_des_antrags(art):
        raise UngueltigeEingabe(
            f"Für „{buch.titel}“ ist in {fach}, Jahrgang {jahrgang} keine {wort} "
            "eingetragen. Bitte die Seite neu laden."
        )

    entscheidung = zeile.antrag(art)
    if ergebnis is not None:
        ergebnis = ergebnis.strip().casefold()
        if not ergebnis:
            entscheidung = Antragsentscheidung()
        elif ergebnis not in ANTRAG_ERGEBNISSE:
            raise UngueltigeEingabe(
                f"„{ergebnis}“ ist keine Entscheidung. Möglich sind: "
                + ", ".join(ANTRAG_ERGEBNISSE) + "."
            )
        elif not kuerzel.strip():
            raise UngueltigeEingabe(
                "Bitte oben das Kürzel eintragen, mit dem entschieden wird."
            )
        else:
            entscheidung = Antragsentscheidung(
                ergebnis=ergebnis, kuerzel=kuerzel.strip(),
                datum=datum or heute or date.today(),
            )

    neue_zeile = replace(
        zeile,
        antrag_einfuehrung=entscheidung if art == ART_EINFUEHRUNG else zeile.antrag_einfuehrung,
        antrag_ausmusterung=entscheidung if art == ART_AUSMUSTERUNG
        else zeile.antrag_ausmusterung,
        begruendung=zeile.begruendung if begruendung is None else begruendung.strip(),
    )
    return _ersetzt(stand, planung=tuple(
        neue_zeile if z is zeile else z for z in stand.planung))


def setze_ruecklage(
    stand: Buchplanung, *, isbn: str, fach: str, anzahl: int | None, status: str = "",
    kuerzel: str = "", datum: date | None = None, bemerkung: str = "",
) -> Buchplanung:
    """Hält fest, wie viele Exemplare eine Fachschaft behalten möchte.

    Nur für Bücher, die die Schule verleiht oder im Vorjahr verliehen hat
    (irgendeine Zeile des Buchs ist leihbar - auch eine ausgemusterte,
    :meth:`Buchplanung.leihbar`). Ein Kaufbuch liegt in
    keinem Regal der Schule; Exemplare davon zurückzulegen ist nichts, was die
    Schule entscheiden könnte.

    Eine **leere** Eintragung bleibt für jedes Buch erlaubt: sonst ließe sich
    ein Wunsch, der vor dieser Regel eingetragen wurde, nie wieder löschen.
    """
    buch = _geprueftes_buch(stand, isbn)
    _geprueftes_fach(stand, buch, fach)
    if not stand.leihbar(isbn) and (anzahl or status.strip() or bemerkung.strip()):
        raise UngueltigeEingabe(
            f"Für „{buch.titel}“ lässt sich nichts zurücklegen: die Schule verleiht "
            "das Buch nicht und hat auch im Vorjahr keine Exemplare davon verliehen."
        )
    if anzahl is not None and not 0 <= anzahl <= 2000:
        raise UngueltigeEingabe(
            f"„{anzahl}“ ist keine sinnvolle Anzahl. Erwartet wird 0 bis 2000."
        )
    if status and status not in RUECKLAGE_STATUS:
        raise UngueltigeEingabe(
            f"„{status}“ ist kein Rücklage-Status. Möglich sind: "
            + ", ".join(RUECKLAGE_STATUS) + "."
        )
    if anzahl is not None and anzahl > 0 and not status:
        status = RUECKLAGE_GEWUENSCHT

    eintrag = Ruecklage(isbn=isbn, fach=fach, anzahl=anzahl, status=status,
                        kuerzel=kuerzel.strip(), datum=datum, bemerkung=bemerkung.strip())
    neuer = None if eintrag.leer else eintrag
    return _ersetzt(
        stand,
        ruecklagen=_ersetze(stand.ruecklagen,
                            lambda e: e.isbn == isbn and e.fach == fach, neuer),
    )


def _ersetzt(stand: Buchplanung, **felder: Any) -> Buchplanung:
    """Eine Kopie des Stands mit geänderten Feldern - Dataclasses sind eingefroren."""
    return replace(stand, **felder)
