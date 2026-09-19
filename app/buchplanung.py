"""Die Buchplanung von der Seite der Anwendung aus.

Die Regeln und die Dateistruktur stehen in ``buchplanung/core/`` - das Paket
liegt neben ``bestand/``, ``buecherlisten/`` und ``mehrjahresbaende/`` und weiß
nichts von HTTP, von Einstellungen und von Sperren. Dieses Modul verbindet
beides:

* **Wo die Datei liegt** - im Ordner der Bestandsmappe, je Schuljahr eine
  eigene (``app/settings.py``, ``buchplanung_pfad``).
* **Abgleichen** - beide Schuljahre aus IServ holen, mit dem Eingetragenen
  zusammenführen und schreiben.
* **Eintragen** - Preis, Fachbestätigung, Planung, Rücklage; jedes Mal mit
  derselben Kette wie der Schreibpfad der Bestandsmappe: Schloss,
  ``mtime``-Vergleich, atomar speichern, Sicherung. Warum es diese Kette
  braucht, steht in ``docs/architektur.md``; hier steht nur, dass sie auch für
  diese Datei gilt. Eine zweite, laxere Fassung wäre genau die Drift, gegen
  die sie angetreten ist.

Gelesen wird **aus der Datei**, nicht aus IServ. Die Datei ist der
festgehaltene Arbeitsstand eines Schuljahres; IServ kommt nur beim Abgleich
dazu. Genau deshalb ist sie auch dann noch brauchbar, wenn das Dashboard
gerade nicht läuft.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from math import isfinite
from pathlib import Path

from buchplanung.core import (
    Buchplanung,
    MappeUnlesbar,
    UnbekanntesBuch,
    UngueltigeEingabe,
    lade_schnappschuss,
    lies_datei,
    lies_mappe,
    neue_mappe,
    schreibe_mappe,
    setze_fachbestaetigung,
    setze_planung,
    setze_preis,
    setze_preise_des_verlags,
    setze_ruecklage,
    zusammenfuehren,
)
from buchplanung.core.laden import AusleiheClient
from buecherlisten.core.daten import UnbekanntesSchuljahr

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


@dataclass(frozen=True)
class Stand:
    """Der Stand samt der Version, die der Browser zurückschicken muss."""

    planung: Buchplanung
    pfad: Path
    zustand: Dateizustand


def _pfad(einstellungen: Einstellungen, schuljahr: str) -> Path:
    pfad = einstellungen.buchplanung_pfad(schuljahr)
    if pfad is None:
        raise ExcelFehlt(
            "Es ist kein Ordner für die Buchplanungs-Datei bekannt. Bitte zuerst im "
            "Programmfenster den Ordner der Bestandsmappe einstellen."
        )
    return pfad


def lies(einstellungen: Einstellungen, schuljahr: str) -> Stand | None:
    """Der Stand dieses Schuljahrs - oder ``None``, solange es die Datei nicht gibt.

    ``None`` ist kein Fehler, sondern der Zustand vor dem ersten Abgleich: die
    Seite zeigt dann den Knopf und sonst nichts.
    """
    pfad = _pfad(einstellungen, schuljahr)
    if not pfad.is_file():
        return None
    # Ohne Schloss: Lesen soll auch dann gehen, wenn die Datei gerade in Excel
    # offen ist - dieselbe Entscheidung wie bei der Mehrjahresbände-Übersicht.
    return Stand(planung=lies_datei(pfad), pfad=pfad, zustand=Dateizustand.von(pfad))


def gleiche_ab(
    client: AusleiheClient,
    einstellungen: Einstellungen,
    *,
    schuljahr: str | None = None,
    vorjahr: str | None = None,
) -> Stand:
    """Holt beide Schuljahre aus IServ und schreibt die Datei neu.

    Überschrieben werden nur die Angaben **aus** IServ - Titel, Verlag, Fächer,
    Jahrgänge, Preise. Alles von Hand Eingetragene bleibt, solange sein
    Schlüssel noch existiert; was wegfällt, steht als Warnung im Blatt "Info".

    Bewusst ohne ``mtime``: der Abgleich ist kein Eintragen in eine bekannte
    Fassung, sondern das Nachziehen des Stands aus IServ. Das Schloss schützt
    trotzdem vor gleichzeitigem Schreiben.
    """
    try:
        schnappschuss = lade_schnappschuss(client, schuljahr=schuljahr, vorjahr=vorjahr)
    except UnbekanntesSchuljahr as exc:
        raise UngueltigeAenderung(str(exc)) from exc

    pfad = _pfad(einstellungen, schnappschuss.schuljahr)
    if not pfad.is_file():
        stand = zusammenfuehren(None, schnappschuss)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        wb = neue_mappe()
        schreibe_mappe(wb, stand)
        wb.save(str(pfad))
        return Stand(planung=stand, pfad=pfad, zustand=Dateizustand.von(pfad))

    with arbeitsmappe_sperren(pfad):
        wb = lade_mappe(pfad)
        try:
            vorher = lies_mappe(wb)
        except MappeUnlesbar:
            # Eine Datei, die nicht nach Buchplanung aussieht, wird nicht
            # heimlich überschrieben - aber ihre Blätter werden neu geschrieben,
            # und was darin stand, war ohnehin nicht lesbar. Deshalb: von vorn.
            vorher = None
        stand = zusammenfuehren(vorher, schnappschuss)
        schreibe_mappe(wb, stand)
        speichere_mappe(wb, pfad, backups_behalten=einstellungen.backups_behalten)
    return Stand(planung=stand, pfad=pfad, zustand=Dateizustand.von(pfad))


def _aendere(
    einstellungen: Einstellungen,
    schuljahr: str,
    mtime: float,
    aenderung: Callable[[Buchplanung], Buchplanung],
) -> Stand:
    """Die gemeinsame Kette jeder Eintragung: sperren, prüfen, ändern, sichern.

    Sie steht **einmal** hier und nicht fünfmal in den Routen: Preis,
    Sammelbestätigung, Fachbestätigung, Planung und Rücklage unterscheiden sich
    nur in der Funktion, die den Stand umbaut.
    """
    pfad = _pfad(einstellungen, schuljahr)
    if not pfad.is_file():
        raise ExcelFehlt(
            "Für dieses Schuljahr gibt es noch keine Buchplanungs-Datei. Bitte zuerst "
            "„Aus IServ aktualisieren“."
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
        try:
            vorher = lies_mappe(wb)
        except MappeUnlesbar as exc:
            raise UngueltigeAenderung(str(exc)) from exc
        try:
            nachher = aenderung(vorher)
        except (UnbekanntesBuch, UngueltigeEingabe) as exc:
            raise UngueltigeAenderung(str(exc)) from exc
        schreibe_mappe(wb, nachher)
        speichere_mappe(wb, pfad, backups_behalten=einstellungen.backups_behalten)
    return Stand(planung=nachher, pfad=pfad, zustand=Dateizustand.von(pfad))


def schreibe_preis(
    einstellungen: Einstellungen, *, schuljahr: str, isbn: str, preis: float | None,
    kuerzel: str, datum: date | None, bemerkung: str = "", mtime: float,
) -> Stand:
    """Trägt den gegen die Verlagsliste geprüften Preis **eines** Buchs ein."""
    return _aendere(einstellungen, schuljahr, mtime, lambda stand: setze_preis(
        stand, isbn=isbn, preis=preis, kuerzel=kuerzel, datum=datum, bemerkung=bemerkung,
    ))


def schreibe_preise_des_verlags(
    einstellungen: Einstellungen, *, schuljahr: str, verlag: str, kuerzel: str,
    datum: date | None, mtime: float,
) -> tuple[Stand, int]:
    """Bestätigt die ganze Verlagsliste auf einmal - der Knopf neben dem Drucker."""
    gezaehlt = 0

    def aenderung(stand: Buchplanung) -> Buchplanung:
        nonlocal gezaehlt
        neu, gezaehlt = setze_preise_des_verlags(
            stand, verlag=verlag, kuerzel=kuerzel, datum=datum)
        return neu

    return _aendere(einstellungen, schuljahr, mtime, aenderung), gezaehlt


def schreibe_fachbestaetigung(
    einstellungen: Einstellungen, *, schuljahr: str, fach: str, kuerzel: str,
    datum: date | None, bemerkung: str = "", mtime: float,
) -> Stand:
    """Hält die Freigabe einer Fach-Bücherliste fest, samt bestätigtem Stand."""
    return _aendere(einstellungen, schuljahr, mtime, lambda stand: setze_fachbestaetigung(
        stand, fach=fach, kuerzel=kuerzel, datum=datum, bemerkung=bemerkung,
    ))


def schreibe_planung(
    einstellungen: Einstellungen, *, schuljahr: str, isbn: str, jahrgang: int,
    eingefuehrt_ab: str = "", ausgemustert_nach: str = "", beschluss: str = "",
    bemerkung: str = "", mtime: float,
) -> Stand:
    """Trägt Einführung und Ausmusterung eines Buchs in **einem** Jahrgang ein."""
    return _aendere(einstellungen, schuljahr, mtime, lambda stand: setze_planung(
        stand, isbn=isbn, jahrgang=jahrgang, eingefuehrt_ab=eingefuehrt_ab,
        ausgemustert_nach=ausgemustert_nach, beschluss=beschluss, bemerkung=bemerkung,
    ))


def schreibe_ruecklage(
    einstellungen: Einstellungen, *, schuljahr: str, isbn: str, fach: str,
    anzahl: int | None, status: str = "", kuerzel: str = "", datum: date | None = None,
    bemerkung: str = "", mtime: float,
) -> Stand:
    """Hält fest, wie viele Exemplare eine Fachschaft behalten möchte."""
    return _aendere(einstellungen, schuljahr, mtime, lambda stand: setze_ruecklage(
        stand, isbn=isbn, fach=fach, anzahl=anzahl, status=status, kuerzel=kuerzel,
        datum=datum, bemerkung=bemerkung,
    ))
