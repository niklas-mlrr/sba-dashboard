"""Die Sortierebenen aus app/static/sortieren.js - über node, wenn es da ist.

Die Fach-Ansicht sortiert nach einer Liste von Spalten (Entscheidung
2026-10-31): zu Beginn Jahrgang, dann ISBN; ein Klick setzt die Spalte nach
vorn, die anderen rücken nach hinten und behalten ihre Richtung. Wie bei
mittelspalte.js werden nur die reinen Funktionen geprüft; ohne node wird
übersprungen.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SKRIPT = Path(__file__).resolve().parent.parent / "app" / "static" / "sortieren.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node ist nicht installiert")


def _js(ausdruck: str) -> object:
    programm = (f"const m = require({json.dumps(str(SKRIPT))});"
                f"const r = (({ausdruck}))(m);"
                "console.log(JSON.stringify(r));")
    ausgabe = subprocess.run([NODE, "-e", programm], capture_output=True, encoding="utf-8",
                             check=True, timeout=20)
    return json.loads(ausgabe.stdout)


def _sortiere(zeilen: list[dict], ebenen: list[dict]) -> list[str]:
    ausdruck = (
        "(m) => m.sortierNachEbenen("
        f"{json.dumps(zeilen)}, {json.dumps(ebenen)}, "
        "(zeile, ebene) => m.sortierSchluessel(zeile.werte[ebene.index], ebene.art)"
        ").map((z) => z.name)")
    return _js(ausdruck)  # type: ignore[return-value]


def _ebene(index: int, art: str, absteigend: bool = False) -> dict:
    return {"index": index, "art": art, "absteigend": absteigend}


def test_jahrgangslisten_werden_zahl_fuer_zahl_verglichen_die_kuerzere_zuerst():
    zeilen = [
        {"name": "5,6,7", "werte": ["5,6,7|"]},
        {"name": "5", "werte": ["5|"]},
        {"name": "5,6", "werte": ["5,6|"]},
        {"name": "11", "werte": ["11|"]},
        {"name": "7,8", "werte": ["7,8|"]},
    ]
    assert _sortiere(zeilen, [_ebene(0, "liste")]) == ["5", "5,6", "5,6,7", "7,8", "11"]
    assert _sortiere(zeilen, [_ebene(0, "liste", True)]) == ["11", "7,8", "5,6,7", "5,6", "5"]


def test_leihbare_und_nicht_leihbare_jahrgaenge_bleiben_getrennt():
    """Erst zählt die Liste der leihbaren Jahrgänge, bei Gleichstand die der anderen."""
    zeilen = [
        {"name": "a", "werte": ["6|5"]},
        {"name": "b", "werte": ["5|8"]},
        {"name": "c", "werte": ["5,8|"]},
        {"name": "d", "werte": ["5|7"]},
        {"name": "e", "werte": ["|5"]},
    ]
    # „|5“ hat keine leihbaren Jahrgänge: die leere Liste kommt zuerst.
    assert _sortiere(zeilen, [_ebene(0, "liste")]) == ["e", "d", "b", "c", "a"]


def test_die_naechste_ebene_entscheidet_bei_gleichstand():
    zeilen = [
        {"name": "x", "werte": ["5|", "9783060000099"]},
        {"name": "y", "werte": ["5|", "9783060000005"]},
        {"name": "z", "werte": ["6|", "9783060000001"]},
    ]
    ebenen = [_ebene(0, "liste"), _ebene(1, "text")]
    assert _sortiere(zeilen, ebenen) == ["y", "x", "z"]
    # ISBN steht vorn: jetzt gewinnt sie, bei Gleichstand der Jahrgang.
    assert _sortiere(zeilen, [ebenen[1], ebenen[0]]) == ["z", "y", "x"]


def test_zahlen_und_leere_werte():
    zeilen = [
        {"name": "ohne", "werte": [""]},
        {"name": "10", "werte": ["10"]},
        {"name": "9", "werte": ["9.5"]},
        {"name": "kaputt", "werte": ["abc"]},
    ]
    assert _sortiere(zeilen, [_ebene(0, "zahl")]) == ["9", "10", "ohne", "kaputt"]
    # Ohne Wert steht in beiden Richtungen am Ende.
    assert _sortiere(zeilen, [_ebene(0, "zahl", True)]) == ["10", "9", "ohne", "kaputt"]


def test_ein_klick_setzt_die_spalte_nach_vorn_und_die_anderen_behalten_ihre_richtung():
    start = [_ebene(2, "liste"), _ebene(4, "text", True)]
    # Eine neue Spalte: vorn, aufsteigend; die beiden anderen dahinter, unverändert.
    assert _js(f"(m) => m.sortierNeueEbenen({json.dumps(start)}, 0, 'text')") == [
        _ebene(0, "text"), _ebene(2, "liste"), _ebene(4, "text", True)]
    # Eine hintere Spalte rückt nach vorn und beginnt aufsteigend, die andere folgt.
    assert _js(f"(m) => m.sortierNeueEbenen({json.dumps(start)}, 4, 'text')") == [
        _ebene(4, "text"), _ebene(2, "liste")]
    # Die vorderste kehrt ihre Richtung um - und wieder zurück.
    zweimal = ("(m) => m.sortierNeueEbenen(m.sortierNeueEbenen("
               f"{json.dumps(start)}, 2, 'liste'), 2, 'liste')")
    assert _js(f"(m) => m.sortierNeueEbenen({json.dumps(start)}, 2, 'liste')") == [
        _ebene(2, "liste", True), _ebene(4, "text", True)]
    assert _js(zweimal) == [_ebene(2, "liste"), _ebene(4, "text", True)]
