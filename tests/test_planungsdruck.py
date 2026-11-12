"""Die Fach-PDF aus der Planungsdatei (Vorgabe vom 2026-11-10): app/planungsdruck.py.

Ein Fach, Chemie, im Schuljahr 2026/2027, mit je einem Buch für jeden Fall:
genehmigt und laufend, beantragt, abgelehnt, ausgemustert, später eingeführt.
"""
from __future__ import annotations

import io
from datetime import date

import pytest
from reportlab.lib.enums import TA_RIGHT
from reportlab.pdfbase.pdfmetrics import stringWidth

from app.planungsdruck import NBSP, Antragsdetails, fach_tabellen
from buecherlisten.core.daten import Buecherdaten
from buecherlisten.core.erzeugen import Zuordnungen, erzeuge_buecherlisten_pdfs
from buecherlisten.core.layout import (
    CONTENT_WIDTH,
    EINZUG,
    FACH_LISTE,
    STIL_DURCH,
    STIL_GRAU,
    _wrap_lines,
    _zelle,
    render_table,
)
from buecherlisten.planung import Antragsentscheidung, Buch, Buchplanung, Planungszeile, Ruecklage

SJ = "2026/2027"
GENEHMIGT = Antragsentscheidung("genehmigt")
# Gültige ISBNs, sonst meldet isbnlib beim Formatieren jede als Fehler.
A, B, C, D, E, F, G, H, P = ("9783060000005", "9783121000562", "9783120000013",
                             "9783140000000", "9783127563313", "9783661670003",
                             "9783661310510", "9783120066088", "9783661211015")
ABGELEHNT = Antragsentscheidung("abgelehnt")


def _buch(isbn: str, titel: str, *jahrgaenge: int) -> Buch:
    return Buch(isbn=isbn, titel=titel, verlag="Klett", neupreis=20.0, leihgebuehr=4.0,
                kombinationen=tuple(("Chemie", j) for j in jahrgaenge))


def _zeile(isbn: str, jahrgang: int, **werte) -> Planungszeile:
    return Planungszeile(isbn=isbn, fach="Chemie", jahrgang=jahrgang,
                         leihbar=werte.pop("leihbar", True), **werte)


@pytest.fixture()
def planung() -> Buchplanung:
    return Buchplanung(
        schuljahr=SJ,
        buecher=(
            _buch(A, "Laufend", 5, 6),
            _buch(B, "Neu beantragt"),
            _buch(C, "Neu abgelehnt"),
            _buch(D, "Ausmusterung offen", 10),
            _buch(E, "Ausmusterung abgelehnt", 10),
            _buch(F, "Ausgemustert", 11),
            _buch(G, "Später genehmigt"),
            _buch(H, "Kaufbuch", 5),
            Buch(isbn=P, titel="Physikbuch", verlag="Klett", kombinationen=(("Physik", 7),)),
        ),
        planung=(
            _zeile(A, 5), _zeile(A, 6),
            _zeile(A, 7, eingefuehrt_ab=SJ),
            _zeile(B, 8, eingefuehrt_ab="2027/2028"),
            _zeile(C, 9, eingefuehrt_ab=SJ, antrag_einfuehrung=ABGELEHNT),
            _zeile(D, 10, ausgemustert_nach="2025/2026"),
            _zeile(E, 10, ausgemustert_nach="2025/2026", antrag_ausmusterung=ABGELEHNT),
            _zeile(F, 11, ausgemustert_nach="2025/2026", antrag_ausmusterung=GENEHMIGT),
            _zeile(G, 5, eingefuehrt_ab="2027/2028", antrag_einfuehrung=GENEHMIGT),
            _zeile(H, 5, leihbar=False),
        ),
    )


def _je_titel(zeilen: list[dict]) -> dict[str, dict]:
    return {zeile["titel"]: zeile for zeile in zeilen}


def test_ohne_antraege_nur_was_genehmigt_ist_und_dieses_jahr_gilt(planung):
    tabellen = fach_tabellen(planung, antraege=False)
    assert list(tabellen) == ["Chemie", "Physik"]
    leih = _je_titel(tabellen["Chemie"]["leih"])
    # Offene Ausmusterung nach dem Vorjahr: läuft noch; abgelehnte: bleibt.
    assert set(leih) == {"Laufend", "Ausmusterung offen", "Ausmusterung abgelehnt"}
    assert leih["Laufend"]["klasse"] == "5, 6"
    assert "klasse_teile" not in leih["Laufend"] and not leih["Laufend"].get("stil")
    assert [z["titel"] for z in tabellen["Chemie"]["kauf"]] == ["Kaufbuch"]
    assert leih["Laufend"]["neupreis"] == "20,00 €" and leih["Laufend"]["verlag"] == "Klett"


