"""Die Version steht an zwei Stellen - dieser Test hält sie zusammen.

``app.__version__`` ist die Zahl, die zur Laufzeit antwortet (``/health``, das
Startfenster, ``tools/diagnose.py``); die Version in ``pyproject.toml`` ist die
der Paketmetadaten. Beide werden selten geändert - genau deshalb verliert man
leicht eine von beiden aus den Augen, und ein falsch gemeldeter Stand ist im
Fern-Diagnosefall schlimmer als gar keiner.
"""
from __future__ import annotations

import re
from pathlib import Path

import app

WURZEL = Path(__file__).resolve().parents[1]
PYPROJECT = WURZEL / "pyproject.toml"


def test_pyproject_und_app_nennen_dieselbe_version():
    roh = PYPROJECT.read_text(encoding="utf-8")
    gefunden = re.search(r'(?m)^version = "([^"]+)"', roh)
    assert gefunden, "pyproject.toml: keine 'version'-Zeile gefunden"
    assert app.__version__ == gefunden.group(1)


def test_die_version_ist_nicht_leer():
    assert app.__version__ and app.__version__.strip() == app.__version__