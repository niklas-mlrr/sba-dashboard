"""Das Programmfenster, geprüft ohne Bildschirm.

Möglich ist das, weil die Logik in ``Fenstersteuerung`` steckt und dort nur eine
URL kennt (Begründung im Modul-Docstring von ``app/fenster.py``). Hier hängt sie
an einem ``TestClient`` - damit läuft jeder Weg, den ein Knopf nimmt, gegen die
echten Routen, ohne dass ein Fenster gebaut wird.

Der eine Test, der wirklich ein ``Tk()`` baut, steht am Ende und wird überall
übersprungen, wo es keinen Bildschirm gibt.
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from typing import Any

import pytest
from bestand.core.testing import FakeClient
from fastapi.testclient import TestClient

from app.fenster import Antwort, FensterFehler, Fenstersteuerung, tkinter_verfuegbar
from conftest import TEST_BASIS_URL, TEST_BENUTZER, TEST_PASSWORT


def _ueber_testclient(client: TestClient):
    """Dieselben Anfragen, nur ohne Netz - die Einsatzstelle aus dem Konstruktor."""
    def anfrage(url: str, methode: str, koerper: dict[str, Any] | None) -> Antwort:
        antwort = client.request(methode, url, json=koerper)
        try:
            geparst = antwort.json()
        except ValueError:
            geparst = {}
        return Antwort(status=antwort.status_code,
                       koerper=geparst if isinstance(geparst, dict) else {})
    return anfrage


@pytest.fixture()
def geoeffnet() -> list[str]:
    return []


@pytest.fixture()
def steuerung(client: TestClient, geoeffnet: list[str]) -> Fenstersteuerung:
    client.app.state.client_factory = FakeClient
    return Fenstersteuerung(
        TEST_BASIS_URL, anfrage=_ueber_testclient(client), browser_oeffnen=geoeffnet.append,
    )


# ── Anmelden und abmelden ─────────────────────────────────────────────────────

def test_anmelden_gibt_die_statuszeile_zurueck(steuerung: Fenstersteuerung):
    zeile = steuerung.anmelden(TEST_BENUTZER, TEST_PASSWORT)
    assert f"Angemeldet als {TEST_BENUTZER}" in zeile
    assert "30 Minuten" in zeile
    assert steuerung.anmeldestatus()["angemeldet"] is True


def test_leere_felder_loesen_keine_anfrage_aus(client: TestClient, geoeffnet: list[str]):
    """Der Klick mit leeren Feldern soll nicht erst über den Server gehen."""
    gerufen: list[str] = []

    def zaehlend(url: str, methode: str, koerper: Any) -> Antwort:
        gerufen.append(url)
        return Antwort(status=200, koerper={})

    steuerung = Fenstersteuerung(TEST_BASIS_URL, anfrage=zaehlend,
                                 browser_oeffnen=geoeffnet.append)
    for benutzer, passwort in [("", TEST_PASSWORT), ("   ", TEST_PASSWORT),
                               (TEST_BENUTZER, "")]:
        with pytest.raises(FensterFehler, match="Benutzername und Passwort"):
            steuerung.anmelden(benutzer, passwort)
    assert gerufen == []


def test_falsche_zugangsdaten_zeigen_den_satz_des_servers(client: TestClient,
                                                          steuerung: Fenstersteuerung):
    from ausleihe.exceptions import AuthError

    class _Falsch:
        def __init__(self, *args: object) -> None:
            pass

        def login(self) -> None:
            raise AuthError("401")

    client.app.state.client_factory = _Falsch
    with pytest.raises(FensterFehler, match="Zugangsdaten stimmen nicht"):
        steuerung.anmelden(TEST_BENUTZER, TEST_PASSWORT)
    assert steuerung.anmeldestatus()["angemeldet"] is False


def test_abmelden_beendet_die_anmeldung(steuerung: Fenstersteuerung):
    steuerung.anmelden(TEST_BENUTZER, TEST_PASSWORT)
    zeile = steuerung.abmelden()
    assert "Nicht angemeldet" in zeile
    assert steuerung.anmeldestatus()["angemeldet"] is False


def test_ohne_anmeldung_scheitert_der_abruf_mit_dem_hinweis_aufs_fenster(client: TestClient):
    """Die Kette, auf die es ankommt: kein Fenster-Login -> 401 mit Anleitung."""
    antwort = client.post("/api/refresh")
    assert antwort.status_code == 401
    assert "im Programmfenster anmelden" in antwort.json()["fehler"]


def test_nach_dem_anmelden_startet_der_abruf_ohne_zugangsdaten(steuerung: Fenstersteuerung,
                                                               client: TestClient):
    steuerung.anmelden(TEST_BENUTZER, TEST_PASSWORT)
    antwort = client.post("/api/refresh")
    assert antwort.status_code == 202, antwort.text


# ── Statuszeile ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status,erwartet", [
    ({"angemeldet": False}, "Nicht angemeldet"),
    ({"angemeldet": True, "benutzer": "b.lehrer", "verfaellt_in": 1800}, "30 Minuten"),
    # Aufgerundet: "0 Minuten" wäre für zwanzig Sekunden die unfreundlichste
    # aller wahren Aussagen.
    ({"angemeldet": True, "benutzer": "b.lehrer", "verfaellt_in": 20}, "1 Minuten"),
    ({"angemeldet": True, "benutzer": "b.lehrer", "verfaellt_in": 61}, "2 Minuten"),
    ({"angemeldet": True, "benutzer": "b.lehrer"}, "Angemeldet als b.lehrer."),
])
def test_statuszeile(status: dict, erwartet: str):
    assert erwartet in Fenstersteuerung.statuszeile(status)


# ── Einstellungen ─────────────────────────────────────────────────────────────

def test_einstellungen_kommen_vorbelegt_zurueck(steuerung: Fenstersteuerung,
                                                workbook_path: Path):
    werte = steuerung.einstellungen()
    assert werte["server"] == "beispiel-schule.de"
    assert werte["ordner"] is None          # noch nichts eingestellt
    assert werte["mappe"] == str(workbook_path)
    assert steuerung.mappenzeile(werte) == str(workbook_path)


def test_speichern_nennt_die_gefundene_mappe(steuerung: Fenstersteuerung,
                                             workbook_path: Path):
    zeile = steuerung.speichere_einstellungen("neu-schule.de", str(workbook_path.parent))
    assert str(workbook_path) in zeile

    werte = steuerung.einstellungen()
    assert werte["server"] == "neu-schule.de"
    assert werte["ordner"] == str(workbook_path.parent)


def test_ein_ordner_ohne_mappe_wird_gemeldet_und_nicht_gespeichert(steuerung: Fenstersteuerung,
                                                                   tmp_path: Path):
    leer = tmp_path / "leer"
    leer.mkdir()
    with pytest.raises(FensterFehler, match="keine Excel-Datei"):
        steuerung.speichere_einstellungen("beispiel-schule.de", str(leer))
    assert steuerung.einstellungen()["ordner"] is None


def test_die_mappenzeile_nennt_die_geprueften_pfade_wenn_nichts_gefunden_wurde():
    zeile = Fenstersteuerung.mappenzeile({"mappe": None, "geprueft": ["N:\\a.xlsx", "X:\\b.xlsx"]})
    assert "keine gefunden" in zeile
    assert "N:\\a.xlsx" in zeile and "X:\\b.xlsx" in zeile


# ── Seite öffnen und beenden ──────────────────────────────────────────────────

def test_seite_oeffnen_ruft_den_browser_mit_der_eigenen_adresse(steuerung: Fenstersteuerung,
                                                                geoeffnet: list[str]):
    steuerung.seite_oeffnen()
    assert geoeffnet == ["http://127.0.0.1/"]


def test_beenden_setzt_das_abschaltsignal(steuerung: Fenstersteuerung, client: TestClient):
    class _Server:
        should_exit = False

    server = _Server()
    client.app.state.server = server
    try:
        assert "beendet" in steuerung.beenden()
        assert server.should_exit is True
    finally:
        client.app.state.server = None


def test_ein_abbruch_beim_beenden_gilt_als_erfolg(client: TestClient, geoeffnet: list[str]):
    """Der Server kann abschalten, bevor er antwortet - genau wie auf der Seite."""
    def abgebrochen(url: str, methode: str, koerper: Any) -> Antwort:
        raise FensterFehler("Der Server antwortet nicht.")

    steuerung = Fenstersteuerung(TEST_BASIS_URL, anfrage=abgebrochen,
                                 browser_oeffnen=geoeffnet.append)
    assert "beendet" in steuerung.beenden()


# ── Die echte HTTP-Schicht ────────────────────────────────────────────────────

def test_ein_toter_server_wird_zu_einem_deutschen_satz():
    """Der Pfad über ``urllib``, den die Einsatzstelle sonst ersetzt."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]   # gebunden und sofort wieder frei: niemand hört

    steuerung = Fenstersteuerung(f"http://127.0.0.1:{port}")
    with pytest.raises(FensterFehler, match="antwortet nicht"):
        steuerung.anmeldestatus()


