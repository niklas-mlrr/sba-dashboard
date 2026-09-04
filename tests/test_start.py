"""Start und Beenden: freier Port, 127.0.0.1, Knopf statt Strg+C."""
from __future__ import annotations

import json
import socket

import pytest

from app.main import app
from app.start import HOST, freier_port, main


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


def test_alle_ports_belegt_meldet_klartext():
    sockets = []
    try:
        with socket.socket() as erster:
            erster.bind((HOST, 0))
            start = erster.getsockname()[1]
        for versatz in range(3):
            sock = socket.socket()
            sock.bind((HOST, start + versatz))
            sock.listen(1)
            sockets.append(sock)
        with pytest.raises(SystemExit) as fehler:
            freier_port(start, versuche=3)
        assert "belegt" in str(fehler.value)
    finally:
        for sock in sockets:
            sock.close()


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


def test_start_nimmt_alternative_config_und_setzt_app_zustand(tmp_path, monkeypatch):
    config = tmp_path / "arbeitskopie.json"
    config.write_text(json.dumps({
        "iserv_domain": "iserv.example",
        "excel_pfad_kandidaten": [str(tmp_path / "kopie.xlsx")],
        "blatt_raster": "Raster",
        "port": 18765,
    }), encoding="utf-8")

    class _Server:
        def __init__(self, _config):
            self.should_exit = False

        def run(self):
            pass

    import uvicorn

    monkeypatch.setattr(uvicorn, "Server", _Server)
    monkeypatch.setattr("app.start.freier_port", lambda port: port)
    try:
        assert main(["--config", str(config), "--kein-browser"]) == 0
        assert app.state.einstellungen.excel_pfad_kandidaten == (tmp_path / "kopie.xlsx",)
    finally:
        app.state.einstellungen = None
        app.state.server = None