def test_mit_antraegen_alle_daten_samt_jahreszahlen(planung):
    leih = _je_titel(fach_tabellen(planung, antraege=True)["Chemie"]["leih"])
    # Die genehmigte Ausmusterung nach dem Vorjahr steht nicht mehr da.
    assert "Ausgemustert" not in leih
    assert leih["Laufend"]["klasse"] == f"5, 6,\n7{NBSP}({EINZUG}ab{NBSP}2026/2027)"
    assert leih["Später genehmigt"]["klasse"] == f"5{NBSP}({EINZUG}ab{NBSP}2027/2028)"
    assert leih["Ausmusterung offen"]["klasse"] == f"10{NBSP}({EINZUG}bis{NBSP}2025/2026)"
    # Der Jahrgang steht nur wegen der offenen Einführung da: ganz grau.
    assert ("7", (STIL_GRAU,)) in leih["Laufend"]["klasse_teile"]
    assert (f"ab{NBSP}2026/2027", (STIL_GRAU,)) in leih["Laufend"]["klasse_teile"]
    assert ("5", ()) in leih["Laufend"]["klasse_teile"] and leih["Laufend"]["stil"] == ""
    # Genehmigt: kein Stil, auch für die Jahreszahl.
    assert all(not stile for _, stile in leih["Später genehmigt"]["klasse_teile"])


def test_offen_ist_grau_und_abgelehnt_durchgestrichen(planung):
    leih = _je_titel(fach_tabellen(planung, antraege=True)["Chemie"]["leih"])
    # Nur die Jahreszahl samt Präfix - der Jahrgang läuft.
    offen = leih["Ausmusterung offen"]
    assert offen["stil"] == "" and ("10", ()) in offen["klasse_teile"]
    assert (f"bis{NBSP}2025/2026", (STIL_GRAU,)) in offen["klasse_teile"]
    abgelehnt = leih["Ausmusterung abgelehnt"]
    assert abgelehnt["stil"] == ""
    assert (f"bis{NBSP}2025/2026", (STIL_DURCH,)) in abgelehnt["klasse_teile"]


def test_neues_buch_beantragt_ist_ganz_grau_abgelehnt_ganz_durchgestrichen(planung):
    leih = _je_titel(fach_tabellen(planung, antraege=True)["Chemie"]["leih"])
    assert leih["Neu beantragt"]["stil"] == STIL_GRAU
    assert leih["Neu abgelehnt"]["stil"] == STIL_DURCH
    assert leih["Neu abgelehnt"]["klasse"] == f"9{NBSP}({EINZUG}ab{NBSP}2026/2027)"


def test_von_bis_bricht_nur_vor_bis():
    planung = Buchplanung(schuljahr=SJ, buecher=(_buch(A, "Kurz"),), planung=(
        _zeile(A, 7, eingefuehrt_ab="2027/2028", ausgemustert_nach="2028/2029"),))
    (zeile,) = fach_tabellen(planung, antraege=True)["Chemie"]["leih"]
    assert zeile["klasse"] == f"7{NBSP}({EINZUG}von{NBSP}2027/2028 bis{NBSP}2028/2029)"
    assert _wrap_lines(zeile["klasse"], 1.0) == [f"7{NBSP}(von{NBSP}2027/2028",
                                                 f"bis{NBSP}2028/2029)"]


def test_zellen_tragen_den_stil(planung):
    leih = _je_titel(fach_tabellen(planung, antraege=True)["Chemie"]["leih"])
    klasse, titel, isbn = FACH_LISTE.spalten[0], FACH_LISTE.spalten[1], \
        FACH_LISTE.spalten[3]
    grau = _zelle(leih["Neu beantragt"], titel)
    assert 'color="#8c8c8c"' in grau.text and "Neu beantragt" in grau.text
    durch = _zelle(leih["Neu abgelehnt"], isbn)
    assert "<strike>" in durch.text
    (absatz,) = _zelle(leih["Ausmusterung abgelehnt"], klasse)
    assert "<strike>" in absatz.text and EINZUG not in absatz.text
    assert isinstance(_zelle(leih["Laufend"], isbn), str)


def test_pdf_mit_antragsinformationen(planung):
    from pypdf import PdfReader

    daten = Buecherdaten(SJ, "Schuljahr 26/27", fach_tabellen(planung, antraege=True))
    (pdf,) = erzeuge_buecherlisten_pdfs(daten, antraege=True, zuordnungen=Zuordnungen(
        fkl={}, kollegium={}, aufgabenfeld={}))
    text = "".join(seite.extract_text() for seite in PdfReader(io.BytesIO(pdf.inhalt)).pages)
    assert "Neu abgelehnt" in text and "2027/2028" in text
    assert "Planungsbücherliste" in text


