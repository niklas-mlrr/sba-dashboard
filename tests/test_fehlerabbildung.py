"""Ausnahme → HTTP: eine Tabelle, nicht ein ``except`` je Route.

Die Abbildung selbst steht in ``app/fehler.py``. Diese Datei prüft zwei Dinge,
die sich beim Umbau am 2026-09-05 verschieben konnten und niemandem aufgefallen
wären: dass jede Antwort weiterhin **deutschen Klartext** im Feld ``fehler``
trägt (die Oberfläche zeigt ihn wörtlich an), und dass derselbe Fehler auf
allen Routen denselben Statuscode bekommt.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.excel import BlattFehlt, Gesperrt, Konflikt
from app.fehler import validierungsmeldung
from app.modelle import KOERPER_UNBRAUCHBAR
from app.settings import Einstellungen


def _zeile(client: TestClient) -> tuple[str, float]:
    daten = client.get("/api/rows").json()
    return next(z for z in daten["zeilen"] if z["bestand_ref"] == "G3")["key"], daten["mtime"]


# ── Deutscher Klartext statt FastAPIs englischem 422 ──────────────────────────

@pytest.mark.parametrize("pfad,nutzlast,erwartet", [
    ("/api/cell", {"spalte": "bestand", "mtime": 1.0}, "Schlüssel"),
    ("/api/cell", {"key": "x", "mtime": 1.0}, "Erlaubt sind nur die Spalten"),
    ("/api/cell", {"key": "x", "spalte": "bestand"}, "Änderungszeit"),
    ("/api/refresh", {}, "Benutzername und Passwort"),
    ("/api/refresh", {"benutzer": "  ", "passwort": "x"}, "Benutzername und Passwort"),
    ("/api/einrichtung", {}, "Pfad zur Excel-Datei"),
])
def test_ungueltiger_koerper_ist_400_mit_deutschem_text(client, pfad, nutzlast, erwartet):
    antwort = client.post(pfad, json=nutzlast)
    assert antwort.status_code == 400, antwort.text
    koerper = antwort.json()
    # Kein "detail", keine Fehlerliste, kein englisches Schema.
    assert set(koerper) == {"fehler"}
    assert erwartet in koerper["fehler"]


def test_koerper_ohne_objekt_meldet_trotzdem_deutsch(client):
    antwort = client.post("/api/cell", json=["kein", "objekt"])
    assert antwort.status_code == 400
    assert antwort.json()["fehler"] == KOERPER_UNBRAUCHBAR


def test_validierungsmeldung_faellt_auf_den_allgemeinen_satz_zurueck():
    """Ein Feld ohne eigenen Satz darf keine englische Rohmeldung durchlassen."""
    assert validierungsmeldung([{"loc": ("body", "unbekannt"), "msg": "Field required"}]) == (
        KOERPER_UNBRAUCHBAR
    )
    assert validierungsmeldung([]) == KOERPER_UNBRAUCHBAR


def test_das_passwort_steht_in_keiner_validierungsantwort(client):
    """Pydantic legt den Eingabewert in jeden Fehlereintrag - hier das Passwort."""
    antwort = client.post("/api/refresh", json={"benutzer": "", "passwort": "geheim-2026"})
    assert antwort.status_code == 400
    assert "geheim-2026" not in antwort.text


# ── Derselbe Fehler, derselbe Code - überall ──────────────────────────────────

def test_gesperrt_ist_ueberall_423(client, monkeypatch):
    from app import excel as excel_modul

    def verweigern(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(excel_modul, "atomic_save_workbook", verweigern)
    key, mtime = _zeile(client)
    antwort = client.post("/api/cell", json={
        "key": key, "spalte": "bestand", "wert": 1, "mtime": mtime,
    })
    assert antwort.status_code == 423
    koerper = antwort.json()
    assert "in Excel geöffnet" in koerper["fehler"]
    # Der Name aus der ~$-Datei gehört mit in die Antwort; hier gibt es keine.
    assert koerper["benutzer"] is None


def test_konflikt_traegt_die_aktuelle_mtime(client):
    key, mtime = _zeile(client)
    antwort = client.post("/api/cell", json={
        "key": key, "spalte": "bestand", "wert": 1, "mtime": mtime - 60,
    })
    assert antwort.status_code == 409
    assert antwort.json()["mtime"] == pytest.approx(mtime)


def test_fehlendes_blatt_ist_auf_beiden_wegen_500(client, einstellungen, workbook_path):
    """Vor dem Umbau: 500 auf dem Lese-, 503 auf dem Schreibweg."""
    key, mtime = _zeile(client)
    client.app.state.einstellungen = Einstellungen(
        iserv_domain=einstellungen.iserv_domain,
        excel_pfad_kandidaten=(workbook_path,),
        blatt_raster="Gibt-es-nicht",
    )
    assert client.get("/api/rows").status_code == 500
    schreiben = client.post("/api/cell", json={
        "key": key, "spalte": "bestand", "wert": 1, "mtime": mtime,
    })
    assert schreiben.status_code == 500
    # KeyError.__str__ liefert das repr des Arguments - der Klartext darf nicht
    # in Anführungszeichen bei der Lehrkraft ankommen.
    assert not schreiben.json()["fehler"].startswith('"')
    assert "Gibt-es-nicht" in schreiben.json()["fehler"]


def test_verschwundene_datei_ist_503(client, monkeypatch):
    """Die Datei war beim Prüfen der Kandidaten da und beim Laden nicht mehr.

    Auf dem Netzlaufwerk ist das kein Programmfehler, sondern eine Sekunde
    ohne Verbindung - also 503 wie der Fall "noch gar keine Datei eingetragen"
    und nicht 500. Nachgestellt wird der Zeitpunkt: ``excel_pfad()`` hat schon
    einen Pfad geliefert, ``lade_mappe`` findet ihn nicht mehr.
    """
    from app import rows as rows_modul
    from app.excel import ExcelFehlt

    def weg(pfad):
        raise ExcelFehlt(f"Excel-Datei nicht gefunden: {pfad}")

    monkeypatch.setattr(rows_modul, "lade_mappe", weg)
    antwort = client.get("/api/rows")
    assert antwort.status_code == 503
    assert "nicht gefunden" in antwort.json()["fehler"]


def test_verschwundene_datei_zeigt_auf_der_startseite_eine_seite(client, monkeypatch):
    """GET / ist die einzige Route, die ihre Fehler selbst behandelt - als HTML."""
    from app import rows as rows_modul
    from app.excel import ExcelFehlt

    def weg(pfad):
        raise ExcelFehlt(f"Excel-Datei nicht gefunden: {pfad}")

    monkeypatch.setattr(rows_modul, "lade_mappe", weg)
    antwort = client.get("/")
    assert antwort.status_code == 503
    assert antwort.headers["content-type"].startswith("text/html")
    assert "nicht gefunden" in antwort.text


def test_die_ausnahmen_kennen_kein_http(client):
    """Der Grund, warum die Abbildung überhaupt zentral sein kann.

    ``app/excel.py`` und ``app/refresh.py`` importieren nichts aus FastAPI und
    entscheiden nichts über Statuscodes. Bricht das, wandert die Abbildung
    unbemerkt zurück in die Domänenmodule.
    """
    for ausnahme in (BlattFehlt, Gesperrt, Konflikt):
        quelle = ausnahme.__module__
        assert quelle.startswith("app."), quelle
    import app.excel
    import app.refresh
    import app.rows

    for modul in (app.excel, app.refresh, app.rows):
        namen = {getattr(getattr(modul, n, None), "__module__", "") for n in dir(modul)}
        assert not any(name.startswith(("fastapi", "starlette")) for name in namen), modul.__name__


def test_wettlauf_beim_abruf_ist_409_mit_status(client, monkeypatch):
    """``LaeuftBereits`` fliegt trotz der Vorprüfung - und hatte einen echten Fehler.

    ``POST /api/refresh`` prüft ``manager.laeuft()``, bevor es anmeldet. Zwischen
    dieser Prüfung und ``manager.starte()`` liegt aber die Anmeldung bei IServ,
    also eine knappe Sekunde Netz - ein zweites Fenster kann in dieser Lücke
    starten. Der Weg war deshalb nie tot, nur ungetestet, und der Handler dafür
    hätte mit ``TypeError`` abgebrochen: sein Hilfsaufruf bekam den Statuscode
    zweimal, einmal als Position und einmal als Feld ``status`` des Körpers.
    Gefunden hat das mypy, nicht die Suite - deshalb steht hier jetzt ein Test.
    """
    from bestand.core.testing import FakeClient

    from app.refresh import LaeuftBereits, RefreshManager

    def belegt(self, einstellungen, client, *, sy_id=None):
        raise LaeuftBereits("Es läuft bereits ein Abruf. Bitte warten, bis er fertig ist.")

    monkeypatch.setattr(RefreshManager, "starte", belegt)
    client.app.state.client_factory = FakeClient
    antwort = client.post("/api/refresh", json={"benutzer": "b.lehrer", "passwort": "geheim"})

    assert antwort.status_code == 409
    koerper = antwort.json()
    assert "bereits ein Abruf" in koerper["fehler"]
    # Der Status gehört mit hinein: die Oberfläche zeigt den laufenden Abruf
    # dann sofort an, statt zuerst /api/refresh/status zu fragen.
    assert koerper["status"]["laeuft"] is False
    assert "geheim" not in antwort.text
