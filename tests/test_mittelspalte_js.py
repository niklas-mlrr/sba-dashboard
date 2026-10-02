"""``verteile()`` aus app/static/mittelspalte.js - über node, wenn es da ist.

Die Funktion richtet die Werte der Mittelspalte der Änderungsliste aus und
ist rein: Wunschplätze und Bereiche hinein, Plätze und fehlende Höhe heraus.
Das Projekt hat keine JS-Testumgebung (siehe tests/test_oberflaeche.py), und
auf den Schulrechnern gibt es kein node; dort wird dieser Test übersprungen.
Wo node installiert ist, prüft er die Fälle aus dem Entwurf.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SKRIPT = Path(__file__).resolve().parent.parent / "app" / "static" / "mittelspalte.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node ist nicht installiert")


def _verteile(werte: list[dict]) -> dict:
    programm = (
        f"const {{ verteile, ABSTAND }} = require({json.dumps(str(SKRIPT))});"
        f"const r = verteile({json.dumps(werte)}, ABSTAND);"
        "console.log(JSON.stringify({ y: r.y, fehlt: r.fehlt,"
        " engster: r.engster ? r.engster.i : null, abstand: ABSTAND }));"
    )
    ausgabe = subprocess.run([NODE, "-e", programm], capture_output=True, text=True,
                             check=True, timeout=20)
    return json.loads(ausgabe.stdout)


def _abschnitt(*hoehen: int) -> list[dict]:
    """Fett über den ganzen Abschnitt, je Teil ein Grau - wie platziereMitte() misst."""
    halb = 9
    gesamt = sum(hoehen)
    werte = [{"fett": True, "wunsch": gesamt / 2, "min": halb, "max": gesamt - halb}]
    von = 0
    for hoehe in hoehen:
        werte.append({"wunsch": von + hoehe / 2, "min": von + halb, "max": von + hoehe - halb})
        von += hoehe
    return werte


def _beruehrungsfrei(werte: list[dict], ergebnis: dict) -> bool:
    plaetze = sorted(ergebnis["y"])
    return all(b - a >= ergebnis["abstand"] - 0.01 for a, b in zip(plaetze, plaetze[1:])) \
        and all(w["min"] - 0.01 <= y <= w["max"] + 0.01 for w, y in zip(werte, ergebnis["y"]))


def test_ohne_beruehrung_steht_jeder_wert_auf_seinem_wunschplatz():
    werte = _abschnitt(45, 45)
    ergebnis = _verteile(werte)
    assert ergebnis["y"] == [45, 22.5, 67.5] and ergebnis["fehlt"] == 0


def test_bei_gleichem_platz_weichen_beide_je_zur_haelfte_aus_grau_nach_unten():
    werte = _abschnitt(45, 45, 45)
    ergebnis = _verteile(werte)
    # Das mittlere Grau lag genau auf dem Fett (67,5): je 9 px auseinander.
    assert ergebnis["y"] == [58.5, 22.5, 76.5, 112.5]
    assert _beruehrungsfrei(werte, ergebnis)


def test_liegt_grau_hoeher_weicht_es_nach_oben_aus():
    werte = [{"fett": True, "wunsch": 50, "min": 9, "max": 91},
             {"wunsch": 45, "min": 9, "max": 91}]
    ergebnis = _verteile(werte)
    assert ergebnis["y"] == [56.5, 38.5]


def test_stoesst_einer_an_seinen_bereich_geht_der_andere_den_rest():
    # Das Grau darf nur bis 50 hinunter; das Fett weicht deshalb weiter aus.
    werte = [{"fett": True, "wunsch": 45, "min": 9, "max": 91},
             {"wunsch": 45, "min": 40, "max": 50}]
    ergebnis = _verteile(werte)
    assert ergebnis["y"] == [32, 50] and ergebnis["fehlt"] == 0


def test_passt_es_gar_nicht_steht_die_fehlende_hoehe_fest():
    werte = _abschnitt(24, 24, 24)
    ergebnis = _verteile(werte)
    assert ergebnis["fehlt"] == 6
    # Gestreckt wird der Teil, dessen unterer Rand begrenzt: der mittlere.
    assert ergebnis["engster"] == 2
    gestreckt = _abschnitt(24, 30, 24)
    assert _verteile(gestreckt)["fehlt"] == 0
    assert _beruehrungsfrei(gestreckt, _verteile(gestreckt))
