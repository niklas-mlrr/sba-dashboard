"""Start und Beenden: freier Port, 127.0.0.1, Knopf statt Strg+C."""
from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from app.start import HOST, freier_port, main

WURZEL = Path(__file__).resolve().parents[1]
START_SH = WURZEL / "START.sh"


def test_freier_port_nimmt_den_wunschport():
    with socket.socket() as sock:
        sock.bind((HOST, 0))
        frei = sock.getsockname()[1]
    assert freier_port(frei) == frei


def test_belegter_port_wird_uebersprungen():
    """Ein zweites Fenster soll ausweichen, nicht abbrechen."""
    with socket.socket() as belegt:
        belegt.bind((HOST, 0))
        belegt.listen(1)
        port = belegt.getsockname()[1]
        assert freier_port(port) == port + 1


def test_alle_ports_belegt_meldet_klartext(monkeypatch):
    """Der Test braucht keine zufällig freien Nachbarports des Systems."""
    class _BesetzterSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def setsockopt(self, *_):
            pass

        def bind(self, *_):
            raise OSError("Adresse bereits in Verwendung")

    monkeypatch.setattr("app.start.socket.socket", lambda *_: _BesetzterSocket())
    with pytest.raises(SystemExit) as fehler:
        freier_port(18765, versuche=3)
    assert "belegt" in str(fehler.value)


def test_beenden_ohne_server_meldet_501(client):
    """Wer von Hand `uvicorn` startet, beendet auch von Hand."""
    client.app.state.server = None
    antwort = client.post("/api/beenden")
    assert antwort.status_code == 501
    assert "Strg+C" in antwort.json()["fehler"]


def test_beenden_setzt_das_abschaltsignal(client):
    class _Server:
        should_exit = False

    server = _Server()
    client.app.state.server = server
    try:
        antwort = client.post("/api/beenden")
        assert antwort.status_code == 200
        assert server.should_exit is True
    finally:
        client.app.state.server = None


def test_die_seite_hat_einen_beenden_knopf(client):
    assert 'id="beenden"' in client.get("/").text


def _config(tmp_path: Path) -> Path:
    config = tmp_path / "arbeitskopie.json"
    config.write_text(json.dumps({
        "iserv_domain": "iserv.example",
        "excel_pfad_kandidaten": [str(tmp_path / "kopie.xlsx")],
        "blatt_raster": "Raster",
        "port": 18765,
    }), encoding="utf-8")
    return config


class _ServerStub:
    """Ein uvicorn-Server, der nicht bindet - er merkt sich nur, was passiert ist."""

    letzte: "_ServerStub | None" = None

    def __init__(self, _config) -> None:
        _ServerStub.letzte = self
        self.config = _config
        self.should_exit = False
        self.gelaufen_in: str | None = None

    def run(self) -> None:
        self.gelaufen_in = threading.current_thread().name


@pytest.fixture()
def server_stub(monkeypatch):
    import uvicorn

    monkeypatch.setattr(uvicorn, "Server", _ServerStub)
    monkeypatch.setattr("app.start.freier_port", lambda port: port)
    _ServerStub.letzte = None
    return _ServerStub


def test_start_nimmt_alternative_config_und_setzt_app_zustand(tmp_path, monkeypatch,
                                                              server_stub):
    config = _config(tmp_path)
    assert main(["--config", str(config), "--kein-browser", "--kein-fenster"]) == 0
    assert server_stub.letzte.config.app.state.einstellungen.excel_pfad_kandidaten == (
        tmp_path / "kopie.xlsx",
    )


def test_ohne_fenster_laeuft_der_server_auf_dem_hauptthread(tmp_path, server_stub):
    """Der alte Ablauf bleibt erhalten: kein Fenster, Strg+C beendet."""
    assert main(["--config", str(_config(tmp_path)), "--kein-browser", "--kein-fenster"]) == 0
    assert server_stub.letzte.gelaufen_in == threading.main_thread().name


