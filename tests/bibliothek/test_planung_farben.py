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
    assert m.strich_stil() == "" and m.zeile == ""
    assert m.jahrgaenge == (5, 6) and m.leihbar and not m.leihbar_teilweise


def test_eine_einfuehrung_ist_blau_geschrieben_auch_eine_kuenftige():
    m = _markierung(_zeile(5), _zeile(6, ab="2026/2027"), _zeile(7, ab="2027/2028"))
    assert m.ganz == ""
    assert _werte(m) == [("5", "", "", False, ""),
                         ("6", "ab 2026/2027", EINFUEHRUNG, False, ""),
                         ("7", "ab 2027/2028", EINFUEHRUNG, False, "")]
    # Ein Abschnitt je vorkommender Farbe; ist sie überall blau, ist der Strich blau.
    assert m.strich() == (EINFUEHRUNG,)
    assert m.strich_klassen == ("strich",) and m.strich_stil() == "var(--einfuehrung-strich)"
    assert m.werte[1].hinweis == "Einführung der Buchreihe in Jahrgang 6 beantragt"
    assert m.werte[2].hinweis == "Einführung der Buchreihe in Jahrgang 7 für 2027/2028 beantragt"


def test_ein_ganz_neues_buch_hinterlegt_die_zeile():
    m = _markierung(_zeile(7, ab="2027/2028"), _zeile(8, ab="2028/2029"))
    assert m.ganz == EINFUEHRUNG
    # Läuft es in einem anderen Fach schon, ist es nicht ganz neu.
    assert _markierung(_zeile(7, ab="2027/2028"), _zeile(5, fach="Latein")).ganz == ""


def test_eine_ausmusterung_nach_dem_vorjahr_ist_rot_und_durchgestrichen():
    m = _markierung(_zeile(5, nach="2025/2026"), _zeile(6))
    # Der Antrag ist noch offen: das Jahr steht da, mit Kasten.
    assert _werte(m) == [("5", "bis 2025/2026", AUSMUSTERUNG, True, ""),
                         ("6", "", "", False, "")]
    assert m.werte[0].hinweis == "Ausmusterung der Buchreihe in Jahrgang 5 beantragt"
    # Was früher endete, steht nicht mehr in der Spalte.
    m = _markierung(_zeile(5, nach="2024/2025"), _zeile(6))
    assert _werte(m) == [("6", "", "", False, "")] and m.strich() == ()


def test_ein_auslaufender_jahrgang_ist_rot_aber_nicht_durchgestrichen():
    m = _markierung(_zeile(5), _zeile(6, nach="2026/2027"))
    assert _werte(m)[1] == ("6", "bis 2026/2027", AUSMUSTERUNG, False, "")
    assert m.werte[1].hinweis == "Ausmusterung der Buchreihe in Jahrgang 6 nach 2026/2027 beantragt"


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
    # Rot kommt beim Lesen zuerst, blau danach: zwei gleich hohe Abschnitte.
    assert m.strich() == (AUSMUSTERUNG, EINFUEHRUNG)
    assert m.strich_stil() == (
        "linear-gradient(var(--ausmusterung-strich) 0% 50%, "
        "var(--einfuehrung-strich) 50% 100%)")


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
    # Die Teilzeile mit den kleineren Jahrgängen steht oben: das Kaufbuch (Jg. 7)
    # vor dem Leihbuch (Jg. 7, 8, 10).
    kauf, leihbar = m.teilzeilen
    # Jg. 10 kennt die Datei nicht: er steht nur da, weil IServ ihn führt -
    # rot markiert, ohne Planfarbe, nicht durchgestrichen. Latein gehört
    # nicht in diese Zeile.
    assert [(w.text, w.plan, w.durch, w.iserv) for w in leihbar.werte] == [
        ("7", AUSMUSTERUNG, True, STEHT_NOCH),
        ("8", EINFUEHRUNG, False, FEHLT),
        ("10", "", False, STEHT_NOCH)]
    assert [(w.text, w.iserv, w.markierung) for w in kauf.werte] == [("7", FEHLT, EINFUEHRUNG)]
    assert leihbar.werte[2].hinweis == \
        "Buchreihe ist aus Bücherliste für Jahrgang 10 in IServ zu entfernen"
    # Jg. 7 ist leihbar rot und als Kaufbuch blau markiert: in IServ ist nur
    # „leihbar“ umzustellen, in beiden Teilzeilen (Entscheidung 2026-11-04).
    assert kauf.werte[0].hinweis == (
        "Einführung der Buchreihe in Jahrgang 7 beantragt\n"
        "Buchreihe ist in Bücherliste für Jahrgang 7 auf nicht leihbar zu setzen")
    assert leihbar.werte[0].hinweis == (
        "Ausmusterung der Buchreihe in Jahrgang 7 beantragt\n"
        "Buchreihe ist in Bücherliste für Jahrgang 7 auf nicht leihbar zu setzen")
    assert leihbar.werte[1].hinweis == (
        "Einführung der Buchreihe in Jahrgang 8 beantragt\n"
        "Buchreihe ist Bücherliste für Jahrgang 8 hinzuzufügen")
    # Der Strich der Fach-Ansicht zeigt nur die Planung (je vorkommender Farbe
    # ein Abschnitt, in Lesefolge: erst das Kaufbuch, blau), der einer
    # IServ-Ansicht nur IServ.
    assert m.strich() == (EINFUEHRUNG, AUSMUSTERUNG)
    assert m.strich_stil() == (
        "linear-gradient(var(--einfuehrung-strich) 0% 50%, "
        "var(--ausmusterung-strich) 50% 100%)")
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


