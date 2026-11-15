"""Oben im Programmordner liegt für die Lehrkraft nur ``START.bat``.

Seit 2026-11-15 steckt alles andere in ``programm/``. Das ist für eine
Codebase ungewöhnlich, aber der Ordner landet so, wie er ist, auf dem Rechner
einer Lehrkraft, und dort soll es genau eine Datei zum Doppelklicken geben.
Was Git und GitHub oben zwingend brauchen (``.github/``, ``.gitattributes``),
ist vom ZIP-Download ausgenommen (``export-ignore``).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ERLAUBT_OBEN = {"START.bat", "programm"}
NUR_FUER_GIT = {".github", ".gitattributes"}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, check=True, capture_output=True, text=True
    ).stdout


pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not (REPO / ".git").exists(),
    reason="kein Git-Checkout",
)


def test_oben_liegt_nur_der_starter():
    oben = {name.split("/", 1)[0] for name in _git("ls-files").splitlines()}
    assert oben <= ERLAUBT_OBEN | NUR_FUER_GIT, sorted(oben - ERLAUBT_OBEN - NUR_FUER_GIT)
    assert ERLAUBT_OBEN <= oben


def test_zip_download_enthaelt_nur_starter_und_programm():
    """GitHubs "Download ZIP" ist ``git archive`` - und das liest export-ignore."""
    for name in NUR_FUER_GIT:
        attribut = _git("check-attr", "export-ignore", "--", name)
        assert attribut.strip().endswith("export-ignore: set"), attribut
