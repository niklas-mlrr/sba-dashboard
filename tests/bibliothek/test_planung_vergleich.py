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


def _stand(*planung: Planungszeile, leihbar: bool = True, **felder) -> Buchplanung:
    """Terra in drei Paaren, leihbar; ``planung`` ersetzt die Zeile ihres Paars.

    Wie in einer gelesenen Datei ist ein Paar nur dann eingeführt, wenn seine
    Zeile keine Einführung hat.
    """
    paare = (("Erdkunde", 5), ("Erdkunde", 6), ("Politik", 5))
    gegeben = {(z.fach, z.jahrgang) for z in planung}
    zeilen = tuple(replace(z, leihbar=leihbar) for z in planung) + tuple(
        Planungszeile(TERRA, f, j, leihbar=leihbar) for f, j in paare if (f, j) not in gegeben)
    buch = Buch(isbn=TERRA, titel="Terra 5/6", verlag="Klett",
                kombinationen=tuple(sorted((z.fach, z.jahrgang) for z in zeilen
                                           if not z.eingefuehrt_ab)),
                neupreis=25.0, leihgebuehr=5.0)
    return Buchplanung(schuljahr="2026/2027", vorjahr="2025/2026",
                       buecher=(replace(buch, **felder),), planung=zeilen)


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


def test_leihbar_wird_je_paar_verglichen():
    """In IServ steht „leihbar“ je Jahrgangsliste, in der Datei je Zeile."""
    nur_erdkunde_5 = frozenset({("Erdkunde", 5)})
    ergebnis = vergleiche(_stand(), _iserv(leihbar_paare=nur_erdkunde_5))[TERRA]
    assert ergebnis.leihbar_anders == ((("Erdkunde", 6), False), (("Politik", 5), False))
    assert ergebnis.iserv == {"leihbar": False}
    assert not ergebnis.gleich
    # Stimmt es je Paar, ist das Buch gleich - auch wenn es nur teils leihbar ist.
    stand = _stand(Planungszeile(TERRA, "Erdkunde", 6), Planungszeile(TERRA, "Politik", 5))
    stand = replace(stand, planung=tuple(replace(z, leihbar=(z.fach, z.jahrgang) == ("Erdkunde", 5))
                                         for z in stand.planung))
    assert vergleiche(stand, _iserv(leihbar_paare=nur_erdkunde_5))[TERRA].gleich


def test_ein_wechsel_von_leihbar_vergleicht_die_zeile_die_wirkt():
    """Die alte Zeile (leihbar, bis zum Vorjahr) zählt nicht mehr, die neue schon."""
    stand = _stand(Planungszeile(TERRA, "Politik", 5, ausgemustert_nach="2025/2026"))
    neu = replace(stand, planung=stand.planung + (
        Planungszeile(TERRA, "Politik", 5, eingefuehrt_ab="2026/2027", leihbar=False),))
    alle = frozenset({("Erdkunde", 5), ("Erdkunde", 6)})
    assert vergleiche(neu, _iserv(leihbar_paare=alle))[TERRA].gleich
    assert vergleiche(neu, _iserv())[TERRA].leihbar_anders == ((("Politik", 5), True),)


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
    # Ohne Inventar ist unbekannt, ob es die Buchreihe gibt.
    assert ergebnis.buchreihe_angelegt is None and ergebnis.buchreihe_fehlt == ()


def test_nur_in_der_datei_mit_inventar():
    """Entscheidung 2026-11-04: fehlt die Buchreihe im Inventar, fehlt sie jedem
    Jahrgang; gibt es sie, zählt ihre Zuweisung (unlesbar: nicht verglichen)."""
    ergebnis = vergleiche(_stand(), {}, {})[TERRA]
    assert ergebnis.buchreihe_angelegt is False and ergebnis.buchreihe_fehlt == (5, 6)
    ergebnis = vergleiche(_stand(), {}, {TERRA: frozenset({5})})[TERRA]
    assert ergebnis.buchreihe_angelegt is True and ergebnis.buchreihe_fehlt == (6,)
    ergebnis = vergleiche(_stand(), {}, {TERRA: None})[TERRA]
    assert ergebnis.buchreihe_angelegt is True and ergebnis.buchreihe_fehlt == ()


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


