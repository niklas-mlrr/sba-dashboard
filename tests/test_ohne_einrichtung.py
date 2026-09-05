"""Der Zustand vor der Ersteinrichtung - was die Lehrkraft am ersten Tag sieht.

Kein Fehlerfall: die eingetragenen Kandidatenpfade zeigen auf ein Laufwerk, das
auf diesem Rechner anders heißt, und keiner von ihnen existiert. Jede Route muss
das erkennen und sagen, **wo** sie gesucht hat - "Datei nicht gefunden" ohne
diese Liste ist auf einem Netzlaufwerk nicht zu klären.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Einstellungen
from conftest import TEST_BASIS_URL


@pytest.fixture()
def uneingerichtet(client: TestClient, tmp_path: Path) -> TestClient:
    client.app.state.einstellungen = Einstellungen(
        iserv_domain="beispiel-schule.de",
        excel_pfad_kandidaten=(tmp_path / "N-Laufwerk.xlsx", tmp_path / "UNC.xlsx"),
        blatt_raster="Bestand- und Nachbestellung",
    )
    return client


def test_startseite_zeigt_die_einrichtung(uneingerichtet: TestClient):
    antwort = uneingerichtet.get("/")
    assert antwort.status_code == 503
    assert "Wo liegt die Bestandsliste?" in antwort.text
    assert "N-Laufwerk.xlsx" in antwort.text and "UNC.xlsx" in antwort.text


@pytest.mark.parametrize("aufruf", [
    ("GET", "/api/rows", None),
    ("POST", "/api/cell", {"key": "0:Deutsch:C3", "spalte": "bestand", "wert": 1, "mtime": 1.0}),
    ("POST", "/api/refresh", {"benutzer": "b.lehrer", "passwort": "geheim"}),
])
def test_jede_api_route_nennt_die_geprueften_pfade(uneingerichtet: TestClient, aufruf):
    methode, pfad, nutzlast = aufruf
    antwort = uneingerichtet.request(methode, pfad, json=nutzlast)
    assert antwort.status_code == 503, antwort.text
    koerper = antwort.json()
    assert "Keine der eingetragenen Excel-Dateien" in koerper["fehler"]
    assert len(koerper["geprueft"]) == 2


def test_einrichtung_lehnt_nicht_xlsx_ab(uneingerichtet: TestClient, tmp_path: Path):
    """Vor jedem Öffnen: Endung und Existenz. Sonst stünde hier ein Zip-Fehler."""
    textdatei = tmp_path / "notiz.txt"
    textdatei.write_text("kein Workbook", encoding="utf-8")
    for kandidat in (textdatei, tmp_path / "gibt-es-nicht.xlsx"):
        antwort = uneingerichtet.post("/api/einrichtung", json={"pfad": str(kandidat)})
        assert antwort.status_code == 400, kandidat
        assert "keine .xlsx-Datei" in antwort.json()["fehler"]


def test_unbeschreibbare_benutzerkonfiguration_meldet_500(tmp_path: Path, einstellungen,
                                                          leeres_workbook: Path, monkeypatch):
    """Die Mappe ist in Ordnung, nur das Ablegen der Auswahl scheitert.

    Getrennte Meldung, weil die Lehrkraft sonst die Datei für kaputt hielte und
    eine andere suchte - während in Wahrheit ihr Benutzerprofil schreibgeschützt
    ist.
    """
    from app import settings as settings_modul

    def kein_schreibrecht(*args, **kwargs):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(settings_modul, "_atomar_schreiben", kein_schreibrecht)
    config_pfad = tmp_path / "config.json"
    config_pfad.write_text(json.dumps({
        "iserv_domain": einstellungen.iserv_domain,
        "excel_pfad_kandidaten": [str(p) for p in einstellungen.excel_pfad_kandidaten],
        "blatt_raster": einstellungen.blatt_raster,
    }), encoding="utf-8")

    anwendung = create_app(einstellungen=einstellungen, config_pfad=config_pfad)
    with TestClient(anwendung, base_url=TEST_BASIS_URL) as testclient:
        antwort = testclient.post("/api/einrichtung", json={"pfad": str(leeres_workbook)})
    assert antwort.status_code == 500
    assert "nicht gespeichert werden" in antwort.json()["fehler"]


def test_ohne_injizierte_einstellungen_wird_je_anfrage_geladen(tmp_path: Path, workbook_path: Path):
    """Der Weg von ``uvicorn app.main:app``: create_app() ohne Einstellungen.

    Dann gibt es keinen gehaltenen Zustand, und jede Anfrage lädt die
    Konfiguration neu - eine von Hand geänderte Datei wirkt ohne Neustart.
    """
    config_pfad = tmp_path / "config.json"

    def schreibe(*kandidaten: Path) -> None:
        config_pfad.write_text(json.dumps({
            "iserv_domain": "beispiel-schule.de",
            "excel_pfad_kandidaten": [str(p) for p in kandidaten],
            "blatt_raster": "Bestand- und Nachbestellung",
        }), encoding="utf-8")

    schreibe(tmp_path / "noch-nicht-da.xlsx")
    anwendung = create_app(config_pfad=config_pfad)
    assert anwendung.state.einstellungen is None
    with TestClient(anwendung, base_url=TEST_BASIS_URL) as testclient:
        assert testclient.get("/api/rows").status_code == 503
        # Dieselbe laufende Anwendung, nur eine geänderte Datei daneben.
        schreibe(workbook_path)
        antwort = testclient.get("/api/rows")
        assert antwort.status_code == 200
        assert antwort.json()["datei"] == str(workbook_path)
