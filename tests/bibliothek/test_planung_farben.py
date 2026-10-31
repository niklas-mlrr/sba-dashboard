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
from buecherlisten.planung.vergleich import BEIDE, NUR_EXCEL, NUR_ISERV

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
    assert m.ganz == "" and m.strich() == () and m.strich_klassen == ()
    assert m.strich_stil() == "" and m.strich_teile is None and m.zeile == ""
    assert m.jahrgaenge == (5, 6) and m.leihbar and not m.leihbar_teilweise


def test_eine_einfuehrung_ist_blau_geschrieben_auch_eine_kuenftige():
    m = _markierung(_zeile(5), _zeile(6, ab="2026/2027"), _zeile(7, ab="2027/2028"))
    assert m.ganz == ""
    assert _werte(m) == [("5", "", "", False, ""),
                         ("6", "", EINFUEHRUNG, False, ""),
                         ("7", "ab 2027/2028", EINFUEHRUNG, False, "")]
    # Ein Abschnitt je farbigem Wert; ist er überall blau, ist der Strich blau.
    assert m.strich() == (EINFUEHRUNG, EINFUEHRUNG)
    assert m.strich_klassen == ("strich",) and m.strich_stil() == "var(--einfuehrung-strich)"
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
    # Je Teilzeile genau eine Farbe: der Strich teilt sich an ihrer Grenze.
    assert m.strich_teile == (AUSMUSTERUNG, EINFUEHRUNG)
    assert m.strich_stil() == (
        "linear-gradient(var(--ausmusterung-strich) 0 var(--teilung, 50%), "
        "var(--einfuehrung-strich) var(--teilung, 50%) 100%)")


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
    # rot markiert, ohne Planfarbe, nicht durchgestrichen. Latein gehört
    # nicht in diese Zeile.
    assert [(w.text, w.plan, w.durch, w.iserv) for w in leihbar.werte] == [
        ("7", AUSMUSTERUNG, True, STEHT_NOCH),
        ("8", EINFUEHRUNG, False, FEHLT),
        ("10", "", False, STEHT_NOCH)]
    assert [(w.text, w.iserv, w.markierung) for w in kauf.werte] == [("7", FEHLT, EINFUEHRUNG)]
    assert leihbar.werte[2].hinweis == "IServ-Bücherliste: als Leihbuch noch eingetragen"
    assert kauf.werte[0].hinweis == (
        "Planung: als Kaufbuch eingeführt zu 2026/2027"
        " · IServ-Bücherliste: als Kaufbuch noch nicht eingetragen")
    # Der Strich der Fach-Ansicht zeigt nur die Planung (je farbigem Wert, nach
    # Jahrgang, Jahr, rot vor blau), der einer IServ-Ansicht nur IServ.
    assert m.strich() == (AUSMUSTERUNG, EINFUEHRUNG, EINFUEHRUNG)
    assert m.strich_teile is None  # die Leihbuch-Teilzeile hat zwei Farben
    assert m.strich_stil() == (
        "linear-gradient(var(--ausmusterung-strich) 0% 33.333%, "
        "var(--einfuehrung-strich) 33.333% 66.667%, var(--einfuehrung-strich) 66.667% 100%)")
    assert m.strich(ISERV) == (AUSMUSTERUNG, EINFUEHRUNG)
    gelb = _markierung(_zeile(5), abweichung=Abweichung(ISBN, BEIDE, felder=(("neupreis", 20.0),)))
    assert gelb.strich() == () and gelb.strich_klassen == ("strich-gelb",)


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


def test_durchgestrichen_ist_nur_was_nach_dem_vorjahr_ausgemustert_ist():
    assert Wert("5", weg=True).durch
    assert not Wert("5", iserv=STEHT_NOCH).durch
    assert not Wert("5", plan=AUSMUSTERUNG).durch


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


def test_der_strich_folgt_jahrgang_jahr_und_rot_vor_blau():
    m = _markierung(_zeile(5, nach="2026/2027"), _zeile(6, ab="2026/2027"),
                    _zeile(7, nach="2027/2028"), _zeile(7, ab="2026/2027", leihbar=False),
                    _zeile(8, nach="2026/2027"), _zeile(8, ab="2026/2027", leihbar=False))
    # Jg. 7: die Einführung als Kaufbuch (2026) vor der Ausmusterung als Leihbuch
    # (2027); Jg. 8: beides 2026, rot vor blau.
    assert m.strich() == (AUSMUSTERUNG, EINFUEHRUNG, EINFUEHRUNG, AUSMUSTERUNG,
                          AUSMUSTERUNG, EINFUEHRUNG)
    assert m.strich_teile is None


def test_hat_nur_eine_teilzeile_eine_farbe_ist_der_strich_ganz_in_ihr():
    m = _markierung(_zeile(5), _zeile(6, ab="2026/2027", leihbar=False))
    assert m.strich_teile is None and m.strich_stil() == "var(--einfuehrung-strich)"


