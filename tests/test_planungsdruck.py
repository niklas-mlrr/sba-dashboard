"""Die Fach-PDF aus der Planungsdatei (Vorgabe vom 2026-11-10): app/planungsdruck.py.

Ein Fach, Chemie, im Schuljahr 2026/2027, mit je einem Buch für jeden Fall:
genehmigt und laufend, beantragt, abgelehnt, ausgemustert, später eingeführt.
"""
from __future__ import annotations

import io

import pytest
from reportlab.pdfbase.pdfmetrics import stringWidth

from app.planungsdruck import NBSP, fach_tabellen
from buecherlisten.core.daten import Buecherdaten
from buecherlisten.core.erzeugen import Zuordnungen, erzeuge_buecherlisten_pdfs
from buecherlisten.core.layout import (
    CONTENT_WIDTH,
    FACH_LISTE_ANTRAEGE,
    STIL_DURCH,
    STIL_GRAU,
    _wrap_lines,
    _zelle,
    render_table,
)
from buecherlisten.planung import Antragsentscheidung, Buch, Buchplanung, Planungszeile

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
    assert leih["Laufend"]["klasse"] == f"5, 6, 7{NBSP}(ab{NBSP}2026/2027)"
    assert leih["Später genehmigt"]["klasse"] == f"5{NBSP}(ab{NBSP}2027/2028)"
    assert leih["Ausmusterung offen"]["klasse"] == f"10{NBSP}(bis{NBSP}2025/2026)"
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
    assert leih["Neu abgelehnt"]["klasse"] == f"9{NBSP}(ab{NBSP}2026/2027)"


def test_von_bis_bricht_nur_vor_bis():
    planung = Buchplanung(schuljahr=SJ, buecher=(_buch(A, "Kurz"),), planung=(
        _zeile(A, 7, eingefuehrt_ab="2027/2028", ausgemustert_nach="2028/2029"),))
    (zeile,) = fach_tabellen(planung, antraege=True)["Chemie"]["leih"]
    assert zeile["klasse"] == f"7{NBSP}(von{NBSP}2027/2028 bis{NBSP}2028/2029)"
    assert _wrap_lines(zeile["klasse"], 1.0) == [f"7{NBSP}(von{NBSP}2027/2028",
                                                 f"bis{NBSP}2028/2029)"]


def test_zellen_tragen_den_stil(planung):
    leih = _je_titel(fach_tabellen(planung, antraege=True)["Chemie"]["leih"])
    klasse, titel, isbn = FACH_LISTE_ANTRAEGE.spalten[0], FACH_LISTE_ANTRAEGE.spalten[1], \
        FACH_LISTE_ANTRAEGE.spalten[3]
    grau = _zelle(leih["Neu beantragt"], titel)
    assert 'color="#8c8c8c"' in grau.text and "Neu beantragt" in grau.text
    durch = _zelle(leih["Neu abgelehnt"], isbn)
    assert "<strike>" in durch.text
    assert "<strike>" in _zelle(leih["Ausmusterung abgelehnt"], klasse).text
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
    tabelle = render_table([lang], with_fee=True, spalten=FACH_LISTE_ANTRAEGE.spalten)
    einzeilig = stringWidth(lang["klasse"], "Helvetica", 10)
    assert tabelle._colWidths[0] < einzeilig * 0.6
    # Die Tabelle bleibt in der Breite des Satzspiegels.
    assert sum(tabelle._colWidths) == pytest.approx(CONTENT_WIDTH)


def test_ein_nur_beantragtes_fach_hat_ohne_antraege_leere_tabellen():
    """Die Fächer sind die des Druckmenüs ohne IServ-Stand - mit und ohne Anträge gleich."""
    planung = Buchplanung(schuljahr=SJ, buecher=(_buch(A, "Neu"),), planung=(
        _zeile(A, 7, eingefuehrt_ab="2027/2028"),))
    assert fach_tabellen(planung, antraege=False) == {"Chemie": {"leih": [], "kauf": []}}
    assert len(fach_tabellen(planung, antraege=True)["Chemie"]["leih"]) == 1
