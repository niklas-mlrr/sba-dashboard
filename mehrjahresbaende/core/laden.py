"""Ein Schuljahr aus der IServ-Ausleihe-API holen - nur, was der Vergleich braucht.

Rein lesend (nur GET). Gebraucht werden je Jahrgangsliste drei Dinge: der
Jahrgang, ob es eine Paket- oder eine individuelle Ausleihe ist (``package``),
und die Bücher mit ihrer Leihbarkeit. Alles andere aus den Listen - Preise,
Fristen, Bankverbindung - bleibt liegen.

Warum nicht ``app.buecherlisten.lade_buecherlisten``: das Paket hier liegt
**neben** ``app/`` wie ``bestand/`` und ``buecherlisten/``, nicht darunter. Eine
Abhängigkeit in diese Richtung wäre die erste im Projekt.
"""
from __future__ import annotations

from typing import Any, Protocol

from buecherlisten.core.daten import UnbekanntesSchuljahr, vorjahr_kennung

from .modelle import Buchvorkommen, Jahrgangsliste, Schuljahr


class _Schuljahre(Protocol):
    def get_current(self) -> dict: ...
    def get_by_id(self, schoolyear_id: str) -> dict: ...
    def get_booklists(self, schoolyear_id: str) -> list[dict]: ...
    def get_booklist(self, schoolyear_id: str, booklist_id: int) -> dict: ...


class AusleiheClient(Protocol):
    """Was von ``ausleihe.AusleiheClient`` hier gebraucht wird."""

    @property
    def schoolyears(self) -> Any: ...


# Die Schuljahres-Schreibweise (``vorjahr_kennung``, ``UnbekanntesSchuljahr``)
# steht seit 2026-09-19 in ``buecherlisten/core/daten.py``: inzwischen brauchen
# sie drei Pakete, und ein zweiter Parser wäre genau die Stelle, an der sie
# auseinanderlaufen. Beide Namen bleiben von hier aus erreichbar, damit alles,
# was sie bisher hier importiert hat, unverändert weiterläuft.


def _buch(item: dict) -> Buchvorkommen | None:
    daten = item.get("series_data") or {}
    isbn = daten.get("isbn") or item.get("series")
    if not isbn:
        return None
    return Buchvorkommen(
        isbn=str(isbn),
        titel=daten.get("title") or "?",
        faecher=tuple(daten.get("subjectsFlat") or ()),
        leihbar=bool(item.get("borrowable")),
    )


def _liste(kopf: dict, detail: dict) -> Jahrgangsliste | None:
    jahrgang = kopf.get("grade")
    if jahrgang is None:
        # Listen ohne Jahrgang (Sonderlisten) haben in einer Matrix aus
        # Jahrgängen keinen Platz und bleiben deshalb ganz draußen - auch bei
        # der Frage, ob ein Buch noch irgendwo vorkommt. Am TRG gibt es sie
        # nicht; käme eine dazu, stünde ihr Bestand hier zu Unrecht als
        # ausgemustert, und das fiele beim ersten Blick in die Übersicht auf.
        return None
    gesehen: set[str] = set()
    buecher: list[Buchvorkommen] = []
    for abschnitt in detail.get("sections") or []:
        for option in abschnitt.get("options") or []:
            for item in option.get("items") or []:
                buch = _buch(item)
                if buch is None or buch.isbn in gesehen:
                    continue
                gesehen.add(buch.isbn)
                buecher.append(buch)
    return Jahrgangsliste(jahrgang=int(jahrgang), paket=bool(kopf.get("package")),
                          buecher=tuple(buecher))


def lade_schuljahr(client: AusleiheClient, kennung: str | None = None) -> Schuljahr:
    """Ein Schuljahr mit allen Jahrgangslisten; ohne ``kennung`` das laufende."""
    if kennung:
        kopf = client.schoolyears.get_by_id(kennung)
        schuljahr_id, name = kennung, kopf.get("name") or kennung
    else:
        aktuell = client.schoolyears.get_current()
        schuljahr_id = str(aktuell["id"])
        name = aktuell.get("name") or schuljahr_id

    listen: list[Jahrgangsliste] = []
    for kopf in client.schoolyears.get_booklists(schuljahr_id):
        detail = client.schoolyears.get_booklist(schuljahr_id, kopf["id"])
        liste = _liste(kopf, detail)
        if liste is not None:
            listen.append(liste)
    listen.sort(key=lambda liste: liste.jahrgang)
    return Schuljahr(kennung=schuljahr_id, name=str(name), listen=tuple(listen))


__all__ = [
    "AusleiheClient",
    "UnbekanntesSchuljahr",
    "lade_schuljahr",
    "vorjahr_kennung",
]