def test_antraege_nur_fuer_faecher_ohne_iserv_stand(planung):
    daten = Buecherdaten(SJ, "Schuljahr 26/27", {}, listen_ids={"Jahrgang 5": 1})
    with pytest.raises(ValueError):
        erzeuge_buecherlisten_pdfs(daten, antraege=True, iserv_stand=True)


def test_klasse_bricht_um_wenn_es_zeilen_spart(planung):
    zeilen = fach_tabellen(planung, antraege=True)["Chemie"]["leih"]
    lang = {**zeilen[0], "klasse": ", ".join([f"{j}{NBSP}(ab{NBSP}2027/2028)" for j in range(5, 11)])}
    lang.pop("klasse_teile")
    tabelle = render_table([lang], with_fee=True, spalten=FACH_LISTE.spalten)
    einzeilig = stringWidth(lang["klasse"], "Helvetica", 10)
    assert tabelle._colWidths[0] < einzeilig * 0.6
    # Die Tabelle bleibt in der Breite des Satzspiegels.
    assert sum(tabelle._colWidths) == pytest.approx(CONTENT_WIDTH)


def test_ein_nur_beantragtes_fach_hat_ohne_antraege_leere_tabellen():
    """Die Fächer sind die des Druckmenüs ohne IServ-Stand - mit und ohne Anträge gleich."""
    planung = Buchplanung(schuljahr=SJ, buecher=(_buch(A, "Neu"),), planung=(
        _zeile(A, 7, eingefuehrt_ab="2027/2028"),))
    assert fach_tabellen(planung, antraege=False) == {
        "Chemie": {"leih": [], "kauf": [], "ausgemustert": []}}
    assert len(fach_tabellen(planung, antraege=True)["Chemie"]["leih"]) == 1


def test_jahrgang_mit_jahreszusatz_steht_allein_in_seinen_zeilen():
    """Vorgabe vom 2026-11-10: vor und hinter ihm wird umbrochen, das Komma bleibt hinten."""
    planung = Buchplanung(schuljahr=SJ, buecher=(_buch(A, "Gemischt", 5, 6, 8, 9),), planung=(
        _zeile(A, 5), _zeile(A, 6),
        _zeile(A, 7, eingefuehrt_ab="2027/2028", ausgemustert_nach="2028/2029"),
        _zeile(A, 8), _zeile(A, 9)))
    (zeile,) = fach_tabellen(planung, antraege=True)["Chemie"]["leih"]
    assert zeile["klasse"] == f"5, 6,\n7{NBSP}({EINZUG}von{NBSP}2027/2028 bis{NBSP}2028/2029),\n8, 9"
    # Auch bei viel Platz drei Zeilen; wird es eng, bricht nur der Zusatz weiter um.
    assert _wrap_lines(zeile["klasse"], 500.0) == [
        "5, 6,", f"7{NBSP}(von{NBSP}2027/2028 bis{NBSP}2028/2029),", "8, 9"]
    assert _wrap_lines(zeile["klasse"], 1.0) == [
        "5,", "6,", f"7{NBSP}(von{NBSP}2027/2028", f"bis{NBSP}2028/2029),", "8,", "9"]
    # Je Zeile ein Absatz; der mit Zusatz hängt hinter „7 (“: sein Umbruch
    # beginnt bündig unter „von“ (Vorgabe vom 2026-11-10).
    erste, zusatz, letzte = _zelle(zeile, FACH_LISTE.spalten[0])
    assert (erste.text, letzte.text) == ("5, 6,", "8, 9")
    einzug = stringWidth(f"7{NBSP}(", "Helvetica", 10)
    assert zusatz.style.leftIndent == pytest.approx(einzug)
    assert zusatz.style.firstLineIndent == pytest.approx(-einzug)
    assert erste.style.leftIndent == 0
    # Gemessen wird wie gesetzt: die Folgezeile ist um den Kopf eingerückt.
    breite = stringWidth(f"7{NBSP}(von{NBSP}2027/2028", "Helvetica", 10) + 1
    assert _wrap_lines(zeile["klasse"], breite)[1:3] == [
        f"7{NBSP}(von{NBSP}2027/2028", f"bis{NBSP}2028/2029),"]
    zusatz.wrap(breite, 1000.0)
    assert len(zusatz.blPara.lines) == 2
    # Die Spalte ist so breit wie die breiteste Zeile, nicht wie der ganze Wert.
    tabelle = render_table([zeile], with_fee=True, spalten=FACH_LISTE.spalten)
    assert tabelle._colWidths[0] < stringWidth(zeile["klasse"], "Helvetica", 10)


