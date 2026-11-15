"""Gemeinsamer Versionsvertrag der drei Schreibpfade - ohne HTTP oder Speichern."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

import pytest

from app import buchplanung, excel, mehrjahresbaende
from app.excel import (
    Dateizustand,
    ExcelFehlt,
    Konflikt,
    UngueltigeAenderung,
    pruefe_dateiversion,
    validiere_mtime,
)

_UNGUELTIG = "Es fehlt eine gültige Änderungszeit der geladenen Datei."
_KONFLIKT = (
    "Die Datei wurde inzwischen geändert. Bitte die Seite neu laden und "
    "die Änderung erneut eintragen."
)


@pytest.fixture(params=["bestand", "buchplanung", "mehrjahresbaende"])
def schreibpfad(request, einstellungen, workbook_path):
    if request.param == "bestand":
        modul, pfad = excel, workbook_path

        def schreiben(mtime):
            return excel.schreibe_zelle(
                pfad, einstellungen.blatt_raster, key="unbenutzt", spalte="bestellt",
                wert=1, mtime=mtime,
            )
    elif request.param == "buchplanung":
        modul, pfad = buchplanung, einstellungen.buchplanung_pfad("2026/2027")

        def schreiben(mtime):
            return buchplanung.schreibe_planung(
                einstellungen, schuljahr="2026/2027", isbn="unbenutzt", fach="Deutsch",
                jahrgang=5, mtime=mtime,
            )
    else:
        modul, pfad = mehrjahresbaende, einstellungen.mehrjahresbaende_pfad()

        def schreiben(mtime):
            return mehrjahresbaende.schreibe_marke(
                einstellungen, jahrgang=5, fach="Deutsch", marke="X", mtime=mtime,
            )

    assert pfad is not None
    if not pfad.exists():
        pfad.touch()
    return modul, pfad, schreiben


@pytest.mark.parametrize("mtime", [None, True, False, "1.0", [], float("nan"),
                                   float("inf"), -float("inf")])
def test_ungueltige_version_wird_vor_dem_sperren_abgelehnt(schreibpfad, monkeypatch, mtime):
    modul, pfad, schreiben = schreibpfad
    vorher = pfad.read_bytes()

    def unerwartetes_sperren(*args, **kwargs):
        pytest.fail("Eine ungültige Änderungszeit darf die Mappe nicht sperren.")

    monkeypatch.setattr(modul, "arbeitsmappe_sperren", unerwartetes_sperren)
    with pytest.raises(UngueltigeAenderung) as fehler:
        schreiben(mtime)
    assert str(fehler.value) == _UNGUELTIG
    assert pfad.read_bytes() == vorher


@pytest.mark.parametrize("abweichung", [0, -0.5e-6, 0.5e-6, -2e-6, 2e-6])
def test_version_wird_unter_dem_schloss_vor_dem_laden_verglichen(
    schreibpfad, monkeypatch, abweichung,
):
    modul, pfad, schreiben = schreibpfad
    vorher = pfad.read_bytes()
    gesperrt = False
    zustand = Dateizustand(pfad, 1.0, datetime(2026, 9, 4))

    @contextmanager
    def sperren(datei):
        nonlocal gesperrt
        assert datei == pfad
        gesperrt = True
        try:
            yield
        finally:
            gesperrt = False

    def dateizustand(cls, datei):
        assert gesperrt
        assert datei == pfad
        return zustand

    class LadenErreicht(Exception):
        pass

    def laden(datei):
        assert gesperrt
        assert datei == pfad
        raise LadenErreicht

    monkeypatch.setattr(modul, "arbeitsmappe_sperren", sperren)
    monkeypatch.setattr(Dateizustand, "von", classmethod(dateizustand))
    monkeypatch.setattr(modul, "lade_mappe", laden)
    if abs(abweichung) > 1e-6:
        with pytest.raises(Konflikt) as fehler:
            schreiben(1.0 + abweichung)
        assert str(fehler.value) == _KONFLIKT
        assert fehler.value.aktuelle_mtime == 1.0
    else:
        with pytest.raises(LadenErreicht):
            schreiben(1.0 + abweichung)
    assert not gesperrt
    assert pfad.read_bytes() == vorher


def test_fehlerreihenfolge_bei_fehlender_datei_bleibt_erhalten(schreibpfad):
    modul, pfad, schreiben = schreibpfad
    pfad.unlink()
    # Bestand prüft die Eingabe zuerst; die beiden anderen benötigen erst ihre Datei.
    erwartet = UngueltigeAenderung if modul is excel else ExcelFehlt
    with pytest.raises(erwartet):
        schreiben(None)


@pytest.mark.parametrize("mtime", [0, -1, 1, 1.25])
def test_gueltige_versionen_werden_ohne_zusaetzliche_einschraenkung_uebernommen(mtime):
    assert validiere_mtime(mtime) == mtime
    assert isinstance(validiere_mtime(mtime), float)


@pytest.mark.parametrize("erwartet", [-1e-6, 0, 1e-6])
def test_die_toleranzgrenze_selbst_ist_noch_kein_konflikt(tmp_path, erwartet):
    zustand = Dateizustand(tmp_path / "Mappe.xlsx", 0.0, datetime(2026, 9, 4))
    pruefe_dateiversion(zustand, erwartet)
