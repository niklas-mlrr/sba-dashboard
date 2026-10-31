"""Die Buchplanung von der Seite der Anwendung aus.

Die Regeln und die Dateistruktur stehen in ``buecherlisten/planung/`` - das
Paket weiß nichts von HTTP, von Einstellungen und von Sperren, und es liegt
unter ``buecherlisten/``, weil die Buchplanung keinen eigenen Reiter hat:
eingetragen wird in den Bücherlisten-Seiten. Dieses Modul verbindet beides:

* **Wo die Datei liegt** - im Ordner der Bestandsmappe, je Schuljahr eine
  eigene (``app/settings.py``, ``buchplanung_pfad``).
* **Abgleichen** - beide Schuljahre aus IServ holen, mit dem Eingetragenen
  zusammenführen und schreiben.
* **Eintragen** - Fachbestätigung, Planung, Rücklage, Anträge; jedes Mal mit
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

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from math import isfinite
from pathlib import Path
from typing import Any

from buecherlisten.core.daten import UnbekanntesSchuljahr
from buecherlisten.planung import (
    FACH_BESTAETIGT,
    Buchplanung,
    Buchreiheneingabe,
    Jahrgangseingabe,
    MappeUnlesbar,
    Ruecklageneingabe,
    UnbekanntesBuch,
    UngueltigeEingabe,
    bestaetige_fach,
    entscheide_antrag,
    ersetze_isbn,
    fach_status,
    fuege_buch_hinzu,
    halte_bestaetigung,
    lade_schnappschuss,
    lies_datei,
    lies_mappe,
    neue_mappe,
    schreibe_mappe,
    setze_buchplanung,
    setze_buchreihe,
    setze_planung,
    setze_ruecklage,
    verbinde_fortlaufende,
    verfallsgruende,
    zusammenfuehren,
)
from buecherlisten.planung.laden import AusleiheClient

from .excel import (
    Dateizustand,
    ExcelFehlt,
    Konflikt,
    UngueltigeAenderung,
    arbeitsmappe_sperren,
    lade_mappe,
    speichere_mappe,
)
from .planungsansicht import eintrag_stand, fach_stand
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
        stand = verbinde_fortlaufende(zusammenfuehren(None, schnappschuss))
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
        stand = verbinde_fortlaufende(zusammenfuehren(vorher, schnappschuss))
        schreibe_mappe(wb, stand)
        speichere_mappe(wb, pfad, backups_behalten=einstellungen.backups_behalten)
    return Stand(planung=stand, pfad=pfad, zustand=Dateizustand.von(pfad))


@dataclass(frozen=True)
class Eintrag:
    """Der Eintrag, den ein Menü ändert - so, wie es ihn beim Öffnen gesehen hat.

    ``vorher`` ist der Schnappschuss aus der Seite, ``stand_von`` rechnet
    denselben aus der Datei (``app/planungsansicht.py``). Mit einem ``Eintrag``
    zählt nicht mehr, ob sich die **Datei** geändert hat (``mtime``), sondern
    nur, ob sich **dieser Eintrag** geändert hat: was zwei Leute an zwei
    Büchern tun, stört sich nicht (Entscheidung 2026-10-30).
    """

    vorher: Any
    stand_von: Callable[[Buchplanung], Any]


class EintragGeaendert(Exception):
    """Der Eintrag steht nicht mehr so in der Datei, wie das Menü ihn gesehen hat.

    ``aktuell`` ist der Schnappschuss von jetzt: der Browser legt ihn neben
    die Eingabe und lässt wählen, was bleibt.
    """

    def __init__(self, aktuell: Any) -> None:
        super().__init__("Dieser Eintrag wurde inzwischen geändert.")
        self.aktuell = aktuell


class BestaetigungVerfaellt(Exception):
    """Die Eintragung würde die Bestätigung einer Fachliste kosten - und das ist
    noch nicht bestätigt (``verfall_ok``). ``gruende`` nennt, woran es liegt."""

    def __init__(self, gruende: Sequence[str]) -> None:
        super().__init__("Die Bestätigung der Liste würde verfallen.")
        self.gruende = tuple(gruende)


def _aendere(
    einstellungen: Einstellungen,
    schuljahr: str,
    mtime: float | None,
    aenderung: Callable[[Buchplanung], Buchplanung],
    *,
    eintrag: Eintrag | None = None,
    verfall_fach: str | None = None,
    verfall_ok: bool = True,
) -> Stand:
    """Die gemeinsame Kette jeder Eintragung: sperren, prüfen, ändern, sichern.

    Sie steht **einmal** hier und nicht fünfmal in den Routen: Preis,
    Sammelbestätigung, Fachbestätigung, Planung und Rücklage unterscheiden sich
    nur in der Funktion, die den Stand umbaut.

    Geprüft wird entweder die ganze Datei (``mtime``) oder, mit ``eintrag``,
    nur der Eintrag, den das Menü ändert. Mit ``verfall_fach`` und ohne
    ``verfall_ok`` wird nicht geschrieben, wenn die Eintragung die Bestätigung
    dieser Fachliste kosten würde - der Browser fragt erst nach.
    """
    pfad = _pfad(einstellungen, schuljahr)
    if not pfad.is_file():
        raise ExcelFehlt(
            "Für dieses Schuljahr gibt es noch keine Buchplanungs-Datei. Bitte zuerst "
            "„Aus IServ aktualisieren“."
        )
    if eintrag is None and (isinstance(mtime, bool) or not isinstance(mtime, (int, float))
                            or not isfinite(mtime)):
        raise UngueltigeAenderung("Es fehlt eine gültige Änderungszeit der geladenen Datei.")

    with arbeitsmappe_sperren(pfad):
        zustand = Dateizustand.von(pfad)
        if eintrag is None and abs(zustand.mtime - float(mtime or 0)) > 1e-6:
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
        if eintrag is not None:
            aktuell = eintrag.stand_von(vorher)
            if aktuell != eintrag.vorher:
                raise EintragGeaendert(aktuell)
        try:
            nachher = aenderung(vorher)
        except (UnbekanntesBuch, UngueltigeEingabe) as exc:
            raise UngueltigeAenderung(str(exc)) from exc
        # Lückenlos anschließende Zeilen mit gleichem „leihbar“ sind eine.
        nachher = verbinde_fortlaufende(nachher)
        if (verfall_fach is not None and not verfall_ok
                and fach_status(vorher, verfall_fach).status == FACH_BESTAETIGT):
            gruende = verfallsgruende(vorher, nachher, verfall_fach)
            if gruende:
                raise BestaetigungVerfaellt(gruende)
        # Jede Fachliste ist danach ganz oder gar nicht bestätigt.
        nachher = halte_bestaetigung(vorher, nachher)
        schreibe_mappe(wb, nachher)
        speichere_mappe(wb, pfad, backups_behalten=einstellungen.backups_behalten)
    return Stand(planung=nachher, pfad=pfad, zustand=Dateizustand.von(pfad))


def schreibe_fachbestaetigung(
    einstellungen: Einstellungen, *, schuljahr: str, fach: str, kuerzel: str,
    datum: date | None, mtime: float | None, vorher: Any = None,
) -> tuple[Stand, int]:
    """Setzt Kürzel und Datum der Fachkonferenzleitung in alle Zeilen des Fachs.

    Mit ``vorher`` (dem Schnappschuss der Kopfmenüs) zählt nur, ob sich die
    Bestätigung dieses Fachs inzwischen geändert hat.
    """
    gezaehlt = 0

    def aenderung(stand: Buchplanung) -> Buchplanung:
        nonlocal gezaehlt
        neu, gezaehlt = bestaetige_fach(stand, fach=fach, kuerzel=kuerzel, datum=datum)
        return neu

    eintrag = None if vorher is None else Eintrag(
        vorher=vorher, stand_von=lambda stand: fach_stand(stand, fach))
    return _aendere(einstellungen, schuljahr, mtime, aenderung, eintrag=eintrag), gezaehlt


def schreibe_planung(
    einstellungen: Einstellungen, *, schuljahr: str, isbn: str, fach: str, jahrgang: int,
    eingefuehrt_ab: str = "", ausgemustert_nach: str = "", kuerzel: str = "",
    datum: date | None = None, bemerkung: str = "", leihbar: bool | None = None,
    mtime: float | None,
) -> Stand:
    """Trägt die Zeile eines Buchs in **einem** Fach und Jahrgang ein."""
    return _aendere(einstellungen, schuljahr, mtime, lambda stand: setze_planung(
        stand, isbn=isbn, fach=fach, jahrgang=jahrgang, eingefuehrt_ab=eingefuehrt_ab,
        ausgemustert_nach=ausgemustert_nach, kuerzel=kuerzel, datum=datum,
        bemerkung=bemerkung, leihbar=leihbar,
    ))


def schreibe_buchplanung(
    einstellungen: Einstellungen, *, schuljahr: str, isbn: str, fach: str,
    zeilen: Sequence[Jahrgangseingabe], ruecklage: Ruecklageneingabe | None = None,
    buchreihe: Buchreiheneingabe | None = None,
    mtime: float | None, vorher: Any = None, verfall_ok: bool = True,
) -> Stand:
    """Alles, was das Planungsmenü eines Buchs einträgt - in **einem** Schreibvorgang.

    Das Menü kennt nur Speichern und Abbrechen; ein halb geschriebener Stand
    wäre genau das, was die Sperre und der ``mtime``-Vergleich sonst verhindern.
    Mit ``vorher`` zählt nur, ob sich dieser Eintrag geändert hat
    (:class:`Eintrag`); ohne ``verfall_ok`` fragt eine Eintragung, die die
    Bestätigung des Fachs kostet, erst nach (:class:`BestaetigungVerfaellt`).
    """
    def aenderung(stand: Buchplanung) -> Buchplanung:
        if buchreihe is not None:
            stand = setze_buchreihe(stand, isbn=isbn, eingabe=buchreihe)
        stand = setze_buchplanung(
            stand, isbn=isbn, fach=fach, zeilen=zeilen, ruecklage=ruecklage,
        )
        # Zuletzt: die ISBN eines Buchs, das bisher „ISBN folgt“ hieß.
        if buchreihe is not None and (buchreihe.isbn or "").strip():
            stand = ersetze_isbn(stand, alt=isbn, neu=buchreihe.isbn or "")
        return stand

    eintrag = None if vorher is None else Eintrag(
        vorher=vorher, stand_von=lambda stand: eintrag_stand(stand, isbn, fach))
    return _aendere(einstellungen, schuljahr, mtime, aenderung, eintrag=eintrag,
                    verfall_fach=fach, verfall_ok=verfall_ok)


def schreibe_neues_buch(
    einstellungen: Einstellungen, *, schuljahr: str, isbn: str, fach: str,
    buchreihe: Buchreiheneingabe, zeilen: Sequence[Jahrgangseingabe], mtime: float | None,
    verfall_ok: bool = True, ohne_mtime: bool = False,
) -> Stand:
    """Nimmt ein Buch in die Liste eines Fachs auf - aus einem anderen Fach oder neu.

    ``ohne_mtime``: das Menü „+ Buch hinzufügen“ ändert keinen bestehenden
    Eintrag, also gibt es auch keinen, der sich inzwischen geändert haben
    könnte. Steht das Buch schon im Fach, sagt :func:`fuege_buch_hinzu` das.
    """
    eintrag = Eintrag(vorher=None, stand_von=lambda stand: None) if ohne_mtime else None
    return _aendere(einstellungen, schuljahr, mtime, lambda stand: fuege_buch_hinzu(
        stand, isbn=isbn, fach=fach, buchreihe=buchreihe, zeilen=zeilen,
    ), eintrag=eintrag, verfall_fach=fach, verfall_ok=verfall_ok)


def schreibe_antrag(
    einstellungen: Einstellungen, *, schuljahr: str, isbn: str, fach: str, jahrgang: int,
    art: str, ergebnis: str | None, kuerzel: str = "", datum: date | None = None,
    begruendung: str | None = None, eingefuehrt_ab: str | None = None, mtime: float | None,
) -> Stand:
    """Genehmigt oder lehnt eine Einführung oder Ausmusterung ab - die Änderungsliste."""
    return _aendere(einstellungen, schuljahr, mtime, lambda stand: entscheide_antrag(
        stand, isbn=isbn, fach=fach, jahrgang=jahrgang, art=art, ergebnis=ergebnis,
        kuerzel=kuerzel, datum=datum, begruendung=begruendung, eingefuehrt_ab=eingefuehrt_ab,
    ))


def schreibe_ruecklage(
    einstellungen: Einstellungen, *, schuljahr: str, isbn: str, fach: str,
    anzahl: int | None, status: str = "", kuerzel: str = "", datum: date | None = None,
    bemerkung: str = "", mtime: float | None,
) -> Stand:
    """Hält fest, wie viele Exemplare eine Fachschaft behalten möchte."""
    return _aendere(einstellungen, schuljahr, mtime, lambda stand: setze_ruecklage(
        stand, isbn=isbn, fach=fach, anzahl=anzahl, status=status, kuerzel=kuerzel,
        datum=datum, bemerkung=bemerkung,
    ))
