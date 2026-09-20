"""buecherlisten/planung: Mappe, Abgleich und die gerechneten Status - ohne Netz.

Die beiden Fragen, an denen diese Datei hängt:

1. **Überlebt Eingetragenes den Abgleich?** Eine Preisprüfung, eine Rücklage
   und eine Planungszeile müssen einen Abruf aus IServ überstehen - sonst wäre
   die Datei nach dem ersten „Aktualisieren" leer.
2. **Fällt auf, wenn sich etwas ändert?** Ein geänderter Preis muss die
   Prüfung kippen, ein neues Buch das Fach aus seiner Bestätigung werfen.
"""
from __future__ import annotations

from datetime import date

import pytest

from buecherlisten.planung import (
    FACH_BESTAETIGT,
    FACH_OFFEN,
    FACH_TEILWEISE,
    PLANUNG_AUSGEMUSTERT,
    PLANUNG_GEPLANT,
    PLANUNG_LAEUFT_AUS,
    PREIS_ABWEICHEND,
    PREIS_BESTAETIGT,
    PREIS_OFFEN,
    Buch,
    Buchplanung,
    Schnappschuss,
    UnbekanntesBuch,
    UngueltigeEingabe,
    bestaetige_fach,
    fach_status,
    lade_schnappschuss,
    lies_datei,
    planungs_status,
    preis_status,
    schreibe_datei,
    setze_planung,
    setze_preis,
    setze_preise_des_verlags,
    setze_ruecklage,
    zusammenfuehren,
)
from buecherlisten.planung.modelle import Planungszeile

DEUTSCH = "9783060000005"
TERRA = "9783121000562"
ALT = "9783120000009"
KAUF = "9783140000000"


def _buecher() -> tuple[Buch, ...]:
    return (
        Buch(isbn=DEUTSCH, titel="Deutschbuch 5", verlag="Cornelsen",
             kombinationen=(("Deutsch", 5),), leihbar=True,
             neupreis=22.5, leihgebuehr=5.0),
        # Ein Mehrjahresband in zwei Fächern: vier Zeilen auf "Fächer & Jahrgang".
        Buch(isbn=TERRA, titel="Terra 5/6", verlag="Klett",
             kombinationen=(("Erdkunde", 5), ("Erdkunde", 6),
                            ("Politik", 5), ("Politik", 6)),
             leihbar=True, neupreis=25.0, leihgebuehr=5.0),
        # Nur im Vorjahr und leihbar: das ist der Fall "ausgemustert", für den
        # eine Fachschaft Exemplare zurücklegen lassen möchte.
        Buch(isbn=ALT, titel="Chemie heute 9", verlag="Westermann",
             kombinationen=(("Chemie", 9),), leihbar=True, neupreis=30.0),
        # Kein Leihbuch: die Familien kaufen es selbst.
        Buch(isbn=KAUF, titel="Wörterbuch Latein", verlag="Langenscheidt",
             kombinationen=(("Latein", 7),), leihbar=False, neupreis=19.9),
    )


def _schnappschuss(buecher=None, **felder) -> Schnappschuss:
    return Schnappschuss(
        schuljahr=felder.pop("schuljahr", "2026/2027"),
        vorjahr=felder.pop("vorjahr", "2025/2026"),
        buecher=buecher if buecher is not None else _buecher(),
        stand=felder.pop("stand", date(2026, 9, 19)),
        **felder,
    )


@pytest.fixture()
def stand() -> Buchplanung:
    return zusammenfuehren(None, _schnappschuss())


# ── Der Aufbau der Datei ─────────────────────────────────────────────────────


def test_die_achsen_gruppieren_wie_erwartet(stand):
    # Jedes Buch hat genau einen Verlag, und jedes Buch der Datei bekommt einen
    # geprüften Preis - auch das ausgemusterte.
    assert stand.verlage == ("Cornelsen", "Klett", "Langenscheidt", "Westermann")
    # Ein Buch mit zwei Fächern steht in beiden.
    assert stand.faecher == ("Chemie", "Deutsch", "Erdkunde", "Latein", "Politik")
    assert [b.isbn for b in stand.buecher_je_fach("Politik")] == [TERRA]
    assert stand.jahrgaenge == (5, 6, 7, 9)
    # Die Paare, nicht das Kreuzprodukt: Terra steht viermal, nicht achtmal.
    assert stand.zeilen_des_buchs(stand.buch(TERRA)) == (
        ("Erdkunde", 5), ("Erdkunde", 6), ("Politik", 5), ("Politik", 6),
    )