def test_leihbuch_nach_dem_vorjahr_weg_kaufbuch_laeuft_weiter_zwei_teilzeilen():
    """Ausgemustert nach dem Vorjahr ist durchgestrichen, das laufende Kaufbuch nicht."""
    stand = _stand(_zeile(7, nach="2025/2026"), _zeile(8, leihbar=False))
    m = markierung(stand, stand.buecher[0], im=im_fach("Deutsch"))
    assert [[(w.text, w.durch) for w in t.werte] for t in m.teilzeilen] == [
        [("7", True)], [("8", False)]]


def test_ein_buch_das_ueberall_gleich_leihbar_ist_hat_eine_teilzeile():
    assert len(_markierung(_zeile(5), _zeile(6)).teilzeilen) == 1


def test_der_strich_hat_je_farbe_einen_abschnitt_in_der_reihenfolge_des_lesens():
    # Gelesen wird Teilzeile für Teilzeile (leihbar zuerst), Jahrgang für Jahrgang.
    m = _markierung(_zeile(5, ab="2026/2027"), _zeile(6, nach="2026/2027"),
                    _zeile(7, ab="2026/2027"), _zeile(7, nach="2025/2026", leihbar=False))
    assert m.strich() == (EINFUEHRUNG, AUSMUSTERUNG)
    assert m.strich_stil() == (
        "linear-gradient(var(--einfuehrung-strich) 0% 50%, var(--ausmusterung-strich) 50% 100%)")
    m = _markierung(_zeile(5, nach="2026/2027"), _zeile(6, ab="2026/2027"),
                    _zeile(7, nach="2026/2027"))
    assert m.strich() == (AUSMUSTERUNG, EINFUEHRUNG)


def test_hat_nur_eine_farbe_ist_der_strich_ganz_in_ihr():
    m = _markierung(_zeile(5), _zeile(6, ab="2026/2027", leihbar=False))
    assert m.strich_stil() == "var(--einfuehrung-strich)"


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
    assert m.werte[1].hinweis == "Jahrgang 6 ist der Buchreihe hinzuzufügen"
    # Nur der Strich oben (Buchreihe), die Bücherliste führt ihn.
    assert (m.werte[1].reihe_fehlt, m.werte[1].liste_fehlt, m.werte[1].striche) \
        == (True, False, "oben")
    # Fehlt er auch in der Bücherliste, nennt der Tooltip beides, und es gibt
    # beide Striche.
    m = _markierung(_zeile(6), abweichung=Abweichung(
        ISBN, BEIDE, buchreihe_fehlt=(6,), eintraege_fehlen=(("Deutsch", 6, True),)))
    assert m.werte[0].hinweis == ("Jahrgang 6 ist der Buchreihe hinzuzufügen\n"
                                  "Buchreihe ist Bücherliste für Jahrgang 6 hinzuzufügen")
    assert m.werte[0].striche == "oben-unten"
    # Nur in der Bücherliste: der gewöhnliche Strich unten.
    m = _markierung(_zeile(6), abweichung=Abweichung(
        ISBN, BEIDE, eintraege_fehlen=(("Deutsch", 6, True),)))
    assert (m.werte[0].markierung, m.werte[0].striche) == (EINFUEHRUNG, "")


def test_steht_die_isbn_nur_auf_einer_seite_ist_die_ganze_zeile_markiert():
    assert _markierung(_zeile(5), abweichung=Abweichung(ISBN, NUR_EXCEL)).zeile == EINFUEHRUNG
    assert _markierung(_zeile(5), abweichung=Abweichung(ISBN, NUR_ISERV)).zeile == AUSMUSTERUNG
    assert _markierung(_zeile(5), abweichung=Abweichung(ISBN, BEIDE)).zeile == ""


