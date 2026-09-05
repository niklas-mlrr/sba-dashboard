"""Start und Beenden: freier Port, 127.0.0.1, Knopf statt Strg+C."""
from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
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


def test_start_nimmt_alternative_config_und_setzt_app_zustand(tmp_path, monkeypatch):
    config = tmp_path / "arbeitskopie.json"
    config.write_text(json.dumps({
        "iserv_domain": "iserv.example",
        "excel_pfad_kandidaten": [str(tmp_path / "kopie.xlsx")],
        "blatt_raster": "Raster",
        "port": 18765,
    }), encoding="utf-8")

    server_instanz = None

    class _Server:
        def __init__(self, _config):
            nonlocal server_instanz
            server_instanz = self
            self.config = _config
            self.should_exit = False

        def run(self):
            pass

    import uvicorn

    monkeypatch.setattr(uvicorn, "Server", _Server)
    monkeypatch.setattr("app.start.freier_port", lambda port: port)
    assert main(["--config", str(config), "--kein-browser"]) == 0
    assert server_instanz.config.app.state.einstellungen.excel_pfad_kandidaten == (
        tmp_path / "kopie.xlsx",
    )


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
        "PATH": f"{bin_ordner}:{os.environ['PATH']}",
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