def test_schreiben_und_lesen_ergibt_denselben_stand(tmp_path, stand):
    stand = setze_preis(stand, isbn=DEUTSCH, preis=22.5, kuerzel="MLR",
                        datum=date(2026, 9, 1))
    stand = setze_ruecklage(stand, isbn=ALT, fach="Chemie", anzahl=5,
                            kuerzel="FK", datum=date(2026, 9, 2),
                            bemerkung="für die Sammlung")
    stand = setze_planung(stand, isbn=ALT, fach="Chemie", jahrgang=9,
                          ausgemustert_nach="2026/2027", bemerkung="FK 12.05.2026")
    stand, _ = bestaetige_fach(stand, fach="Deutsch", kuerzel="ABC",
                               datum=date(2026, 9, 3))

    pfad = tmp_path / "Buchplanung.xlsx"
    schreibe_datei(pfad, stand)
    gelesen = lies_datei(pfad)

    assert gelesen.schuljahr == "2026/2027"
    assert gelesen.vorjahr == "2025/2026"
    assert gelesen.stand == date(2026, 9, 19)
    assert {b.isbn for b in gelesen.buecher} == {DEUTSCH, TERRA, ALT, KAUF}

    pruefung = gelesen.pruefung(DEUTSCH)
    assert (pruefung.preis, pruefung.kuerzel, pruefung.datum) == (22.5, "MLR", date(2026, 9, 1))
    ruecklage = gelesen.ruecklage(ALT, "Chemie")
    assert (ruecklage.anzahl, ruecklage.bemerkung) == (5, "für die Sammlung")
    zeile = gelesen.planungszeile(ALT, "Chemie", 9)
    assert (zeile.ausgemustert_nach, zeile.bemerkung) == ("2026/2027", "FK 12.05.2026")
    bestaetigt = gelesen.planungszeile(DEUTSCH, "Deutsch", 5)
    assert (bestaetigt.kuerzel, bestaetigt.datum) == ("ABC", date(2026, 9, 3))


def test_buecher_kommen_mit_ihren_kombinationen_zurueck(tmp_path, stand):
    pfad = tmp_path / "Buchplanung.xlsx"
    schreibe_datei(pfad, stand)
    gelesen = lies_datei(pfad)

    terra = gelesen.buch(TERRA)
    assert terra.faecher == ("Erdkunde", "Politik")
    assert terra.jahrgaenge == (5, 6)
    assert terra.jahrgaenge_im_fach("Politik") == (5, 6)
    assert terra.neupreis == 25.0
    assert terra.leihgebuehr == 5.0

    # Jedes Buch steht auf "Buchreihen" - auch das nur im Vorjahr geführte und
    # das Kaufbuch; die Preisprüfung gilt für beide.
    assert gelesen.buch(ALT).neupreis == 30.0
    assert gelesen.buch(KAUF).leihbar is False
    assert gelesen.buch(ALT).leihbar is True


def test_eine_planung_ohne_heutiges_vorkommen_bleibt_erhalten(tmp_path, stand):
    """Einführung in einen Jahrgang, den das Buch noch gar nicht führt."""
    stand = setze_planung(stand, isbn=DEUTSCH, fach="Deutsch", jahrgang=7,
                          eingefuehrt_ab="2028/2029")
    pfad = tmp_path / "Buchplanung.xlsx"
    schreibe_datei(pfad, stand)
    gelesen = lies_datei(pfad)

    zeile = gelesen.planungszeile(DEUTSCH, "Deutsch", 7)
    assert zeile.eingefuehrt_ab == "2028/2029"
    assert planungs_status(zeile, gelesen.schuljahr) == PLANUNG_GEPLANT


def test_von_hand_geaenderter_mitgefuehrter_wert_wirkt_nicht_zurueck(tmp_path, stand):
    """Wer den Titel auf "Buchreihen" überschreibt, ändert nichts an der Wahrheit."""
    from openpyxl import load_workbook

    pfad = tmp_path / "Buchplanung.xlsx"
    schreibe_datei(pfad, stand)

    wb = load_workbook(str(pfad))
    ws = wb["Buchreihen"]
    ws.cell(2, 1).value = "Von Hand verbogen"
    wb.save(str(pfad))

    # Der nächste Abgleich holt den Titel aus IServ zurück.
    neu = zusammenfuehren(lies_datei(pfad), _schnappschuss())
    assert "Von Hand verbogen" not in {b.titel for b in neu.buecher}


