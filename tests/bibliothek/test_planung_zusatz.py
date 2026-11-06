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
    # SJ < ESJ = ASJ: nur dieses Jahr (ohne genehmigte Anträge: siehe unten).
    # SJ < ESJ < ASJ: „von ESJ bis ASJ“.
    ("2027/2028", "2029/2030", "von 2027/2028 bis 2029/2030"),
    # SJ < ESJ, ohne ASJ: „ab ESJ“.
    ("2027/2028", "", "ab 2027/2028"),
    # Sonst nichts: längst eingeführt, nie ausgemustert; ausgemustert nach dem Vorjahr.
    ("2020/2021", "", None),
    ("", "", None),
])
def test_die_vier_regeln(ab, nach, erwartet):
    assert _text(_zeile(ab, nach)) == erwartet


def test_zum_laufenden_schuljahr_eingefuehrt_zeigt_die_einfuehrung_bis_sie_genehmigt_ist():
    """Sonst hätte ihr offener oder abgelehnter Antrag kein Jahr für den Kasten."""
    assert _text(_zeile("2026/2027", "2028/2029")) == "von 2026/2027 bis 2028/2029"
    assert _text(_zeile("2026/2027", "2026/2027")) == "von 2026/2027 bis 2026/2027"
    assert _text(_zeile("2026/2027")) == "ab 2026/2027"
    assert _text(_zeile("2026/2027", einfuehrung="abgelehnt")) == "ab 2026/2027"
    # Genehmigt: die Einführung ist vollzogen, es bleibt, was sie nicht sagt.
    assert _text(_zeile("2026/2027", "2028/2029", einfuehrung="genehmigt")) == "bis 2028/2029"
    assert _text(_zeile("2026/2027", "2026/2027", einfuehrung="genehmigt")) == "bis 2026/2027"
    assert _text(_zeile("2026/2027", einfuehrung="genehmigt")) is None


def test_nach_dem_vorjahr_ausgemustert_zeigt_die_ausmusterung_bis_sie_genehmigt_ist():
    assert _text(_zeile("2020/2021", "2025/2026")) == "bis 2025/2026"
    assert _text(_zeile("", "2025/2026", ausmusterung="abgelehnt")) == "bis 2025/2026"
    assert _text(_zeile("2020/2021", "2025/2026", ausmusterung="genehmigt")) is None
    # Früher ausgemustert: nichts, auch ohne Entscheidung.
    assert _text(_zeile("2020/2021", "2024/2025")) is None


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


def test_die_kaesten_der_einfuehrung_zum_laufenden_und_der_ausmusterung_nach_dem_vorjahr():
    einf = zusatz_der_zeile(_zeile("2026/2027"), SJ)
    assert einf is not None
    assert einf.teile == (Teil("ab "), Teil("2026/2027", art="einfuehrung", antrag="offen"))
    ausm = zusatz_der_zeile(_zeile("2020/2021", "2025/2026", ausmusterung="abgelehnt"), SJ)
    assert ausm is not None
    assert ausm.teile == (Teil("bis "), Teil(
        "2025/2026", art="ausmusterung", antrag="abgelehnt",
        hinweis="Ausmusterung der Buchreihe in Jahrgang 7 abgelehnt"))


def test_mehrere_zeilen_ergeben_je_eines_in_der_reihenfolge_der_uebergabe():
    ergebnis = zusatz_je_zeile((_zeile("2020/2021", "2026/2027"), _zeile("2029/2030"),
                                _zeile("2020/2021")), SJ)
    assert [z.text for z in ergebnis] == ["bis 2026/2027", "ab 2029/2030"]


@pytest.mark.parametrize(("ab", "nach", "erwartet"), [
    # Ausmusterung vor der Einführung (nur aus Excel): die Ereignisse der Reihe
    # nach (Entscheidung 2026-11-06; bis dahin nur „ab ESJ“).
    ("2028/2029", "2027/2028", "bis 2027/2028, ab 2028/2029"),
    # Die Ausmusterung liegt vor dem Vorjahr: sie zählt nicht mehr.
    ("2028/2029", "2024/2025", "ab 2028/2029"),
    # Nach dem Vorjahr, offen: sie zählt.
    ("2028/2029", "2025/2026", "bis 2025/2026, ab 2028/2029"),
])
def test_eine_ausmusterung_vor_der_einfuehrung_ergibt_die_ereignisse_der_reihe_nach(
        ab, nach, erwartet):
    assert _text(_zeile(ab, nach)) == erwartet


def test_ein_unlesbares_schuljahr_gibt_nichts():
    assert zusatz_der_zeile(_zeile("2027/2028"), "kaputt") is None


def test_eine_entschiedene_jahreszahl_nennt_entscheidung_datum_und_signatur():
    """Tooltip der Jahreszahl (Entscheidung 2026-11-04); ein offener Antrag hat keinen."""
    from datetime import date

    zeile = Planungszeile(
        isbn="9783060000005", fach="Deutsch", jahrgang=7, eingefuehrt_ab="2027/2028",
        ausgemustert_nach="2029/2030", leihbar=True,
        antrag_einfuehrung=Antragsentscheidung("abgelehnt", "b.lehrer", date(2026, 10, 12)),
        antrag_ausmusterung=Antragsentscheidung("genehmigt"))
    zusatz = zusatz_der_zeile(zeile, SJ)
    assert zusatz is not None
    einfuehrung, ausmusterung = (teil for teil in zusatz.teile if teil.art)
    assert einfuehrung.hinweis == (
        "Einführung der Buchreihe in Jahrgang 7 abgelehnt\nam 12.10.2026\ndurch b.lehrer")
    # Ohne Datum und Signatur (etwa in Excel eingetragen) fallen die Zeilen weg.
    assert ausmusterung.hinweis == "Ausmusterung der Buchreihe in Jahrgang 7 genehmigt"
    offen = zusatz_der_zeile(_zeile("2027/2028"), SJ)
    assert offen is not None and all(not teil.hinweis for teil in offen.teile)


def test_eine_entschiedene_jahreszahl_nennt_die_begruendung_ihres_antrags():
    """Je Antrag eine Begründung (Entscheidung 2026-11-06), im Tooltip als
    letzte Zeile; ein offener Antrag hat weiter keinen Tooltip."""
    zeile = Planungszeile(
        isbn="9783060000005", fach="Deutsch", jahrgang=7, eingefuehrt_ab="2027/2028",
        ausgemustert_nach="2029/2030", leihbar=True,
        antrag_einfuehrung=Antragsentscheidung("genehmigt"),
        begruendung_einfuehrung="neuer Lehrplan", begruendung_ausmusterung="G9")
    zusatz = zusatz_der_zeile(zeile, SJ)
    assert zusatz is not None
    einfuehrung, ausmusterung = (teil for teil in zusatz.teile if teil.art)
    assert einfuehrung.hinweis == (
        "Einführung der Buchreihe in Jahrgang 7 genehmigt\nBegründung: neuer Lehrplan")
    assert ausmusterung.hinweis == ""
