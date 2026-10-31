"""buecherlisten/planung/farben.py: wie ein Buch in der Liste eines Fachs aussieht.

Die Regeln (Entscheidung 2026-10-30) an je einem kleinen Stand: blau für
Einführungen, rot für Ausmusterungen, gelb für einen Wechsel von „leihbar“ -
ganz oder nur in der Zelle, und welche Jahrgangszahl farbig geschrieben ist.
"""
from __future__ import annotations

from buecherlisten.planung import Buch, Buchplanung, Planungszeile
from buecherlisten.planung.farben import (
    AENDERUNG,
    AUSMUSTERUNG,
    EINFUEHRUNG,
    Jahrgangswert,
    in_ausmusterungen,
    markierung,
)

ISBN = "9783060000005"


def _stand(*zeilen: Planungszeile) -> Buchplanung:
    return Buchplanung(
        schuljahr="2026/2027", vorjahr="2025/2026",
        buecher=(Buch(isbn=ISBN, titel="Deutschbuch", verlag="Cornelsen"),),
        planung=zeilen,
    )


def _zeile(jahrgang: int, ab: str = "", nach: str = "", leihbar: bool = True,
           fach: str = "Deutsch") -> Planungszeile:
    return Planungszeile(isbn=ISBN, fach=fach, jahrgang=jahrgang, eingefuehrt_ab=ab,
                         ausgemustert_nach=nach, leihbar=leihbar)


def _markierung(*zeilen: Planungszeile, fach: str = "Deutsch"):
    stand = _stand(*zeilen)
    return markierung(stand, stand.buecher[0], fach)


def test_ohne_planung_ist_nichts_farbig():
    m = _markierung(_zeile(5), _zeile(6))
    assert (m.ganz, m.jahrgang, m.leihbar, m.strich) == (frozenset(), frozenset(), frozenset(), ())
    assert m.jahrgaenge == (Jahrgangswert(5), Jahrgangswert(6))
    assert m.zelle() == "" and m.strich_klasse() == ""


def test_eine_einfuehrung_neben_laufenden_jahrgaengen_faerbt_nur_die_jahrgang_zelle():
    m = _markierung(_zeile(5), _zeile(6, ab="2026/2027"), _zeile(7, ab="2027/2028"))
    assert m.ganz == frozenset() and m.jahrgang == {EINFUEHRUNG}
    # Blau geschrieben nur die Einführung zum laufenden Schuljahr.
    assert m.jahrgaenge == (Jahrgangswert(5), Jahrgangswert(6, "", EINFUEHRUNG),
                           Jahrgangswert(7, "ab 2027/2028"))
    assert m.zelle("jahrgang") == "band-einfuehrung" and m.zelle() == ""


def test_ein_ganz_neues_buch_ist_ganz_blau_auch_wenn_es_erst_spaeter_kommt():
    m = _markierung(_zeile(7, ab="2027/2028"), _zeile(8, ab="2028/2029"))
    assert m.ganz == {EINFUEHRUNG} and m.jahrgang == frozenset()
    assert all(j.farbe == "" for j in m.jahrgaenge)
    # Läuft es in einem anderen Fach schon, ist es nicht ganz neu.
    m = _markierung(_zeile(7, ab="2027/2028"), _zeile(5, fach="Latein"))
    assert m.ganz == frozenset() and m.jahrgang == {EINFUEHRUNG}


def test_eine_ausmusterung_nach_dem_vorjahr_ist_rot_und_durchgestrichen():
    m = _markierung(_zeile(5, nach="2025/2026"), _zeile(6))
    assert m.jahrgang == {AUSMUSTERUNG}
    assert m.jahrgaenge == (Jahrgangswert(5, "bis 2025/2026", AUSMUSTERUNG), Jahrgangswert(6))
    # Was früher endete, steht nicht mehr in der Spalte.
    m = _markierung(_zeile(5, nach="2024/2025"), _zeile(6))
    assert m.jahrgaenge == (Jahrgangswert(6),) and m.strich == ()


def test_ein_buch_das_danach_nirgends_mehr_steht_ist_ganz_rot():
    m = _markierung(_zeile(5, nach="2027/2028"), _zeile(6, nach="2028/2029"))
    assert m.ganz == {AUSMUSTERUNG}
    # Künftige Ausmusterung: rot, aber die Zahl nicht durchgestrichen.
    assert all(j.farbe == "" for j in m.jahrgaenge)
    m = _markierung(_zeile(5, nach="2027/2028"), _zeile(5, fach="Latein"))
    assert m.ganz == frozenset() and m.jahrgang == {AUSMUSTERUNG}


def test_ein_wechsel_von_leihbar_ist_nur_gelb():
    m = _markierung(_zeile(5, nach="2025/2026", leihbar=True),
                    _zeile(5, ab="2026/2027", leihbar=False))
    assert (m.ganz, m.jahrgang, m.leihbar) == (frozenset(), frozenset(), {AENDERUNG})
    assert m.jahrgaenge == (Jahrgangswert(5),)
    assert m.zelle("leihbar") == "band-aenderung"


def test_mehrere_farben_stehen_rot_gelb_blau():
    m = _markierung(_zeile(5, nach="2025/2026"), _zeile(6),
                    _zeile(7, nach="2027/2028", leihbar=True),
                    _zeile(7, ab="2028/2029", leihbar=False),
                    _zeile(8, ab="2026/2027"))
    assert m.strich == (AUSMUSTERUNG, AENDERUNG, EINFUEHRUNG)
    assert m.strich_klasse() == "strich-ausmusterung-aenderung-einfuehrung"
    assert m.zelle("jahrgang") == "band-ausmusterung-einfuehrung"
    # Eine Zelle trägt die Farben der Zeile und ihre eigenen.
    ganz_neu = _markierung(_zeile(7, ab="2026/2027"))
    assert ganz_neu.zelle("", AENDERUNG) == "band-aenderung-einfuehrung"


def test_ausmusterungen_zeigen_was_aus_den_regalen_geht():
    stand = _stand(_zeile(5, nach="2025/2026"), _zeile(6, nach="2025/2026"))
    assert in_ausmusterungen(stand, stand.buecher[0], "Deutsch")
    # Läuft ein leihbarer Jahrgang weiter, ist es keine Ausmusterung …
    stand = _stand(_zeile(5, nach="2025/2026"), _zeile(6))
    assert not in_ausmusterungen(stand, stand.buecher[0], "Deutsch")
    # … ein Kaufbuch-Jahrgang hält es nicht heraus (es steht dann in beiden Listen).
    stand = _stand(_zeile(7, nach="2025/2026"), _zeile(8, leihbar=False))
    assert in_ausmusterungen(stand, stand.buecher[0], "Deutsch")
    m = markierung(stand, stand.buecher[0], "Deutsch")
    assert m.jahrgaenge == (Jahrgangswert(7, "bis 2025/2026", AUSMUSTERUNG), Jahrgangswert(8))


def test_keine_ausmusterung_ohne_leihbares_vor_zwei_jahren_oder_mit_neuer_einfuehrung():
    for zeilen in (
        (_zeile(5, nach="2025/2026", leihbar=False),),          # reines Kaufbuch
        (_zeile(5, nach="2024/2025"),),                         # schon voriges Jahr weg
        (_zeile(5, nach="2025/2026"), _zeile(6, ab="2027/2028")),  # kommt wieder
    ):
        stand = _stand(*zeilen)
        assert not in_ausmusterungen(stand, stand.buecher[0], "Deutsch"), zeilen
