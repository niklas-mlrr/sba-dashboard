"""buecherlisten/planung: Mappe, Abgleich und die gerechneten Status - ohne Netz.

Die beiden Fragen, an denen diese Datei hängt:

1. **Überlebt Eingetragenes den Abgleich?** Eine Bemerkung, eine Rücklage
   und eine Planungszeile müssen einen Abruf aus IServ überstehen - sonst wäre
   die Datei nach dem ersten „Aktualisieren" leer.
2. **Fällt auf, wenn sich etwas ändert?** Ein neues Buch muss das Fach aus
   seiner Bestätigung werfen.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from buecherlisten.planung import (
    FACH_BESTAETIGT,
    FACH_OFFEN,
    FACH_TEILWEISE,
    PLANUNG_AUSGEMUSTERT,
    PLANUNG_GEPLANT,
    PLANUNG_LAEUFT_AUS,
    Buch,
    Buchplanung,
    Buchreiheneingabe,
    Jahrgangseingabe,
    Ruecklageneingabe,
    Schnappschuss,
    UnbekanntesBuch,
    UngueltigeEingabe,
    bestaetige_fach,
    fach_status,
    fuege_buch_hinzu,
    lade_schnappschuss,
    lies_datei,
    planungs_status,
    schreibe_datei,
    setze_buchplanung,
    setze_buchreihe,
    setze_planung,
    setze_ruecklage,
    wirkt_im_schuljahr,
    zusammenfuehren,
)
from buecherlisten.planung.modelle import Buchbemerkung, Planungszeile

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


def _mit_bemerkung(stand, isbn, text):
    return replace(stand, bemerkungen=stand.bemerkungen + (Buchbemerkung(isbn, text),))


# ── Der Aufbau der Datei ─────────────────────────────────────────────────────


def test_die_achsen_gruppieren_wie_erwartet(stand):
    # Jedes Buch hat genau einen Verlag.
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
    stand = _mit_bemerkung(stand, DEUTSCH, "Preis beim Verlag erfragt")
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

    assert gelesen.bemerkung(DEUTSCH).bemerkung == "Preis beim Verlag erfragt"
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
    # das Kaufbuch.
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
    # Der geplante Jahrgang wird dadurch **kein** Vorkommen: das Buch steht in
    # Jahrgang 7 in keiner Bücherliste. Daran hängt, dass das Planungsmenü die
    # Einführung dort noch ändern lässt (Spalte "in der Bücherliste").
    assert gelesen.buch(DEUTSCH).jahrgaenge == (5,)
    assert gelesen.zeilen_des_buchs(gelesen.buch(DEUTSCH)) == (("Deutsch", 5), ("Deutsch", 7))


def test_eine_geleerte_planungszeile_kommt_nicht_als_leere_zeile_zurueck(tmp_path, stand):
    """Sonst ließe sich ein versehentlich angelegter Jahrgang nie mehr loswerden."""
    stand = setze_planung(stand, isbn=DEUTSCH, fach="Deutsch", jahrgang=7,
                          eingefuehrt_ab="2028/2029")
    pfad = tmp_path / "Buchplanung.xlsx"
    schreibe_datei(pfad, stand)

    geleert = setze_planung(lies_datei(pfad), isbn=DEUTSCH, fach="Deutsch", jahrgang=7)
    schreibe_datei(pfad, geleert)
    gelesen = lies_datei(pfad)

    assert gelesen.planungszeile(DEUTSCH, "Deutsch", 7) is None
    assert gelesen.zeilen_des_buchs(gelesen.buch(DEUTSCH)) == (("Deutsch", 5),)


def test_in_excel_geaenderter_titel_ist_das_soll(tmp_path, stand):
    """Die Datei ist das Soll: ein in Excel überschriebener Titel bleibt stehen."""
    from openpyxl import load_workbook

    pfad = tmp_path / "Buchplanung.xlsx"
    schreibe_datei(pfad, stand)

    wb = load_workbook(str(pfad))
    ws = wb["Buchreihen"]
    ws.cell(2, 1).value = "Von Hand verbogen"
    wb.save(str(pfad))

    # Der nächste Abgleich lässt ihn stehen und merkt sich, was IServ sagt.
    neu = zusammenfuehren(lies_datei(pfad), _schnappschuss())
    buch = next(b for b in neu.buecher if b.titel == "Von Hand verbogen")
    assert buch.korrigiert == {"titel": stand.buch(buch.isbn).titel}


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
    stand = _mit_bemerkung(stand, DEUTSCH, "Preis beim Verlag erfragt")
    stand = setze_ruecklage(stand, isbn=ALT, fach="Chemie", anzahl=5)
    stand = setze_planung(stand, isbn=TERRA, fach="Erdkunde", jahrgang=7,
                          eingefuehrt_ab="2027/2028")
    stand, _ = bestaetige_fach(stand, fach="Deutsch", kuerzel="ABC", datum=None)

    neu = zusammenfuehren(stand, _schnappschuss())

    assert neu.bemerkung(DEUTSCH).bemerkung == "Preis beim Verlag erfragt"
    assert neu.ruecklage(ALT, "Chemie").anzahl == 5
    assert neu.planungszeile(TERRA, "Erdkunde", 7).eingefuehrt_ab == "2027/2028"
    assert neu.planungszeile(DEUTSCH, "Deutsch", 5).kuerzel == "ABC"


def test_ein_aus_iserv_verschwundenes_buch_bleibt_in_der_datei(stand):
    """Verschwindet ein Buch aus IServ, ist das eine Abweichung - kein Aufräumen."""
    stand = _mit_bemerkung(stand, ALT, "läuft aus")
    stand = setze_ruecklage(stand, isbn=ALT, fach="Chemie", anzahl=5)
    ohne_alt = tuple(b for b in _buecher() if b.isbn != ALT)

    neu = zusammenfuehren(stand, _schnappschuss(ohne_alt))

    assert neu.buch(ALT) == stand.buch(ALT)
    assert neu.bemerkung(ALT).bemerkung == "läuft aus"
    assert neu.ruecklage(ALT, "Chemie").anzahl == 5
    assert not neu.warnungen


def test_ein_neues_buch_aus_iserv_wird_aufgenommen(stand):
    dazu = Buch(isbn=NEU, titel="Neu 7", verlag="Klett", kombinationen=(("Deutsch", 7),))
    neu = zusammenfuehren(stand, _schnappschuss(_buecher() + (dazu,)))
    assert neu.buch(NEU) == dazu


def test_faecher_und_jahrgaenge_bleiben_die_der_datei(stand):
    """Ein neuer Jahrgang in IServ wird markiert, nicht übernommen - und ein
    weggefallener nicht still ausgemustert."""
    anders = tuple(replace(b, kombinationen=(("Deutsch", 6),), ausgemustert=(("Deutsch", 5),))
                   if b.isbn == DEUTSCH else b for b in _buecher())
    neu = zusammenfuehren(stand, _schnappschuss(anders))
    assert neu.buch(DEUTSCH).kombinationen == (("Deutsch", 5),)
    assert neu.planungszeile(DEUTSCH, "Deutsch", 5) is None


def test_fehlendes_vorjahr_ist_kein_fehler_sondern_eine_warnung(stand):
    neu = zusammenfuehren(stand, _schnappschuss(warnungen=("Das Vorjahr fehlt.",)))
    assert "Das Vorjahr fehlt." in neu.warnungen


# ── Die gerechneten Status ───────────────────────────────────────────────────


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


@pytest.mark.parametrize(("zeile", "erwartet"), [
    (None, True),                                                        # im Einsatz
    (Planungszeile(isbn=DEUTSCH, fach="Deutsch", jahrgang=5,
                   ausgemustert_nach="2029/2030"), True),                # läuft aus
    (Planungszeile(isbn=DEUTSCH, fach="Deutsch", jahrgang=5,
                   eingefuehrt_ab="2028/2029"), False),                  # geplant
    (Planungszeile(isbn=DEUTSCH, fach="Deutsch", jahrgang=5,
                   ausgemustert_nach="2025/2026"), False),               # ausgemustert
])
def test_wirkt_im_schuljahr_trennt_da_von_nicht_da(zeile, erwartet):
    """"läuft aus" heißt: dieses Jahr noch da, ausgemustert wird erst danach."""
    assert wirkt_im_schuljahr(zeile, "2026/2027") is erwartet


# ── Das Planungsmenü: alle Zeilen eines Buchs in einem Fach ──────────────────


def test_setze_buchplanung_schreibt_mehrere_jahrgaenge_und_entfernt_fehlende(stand):
    neu = setze_buchplanung(stand, isbn=DEUTSCH, fach="Deutsch", zeilen=[
        Jahrgangseingabe(jahrgang=5, ausgemustert_nach="2029/2030", bemerkung="FK"),
        Jahrgangseingabe(jahrgang=7, eingefuehrt_ab="2028/2029"),
        Jahrgangseingabe(jahrgang=8, eingefuehrt_ab="2029/2030"),
    ], ruecklage=Ruecklageneingabe(anzahl=4, bemerkung="für die Sammlung"))
    assert neu.planungszeile(DEUTSCH, "Deutsch", 5).ausgemustert_nach == "2029/2030"
    assert neu.planungszeile(DEUTSCH, "Deutsch", 8).eingefuehrt_ab == "2029/2030"
    assert neu.ruecklage(DEUTSCH, "Deutsch").anzahl == 4

    # Jahrgang 8 nicht mehr mitgeschickt: das Menü zeigt den ganzen Stand, also
    # heißt "fehlt" hier "gelöscht".
    ohne = setze_buchplanung(neu, isbn=DEUTSCH, fach="Deutsch", zeilen=[
        Jahrgangseingabe(jahrgang=5, ausgemustert_nach="2029/2030"),
        Jahrgangseingabe(jahrgang=7, eingefuehrt_ab="2028/2029"),
    ])
    assert ohne.planungszeile(DEUTSCH, "Deutsch", 8) is None


def test_derselbe_jahrgang_zweimal_wird_abgelehnt(stand):
    with pytest.raises(UngueltigeEingabe, match="zweimal"):
        setze_buchplanung(stand, isbn=DEUTSCH, fach="Deutsch", zeilen=[
            Jahrgangseingabe(jahrgang=7, eingefuehrt_ab="2028/2029"),
            Jahrgangseingabe(jahrgang=7, eingefuehrt_ab="2029/2030"),
        ])


def test_bestaetigung_bleibt_bei_einer_aenderung_fuer_ein_kuenftiges_jahr(stand):
    """Was erst 2029 greift, ändert die Liste nicht, die 2026 bestätigt wurde."""
    stand, _ = bestaetige_fach(stand, fach="Deutsch", kuerzel="ABC", datum=date(2026, 9, 3))
    neu = setze_buchplanung(stand, isbn=DEUTSCH, fach="Deutsch", zeilen=[
        Jahrgangseingabe(jahrgang=5, ausgemustert_nach="2029/2030"),
    ])
    zeile = neu.planungszeile(DEUTSCH, "Deutsch", 5)
    assert (zeile.kuerzel, zeile.datum) == ("ABC", date(2026, 9, 3))
    assert fach_status(neu, "Deutsch")[0] == FACH_BESTAETIGT


@pytest.mark.parametrize("eingabe", [
    # Ab sofort weg …
    Jahrgangseingabe(jahrgang=5, ausgemustert_nach="2025/2026"),
    # … und ab sofort erst geplant: beides ändert die Liste dieses Schuljahrs.
    Jahrgangseingabe(jahrgang=5, eingefuehrt_ab="2028/2029"),
])
def test_bestaetigung_faellt_weg_wenn_sich_das_laufende_schuljahr_aendert(stand, eingabe):
    stand, _ = bestaetige_fach(stand, fach="Deutsch", kuerzel="ABC", datum=date(2026, 9, 3))
    neu = setze_buchplanung(stand, isbn=DEUTSCH, fach="Deutsch", zeilen=[eingabe])
    zeile = neu.planungszeile(DEUTSCH, "Deutsch", 5)
    assert (zeile.kuerzel, zeile.datum) == ("", None)
    assert fach_status(neu, "Deutsch")[0] == FACH_OFFEN


def test_das_menue_weist_ein_fremdes_fach_ab(stand):
    with pytest.raises(UngueltigeEingabe, match="gehört nicht zum Fach"):
        setze_buchplanung(stand, isbn=DEUTSCH, fach="Chemie",
                          zeilen=[Jahrgangseingabe(jahrgang=5)])


# ── Was nicht eingetragen werden darf ────────────────────────────────────────


def test_unbekannte_isbn_wird_abgelehnt(stand):
    with pytest.raises(UnbekanntesBuch):
        setze_planung(stand, isbn="9780000000000", fach="Deutsch", jahrgang=5,
                      eingefuehrt_ab="2027/2028")


def test_ausmusterung_vor_der_einfuehrung_wird_abgelehnt(stand):
    with pytest.raises(UngueltigeEingabe):
        setze_planung(stand, isbn=DEUTSCH, fach="Deutsch", jahrgang=5,
                      eingefuehrt_ab="2027/2028", ausgemustert_nach="2026/2027")


def test_auch_ein_kaufbuch_wird_eingefuehrt_und_ausgemustert(stand):
    """Ausgemustert wird die Bücherliste, nicht der Bestand der Schule.

    Bis 2026-09-20 wies ``setze_planung`` die Ausmusterung eines Kaufbuchs ab.
    Das verwechselte zwei Dinge: auch ein Buch, das die Familien selbst kaufen,
    steht bis zu einem Schuljahr auf der Liste und danach nicht mehr.
    """
    neu = setze_planung(stand, isbn=KAUF, fach="Latein", jahrgang=7,
                        eingefuehrt_ab="2024/2025", ausgemustert_nach="2026/2027")
    zeile = neu.planungszeile(KAUF, "Latein", 7)
    assert (zeile.eingefuehrt_ab, zeile.ausgemustert_nach) == ("2024/2025", "2026/2027")
    assert planungs_status(zeile, neu.schuljahr) == PLANUNG_LAEUFT_AUS


def test_fuer_ein_kaufbuch_gibt_es_keine_ruecklage(stand):
    """Was die Schule nie besessen hat, kann sie nicht zurücklegen."""
    with pytest.raises(UngueltigeEingabe, match="lässt sich nichts zurücklegen"):
        setze_ruecklage(stand, isbn=KAUF, fach="Latein", anzahl=3)


def test_eine_leere_ruecklage_bleibt_auch_beim_kaufbuch_erlaubt(stand):
    """Sonst ließe sich ein Wunsch von vor dieser Regel nie wieder löschen."""
    assert setze_ruecklage(stand, isbn=KAUF, fach="Latein", anzahl=None) is not None


def test_ein_ehemals_leihbares_buch_darf_eine_ruecklage_haben(stand):
    """ALT kommt nur noch im Vorjahr vor - genau dafür gibt es die Rücklage."""
    neu = setze_ruecklage(stand, isbn=ALT, fach="Chemie", anzahl=5)
    assert neu.ruecklage(ALT, "Chemie").anzahl == 5


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


# ── Korrekturen an der Buchreihe ─────────────────────────────────────────────


def _reihe(buch: Buch, **felder) -> Buchreiheneingabe:
    return Buchreiheneingabe(**{
        "titel": buch.titel, "verlag": buch.verlag,
        "neupreis": buch.neupreis, "leihgebuehr": buch.leihgebuehr, **felder,
    })


def test_titel_und_preis_werden_korrigiert(stand):
    buch = stand.buch(DEUTSCH)
    neu = setze_buchreihe(stand, isbn=DEUTSCH,
                          eingabe=_reihe(buch, titel="Deutschbuch 5 (NRW)", neupreis=24.0))

    korrigiert = neu.buch(DEUTSCH)
    assert korrigiert.titel == "Deutschbuch 5 (NRW)"
    assert korrigiert.neupreis == 24.0
    # Die Datei merkt sich, was IServ sagt - nur zu den korrigierten Feldern.
    assert korrigiert.korrigiert == {"titel": "Deutschbuch 5", "neupreis": 22.5}
    assert neu.korrekturen_fuer_iserv() == {
        DEUTSCH: {"title": "Deutschbuch 5 (NRW)", "price": 24.0}}


def test_zurueck_auf_den_iserv_wert_nimmt_die_korrektur_zurueck(stand):
    buch = stand.buch(DEUTSCH)
    korrigiert = setze_buchreihe(stand, isbn=DEUTSCH,
                                 eingabe=_reihe(buch, verlag="Cornelsen Verlag"))
    assert korrigiert.buch(DEUTSCH).korrigiert == {"verlag": "Cornelsen"}

    zurueck = setze_buchreihe(korrigiert, isbn=DEUTSCH,
                              eingabe=_reihe(korrigiert.buch(DEUTSCH), verlag="Cornelsen"))
    assert zurueck.buch(DEUTSCH) == buch


def test_eine_zweite_korrektur_behaelt_den_iserv_wert(stand):
    """Der IServ-Wert ist der vom ersten Mal - nicht die vorige Korrektur."""
    buch = stand.buch(DEUTSCH)
    einmal = setze_buchreihe(stand, isbn=DEUTSCH, eingabe=_reihe(buch, neupreis=24.0))
    zweimal = setze_buchreihe(einmal, isbn=DEUTSCH,
                              eingabe=_reihe(einmal.buch(DEUTSCH), neupreis=26.0))
    assert zweimal.buch(DEUTSCH).korrigiert == {"neupreis": 22.5}
    assert zweimal.buch(DEUTSCH).neupreis == 26.0


def test_ein_leerer_preis_gilt_wie_in_iserv(stand):
    buch = stand.buch(DEUTSCH)
    korrigiert = setze_buchreihe(stand, isbn=DEUTSCH, eingabe=_reihe(buch, leihgebuehr=7.0))
    zurueck = setze_buchreihe(korrigiert, isbn=DEUTSCH,
                              eingabe=_reihe(korrigiert.buch(DEUTSCH), leihgebuehr=None))
    assert zurueck.buch(DEUTSCH).korrigiert == {}
    assert zurueck.buch(DEUTSCH).leihgebuehr == 5.0


@pytest.mark.parametrize("felder, teil", [
    ({"titel": "  "}, "Titel"),
    ({"verlag": ""}, "Verlag"),
    ({"neupreis": -1.0}, "Neupreis"),
])
def test_ungueltige_buchreihe_wird_abgelehnt(stand, felder, teil):
    buch = stand.buch(DEUTSCH)
    with pytest.raises(UngueltigeEingabe, match=teil):
        setze_buchreihe(stand, isbn=DEUTSCH, eingabe=_reihe(buch, **felder))


def test_korrekturen_stehen_auf_buchreihen_mit_dem_iserv_wert_als_kommentar(tmp_path, stand):
    from openpyxl import load_workbook

    buch = stand.buch(ALT)
    stand = setze_buchreihe(stand, isbn=ALT,
                            eingabe=_reihe(buch, verlag="Westermann Schulbuch", neupreis=31.0))
    pfad = tmp_path / "Buchplanung.xlsx"
    schreibe_datei(pfad, stand)

    wb = load_workbook(str(pfad))
    # Kein eigenes Blatt: die Korrektur steht in der Zeile des Buchs.
    assert "Korrekturen" not in wb.sheetnames
    ws = wb["Buchreihen"]
    kopf = {ws.cell(1, s).value: s for s in range(1, ws.max_column + 1)}
    (zeile,) = [z for z in range(2, ws.max_row + 1) if ws.cell(z, kopf["ISBN"]).value == ALT]
    assert ws.cell(zeile, kopf["Verlag"]).value == "Westermann Schulbuch"
    assert ws.cell(zeile, kopf["Verlag"]).comment.text == "in IServ: Westermann"
    assert ws.cell(zeile, kopf["Neupreis"]).comment.text == "in IServ: 30,00 €"
    assert ws.cell(zeile, kopf["Titel"]).comment is None

    gelesen = lies_datei(pfad).buch(ALT)
    assert gelesen.verlag == "Westermann Schulbuch"
    assert gelesen.korrigiert == {"verlag": "Westermann", "neupreis": 30.0}


def test_ein_von_excel_ergaenzter_kommentar_wird_trotzdem_gelesen(tmp_path, stand):
    """Excel setzt beim Bearbeiten den Namen des Bearbeiters vor den Kommentar."""
    from openpyxl import load_workbook
    from openpyxl.comments import Comment

    stand = setze_buchreihe(stand, isbn=ALT, eingabe=_reihe(stand.buch(ALT), titel="Chemie 9"))
    pfad = tmp_path / "Buchplanung.xlsx"
    schreibe_datei(pfad, stand)
    wb = load_workbook(str(pfad))
    ws = wb["Buchreihen"]
    for zeile in range(2, ws.max_row + 1):
        if ws.cell(zeile, 1).value == "Chemie 9":
            ws.cell(zeile, 1).comment = Comment("Frau Muster:\nin IServ: Chemie heute 9", "x")
    wb.save(str(pfad))

    assert lies_datei(pfad).buch(ALT).korrigiert == {"titel": "Chemie heute 9"}


def test_der_abgleich_behaelt_korrekturen_und_nimmt_den_frischen_iserv_wert(stand):
    stand = setze_buchreihe(stand, isbn=DEUTSCH, eingabe=_reihe(
        stand.buch(DEUTSCH), titel="Deutschbuch 5 NRW", neupreis=24.0))

    # In IServ ist inzwischen der Preis gestiegen - auf genau den korrigierten.
    frisch = tuple(replace(b, neupreis=24.0) if b.isbn == DEUTSCH else b for b in _buecher())
    neu = zusammenfuehren(stand, _schnappschuss(frisch))

    buch = neu.buch(DEUTSCH)
    assert buch.titel == "Deutschbuch 5 NRW"
    # Die Preiskorrektur ist erledigt: IServ nennt den Wert selbst.
    assert buch.korrigiert == {"titel": "Deutschbuch 5"}
    assert buch.neupreis == 24.0


def test_eine_preisaenderung_in_iserv_aendert_das_soll_nicht(stand):
    """Der Preis der Datei bleibt; der neue IServ-Preis steht als Abweichung daneben."""
    frisch = tuple(replace(b, neupreis=23.9) if b.isbn == DEUTSCH else b for b in _buecher())
    buch = zusammenfuehren(stand, _schnappschuss(frisch)).buch(DEUTSCH)
    assert buch.neupreis == 22.5
    assert buch.korrigiert == {"neupreis": 23.9}


def test_die_alte_korrekturen_mappe_verliert_ihr_blatt(tmp_path, stand):
    """Das Blatt "Korrekturen" gab es nur am 2026-09-24 für einige Stunden."""
    from openpyxl import load_workbook

    pfad = tmp_path / "Buchplanung.xlsx"
    schreibe_datei(pfad, stand)
    wb = load_workbook(str(pfad))
    wb.create_sheet("Korrekturen")
    wb.save(str(pfad))

    schreibe_datei(pfad, lies_datei(pfad))
    assert "Korrekturen" not in load_workbook(str(pfad)).sheetnames


# ── Ein Buch in ein Fach aufnehmen ───────────────────────────────────────────

NEU = "9783161484100"


def _einfuehrung(*jahrgaenge: int, ab: str = "2027/2028") -> list[Jahrgangseingabe]:
    return [Jahrgangseingabe(jahrgang=j, eingefuehrt_ab=ab) for j in jahrgaenge]


def test_ein_buch_aus_einem_anderen_fach_kommt_ueber_seine_jahrgaenge_dazu(stand):
    terra = stand.buch(TERRA)
    neu = fuege_buch_hinzu(stand, isbn="978-3-12-100056-2", fach="Deutsch",
                           buchreihe=_reihe(terra), zeilen=_einfuehrung(7, 8))

    assert [b.isbn for b in neu.buecher_je_fach("Deutsch")] == [DEUTSCH, TERRA]
    assert neu.planungszeile(TERRA, "Deutsch", 7).eingefuehrt_ab == "2027/2028"
    assert planungs_status(neu.planungszeile(TERRA, "Deutsch", 8), neu.schuljahr) \
        == PLANUNG_GEPLANT
    # Dasselbe Buch, keine Kopie: IServ-Werte, keine Korrektur.
    assert len(neu.buecher) == len(stand.buecher)
    assert not neu.buch(TERRA).von_hand
    assert neu.buch(TERRA).korrigiert == {}
    # Die neue Zeile ist unbestätigt, das Fach damit nicht mehr ganz bestätigt.
    bestaetigt, _ = bestaetige_fach(stand, fach="Deutsch", kuerzel="ABC", datum=None)
    nachher = fuege_buch_hinzu(bestaetigt, isbn=TERRA, fach="Deutsch",
                               buchreihe=_reihe(terra), zeilen=_einfuehrung(7))
    assert fach_status(nachher, "Deutsch")[0] == FACH_TEILWEISE


def test_eine_abweichende_buchreihe_ist_eine_korrektur(stand):
    terra = stand.buch(TERRA)
    neu = fuege_buch_hinzu(stand, isbn=TERRA, fach="Deutsch",
                           buchreihe=_reihe(terra, neupreis=26.0), zeilen=_einfuehrung(7))
    assert neu.buch(TERRA).korrigiert == {"neupreis": 25.0}


def test_eine_neue_isbn_legt_das_buch_von_hand_an(stand):
    neu = fuege_buch_hinzu(
        stand, isbn="3-16-148410-X", fach="Deutsch",
        buchreihe=Buchreiheneingabe(titel="Neues Deutschbuch 7", verlag="Klett",
                                    neupreis=24.999, leihgebuehr=None),
        zeilen=_einfuehrung(7),
    )
    buch = neu.buch(NEU)          # als ISBN-13
    assert buch is not None and buch.von_hand
    assert (buch.titel, buch.verlag, buch.neupreis, buch.leihgebuehr) == (
        "Neues Deutschbuch 7", "Klett", 25.0, None)
    assert buch.kombinationen == ()
    assert NEU in [b.isbn for b in neu.buecher_je_fach("Deutsch")]

    # Bearbeitet wird es danach ohne IServ-Kommentar: es gibt keinen IServ-Wert.
    geaendert = setze_buchreihe(neu, isbn=NEU, eingabe=_reihe(buch, titel="Deutschbuch 7"))
    assert geaendert.buch(NEU).titel == "Deutschbuch 7"
    assert geaendert.buch(NEU).korrigiert == {}


@pytest.mark.parametrize(("isbn", "zeilen", "teil"), [
    (NEU, [], "mindestens einen Jahrgang"),
    (NEU, [Jahrgangseingabe(jahrgang=7)], "Schuljahr der Einführung"),
    (NEU, _einfuehrung(7, 7), "zweimal"),
    (NEU, _einfuehrung(20), "kein Jahrgang"),
    (NEU, _einfuehrung(7, ab="2027"), "keine Schuljahresangabe"),
    ("9783161484101", _einfuehrung(7), "keine gültige ISBN"),
    ("", _einfuehrung(7), "Bitte die ISBN"),
    (DEUTSCH, _einfuehrung(7), "gehört schon zum Fach Deutsch"),
])
def test_ungueltiges_hinzufuegen_wird_abgelehnt(stand, isbn, zeilen, teil):
    with pytest.raises(UngueltigeEingabe, match=teil):
        fuege_buch_hinzu(stand, isbn=isbn, fach="Deutsch",
                         buchreihe=Buchreiheneingabe(titel="X", verlag="Y"), zeilen=zeilen)


def test_ein_von_hand_angelegtes_buch_uebersteht_datei_und_abgleich(tmp_path, stand):
    stand = fuege_buch_hinzu(stand, isbn=NEU, fach="Deutsch",
                             buchreihe=Buchreiheneingabe(titel="Neu 7", verlag="Klett"),
                             zeilen=_einfuehrung(7))
    pfad = tmp_path / "Buchplanung.xlsx"
    schreibe_datei(pfad, stand)
    gelesen = lies_datei(pfad)
    assert gelesen.buch(NEU).von_hand
    assert not gelesen.buch(DEUTSCH).von_hand

    neu = zusammenfuehren(gelesen, _schnappschuss())
    assert neu.buch(NEU).von_hand
    assert neu.planungszeile(NEU, "Deutsch", 7).eingefuehrt_ab == "2027/2028"
    assert not neu.warnungen

    # Führt IServ das Buch inzwischen selbst, ist es nicht mehr "von Hand";
    # Werte und Planung bleiben die der Datei.
    aus_iserv = Buch(isbn=NEU, titel="Neu 7 (IServ)", verlag="Klett",
                     kombinationen=(("Deutsch", 7),), leihbar=True)
    uebergeben = zusammenfuehren(neu, _schnappschuss(_buecher() + (aus_iserv,)))
    assert not uebergeben.buch(NEU).von_hand
    assert uebergeben.buch(NEU).titel == "Neu 7"
    assert uebergeben.buch(NEU).korrigiert == {"titel": "Neu 7 (IServ)", "leihbar": True}
    assert uebergeben.planungszeile(NEU, "Deutsch", 7).eingefuehrt_ab == "2027/2028"


def test_ein_von_hand_angelegtes_buch_ohne_jahrgang_verschwindet(stand):
    stand = fuege_buch_hinzu(stand, isbn=NEU, fach="Deutsch",
                             buchreihe=Buchreiheneingabe(titel="Neu 7", verlag="Klett"),
                             zeilen=_einfuehrung(7))
    ohne = setze_buchplanung(stand, isbn=NEU, fach="Deutsch", zeilen=[])
    assert ohne.buch(NEU) is None
    # Ein Buch aus IServ bleibt dagegen, auch ohne Planung.
    assert setze_buchplanung(stand, isbn=DEUTSCH, fach="Deutsch", zeilen=[]).buch(DEUTSCH)


def test_eine_alte_datei_ohne_spalte_kennt_nur_buecher_aus_iserv(tmp_path, stand):
    from openpyxl import load_workbook

    pfad = tmp_path / "Buchplanung.xlsx"
    schreibe_datei(pfad, stand)
    wb = load_workbook(str(pfad))
    ws = wb["Buchreihen"]
    spalte = next(z.column for z in ws[1] if z.value == "in IServ")
    ws.delete_cols(spalte)
    wb.save(str(pfad))
    assert not any(b.von_hand for b in lies_datei(pfad).buecher)


# ── Leihbar als Korrektur ────────────────────────────────────────────────────


def test_leihbar_wird_korrigiert_und_uebersteht_datei_und_abgleich(tmp_path, stand):
    kauf = stand.buch(KAUF)
    neu = setze_buchreihe(stand, isbn=KAUF, eingabe=_reihe(kauf, leihbar=True))
    assert neu.buch(KAUF).leihbar
    assert neu.buch(KAUF).korrigiert == {"leihbar": False}
    # Jetzt darf die Fachschaft auch zurücklegen.
    setze_ruecklage(neu, isbn=KAUF, fach="Latein", anzahl=3)

    pfad = tmp_path / "Buchplanung.xlsx"
    schreibe_datei(pfad, neu)
    gelesen = lies_datei(pfad)
    assert gelesen.buch(KAUF).leihbar
    assert gelesen.buch(KAUF).korrigiert == {"leihbar": False}
    assert gelesen.korrekturen_fuer_iserv() == {KAUF: {"borrowable": True}}

    abgeglichen = zusammenfuehren(gelesen, _schnappschuss())
    assert abgeglichen.buch(KAUF).leihbar
    # Ohne Angabe gilt wieder IServ.
    zurueck = setze_buchreihe(abgeglichen, isbn=KAUF, eingabe=_reihe(kauf, leihbar=None))
    assert not zurueck.buch(KAUF).leihbar
    assert zurueck.buch(KAUF).korrigiert == {}


def test_der_kommentar_nennt_leihbar_als_ja_oder_nein(tmp_path, stand):
    from openpyxl import load_workbook

    neu = setze_buchreihe(stand, isbn=KAUF, eingabe=_reihe(stand.buch(KAUF), leihbar=True))
    pfad = tmp_path / "Buchplanung.xlsx"
    schreibe_datei(pfad, neu)
    ws = load_workbook(str(pfad))["Buchreihen"]
    spalte = next(z.column for z in ws[1] if z.value == "leihbar")
    zeile = next(z.row for z in ws["E"] if z.value == KAUF)
    zelle = ws.cell(zeile, spalte)
    assert (zelle.value, zelle.comment.text) == ("ja", "in IServ: nein")


def test_ein_neues_buch_nimmt_leihbar_aus_dem_menue(stand):
    neu = fuege_buch_hinzu(stand, isbn=NEU, fach="Deutsch",
                           buchreihe=Buchreiheneingabe(titel="Neu", verlag="Klett", leihbar=True),
                           zeilen=_einfuehrung(7))
    assert neu.buch(NEU).leihbar
    assert neu.buch(NEU).korrigiert == {}
