"""Die IServ-Domain lässt sich nur im abgemeldeten Zustand ändern.

Der Grund liegt in ``app/sitzung.py``: die Anmeldung hält einen ``AusleiheClient``,
der an genau eine Domain gebunden ist und sich dort bei einem 401 selbsttätig neu
anmeldet. Würde die Domain unter ihm gewechselt, arbeitete das Dashboard ab da mit
einer Anmeldung, die zu keiner Einstellung mehr passt - und niemand sähe, woran es
liegt. Das Programmfenster sperrt das Feld deshalb (``app/_fenster_tk.py``); hier
steht, dass auch der Server es abweist, denn die Sperre im Fenster ist nur Bequem-
lichkeit.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from conftest import melde_an


def test_angemeldet_wird_eine_andere_domain_abgewiesen(client: TestClient,
                                                       workbook_path: Path):
    melde_an(client)
    antwort = client.post("/api/einstellungen", json={
        "server": "andere-schule.de", "ordner": str(workbook_path.parent)})
    assert antwort.status_code == 409, antwort.text
    assert "abgemeldeten Zustand" in antwort.json()["fehler"]
    # Abgewiesen heißt unverändert - auch nicht der Ordner nebenan.
    assert client.app.state.einstellungen.iserv_domain == "beispiel-schule.de"


def test_angemeldet_bleibt_das_speichern_mit_gleicher_domain_erlaubt(client: TestClient,
                                                                    workbook_path: Path):
    """Nur die Domain ist gesperrt, nicht die Einstellungen insgesamt.

    Sonst könnte niemand den Ordner umstellen, ohne sich vorher abzumelden.
    """
    melde_an(client)
    antwort = client.post("/api/einstellungen", json={
        "server": "beispiel-schule.de", "ordner": str(workbook_path.parent)})
    assert antwort.status_code == 200, antwort.text


def test_abgemeldet_ist_die_domain_aenderbar(client: TestClient, workbook_path: Path):
    antwort = client.post("/api/einstellungen", json={
        "server": "andere-schule.de", "ordner": str(workbook_path.parent)})
    assert antwort.status_code == 200, antwort.text
    assert client.app.state.einstellungen.iserv_domain == "andere-schule.de"


def test_nach_dem_abmelden_geht_es_wieder(client: TestClient, workbook_path: Path):
    melde_an(client)
    client.delete("/api/anmeldung")
    antwort = client.post("/api/einstellungen", json={
        "server": "andere-schule.de", "ordner": str(workbook_path.parent)})
    assert antwort.status_code == 200, antwort.text