def test_die_alten_blaetter_verschwinden(tmp_path, stand):
    """Eine Datei des Aufbaus bis 2026-09-20 behält keine zweite Bücherliste."""
    from openpyxl import Workbook

    pfad = tmp_path / "Buchplanung.xlsx"
    wb = Workbook()
    wb.worksheets[0].title = "Preise je Verlag"
    for name in ("Bücher je Fach", "Bücher je Jahrgang", "Fachbestätigung"):
        wb.create_sheet(name)
    wb.save(str(pfad))

    schreibe_datei(pfad, stand)

    from openpyxl import load_workbook
    assert load_workbook(str(pfad)).sheetnames == [
        "Buchreihen", "Fächer & Jahrgang", "Rücklage", "Info",
    ]


# ── Der Abgleich ─────────────────────────────────────────────────────────────


def test_eintragungen_ueberleben_den_abgleich(stand):
    stand = setze_preis(stand, isbn=DEUTSCH, preis=22.5, kuerzel="MLR", datum=date(2026, 9, 1))
    stand = setze_ruecklage(stand, isbn=ALT, fach="Chemie", anzahl=5)
    stand = setze_planung(stand, isbn=TERRA, fach="Erdkunde", jahrgang=7,
                          eingefuehrt_ab="2027/2028")
    stand, _ = bestaetige_fach(stand, fach="Deutsch", kuerzel="ABC", datum=None)

    neu = zusammenfuehren(stand, _schnappschuss())

    assert neu.pruefung(DEUTSCH).preis == 22.5
    assert neu.ruecklage(ALT, "Chemie").anzahl == 5
    assert neu.planungszeile(TERRA, "Erdkunde", 7).eingefuehrt_ab == "2027/2028"
    assert neu.planungszeile(DEUTSCH, "Deutsch", 5).kuerzel == "ABC"


def test_verschwundenes_buch_wird_verworfen_aber_gemeldet(stand):
    stand = setze_preis(stand, isbn=ALT, preis=30.0, kuerzel="MLR", datum=None)
    ohne_alt = tuple(b for b in _buecher() if b.isbn != ALT)

    neu = zusammenfuehren(stand, _schnappschuss(ohne_alt))

    assert neu.pruefung(ALT) is None
    assert any(ALT in warnung for warnung in neu.warnungen)


def test_fehlendes_vorjahr_ist_kein_fehler_sondern_eine_warnung(stand):
    neu = zusammenfuehren(stand, _schnappschuss(warnungen=("Das Vorjahr fehlt.",)))
    assert "Das Vorjahr fehlt." in neu.warnungen


# ── Die gerechneten Status ───────────────────────────────────────────────────


def test_preisstatus_kippt_wenn_iserv_den_preis_aendert(stand):
    stand = setze_preis(stand, isbn=DEUTSCH, preis=22.5, kuerzel="MLR", datum=None)
    buch = stand.buch(DEUTSCH)
    assert preis_status(buch, stand.pruefung(DEUTSCH))[0] == PREIS_BESTAETIGT

    teurer = tuple(
        b if b.isbn != DEUTSCH else Buch(**{**b.__dict__, "neupreis": 24.9})
        for b in _buecher()
    )
    neu = zusammenfuehren(stand, _schnappschuss(teurer))
    status, hinweis = preis_status(neu.buch(DEUTSCH), neu.pruefung(DEUTSCH))
    assert status == PREIS_ABWEICHEND
    assert "22,50" in hinweis and "24,90" in hinweis


def test_neues_buch_steht_von_allein_auf_offen(stand):
    stand = setze_preise_des_verlags(stand, verlag="Cornelsen", kuerzel="MLR", datum=None)[0]
    zusaetzlich = _buecher() + (
        Buch(isbn="9783060000012", titel="Deutschbuch 6", verlag="Cornelsen",
             kombinationen=(("Deutsch", 6),), leihbar=True, neupreis=23.0),
    )
    neu = zusammenfuehren(stand, _schnappschuss(zusaetzlich))

    assert preis_status(neu.buch(DEUTSCH), neu.pruefung(DEUTSCH))[0] == PREIS_BESTAETIGT
    assert preis_status(neu.buch("9783060000012"), neu.pruefung("9783060000012"))[0] == PREIS_OFFEN
    assert any("geprüften Preis" in warnung for warnung in neu.warnungen)


