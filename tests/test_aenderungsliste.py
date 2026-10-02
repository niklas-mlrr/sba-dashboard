"""app/aenderungsliste.py: das Raster der Änderungsliste, an den Randfällen aus dem Entwurf.

Die Daten sind die des Mockups (Variante E). Geprüft wird über eine
Textansicht je Zeile - so liest sich ein Fehlschlag wie die Seite selbst:
``links | Mitte | rechts``, eine Zelle als ``Stufe:Inhalt(Zeilen)``, ``#`` vor
einem Titel, ``~`` vor einer Zelle, die am Kasten darüber hängt, ``*`` hinter
einer gestreckten.
"""
from __future__ import annotations

from app.aenderungsliste import FachBlock, Zelle, baue_tabelle
from buecherlisten.planung import (
    ART_AUSMUSTERUNG,
    ART_EINFUEHRUNG,
    RANG_STANDARD,
    Aenderung,
    Antragsentscheidung,
    lies_rang,
    ordne_aenderungen,
)


def _buch(art: str, fach: str, titel: str, *jahrgaenge: tuple[int, int],
          leihbar: bool = True) -> list[Aenderung]:
    """Ein Buch mit seinen Anträgen: je (Jahrgang, Jahr der Angabe) einer."""
    return [Aenderung(isbn=f"{fach}|{titel}", titel=titel, verlag="Klett", fach=fach,
                      jahrgang=jg, art=art, schuljahr=f"{jahr}/{jahr + 1}",
                      entscheidung=Antragsentscheidung(), leihbar=leihbar)
            for jg, jahr in jahrgaenge]


AUS, EIN = ART_AUSMUSTERUNG, ART_EINFUEHRUNG

DATEN = [
    *_buch(AUS, "Biologie", "Natura 5", (5, 2026)),
    *_buch(EIN, "Biologie", "Biologie heute 5", (5, 2027)),
    *_buch(EIN, "Biologie", "Natura 5/7", (5, 2027), (7, 2027)),
    *_buch(EIN, "Biologie", "Bio Arbeitsheft 6", (6, 2027), leihbar=False),
    *_buch(AUS, "Chemie", "Chemie heute", (9, 2025)),
    *_buch(AUS, "Chemie", "Chemie 10 alt", (10, 2026)),
    *_buch(EIN, "Chemie", "Übergangsheft", (10, 2027), leihbar=False),
    *_buch(AUS, "Chemie", "Übergangsheft", (10, 2027), leihbar=False),
    *_buch(EIN, "Chemie", "Elemente 10", (10, 2028)),
    *_buch(AUS, "Deutsch", "Deutschbuch 8 AH", (8, 2026), leihbar=False),
    *_buch(AUS, "Deutsch", "Deutschbuch 8", (8, 2026)),
    *_buch(EIN, "Deutsch", "Deutschbuch 8 NA", (8, 2027)),
    *_buch(AUS, "Mathematik", "Lambacher 5", (5, 2026)),
    *_buch(AUS, "Mathematik", "Lambacher 6", (6, 2026)),
    *_buch(EIN, "Mathematik", "Lambacher 5 2025", (5, 2027)),
    *_buch(EIN, "Mathematik", "Arbeitsheft 5/6", (5, 2027), (6, 2027), leihbar=False),
    *_buch(AUS, "Musik", "Musik um uns 5", (5, 2026)),
    *_buch(AUS, "Musik", "Musik um uns 6", (6, 2026)),
    *_buch(AUS, "Musik", "Musik um uns 7", (7, 2026)),
    *_buch(EIN, "Musik", "Spielpläne 5-7", (5, 2027), (6, 2027), (7, 2027)),
    *_buch(EIN, "Musik", "Liederbuch 6", (6, 2027)),
    *_buch(AUS, "Politik", "Politik & Co. 7/8", (7, 2026), (8, 2026)),
    *_buch(EIN, "Politik", "Politik erleben 7", (7, 2027)),
    *_buch(EIN, "Politik", "Politik erleben 8", (8, 2027)),
]


def _zelle(z: Zelle | None) -> str:
    if z is None:
        return ""
    if z.leer:
        return f"leer({z.rowspan})"
    a = z.eintrag
    inhalt = ("#" + a.titel + " " if z.titel else "") + f"Jg{a.jahrgang}"
    return f"{'' if z.anfang else '~'}{z.stufe}:{inhalt}({z.rowspan}){'*' if z.gestreckt else ''}"


def _ansicht(bloecke: list[FachBlock], fach: str) -> list[str]:
    block = next(b for b in bloecke if b.fach == fach)
    zeilen = []
    for gruppe in block.gruppen:
        zeilen.append("--")
        for zeile in gruppe.zeilen:
            mitte = ""
            if zeile.mitte:
                mitte = f"{zeile.mitte.haupt}{zeile.mitte.neben}"
            zeilen.append(f"{_zelle(zeile.aus)} | {mitte} | {_zelle(zeile.ein)}".strip())
    return zeilen


def _tabelle(rang=RANG_STANDARD) -> list[FachBlock]:
    return baue_tabelle(ordne_aenderungen(DATEN, rang), rang)


