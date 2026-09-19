"""Zwei Schuljahre aus IServ holen und zu einer Buchliste zusammenlegen.

Rein lesend (nur GET). Gebraucht werden das laufende Schuljahr und sein
Vorjahr: erst ihr Unterschied zeigt, was neu eingeführt und was ausgemustert
wurde, und genau für ausgemusterte Bücher wird eine Rücklage beantragt.

Die Bücherlisten selbst holt ``buecherlisten.core.daten`` - dasselbe Paket, das
auch die Bücherlisten-Seiten und die PDF-Erzeugung speist. Ein zweiter Abruf
mit eigener Auswertung wäre eine zweite Stelle, an der sich IServ-Feldnamen
ändern können.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from buecherlisten.core.daten import (
    OHNE_VERLAG,
    SchuljahreClient,
    hole_jahrgangslisten,
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
    """Was IServ zu zwei Schuljahren sagt - der Eingabestand des Abgleichs."""

    schuljahr: str
    vorjahr: str
    buecher: tuple[Buch, ...]
    stand: date
    warnungen: tuple[str, ...] = ()


def _kennung_und_name(client: AusleiheClient, kennung: str | None) -> tuple[str, str]:
    if kennung:
        kopf = client.schoolyears.get_by_id(kennung)
        return kennung, str(kopf.get("name") or kennung)
    aktuell = client.schoolyears.get_current()
    kennung = str(aktuell["id"])
    return kennung, str(aktuell.get("name") or kennung)


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
    """
    kennung, name = _kennung_und_name(client, schuljahr)
    warnungen: list[str] = []

    vorjahr_id = vorjahr or vorjahr_kennung(kennung)
    aktuelle = sammle_je_isbn(hole_jahrgangslisten(client, kennung))
    try:
        alte = sammle_je_isbn(hole_jahrgangslisten(client, vorjahr_id))
    except Exception as exc:  # noqa: BLE001 - jedes Scheitern heißt hier dasselbe
        alte = {}
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
        buecher.append(Buch(
            isbn=isbn,
            titel=str(quelle.get("title") or "?"),
            verlag=str(quelle.get("publisher") or "") or OHNE_VERLAG,
            faecher=tuple(quelle.get("subjects") or ()),
            jahrgaenge_vorjahr=tuple(sorted(frueher["grades"])) if frueher else (),
            jahrgaenge_aktuell=tuple(sorted(jetzt["grades"])) if jetzt else (),
            leihbar=bool(quelle.get("borrowable")),
            neupreis=_preis(quelle.get("price")),
            leihgebuehr=_preis(quelle.get("fee")),
        ))

    return Schnappschuss(
        schuljahr=name, vorjahr=vorjahr_id, buecher=tuple(buecher),
        stand=heute or date.today(), warnungen=tuple(warnungen),
    )


def _preis(roh: object) -> float | None:
    if roh is None or isinstance(roh, bool):
        return None
    try:
        return float(roh)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
