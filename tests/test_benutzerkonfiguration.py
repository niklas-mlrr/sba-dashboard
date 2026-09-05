"""Zwei Ebenen (ausgelieferter Standard + Benutzerkonfiguration), Migration alter
Vollkopien, plattformabhängige Pfadauflösung - siehe Modul-Docstring von
app/settings.py für die Begründung des gesamten Entwurfs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app import paths as pfade_modul
from app.settings import Einstellungen, EinstellungsFehler, speichere_excel_pfad

STANDARD = {
    "iserv_domain": "beispiel-schule.de",
    "excel_pfad_kandidaten": ["a.xlsx", "b.xlsx"],
    "blatt_raster": "Bestand- und Nachbestellung",
    "sicherheitsbestand": 5,
    "match_overrides": {},
    "port": 8765,
    "backups_behalten": 30,
}


# Das frühere Sicherheitsnetz hier (eine eigene autouse-Fixture, die nur
# SBA_CONFIG_DIR setzte) ist seit 2026-09-05 redundant: die autouse-Fixture
# ``_isolierte_plattformordner`` in ``tests/conftest.py`` setzt dieselbe
# Variable bereits für die gesamte Suite, inklusive dieses Moduls. Tests unten,
# die ``SBA_CONFIG_DIR`` gezielt auf einen bestimmten Wert setzen oder mit
# ``monkeypatch.delenv(..., raising=False)`` entfernen, tun das weiterhin selbst
# im Testkörper - das läuft nach der conftest-Fixture und überschreibt bzw.
# entfernt deren Wert zuverlässig.


def _schreibe(pfad: Path, daten: dict) -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return pfad


@pytest.fixture()
def standard_pfad(tmp_path: Path) -> Path:
    """Der ausgelieferte Standard - eine eigene, von SBA_CONFIG_DIR unabhängige Datei."""
    return _schreibe(tmp_path / "config.json", dict(STANDARD))


@pytest.fixture()
def benutzer_pfad(tmp_path: Path) -> Path:
    """Die Benutzerkonfiguration - existiert anfangs nicht, wie bei einer Ersteinrichtung."""
    return tmp_path / "benutzer" / "config.json"


# ── Ebenen-Auflösung ─────────────────────────────────────────────────────────

def test_ohne_overlay_gilt_der_ausgelieferte_standard(standard_pfad, benutzer_pfad):
    einst, hinweis = Einstellungen.laden_mit_benutzerkonfiguration(standard_pfad, benutzer_pfad)
    assert hinweis is None
    assert einst.iserv_domain == STANDARD["iserv_domain"]
    assert einst.port == STANDARD["port"]
    assert einst.excel_pfad_kandidaten == tuple(Path(p) for p in STANDARD["excel_pfad_kandidaten"])


def test_overlay_uebersteuert_nur_die_tatsaechlich_gesetzten_schluessel(standard_pfad, benutzer_pfad):
    _schreibe(benutzer_pfad, {"port": 9000})
    einst, hinweis = Einstellungen.laden_mit_benutzerkonfiguration(standard_pfad, benutzer_pfad)
    assert hinweis is None
    assert einst.port == 9000
    assert einst.iserv_domain == STANDARD["iserv_domain"]  # nicht übersteuert -> Standard gilt


def test_match_overrides_wird_im_overlay_flach_ersetzt_nicht_gemischt(standard_pfad, benutzer_pfad):
    _schreibe(standard_pfad, dict(STANDARD, match_overrides={"5|Deutsch|": "9783062052224"}))
    _schreibe(benutzer_pfad, {"match_overrides": {"6|Englisch|": "111"}})
    einst, _ = Einstellungen.laden_mit_benutzerkonfiguration(standard_pfad, benutzer_pfad)
    # Der Standard-Eintrag "5|Deutsch|" taucht nicht mehr auf - kein Mischen der Objekte.
    assert einst.match_overrides == {"6|Englisch|": "111"}


def test_kaputtes_overlay_faellt_auf_den_standard_zurueck_und_meldet_den_grund(standard_pfad, benutzer_pfad):
    _schreibe(benutzer_pfad, {})
    benutzer_pfad.write_text("{ kein json", encoding="utf-8")
    einst, hinweis = Einstellungen.laden_mit_benutzerkonfiguration(standard_pfad, benutzer_pfad)
    # Start funktioniert trotzdem, mit dem ausgelieferten Standard:
    assert einst.iserv_domain == STANDARD["iserv_domain"]
    assert einst.excel_pfad_kandidaten == tuple(Path(p) for p in STANDARD["excel_pfad_kandidaten"])
    assert hinweis is not None
    assert "unbrauchbar" in hinweis


def test_fehlendes_overlay_ist_kein_fehler(standard_pfad, benutzer_pfad):
    assert not benutzer_pfad.exists()
    einst, hinweis = Einstellungen.laden_mit_benutzerkonfiguration(standard_pfad, benutzer_pfad)
    assert hinweis is None
    assert einst.blatt_raster == STANDARD["blatt_raster"]


# ── Schreiben: nur ins Overlay, config.json bleibt unberührt ────────────────

def test_speichere_excel_pfad_schreibt_nur_ins_overlay_config_json_bleibt_byteweise_gleich(
    standard_pfad, benutzer_pfad, tmp_path,
):
    vorher = standard_pfad.read_bytes()
    einst, _ = Einstellungen.laden_mit_benutzerkonfiguration(standard_pfad, benutzer_pfad)

    neuer_kandidat = tmp_path / "gewaehlt.xlsx"
    neuer_kandidat.write_text("x")
    ergebnis = speichere_excel_pfad(einst, neuer_kandidat)

    assert standard_pfad.read_bytes() == vorher  # der ausgelieferte Standard ist unverändert
    assert benutzer_pfad.is_file()

    overlay = json.loads(benutzer_pfad.read_text(encoding="utf-8"))
    assert overlay == {
        "excel_pfad_kandidaten": [
            str(neuer_kandidat), *STANDARD["excel_pfad_kandidaten"],
        ]
    }  # nur der geänderte Schlüssel, kein Vollduplikat des Standards
    assert ergebnis.excel_pfad_kandidaten[0] == neuer_kandidat


def test_speichere_excel_pfad_ohne_bekannten_zielpfad_ist_ein_fehler(tmp_path):
    """Eine direkt konstruierte Einstellungen-Instanz ohne benutzer_config_pfad ist ein Programmierfehler."""
    einst = Einstellungen(
        iserv_domain="beispiel-schule.de",
        excel_pfad_kandidaten=(tmp_path / "a.xlsx",),
        blatt_raster="Bestand- und Nachbestellung",
    )
    with pytest.raises(EinstellungsFehler):
        speichere_excel_pfad(einst, tmp_path / "b.xlsx")


# ── Migration alter Vollkopien ────────────────────────────────────────────────

def test_migration_behaelt_die_benutzerauswahl_und_uebernimmt_eine_geaenderte_voreinstellung(
    standard_pfad, benutzer_pfad,
):
    """Der Kernfall: eine alte Vollkopie (frühere START.bat) darf die Auswahl der
    Lehrkraft nicht verlieren, soll aber künftige Standard-Updates wieder durchlassen."""
    # Altlast: vollständige Kopie des Standards, nur die Kandidatenreihenfolge
    # weicht ab - eine frühere Ersteinrichtung hat "b.xlsx" nach vorne gestellt.
    alte_vollkopie = dict(STANDARD, excel_pfad_kandidaten=["b.xlsx", "a.xlsx"])
    _schreibe(benutzer_pfad, alte_vollkopie)

    einst, hinweis = Einstellungen.laden_mit_benutzerkonfiguration(standard_pfad, benutzer_pfad)
    assert hinweis is not None and "bereinigt" in hinweis
    assert einst.excel_pfad_kandidaten == (Path("b.xlsx"), Path("a.xlsx"))

    bereinigt = json.loads(benutzer_pfad.read_text(encoding="utf-8"))
    assert bereinigt == {"excel_pfad_kandidaten": ["b.xlsx", "a.xlsx"]}  # sonst nichts übrig

    # Der ausgelieferte Standard wird aktualisiert (z. B. neue Programmversion).
    _schreibe(standard_pfad, dict(STANDARD, sicherheitsbestand=8))

    einst2, hinweis2 = Einstellungen.laden_mit_benutzerkonfiguration(standard_pfad, benutzer_pfad)
    assert hinweis2 is None  # bereits bereinigt, keine erneute Migration nötig
    assert einst2.sicherheitsbestand == 8  # die geänderte Voreinstellung wird übernommen
    assert einst2.excel_pfad_kandidaten == (Path("b.xlsx"), Path("a.xlsx"))  # Auswahl überlebt


def test_migration_schreibt_nur_wenn_sich_etwas_aendert(standard_pfad, benutzer_pfad):
    """Ein bereits minimales Overlay wird bei jedem Laden nicht erneut angefasst."""
    _schreibe(benutzer_pfad, {"excel_pfad_kandidaten": ["b.xlsx", "a.xlsx"]})
    inhalt_vorher = benutzer_pfad.read_bytes()

    einst, hinweis = Einstellungen.laden_mit_benutzerkonfiguration(standard_pfad, benutzer_pfad)

    assert hinweis is None
    assert benutzer_pfad.read_bytes() == inhalt_vorher
    assert einst.excel_pfad_kandidaten == (Path("b.xlsx"), Path("a.xlsx"))


def test_migration_verwirft_ein_overlay_das_komplett_dem_standard_entspricht(standard_pfad, benutzer_pfad):
    """Eine reine Vollkopie ohne jede echte Abweichung wird zu einem leeren Overlay bereinigt."""
    _schreibe(benutzer_pfad, dict(STANDARD))
    einst, hinweis = Einstellungen.laden_mit_benutzerkonfiguration(standard_pfad, benutzer_pfad)
    assert hinweis is not None and "bereinigt" in hinweis
    assert json.loads(benutzer_pfad.read_text(encoding="utf-8")) == {}
    assert einst.iserv_domain == STANDARD["iserv_domain"]


# ── --config-Modus: kein Overlay, dieselbe Datei wird gelesen und geschrieben ─

def test_config_modus_liest_und_schreibt_weiterhin_genau_die_angegebene_datei(tmp_path):
    pfad = _schreibe(tmp_path / "arbeitskopie.json", dict(STANDARD))
    einst = Einstellungen.laden(pfad)
    assert einst.benutzer_config_pfad == pfad

    neuer_kandidat = tmp_path / "gewaehlt.xlsx"
    neuer_kandidat.write_text("x")
    ergebnis = speichere_excel_pfad(einst, neuer_kandidat)

    inhalt = json.loads(pfad.read_text(encoding="utf-8"))
    assert inhalt["excel_pfad_kandidaten"][0] == str(neuer_kandidat)
    assert inhalt["iserv_domain"] == STANDARD["iserv_domain"]  # restliche Schlüssel bleiben erhalten
    assert ergebnis.benutzer_config_pfad == pfad


# ── Validierung wirkt auch auf das zusammengeführte Ergebnis ─────────────────

def test_ungueltige_domain_im_overlay_verhindert_das_laden(standard_pfad, benutzer_pfad):
    _schreibe(benutzer_pfad, {"iserv_domain": "https://falsch.de"})
    with pytest.raises(EinstellungsFehler, match="https://"):
        Einstellungen.laden_mit_benutzerkonfiguration(standard_pfad, benutzer_pfad)


def test_ungueltiger_port_im_overlay_verhindert_das_laden(standard_pfad, benutzer_pfad):
    _schreibe(benutzer_pfad, {"port": 80})
    with pytest.raises(EinstellungsFehler, match="1024"):
        Einstellungen.laden_mit_benutzerkonfiguration(standard_pfad, benutzer_pfad)


def test_ungueltiges_backups_behalten_im_overlay_verhindert_das_laden(standard_pfad, benutzer_pfad):
    _schreibe(benutzer_pfad, {"backups_behalten": -5})
    with pytest.raises(EinstellungsFehler, match="backups_behalten"):
        Einstellungen.laden_mit_benutzerkonfiguration(standard_pfad, benutzer_pfad)


# ── Plattformabhängige Pfadauflösung ──────────────────────────────────────────

def test_sba_config_dir_hat_vorrang_vor_jeder_plattformlogik(monkeypatch, tmp_path):
    ziel = tmp_path / "eigener-ordner"
    monkeypatch.setenv("SBA_CONFIG_DIR", str(ziel))
    monkeypatch.setattr(sys, "platform", "linux")
    assert pfade_modul.benutzer_konfigurationsordner() == ziel


def test_windows_pfad_liegt_unter_localappdata(monkeypatch, tmp_path):
    monkeypatch.delenv("SBA_CONFIG_DIR", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert pfade_modul.benutzer_konfigurationsordner() == tmp_path / "Local" / "sba-dashboard"


def test_macos_pfad_liegt_unter_application_support(monkeypatch, tmp_path):
    monkeypatch.delenv("SBA_CONFIG_DIR", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert pfade_modul.benutzer_konfigurationsordner() == (
        tmp_path / "Library" / "Application Support" / "sba-dashboard"
    )


def test_linux_pfad_folgt_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.delenv("SBA_CONFIG_DIR", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert pfade_modul.benutzer_konfigurationsordner() == tmp_path / "xdg" / "sba-dashboard"


def test_linux_pfad_faellt_ohne_xdg_auf_punkt_config_zurueck(monkeypatch, tmp_path):
    monkeypatch.delenv("SBA_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert pfade_modul.benutzer_konfigurationsordner() == tmp_path / ".config" / "sba-dashboard"


# ── Plattformabhängige Pfadauflösung: lokaler Cache-Rückfallort ──────────────
#
# Seit 2026-09-05 teilt sich ``lokaler_cache_ordner`` (bis dahin
# ``app.cache._lokaler_cache_ordner``) denselben privaten Kern
# (``pfade_modul._plattformordner``) wie ``benutzer_konfigurationsordner``
# oben - diese Tests spiegeln die Fälle darüber bewusst, damit beide
# Funktionen weiterhin unabhängig voneinander geprüft bleiben, auch wenn sie
# sich intern dieselbe Plattformerkennung teilen. Unterschied zur
# Konfiguration: unter Windows/macOS hängt der Cache eine zusätzliche
# ``cache``-Ebene an (siehe Modul-Docstring von ``app/paths.py``).

def test_sba_cache_dir_hat_vorrang_vor_jeder_plattformlogik(monkeypatch, tmp_path):
    ziel = tmp_path / "eigener-cache-ordner"
    monkeypatch.setenv("SBA_CACHE_DIR", str(ziel))
    monkeypatch.setattr(sys, "platform", "linux")
    assert pfade_modul.lokaler_cache_ordner() == ziel


def test_windows_cache_pfad_liegt_unter_localappdata_mit_cache_unterordner(monkeypatch, tmp_path):
    monkeypatch.delenv("SBA_CACHE_DIR", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert pfade_modul.lokaler_cache_ordner() == tmp_path / "Local" / "sba-dashboard" / "cache"


def test_macos_cache_pfad_liegt_unter_application_support_mit_cache_unterordner(monkeypatch, tmp_path):
    monkeypatch.delenv("SBA_CACHE_DIR", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert pfade_modul.lokaler_cache_ordner() == (
        tmp_path / "Library" / "Application Support" / "sba-dashboard" / "cache"
    )


def test_linux_cache_pfad_folgt_xdg_cache_home_ohne_zusaetzliche_ebene(monkeypatch, tmp_path):
    monkeypatch.delenv("SBA_CACHE_DIR", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    assert pfade_modul.lokaler_cache_ordner() == tmp_path / "xdg-cache" / "sba-dashboard"


def test_linux_cache_pfad_faellt_ohne_xdg_auf_punkt_cache_zurueck(monkeypatch, tmp_path):
    monkeypatch.delenv("SBA_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert pfade_modul.lokaler_cache_ordner() == tmp_path / ".cache" / "sba-dashboard"
