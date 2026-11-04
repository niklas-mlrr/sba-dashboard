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
    """Der kleinste gegen den kleinsten, bei Gleichstand der zweitkleinste; wer
    keinen zweiten hat, steht vor einem mit zweitem."""
    zeilen = [
        {"name": "5,6,7", "werte": ["5,6,7"]},
        {"name": "5", "werte": ["5"]},
        {"name": "5,6", "werte": ["5,6"]},
        {"name": "11", "werte": ["11"]},
        {"name": "7,8", "werte": ["7,8"]},
        {"name": "5,8", "werte": ["5,8"]},
    ]
    erwartet = ["5", "5,6", "5,6,7", "5,8", "7,8", "11"]
    assert _sortiere(zeilen, [_ebene(0, "liste")]) == erwartet
    assert _sortiere(zeilen, [_ebene(0, "liste", True)]) == erwartet[::-1]


def test_ein_buch_mit_kaufbuch_jahrgang_steht_nach_seinem_kleinsten_jahrgang():
    """Alle Jahrgänge der Zeile zählen, leihbar oder nicht - ein Kaufbuch-Jahrgang
    (hier 5) stellt das Buch nicht ans Ende oder an den Anfang."""
    zeilen = [
        {"name": "nur Kaufbuch 8", "werte": ["8"]},
        {"name": "leihbar 7 + Kaufbuch 5", "werte": ["5,7"]},
        {"name": "leihbar 6", "werte": ["6"]},
    ]
    assert _sortiere(zeilen, [_ebene(0, "liste")]) == [
        "leihbar 7 + Kaufbuch 5", "leihbar 6", "nur Kaufbuch 8"]


def test_die_naechste_ebene_entscheidet_bei_gleichstand():
    zeilen = [
        {"name": "x", "werte": ["5", "9783060000099"]},
        {"name": "y", "werte": ["5", "9783060000005"]},
        {"name": "z", "werte": ["6", "9783060000001"]},
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


def test_die_isbn_sortiert_nach_zahl_und_ein_x_zaehlt_als_zehn():
    """Entscheidung 2026-11-04: ISBN nach Zahl, „X“ am Ende = 10; ein Platzhalter
    (``OHNE-ISBN-…``) hat keinen Wert und steht am Ende."""
    zeilen = [
        {"name": "platzhalter", "werte": ["OHNE-ISBN-1"]},
        {"name": "13", "werte": ["9783060000005"]},
        {"name": "10 mit X", "werte": ["312345678X"]},
        {"name": "10", "werte": ["3123456789"]},
        {"name": "10 danach", "werte": ["3123456791"]},
    ]
    assert _sortiere(zeilen, [_ebene(0, "isbn")]) == [
        "10", "10 mit X", "10 danach", "13", "platzhalter"]
    assert _sortiere(zeilen, [_ebene(0, "isbn", True)]) == [
        "13", "10 danach", "10 mit X", "10", "platzhalter"]


def test_ein_klick_setzt_die_spalte_nach_vorn_und_die_anderen_behalten_ihre_richtung():
    start = [_ebene(2, "liste"), _ebene(4, "text", True)]
    # Eine neue Spalte: vorn, aufsteigend; die beiden anderen dahinter, unverändert.
    assert _js(f"(m) => m.sortierNeueEbenen({json.dumps(start)}, 0, 'text')") == [
        _ebene(0, "text"), _ebene(2, "liste"), _ebene(4, "text", True)]
    # Eine hintere Spalte rückt nach vorn und behält ihre letzte Richtung
    # (Entscheidung 2026-11-04), die andere folgt.
    assert _js(f"(m) => m.sortierNeueEbenen({json.dumps(start)}, 4, 'text')") == [
        _ebene(4, "text", True), _ebene(2, "liste")]
    # Die vorderste kehrt ihre Richtung um - und wieder zurück.
    zweimal = ("(m) => m.sortierNeueEbenen(m.sortierNeueEbenen("
               f"{json.dumps(start)}, 2, 'liste'), 2, 'liste')")
    assert _js(f"(m) => m.sortierNeueEbenen({json.dumps(start)}, 2, 'liste')") == [
        _ebene(2, "liste", True), _ebene(4, "text", True)]
    assert _js(zweimal) == [_ebene(2, "liste"), _ebene(4, "text", True)]


def _folge(teile: list[dict], art: str, absteigend: bool = False) -> list[int]:
    kriterium = {"art": art, "absteigend": absteigend}
    return _js(f"(m) => m.sortierTeilzeilenFolge({json.dumps(teile)}, {json.dumps(kriterium)})")  # type: ignore[return-value]


def test_die_teilzeilen_eines_buches_folgen_der_sortierung_nach_jahrgang():
    # leihbar Jg. 7, Kaufbuch Jg. 5: aufsteigend steht das Kaufbuch oben.
    teile = [{"leihbar": 0, "jahrgaenge": [7, 8]}, {"leihbar": 1, "jahrgaenge": [5]}]
    assert _folge(teile, "jahrgang") == [1, 0]
    assert _folge(teile, "jahrgang", True) == [0, 1]
    # Gleicher kleinster Jahrgang: der ohne zweiten zuerst, absteigend umgekehrt.
    teile = [{"leihbar": 0, "jahrgaenge": [5, 6]}, {"leihbar": 1, "jahrgaenge": [5]}]
    assert _folge(teile, "jahrgang") == [1, 0]
    assert _folge(teile, "jahrgang", True) == [0, 1]
    # Ganz gleich: leihbar zuerst, auch absteigend.
    teile = [{"leihbar": 1, "jahrgaenge": [5]}, {"leihbar": 0, "jahrgaenge": [5]}]
    assert _folge(teile, "jahrgang") == [1, 0]
    assert _folge(teile, "jahrgang", True) == [1, 0]


def test_die_teilzeilen_eines_buches_folgen_der_sortierung_nach_leihbar():
    teile = [{"leihbar": 1, "jahrgaenge": [5]}, {"leihbar": 0, "jahrgaenge": [7]}]
    assert _folge(teile, "leihbar") == [1, 0]
    assert _folge(teile, "leihbar", True) == [0, 1]


def test_der_strich_folgt_den_farben_in_der_reihenfolge_der_teilzeilen():
    assert _js("(m) => m.sortierStrichStil([['blau', 'rot'], ['rot']])") == (
        "linear-gradient(var(--blau-strich) 0% 50%, var(--rot-strich) 50% 100%)")
    assert _js("(m) => m.sortierStrichStil([['rot'], ['grau', 'rot'], ['blau']])") == (
        "linear-gradient(var(--rot-strich) 0% 33.333%, var(--grau-strich) 33.333% 66.667%, "
        "var(--blau-strich) 66.667% 100%)")
    assert _js("(m) => m.sortierStrichStil([['blau'], ['blau']])") == "var(--blau-strich)"
    assert _js("(m) => m.sortierStrichStil([[], []])") == ""
