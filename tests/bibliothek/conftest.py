"""Fixtures der Bibliothekstests - dieselben Bausteine, andere Erwartung.

Dieser Ordner existiert wegen genau einer Zeile hier: ``workbook_path``. Das
Dashboard versteht darunter eine über ``apply_snapshot`` GEFÜLLTE Mappe
(``tests/conftest.py``), die Bibliothekstests die rohe, leere aus
``build_workbook``. Beides ist richtig - aber nur solange die beiden Fixtures
nicht in derselben Datei stehen. Zusammengelegt hätte eine der beiden Suiten
still die falsche Mappe bekommen: kein roter Lauf, nur Tests, die etwas anderes
prüfen als ihr Name sagt. Ein Unterordner mit eigener ``conftest.py`` ist die
Trennung, die pytest dafür anbietet.

Der ``sys.path``-Einschub, der hier bis zur Zusammenlegung (2026-09-18) stand,
ist weg: ``tests/conftest.py`` legt die Projektwurzel schon auf den Pfad, und
diese Datei wird erst danach eingelesen.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bestand.core.testing import FakeClient, build_workbook


@pytest.fixture()
def workbook_path(tmp_path: Path) -> Path:
    return build_workbook(tmp_path / "Bestand-Test.xlsx")


@pytest.fixture()
def fake_client() -> FakeClient:
    return FakeClient()
