"""buecherlisten/planung/farben.py: wie ein Buch in einer Bücherliste aussieht.

Die Regeln (Entscheidung 2026-10-31) an je einem kleinen Stand: die Schrift
zeigt die Planung je Jahrgang (blau Einführung, rot Ausmusterung,
durchgestrichen nach dem Vorjahr weg), die Markierung den Vergleich mit IServ
(fehlt dort, steht dort noch), der Hintergrund nur, was ganz neu oder ganz weg
ist. „Leihbar“ hängt am Jahrgang: ein Wechsel ist Ausmusterung und Einführung.
"""
from __future__ import annotations

from buecherlisten.planung import Abweichung, Buch, Buchplanung, Planungszeile
from buecherlisten.planung.farben import (
    AUSMUSTERUNG,
    EINFUEHRUNG,
    FACH,
    FEHLT,
    ISERV,
    STEHT_NOCH,
    Wert,
    im_fach,
    in_ausmusterungen,
    markierung,
)
from buecherlisten.planung.vergleich import BEIDE, NUR_EXCEL

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


def _markierung(*zeilen: Planungszeile, fach: str = "Deutsch",
                abweichung: Abweichung | None = None):
    stand = _stand(*zeilen)
    return markierung(stand, stand.buecher[0], abweichung, im=im_fach(fach))


def _werte(m) -> list[tuple[str, str, str, bool, str]]:
    """(Text, Zusatz, Planfarbe, durchgestrichen, IServ) je Wert, über alle Teilzeilen."""
    return [(w.text, w.zusatz, w.plan, w.durch, w.iserv) for w in m.werte]


def test_ohne_planung_ist_nichts_farbig():
    m = _markierung(_zeile(5), _zeile(6))
    assert _werte(m) == [("5", "", "", False, ""), ("6", "", "", False, "")]
    assert m.ganz == "" and m.strich() == () and m.strich_klasse() == ""
    assert m.jahrgaenge == (5, 6) and m.leihbar and not m.leihbar_teilweise


def test_eine_einfuehrung_ist_blau_geschrieben_auch_eine_kuenftige():
    m = _markierung(_zeile(5), _zeile(6, ab="2026/2027"), _zeile(7, ab="2027/2028"))
    assert m.ganz == ""
    assert _werte(m) == [("5", "", "", False, ""),
                         ("6", "", EINFUEHRUNG, False, ""),
                         ("7", "ab 2027/2028", EINFUEHRUNG, False, "")]
    assert m.strich() == (EINFUEHRUNG,)
    assert m.werte[1].hinweis == "Planung: als Leihbuch eingeführt zu 2026/2027"
    assert m.werte[2].hinweis == "Planung: als Leihbuch eingeführt ab 2027/2028"


def test_ein_ganz_neues_buch_hinterlegt_die_zeile():
    m = _markierung(_zeile(7, ab="2027/2028"), _zeile(8, ab="2028/2029"))
    assert m.ganz == EINFUEHRUNG
    # Läuft es in einem anderen Fach schon, ist es nicht ganz neu.
    assert _markierung(_zeile(7, ab="2027/2028"), _zeile(5, fach="Latein")).ganz == ""


def test_eine_ausmusterung_nach_dem_vorjahr_ist_rot_und_durchgestrichen():
    m = _markierung(_zeile(5, nach="2025/2026"), _zeile(6))
    assert _werte(m) == [("5", "bis 2025/2026", AUSMUSTERUNG, True, ""),
                         ("6", "", "", False, "")]
    assert m.werte[0].hinweis == "Planung: als Leihbuch ausgemustert nach 2025/2026"
    # Was früher endete, steht nicht mehr in der Spalte.
    m = _markierung(_zeile(5, nach="2024/2025"), _zeile(6))
    assert _werte(m) == [("6", "", "", False, "")] and m.strich() == ()


