"""Die Fundregel: welche Mappe das Programm in einem Ordner nimmt.

Die Regel selbst steht bei ``app.settings.mappe_im_ordner``; hier steht, dass sie
die Fälle trifft, um die es auf dem Laufwerk der Schule tatsächlich geht - allen
voran die alte Mappe, die nach dem Schuljahreswechsel noch daneben liegt.
"""
from __future__ import annotations

import os
from pathlib import Path

from app.settings import Einstellungen, mappe_im_ordner

BLATT = "Bestand- und Nachbestellung"


def _datei(ordner: Path, name: str, mtime: float | None = None) -> Path:
    pfad = ordner / name
    pfad.write_text("x", encoding="utf-8")
    if mtime is not None:
        os.utime(pfad, (mtime, mtime))
    return pfad


def test_ein_leerer_ordner_liefert_nichts(tmp_path: Path):
    assert mappe_im_ordner(tmp_path) is None


def test_ein_ordner_der_nicht_existiert_liefert_nichts(tmp_path: Path):
    """Netzlaufwerk nicht verbunden - dasselbe Ergebnis, keine Ausnahme."""
    assert mappe_im_ordner(tmp_path / "gibt-es-nicht") is None


def test_eine_einzelne_mappe_gewinnt(tmp_path: Path):
    mappe = _datei(tmp_path, "Bestand- und Nachbestellungsliste 2026.xlsx")
    _datei(tmp_path, "Notizen.docx")
    _datei(tmp_path, "liste.csv")
    assert mappe_im_ordner(tmp_path) == mappe


def test_das_groessere_jahr_gewinnt(tmp_path: Path):
    """Der Fall nach dem Schuljahreswechsel: die alte Mappe liegt noch daneben."""
    _datei(tmp_path, "Bestand- und Nachbestellungsliste 2025.xlsx")
    neu = _datei(tmp_path, "Bestand- und Nachbestellungsliste 2026.xlsx")
    assert mappe_im_ordner(tmp_path) == neu


def test_ohne_jahreszahl_entscheidet_die_aenderungszeit(tmp_path: Path):
    _datei(tmp_path, "alt.xlsx", mtime=1_000_000)
    neu = _datei(tmp_path, "aktuell.xlsx", mtime=2_000_000)
    assert mappe_im_ordner(tmp_path) == neu


def test_eine_mappe_mit_jahr_schlaegt_eine_neuere_ohne(tmp_path: Path):
    """Die Jahreszahl ist die Absicht, die Änderungszeit nur ein Nebeneffekt.

    Ein Klick auf "Speichern" in der alten Mappe darf die Wahl nicht umdrehen.
    """
    mit_jahr = _datei(tmp_path, "Bestandsliste 2026.xlsx", mtime=1_000_000)
    _datei(tmp_path, "Kopie von Bestandsliste.xlsx", mtime=2_000_000)
    assert mappe_im_ordner(tmp_path) == mit_jahr


def test_excels_sperrdatei_wird_uebersehen(tmp_path: Path):
    """``~$…`` entsteht, während die Mappe offen ist - und ist keine Mappe."""
    mappe = _datei(tmp_path, "Bestand- und Nachbestellungsliste 2026.xlsx")
    _datei(tmp_path, "~$Bestand- und Nachbestellungsliste 2026.xlsx")
    assert mappe_im_ordner(tmp_path) == mappe


def test_die_sicherungen_im_unterordner_zaehlen_nicht(tmp_path: Path):
    """``speichere_mappe`` legt sie in ``backups/`` ab - eine Ebene tiefer."""
    mappe = _datei(tmp_path, "Bestand- und Nachbestellungsliste 2026.xlsx")
    sicherungen = tmp_path / "backups"
    sicherungen.mkdir()
    _datei(sicherungen, "Bestand- und Nachbestellungsliste 2099.xlsx", mtime=9_000_000)
    assert mappe_im_ordner(tmp_path) == mappe


def test_grossschreibung_der_endung_zaehlt_nicht(tmp_path: Path):
    mappe = _datei(tmp_path, "Bestandsliste 2026.XLSX")
    assert mappe_im_ordner(tmp_path) == mappe


# ── Zusammenspiel mit den Einstellungen ───────────────────────────────────────

def _einstellungen(tmp_path: Path, ordner: Path | None) -> Einstellungen:
    return Einstellungen(
        iserv_domain="beispiel-schule.de",
        excel_pfad_kandidaten=(tmp_path / "kandidat.xlsx",),
        blatt_raster=BLATT,
        excel_ordner=ordner,
    )


def test_der_ordner_schlaegt_die_kandidatenliste(tmp_path: Path):
    kandidat = _datei(tmp_path, "kandidat.xlsx")
    ordner = tmp_path / "Buchausleihe"
    ordner.mkdir()
    aus_ordner = _datei(ordner, "Bestand- und Nachbestellungsliste 2026.xlsx")

    assert _einstellungen(tmp_path, ordner).excel_pfad() == aus_ordner
    # Ohne eingestellten Ordner bleibt es beim alten Weg.
    assert _einstellungen(tmp_path, None).excel_pfad() == kandidat


def test_ein_leerer_ordner_faellt_auf_die_kandidaten_zurueck(tmp_path: Path):
    """Damit ein falsch gewählter Ordner nicht die funktionierende Mappe verdeckt."""
    kandidat = _datei(tmp_path, "kandidat.xlsx")
    ordner = tmp_path / "leer"
    ordner.mkdir()
    assert _einstellungen(tmp_path, ordner).excel_pfad() == kandidat


def test_der_eingestellte_ordner_steht_in_den_gepruefte_pfaden(tmp_path: Path):
    """Für die Anzeige: "nichts gefunden" ohne das Wo ist keine Auskunft."""
    ordner = tmp_path / "leer"
    ordner.mkdir()
    geprueft = _einstellungen(tmp_path, ordner).gepruefte_pfade()
    assert geprueft[0] == (ordner, False)
    assert len(geprueft) == 2
