"""buecherlisten/core: Laden, Fächerauswahl und PDF-Erzeugung ohne Netz.

Die Website-Zuordnungen werden über ``Zuordnungen`` vorgegeben; ein Test, der
sie vergäße, würde live die TRG-Website abfragen. Das Layout selbst prüft
diese Datei nicht - dafür war der Pixelvergleich beim Herauslösen aus
generate_booklists.py da (2026-09-17: 48 Seiten identisch).
"""
from __future__ import annotations

import io
import re

import pytest

pytest.importorskip("reportlab")

from bestand.core.testing import FakeClient  # noqa: E402
from buecherlisten.core.daten import lade_buecherdaten, waehle_faecher, waehle_gruppen  # noqa: E402
from buecherlisten.core.erzeugen import (  # noqa: E402
    Zuordnungen,
    erzeuge_buecherlisten_pdfs,
    erzeuge_schuelerlisten_pdfs,
)

OHNE_NETZ = Zuordnungen(fkl={}, kollegium={}, aufgabenfeld={"Erdkunde": "B", "Deutsch": "A"})


@pytest.fixture()
def daten():
    return lade_buecherdaten(FakeClient())


def _seiten(inhalt: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", inhalt))


def test_faecher_und_schuljahr(daten):
    assert daten.faecher == ["Deutsch", "Erdkunde"]
    assert daten.schuljahr_id == "2026/2027"


def test_faecherauswahl_ohne_gross_klein(daten):
    gefunden, unbekannt = waehle_faecher(daten.faecher, ["erdkunde", "Latein", "ERDKUNDE"])
    assert gefunden == ["Erdkunde"]
    assert unbekannt == ["Latein"]


def test_ein_pdf_fuer_alle_faecher(daten):
    (pdf,) = erzeuge_buecherlisten_pdfs(daten, zuordnungen=OHNE_NETZ)
    assert pdf.inhalt.startswith(b"%PDF")
    assert pdf.dateiname == "Bücherliste Fächer 2026-2027.pdf"
    assert _seiten(pdf.inhalt) == 2
    assert pdf.warnungen == []


def test_split_liefert_ein_pdf_je_fach(daten):
    pdfs = erzeuge_buecherlisten_pdfs(daten, faecher=["Erdkunde"], modus="split", zuordnungen=OHNE_NETZ)
    assert [p.dateiname for p in pdfs] == ["Bücherliste Erdkunde 2026-2027.pdf"]


def test_bestaetigung_setzt_praefix(daten):
    (pdf,) = erzeuge_buecherlisten_pdfs(
        daten, bestaetigung=True, rueckgabe_bis="08.09.2026", rueckgabe_an="Ml", zuordnungen=OHNE_NETZ,
    )
    assert pdf.dateiname.startswith("Bestätigung ")
    assert pdf.inhalt.startswith(b"%PDF")


def test_doppelseitig_polstert_jedes_fach_auf_gerade_seitenzahl(daten):
    (pdf,) = erzeuge_buecherlisten_pdfs(daten, doppelseitig=True, zuordnungen=OHNE_NETZ)
    assert _seiten(pdf.inhalt) == 4


def test_falls_noetig_polstert_nicht_wenn_alles_einseitig_ist(daten):
    (pdf,) = erzeuge_buecherlisten_pdfs(
        daten, doppelseitig=True, nur_falls_noetig=True, zuordnungen=OHNE_NETZ,
    )
    assert _seiten(pdf.inhalt) == 2


def test_schulanschrift_kommt_aus_der_api(daten):
    from buecherlisten.core.layout import footer_context

    assert (daten.schule_name, daten.schule_ort) == ("Testschule", "Teststadt")
    assert footer_context(
        "Fächer", daten.schuljahr_name,
        school_name=daten.schule_name, school_city=daten.schule_ort,
    ).startswith("Testschule, Teststadt – Bücherliste Fächer")


def test_fehlende_schulanschrift_wird_warnung_statt_abbruch(daten, monkeypatch):
    from buecherlisten.core.layout import SCHOOL_CITY, SCHOOL_NAME, footer_context

    class KaputterAdmin:
        def get_school_address(self) -> dict[str, str]:
            raise OSError("kein Netz")

    kaputt = FakeClient()
    kaputt.admin = KaputterAdmin()
    ohne_anschrift = lade_buecherdaten(kaputt)
    assert (ohne_anschrift.schule_name, ohne_anschrift.schule_ort) == (None, None)
    assert footer_context("Fächer", "2026/2027").startswith(f"{SCHOOL_NAME}, {SCHOOL_CITY} –")

    (pdf,) = erzeuge_buecherlisten_pdfs(ohne_anschrift, zuordnungen=OHNE_NETZ)
    assert pdf.inhalt.startswith(b"%PDF")
    assert [w for w in pdf.warnungen if "Schulname/Ort" in w]


def test_fehlende_website_wird_warnung_statt_abbruch(daten, monkeypatch):
    from buecherlisten.core import erzeugen

    def kaputt() -> dict[str, str]:
        raise OSError("kein Netz")

    monkeypatch.setattr(erzeugen, "fetch_fkl_mapping", kaputt)
    monkeypatch.setattr(erzeugen, "fetch_kollegium_kuerzel_mapping", kaputt)
    (pdf,) = erzeuge_buecherlisten_pdfs(daten, bestaetigung=True)
    assert pdf.inhalt.startswith(b"%PDF")
    assert len(pdf.warnungen) == 2
    assert all("kein Netz" in w for w in pdf.warnungen)


# ── Verlag, Jahrgang und Schülerliste ────────────────────────────────────────

def test_verlage_und_jahrgaenge_stehen_neben_den_faechern(daten):
    assert daten.verlage == ["Cornelsen", "Klett", "Westermann"]
    # Jahrgänge zählen numerisch, nicht alphabetisch ("Jahrgang 12" zuletzt).
    assert daten.jahrgaenge == ["Jahrgang 5", "Jahrgang 6", "Jahrgang 7", "Jahrgang 12"]
    assert daten.gruppen("verlag") == daten.verlage
    assert set(daten.listen_ids) == set(daten.jahrgaenge)


def test_jahrgangstabelle_behaelt_die_reihenfolge_der_iserv_liste(daten):
    zeilen = daten.je_jahrgang["Jahrgang 5"]["leih"]
    assert [z["titel"] for z in zeilen] == ["Deutschbuch 5", "Terra 5/6", "Deutschbuch eBook"]
    # Fach statt Klasse ist die Spalte, die die Jahrgangsliste braucht.
    assert zeilen[0]["fach"] == "Deutsch"


def test_mehrjahresband_steht_beim_verlag_einmal_mit_allen_klassen(daten):
    (terra,) = [z for z in daten.je_verlag["Klett"]["leih"] if z["titel"] == "Terra 5/6"]
    assert terra["klasse"] == "5, 6"


def test_korrekturen_wirken_auf_titel_verlag_und_preis_im_pdf():
    """Korrigiert wird in der Buchplanung; das PDF zeigt, was dort steht."""
    from bestand.core.testing import ISBN_ERDKUNDE_56

    gesehen: list[str] = []

    def korrekturen(kennung: str) -> dict:
        gesehen.append(kennung)
        return {ISBN_ERDKUNDE_56: {"title": "Terra 5/6 NRW", "publisher": "Klett Verlag",
                                   "price": 27.5}}

    daten = lade_buecherdaten(FakeClient(), korrekturen=korrekturen)

    assert gesehen == [daten.schuljahr_id]
    assert "Klett Verlag" in daten.verlage
    (terra,) = [z for z in daten.je_verlag["Klett Verlag"]["leih"]
                if z["titel"] == "Terra 5/6 NRW"]
    assert terra["neupreis"] == "27,50 €"


def test_korrekturen_aendern_die_rohdaten_aus_iserv_nicht():
    from buecherlisten.core.daten import wende_korrekturen_an

    detail = {"sections": [{"options": [{"items": [
        {"series": "111", "series_data": {"isbn": "111", "title": "Alt"}}]}]}]}
    neu = wende_korrekturen_an(detail, {"111": {"title": "Neu"}})

    (item,) = neu["sections"][0]["options"][0]["items"]
    assert item["series"] == "111"
    assert item["series_data"] == {"isbn": "111", "title": "Neu"}
    assert detail["sections"][0]["options"][0]["items"][0]["series_data"]["title"] == "Alt"


@pytest.mark.parametrize("ansicht, dateiname", [
    ("verlag", "Bücherliste Verlage 2026-2027.pdf"),
    ("jahrgang", "Bücherliste Jahrgänge 2026-2027.pdf"),
])
def test_ein_pdf_je_ansicht(daten, ansicht, dateiname):
    (pdf,) = erzeuge_buecherlisten_pdfs(daten, ansicht=ansicht, zuordnungen=OHNE_NETZ)
    assert pdf.dateiname == dateiname
    assert _seiten(pdf.inhalt) == len(daten.gruppen(ansicht))


def test_auswahl_folgt_der_reihenfolge_der_ansicht(daten):
    gefunden, unbekannt = waehle_gruppen(daten, "jahrgang", ["12", "jahrgang 5", "Jahrgang 3"])
    assert gefunden == ["Jahrgang 5", "Jahrgang 12"]
    assert unbekannt == ["Jahrgang 3"]


@pytest.mark.parametrize("optionen", [
    {"bestaetigung": True}, {"modus": "aufgabenfeld"}, {"iserv_stand": True},
])
def test_bestaetigung_und_aufgabenfeld_nur_fuer_faecher(daten, optionen):
    with pytest.raises(ValueError):
        erzeuge_buecherlisten_pdfs(daten, ansicht="verlag", zuordnungen=OHNE_NETZ, **optionen)


# ── IServ-Stand (Vorgabe vom 2026-11-10) ─────────────────────────────────────

def _seitentexte(inhalt: bytes) -> list[str]:
    from pypdf import PdfReader
    return [seite.extract_text() for seite in PdfReader(io.BytesIO(inhalt)).pages]


def _zeilen_links(inhalt: bytes, seite: int = 0) -> dict[str, float]:
    """Text am linken Rand der Fußzeile -> Grundlinie (Punkte vom Unterrand)."""
    from pypdf import PdfReader
    gefunden: dict[str, float] = {}

    def merke(text, _cm, tm, _font, _size):
        if text.strip() and tm[5] < 40 and abs(tm[4] - 72.0) < 1:
            gefunden[text.strip()] = round(tm[5], 3)

    PdfReader(io.BytesIO(inhalt)).pages[seite].extract_text(visitor_text=merke)
    return gefunden


@pytest.fixture()
def iserv_daten(daten):
    from dataclasses import replace
    return replace(daten, schuljahr_name="Schuljahr 26/27")


def test_iserv_stand_ersetzt_die_einleitung(iserv_daten):
    (pdf,) = erzeuge_buecherlisten_pdfs(iserv_daten, faecher=["Deutsch"], iserv_stand=True,
                                       zuordnungen=OHNE_NETZ)
    text = " ".join(_seitentexte(pdf.inhalt)[0].split())
    # Vier Bücherlisten im Schuljahr: Mehrzahl.
    assert ("Folgende Buchreihen führen die Bücherlisten für das Fach Deutsch im "
            "Schuljahr 26/27.") in text
    assert "über die Schule ausgeliehen" not in text
    assert "gesondert in der zweiten Tabelle" not in text
    # Der Rest bleibt: Kopf und Tabellen.
    assert "Bücherliste Deutsch" in text and "Leihbare Bücher" in text


def test_iserv_stand_mit_einer_buecherliste_steht_in_der_einzahl(iserv_daten):
    from dataclasses import replace
    eine = replace(iserv_daten, listen_ids={"Jahrgang 5": 105})
    (pdf,) = erzeuge_buecherlisten_pdfs(eine, faecher=["Deutsch"], iserv_stand=True,
                                       zuordnungen=OHNE_NETZ)
    text = " ".join(_seitentexte(pdf.inhalt)[0].split())
    assert "Folgende Buchreihen führt die Bücherliste für das Fach Deutsch" in text


def test_iserv_stand_nennt_die_quelle_unter_dem_erstelldatum(iserv_daten):
    from buecherlisten.core.layout import FOOTER_INFO_BASELINE, FOOTER_PAGE_BASELINE

    for modus in ("alphabet", "split"):
        (pdf, *_) = erzeuge_buecherlisten_pdfs(iserv_daten, modus=modus, iserv_stand=True,
                                              zuordnungen=OHNE_NETZ)
        links = _zeilen_links(pdf.inhalt)
        (erstellt,) = [y for text, y in links.items() if text.startswith("Erstellt:")]
        assert erstellt == pytest.approx(FOOTER_PAGE_BASELINE, abs=0.01)
        assert links["IServ-Bücherlisten"] == pytest.approx(FOOTER_INFO_BASELINE, abs=0.01)

    # Ohne IServ-Stand bleibt die Fußzeile, wie sie war.
    (pdf,) = erzeuge_buecherlisten_pdfs(iserv_daten, zuordnungen=OHNE_NETZ)
    links = _zeilen_links(pdf.inhalt)
    assert "IServ-Bücherlisten" not in links
    (erstellt,) = [y for text, y in links.items() if text.startswith("Erstellt:")]
    assert erstellt == pytest.approx(FOOTER_INFO_BASELINE, abs=0.01)


@pytest.mark.parametrize("optionen", [
    {}, {"iserv_stand": True}, {"modus": "aufgabenfeld"}, {"doppelseitig": True},
])
def test_seriendruck_der_faecher_zaehlt_je_fach(iserv_daten, optionen):
    """Für jeden Seriendruck der Fächer (Vorgabe vom 2026-11-10)."""
    (pdf,) = erzeuge_buecherlisten_pdfs(iserv_daten, zuordnungen=OHNE_NETZ, **optionen)
    seiten = [t for t in _seitentexte(pdf.inhalt) if t.strip()]
    assert len(seiten) == 2
    for text, fach in zip(seiten, ["Deutsch", "Erdkunde"], strict=True):
        assert "Seite 1 von 1" in text
        assert f"Bücherliste {fach} (Schuljahr 26/27)" in text


@pytest.mark.parametrize("ansicht", ["verlag", "jahrgang"])
def test_seriendruck_der_verlage_und_jahrgaenge_zaehlt_je_gruppe(iserv_daten, ansicht):
    (pdf,) = erzeuge_buecherlisten_pdfs(iserv_daten, ansicht=ansicht, zuordnungen=OHNE_NETZ)
    gruppen = iserv_daten.gruppen(ansicht)
    seiten = _seitentexte(pdf.inhalt)
    assert len(seiten) == len(gruppen) > 1
    for text, gruppe in zip(seiten, gruppen, strict=True):
        assert "Seite 1 von 1" in text
        assert f"Bücherliste {gruppe} (Schuljahr 26/27)" in text


def test_iserv_stand_ohne_bestaetigung(daten):
    with pytest.raises(ValueError):
        erzeuge_buecherlisten_pdfs(daten, iserv_stand=True, bestaetigung=True,
                                   zuordnungen=OHNE_NETZ)


def _iserv_pdf(seiten: int) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen.canvas import Canvas

    puffer = io.BytesIO()
    c = Canvas(puffer, pagesize=A4)
    for _ in range(seiten):
        c.drawString(72, 700, "IServ")
        c.showPage()
    c.save()
    return puffer.getvalue()


def test_schuelerliste_haengt_die_iserv_pdfs_aneinander(daten):
    (pdf,) = erzeuge_schuelerlisten_pdfs(daten, lambda listen_id: _iserv_pdf(1))
    assert pdf.dateiname == "Bücherliste Jahrgänge 2026-2027 (Schülerliste).pdf"
    assert _seiten(pdf.inhalt) == len(daten.jahrgaenge)


def test_schuelerliste_split_und_auswahl(daten):
    pdfs = erzeuge_schuelerlisten_pdfs(
        daten, lambda listen_id: _iserv_pdf(1), jahrgaenge=["Jahrgang 12", "Jahrgang 5"], modus="split",
    )
    assert [p.dateiname for p in pdfs] == [
        "Bücherliste Jahrgang 5 2026-2027 (Schülerliste).pdf",
        "Bücherliste Jahrgang 12 2026-2027 (Schülerliste).pdf",
    ]


def test_schuelerliste_polstert_nur_bei_bedarf_auf_gerade_seitenzahl(daten):
    einseitig = erzeuge_schuelerlisten_pdfs(
        daten, lambda listen_id: _iserv_pdf(1), doppelseitig=True, nur_falls_noetig=True,
    )[0]
    assert _seiten(einseitig.inhalt) == 4

    def gemischt(listen_id: int) -> bytes:
        return _iserv_pdf(3 if listen_id == daten.listen_ids["Jahrgang 5"] else 1)

    gepolstert = erzeuge_schuelerlisten_pdfs(
        daten, gemischt, doppelseitig=True, nur_falls_noetig=True,
    )[0]
    # 3 + 1 Leerseite für Jahrgang 5, je 1 + 1 für die drei anderen.
    assert _seiten(gepolstert.inhalt) == 10


def test_null_euro_ist_ein_betrag():
    """0 ist ein Preis, kein fehlender (Entscheidung 2026-10-10)."""
    from buecherlisten.core.daten import fmt_price

    assert fmt_price(0) == "0,00 €"
    assert fmt_price(12.5) == "12,50 €"
    assert fmt_price(None) == "–"