def test_ganze_verlagsliste_auf_einmal(stand):
    neu, anzahl = setze_preise_des_verlags(stand, verlag="Westermann", kuerzel="MLR",
                                           datum=date(2026, 9, 5))
    assert anzahl == 1
    assert neu.pruefung(ALT).preis == 30.0
    assert neu.pruefung(ALT).kuerzel == "MLR"
    assert neu.pruefung(DEUTSCH) is None


def test_ein_neues_buch_wirft_das_fach_aus_seiner_bestaetigung(stand):
    stand, anzahl = bestaetige_fach(stand, fach="Deutsch", kuerzel="ABC", datum=None)
    assert anzahl == 1
    assert fach_status(stand, "Deutsch")[0] == FACH_BESTAETIGT

    zusaetzlich = _buecher() + (
        Buch(isbn="9783060000012", titel="Deutschbuch 6", verlag="Cornelsen",
             kombinationen=(("Deutsch", 6),), leihbar=True, neupreis=23.0),
    )
    neu = zusammenfuehren(stand, _schnappschuss(zusaetzlich))
    status, hinweis = fach_status(neu, "Deutsch")
    assert status == FACH_TEILWEISE
    assert "Deutschbuch 6 (Jg. 6)" in hinweis


def test_bestaetigung_gilt_nur_dem_eigenen_fach(stand):
    """Terra steht in Erdkunde und Politik - Erdkunde bestätigt nicht für Politik."""
    stand, anzahl = bestaetige_fach(stand, fach="Erdkunde", kuerzel="ABC", datum=None)
    assert anzahl == 2
    assert fach_status(stand, "Erdkunde")[0] == FACH_BESTAETIGT
    assert fach_status(stand, "Politik")[0] == FACH_OFFEN


def test_leeres_kuerzel_nimmt_die_bestaetigung_zurueck(stand):
    stand, _ = bestaetige_fach(stand, fach="Deutsch", kuerzel="ABC", datum=None)
    zurueck, _ = bestaetige_fach(stand, fach="Deutsch", kuerzel="", datum=None)
    assert fach_status(zurueck, "Deutsch")[0] == FACH_OFFEN
    assert zurueck.planungszeile(DEUTSCH, "Deutsch", 5) is None


def test_fach_ohne_bestaetigung_ist_offen(stand):
    assert fach_status(stand, "Erdkunde")[0] == FACH_OFFEN


@pytest.mark.parametrize(("zeile", "erwartet"), [
    (Planungszeile(isbn=DEUTSCH, fach="Deutsch", jahrgang=5,
                   eingefuehrt_ab="2028/2029"), PLANUNG_GEPLANT),
    (Planungszeile(isbn=DEUTSCH, fach="Deutsch", jahrgang=5,
                   ausgemustert_nach="2026/2027"), PLANUNG_LAEUFT_AUS),
    (Planungszeile(isbn=DEUTSCH, fach="Deutsch", jahrgang=5,
                   ausgemustert_nach="2025/2026"), PLANUNG_AUSGEMUSTERT),
])
def test_planungsstatus_wird_gegen_das_schuljahr_gerechnet(zeile, erwartet):
    assert planungs_status(zeile, "2026/2027") == erwartet


# ── Was nicht eingetragen werden darf ────────────────────────────────────────


def test_unbekannte_isbn_wird_abgelehnt(stand):
    with pytest.raises(UnbekanntesBuch):
        setze_preis(stand, isbn="9780000000000", preis=1.0, kuerzel="MLR", datum=None)


def test_ausmusterung_vor_der_einfuehrung_wird_abgelehnt(stand):
    with pytest.raises(UngueltigeEingabe):
        setze_planung(stand, isbn=DEUTSCH, fach="Deutsch", jahrgang=5,
                      eingefuehrt_ab="2027/2028", ausgemustert_nach="2026/2027")


def test_ein_kaufbuch_wird_nicht_ausgemustert(stand):
    with pytest.raises(UngueltigeEingabe, match="kein Leihbuch"):
        setze_planung(stand, isbn=KAUF, fach="Latein", jahrgang=7,
                      ausgemustert_nach="2026/2027")
    # Die Einführung darf es trotzdem haben: eingeführt wird auch, was gekauft wird.
    neu = setze_planung(stand, isbn=KAUF, fach="Latein", jahrgang=7,
                        eingefuehrt_ab="2027/2028")
    assert neu.planungszeile(KAUF, "Latein", 7).eingefuehrt_ab == "2027/2028"