def test_eine_antwort_ohne_fehlerfeld_bleibt_nicht_stumm():
    """Jede Fehlerantwort des Dashboards hat ein ``fehler``-Feld - fast sicher."""
    assert "Status 500" in Antwort(status=500, koerper={}).fehlertext
    assert Antwort(status=400, koerper={"fehler": "  "}).fehlertext.startswith("Unerwartete")
    assert Antwort(status=400, koerper={"fehler": "Klartext"}).fehlertext == "Klartext"


# ── Mit Bildschirm ────────────────────────────────────────────────────────────

def test_tkinter_verfuegbar_nennt_einen_grund_wenn_es_nicht_geht(monkeypatch):
    """Ohne DISPLAY ist das kein Fehler, sondern "dann eben ohne Fenster"."""
    if sys.platform in ("win32", "darwin"):
        pytest.skip("Auf Windows und macOS gibt es kein DISPLAY.")
    monkeypatch.delenv("DISPLAY", raising=False)
    moeglich, grund = tkinter_verfuegbar()
    assert moeglich is False
    assert "Bildschirm" in grund


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and sys.platform not in ("win32", "darwin"),
    reason="Kein Bildschirm vorhanden - das Fenster lässt sich hier nicht bauen.",
)
def test_das_fenster_baut_sich_und_zeigt_die_vorbelegten_werte(steuerung: Fenstersteuerung):
    """Der einzige Test, der Widgets anfasst: baut er sich, stimmt die Verdrahtung."""
    pytest.importorskip("tkinter")
    from app._fenster_tk import Hauptfenster

    fenster = Hauptfenster(steuerung, version="9.9.9")
    try:
        assert "beispiel-schule.de" in fenster._zeile_server.cget("text")
        assert "Nicht angemeldet" in fenster._zeile_status.cget("text")
        assert fenster._knopf_anmelden.cget("text") == "Anmelden"

        fenster._benutzer.set(TEST_BENUTZER)
        fenster._passwort.set(TEST_PASSWORT)
        fenster._anmelden()

        assert fenster._passwort.get() == ""       # sofort überschrieben
        assert fenster._knopf_anmelden.cget("text") == "Abmelden"
        assert TEST_BENUTZER in fenster._zeile_status.cget("text")
    finally:
        if fenster._timer is not None:
            fenster.wurzel.after_cancel(fenster._timer)
        fenster.wurzel.destroy()