def test_ohne_jahreszusatz_kein_erzwungener_umbruch(planung):
    leih = _je_titel(fach_tabellen(planung, antraege=True)["Chemie"]["leih"])
    assert "\n" not in leih["Später genehmigt"]["klasse"]
    planung = Buchplanung(schuljahr=SJ, buecher=(_buch(A, "Ohne", 5, 6),),
                          planung=(_zeile(A, 5), _zeile(A, 6)))
    (zeile,) = fach_tabellen(planung, antraege=True)["Chemie"]["leih"]
    assert zeile["klasse"] == "5, 6"


def _pdf_text(planung: Buchplanung, *, antraege: bool) -> str:
    from pypdf import PdfReader

    daten = Buecherdaten(SJ, "Schuljahr 26/27", fach_tabellen(planung, antraege=antraege))
    (pdf,) = erzeuge_buecherlisten_pdfs(daten, faecher=["Chemie"], antraege=antraege,
                                        zuordnungen=Zuordnungen(fkl={}, kollegium={},
                                                                aufgabenfeld={}))
    return "".join(seite.extract_text() for seite in PdfReader(io.BytesIO(pdf.inhalt)).pages)


@pytest.mark.parametrize("antraege", [False, True])
def test_ruecklagen_als_letzte_spalte_der_leihbaren_buecher(planung, antraege):
    """Vorgabe vom 2026-11-10: nur leihbar, nur dieses Fach, nur wenn es eine gibt."""
    planung = Buchplanung(
        schuljahr=planung.schuljahr, buecher=planung.buecher, planung=planung.planung,
        ruecklagen=(Ruecklage(isbn=A, fach="Chemie", anzahl=3),
                    Ruecklage(isbn=A, fach="Physik", anzahl=7),
                    Ruecklage(isbn=D, fach="Chemie", status="gewünscht")))
    tabellen = fach_tabellen(planung, antraege=antraege)["Chemie"]
    leih = _je_titel(tabellen["leih"])
    assert leih["Laufend"]["ruecklage"] == "3"
    assert leih["Ausmusterung offen"]["ruecklage"] == ""
    assert all("ruecklage" not in zeile for zeile in tabellen["kauf"])
    text = _pdf_text(planung, antraege=antraege)
    assert "Rücklagen" in text or "Rückl." in text
    # Letzte Spalte: die Anzahl steht hinter der Leihgebühr.
    assert "4,00 €\n3\n" in text


def test_ohne_ruecklage_keine_spalte(planung):
    text = _pdf_text(planung, antraege=False)
    assert "Rücklagen" not in text and "Rückl." not in text


def test_spalte_heisst_jahrgang(planung):
    text = _pdf_text(planung, antraege=False)
    assert "Jahrgang" in text and "Klasse" not in text


def _ausmusterung(isbn: str, jahrgang: int, *, status: Antragsentscheidung = GENEHMIGT,
                  nach: str = "2025/2026", **werte) -> Planungszeile:
    return _zeile(isbn, jahrgang, ausgemustert_nach=nach, antrag_ausmusterung=status, **werte)


@pytest.mark.parametrize("antraege", [False, True])
def test_ausgemustert_nur_wenn_jeder_leihbare_jahrgang_genehmigt_geht(antraege):
    """Vorgabe vom 2026-11-10: in jedem Jahrgang, in dem die Buchreihe leihbar war."""
    planung = Buchplanung(schuljahr=SJ, buecher=(
        _buch(A, "Ganz weg"), _buch(B, "Halb weg", 6), _buch(C, "Antrag offen"),
        _buch(D, "Abgelehnt"), _buch(E, "Wird Kaufbuch", 7), _buch(F, "Kommt wieder"),
        _buch(G, "Länger her"), _buch(H, "Kaufbuch weg"),
    ), planung=(
        _ausmusterung(A, 5), _ausmusterung(A, 6),
        _ausmusterung(B, 5), _zeile(B, 6),
        _ausmusterung(C, 8), _ausmusterung(C, 9, status=Antragsentscheidung()),
        _ausmusterung(D, 10, status=ABGELEHNT),
        # Leihbar zu Kaufbuch: der leihbare Teil geht ganz.
        _ausmusterung(E, 7), _zeile(E, 7, eingefuehrt_ab=SJ, leihbar=False, antrag_einfuehrung=GENEHMIGT),
        # Geht und kommt in einem anderen Jahrgang wieder: geht nicht.
        _ausmusterung(F, 5), _zeile(F, 7, eingefuehrt_ab="2027/2028"),
        # Nach dem Vorvorjahr ausgemustert: steht nicht mehr da.
        _ausmusterung(G, 5, nach="2024/2025"),
        _ausmusterung(H, 5, leihbar=False),
    ), ruecklagen=(Ruecklage(isbn=A, fach="Chemie", anzahl=4),))
    tabellen = fach_tabellen(planung, antraege=antraege)["Chemie"]
    ausgemustert = _je_titel(tabellen["ausgemustert"])
    assert set(ausgemustert) == {"Ganz weg", "Wird Kaufbuch"}
    assert ausgemustert["Ganz weg"]["klasse"] == "5, 6"
    assert ausgemustert["Ganz weg"]["ruecklage"] == "4"
    assert "klasse_teile" not in ausgemustert["Ganz weg"]
    assert ausgemustert["Ganz weg"]["neupreis"] == "20,00 €"
    assert "Ganz weg" not in _je_titel(tabellen["leih"])


