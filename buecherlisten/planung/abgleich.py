"""Den Stand aus IServ mit dem zusammenführen, was von Hand eingetragen wurde -
und die einzelnen Eintragungen vornehmen.

Der Abgleich ist die Stelle, an der die beiden Wahrheiten aufeinandertreffen:

* **IServ** sagt, welche Bücher es gibt, in welchen Fächern und Jahrgängen und
  zu welchem Preis. Das wird bei jedem Abgleich frisch übernommen.
* **Die Datei** sagt, was geprüft, bestätigt, geplant und zurückgelegt wurde.
  Das überlebt jeden Abgleich.

Was verlorengeht, geht nicht stillschweigend verloren: eine Eintragung zu einem
Buch, das in beiden Schuljahren nicht mehr vorkommt, wird verworfen **und** als
Warnung ins Blatt ``Info`` geschrieben.

Alle Funktionen hier geben einen **neuen**
:class:`~buecherlisten.planung.modelle.Buchplanung`-Wert zurück; nichts wird an
Ort und Stelle verändert. Das Speichern (Schloss, ``mtime``, Sicherung) steht im
Dashboard.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from typing import Any, TypeVar

from .laden import Schnappschuss
from .modelle import (
    OHNE_FACH,
    RUECKLAGE_GEWUENSCHT,
    RUECKLAGE_STATUS,
    Buch,
    Buchplanung,
    Planungszeile,
    Preispruefung,
    Ruecklage,
    UngueltigesSchuljahr,
    schuljahr_zahl,
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
    """Übernimmt die Bücher aus IServ und behält alles von Hand Eingetragene.

    Der Schlüssel ist jeweils der seines Blatts: die ISBN bei der Preisprüfung,
    (ISBN, Fach, Jahrgang) bei der Planung, (ISBN, Fach) bei der Rücklage.
    Fällt die ISBN weg, fällt die Eintragung weg - mit einer Warnung, die in der
    Datei landet. Fach und Jahrgang einer Planungszeile werden **nicht** geprüft:
    „wird ab 2028/29 auch in Jahrgang 9 eingeführt" ist gerade die Zeile, die es
    in keiner Bücherliste gibt.
    """
    alt = vorher or Buchplanung()
    bekannt = {buch.isbn for buch in schnappschuss.buecher}
    titel = {buch.isbn: buch.titel for buch in schnappschuss.buecher}
    warnungen: list[str] = list(schnappschuss.warnungen)

    def verloren(was: str, isbn: str) -> None:
        warnungen.append(
            f"{was} zu ISBN {isbn} wurde verworfen: das Buch steht weder im "
            f"Schuljahr {schnappschuss.schuljahr} noch als leihbares Buch im "
            f"Vorjahr {schnappschuss.vorjahr} in einer Bücherliste."
        )

    preise: list[Preispruefung] = []
    for eintrag in alt.preise:
        if eintrag.isbn in bekannt:
            preise.append(eintrag)
        else:
            verloren("Die Preisprüfung", eintrag.isbn)

    planung: list[Planungszeile] = []
    for zeile in alt.planung:
        if zeile.isbn in bekannt:
            planung.append(zeile)
        else:
            verloren("Die Planungszeile", zeile.isbn)

    ruecklagen: list[Ruecklage] = []
    for wunsch in alt.ruecklagen:
        if wunsch.isbn in bekannt:
            ruecklagen.append(wunsch)
        else:
            verloren("Der Rücklage-Wunsch", wunsch.isbn)

    neu = Buchplanung(
        schuljahr=schnappschuss.schuljahr,
        vorjahr=schnappschuss.vorjahr,
        stand=schnappschuss.stand,
        buecher=schnappschuss.buecher,
        preise=tuple(preise),
        planung=tuple(planung),
        ruecklagen=tuple(ruecklagen),
        warnungen=tuple(warnungen),
    )
    return _mit_hinweis_auf_offene_preise(neu, titel)


def _mit_hinweis_auf_offene_preise(stand: Buchplanung, titel: dict[str, str]) -> Buchplanung:
    """Ergänzt eine Warnung, wenn Bücher ohne geprüften Preis in der Datei stehen.

    Kein neuer Zustand, nur ein Satz: die Preisprüfung eines neu eingeführten
    Buchs ist genau der Schritt, der nach einer Fachkonferenz vergessen wird.
    """
    geprueft = {eintrag.isbn for eintrag in stand.preise if eintrag.preis is not None}
    offen = [buch for buch in stand.buecher if buch.isbn not in geprueft]
    if not offen:
        return stand
    namen = ", ".join(sorted(titel.get(buch.isbn, buch.isbn) for buch in offen)[:5])
    mehr = "" if len(offen) <= 5 else f" und {len(offen) - 5} weitere"
    hinweis = f"{len(offen)} Buch/Bücher haben noch keinen geprüften Preis: {namen}{mehr}."
    return replace(stand, warnungen=stand.warnungen + (hinweis,))


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


def setze_preis(
    stand: Buchplanung, *, isbn: str, preis: float | None, kuerzel: str,
    datum: date | None, bemerkung: str = "",
) -> Buchplanung:
    """Trägt den gegen die Verlagsliste geprüften Preis eines Buchs ein.

    ``preis=None`` löscht die Prüfung - das ist der Weg zurück auf "offen",
    wenn jemand versehentlich bestätigt hat.
    """
    _geprueftes_buch(stand, isbn)
    if preis is not None and (preis < 0 or preis > 1000):
        raise UngueltigeEingabe(
            f"„{preis}“ ist kein Buchpreis. Erwartet wird ein Betrag zwischen 0 und 1000 €."
        )
    neuer = None if preis is None and not kuerzel.strip() and not bemerkung.strip() else (
        Preispruefung(isbn=isbn, preis=preis, kuerzel=kuerzel.strip(),
                      datum=datum, bemerkung=bemerkung.strip())
    )
    return _ersetzt(stand, preise=_ersetze(stand.preise, lambda e: e.isbn == isbn, neuer))


def setze_preise_des_verlags(
    stand: Buchplanung, *, verlag: str, kuerzel: str, datum: date | None,
) -> tuple[Buchplanung, int]:
    """Bestätigt **alle** Preise eines Verlags zum Preis, der in IServ steht.

    Das ist der Knopf neben dem Drucker in der Verlags-Ansicht: wer die
    Verlagsliste einmal durchgegangen ist, soll nicht zwanzigmal klicken.
    Gespeichert wird trotzdem je Buch der Betrag, nicht ein Sammelhaken -
    sonst fiele eine spätere Preisänderung nicht mehr auf.
    """
    buecher = stand.buecher_je_verlag(verlag)
    if not buecher:
        raise UngueltigeEingabe(f"„{verlag}“ kommt in dieser Datei als Verlag nicht vor.")
    neu = stand
    geaendert = 0
    for buch in buecher:
        if buch.neupreis is None:
            continue
        neu = setze_preis(neu, isbn=buch.isbn, preis=buch.neupreis,
                          kuerzel=kuerzel, datum=datum,
                          bemerkung=_vorhandene_bemerkung(stand, buch.isbn))
        geaendert += 1
    return neu, geaendert


def _vorhandene_bemerkung(stand: Buchplanung, isbn: str) -> str:
    eintrag = stand.pruefung(isbn)
    return eintrag.bemerkung if eintrag else ""


def setze_planung(
    stand: Buchplanung, *, isbn: str, fach: str, jahrgang: int, eingefuehrt_ab: str = "",
    ausgemustert_nach: str = "", kuerzel: str = "", datum: date | None = None,
    bemerkung: str = "",
) -> Buchplanung:
    """Trägt für **ein** Buch in **einem** Fach und Jahrgang die Zeile ein.

    Der Jahrgang muss nicht der eines heutigen Vorkommens sein: "wird ab
    2028/29 auch in Jahrgang 9 eingeführt" ist genau der Fall, für den es
    diese Zeile gibt. Ist alles leer, verschwindet die Zeile wieder.

    Die Ausmusterung gilt nur für **leihbare** Bücher: ein Buch, das die
    Familien selbst kaufen, liegt nicht im Bestand der Schule und wird dort
    auch nicht ausgemustert. Ohne diese Prüfung stünde in der Spalte ein
    Schuljahr, aus dem niemand eine Handlung ableiten könnte.
    """
    buch = _geprueftes_buch(stand, isbn)
    _geprueftes_fach(stand, buch, fach)
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
    if nach and not buch.leihbar:
        raise UngueltigeEingabe(
            f"„{buch.titel}“ ist kein Leihbuch und wird deshalb nicht ausgemustert - "
            "die Familien kaufen es selbst. Die Ausmusterung bleibt leer."
        )
    if ab and nach and schuljahr_zahl(nach) < schuljahr_zahl(ab):
        raise UngueltigeEingabe(
            f"Das Buch kann nicht nach {nach} ausgemustert werden, wenn es erst "
            f"ab {ab} eingeführt wird."
        )

    zeile = Planungszeile(isbn=isbn, fach=fach, jahrgang=jahrgang, eingefuehrt_ab=ab,
                          ausgemustert_nach=nach, kuerzel=kuerzel.strip(), datum=datum,
                          bemerkung=bemerkung.strip())
    neuer = None if zeile.leer else zeile
    return _ersetzt(
        stand,
        planung=_ersetze(
            stand.planung,
            lambda e: e.isbn == isbn and e.fach == fach and e.jahrgang == jahrgang,
            neuer,
        ),
    )


def bestaetige_fach(
    stand: Buchplanung, *, fach: str, kuerzel: str, datum: date | None,
) -> tuple[Buchplanung, int]:
    """Setzt Kürzel und Datum in **alle** Zeilen eines Fachs.

    Die Fachkonferenzleitung gibt ihre Liste als Ganzes frei - dieselbe
    Sammelgeste wie :func:`setze_preise_des_verlags` beim Verlag. Bestätigt
    wird aber je Zeile, und genau deshalb braucht es keinen zweiten Zustand
    "bestätigter Stand": kommt später ein Buch dazu, ist seine Zeile leer, und
    das Fach ist wieder nur teilweise bestätigt.

    Ein leeres Kürzel nimmt die Bestätigung des ganzen Fachs zurück.
    """
    if fach not in stand.faecher:
        raise UngueltigeEingabe(f"„{fach}“ kommt in dieser Datei als Fach nicht vor.")
    neu = stand
    geaendert = 0
    for buch in stand.buecher_je_fach(fach):
        for eigenes, jahrgang in stand.zeilen_des_buchs(buch):
            if eigenes != fach:
                continue
            vorher = stand.planungszeile(buch.isbn, fach, jahrgang)
            neu = setze_planung(
                neu, isbn=buch.isbn, fach=fach, jahrgang=jahrgang,
                eingefuehrt_ab=vorher.eingefuehrt_ab if vorher else "",
                ausgemustert_nach=vorher.ausgemustert_nach if vorher else "",
                kuerzel=kuerzel, datum=datum,
                bemerkung=vorher.bemerkung if vorher else "",
            )
            geaendert += 1
    return neu, geaendert


def setze_ruecklage(
    stand: Buchplanung, *, isbn: str, fach: str, anzahl: int | None, status: str = "",
    kuerzel: str = "", datum: date | None = None, bemerkung: str = "",
) -> Buchplanung:
    """Hält fest, wie viele Exemplare eine Fachschaft behalten möchte."""
    buch = _geprueftes_buch(stand, isbn)
    _geprueftes_fach(stand, buch, fach)
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
