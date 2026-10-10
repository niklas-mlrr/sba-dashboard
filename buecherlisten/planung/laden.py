"""Zwei Schuljahre aus IServ holen und zu einer Buchliste zusammenlegen.

Rein lesend (nur GET). Gebraucht werden das laufende Schuljahr und sein
Vorjahr: erst ihr Unterschied zeigt, was ausgemustert wurde, und genau für
ausgemusterte Bücher wird eine Rücklage beantragt.

**Welche Bücher in die Datei kommen** (Entscheidung 2026-09-20):

* aus dem laufenden Schuljahr **alle**,
* aus dem Vorjahr nur die **leihbaren**.

Ein nicht-leihbares Buch kauft die Familie selbst. Ist es aus der Bücherliste
verschwunden, gibt es daran nichts mehr zu planen: die Schule hat kein Exemplar
im Bestand, das ausgemustert oder für eine Fachschaft zurückgelegt werden
könnte. Ein leihbares Buch des Vorjahres liegt dagegen im Regal, und genau
darum steht es weiter in der Datei.

Die Bücherlisten selbst holt ``buecherlisten.core.daten`` - dasselbe Modul, das
auch die Bücherlisten-Seiten und die PDF-Erzeugung speist. Ein zweiter Abruf
mit eigener Auswertung wäre eine zweite Stelle, an der sich IServ-Feldnamen
ändern können.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..core.daten import (
    OHNE_VERLAG,
    SchuljahreClient,
    hole_jahrgangslisten,
    sammle_je_fach_und_isbn,
    sammle_je_isbn,
    vorjahr_kennung,
)
from .modelle import Buch

# Was von ``ausleihe.AusleiheClient`` hier gebraucht wird: die Schuljahre, und
# sonst nichts. Der Name bleibt ``AusleiheClient``, weil ihn das Dashboard so
# importiert; das Protokoll selbst steht bei den Bücherlisten, damit es nicht
# zweimal formuliert wird.
AusleiheClient = SchuljahreClient


@dataclass(frozen=True)
class Schnappschuss:
    """Was IServ zu zwei Schuljahren sagt - der Eingabestand des Abgleichs.

    ``schuljahr`` ist die **Kennung** (``"2026/2027"``), nicht der Anzeigename
    (``"Schuljahr 26/27"``). Beides kommt aus demselben Objekt und sieht
    ähnlich aus, ist aber nicht dasselbe: die Kennung adressiert das Schuljahr
    in IServ, steht im Dateinamen und wird mit anderen Schuljahren verglichen
    (``Einführung``, ``Ausmusterung nach Schuljahr``). Der Name ist nur
    Beschriftung - und könnte morgen "SJ 2026/27" heißen, ohne dass sich etwas
    ändert.
    """

    schuljahr: str
    vorjahr: str
    buecher: tuple[Buch, ...]
    stand: date
    name: str = ""
    warnungen: tuple[str, ...] = ()


def _kennung_und_name(client: AusleiheClient, kennung: str | None) -> tuple[str, str]:
    if kennung:
        kopf = client.schoolyears.get_by_id(kennung)
        return kennung, str(kopf.get("name") or kennung)
    aktuell = client.schoolyears.get_current()
    kennung = str(aktuell["id"])
    return kennung, str(aktuell.get("name") or kennung)


Paare = dict[str, set[tuple[str, int]]]


def _jahr(client: AusleiheClient, kennung: str) -> tuple[dict[str, dict], Paare, Paare]:
    """Ein Schuljahr einmal holen und zweimal auswerten.

    Zurück kommen die Bücher je ISBN und, je ISBN, die (Fach, Jahrgang)-Paare,
    in denen das Buch in diesem Schuljahr vorkommt - einmal alle, einmal die,
    in denen es leihbar ist (``borrowable`` steht in IServ je Jahrgangsliste).
    """
    listen = hole_jahrgangslisten(client, kennung)
    paare: Paare = {}
    leihbar: Paare = {}
    for (fach, isbn), eintrag in sammle_je_fach_und_isbn(listen).items():
        paare.setdefault(isbn, set()).update((fach, jahrgang) for jahrgang in eintrag["grades"])
        leihbar.setdefault(isbn, set()).update(
            (fach, jahrgang) for jahrgang in eintrag["borrowable_grades"])
    return sammle_je_isbn(listen), paare, leihbar


def lade_schnappschuss(
    client: AusleiheClient,
    *,
    schuljahr: str | None = None,
    vorjahr: str | None = None,
    heute: date | None = None,
) -> Schnappschuss:
    """Beide Schuljahre holen und je ISBN zu einem :class:`Buch` zusammenlegen.

    Fehlt das Vorjahr in IServ (erstes Schuljahr im System), ist das **kein**
    Fehler: der Schnappschuss enthält dann nur das laufende Jahr, und eine
    Warnung sagt, warum keine Ausmusterung erkannt werden konnte.

    Leihbar ist ein Buch je (Fach, Jahrgang); aus dem Vorjahr zählen nur die
    Paare, in denen es leihbar war.
    """
    kennung, name = _kennung_und_name(client, schuljahr)
    warnungen: list[str] = []

    vorjahr_id = vorjahr or vorjahr_kennung(kennung)
    aktuelle, aktuelle_paare, aktuell_leihbar = _jahr(client, kennung)
    try:
        alte, _, alt_leihbar = _jahr(client, vorjahr_id)
    except Exception as exc:  # noqa: BLE001 - jedes Scheitern heißt hier dasselbe
        alte, alt_leihbar = {}, {}
        warnungen.append(
            f"Das Vorjahr {vorjahr_id} ließ sich nicht laden ({exc}); "
            "ausgemusterte Bücher des Vorjahres fehlen deshalb in dieser Datei."
        )

    def sortiert(paare: set[tuple[str, int]]) -> tuple[tuple[str, int], ...]:
        return tuple(sorted(paare, key=lambda paar: (paar[0].casefold(), paar[1])))

    buecher = []
    for isbn in sorted(set(aktuelle) | set(alte)):
        jetzt = aktuelle.get(isbn)
        quelle = jetzt or alte.get(isbn)
        assert quelle is not None  # eine der beiden Seiten hat die ISBN geliefert
        kombinationen = set(aktuelle_paare.get(isbn, ()))
        # Aus dem Vorjahr verschwunden und dort nirgends leihbar: das Buch lag
        # nie im Bestand der Schule, dazu gibt es nichts zu planen.
        ausgemustert = set(alt_leihbar.get(isbn, ())) - kombinationen
        if jetzt is None and not ausgemustert:
            continue
        buecher.append(Buch(
            isbn=isbn,
            titel=str(quelle.get("title") or "?"),
            verlag=str(quelle.get("publisher") or "") or OHNE_VERLAG,
            kombinationen=sortiert(kombinationen | ausgemustert),
            neupreis=_preis(quelle.get("price")),
            leihgebuehr=_preis(quelle.get("fee")),
            ausgemustert=sortiert(ausgemustert),
            leihbar_paare=sortiert(set(aktuell_leihbar.get(isbn, ())) | ausgemustert),
        ))

    return Schnappschuss(
        schuljahr=kennung, vorjahr=vorjahr_id, buecher=tuple(buecher), name=name,
        stand=heute or date.today(), warnungen=tuple(warnungen),
    )


def _preis(roh: object) -> float | None:
    if roh is None or isinstance(roh, bool):
        return None
    try:
        return float(roh)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