def test_ausgemustert_im_pdf_mit_spalten_der_leihbaren():
    planung = Buchplanung(schuljahr=SJ, buecher=(_buch(A, "Ganz weg"), _buch(B, "Läuft", 5)),
                          planung=(_ausmusterung(A, 5), _zeile(B, 5)),
                          ruecklagen=(Ruecklage(isbn=A, fach="Chemie", anzahl=4),))
    text = _pdf_text(planung, antraege=False)
    assert "Leihbare Buchreihen" in text and "Selbst anzuschaffende Buchreihen" in text
    _, unten = text.split("Leihbare nach vorigem Schuljahr ausgemusterte Buchreihen")
    assert "Ganz weg" in unten and "Läuft" not in unten
    # Leihgebühr und Rücklagen - die Rücklagen-Spalte nur in dieser Tabelle.
    assert "4,00 €\n4\n" in unten
    oben = text.split("Selbst anzuschaffende")[0]
    assert "Rückl" not in oben


def test_genehmigte_ausmusterung_nach_dem_vorjahr_in_der_dritten_tabelle(planung):
    """Offen oder abgelehnt bleibt die Buchreihe bei den leihbaren."""
    tabellen = fach_tabellen(planung, antraege=True)["Chemie"]
    assert [z["titel"] for z in tabellen["ausgemustert"]] == ["Ausgemustert"]
    assert tabellen["ausgemustert"][0]["klasse"] == "11"


def test_ohne_ausgemusterte_keine_dritte_tabelle():
    planung = Buchplanung(schuljahr=SJ, buecher=(_buch(A, "Läuft", 5),), planung=(_zeile(A, 5),))
    assert "ausgemusterte Buchreihen" not in _pdf_text(planung, antraege=True)


def _in(fach: str, isbn: str, jahrgang: int, **werte) -> Planungszeile:
    return Planungszeile(isbn=isbn, fach=fach, jahrgang=jahrgang,
                         leihbar=werte.pop("leihbar", True), **werte)


@pytest.fixture()
def weiter_planung() -> Buchplanung:
    """Drei in Chemie ausgemusterte Buchreihen; in anderen Fächern unterschiedlich weiter."""
    return Buchplanung(schuljahr=SJ, buecher=(
        _buch(A, "Zwei Fächer"), _buch(B, "Ein Fach"), _buch(C, "Nirgends"), _buch(D, "Wie zwei"),
    ), planung=(
        _ausmusterung(A, 5), _ausmusterung(A, 6),
        _in("Physik", A, 7), _in("Physik", A, 8),
        _in("Biologie", A, 9, eingefuehrt_ab="2027/2028", antrag_einfuehrung=GENEHMIGT),
        _ausmusterung(B, 5),
        _in("Physik", B, 10, ausgemustert_nach="2027/2028", antrag_ausmusterung=GENEHMIGT),
        _ausmusterung(C, 5),
        # Nicht genehmigt, nur Kaufbuch oder schon genehmigt ausgemustert: zählt nicht.
        _in("Physik", C, 7, eingefuehrt_ab="2027/2028"),
        _in("Biologie", C, 7, leihbar=False),
        _in("Erdkunde", C, 7, ausgemustert_nach="2025/2026", antrag_ausmusterung=GENEHMIGT),
        _ausmusterung(D, 6),
        _in("Physik", D, 7), _in("Physik", D, 8),
        _in("Biologie", D, 9, eingefuehrt_ab="2027/2028", antrag_einfuehrung=GENEHMIGT),
        # Eine offene Ausmusterung nach dem Vorjahr lässt die Buchreihe laufen.
        _in("Erdkunde", D, 5, ausgemustert_nach="2025/2026"),
    ))