def test_ganz_blau_nur_wenn_die_buchreihe_im_inventar_fehlt():
    """Entscheidung 2026-11-04 (Variante B): fehlt die Buchreihe im Inventar,
    ist die Zeile ganz blau und jeder Jahrgang hat beide Striche; gibt es sie,
    markieren nur die Jahrgänge, was in IServ fehlt."""
    fehlen = (("Deutsch", 5, True), ("Deutsch", 6, True))
    m = _markierung(_zeile(5), _zeile(6), abweichung=Abweichung(
        ISBN, NUR_EXCEL, eintraege_fehlen=fehlen, buchreihe_fehlt=(5, 6),
        buchreihe_angelegt=False))
    assert m.zeile == EINFUEHRUNG
    assert [w.striche for w in m.werte] == ["oben-unten", "oben-unten"]
    assert m.werte[0].hinweis == ("Buchreihe muss in IServ angelegt werden\n"
                                  "Jahrgang 5 ist der Buchreihe hinzuzufügen\n"
                                  "Buchreihe ist Bücherliste für Jahrgang 5 hinzuzufügen")
    # Die Buchreihe gibt es schon, Jg. 6 ist ihr zugewiesen.
    m = _markierung(_zeile(5), _zeile(6), abweichung=Abweichung(
        ISBN, NUR_EXCEL, eintraege_fehlen=fehlen, buchreihe_fehlt=(5,),
        buchreihe_angelegt=True))
    assert m.zeile == ""
    assert [(w.markierung, w.striche) for w in m.werte] == [
        (EINFUEHRUNG, "oben-unten"), (EINFUEHRUNG, "")]
    assert m.werte[1].hinweis == "Buchreihe ist Bücherliste für Jahrgang 6 hinzuzufügen"


def test_einfuehrung_mit_ausmusterung_ist_blau_bis_iserv_den_jahrgang_fuehrt():
    """Entscheidung 2026-10-31: erst blau (noch einzutragen), dann rot (läuft aus)."""
    zeile = _zeile(6, ab="2026/2027", nach="2029/2030")
    # In IServ fehlt Jg. 6 noch in der Bücherliste …
    m = _markierung(zeile, abweichung=Abweichung(
        ISBN, BEIDE, eintraege_fehlen=(("Deutsch", 6, True),)))
    assert (m.werte[0].plan, m.werte[0].jahr) == (EINFUEHRUNG, 2026)
    assert m.werte[0].hinweis == (
        "Einführung der Buchreihe in Jahrgang 6 beantragt\n"
        "Buchreihe ist Bücherliste für Jahrgang 6 hinzuzufügen")
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
    assert m.werte[1].hinweis == "Einführung der Buchreihe in Jahrgang 7 für 2027/2028 beantragt"
    assert m.werte[2].hinweis == "Einführung der Buchreihe in Jahrgang 8 für 2027/2028 beantragt"


# ── Wiedereinführung, abgelehnte Anträge, Grau (Entscheidung 2026-10-31) ─────


def test_nach_dem_vorjahr_ausgemustert_und_spaeter_wieder_eingefuehrt():
    """Rot und durchgestrichen, solange IServ den Jahrgang noch führt; danach blau."""
    zeilen = (_zeile(5, nach="2025/2026"), _zeile(5, ab="2028/2029"), _zeile(6))
    noch = Abweichung(ISBN, BEIDE, eintraege_nur_iserv=(("Deutsch", 5, True),))
    m = _markierung(*zeilen, abweichung=noch)
    assert [(w.text, w.plan, w.durch) for w in m.werte] == [
        ("5", AUSMUSTERUNG, True), ("6", "", False)]
    assert m.werte[0].zusatz == "bis 2025/2026, ab 2028/2029" and m.werte[0].iserv == STEHT_NOCH
    # In IServ ist er weg: die Wiedereinführung ist das Nächste, blau, nicht durchgestrichen.
    m = _markierung(*zeilen, abweichung=Abweichung(ISBN, BEIDE))
    assert [(w.text, w.plan, w.durch) for w in m.werte] == [
        ("5", EINFUEHRUNG, False), ("6", "", False)]
    # Ohne Wiedereinführung bleibt er rot und durchgestrichen, auch ohne IServ.
    m = _markierung(_zeile(5, nach="2025/2026"), _zeile(6), abweichung=Abweichung(ISBN, BEIDE))
    assert [(w.text, w.plan, w.durch) for w in m.werte] == [
        ("5", AUSMUSTERUNG, True), ("6", "", False)]


