"""Fixtures: synthetisches Workbook aus bestand.core.testing, App ohne Netz."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

from bestand.core import (  # noqa: E402
    UpdateResult,
    apply_snapshot,
    fetch_snapshot,
    load_bestellt_counts,
    parse_grid,
    write_stand,
)
from bestand.core.config import BestandConfig  # noqa: E402
from bestand.core.testing import SHEET_NAME, FakeClient, build_workbook  # noqa: E402

from app.main import create_app  # noqa: E402
from app.settings import Einstellungen  # noqa: E402


@pytest.fixture(autouse=True)
def _isolierte_plattformordner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Für die GESAMTE Suite, nicht nur für Tests, die selbst daran denken: zeigt
    ``SBA_CONFIG_DIR`` und ``SBA_CACHE_DIR`` auf je ein eigenes ``tmp_path``-
    Unterverzeichnis dieses Tests.

    Ohne diese Fixture entscheidet allein das Gedächtnis der Testautorin, ob ein
    schreibender Test ``SBA_CACHE_DIR``/``SBA_CONFIG_DIR`` selbst setzt - vergisst
    sie es, schreibt der Code klammheimlich ins echte Benutzerprofil
    (``~/.cache/sba-dashboard`` bzw. ``~/.config/sba-dashboard``), und nichts im
    Testlauf bemerkt das. ``tmp_path`` ist pro Testfunktion eindeutig, also
    bekommt auch jeder Test seinen eigenen, von jedem anderen Test unabhängigen
    Ordner - kein gemeinsam genutztes Verzeichnis, über das ein Test die
    Cache-Datei eines anderen sehen könnte.

    Ein Test, der einen BESTIMMTEN Wert dieser Variablen braucht (weil er ihn
    hinterher selbst prüft, z. B. ``test_sba_cache_dir_hat_vorrang_vor_jeder_
    plattformlogik``) oder ihn bewusst entfernen will, um die Plattform-Rückfälle
    zu prüfen (``monkeypatch.delenv(..., raising=False)``), tut das weiterhin
    selbst - sein eigener ``monkeypatch``-Aufruf läuft im Testkörper und damit
    NACH dieser Fixture, überschreibt oder entfernt den hier gesetzten Wert also
    zuverlässig.
    """
    monkeypatch.setenv("SBA_CONFIG_DIR", str(tmp_path / "sba-config-dir"))
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "sba-cache-dir"))


@pytest.fixture()
def leeres_workbook(tmp_path: Path) -> Path:
    """Das Raster ohne Zahlen - so sieht die Mappe vor dem ersten Abruf aus."""
    return build_workbook(tmp_path / "Bestand- und Nachbestellungsliste 2026.xlsx")


@pytest.fixture()
def workbook_path(leeres_workbook: Path) -> Path:
    """Dieselbe Mappe, gefüllt über den Kern - kein Netz, keine echten Daten.

    Der Umweg über ``apply_snapshot`` statt handgesetzter Zellen ist Absicht:
    so testet das Dashboard gegen genau die Zahlen, die das Skript schreiben
    würde, inklusive Mehrjahresbändern und leer gelassener Bestellt-Zellen.
    """
    from openpyxl import load_workbook

    wb = load_workbook(str(leeres_workbook))
    ws = wb[SHEET_NAME]
    grid = parse_grid(ws)
    snapshot = fetch_snapshot(FakeClient(), "2026/2027",
                              fetched_at=datetime(2026, 9, 4, 12, 0, 0))
    counts, fehler = load_bestellt_counts(wb["bestellt"])
    config = BestandConfig(excel_path=leeres_workbook, sheet_name=SHEET_NAME)
    result = apply_snapshot(ws, grid, snapshot, config, bestellt_counts=counts,
                            result=UpdateResult(diagnostics=list(fehler)))
    assert result.ok, result.diagnostics
    write_stand(ws, grid, snapshot.fetched_at, result)
    wb.save(str(leeres_workbook))
    return leeres_workbook


@pytest.fixture()
def einstellungen(workbook_path: Path) -> Einstellungen:
    """Zwei Kandidaten - der erste existiert nicht, wie im Schulnetz üblich."""
    return Einstellungen(
        iserv_domain="beispiel-schule.de",
        excel_pfad_kandidaten=(
            workbook_path.parent / "gibt-es-nicht.xlsx",
            workbook_path,
        ),
        blatt_raster=SHEET_NAME,
    )


@pytest.fixture()
def client(einstellungen: Einstellungen) -> TestClient:
    """Eine isolierte App mit dieser Mappe und ohne echten IServ-Client."""
    application = create_app(einstellungen=einstellungen)
    with TestClient(application) as testclient:
        yield testclient
