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
    ausgabe = subprocess.run([NODE, "-e", programm], capture_output=True, encoding="utf-8",
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


def test_eine_kuenftige_zeile_nimmt_den_wechsel_ebenfalls_zurueck():
    """Auch ab einem späteren Schuljahr: die Vorgängerin endet im Jahr davor."""
    zeilen = [_zeile(nach="2027/2028", leihbar=True),
              _zeile(ab="2028/2029", leihbar=False)]
    assert _schritt(zeilen, 1) == {"art": "zurueck", "vorgaenger": 0}
    # Mit einer Lücke dazwischen ist es keine Vorgängerin: nur umschalten.
    zeilen[0]["ausgemustert_nach"] = "2026/2027"
    assert _schritt(zeilen, 1) == {"art": "umschalten"}


# ── dreiwege(): vorher, aktuell und Eingabe zusammenführen ──────────────────


def _js(ausdruck: str, **werte) -> object:
    belegung = "".join(f"const {name} = {json.dumps(wert)};" for name, wert in werte.items())
    programm = (
        f"const {{ dreiwege, mitWahl, beschreibe }} = require({json.dumps(str(SKRIPT))});"
        f"{belegung} console.log(JSON.stringify({ausdruck}));"
    )
    ausgabe = subprocess.run([NODE, "-e", programm], capture_output=True, encoding="utf-8",
                             check=True, timeout=20)
    return json.loads(ausgabe.stdout)


def _eintrag(titel="Deutschbuch", preis=22.5, zeilen=None) -> dict:
    return {
        "buchreihe": {"titel": titel, "verlag": "Cornelsen", "neupreis": preis,
                      "leihgebuehr": 5.0, "bemerkung": ""},
        "zeilen": zeilen if zeilen is not None else {
            "5|": {"jahrgang": 5, "eingefuehrt_ab": "", "ausgemustert_nach": "",
                   "leihbar": True, "bemerkung": ""}},
        "ruecklage": None,
    }


def _dreiwege(vorher, aktuell, eingabe) -> dict:
    return _js("dreiwege(v, a, e)", v=vorher, a=aktuell, e=eingabe)


def test_was_nur_eine_seite_geaendert_hat_wird_ohne_frage_uebernommen():
    vorher = _eintrag()
    aktuell = _eintrag(preis=24.0)        # dort geändert
    eingabe = _eintrag(titel="Deutsch!")  # hier geändert
    ergebnis = _dreiwege(vorher, aktuell, eingabe)
    assert ergebnis["konflikte"] == []
    assert ergebnis["ergebnis"]["buchreihe"]["titel"] == "Deutsch!"
    assert ergebnis["ergebnis"]["buchreihe"]["neupreis"] == 24.0


def test_beide_verschieden_geaendert_ist_ein_konflikt_vorgewaehlt_die_eingabe():
    ergebnis = _dreiwege(_eintrag(), _eintrag(titel="A"), _eintrag(titel="B"))
    assert ergebnis["konflikte"] == [
        {"pfad": ["buchreihe", "titel"], "neu": "A", "deins": "B"}]
    assert ergebnis["ergebnis"]["buchreihe"]["titel"] == "B"
    gewaehlt = _js("mitWahl(r.ergebnis, r.konflikte, ['neu'])", r=ergebnis)
    assert gewaehlt["buchreihe"]["titel"] == "A"
    assert _js("beschreibe(k)", k=ergebnis["konflikte"][0]) == {
        "feld": "Titel", "neu": "A", "deins": "B"}


def test_beide_gleich_geaendert_ist_kein_konflikt():
    ergebnis = _dreiwege(_eintrag(), _eintrag(titel="A"), _eintrag(titel="A"))
    assert ergebnis["konflikte"] == []


def test_zeilen_werden_feldweise_zusammengefuehrt():
    def zeile(nach="", bemerkung=""):
        return {"5|": {"jahrgang": 5, "eingefuehrt_ab": "", "ausgemustert_nach": nach,
                       "leihbar": True, "bemerkung": bemerkung}}
    ergebnis = _dreiwege(_eintrag(zeilen=zeile()),
                         _eintrag(zeilen=zeile(nach="2027/2028")),
                         _eintrag(zeilen=zeile(bemerkung="neu")))
    assert ergebnis["konflikte"] == []
    assert ergebnis["ergebnis"]["zeilen"]["5|"]["ausgemustert_nach"] == "2027/2028"
    assert ergebnis["ergebnis"]["zeilen"]["5|"]["bemerkung"] == "neu"
    # Beide ändern die Ausmusterung verschieden: ein Konflikt in genau diesem Feld.
    ergebnis = _dreiwege(_eintrag(zeilen=zeile()), _eintrag(zeilen=zeile(nach="2027/2028")),
                         _eintrag(zeilen=zeile(nach="2028/2029")))
    [konflikt] = ergebnis["konflikte"]
    assert konflikt["pfad"] == ["zeilen", "5|", "ausgemustert_nach"]
    assert _js("beschreibe(k)", k=konflikt) == {
        "feld": "Jg. 5: Ausmusterung", "neu": "2027/2028", "deins": "2028/2029"}


def test_eine_dort_entfernte_hier_geaenderte_zeile_steht_als_ganzes_zur_wahl():
    vorher = _eintrag(zeilen={
        "7|2027/2028": {"jahrgang": 7, "eingefuehrt_ab": "2027/2028", "ausgemustert_nach": "",
                        "leihbar": True, "bemerkung": ""}})
    eingabe = json.loads(json.dumps(vorher))
    eingabe["zeilen"]["7|2027/2028"]["bemerkung"] = "wichtig"
    # Eine hier neu angelegte Zeile kommt ohne Frage dazu.
    eingabe["zeilen"]["neu:1"] = {"jahrgang": 8, "eingefuehrt_ab": "2028/2029",
                                  "ausgemustert_nach": "", "leihbar": False, "bemerkung": ""}
    ergebnis = _dreiwege(vorher, _eintrag(zeilen={}), eingabe)
    [konflikt] = ergebnis["konflikte"]
    assert konflikt["pfad"] == ["zeilen", "7|2027/2028"]
    assert "neu:1" in ergebnis["ergebnis"]["zeilen"]
    assert _js("beschreibe(k)", k=konflikt) == {
        "feld": "Jg. 7 (ab 2027/2028)", "neu": "nicht vorhanden",
        "deins": "Jg. 7, ab 2027/2028, leihbar, wichtig"}
    # „Neuer Stand“ gewählt: die Zeile bleibt weg.
    gewaehlt = _js("mitWahl(r.ergebnis, r.konflikte, ['neu'])", r=ergebnis)
    assert set(gewaehlt["zeilen"]) == {"neu:1"}


def test_die_bestaetigung_wird_genauso_verglichen():
    vorher = {"fach": {"kuerzel": "", "datum": None}}
    ergebnis = _dreiwege(vorher, {"fach": {"kuerzel": "ABC", "datum": "2026-10-01"}},
                         {"fach": {"kuerzel": "XY", "datum": "2026-10-30"}})
    assert [_js("beschreibe(k)", k=k) for k in ergebnis["konflikte"]] == [
        {"feld": "Kürzel", "neu": "ABC", "deins": "XY"},
        {"feld": "Datum", "neu": "01.10.2026", "deins": "30.10.2026"}]
