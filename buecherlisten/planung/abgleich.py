"""Den Stand aus IServ mit dem zusammenführen, was von Hand eingetragen wurde -
und die einzelnen Eintragungen vornehmen.

Der Abgleich ist die Stelle, an der die beiden Wahrheiten aufeinandertreffen:

* **IServ** sagt, welche Bücher es gibt, in welchen Fächern und Jahrgängen und
  zu welchem Preis. Das wird bei jedem Abgleich frisch übernommen.
* **Die Datei** sagt, was bemerkt, bestätigt, geplant und zurückgelegt wurde.
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

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from math import isfinite
from typing import Any, TypeVar

from .laden import Schnappschuss
from .modelle import (
    ISERV_FELD,
    OHNE_FACH,
    RUECKLAGE_GEWUENSCHT,
    RUECKLAGE_STATUS,
    Buch,
    Buchbemerkung,
    Buchplanung,
    Planungszeile,
    Ruecklage,
    UngueltigesSchuljahr,
    schuljahr_zahl,
    wirkt_im_schuljahr,
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

    Der Schlüssel ist jeweils der seines Blatts: die ISBN bei der Bemerkung,
    (ISBN, Fach, Jahrgang) bei der Planung, (ISBN, Fach) bei der Rücklage.
    Fällt die ISBN weg, fällt die Eintragung weg - mit einer Warnung, die in der
    Datei landet. Fach und Jahrgang einer Planungszeile werden **nicht** geprüft:
    „wird ab 2028/29 auch in Jahrgang 9 eingeführt" ist gerade die Zeile, die es
    in keiner Bücherliste gibt.
    """
    alt = vorher or Buchplanung()
    bekannt = {buch.isbn for buch in schnappschuss.buecher}
    warnungen: list[str] = list(schnappschuss.warnungen)

    def verloren(was: str, isbn: str) -> None:
        warnungen.append(
            f"{was} zu ISBN {isbn} wurde verworfen: das Buch steht weder im "
            f"Schuljahr {schnappschuss.schuljahr} noch als leihbares Buch im "
            f"Vorjahr {schnappschuss.vorjahr} in einer Bücherliste."
        )

    bemerkungen: list[Buchbemerkung] = []
    for eintrag in alt.bemerkungen:
        if eintrag.isbn in bekannt:
            bemerkungen.append(eintrag)
        else:
            verloren("Die Bemerkung", eintrag.isbn)

    planung: list[Planungszeile] = []
    for zeile in alt.planung:
        if zeile.isbn in bekannt:
            planung.append(zeile)
        else:
            verloren("Die Planungszeile", zeile.isbn)

    # Was im Vorjahr in einer Liste stand und heuer nicht mehr, ist nach dem
    # Vorjahr ausgemustert. Ein von Hand eingetragener Wert bleibt.
    for buch in schnappschuss.buecher:
        for fach, jahrgang in buch.ausgemustert:
            bisher = next((i for i, z in enumerate(planung)
                           if (z.isbn, z.fach, z.jahrgang) == (buch.isbn, fach, jahrgang)), None)
            if bisher is None:
                planung.append(Planungszeile(isbn=buch.isbn, fach=fach, jahrgang=jahrgang,
                                             ausgemustert_nach=schnappschuss.vorjahr))
            elif not planung[bisher].ausgemustert_nach:
                planung[bisher] = replace(planung[bisher],
                                          ausgemustert_nach=schnappschuss.vorjahr)

    ruecklagen: list[Ruecklage] = []
    for wunsch in alt.ruecklagen:
        if wunsch.isbn in bekannt:
            ruecklagen.append(wunsch)
        else:
            verloren("Der Rücklage-Wunsch", wunsch.isbn)

    # Korrigierte Titel, Verlage und Preise bleiben - gegen den frischen Wert
    # aus IServ. Nennt IServ inzwischen selbst den korrigierten Wert, ist die
    # Korrektur erledigt und fällt weg.
    buecher: list[Buch] = []
    for buch in schnappschuss.buecher:
        altes = alt.buch(buch.isbn)
        korrigiert = {feld: getattr(altes, feld) for feld in altes.korrigiert} if altes else {}
        buecher.append(_mit_korrekturen(buch, korrigiert))
    for altes in alt.buecher:
        if altes.korrigiert and altes.isbn not in bekannt:
            verloren("Die Korrektur", altes.isbn)

    neu = Buchplanung(
        schuljahr=schnappschuss.schuljahr,
        vorjahr=schnappschuss.vorjahr,
        stand=schnappschuss.stand,
        buecher=tuple(buecher),
        bemerkungen=tuple(bemerkungen),
        planung=tuple(planung),
        ruecklagen=tuple(ruecklagen),
        warnungen=tuple(warnungen),
    )
    return neu


