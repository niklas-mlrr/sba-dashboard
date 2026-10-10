"""``leihbarSchritt()`` aus app/static/buchplanung.js - über node, wenn es da ist.

Die Funktion entscheidet, was ein Klick auf „Leihbar“ in einer Zeile des
Buchmenüs bewirkt: die Zeile teilen, einen Wechsel zurücknehmen oder nur
umschalten. Sie ist rein (Zeilen hinein, Anweisung heraus); wie
tests/test_mittelspalte_js.py wird sie ohne node übersprungen.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SKRIPT = Path(__file__).resolve().parent.parent / "app" / "static" / "buchplanung.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node ist nicht installiert")

SCHULJAHR = "2026/2027"


def _schritt(zeilen: list[dict], nummer: int) -> dict:
    programm = (
        f"const {{ leihbarSchritt }} = require({json.dumps(str(SKRIPT))});"
        f"console.log(JSON.stringify(leihbarSchritt({json.dumps(zeilen)}, {nummer},"
        f" {json.dumps(SCHULJAHR)})));"
    )
    ausgabe = subprocess.run([NODE, "-e", programm], capture_output=True, text=True,
                             check=True, timeout=20)
    return json.loads(ausgabe.stdout)


def _zeile(jahrgang=7, ab="", nach="", leihbar=True, alt=None) -> dict:
    return {"jahrgang": jahrgang, "eingefuehrt_ab": ab, "ausgemustert_nach": nach,
            "leihbar": leihbar, "alt": (not ab or ab < SCHULJAHR) if alt is None else alt}


def test_eine_schon_gefuehrte_zeile_wird_geteilt():
    assert _schritt([_zeile()], 0) == {"art": "teilen"}
    assert _schritt([_zeile(ab="2024/2025")], 0) == {"art": "teilen"}


def test_eine_kuenftige_oder_neue_zeile_wird_nur_umgeschaltet():
    assert _schritt([_zeile(ab="2028/2029")], 0) == {"art": "umschalten"}
    # Ab diesem Schuljahr, aber ohne Vorgängerin: auch nur umschalten.
    assert _schritt([_zeile(ab="2026/2027")], 0) == {"art": "umschalten"}


def test_die_untere_zeile_nimmt_den_wechsel_zurueck():
    zeilen = [_zeile(nach="2025/2026", leihbar=True),
              _zeile(ab="2026/2027", leihbar=False)]
    assert _schritt(zeilen, 1) == {"art": "zurueck", "vorgaenger": 0}
    # „2026/27“ ist dasselbe Schuljahr.
    zeilen[1]["eingefuehrt_ab"] = "2026/27"
    assert _schritt(zeilen, 1) == {"art": "zurueck", "vorgaenger": 0}


def test_zurueck_nur_zur_passenden_vorgaengerin():
    # Anderer Jahrgang, anderes Ende oder schon dasselbe Häkchen: keine Vorgängerin.
    for vorher in (_zeile(jahrgang=8, nach="2025/2026"), _zeile(nach="2024/2025"),
                   _zeile(nach="2025/2026", leihbar=False)):
        assert _schritt([vorher, _zeile(ab="2026/2027", leihbar=False)], 1) \
            == {"art": "umschalten"}