def test_mehrere_zeilen_im_eintrag_haben_je_ein_ergebnis_im_zusatz():
    m = _markierung(_zeile(5, ab="2020/2021", nach="2026/2027"), _zeile(5, ab="2029/2030"))
    assert m.werte[0].zusatz == "bis 2026/2027, ab 2029/2030"
    # Das nächste Ereignis ist die Ausmusterung: rot.
    assert m.werte[0].plan == AUSMUSTERUNG
    # Im Folgejahr endete die erste Zeile mit dem Vorjahr; IServ führt den Jahrgang nicht mehr.
    stand = _stand(_zeile(5, ab="2020/2021", nach="2026/2027"), _zeile(5, ab="2029/2030"))
    from dataclasses import replace
    spaeter = replace(stand, schuljahr="2027/2028", vorjahr="2026/2027")
    m = markierung(spaeter, spaeter.buecher[0], Abweichung(ISBN, BEIDE), im=im_fach("Deutsch"))
    assert m.werte[0].zusatz == "bis 2026/2027, ab 2029/2030" and m.werte[0].plan == EINFUEHRUNG


def _abgelehnt(zeile: Planungszeile, *, einfuehrung: bool = False, ausmusterung: bool = False,
               ) -> Planungszeile:
    from dataclasses import replace

    from buecherlisten.planung import Antragsentscheidung
    abgelehnt = Antragsentscheidung(ergebnis="abgelehnt")
    return replace(zeile,
                   antrag_einfuehrung=abgelehnt if einfuehrung else zeile.antrag_einfuehrung,
                   antrag_ausmusterung=abgelehnt if ausmusterung else zeile.antrag_ausmusterung)


def test_eine_abgelehnte_einfuehrung_zaehlt_nicht_die_jahreszahl_bleibt_grau():
    m = _markierung(_zeile(5), _zeile(6),
                    _abgelehnt(_zeile(7, ab="2027/2028"), einfuehrung=True))
    wert = m.werte[2]
    # Keine Farbe, nicht verglichen, der Zusatz bleibt (mit dem Kasten „abgelehnt“).
    assert (wert.plan, wert.iserv, wert.grau, wert.zusatz) == ("", "", True, "ab 2027/2028")
    assert wert.zusaetze[0].teile[1].antrag == "abgelehnt"
    assert wert.lesefarben == ("grau",)
    # Der Strich zeigt das Grau, an Stelle des Vorkommens in Lesefolge.
    assert m.strich() == ("grau",)
    assert m.strich_stil() == "var(--grau-strich)"


def test_hinge_das_buch_nur_an_abgelehnten_einfuehrungen_ist_die_zeile_grau():
    m = _markierung(_abgelehnt(_zeile(7, ab="2027/2028"), einfuehrung=True),
                    _abgelehnt(_zeile(8, ab="2027/2028"), einfuehrung=True))
    assert [w.grau for w in m.werte] == [True, True] and m.ganz == "grau"
    assert m.werte[0].hinweis.startswith("Einführung der Buchreihe in Jahrgang 7 für 2027/2028 abgelehnt")
    # Läuft es anderswo oder in einem anderen Jahrgang, gibt es das Buch: nicht grau.
    m = _markierung(_abgelehnt(_zeile(7, ab="2027/2028"), einfuehrung=True), _zeile(5))
    assert m.ganz == ""
    # Eine abgelehnte Einführung zum laufenden Schuljahr: nicht in IServ erwartet (keine
    # blaue Markierung), und steht der Jahrgang dort schon, ist er rot markiert.
    alt = _abgelehnt(_zeile(7, ab="2026/2027"), einfuehrung=True)
    fehlt = Abweichung(ISBN, BEIDE, eintraege_fehlen=(("Deutsch", 7, True),))
    assert _markierung(alt, abweichung=fehlt).werte[0].iserv == ""
    steht = Abweichung(ISBN, BEIDE)
    assert _markierung(alt, abweichung=steht).werte[0].iserv == STEHT_NOCH