def _gleich(a: object, b: object) -> bool:
    """Gleich im Sinn einer Korrektur: Preise auf den Cent, Texte ohne Randleerzeichen."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return round(float(a), 2) == round(float(b), 2)
    if isinstance(a, str) and isinstance(b, str):
        return a.strip() == b.strip()
    return a == b


def _mit_korrekturen(buch: Buch, korrigiert: dict[str, object]) -> Buch:
    """Das Buch aus IServ, mit den korrigierten Feldern darüber.

    ``buch`` trägt die Werte aus IServ; sie wandern nach ``iserv``, soweit ein
    Feld korrigiert ist. Ein Feld, dessen Korrektur dem IServ-Wert gleicht,
    ist nicht korrigiert.
    """
    felder: dict[str, Any] = {}
    iserv: list[tuple[str, object]] = []
    for feld in ISERV_FELD:
        if feld not in korrigiert:
            continue
        original = getattr(buch, feld)
        if _gleich(korrigiert[feld], original):
            continue
        felder[feld] = korrigiert[feld]
        iserv.append((feld, original))
    return replace(buch, iserv=tuple(iserv), **felder)


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
    bemerkung: str = "",
) -> Buchplanung:
    """Trägt für **ein** Buch in **einem** Fach und Jahrgang die Zeile ein.

    Der Jahrgang muss nicht der eines heutigen Vorkommens sein: "wird ab
    2028/29 auch in Jahrgang 9 eingeführt" ist genau der Fall, für den es
    diese Zeile gibt. Ist alles leer, verschwindet die Zeile wieder.

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