def test_ein_auslaufender_jahrgang_ist_rot_aber_nicht_durchgestrichen():
    m = _markierung(_zeile(5), _zeile(6, nach="2026/2027"))
    assert _werte(m)[1] == ("6", "bis 2026/2027", AUSMUSTERUNG, False, "")
    assert m.werte[1].hinweis == "Planung: als Leihbuch läuft aus (bis 2026/2027)"


def test_ein_buch_das_danach_nirgends_mehr_steht_hinterlegt_die_zeile_rot():
    assert _markierung(_zeile(5, nach="2027/2028"), _zeile(6, nach="2028/2029")).ganz \
        == AUSMUSTERUNG
    assert _markierung(_zeile(5, nach="2027/2028"), _zeile(5, fach="Latein")).ganz == ""


def test_ein_wechsel_von_leihbar_ist_ausmusterung_und_einfuehrung_in_zwei_teilzeilen():
    m = _markierung(_zeile(5), _zeile(6),
                    _zeile(7, nach="2025/2026", leihbar=True),
                    _zeile(7, ab="2026/2027", leihbar=False))
    leihbar, kauf = m.teilzeilen
    assert (leihbar.leihbar, kauf.leihbar) == (True, False)
    assert [(w.text, w.plan, w.durch) for w in leihbar.werte] == [
        ("5", "", False), ("6", "", False), ("7", AUSMUSTERUNG, True)]
    assert [(w.text, w.plan, w.durch) for w in kauf.werte] == [("7", EINFUEHRUNG, False)]
    assert m.leihbar_teilweise and m.jahrgaenge == (5, 6, 7)
    # Das Buch ist zum ersten Mal Kaufbuch: die Teilzeile ist ganz neu.
    assert (leihbar.ganz, kauf.ganz) == ("", EINFUEHRUNG)
    assert m.strich() == (AUSMUSTERUNG, EINFUEHRUNG)


def test_wird_das_ganze_buch_kaufbuch_ist_die_eine_teilzeile_weg_die_andere_neu():
    m = _markierung(_zeile(5, nach="2025/2026"), _zeile(6, nach="2025/2026"),
                    _zeile(5, ab="2026/2027", leihbar=False),
                    _zeile(6, ab="2026/2027", leihbar=False))
    leihbar, kauf = m.teilzeilen
    assert (m.ganz, leihbar.ganz, kauf.ganz) == ("", AUSMUSTERUNG, EINFUEHRUNG)


def test_iserv_fehlt_und_steht_noch_je_eintrag():
    """Führt IServ Jg. 7 noch als leihbar, steht er dort noch, und als Kaufbuch fehlt er."""
    abweichung = Abweichung(
        ISBN, BEIDE,
        eintraege_fehlen=(("Deutsch", 7, False), ("Deutsch", 8, True)),
        eintraege_nur_iserv=(("Deutsch", 7, True), ("Deutsch", 10, True), ("Latein", 5, True)))
    m = _markierung(_zeile(7, nach="2025/2026", leihbar=True),
                    _zeile(7, ab="2026/2027", leihbar=False),
                    _zeile(8, ab="2026/2027"), abweichung=abweichung)
    leihbar, kauf = m.teilzeilen
    # Jg. 10 kennt die Datei nicht: er steht nur da, weil IServ ihn führt -
    # durchgestrichen, ohne Planfarbe. Latein gehört nicht in diese Zeile.
    assert [(w.text, w.plan, w.durch, w.iserv) for w in leihbar.werte] == [
        ("7", AUSMUSTERUNG, True, STEHT_NOCH),
        ("8", EINFUEHRUNG, False, FEHLT),
        ("10", "", True, STEHT_NOCH)]
    assert [(w.text, w.iserv, w.markierung) for w in kauf.werte] == [("7", FEHLT, EINFUEHRUNG)]
    assert leihbar.werte[2].hinweis == "IServ: als Leihbuch noch eingetragen"
    assert kauf.werte[0].hinweis == (
        "Planung: als Kaufbuch eingeführt zu 2026/2027 · IServ: als Kaufbuch noch nicht eingetragen")
    # Der Strich der Fach-Ansicht zeigt nur die Planung, der einer IServ-Ansicht nur IServ.
    assert m.strich() == (AUSMUSTERUNG, EINFUEHRUNG)
    assert m.strich(ISERV) == (AUSMUSTERUNG, EINFUEHRUNG)
    assert _markierung(_zeile(5), abweichung=Abweichung(
        ISBN, BEIDE, felder=(("neupreis", 20.0),))).strich() == ()