def test_schuljahr_ohne_schraegstrich_wird_abgelehnt(stand):
    with pytest.raises(UngueltigeEingabe):
        setze_planung(stand, isbn=DEUTSCH, fach="Deutsch", jahrgang=5,
                      eingefuehrt_ab="2027")


def test_planung_fuer_ein_fremdes_fach_wird_abgelehnt(stand):
    with pytest.raises(UngueltigeEingabe):
        setze_planung(stand, isbn=DEUTSCH, fach="Chemie", jahrgang=5,
                      eingefuehrt_ab="2027/2028")


def test_ruecklage_fuer_ein_fremdes_fach_wird_abgelehnt(stand):
    with pytest.raises(UngueltigeEingabe):
        setze_ruecklage(stand, isbn=DEUTSCH, fach="Chemie", anzahl=3)


def test_ruecklage_bekommt_ohne_angabe_den_status_gewuenscht(stand):
    neu = setze_ruecklage(stand, isbn=ALT, fach="Chemie", anzahl=4)
    assert neu.ruecklage(ALT, "Chemie").status == "gewünscht"


# ── Laden aus IServ ──────────────────────────────────────────────────────────


class _ZweiJahre:
    """Ein IServ, in dem sich das Vorjahr vom laufenden Jahr unterscheidet."""

    # (ISBN, Titel, Fächer, Preis, leihbar)
    LISTEN = {
        "2026/2027": {5: [(DEUTSCH, "Deutschbuch 5", ["Deutsch"], 22.5, True)]},
        "2025/2026": {5: [(DEUTSCH, "Deutschbuch 5", ["Deutsch"], 21.0, True)],
                      9: [(ALT, "Chemie heute 9", ["Chemie"], 30.0, True),
                          (KAUF, "Wörterbuch Latein", ["Latein"], 19.9, False)]},
    }

    class _Schuljahre:
        # Kennung und Anzeigename sind verschieden - wie im echten IServ.
        def get_current(self):
            return {"id": "2026/2027", "name": "Schuljahr 26/27"}

        def get_by_id(self, kennung):
            return {"id": kennung, "name": "Schuljahr 26/27"}

        def get_booklists(self, kennung):
            if kennung not in _ZweiJahre.LISTEN:
                raise LookupError(f"Schuljahr {kennung} gibt es nicht.")
            return [{"id": 100 + g, "grade": g} for g in sorted(_ZweiJahre.LISTEN[kennung])]

        def get_booklist(self, kennung, listen_id):
            grade = listen_id - 100
            return {"sections": [{"options": [{"items": [
                {"borrowable": leihbar, "series": isbn,
                 "series_data": {"isbn": isbn, "title": titel, "subjectsFlat": faecher,
                                 "publisher": "Cornelsen", "price": preis, "fee": 5.0}}
                for isbn, titel, faecher, preis, leihbar in _ZweiJahre.LISTEN[kennung][grade]
            ]}]}]}

    def __init__(self):
        self.schoolyears = self._Schuljahre()


def test_schnappschuss_legt_beide_schuljahre_uebereinander():
    schnappschuss = lade_schnappschuss(_ZweiJahre(), heute=date(2026, 9, 19))

    # Die Kennung, nicht der Name: mit ihr adressiert IServ das Schuljahr, und
    # nur sie lässt sich mit "Einführung" und "Ausmusterung" vergleichen.
    assert schnappschuss.schuljahr == "2026/2027"
    assert schnappschuss.name == "Schuljahr 26/27"
    assert schnappschuss.vorjahr == "2025/2026"
    je_isbn = {buch.isbn: buch for buch in schnappschuss.buecher}
    assert je_isbn[DEUTSCH].kombinationen == (("Deutsch", 5),)
    # Leihbar und nur im Vorjahr: bleibt in der Datei, es liegt im Bestand.
    assert je_isbn[ALT].kombinationen == (("Chemie", 9),)
    # Kein Leihbuch und aus der Liste verschwunden: nichts mehr zu planen.
    assert KAUF not in je_isbn
    assert not schnappschuss.warnungen


def test_fehlendes_vorjahr_bricht_den_abruf_nicht_ab():
    schnappschuss = lade_schnappschuss(_ZweiJahre(), vorjahr="2019/2020",
                                       heute=date(2026, 9, 19))
    assert {b.isbn for b in schnappschuss.buecher} == {DEUTSCH}
    assert any("2019/2020" in warnung for warnung in schnappschuss.warnungen)
