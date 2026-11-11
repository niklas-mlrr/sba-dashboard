"""Spaltenbreiten der Bücherlisten-Tabellen (Vorgabe vom 2026-11-11).

Köpfe zuerst kurz; Jahrgang, Titel und Verlag teilen sich den Rest so, dass
die Tabelle am wenigsten Zeilen hoch ist - ohne feste Mindestbreite, nur nie
schmaler als ihr breitestes Wort und ihr Kopf; dann lange Köpfe, dann Abstände.
"""
from __future__ import annotations

import pytest

pytest.importorskip("reportlab")

from buecherlisten.core.layout import (  # noqa: E402
    CELL_STYLE,
    CELL_VPAD,
    CONTENT_WIDTH,
    FACH_LISTE,
    ISBN_FONT_SIZE,
    MIN_GAP,
    MIN_WRAP_COL,
    RUECKLAGEN,
    _lange_koepfe,
    _max_word_width,
    _raw_width,
    _wrap_info,
    render_table,
)


def _zeile(klasse: str, titel: str, verlag: str, ruecklage: str = "") -> dict:
    return {"klasse": klasse, "titel": titel, "verlag": verlag, "isbn": "978-3-12-345678-9",
            "neupreis": "24,95 €", "leihgebuehr": "8,00 €", "ruecklage": ruecklage}


# Nach Chemie und Geschichte der Planungsdatei 2026/2027: mit der früheren
# 20-mm-Mindestbreite brauchten beide eine Zeile mehr.
CHEMIE = [
    _zeile("5, 6", "Elemente Chemie 5/6, Nds. G9", "Klett"),
    _zeile("7, 8", "Elemente Chemie 7/8 Niedersachsen G9", "Klett"),
    _zeile("9, 10", "Elemente Chemie 9/10 Nds G9", "Klett"),
    _zeile("11", "Elemente Chemie Oberstufe Einführungsphase Nds", "Klett"),
    _zeile("12, 13", "Elemente Chemie Oberstufe, Ausgabe Niedersachsen Klassen 11-13 G9", "Klett"),
]
GESCHICHTE = [
    _zeile("5", "Das waren Zeiten 1 - Neue Ausgabe Nds.", "Buchner"),
    _zeile("6", "Das waren Zeiten - Neue Ausgabe Nds. Bd.2", "Buchner"),
    _zeile("7, 8", "Das waren Zeiten - Neue Ausgabe Band 3", "Buchner"),
    _zeile("9, 10", "Das waren Zeiten - Neue Ausgabe Band 4", "C. C. Buchner"),
    _zeile("11", "Kurshefte Geschichte Gesamtband Nds. Einführungsphase", "Cornelsen"),
]


def _gesetzt(rows: list[dict], spalten=FACH_LISTE.spalten):
    tabelle = render_table(rows, with_fee=True, spalten=spalten)
    tabelle.wrap(CONTENT_WIDTH, 1e6)
    return tabelle


def _hoehe(tabelle) -> int:
    """Die Höhe der gesetzten Tabelle in Textzeilen (ohne Kopf)."""
    return sum(round((h - 2 * CELL_VPAD) / CELL_STYLE.leading) for h in tabelle._rowHeights[1:])


def _inhalte(tabelle) -> list[float]:
    """Je Spalte die Breite der Textfläche (ohne Polster, also ohne Lücken)."""
    return [w - zelle.leftPadding - zelle.rightPadding
            for w, zelle in zip(tabelle._colWidths, tabelle._cellStyles[1], strict=True)]


def _zeilen(text: str, breite: float) -> int:
    return _wrap_info(text, breite)[0]


def _bestes(rows: list[dict], jahrgang: float, verfuegbar: float) -> int:
    """Die kleinste Höhe, wenn der Jahrgang ``jahrgang`` breit ist und Titel
    und Verlag sich ``verfuegbar`` in 0,25-pt-Schritten teilen - keine
    schmaler als ihr Kopf."""
    titel_min = max(_raw_width("Titel", []), _max_word_width([r["titel"] for r in rows]))
    verlag_min = max(_raw_width("Verlag", []), _max_word_width([r["verlag"] for r in rows]))
    hoehen = []
    w = titel_min
    while w <= verfuegbar - verlag_min:
        hoehen.append(sum(
            max(_wrap_info(r["titel"], w)[0], _wrap_info(r["verlag"], verfuegbar - w)[0],
                _wrap_info(r["klasse"], jahrgang)[0])
            for r in rows))
        w += 0.25
    return min(hoehen)


def test_eine_spalte_mit_kurzen_werten_ist_schmaler_als_20_mm():
    tabelle = _gesetzt(CHEMIE)
    # „Klett“ unter „Verlag“: die Spalte ist so breit wie ihr Kopf.
    assert _inhalte(tabelle)[2] < MIN_WRAP_COL