def test_der_hintergrund_zaehlt_nur_was_die_liste_zeigt():
    # Jg. 5 ist seit Jahren weg und steht nicht mehr da: alles Gezeigte ist neu.
    assert _markierung(_zeile(5, nach="2022/2023"), _zeile(6, ab="2026/2027")).ganz == EINFUEHRUNG
    # Gemischt: kein Hintergrund.
    assert _markierung(_zeile(5, nach="2026/2027"), _zeile(6, ab="2026/2027")).ganz == ""


def test_fehlt_der_jahrgang_an_der_buchreihe_ist_er_blau_markiert():
    abweichung = Abweichung(ISBN, BEIDE, buchreihe_fehlt=(6, 7, 8))
    m = _markierung(_zeile(5), _zeile(6), _zeile(7, ab="2027/2028"), _zeile(8, nach="2025/2026"),
                    abweichung=abweichung)
    # Nur was dieses Schuljahr gilt: Jg. 7 kommt erst, Jg. 8 ist weg.
    assert [(w.text, w.iserv) for w in m.werte] == [("5", ""), ("6", FEHLT), ("7", ""), ("8", "")]
    assert m.werte[1].hinweis == "IServ-Buchreihe: Jahrgang 6 noch nicht zugewiesen"
    # Fehlt er auch in der Bücherliste, nennt der Tooltip beides.
    m = _markierung(_zeile(6), abweichung=Abweichung(
        ISBN, BEIDE, buchreihe_fehlt=(6,), eintraege_fehlen=(("Deutsch", 6, True),)))
    assert m.werte[0].hinweis == ("IServ-Bücherliste: als Leihbuch noch nicht eingetragen"
                                  " · IServ-Buchreihe: Jahrgang 6 noch nicht zugewiesen")


def test_steht_die_isbn_nur_auf_einer_seite_ist_die_ganze_zeile_markiert():
    assert _markierung(_zeile(5), abweichung=Abweichung(ISBN, NUR_EXCEL)).zeile == EINFUEHRUNG
    assert _markierung(_zeile(5), abweichung=Abweichung(ISBN, NUR_ISERV)).zeile == AUSMUSTERUNG
    assert _markierung(_zeile(5), abweichung=Abweichung(ISBN, BEIDE)).zeile == ""


def test_einfuehrung_mit_ausmusterung_ist_blau_bis_iserv_den_jahrgang_fuehrt():
    """Entscheidung 2026-10-31: erst blau (noch einzutragen), dann rot (läuft aus)."""
    zeile = _zeile(6, ab="2026/2027", nach="2029/2030")
    # In IServ fehlt Jg. 6 noch in der Bücherliste …
    m = _markierung(zeile, abweichung=Abweichung(
        ISBN, BEIDE, eintraege_fehlen=(("Deutsch", 6, True),)))
    assert (m.werte[0].plan, m.werte[0].jahr) == (EINFUEHRUNG, 2026)
    assert m.werte[0].hinweis == (
        "Planung: als Leihbuch eingeführt zu 2026/2027 (bis 2029/2030)"
        " · IServ-Bücherliste: als Leihbuch noch nicht eingetragen")
    # … oder an der Buchreihe: blau.
    m = _markierung(zeile, abweichung=Abweichung(ISBN, BEIDE, buchreihe_fehlt=(6,)))
    assert m.werte[0].plan == EINFUEHRUNG
    # Führt IServ ihn, ist er rot.
    m = _markierung(zeile, abweichung=Abweichung(ISBN, BEIDE))
    assert (m.werte[0].plan, m.werte[0].jahr, m.ganz) == (AUSMUSTERUNG, 2029, AUSMUSTERUNG)
    # Einjährig im laufenden Schuljahr: genauso.
    m = _markierung(_zeile(6, ab="2026/2027", nach="2026/2027"), abweichung=Abweichung(ISBN, BEIDE))
    assert m.werte[0].plan == AUSMUSTERUNG


def test_eine_spaetere_einfuehrung_mit_ausmusterung_bleibt_blau():
    """Sie wird noch nicht mit IServ verglichen."""
    m = _markierung(_zeile(5), _zeile(7, ab="2027/2028", nach="2027/2028"),
                    _zeile(8, ab="2027/2028", nach="2030/2031"), abweichung=Abweichung(ISBN, BEIDE))
    assert [(w.text, w.plan, w.iserv) for w in m.werte] == [
        ("5", "", ""), ("7", EINFUEHRUNG, ""), ("8", EINFUEHRUNG, "")]
    assert m.werte[1].hinweis == "Planung: als Leihbuch eingeführt nur für 2027/2028"
    assert m.werte[2].hinweis == "Planung: als Leihbuch eingeführt ab 2027/2028"
