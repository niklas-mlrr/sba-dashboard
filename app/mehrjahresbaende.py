"""Der Reiter „Mehrjahresbände" von der Seite der Anwendung aus.

Die Regeln und die Dateistruktur stehen in ``mehrjahresbaende/core/`` - das
Paket liegt neben ``bestand/`` und ``buecherlisten/`` und weiß nichts von
HTTP, von Einstellungen und von Sperren. Dieses Modul verbindet beides:

* **Wo die Datei liegt** - im Ordner der Bestandsmappe, denn dort sucht sie
  jeder, der das Dashboard nicht hat (``app/settings.py``).
* **Erzeugen** - beide Schuljahre aus IServ holen, die Aufgabenfelder von der
  Schulwebsite, dann rechnen und schreiben.
* **Eine Marke ändern** - mit derselben Kette wie der Schreibpfad der
  Bestandsmappe: Schloss, ``mtime``-Vergleich, atomar speichern, Sicherung.
  Warum es diese Kette braucht, steht in ``docs/architektur.md``; hier steht
  nur, dass sie auch für diese Datei gilt. Eine zweite, laxere Fassung wäre
  genau die Drift, gegen die sie angetreten ist.

Geladen wird **aus der Datei**, nicht aus IServ: die Übersicht ist eine
Entscheidung, keine Abfrage. Sie ändert sich einmal im Jahr, wird von Hand
nachkorrigiert, und genau der korrigierte Stand soll auf der Seite stehen.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from buecherlisten.core.erzeugen import aufgabenfeld_zuordnung
from mehrjahresbaende.core import (
    MappeUnlesbar,
    Uebersicht,
    erlaubte_marken,
    lade_schuljahr,
    lies_blatt,
    lies_uebersicht,
    schreibe_blatt,
    schreibe_datei,
    setze_marke,
    vergleiche,
    vorjahr_kennung,
)
from mehrjahresbaende.core import (
    blatt as _blatt,
)
from mehrjahresbaende.core.laden import AusleiheClient

from .excel import (
    Dateizustand,
    ExcelFehlt,
    Konflikt,
    UngueltigeAenderung,
    arbeitsmappe_sperren,
    lade_mappe,
    speichere_mappe,
)
from .settings import Einstellungen

# Was im Warntext steht, wenn die Schulwebsite gerade nicht erreichbar ist.
_RUECKFALL = "die Spaltenfolge der vorhandenen Datei bleibt, neue Fächer kommen ans Ende"


@dataclass(frozen=True)
class Stand:
    """Die Übersicht samt dem Versionsstand, den der Browser zurückschicken muss."""

    uebersicht: Uebersicht
    pfad: Path
    zustand: Dateizustand


def lies(einstellungen: Einstellungen) -> Stand | None:
    """Die Übersicht aus der Datei - oder ``None``, solange es sie nicht gibt.

    ``None`` ist kein Fehler, sondern der Zustand vor dem ersten Erzeugen: die
    Seite zeigt dann den Knopf und sonst nichts.
    """
    pfad = einstellungen.mehrjahresbaende_pfad()
    if pfad is None or not pfad.is_file():
        return None
    return Stand(uebersicht=lies_uebersicht(pfad), pfad=pfad, zustand=Dateizustand.von(pfad))


def erzeuge(
    client: AusleiheClient,
    einstellungen: Einstellungen,
    *,
    schuljahr: str | None = None,
    vorjahr: str | None = None,
) -> Stand:
    """Holt beide Schuljahre, rechnet die Marken und schreibt die Datei neu.

    Überschreibt dabei **alles**, auch von Hand geänderte Zellen: zwei
    Wahrheiten in einer Datei - hier die gerechnete, dort die nachgebesserte -
    wären nach einem Jahr nicht mehr auseinanderzuhalten. Die Oberfläche fragt
    vorher nach.

    Was erhalten bleibt, ist die **Spaltenfolge** der vorhandenen Datei: wer
    sie kennt, soll seine Fächer wiederfinden.
    """
    pfad = einstellungen.mehrjahresbaende_pfad()
    if pfad is None:
        raise ExcelFehlt(
            "Es ist kein Ordner für die Mehrjahresbände-Datei bekannt. Bitte zuerst im "
            "Programmfenster den Ordner der Bestandsmappe einstellen."
        )

    neu = lade_schuljahr(client, schuljahr)
    alt = lade_schuljahr(client, vorjahr or vorjahr_kennung(neu.kennung))

    warnungen: list[str] = []
    aufgabenfelder = aufgabenfeld_zuordnung(None, warnungen, rueckfall=_RUECKFALL)

    bestehende = lies_uebersicht(pfad).spalten if pfad.is_file() else ()
    uebersicht = vergleiche(
        alt, neu,
        bestehende_spalten=bestehende,
        aufgabenfelder=aufgabenfelder,
        aliase=einstellungen.mehrjahresbaende_fach_aliase,
        warnungen=tuple(warnungen),
    )

    if not pfad.is_file():
        pfad.parent.mkdir(parents=True, exist_ok=True)
        schreibe_datei(pfad, uebersicht)
        return Stand(uebersicht=uebersicht, pfad=pfad, zustand=Dateizustand.von(pfad))

    with arbeitsmappe_sperren(pfad):
        wb = lade_mappe(pfad)
        schreibe_blatt(_blatt(wb), uebersicht)
        speichere_mappe(wb, pfad, backups_behalten=einstellungen.backups_behalten)
    return Stand(uebersicht=uebersicht, pfad=pfad, zustand=Dateizustand.von(pfad))


def schreibe_marke(
    einstellungen: Einstellungen,
    *,
    jahrgang: int,
    fach: str,
    marke: str,
    mtime: float,
) -> tuple[Stand, str]:
    """Setzt genau eine Zelle. Gibt den neuen Stand und den Zellbezug zurück.

    Erlaubt sind die vier festen Marken und die Buchstaben, die **in dieser
    Datei** eine Legendenzeile haben: ein Buchstabe ohne Erklärung wäre für
    jeden, der die Datei ohne das Dashboard öffnet, nicht auflösbar.
    """
    pfad = einstellungen.mehrjahresbaende_pfad()
    if pfad is None or not pfad.is_file():
        raise ExcelFehlt(
            "Es gibt noch keine Mehrjahresbände-Datei. Bitte zuerst „Aus IServ erzeugen“."
        )
    if isinstance(mtime, bool) or not isinstance(mtime, (int, float)) or not isfinite(mtime):
        raise UngueltigeAenderung("Es fehlt eine gültige Änderungszeit der geladenen Datei.")

    with arbeitsmappe_sperren(pfad):
        zustand = Dateizustand.von(pfad)
        if abs(zustand.mtime - float(mtime)) > 1e-6:
            raise Konflikt(
                "Die Datei wurde inzwischen geändert. Bitte die Seite neu laden und "
                "die Änderung erneut eintragen.",
                zustand.mtime,
            )
        wb = lade_mappe(pfad)
        ws = _blatt(wb)
        vorher = lies_blatt(ws)
        if marke not in erlaubte_marken(vorher):
            raise UngueltigeAenderung(
                f"„{marke}“ ist in dieser Übersicht keine gültige Marke. Erlaubt sind: "
                + ", ".join(eintrag or "(frei)" for eintrag in erlaubte_marken(vorher))
                + "."
            )
        try:
            ref = setze_marke(ws, jahrgang, fach, marke)
        except MappeUnlesbar as exc:
            raise UngueltigeAenderung(str(exc)) from exc
        speichere_mappe(wb, pfad, backups_behalten=einstellungen.backups_behalten)
        nachher = lies_blatt(ws)

    return Stand(uebersicht=nachher, pfad=pfad, zustand=Dateizustand.von(pfad)), ref