def test_weiter_nur_genehmigt_leihbar_ab_diesem_schuljahr(weiter_planung):
    ausgemustert = _je_titel(fach_tabellen(weiter_planung, antraege=True)["Chemie"]["ausgemustert"])
    biologie = ("Biologie", ((f"9{NBSP}(", f"ab{NBSP}2027/2028)"),))
    assert ausgemustert["Zwei Fächer"]["weiter"] == (biologie, ("Physik", (("7, 8", ""),)))
    assert ausgemustert["Ein Fach"]["weiter"] == (
        ("Physik", ((f"10{NBSP}(", f"bis{NBSP}2027/2028)"),)),)
    assert ausgemustert["Nirgends"]["weiter"] == ()
    assert ausgemustert["Wie zwei"]["weiter"] == (
        biologie, ("Erdkunde", (("5", ""),)), ("Physik", (("7, 8", ""),)))


def test_weiter_sterne_und_buendige_erklaerung(weiter_planung):
    from buecherlisten.core.layout import _weiter_sterne

    zeilen = fach_tabellen(weiter_planung, antraege=False)["Chemie"]["ausgemustert"]
    markiert, weiter = _weiter_sterne(zeilen)
    klassen = {z["titel"]: z["klasse"] for z in markiert}
    assert klassen["Nirgends"] == "5"
    # Sortiert nach Jahrgängen und Titel; Sterne in der Reihenfolge des Auftretens.
    assert [z["titel"] for z in markiert] == ["Ein Fach", "Nirgends", "Zwei Fächer", "Wie zwei"]
    assert (klassen["Ein Fach"], klassen["Zwei Fächer"], klassen["Wie zwei"]) == (
        f"5{NBSP}*", f"5, 6{NBSP}**", f"6{NBSP}***")
    assert [stern for stern, _ in weiter] == ["*", "**", "***"]
    text = _pdf_text(weiter_planung, antraege=False)
    unten = text.split("ausgemusterte Buchreihen")[1]
    # Je weiteres Fach eine Zeile; „weiterhin leihbar in“ nur in der ersten.
    assert unten.count("weiterhin leihbar in") == 3
    assert "Physik:" in unten and "Biologie:" in unten and "Erdkunde:" in unten


def test_weiter_mehrere_zusaetze_je_jahrgang():
    """Lücke im anderen Fach: beide genehmigten Zeilen in einer Klammer, nur Beantragtes fehlt."""
    planung = Buchplanung(schuljahr=SJ, buecher=(_buch(A, "Lücke"),), planung=(
        _ausmusterung(A, 5),
        _in("Physik", A, 7, ausgemustert_nach="2027/2028", antrag_ausmusterung=GENEHMIGT),
        _in("Physik", A, 7, eingefuehrt_ab="2029/2030", antrag_einfuehrung=GENEHMIGT),
        _in("Physik", A, 8, ausgemustert_nach="2027/2028", antrag_ausmusterung=GENEHMIGT),
        _in("Physik", A, 8, eingefuehrt_ab="2029/2030"),
    ))
    (zeile,) = fach_tabellen(planung, antraege=False)["Chemie"]["ausgemustert"]
    assert zeile["weiter"] == (("Physik", (
        (f"7{NBSP}(", f"bis{NBSP}2027/2028, ab{NBSP}2029/2030),"),
        (f"8{NBSP}(", f"bis{NBSP}2027/2028)"))),)


def test_weiter_jahrgang_mit_zusatz_allein_und_buendig():
    """Vorgabe vom 2026-11-10: wie in der Spalte „Jahrgang“ steht ein Jahrgang mit
    Zusatz allein; sein Umbruch läuft bündig unter „von“ weiter."""
    from buecherlisten.core.layout import _weiter_tabelle

    planung = Buchplanung(schuljahr=SJ, buecher=(_buch(A, "Gemischt"),), planung=(
        _ausmusterung(A, 5), _in("Physik", A, 5), _in("Physik", A, 6),
        _in("Physik", A, 7, eingefuehrt_ab="2027/2028", ausgemustert_nach="2028/2029",
            antrag_einfuehrung=GENEHMIGT, antrag_ausmusterung=GENEHMIGT),
        _in("Physik", A, 8), _in("Physik", A, 9)))
    (zeile,) = fach_tabellen(planung, antraege=False)["Chemie"]["ausgemustert"]
    ((fach, gruppen),) = zeile["weiter"]
    assert gruppen == (("5, 6,", ""), (f"7{NBSP}(", f"von{NBSP}2027/2028 bis{NBSP}2028/2029),"),
                       ("8, 9", ""))
    # Je Gruppe ein Absatz; der mit Zusatz hängt hinter „7 (“.
    tabelle = _weiter_tabelle([("*", zeile["weiter"])], 140.0)
    erste, zusatz, letzte = tabelle._cellvalues[0][3]
    einzug = stringWidth(f"7{NBSP}(", "Helvetica", 8)
    assert zusatz.style.leftIndent == pytest.approx(einzug)
    assert zusatz.style.firstLineIndent == pytest.approx(-einzug)
    assert erste.style.leftIndent == letzte.style.leftIndent == 0
    zusatz.wrap(stringWidth(f"7{NBSP}(von{NBSP}2027/2028", "Helvetica", 8) + 1, 1000.0)
    assert len(zusatz.blPara.lines) == 2


