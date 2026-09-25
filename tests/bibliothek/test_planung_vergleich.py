"""buecherlisten/planung/vergleich.py: wann die Datei und IServ gleich sind.

Die Datei ist das Soll. Gleich ist ein Buch, wenn es auf beiden Seiten steht,
seine Werte übereinstimmen und die (Fach, Jahrgang)-Paare aus IServ genau die
sind, in denen die Datei es in diesem Schuljahr führt.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from buecherlisten.planung import (
    BEIDE,
    NUR_EXCEL,
    NUR_ISERV,
    Buch,
    Buchplanung,
    IservBuch,
    aktive_paare,
    vergleiche,
)
from buecherlisten.planung.modelle import OHNE_VERLAG, Planungszeile

TERRA = "9783121000562"
NEU = "9783161484100"


def _stand(*planung: Planungszeile, **felder) -> Buchplanung:
    buch = Buch(isbn=TERRA, titel="Terra 5/6", verlag="Klett",
                kombinationen=(("Erdkunde", 5), ("Erdkunde", 6), ("Politik", 5)),
                leihbar=True, neupreis=25.0, leihgebuehr=5.0)
    return Buchplanung(schuljahr="2026/2027", vorjahr="2025/2026",
                       buecher=(replace(buch, **felder),), planung=planung)


def _iserv(**felder) -> dict[str, IservBuch]:
    werte = dict(isbn=TERRA, titel="Terra 5/6", verlag="Klett", neupreis=25.0,
                 leihgebuehr=5.0, leihbar=True,
                 paare=frozenset({("Erdkunde", 5), ("Erdkunde", 6), ("Politik", 5)}))
    werte.update(felder)
    return {TERRA: IservBuch(**werte)}


def test_gleiche_werte_und_paare_sind_gleich():
    assert vergleiche(_stand(), _iserv())[TERRA].gleich


def test_preise_auf_den_cent_und_texte_ohne_randleerzeichen():
    assert vergleiche(_stand(), _iserv(neupreis=25.001, titel=" Terra 5/6 "))[TERRA].gleich


@pytest.mark.parametrize("feld, iserv_wert", [
    ("titel", "Terra 5/6 neu"), ("verlag", "Westermann"), ("neupreis", 26.0),
    ("leihgebuehr", None), ("leihbar", False),
])
def test_ein_abweichender_wert_nennt_den_iserv_wert(feld, iserv_wert):
    ergebnis = vergleiche(_stand(), _iserv(**{feld: iserv_wert}))[TERRA]
    assert ergebnis.art == BEIDE
    assert ergebnis.iserv == {feld: iserv_wert}
    assert not ergebnis.gleich


def test_ohne_verlag_gleicht_dem_leeren_verlag():
    assert vergleiche(_stand(verlag=OHNE_VERLAG), _iserv(verlag=""))[TERRA].gleich


def test_ein_buch_in_zwei_faechern_muss_in_beiden_stimmen():
    ohne_politik = frozenset({("Erdkunde", 5), ("Erdkunde", 6)})
    ergebnis = vergleiche(_stand(), _iserv(paare=ohne_politik))[TERRA]
    assert ergebnis.fehlt_in_iserv == (("Politik", 5),)
    assert not ergebnis.nur_in_iserv
    assert not ergebnis.gleich


def test_ein_mehrjahresband_muss_in_jedem_jahrgang_stimmen():
    dazu = frozenset({("Erdkunde", 5), ("Erdkunde", 6), ("Erdkunde", 7), ("Politik", 5)})
    ergebnis = vergleiche(_stand(), _iserv(paare=dazu))[TERRA]
    assert ergebnis.nur_in_iserv == (("Erdkunde", 7),)


@pytest.mark.parametrize("zeile, aktiv", [
    # Eingeführt in diesem Schuljahr oder vorher: aktiv.
    (Planungszeile(TERRA, "Politik", 5, eingefuehrt_ab="2026/2027"), True),
    (Planungszeile(TERRA, "Politik", 5, eingefuehrt_ab="2020/2021"), True),
    (Planungszeile(TERRA, "Politik", 5, eingefuehrt_ab="2027/2028"), False),
    # Ausgemustert nach diesem Schuljahr oder später: aktiv.
    (Planungszeile(TERRA, "Politik", 5, ausgemustert_nach="2026/2027"), True),
    (Planungszeile(TERRA, "Politik", 5, ausgemustert_nach="2030/2031"), True),
    (Planungszeile(TERRA, "Politik", 5, ausgemustert_nach="2025/2026"), False),
])
def test_die_planung_entscheidet_ueber_das_schuljahr(zeile, aktiv):
    stand = _stand(zeile)
    assert (("Politik", 5) in aktive_paare(stand, stand.buecher[0])) is aktiv
    assert vergleiche(stand, _iserv())[TERRA].gleich is aktiv


def test_eine_geplante_einfuehrung_in_diesem_jahr_gleicht_iserv():
    """Ein nur geplanter Jahrgang (in keiner Liste der Datei) zählt, sobald er gilt."""
    stand = _stand(Planungszeile(TERRA, "Erdkunde", 7, eingefuehrt_ab="2026/2027"))
    dazu = frozenset({("Erdkunde", 5), ("Erdkunde", 6), ("Erdkunde", 7), ("Politik", 5)})
    assert vergleiche(stand, _iserv(paare=dazu))[TERRA].gleich


def test_nur_in_der_datei():
    ergebnis = vergleiche(_stand(), {})[TERRA]
    assert ergebnis.art == NUR_EXCEL
    assert len(ergebnis.fehlt_in_iserv) == 3


def test_nur_in_iserv():
    fremd = IservBuch(isbn=NEU, titel="Neu", verlag="", neupreis=None, leihgebuehr=None,
                      leihbar=False, paare=frozenset({("Deutsch", 7)}))
    ergebnis = vergleiche(_stand(), {**_iserv(), NEU: fremd})[NEU]
    assert ergebnis.art == NUR_ISERV
    assert ergebnis.nur_in_iserv == (("Deutsch", 7),)


def test_in_der_datei_dieses_jahr_nicht_gefuehrt_aber_in_iserv():
    alle_aus = tuple(Planungszeile(TERRA, f, j, ausgemustert_nach="2025/2026")
                     for f, j in (("Erdkunde", 5), ("Erdkunde", 6), ("Politik", 5)))
    assert vergleiche(_stand(*alle_aus), _iserv())[TERRA].art == NUR_ISERV


def test_ohne_vorkommen_auf_beiden_seiten_kein_vergleich():
    alle_aus = tuple(Planungszeile(TERRA, f, j, ausgemustert_nach="2025/2026")
                     for f, j in (("Erdkunde", 5), ("Erdkunde", 6), ("Politik", 5)))
    assert vergleiche(_stand(*alle_aus), {}) == {}