def test_eine_abgelehnte_ausmusterung_laesst_das_buch_bleiben_ohne_grauen_hintergrund():
    from buecherlisten.planung.farben import ohne_abgelehnte_ausmusterungen
    stand = _stand(_abgelehnt(_zeile(5, nach="2025/2026"), ausmusterung=True), _zeile(6))
    wirksam = ohne_abgelehnte_ausmusterungen(stand)
    assert [z.ausgemustert_nach for z in wirksam.planung] == ["", ""]
    assert [z.ausgemustert_nach for z in stand.planung] == ["2025/2026", ""]
    m = markierung(wirksam, wirksam.buecher[0], Abweichung(ISBN, BEIDE), im=im_fach("Deutsch"),
                   original=stand)
    # Jahrgang 5 gilt weiter; der Zusatz zeigt die abgelehnte Ausmusterung nicht (keine Regel).
    assert [(w.text, w.plan, w.durch, w.grau) for w in m.werte] == [
        ("5", "", False, False), ("6", "", False, False)]
    assert m.ganz == ""
    # Ohne Ablehnung bleibt der Stand derselbe Objekt.
    assert ohne_abgelehnte_ausmusterungen(_stand(_zeile(5))) is not None


def test_die_teilzeilen_stehen_geordnet_nach_ihren_jahrgaengen():
    """Wie die Fach-Ansicht beim Laden sortiert ist: der kleinste Jahrgang zuerst,
    bei Gleichstand der zweitkleinste, ohne zweiten vor einem zweiten; bei völliger
    Gleichheit leihbar vor Kaufbuch."""
    # Das Kaufbuch hat den kleineren Jahrgang: es steht oben.
    m = _markierung(_zeile(7), _zeile(8), _zeile(5, leihbar=False))
    assert [(t.leihbar, t.jahrgaenge) for t in m.teilzeilen] == [(False, (5,)), (True, (7, 8))]
    # Gleicher kleinster Jahrgang: wer keinen zweiten hat, steht davor.
    m = _markierung(_zeile(5), _zeile(6), _zeile(5, leihbar=False))
    assert [(t.leihbar, t.jahrgaenge) for t in m.teilzeilen] == [(False, (5,)), (True, (5, 6))]
    # Gleich: leihbar zuerst.
    m = _markierung(_zeile(5), _zeile(5, leihbar=False))
    assert [t.leihbar for t in m.teilzeilen] == [True, False]
    # Der Strich folgt der Reihenfolge, in der gelesen wird.
    m = _markierung(_zeile(7, nach="2026/2027"), _zeile(5, ab="2027/2028", leihbar=False))
    assert m.strich() == (EINFUEHRUNG, AUSMUSTERUNG)


# ── Tooltips am Jahrgang (Entscheidung 2026-11-04) ───────────────────────────


def _entschieden(zeile: Planungszeile, *, einfuehrung: str = "", ausmusterung: str = "",
                 ) -> Planungszeile:
    from dataclasses import replace
    from datetime import date

    from buecherlisten.planung import Antragsentscheidung

    def antrag(ergebnis: str) -> Antragsentscheidung:
        return Antragsentscheidung(ergebnis, "b.lehrer", date(2026, 10, 12)) if ergebnis \
            else Antragsentscheidung()
    return replace(zeile, antrag_einfuehrung=antrag(einfuehrung),
                   antrag_ausmusterung=antrag(ausmusterung))


def test_ein_genehmigter_antrag_steht_ohne_beantragt_im_tooltip():
    m = _markierung(_entschieden(_zeile(5, nach="2025/2026"), ausmusterung="genehmigt"),
                    _entschieden(_zeile(6, ab="2026/2027"), einfuehrung="genehmigt"),
                    _entschieden(_zeile(7, ab="2027/2028"), einfuehrung="genehmigt"),
                    _entschieden(_zeile(8, nach="2027/2028"), ausmusterung="genehmigt"))
    assert [w.hinweis for w in m.werte] == [
        "Ausmusterung der Buchreihe in Jahrgang 5",
        "Einführung der Buchreihe in Jahrgang 6",
        "Einführung der Buchreihe in Jahrgang 7 für 2027/2028",
        "Ausmusterung der Buchreihe in Jahrgang 8 nach 2027/2028"]


def test_grau_nennt_die_abgelehnte_einfuehrung_mit_datum_und_signatur():
    """„für ESJ“ nur, wenn die Einführung nach dem ausgewählten Schuljahr liegt."""
    m = _markierung(_entschieden(_zeile(7, ab="2027/2028"), einfuehrung="abgelehnt"),
                    _entschieden(_zeile(8, ab="2026/2027"), einfuehrung="abgelehnt"))
    assert [w.grau for w in m.werte] == [True, True]
    assert [w.hinweis for w in m.werte] == [
        "Einführung der Buchreihe in Jahrgang 7 für 2027/2028 abgelehnt\n"
        "am 12.10.2026\ndurch b.lehrer",
        "Einführung der Buchreihe in Jahrgang 8 abgelehnt\nam 12.10.2026\ndurch b.lehrer"]