def test_mit_fenster_laeuft_der_server_im_nebenthread(tmp_path, monkeypatch, server_stub):
    """Tk muss auf den Hauptthread - also tauschen Server und Oberfläche die Plätze.

    Geprüft wird genau die Reihenfolge, von der das Beenden abhängt: das Fenster
    bekommt die Adresse, der Server läuft daneben, und wenn das Fenster zu ist,
    steht ``should_exit``.
    """
    gerufen: list[str] = []

    monkeypatch.setattr("app.start.tkinter_verfuegbar", lambda: (True, ""))
    monkeypatch.setattr(
        "app.fenster.starte",
        lambda url, version="": gerufen.append(url),
    )

    assert main(["--config", str(_config(tmp_path)), "--kein-browser"]) == 0

    assert gerufen == ["http://127.0.0.1:18765/"]
    assert server_stub.letzte.gelaufen_in == "sba-server"
    assert server_stub.letzte.should_exit is True


def test_ohne_bildschirm_faellt_der_start_auf_die_konsole_zurueck(tmp_path, monkeypatch,
                                                                 server_stub, capsys):
    """Auf dem Entwicklungsrechner und in der CI gibt es kein DISPLAY.

    Das ist kein Fehler, sondern "dann eben ohne Fenster" - und die Konsole muss
    dann sagen, wie man sich stattdessen anmeldet.
    """
    monkeypatch.setattr("app.start.tkinter_verfuegbar",
                        lambda: (False, "Kein Bildschirm gefunden (DISPLAY ist nicht gesetzt)."))

    assert main(["--config", str(_config(tmp_path)), "--kein-browser"]) == 0

    ausgabe = capsys.readouterr().out
    assert "Kein Programmfenster" in ausgabe
    assert "/api/anmeldung" in ausgabe
    assert server_stub.letzte.gelaufen_in == threading.main_thread().name


@pytest.mark.skipif(sys.platform == "win32", reason="START.sh ist nur für macOS und Linux")
def test_macos_start_wechselt_ins_projektverzeichnis(tmp_path):
    """Der macOS-Start kommt oft aus dem Home-Ordner, nicht aus dem Checkout.

    ``uv run --project`` installiert zwar die Abhängigkeiten des Checkouts,
    setzt aber nicht dessen Arbeitsverzeichnis. Da ``app`` absichtlich nicht
    als Paket installiert wird, würde ``python -m app.start`` es sonst nicht
    finden. Das Stub zeichnet deshalb das Verzeichnis beider uv-Aufrufe auf.
    """
    bin_ordner = tmp_path / "bin"
    bin_ordner.mkdir()
    uv = bin_ordner / "uv"
    uv.write_text("#!/usr/bin/env bash\npwd >> \"$UV_LOG\"\n", encoding="utf-8")
    uv.chmod(uv.stat().st_mode | stat.S_IXUSR)
    protokoll = tmp_path / "uv-cwd.txt"
    arbeitsordner = tmp_path / "arbeitskopie"
    fremder_ordner = tmp_path / "home"
    fremder_ordner.mkdir()

    umgebung = os.environ | {
        # ``subprocess`` reicht die Umgebung auf Windows nativ weiter; dort
        # trennt PATH mit ``;``. Ein hartes ``:`` ließ den GitHub-Runner am
        # Stub vorbei das echte uv starten.
        "PATH": f"{bin_ordner}{os.pathsep}{os.environ['PATH']}",
        "SBA_ARBEITSORDNER": str(arbeitsordner),
        "UV_LOG": str(protokoll),
    }
    ergebnis = subprocess.run(
        ["bash", str(START_SH)],
        cwd=fremder_ordner,
        env=umgebung,
        capture_output=True,
        text=True,
    )

    assert ergebnis.returncode == 0, ergebnis.stderr
    assert protokoll.read_text(encoding="utf-8").splitlines() == [str(WURZEL), str(WURZEL)]