def test_mathe_ein_kasten_ueber_zwei_zeilen_und_die_fortsetzung_haengt_an():
    assert _ansicht(_tabelle(), "Mathematik") == [
        "--",
        # Lambacher 5 ist gestreckt neben zwei neuen Büchern.
        "0:#Lambacher 5 Jg5(4)* | 5[2027] | 0:#Lambacher 5 2025 Jg5(2)",
        "|  |",
        "|  | 0:#Arbeitsheft 5/6 Jg5(2)",
        "|  |",
        "--",
        # Das Arbeitsheft Jg. 6 hängt am Kasten darüber: ohne Titel, keine Einrückung.
        "0:#Lambacher 6 Jg6(2) | 6[2027] | ~0:Jg6(2)",
        "|  |",
    ]


def test_biologie_ein_getrenntes_buch_rueckt_nur_seine_spalte_ein():
    ansicht = _ansicht(_tabelle(), "Biologie")
    # Natura 5/7 Jg. 7 steht getrennt (Jg. 6 dazwischen) und ohne Titel.
    assert "leer(1) | 7[2027] | 1:Jg7(1)" in ansicht
    # Die Einführungen sind eingerückt (Stufen 0, 1, 2), die Ausmusterungen nicht.
    assert "0:#Natura 5 Jg5(4)* | 5[2027] | 0:#Biologie heute 5 Jg5(2)" in ansicht
    assert "|  | 1:#Natura 5/7 Jg5(2)" in ansicht
    assert "leer(2) | 6[2027] | 2:#Bio Arbeitsheft 6 Jg6(2)" in ansicht


def test_chemie_das_uebergangsheft_steht_als_ausmusterung_ohne_titel():
    ansicht = _ansicht(_tabelle(), "Chemie")
    # Jg. 10 hat zwei Wechsel: eine Gruppe, der Jahrgang steht einmal.
    assert "1:#Chemie 10 alt Jg10(2) | 10[2027, 2028] | 0:#Übergangsheft Jg10(2)" in ansicht
    # Links ohne Titel und getrennt: die Ausmusterungen rücken ein.
    assert "2:Jg10(2) |  | 0:#Elemente 10 Jg10(2)" in ansicht


def test_zwei_gehen_eines_kommt_das_eine_ist_gestreckt():
    assert _ansicht(_tabelle(), "Deutsch") == [
        "--",
        "0:#Deutschbuch 8 Jg8(2) | 8[2027] | 0:#Deutschbuch 8 NA Jg8(4)*",
        "|  |",
        "0:#Deutschbuch 8 AH Jg8(2) |  |",
        "|  |",
    ]


def test_musik_reichweite_haelt_den_kasten_zusammen_soweit_es_geht():
    assert _ansicht(_tabelle(), "Musik") == [
        "--",
        "0:#Musik um uns 5 Jg5(2) | 5[2027] | 0:#Spielpläne 5-7 Jg5(2)",
        "|  |",
        "--",
        # Jg. 6: Spielpläne kommt von oben, steht oben und hängt an; das
        # Liederbuch ist das zweite Buch der Spalte und rückt eine Stufe ein.
        "0:#Musik um uns 6 Jg6(4)* | 6[2027] | ~0:Jg6(2)",
        "|  |",
        "|  | 1:#Liederbuch 6 Jg6(2)",
        "|  |",
        "--",
        # Jg. 7: unter dem Liederbuch getrennt - ohne Titel auf der Stufe von Spielpläne.
        "0:#Musik um uns 7 Jg7(2) | 7[2027] | 0:Jg7(2)",
        "|  |",
    ]


def test_politik_der_alte_band_steht_einmal_ueber_beide_jahrgaenge():
    assert _ansicht(_tabelle(), "Politik") == [
        "--",
        "0:#Politik & Co. 7/8 Jg7(2) | 7[2027] | 0:#Politik erleben 7 Jg7(2)",
        "|  |",
        "--",
        "~0:Jg8(2) | 8[2027] | 0:#Politik erleben 8 Jg8(2)",
        "|  |",
    ]


def test_nach_jahr_sortiert_werden_gleiche_jahre_eine_gruppe():
    tabelle = _tabelle(lies_rang("wechsel"))
    biologie = next(b for b in tabelle if b.fach == "Biologie")
    assert len(biologie.gruppen) == 1
    mitte = biologie.gruppen[0].zeilen[0].mitte
    assert (mitte.haupt, mitte.neben, mitte.paar) == (2027, [5, 6, 7], False)
    # Der zweite und dritte Teil beginnen mit einer feinen Linie.
    assert [z.unterabschnitt for z in biologie.gruppen[0].zeilen].count(True) == 2
    chemie = next(b for b in tabelle if b.fach == "Chemie")
    assert [(g.zeilen[0].mitte.haupt, g.zeilen[0].mitte.neben) for g in chemie.gruppen] \
        == [(2026, [9]), (2027, [10]), (2028, [10])]
    assert chemie.gruppen[0].zeilen[0].mitte.paar


def test_der_partnerfilter_kennt_gruppen_mit_beiden_seiten():
    tabelle = _tabelle()
    chemie = next(b for b in tabelle if b.fach == "Chemie")
    assert [g.mit_partner for g in chemie.gruppen] == [False, True]
