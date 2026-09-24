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
    Korrekturen,
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


def _jahr(
    client: AusleiheClient, kennung: str, korrekturen: Korrekturen | None = None,
) -> tuple[dict[str, dict], dict[str, set[tuple[str, int]]]]:
    """Ein Schuljahr einmal holen und zweimal auswerten.

    Zurück kommen die Bücher je ISBN und, je ISBN, die (Fach, Jahrgang)-Paare,
    in denen das Buch in diesem Schuljahr vorkommt.
    """
    listen = hole_jahrgangslisten(client, kennung, korrekturen)
    paare: dict[str, set[tuple[str, int]]] = {}
    for (fach, isbn), eintrag in sammle_je_fach_und_isbn(listen).items():
        paare.setdefault(isbn, set()).update((fach, jahrgang) for jahrgang in eintrag["grades"])
    return sammle_je_isbn(listen), paare


def lade_schnappschuss(
    client: AusleiheClient,
    *,
    schuljahr: str | None = None,
    vorjahr: str | None = None,
    heute: date | None = None,
    korrekturen: Korrekturen | None = None,
) -> Schnappschuss:
    """Beide Schuljahre holen und je ISBN zu einem :class:`Buch` zusammenlegen.

    ``korrekturen`` (aus der bisherigen Datei) wirken schon auf die Rohdaten
    beider Jahre: der Schnappschuss führt ein Buch mit korrigierter ISBN unter
    dieser, und alles daran Eingetragene findet beim Zusammenführen seinen
    Schlüssel wieder.

    Fehlt das Vorjahr in IServ (erstes Schuljahr im System), ist das **kein**
    Fehler: der Schnappschuss enthält dann nur das laufende Jahr, und eine
    Warnung sagt, warum keine Ausmusterung erkannt werden konnte.
    """
    kennung, name = _kennung_und_name(client, schuljahr)
    warnungen: list[str] = []

    vorjahr_id = vorjahr or vorjahr_kennung(kennung)
    aktuelle, aktuelle_paare = _jahr(client, kennung, korrekturen)
    try:
        alte, alte_paare = _jahr(client, vorjahr_id, korrekturen)
    except Exception as exc:  # noqa: BLE001 - jedes Scheitern heißt hier dasselbe
        alte, alte_paare = {}, {}
        warnungen.append(
            f"Das Vorjahr {vorjahr_id} ließ sich nicht laden ({exc}); "
            "ausgemusterte Bücher des Vorjahres fehlen deshalb in dieser Datei."
        )

    buecher = []
    for isbn in sorted(set(aktuelle) | set(alte)):
        jetzt = aktuelle.get(isbn)
        frueher = alte.get(isbn)
        quelle = jetzt or frueher
        assert quelle is not None  # eine der beiden Seiten hat die ISBN geliefert
        leihbar = bool(quelle.get("borrowable"))
        if jetzt is None and not leihbar:
            # Aus dem Vorjahr verschwunden und nie im Bestand der Schule: dazu
            # gibt es nichts zu planen.
            continue
        kombinationen = set(aktuelle_paare.get(isbn, ()))
        ausgemustert: set[tuple[str, int]] = set()
        if leihbar:
            ausgemustert = set(alte_paare.get(isbn, ())) - kombinationen
            kombinationen |= ausgemustert
        buecher.append(Buch(
            isbn=isbn,
            titel=str(quelle.get("title") or "?"),
            verlag=str(quelle.get("publisher") or "") or OHNE_VERLAG,
            kombinationen=tuple(sorted(kombinationen,
                                       key=lambda paar: (paar[0].casefold(), paar[1]))),
            leihbar=leihbar,
            neupreis=_preis(quelle.get("price")),
            leihgebuehr=_preis(quelle.get("fee")),
            ausgemustert=tuple(sorted(ausgemustert,
                                      key=lambda paar: (paar[0].casefold(), paar[1]))),
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
