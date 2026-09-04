"""Die Mappe ist in Excel geöffnet: HTTP 423 mit Klartext, möglichst mit Namen.

Auf dem Schul-Laptop ist das der mit Abstand häufigste Fehlerfall - die Datei
liegt auf dem Netzlaufwerk und jemand hat sie noch offen. Ein nackter
``PermissionError`` im Browser hilft dort niemandem weiter.
"""
from __future__ import annotations

import multiprocessing
from pathlib import Path

import pytest

from app import excel as excel_modul
from app.excel import (
    Gesperrt,
    _benutzer_aus_sperrdatei,
    arbeitsmappe_sperren,
    sperr_benutzer,
    sperrdatei,
    sperrmeldung,
)


def _halte_dashboard_sperre(pfad_text: str, bereit, freigeben) -> None:
    """Kindprozess für den Plattformtest der Nachbardatei-Sperre."""
    with arbeitsmappe_sperren(Path(pfad_text), wartezeit=5):
        bereit.set()
        freigeben.wait(timeout=10)


def _sperrdatei_anlegen(pfad: Path, name: str) -> Path:
    """Baut eine ``~$…``-Datei im Format von Excel unter Windows (UTF-16LE)."""
    datei = pfad.parent / f"~${pfad.name}"
    roh = bytes([len(name), 0]) + name.encode("utf-16-le")
    roh += b"\x00" * (54 * 2 - len(name) * 2)
    datei.write_bytes(roh)
    return datei


def _zeile(client, bestand_ref="G3"):
    daten = client.get("/api/rows").json()
    return daten, next(z for z in daten["zeilen"] if z["bestand_ref"] == bestand_ref)


def test_permission_error_wird_zu_423(client, monkeypatch):
    def verweigern(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(excel_modul, "atomic_save_workbook", verweigern)
    daten, zeile = _zeile(client)
    antwort = client.post("/api/cell", json={
        "key": zeile["key"], "spalte": "bestand", "wert": 1, "mtime": daten["mtime"],
    })
    assert antwort.status_code == 423
    assert "in Excel geöffnet" in antwort.json()["fehler"]


def test_423_nennt_den_benutzer_aus_der_sperrdatei(client, workbook_path: Path, monkeypatch):
    _sperrdatei_anlegen(workbook_path, "m.schulz")

    def verweigern(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(excel_modul, "atomic_save_workbook", verweigern)
    daten, zeile = _zeile(client)
    antwort = client.post("/api/cell", json={
        "key": zeile["key"], "spalte": "bestand", "wert": 1, "mtime": daten["mtime"],
    })
    assert antwort.status_code == 423
    körper = antwort.json()
    assert körper["benutzer"] == "m.schulz"
    assert "von m.schulz" in körper["fehler"]


def test_sonstiger_oser_error_meldet_die_mappe_als_unveraendert(client, monkeypatch):
    def verweigern(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(excel_modul, "atomic_save_workbook", verweigern)
    daten, zeile = _zeile(client)
    antwort = client.post("/api/cell", json={
        "key": zeile["key"], "spalte": "bestand", "wert": 1, "mtime": daten["mtime"],
    })
    assert antwort.status_code == 423
    assert "unverändert" in antwort.json()["fehler"]


def test_sperrdatei_wird_in_der_leseantwort_gemeldet(client, workbook_path: Path):
    assert client.get("/api/rows").json()["in_excel_geoeffnet"] is False
    _sperrdatei_anlegen(workbook_path, "m.schulz")
    assert client.get("/api/rows").json()["in_excel_geoeffnet"] is True


def test_startseite_warnt_bei_offener_datei(client, workbook_path: Path):
    _sperrdatei_anlegen(workbook_path, "m.schulz")
    text = client.get("/").text
    assert "in Excel geöffnet" in text
    assert "m.schulz" in text


def test_offene_datei_allein_blockiert_das_schreiben_nicht(client, workbook_path: Path):
    """Eine ``~$…``-Datei kann verwaist sein; erst der echte Fehler ist einer."""
    _sperrdatei_anlegen(workbook_path, "m.schulz")
    daten, zeile = _zeile(client)
    antwort = client.post("/api/cell", json={
        "key": zeile["key"], "spalte": "bestand", "wert": 2, "mtime": daten["mtime"],
    })
    assert antwort.status_code == 200


# ── Sperrdatei lesen ──────────────────────────────────────────────────────────

def test_benutzername_utf16(tmp_path: Path):
    pfad = tmp_path / "Mappe.xlsx"
    pfad.write_bytes(b"x")
    _sperrdatei_anlegen(pfad, "Müller")
    assert sperr_benutzer(pfad) == "Müller"


def test_benutzername_acht_bit():
    """Ältere Excel-Versionen schreiben den Namen als 8-Bit-Text ab Byte 1."""
    name = "j.klein"
    roh = bytes([len(name)]) + name.encode("cp1252") + b"\x00" * 20
    assert _benutzer_aus_sperrdatei(roh) == name


@pytest.mark.parametrize("roh", [b"", b"\x07", b"\x00\x00", bytes([200]) + b"\x00" * 4])
def test_unlesbare_sperrdatei_gibt_keinen_namen(roh):
    assert _benutzer_aus_sperrdatei(roh) is None


def test_ohne_sperrdatei_kein_name(tmp_path: Path):
    pfad = tmp_path / "Mappe.xlsx"
    pfad.write_bytes(b"x")
    assert sperrdatei(pfad) is None
    assert sperr_benutzer(pfad) is None
    assert "in Excel geöffnet." in sperrmeldung(pfad)


def test_gesperrt_traegt_den_benutzer():
    fehler = Gesperrt("Die Datei ist gerade in Excel geöffnet von a.b.", "a.b")
    assert fehler.benutzer == "a.b"


def test_dateisperre_koordiniert_getrennte_dashboard_prozesse(workbook_path: Path):
    """Die SMB-taugliche Nachbardatei sperrt nicht nur Python-Threads."""
    context = multiprocessing.get_context("spawn")
    bereit = context.Event()
    freigeben = context.Event()
    prozess = context.Process(
        target=_halte_dashboard_sperre,
        args=(str(workbook_path), bereit, freigeben),
    )
    prozess.start()
    try:
        assert bereit.wait(timeout=10)
        with pytest.raises(Gesperrt, match="anderes SBA Dashboard"):
            with arbeitsmappe_sperren(workbook_path, wartezeit=0.1):
                pass
    finally:
        freigeben.set()
        prozess.join(timeout=10)
        if prozess.is_alive():
            prozess.terminate()
            prozess.join(timeout=5)
    assert prozess.exitcode == 0