def test_ein_verlag_bricht_um_wenn_es_zeilen_spart():
    """„C. C. Buchner“ zweizeilig neben einem zweizeiligen Titel gibt dem Titel Platz."""
    tabelle = _gesetzt(GESCHICHTE)
    assert _zeilen(GESCHICHTE[3]["verlag"], _inhalte(tabelle)[2]) == 2


@pytest.mark.parametrize("rows", [CHEMIE, GESCHICHTE], ids=["chemie", "geschichte"])
def test_keine_aufteilung_von_titel_und_verlag_ist_niedriger(rows):
    tabelle = _gesetzt(rows)
    inhalte = _inhalte(tabelle)
    # Was neben Jahrgang, den einzeiligen Spalten (mit kurzem Kopf) und den
    # Mindestabständen bleibt - unabhängig davon gerechnet, wie die Tabelle
    # den Platz verteilt hat.
    einzeilig = [_raw_width("ISBN", [r["isbn"] for r in rows], value_size=ISBN_FONT_SIZE),
                 _raw_width("Neupreis", [r["neupreis"] for r in rows]),
                 _raw_width("Leihgeb.", [r["leihgebuehr"] for r in rows])]
    verfuegbar = CONTENT_WIDTH - MIN_GAP * (len(inhalte) - 1) - sum(einzeilig) - inhalte[0]
    assert _hoehe(tabelle) <= _bestes(rows, inhalte[0], verfuegbar)
    assert sum(tabelle._colWidths) == pytest.approx(CONTENT_WIDTH)


def test_koepfe_werden_lang_wenn_platz_bleibt():
    tabelle = _gesetzt([_zeile("5", "Kurz", "Klett", "3")], (*FACH_LISTE.spalten, RUECKLAGEN))
    assert tabelle._cellvalues[0] == ["Jahrgang", "Titel", "Verlag", "ISBN", "Neupreis",
                                      "Leihgebühr", "Rücklagen"]
    assert _hoehe(tabelle) == 1


def test_koepfe_bleiben_kurz_wenn_der_platz_fuer_zeilen_gebraucht_wird():
    tabelle = _gesetzt(CHEMIE, (*FACH_LISTE.spalten, RUECKLAGEN))
    koepfe = tabelle._cellvalues[0]
    assert (koepfe[0], koepfe[5], koepfe[6]) == ("Jg.", "Leihgeb.", "Rückl.")


def test_nichts_bricht_um_ohne_hoehe_zu_sparen():
    """Neben dem zweizeiligen Titel bliebe der Verlag auch umbrochen bei zwei
    Zeilen - er tut es trotzdem nicht, solange es keine Zeile spart."""
    zeile = _zeile("5", "Elemente Chemie Oberstufe, Ausgabe Niedersachsen "
                        "Klassen 11-13 G9 mit noch mehr Text dahinter", "C. C. Buchner")
    tabelle = _gesetzt([zeile])
    assert _zeilen(zeile["titel"], _inhalte(tabelle)[1]) > 1
    assert _zeilen(zeile["verlag"], _inhalte(tabelle)[2]) == 1


def test_der_jahrgang_bricht_auch_ohne_antragsinformationen_um():
    zeile = _zeile("5, 6, 7, 8, 9, 10, 11, 12, 13",
                   "Ein recht langer Titel, der ohnehin über mehrere Zeilen geht "
                   "und noch etwas länger ist", "Westermann")
    tabelle = _gesetzt([zeile])
    assert _zeilen(zeile["klasse"], _inhalte(tabelle)[0]) > 1
    assert sum(tabelle._colWidths) == pytest.approx(CONTENT_WIDTH)


def test_die_meisten_langen_koepfe_gewinnen():
    """Jahrgang allein passte, Leihgebühr und Rücklagen zusammen auch - zwei schlagen einen."""
    breiten = [10.0, 100.0, 20.0, 15.0]
    lang = {0: 40.0, 2: 35.0, 3: 30.0}  # je +30, +15, +15
    assert _lange_koepfe(breiten, lang, sum(breiten) + 30.0) == (2, 3)


def test_bei_gleichstand_gewinnen_die_vorderen_koepfe():
    breiten = [10.0, 100.0, 20.0, 15.0]
    lang = {0: 25.0, 2: 35.0, 3: 30.0}  # je +15
    assert _lange_koepfe(breiten, lang, sum(breiten) + 30.0) == (0, 2)
    assert _lange_koepfe(breiten, lang, sum(breiten) + 15.0) == (0,)
    assert _lange_koepfe(breiten, lang, sum(breiten) + 45.0) == (0, 2, 3)
    assert _lange_koepfe(breiten, lang, sum(breiten) + 14.0) == ()


def test_ein_hinterer_kopf_wird_lang_wenn_ein_vorderer_nicht_passt():
    breiten = [10.0, 100.0, 20.0]
    lang = {0: 50.0, 2: 30.0}  # +40, +10
    assert _lange_koepfe(breiten, lang, sum(breiten) + 20.0) == (2,)
