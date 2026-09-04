"""Lesepfad über HTTP: Tabelle, JSON, fehlende Datei."""
from __future__ import annotations

from app.settings import Einstellungen


def test_startseite_zeigt_die_tabelle(client):
    antwort = client.get("/")
    assert antwort.status_code == 200
    text = antwort.text
    assert "Bestand und Nachbestellung" in text
    assert "Erdkunde" in text
    assert "5-6" in text          # Mehrjahresband
    assert "Latein" in text


def test_startseite_weist_auf_den_fehlenden_abruf_hin(client):
    """Ohne Cache stehen Titel und ISBN nicht zur Verfügung - das muss dastehen."""
    text = client.get("/").text
    assert "nach dem\nersten Abruf aus IServ" in text
    assert text.count("<td>—</td>") > 0


def test_api_rows_liefert_die_zeilen(client):
    daten = client.get("/api/rows").json()
    assert daten["cache_leer"] is True
    band = next(z for z in daten["zeilen"] if z["bestand_ref"] == "G3")
    assert (band["jahrgang"], band["angemeldet"], band["zu_bestellen"]) == ("5-6", 92, 2)


def test_fehlende_excel_datei_zeigt_die_geprueften_pfade(client, tmp_path):
    client.app.state.einstellungen = Einstellungen(
        iserv_domain="beispiel-schule.de",
        excel_pfad_kandidaten=(tmp_path / "a.xlsx", tmp_path / "b.xlsx"),
        blatt_raster="Bestand- und Nachbestellung",
    )
    antwort = client.get("/")
    assert antwort.status_code == 503
    assert "a.xlsx" in antwort.text and "b.xlsx" in antwort.text

    json_antwort = client.get("/api/rows")
    assert json_antwort.status_code == 503
    assert len(json_antwort.json()["geprueft"]) == 2


def test_fehlendes_blatt_meldet_klartext(client, einstellungen, workbook_path):
    client.app.state.einstellungen = Einstellungen(
        iserv_domain=einstellungen.iserv_domain,
        excel_pfad_kandidaten=(workbook_path,),
        blatt_raster="Gibt-es-nicht",
    )
    antwort = client.get("/")
    assert antwort.status_code == 500
    assert "Gibt-es-nicht" in antwort.text