# ── Anmerkungen zu entschiedenen Anträgen (Vorgabe vom 2026-11-12) ───────────

ALLE_DETAILS = Antragsdetails(datum=True, bearbeiter=True, begruendung=True)


def _entschieden(ergebnis: str, signatur: str = "max.mustermann", tag: int = 5):
    return Antragsentscheidung(ergebnis, signatur, date(2026, 11, tag))


@pytest.fixture()
def anmerkungs_planung() -> Buchplanung:
    g, a = _entschieden("genehmigt"), _entschieden("abgelehnt", "erika.musterfrau", 6)
    return Buchplanung(schuljahr=SJ, buecher=(
        _buch(A, "Viele Anträge"), _buch(B, "Ohne Begründung"), _buch(F, "Ausgemustert"),
        _buch(H, "Kaufbuch"),
    ), planung=(
        # Zu alt: Einführung vor diesem Schuljahr, Ausmusterung vor dem Vorjahr.
        _zeile(A, 5, eingefuehrt_ab="2025/2026", antrag_einfuehrung=g),
        _zeile(A, 6, ausgemustert_nach="2027/2028", antrag_ausmusterung=a,
               begruendung_ausmusterung="Wird noch gebraucht."),
        _zeile(A, 7, eingefuehrt_ab=SJ, antrag_einfuehrung=g, begruendung_einfuehrung="Neu",
               ausgemustert_nach=SJ, antrag_ausmusterung=g),
        _zeile(A, 7, eingefuehrt_ab="2028/2029", antrag_einfuehrung=a),
        # Offen: keine Anmerkung.
        _zeile(A, 8, eingefuehrt_ab="2027/2028"),
        # Genehmigt ausgemustert nach dem Vorjahr: zählt.
        _zeile(A, 9, ausgemustert_nach="2025/2026", antrag_ausmusterung=g),
        _zeile(B, 10, eingefuehrt_ab="2027/2028", antrag_einfuehrung=g),
        _ausmusterung(F, 11, status=g, begruendung_ausmusterung="Veraltet."),
        _zeile(H, 5, leihbar=False, eingefuehrt_ab=SJ, antrag_einfuehrung=g),
    ))


def test_anmerkungen_sortiert_und_jahrgang_nur_einmal(anmerkungs_planung):
    tabellen = fach_tabellen(anmerkungs_planung, antraege=True, details=ALLE_DETAILS)["Chemie"]
    leih = _je_titel(tabellen["leih"])
    am5, am6 = "am 05.11.2026", "am 06.11.2026"
    durch_m, durch_e = "durch max.mustermann", "durch erika.musterfrau"
    assert leih["Viele Anträge"]["anmerkungen"] == (
        ("Jahrgang", "6", "Ausmusterung", "2027/2028", "abgelehnt", am6, durch_e,
         f"Begründung: {EINZUG}Wird noch gebraucht."),
        # Gleiches Schuljahr: die Einführung zuerst.
        ("Jahrgang", "7", "Einführung", SJ, "genehmigt", am5, durch_m, f"Begründung: {EINZUG}Neu"),
        ("", "", "Ausmusterung", SJ, "genehmigt", am5, durch_m, ""),
        ("", "", "Einführung", "2028/2029", "abgelehnt", am6, durch_e, ""),
        ("Jahrgang", "9", "Ausmusterung", "2025/2026", "genehmigt", am5, durch_m, ""),
    )
    assert _je_titel(tabellen["kauf"])["Kaufbuch"]["anmerkungen"] == (
        ("Jahrgang", "5", "Einführung", SJ, "genehmigt", am5, durch_m, ""),)
    assert _je_titel(tabellen["ausgemustert"])["Ausgemustert"]["anmerkungen"] == (
        ("Jahrgang", "11", "Ausmusterung", "2025/2026", "genehmigt", am5, durch_m,
         f"Begründung: {EINZUG}Veraltet."),)