@dataclass(frozen=True)
class Jahrgangseingabe:
    """Eine Zeile des Planungsmenüs: ein Jahrgang mit seinen beiden Schuljahren.

    Ohne ``kuerzel`` und ``datum``: bestätigt wird nicht je Zeile, sondern die
    Liste als Ganzes über :func:`bestaetige_fach` (der Knopf „Liste bestätigen“
    oben auf der Fach-Seite).
    """

    jahrgang: int
    eingefuehrt_ab: str = ""
    ausgemustert_nach: str = ""
    bemerkung: str = ""


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
    was nicht mitgeschickt wird, hat der Benutzer im Menü gelöscht.

    ``kuerzel`` und ``datum`` der Fachkonferenzleitung kommen nicht aus dem
    Menü, gehen aber auch nicht verloren. Sie bleiben genau dann stehen, wenn
    die Änderung das **laufende** Schuljahr nicht berührt
    (:func:`~buecherlisten.planung.modelle.wirkt_im_schuljahr`): eine
    Ausmusterung, die erst in drei Jahren greift, ändert nichts an der Liste,
    die bestätigt wurde. Wird ein Buch dagegen ab sofort eingeführt oder ist es
    ab sofort weg, fällt die Bestätigung dieser Zeile - und damit das Fach auf
    "teilweise".
    """
    buch = _geprueftes_buch(stand, isbn)
    _geprueftes_fach(stand, buch, fach)

    neu = stand
    gesehen: set[int] = set()
    for eingabe in zeilen:
        if eingabe.jahrgang in gesehen:
            raise UngueltigeEingabe(
                f"Jahrgang {eingabe.jahrgang} steht zweimal in der Liste. Jeder "
                "Jahrgang darf nur einmal vorkommen."
            )
        gesehen.add(eingabe.jahrgang)
        vorher = stand.planungszeile(isbn, fach, eingabe.jahrgang)

        def eintragen(basis: Buchplanung, kuerzel: str, datum: date | None,
                      eingabe: Jahrgangseingabe = eingabe) -> Buchplanung:
            return setze_planung(
                basis, isbn=isbn, fach=fach, jahrgang=eingabe.jahrgang,
                eingefuehrt_ab=eingabe.eingefuehrt_ab,
                ausgemustert_nach=eingabe.ausgemustert_nach,
                kuerzel=kuerzel, datum=datum, bemerkung=eingabe.bemerkung,
            )

        # Erst mit behaltener Bestätigung eintragen - dieser Aufruf prüft auch
        # die Schuljahresangaben. Erst danach steht fest, ob sie bleiben darf.
        neu = eintragen(neu, vorher.kuerzel if vorher else "", vorher.datum if vorher else None)
        if vorher is not None and vorher.bestaetigt:
            nachher = neu.planungszeile(isbn, fach, eingabe.jahrgang)
            if (wirkt_im_schuljahr(vorher, stand.schuljahr)
                    != wirkt_im_schuljahr(nachher, stand.schuljahr)):
                neu = eintragen(neu, "", None)

    for zeile in stand.planung:
        if zeile.isbn == isbn and zeile.fach == fach and zeile.jahrgang not in gesehen:
            # Alles leer heißt in setze_planung: die Zeile verschwindet.
            neu = setze_planung(neu, isbn=isbn, fach=fach, jahrgang=zeile.jahrgang)

    if ruecklage is not None:
        vorher_r = stand.ruecklage(isbn, fach)
        neu = setze_ruecklage(
            neu, isbn=isbn, fach=fach, anzahl=ruecklage.anzahl,
            status=vorher_r.status if vorher_r else "",
            kuerzel=vorher_r.kuerzel if vorher_r else "",
            datum=vorher_r.datum if vorher_r else None,
            bemerkung=ruecklage.bemerkung,
        )
    return neu


@dataclass(frozen=True)
class Buchreiheneingabe:
    """Der Block „Buchreihe“ des Planungsmenüs - die korrigierbaren Felder.

    Ohne ISBN: sie ist der Schlüssel des Buchs und steht im Menü nur zum
    Lesen. Ein leerer Preis heißt: gilt wie in IServ.
    """

    titel: str
    verlag: str
    neupreis: float | None = None
    leihgebuehr: float | None = None


# Ein Preis, den es für ein Schulbuch geben kann. Geprüft wird wie beim
# Jahrgang nur gegen Tippfehler.
_PREIS_BIS = 10_000.0


def setze_buchreihe(stand: Buchplanung, *, isbn: str, eingabe: Buchreiheneingabe) -> Buchplanung:
    """Korrigiert Titel, Verlag und Preise eines Buchs - in der Datei, nicht in IServ.

    Die Datei kennt zu jedem korrigierten Feld den Wert aus IServ
    (``Buch.iserv``, in der Mappe als Kommentar an der Zelle); zu jedem
    anderen ist der heutige Wert der aus IServ. Damit gilt je Feld: gleicht
    die Eingabe dem IServ-Wert, ist das Feld nicht (mehr) korrigiert, sonst
    gilt die Eingabe. Ein leerer Preis setzt auf IServ zurück.
    """
    buch = _geprueftes_buch(stand, isbn)
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

    # Erst zurück auf IServ, dann die Eingabe darüber: so entscheidet
    # _mit_korrekturen an einer Stelle, was als Korrektur gilt - hier genauso
    # wie beim Abgleich.
    zurueck: dict[str, Any] = buch.korrigiert
    aus_iserv = replace(buch, iserv=(), **zurueck)
    eingegeben: dict[str, object] = {"titel": titel, "verlag": verlag}
    for feld, betrag in (("neupreis", eingabe.neupreis), ("leihgebuehr", eingabe.leihgebuehr)):
        if betrag is not None:
            eingegeben[feld] = round(betrag, 2)
    neues_buch = _mit_korrekturen(aus_iserv, eingegeben)
    return _ersetzt(
        stand, buecher=tuple(neues_buch if b.isbn == isbn else b for b in stand.buecher),
    )


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
    """Hält fest, wie viele Exemplare eine Fachschaft behalten möchte.

    Nur für Bücher, die die Schule verleiht oder im Vorjahr verliehen hat
    (``buch.leihbar`` - der Schnappschuss trägt dort den Wert aus dem Jahr ein,
    in dem das Buch zuletzt vorkam, siehe ``laden.py``). Ein Kaufbuch liegt in
    keinem Regal der Schule; Exemplare davon zurückzulegen ist nichts, was die
    Schule entscheiden könnte.

    Eine **leere** Eintragung bleibt für jedes Buch erlaubt: sonst ließe sich
    ein Wunsch, der vor dieser Regel eingetragen wurde, nie wieder löschen.
    """
    buch = _geprueftes_buch(stand, isbn)
    _geprueftes_fach(stand, buch, fach)
    if not buch.leihbar and (anzahl or status.strip() or bemerkung.strip()):
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
