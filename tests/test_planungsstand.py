"""Der JSON-Vertrag der Konflikterkennung, unabhängig von Vorlagen und HTTP."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

import pytest

from app.planungsansicht import planungskontext
from app.planungsstand import eintrag_stand, fach_stand
from buecherlisten.planung import (
    OHNE_VERLAG,
    Buch,
    Buchbemerkung,
    Buchplanung,
    Planungszeile,
    Ruecklage,
)

_ISBN = "9783060000005"


@pytest.fixture()
def planung():
    return Buchplanung(
        schuljahr="2026/2027", vorjahr="2025/2026",
        buecher=(Buch(_ISBN, "Deutschbuch", "Cornelsen", neupreis=22.5, leihgebuehr=0),
                 Buch("anderes", "Anderes Buch", "Klett")),
        bemerkungen=(Buchbemerkung(_ISBN, "Buchbemerkung\nzweite Zeile"),),
        planung=(
            Planungszeile(_ISBN, "Deutsch", 5, leihbar=True,
                          ausgemustert_nach="2025/2026", bemerkung="alt"),
            Planungszeile(_ISBN, "Deutsch", 5, eingefuehrt_ab="2026/27",
                          leihbar=False, bemerkung="neu"),
            Planungszeile(_ISBN, "Deutsch", 6, eingefuehrt_ab="2027/2028", leihbar=True),
            Planungszeile(_ISBN, "Politik", 7, leihbar=True, bemerkung="anderes Fach"),
            Planungszeile("anderes", "Deutsch", 8, leihbar=True),
        ),
        ruecklagen=(Ruecklage(_ISBN, "Deutsch", anzahl=0, bemerkung="keine Exemplare"),
                    Ruecklage(_ISBN, "Politik", anzahl=9)),
    )


def test_buchstand_behaelt_alle_felder_und_die_rohen_zeilenschluessel(planung):
    erwartet = {
        "buchreihe": {"titel": "Deutschbuch", "verlag": "Cornelsen", "neupreis": 22.5,
                      "leihgebuehr": 0, "bemerkung": "Buchbemerkung\nzweite Zeile"},
        "zeilen": {
            "5|": {"jahrgang": 5, "eingefuehrt_ab": "", "ausgemustert_nach": "2025/2026",
                   "leihbar": True, "bemerkung": "alt"},
            "5|2026/27": {"jahrgang": 5, "eingefuehrt_ab": "2026/27", "ausgemustert_nach": "",
                         "leihbar": False, "bemerkung": "neu"},
            "6|2027/2028": {"jahrgang": 6, "eingefuehrt_ab": "2027/2028", "ausgemustert_nach": "",
                           "leihbar": True, "bemerkung": ""},
        },
        "ruecklage": {"anzahl": 0, "bemerkung": "keine Exemplare"},
    }
    stand = eintrag_stand(planung, _ISBN, "Deutsch")
    assert stand == erwartet
    assert json.loads(json.dumps(stand)) == erwartet
    assert list(stand["zeilen"]) == list(erwartet["zeilen"])
    kontext = planungskontext(planung, schuljahr=planung.schuljahr, mtime=1.0)
    assert kontext["eintrag"](_ISBN, "Deutsch") == erwartet


def test_unbekanntes_buch_ist_none_und_nicht_ein_leerer_stand(planung):
    assert eintrag_stand(planung, "unbekannt", "Deutsch") is None
    stand = eintrag_stand(planung, _ISBN, "unbekannt")
    assert stand["zeilen"] == {}
    # Rücklagenfähigkeit gilt je Buch, nicht nur im angefragten Fach.
    assert stand["ruecklage"] == {"anzahl": None, "bemerkung": ""}


@pytest.mark.parametrize("leihbar", [True, False])
def test_leerer_stand_unterscheidet_fehlende_werte_von_nicht_leihbar(leihbar):
    planung = Buchplanung(
        buecher=(Buch(_ISBN, "Deutschbuch", OHNE_VERLAG),),
        planung=(Planungszeile(_ISBN, "Deutsch", 5, leihbar=leihbar),),
    )
    stand = eintrag_stand(planung, _ISBN, "Deutsch")
    assert stand["buchreihe"] == {
        "titel": "Deutschbuch", "verlag": "", "neupreis": None,
        "leihgebuehr": None, "bemerkung": "",
    }
    assert stand["ruecklage"] == ({"anzahl": None, "bemerkung": ""} if leihbar else None)


def test_ein_schnappschuss_laesst_sich_aendern_ohne_den_planungsstand_zu_aendern(planung):
    vorher = eintrag_stand(planung, _ISBN, "Deutsch")
    bearbeitet = eintrag_stand(planung, _ISBN, "Deutsch")
    bearbeitet["buchreihe"]["titel"] = "Geändert"
    bearbeitet["zeilen"]["5|"]["bemerkung"] = "Geändert"
    bearbeitet["ruecklage"]["anzahl"] = 12
    assert eintrag_stand(planung, _ISBN, "Deutsch") == vorher


@pytest.mark.parametrize("bestaetigt", [True, False])
def test_fachstand_zeigt_nur_eine_vollstaendige_bestaetigung(bestaetigt):
    zeile = Planungszeile(_ISBN, "Deutsch", 5, leihbar=True,
                          kuerzel="FK", datum=date(2026, 9, 3))
    planung = Buchplanung(
        schuljahr="2026/2027", buecher=(Buch(_ISBN, "Deutschbuch", "Cornelsen"),),
        planung=(zeile, replace(zeile, jahrgang=6, kuerzel="FK" if bestaetigt else "")),
    )
    erwartet = {"fach": {"kuerzel": "FK" if bestaetigt else "",
                          "datum": "2026-09-03" if bestaetigt else None}}
    assert fach_stand(planung, "Deutsch") == erwartet
    assert json.loads(json.dumps(fach_stand(planung, "Deutsch"))) == erwartet
    kontext = planungskontext(planung, schuljahr=planung.schuljahr, mtime=1.0)
    assert kontext["fachstand"]("Deutsch") == erwartet
    assert fach_stand(planung, "unbekannt") == {"fach": {"kuerzel": "", "datum": None}}
