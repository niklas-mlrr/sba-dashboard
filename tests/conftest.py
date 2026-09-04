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