def test_je_eintrag_ist_ein_anderes_leihbar_ein_fehlender_und_ein_ueberzaehliger_eintrag():
    """Die Farben vergleichen je (Fach, Jahrgang, leihbar) - Entscheidung 2026-10-31."""
    abweichung = vergleiche(_stand(leihbar=False), _iserv(
        leihbar_paare=frozenset({("Erdkunde", 5)})))[TERRA]
    assert abweichung.eintraege_fehlen == (("Erdkunde", 5, False),)
    assert abweichung.eintraege_nur_iserv == (("Erdkunde", 5, True),)
    assert vergleiche(_stand(), _iserv())[TERRA].eintraege_fehlen == ()


def test_je_eintrag_beim_wechsel_von_leihbar_zaehlt_die_zeile_die_dieses_jahr_wirkt():
    stand = _stand(Planungszeile(TERRA, "Erdkunde", 6, ausgemustert_nach="2025/2026"))
    stand = replace(stand, planung=stand.planung + (
        Planungszeile(TERRA, "Erdkunde", 6, eingefuehrt_ab="2026/2027", leihbar=False),))
    abweichung = vergleiche(stand, _iserv())[TERRA]
    assert abweichung.eintraege_fehlen == (("Erdkunde", 6, False),)
    assert abweichung.eintraege_nur_iserv == (("Erdkunde", 6, True),)


def test_je_eintrag_nur_in_der_datei_und_nur_in_iserv():
    nur_datei = vergleiche(_stand(), {})[TERRA]
    assert nur_datei.art == NUR_EXCEL and len(nur_datei.eintraege_fehlen) == 3
    nur_iserv = vergleiche(replace(_stand(), buecher=(), planung=()), _iserv())[TERRA]
    assert nur_iserv.art == NUR_ISERV
    assert nur_iserv.eintraege_nur_iserv == (
        ("Erdkunde", 5, True), ("Erdkunde", 6, True), ("Politik", 5, True))


def test_die_buchreihe_braucht_jeden_jahrgang_der_dieses_jahr_gilt():
    """Erst muss die Buchreihe dem Jahrgang zugewiesen sein, dann kommt das Buch
    in die Bücherliste. Zu viele Jahrgänge an der Buchreihe schaden nicht."""
    stand = _stand(Planungszeile(TERRA, "Erdkunde", 7, eingefuehrt_ab="2027/2028"),
                   Planungszeile(TERRA, "Politik", 8, ausgemustert_nach="2025/2026"))
    # Jg. 7 kommt erst, Jg. 8 ist weg: gebraucht werden nur 5 und 6.
    assert vergleiche(stand, _iserv(buchreihe_jahrgaenge=frozenset({5, 6, 9})))[TERRA].gleich
    ergebnis = vergleiche(stand, _iserv(buchreihe_jahrgaenge=frozenset({5})))[TERRA]
    assert ergebnis.buchreihe_fehlt == (6,) and not ergebnis.gleich
    # Unbekannt (None) wird nicht verglichen.
    assert vergleiche(stand, _iserv())[TERRA].buchreihe_fehlt == ()


def test_die_buchreihe_eines_buchs_in_keiner_liste_kommt_aus_dem_inventar():
    ergebnis = vergleiche(_stand(), {}, {TERRA: frozenset({6})})[TERRA]
    assert ergebnis.art == NUR_EXCEL and ergebnis.buchreihe_fehlt == (5,)
    # Kennen die Listen die Zuweisung, gilt die aus den Listen.
    ergebnis = vergleiche(_stand(), _iserv(buchreihe_jahrgaenge=frozenset({5, 6})),
                          {TERRA: frozenset()})[TERRA]
    assert ergebnis.buchreihe_fehlt == ()