def test_ein_buch_das_in_iserv_fehlt_und_andere_felder():
    abweichung = Abweichung(ISBN, NUR_EXCEL, eintraege_fehlen=(("Deutsch", 5, True),))
    m = _markierung(_zeile(5, ab="2026/2027"), abweichung=abweichung)
    assert m.iserv == FEHLT and m.strich(ISERV) == (EINFUEHRUNG,)
    m = _markierung(_zeile(5), abweichung=Abweichung(ISBN, BEIDE, felder=(("titel", "X"),)))
    assert m.felder_anders and m.strich(ISERV) == ("aenderung",)


def test_nach_fach_fuer_eine_jahrgangsansicht():
    """Vorbereitet für Verlag und Jahrgang: andere Auswahl, andere Wertspalte."""
    stand = _stand(_zeile(7), _zeile(7, fach="Latein", ab="2026/2027"), _zeile(8))
    m = markierung(stand, stand.buecher[0], None, im=lambda e: e[1] == 7, nach=FACH)
    assert [(w.text, w.plan) for w in m.werte] == [("Deutsch", ""), ("Latein", EINFUEHRUNG)]
    # Ohne Auswahl und nach Jahrgang (Verlag): Jg. 7 aus zwei Fächern ist ein Wert.
    m = markierung(stand, stand.buecher[0], None, im=lambda e: True)
    assert [(w.text, w.plan) for w in m.werte] == [("7", EINFUEHRUNG), ("8", "")]


def test_ein_wert_ist_durchgestrichen_wenn_er_weg_ist_oder_nur_in_iserv_steht():
    assert Wert("5", weg=True).durch
    assert Wert("5", iserv=STEHT_NOCH).durch
    assert not Wert("5", plan=EINFUEHRUNG, iserv=STEHT_NOCH).durch


def test_ausmusterungen_zeigen_was_aus_den_regalen_geht():
    stand = _stand(_zeile(5, nach="2025/2026"), _zeile(6, nach="2025/2026"))
    assert in_ausmusterungen(stand, stand.buecher[0], "Deutsch")
    # Läuft ein leihbarer Jahrgang weiter, ist es keine Ausmusterung …
    stand = _stand(_zeile(5, nach="2025/2026"), _zeile(6))
    assert not in_ausmusterungen(stand, stand.buecher[0], "Deutsch")
    # … ein Kaufbuch-Jahrgang hält es nicht heraus (es steht dann in beiden Listen).
    stand = _stand(_zeile(7, nach="2025/2026"), _zeile(8, leihbar=False))
    assert in_ausmusterungen(stand, stand.buecher[0], "Deutsch")
    m = markierung(stand, stand.buecher[0], im=im_fach("Deutsch"))
    assert [[(w.text, w.durch) for w in t.werte] for t in m.teilzeilen] == [
        [("7", True)], [("8", False)]]


def test_keine_ausmusterung_ohne_leihbares_vor_zwei_jahren_oder_mit_neuer_einfuehrung():
    for zeilen in (
        (_zeile(5, nach="2025/2026", leihbar=False),),          # reines Kaufbuch
        (_zeile(5, nach="2024/2025"),),                         # schon voriges Jahr weg
        (_zeile(5, nach="2025/2026"), _zeile(6, ab="2027/2028")),  # kommt wieder
    ):
        stand = _stand(*zeilen)
        assert not in_ausmusterungen(stand, stand.buecher[0], "Deutsch"), zeilen


def test_ein_buch_das_ueberall_gleich_leihbar_ist_hat_eine_teilzeile():
    assert len(_markierung(_zeile(5), _zeile(6)).teilzeilen) == 1
