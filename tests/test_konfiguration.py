"""``lade_einstellungen`` - der Weg, den jeder produktive Start nimmt.

Die beiden Ebenen selbst (ausgelieferter Standard + Benutzerkonfiguration) hat
``tests/test_benutzerkonfiguration.py`` in der Hand. Hier steht nur der
Bootstrap darum herum: dass ohne ``--config`` wirklich der Overlay-Weg genommen
wird und dass ein kaputtes Overlay den Start nicht verhindert, sondern eine
Zeile auf der Konsole erzeugt.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.konfiguration import lade_einstellungen
from app.settings import Einstellungen


def test_mit_pfad_gilt_genau_diese_datei(tmp_path: Path):
    """Arbeitskopie-Modus (``--config PATH``): kein Overlay, auch nicht heimlich."""
    config = tmp_path / "arbeitskopie.json"
    config.write_text(json.dumps({
        "iserv_domain": "arbeitskopie.example",
        "excel_pfad_kandidaten": [str(tmp_path / "kopie.xlsx")],
        "blatt_raster": "Raster",
    }), encoding="utf-8")
    # Ein Overlay, das es geben WÜRDE - es darf hier nicht durchschlagen.
    overlay = Path(str(tmp_path / "sba-config-dir"))
    overlay.mkdir(parents=True, exist_ok=True)
    (overlay / "config.json").write_text(
        json.dumps({"iserv_domain": "overlay.example"}), encoding="utf-8")

    einstellungen = lade_einstellungen(config)
    assert einstellungen.iserv_domain == "arbeitskopie.example"


def test_ohne_pfad_gilt_der_standard_plus_overlay(tmp_path: Path, monkeypatch, capsys):
    """Produktivmodus: config.json des Repos, darübergelegt die Benutzerdatei."""
    overlay = tmp_path / "sba-config-dir"
    overlay.mkdir(parents=True, exist_ok=True)
    (overlay / "config.json").write_text(
        json.dumps({"iserv_domain": "gymnasium.example"}), encoding="utf-8")
    monkeypatch.setenv("SBA_CONFIG_DIR", str(overlay))

    einstellungen = lade_einstellungen(None)
    assert einstellungen.iserv_domain == "gymnasium.example"
    # Der ausgelieferte Standard trägt alles, was das Overlay nicht nennt.
    assert einstellungen.blatt_raster == Einstellungen.laden(
        Path(__file__).resolve().parent.parent / "config.json").blatt_raster
    assert capsys.readouterr().out == ""


def test_kaputtes_overlay_verhindert_den_start_nicht(tmp_path: Path, monkeypatch, capsys):
    """Ein Handeditier-Versuch darf das Dashboard nicht unstartbar machen.

    Der Grund steht als Klartext auf der Konsole - das schwarze Fenster bleibt
    beim Betrieb ohnehin offen, und dort sucht man, wenn eine Einstellung nicht
    wirkt. Ein Abbruch stattdessen hieße: die Lehrkraft kommt gar nicht mehr an
    ihre Zahlen, weil eine Nebensache kaputt ist.
    """
    overlay = tmp_path / "sba-config-dir"
    overlay.mkdir(parents=True, exist_ok=True)
    (overlay / "config.json").write_text("{kein gültiges JSON", encoding="utf-8")
    monkeypatch.setenv("SBA_CONFIG_DIR", str(overlay))

    einstellungen = lade_einstellungen(None)
    assert einstellungen.blatt_raster  # der Standard trägt
    ausgabe = capsys.readouterr().out
    assert ausgabe.strip(), "ein stillschweigend verworfenes Overlay ist der schlechteste Fall"


def test_fehlender_pfad_meldet_klartext(tmp_path: Path):
    with pytest.raises(Exception) as fehler:
        lade_einstellungen(tmp_path / "gibt-es-nicht.json")
    assert "gibt-es-nicht.json" in str(fehler.value)