def test_anmerkungen_nur_mit_dem_angehakten(anmerkungs_planung):
    nur_datum = _je_titel(fach_tabellen(anmerkungs_planung, antraege=True, details=Antragsdetails(
        datum=True))["Chemie"]["leih"])
    assert nur_datum["Ohne Begründung"]["anmerkungen"] == (
        ("Jahrgang", "10", "Einführung", "2027/2028", "genehmigt", "am 05.11.2026"),)
    # Nur „Begründung“: ein Antrag ohne Begründung fehlt, eine Buchreihe ohne
    # einen solchen hat keine Anmerkungen; der Jahrgang steht im ersten, der bleibt.
    begruendung = fach_tabellen(anmerkungs_planung, antraege=True,
                                details=Antragsdetails(begruendung=True))["Chemie"]
    leih = _je_titel(begruendung["leih"])
    assert "anmerkungen" not in leih["Ohne Begründung"]
    assert [z[1] for z in leih["Viele Anträge"]["anmerkungen"]] == ["6", "7"]
    assert "anmerkungen" not in _je_titel(begruendung["kauf"])["Kaufbuch"]


@pytest.mark.parametrize(("antraege", "details"), [
    (True, Antragsdetails()), (False, ALLE_DETAILS)])
def test_ohne_haekchen_oder_antragsinformationen_keine_anmerkungen(
        anmerkungs_planung, antraege, details):
    tabellen = fach_tabellen(anmerkungs_planung, antraege=antraege, details=details)["Chemie"]
    assert not any("anmerkungen" in zeile for zeilen in tabellen.values() for zeile in zeilen)


def test_anmerkungen_buendig_und_begruendung_haengend():
    from buecherlisten.core.layout import _anmerkungen_tabelle

    tabelle = _anmerkungen_tabelle((
        ("Jahrgang", "6", "Ausmusterung", "2027/2028", "abgelehnt", "",
         f"Begründung: {EINZUG}Zeile 1\nZeile 2"),
        ("", "", "Einführung", SJ, "genehmigt", "", ""),
        ("Jahrgang", "10", "Einführung", SJ, "genehmigt", "", ""),
    ), 300.0)
    # Die in keiner Zeile gefüllte Spalte fällt weg.
    assert len(tabelle._colWidths) == 6
    luecke = stringWidth(" ", "Helvetica", 8)
    assert tabelle._colWidths[2] == pytest.approx(
        stringWidth("Ausmusterung", "Helvetica", 8) + luecke, abs=0.6)
    # Der Jahrgang rechtsbündig, das Leerzeichen rechts von ihm.
    sechs, _, zehn = (zeile[1] for zeile in tabelle._cellvalues)
    assert sechs.style.alignment == zehn.style.alignment == TA_RIGHT
    assert tabelle._cellvalues[0][2].style.alignment != TA_RIGHT
    assert tabelle._cellStyles[2][1].rightPadding == pytest.approx(luecke)
    assert tabelle._cellStyles[2][2].rightPadding == 0
    begruendung = tabelle._cellvalues[0][5]
    einzug = stringWidth("Begründung: ", "Helvetica", 8)
    assert begruendung.style.leftIndent == pytest.approx(einzug)
    assert begruendung.style.firstLineIndent == pytest.approx(-einzug)
    assert "Zeile 1<br/>Zeile 2" in begruendung.text


def test_anmerkungen_in_der_zeile_der_buchreihe(anmerkungs_planung):
    leih = fach_tabellen(anmerkungs_planung, antraege=True, details=ALLE_DETAILS)["Chemie"]["leih"]
    tabelle = render_table(leih, with_fee=True, spalten=FACH_LISTE.spalten)
    # Kopf, je Buchreihe ihre Zeile und darunter die Anmerkungen.
    assert len(tabelle._cellvalues) == 1 + 2 * len(leih)
    befehle = tabelle._linecmds
    linien = sorted(start[1] for name, start, *_ in befehle if name == "LINEBELOW" and start[1])
    assert linien == [2, 4]
    assert ("SPAN", (0, 2), (-1, 2)) in tabelle._spanCmds
    # pypdf liest jede Zelle als eigene Zeile.
    text = " ".join(_pdf_text_mit(anmerkungs_planung, ALLE_DETAILS).split())
    assert "Jahrgang 6 Ausmusterung 2027/2028 abgelehnt am 06.11.2026 durch erika.musterfrau" in text
    assert "Begründung: Veraltet." in text


def _pdf_text_mit(planung: Buchplanung, details: Antragsdetails) -> str:
    from pypdf import PdfReader

    daten = Buecherdaten(SJ, "Schuljahr 26/27",
                         fach_tabellen(planung, antraege=True, details=details))
    (pdf,) = erzeuge_buecherlisten_pdfs(daten, faecher=["Chemie"], antraege=True,
                                        zuordnungen=Zuordnungen(fkl={}, kollegium={},
                                                                aufgabenfeld={}))
    return "".join(seite.extract_text() for seite in PdfReader(io.BytesIO(pdf.inhalt)).pages)
