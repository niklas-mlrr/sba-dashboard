"""config.json: Pfadkandidaten, Prüfungen, Übersetzung in die Bibliothek."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.settings import Einstellungen, EinstellungsFehler

BASIS = {
    "iserv_domain": "beispiel-schule.de",
    "excel_pfad_kandidaten": ["a.xlsx", "b.xlsx"],
    "blatt_raster": "Bestand- und Nachbestellung",
}


def _schreibe(tmp_path: Path, **abweichungen) -> Path:
    inhalt = {**BASIS, **abweichungen}
    pfad = tmp_path / "config.json"
    pfad.write_text(json.dumps(inhalt), encoding="utf-8")
    return pfad


def test_erster_vorhandener_pfad_gewinnt(tmp_path):
    (tmp_path / "b.xlsx").write_text("x")
    einst = Einstellungen.laden(_schreibe(
        tmp_path, excel_pfad_kandidaten=[str(tmp_path / "a.xlsx"), str(tmp_path / "b.xlsx")]))
    assert einst.excel_pfad() == tmp_path / "b.xlsx"


def test_kein_pfad_vorhanden_ist_kein_absturz(tmp_path):
    einst = Einstellungen.laden(_schreibe(
        tmp_path, excel_pfad_kandidaten=[str(tmp_path / "a.xlsx")]))
    assert einst.excel_pfad() is None
    assert einst.gepruefte_pfade() == [(tmp_path / "a.xlsx", False)]
    with pytest.raises(EinstellungsFehler):
        einst.bestand_config()


def test_standardwerte(tmp_path):
    einst = Einstellungen.laden(_schreibe(tmp_path))
    assert (einst.sicherheitsbestand, einst.port, einst.backups_behalten) == (5, 8765, 30)


def test_uebersetzung_in_bestand_config(tmp_path):
    (tmp_path / "a.xlsx").write_text("x")
    einst = Einstellungen.laden(_schreibe(
        tmp_path, excel_pfad_kandidaten=[str(tmp_path / "a.xlsx")],
        sicherheitsbestand=7, match_overrides={"5|Deutsch|": "9783062052224"}))
    config = einst.bestand_config()
    assert config.excel_path == tmp_path / "a.xlsx"
    assert config.sheet_name == BASIS["blatt_raster"]
    assert config.safety_stock == 7
    assert config.match_overrides == {"5|Deutsch|": "9783062052224"}


def test_fehlende_datei(tmp_path):
    with pytest.raises(EinstellungsFehler, match="nicht gefunden"):
        Einstellungen.laden(tmp_path / "gibt-es-nicht.json")


def test_kaputtes_json(tmp_path):
    pfad = tmp_path / "config.json"
    pfad.write_text("{ kein json", encoding="utf-8")
    with pytest.raises(EinstellungsFehler, match="kein gültiges JSON"):
        Einstellungen.laden(pfad)


@pytest.mark.parametrize("abweichung", [
    {"excel_pfad_kandidaten": []},
    {"excel_pfad_kandidaten": "a.xlsx"},
    {"excel_pfad_kandidaten": ["a.xlsx", ""]},
    {"excel_pfad_kandidaten": ["a.xlsx", 42]},
    {"blatt_raster": ""},
    {"blatt_raster": 42},
    {"sicherheitsbestand": -1},
    {"sicherheitsbestand": "fünf"},
    {"match_overrides": {"5|Deutsch|": 42}},
    {"iserv_domain": ""},
    {"iserv_domain": "https://beispiel-schule.de"},
    {"iserv_domain": "beispiel schule.de"},
    {"iserv_domain": "beispiel-schule"},
    {"iserv_domain": "beispiel-schule.de/pfad"},
    {"port": 80},
    {"port": 70000},
    {"port": True},
    {"port": "8765"},
    {"backups_behalten": -1},
    {"backups_behalten": 1001},
    {"backups_behalten": True},
])
def test_ungueltige_werte(tmp_path, abweichung):
    with pytest.raises(EinstellungsFehler):
        Einstellungen.laden(_schreibe(tmp_path, **abweichung))


def test_domain_mit_https_praefix_nennt_den_tippfehler(tmp_path):
    """Ein 'https://' vor der Domain ist der häufigste Tippfehler - die Meldung soll ihn benennen."""
    with pytest.raises(EinstellungsFehler, match="https://"):
        Einstellungen.laden(_schreibe(tmp_path, iserv_domain="https://beispiel-schule.de"))


def test_port_ausserhalb_des_erlaubten_bereichs(tmp_path):
    with pytest.raises(EinstellungsFehler, match="1024"):
        Einstellungen.laden(_schreibe(tmp_path, port=443))


def test_backups_behalten_ausserhalb_des_erlaubten_bereichs(tmp_path):
    with pytest.raises(EinstellungsFehler, match="backups_behalten"):
        Einstellungen.laden(_schreibe(tmp_path, backups_behalten=5000))


def test_unbekannte_schluessel_brechen_das_laden_nicht(tmp_path):
    """Eine künftige Version darf neue Schlüssel einführen, ohne alte Configs zu zerstören."""
    einst = Einstellungen.laden(_schreibe(tmp_path, zukuenftiger_schluessel="neu"))
    assert einst.unbekannte_schluessel == ("zukuenftiger_schluessel",)


def test_laden_setzt_den_benutzer_config_pfad_auf_die_geladene_datei(tmp_path):
    """Im --config-Modus sind Standard und Benutzerkonfiguration dieselbe Datei."""
    pfad = _schreibe(tmp_path)
    einst = Einstellungen.laden(pfad)
    assert einst.benutzer_config_pfad == pfad
