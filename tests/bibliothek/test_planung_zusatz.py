"""buecherlisten/planung/zusatz.py: das Ergebnis je Planungszeile hinter dem Jahrgang.

Die vier Regeln (Entscheidung 2026-10-31) gegen das ausgewählte Schuljahr
2026/2027, der Sonderfall Einführung und Ausmusterung im selben künftigen Jahr
und die Kästen für offene und abgelehnte Anträge.
"""
from __future__ import annotations

import pytest

from buecherlisten.planung import Antragsentscheidung, Planungszeile
from buecherlisten.planung.zusatz import Teil, zusatz_der_zeile, zusatz_je_zeile

SJ = "2026/2027"


def _zeile(ab: str = "", nach: str = "", einfuehrung: str = "", ausmusterung: str = "",
           ) -> Planungszeile:
    return Planungszeile(
        isbn="9783060000005", fach="Deutsch", jahrgang=7, eingefuehrt_ab=ab,
        ausgemustert_nach=nach, leihbar=True,
        antrag_einfuehrung=Antragsentscheidung(ergebnis=einfuehrung),
        antrag_ausmusterung=Antragsentscheidung(ergebnis=ausmusterung))


def _text(zeile: Planungszeile) -> str | None:
    zusatz = zusatz_der_zeile(zeile, SJ)
    return None if zusatz is None else zusatz.text


@pytest.mark.parametrize(("ab", "nach", "erwartet"), [
    # ESJ <= SJ <= ASJ: „bis ASJ“ - auch ohne Einführung (längst eingeführt).
    ("2020/2021", "2026/2027", "bis 2026/2027"),
    ("2020/2021", "2028/2029", "bis 2028/2029"),
    ("", "2027/2028", "bis 2027/2028"),
    ("2026/2027", "2026/2027", "bis 2026/2027"),
    # SJ < ESJ = ASJ: nur dieses Jahr (ohne Anträge nicht genehmigt: siehe unten).
    # SJ < ESJ < ASJ: „von ESJ bis ASJ“.
    ("2027/2028", "2029/2030", "von 2027/2028 bis 2029/2030"),
    # SJ < ESJ, ohne ASJ: „ab ESJ“.
    ("2027/2028", "", "ab 2027/2028"),
    # Sonst nichts: längst eingeführt, nie ausgemustert; ausgemustert nach dem Vorjahr.
    ("2020/2021", "", None),
    ("", "", None),
    ("2020/2021", "2025/2026", None),
])
def test_die_vier_regeln(ab, nach, erwartet):
    assert _text(_zeile(ab, nach)) == erwartet


def test_einfuehrung_und_ausmusterung_im_selben_jahr_bis_beide_genehmigt_sind():
    # Offen, abgelehnt oder ohne Entscheidung: „von … bis …“.
    assert _text(_zeile("2028/2029", "2028/2029")) == "von 2028/2029 bis 2028/2029"
    assert _text(_zeile("2028/2029", "2028/2029", einfuehrung="genehmigt")) \
        == "von 2028/2029 bis 2028/2029"
    assert _text(_zeile("2028/2029", "2028/2029", "genehmigt", "abgelehnt")) \
        == "von 2028/2029 bis 2028/2029"
    # Erst wenn beide genehmigt sind, gilt die Regel: nur dieses Jahr.
    assert _text(_zeile("2028/2029", "2028/2029", "genehmigt", "genehmigt")) == "2028/2029"


def test_ein_offener_oder_abgelehnter_antrag_hat_einen_kasten_ein_genehmigter_nicht():
    offen = zusatz_der_zeile(_zeile("2027/2028"), SJ)
    assert offen is not None
    assert offen.teile == (Teil("ab "), Teil("2027/2028", art="einfuehrung", antrag="offen"))
    abgelehnt = zusatz_der_zeile(_zeile("2027/2028", einfuehrung="abgelehnt"), SJ)
    assert abgelehnt is not None and abgelehnt.teile[1].antrag == "abgelehnt"
    genehmigt = zusatz_der_zeile(_zeile("2027/2028", einfuehrung="genehmigt"), SJ)
    assert genehmigt is not None and genehmigt.teile[1].antrag == ""
    # Von … bis …: jedes Jahr mit seinem eigenen Antrag.
    beide = zusatz_der_zeile(_zeile("2027/2028", "2029/2030", einfuehrung="genehmigt"), SJ)
    assert beide is not None
    assert [(t.text, t.art, t.antrag) for t in beide.teile if t.art] == [
        ("2027/2028", "einfuehrung", ""), ("2029/2030", "ausmusterung", "offen")]


def test_eine_ausmusterung_nach_dem_vorjahr_ist_kein_zusatz_also_kein_kasten():
    assert zusatz_der_zeile(_zeile("2020/2021", "2025/2026"), SJ) is None


def test_mehrere_zeilen_ergeben_je_eines_in_der_reihenfolge_der_uebergabe():
    ergebnis = zusatz_je_zeile((_zeile("2020/2021", "2026/2027"), _zeile("2029/2030"),
                                _zeile("2020/2021")), SJ)
    assert [z.text for z in ergebnis] == ["bis 2026/2027", "ab 2029/2030"]


def test_ein_unlesbares_schuljahr_gibt_nichts():
    assert zusatz_der_zeile(_zeile("2027/2028"), "kaputt") is None
