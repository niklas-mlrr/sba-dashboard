"""Die Buchplanung über HTTP: abgleichen und die fünf Arten einzutragen.

Ohne Netz: der Fake-Client liefert zwei Schuljahre, deren Unterschied die drei
Fälle abdeckt, um die es geht - ein Buch bleibt, eines kommt neu dazu, eines
gibt es nur noch im Vorjahr (ausgemustert, Rücklage-Kandidat).

Der Fake gibt dem Schuljahr einen **anderen Namen als seine Kennung**
("Schuljahr 26/27" gegenüber "2026/2027"), so wie das echte IServ. Das ist
kein Detail: die Kennung adressiert das Jahr in der API, steht im Dateinamen
und wird mit anderen Schuljahren verglichen; der Name ist nur Beschriftung.
Ein Fake, in dem beide gleich sind, verwechselt sie folgenlos - die Anwendung
tat es am 2026-09-19 nicht folgenlos ("Nicht gefunden:
/schoolyears/Schuljahr%2026%2F27").

Was diese Datei festhält, sind die Zusagen der Schreibkette: ohne gültige
``mtime`` wird nicht geschrieben (409), ohne Datei gibt es nichts einzutragen
(503), und jede Fehlermeldung ist ein deutscher Satz.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Einstellungen
from conftest import TEST_BASIS_URL

DEUTSCH = "9783060000005"
TERRA = "9783121000562"
ALT = "9783120000009"

# Schuljahr -> Jahrgang -> (ISBN, Titel, Fächer, Verlag, Preis)
_BUECHER: dict[str, dict[int, list[tuple[str, str, list[str], str, float]]]] = {
    "2025/2026": {
        5: [(DEUTSCH, "Deutschbuch 5", ["Deutsch"], "Cornelsen", 22.5),
            (TERRA, "Terra 5/6", ["Erdkunde", "Politik"], "Klett", 25.0)],
        9: [(ALT, "Chemie heute 9", ["Chemie"], "Westermann", 30.0)],
    },
    "2026/2027": {
        5: [(DEUTSCH, "Deutschbuch 5", ["Deutsch"], "Cornelsen", 22.5)],
        6: [(TERRA, "Terra 5/6", ["Erdkunde", "Politik"], "Klett", 25.0)],
    },
}


NAME = "Schuljahr 26/27"


class _Schuljahre:
    def get_current(self) -> dict:
        return {"id": "2026/2027", "name": NAME}

    def get_by_id(self, schoolyear_id: str) -> dict:
        if schoolyear_id not in _BUECHER:
            raise KeyError(f"Nicht gefunden: /schoolyears/{schoolyear_id}")
        return {"id": schoolyear_id, "name": NAME}

    def get_booklists(self, schoolyear_id: str) -> list[dict]:
        return [{"id": 100 + grade, "grade": grade}
                for grade in sorted(_BUECHER[schoolyear_id])]

    def get_booklist(self, schoolyear_id: str, booklist_id: int) -> dict:
        items = [
            {"borrowable": True, "series": isbn,
             "series_data": {"isbn": isbn, "title": titel, "subjectsFlat": faecher,
                             "publisher": verlag, "price": preis, "fee": 5.0}}
            for isbn, titel, faecher, verlag, preis in
            _BUECHER[schoolyear_id][booklist_id - 100]
        ]
        return {"sections": [{"options": [{"items": items}]}]}


class FakeClient:
    schoolyears = _Schuljahre()

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def login(self) -> bool:
        return True


@pytest.fixture()
def seiten(einstellungen: Einstellungen) -> TestClient:
    application = create_app(einstellungen=einstellungen, client_factory=FakeClient)
    with TestClient(application, base_url=TEST_BASIS_URL) as testclient:
        yield testclient


def _anmelden(client: TestClient) -> None:
    antwort = client.post("/api/anmeldung", json={"benutzer": "b.lehrer", "passwort": "x"})
    assert antwort.status_code == 200, antwort.text


def _datei(einstellungen: Einstellungen) -> Path:
    pfad = einstellungen.buchplanung_pfad("2026/2027")
    assert pfad is not None
    return pfad


@pytest.fixture()
def abgeglichen(seiten: TestClient) -> dict:
    """Der Stand nach dem ersten Abgleich - die Vorbedingung jeder Eintragung."""
    _anmelden(seiten)
    antwort = seiten.post("/api/buchplanung/abgleich", json={})
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


# ── Abgleich ─────────────────────────────────────────────────────────────────


def test_abgleich_ohne_anmeldung_ist_401(seiten: TestClient) -> None:
    antwort = seiten.post("/api/buchplanung/abgleich", json={})
    assert antwort.status_code == 401
    assert "fehler" in antwort.json()


def test_die_seite_reicht_die_kennung_weiter_nicht_den_namen(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Der Rückfall vom 2026-09-19: der Anzeigename ging als Kennung an IServ.

    Die Seite trägt die Kennung in ``data-schuljahr``, und genau sie kommt bei
    jeder Eintragung zurück. Stünde dort der Name, verlangte der nächste
    Abgleich von IServ ein Schuljahr namens „Schuljahr 26/27" - das es nicht
    gibt.
    """
    text = seiten.get("/buecherliste/fach").text
    assert 'data-schuljahr="2026/2027"' in text
    assert NAME not in text.split("<main>")[0].split('data-schuljahr')[1][:40]
    # Und ein zweiter Abgleich von der Seite aus läuft durch.
    assert seiten.post("/api/buchplanung/abgleich",
                       json={"schuljahr": "2026/2027"}).status_code == 200


def test_abgleich_schreibt_die_datei_je_schuljahr(
    abgeglichen: dict, einstellungen: Einstellungen,
) -> None:
    pfad = _datei(einstellungen)
    assert pfad.is_file()
    # Das Schuljahr steht im Dateinamen, mit Bindestrich statt Schrägstrich.
    assert "2026-2027" in pfad.name
    assert abgeglichen["datei"] == str(pfad)

    planung = abgeglichen["planung"]
    # Die Kennung, nicht der Anzeigename: sie steht im Dateinamen und wird mit
    # den Schuljahren der Planung verglichen.
    assert planung["schuljahr"] == "2026/2027"
    assert planung["vorjahr"] == "2025/2026"
    je_isbn = {buch["isbn"]: buch for buch in planung["buecher"]}
    assert je_isbn[DEUTSCH]["jahrgaenge_aktuell"] == [5]
    # Nur im Vorjahr: ausgemustert, steht aber weiter in der Datei.
    assert je_isbn[ALT]["jahrgaenge_aktuell"] == []
    assert je_isbn[ALT]["jahrgaenge_vorjahr"] == [9]
    # Ein Buch mit zwei Fächern steht in beiden.
    assert {f["fach"] for f in planung["faecher"]} == {"Chemie", "Deutsch", "Erdkunde", "Politik"}


def test_lesen_ohne_datei_meldet_keinen_stand(seiten: TestClient) -> None:
    antwort = seiten.get("/api/buchplanung", params={"schuljahr": "2026/2027"})
    assert antwort.status_code == 200
    assert antwort.json()["planung"] is None


def test_lesen_gibt_den_gespeicherten_stand_zurueck(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    antwort = seiten.get("/api/buchplanung", params={"schuljahr": "2026/2027"})
    assert antwort.status_code == 200
    assert antwort.json()["planung"]["schuljahr"] == "2026/2027"
    assert antwort.json()["mtime"] == abgeglichen["mtime"]


# ── Preisprüfung ─────────────────────────────────────────────────────────────


def test_einzelner_preis_wird_bestaetigt(seiten: TestClient, abgeglichen: dict) -> None:
    antwort = seiten.post("/api/buchplanung/preis", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "preis": 22.5,
        "kuerzel": "MLR", "datum": "2026-09-01", "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    buch = next(b for b in antwort.json()["planung"]["buecher"] if b["isbn"] == DEUTSCH)
    assert buch["preis_status"] == "bestätigt"
    assert buch["geprueft"]["kuerzel"] == "MLR"


def test_abweichender_preis_faellt_auf(seiten: TestClient, abgeglichen: dict) -> None:
    antwort = seiten.post("/api/buchplanung/preis", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "preis": 19.9,
        "kuerzel": "MLR", "mtime": abgeglichen["mtime"],
    })
    buch = next(b for b in antwort.json()["planung"]["buecher"] if b["isbn"] == DEUTSCH)
    assert buch["preis_status"] == "abweichend"
    assert "19,90" in buch["preis_hinweis"] and "22,50" in buch["preis_hinweis"]


def test_ganze_verlagsliste_auf_einmal(seiten: TestClient, abgeglichen: dict) -> None:
    antwort = seiten.post("/api/buchplanung/preise", json={
        "schuljahr": "2026/2027", "verlag": "Klett", "kuerzel": "MLR",
        "datum": "2026-09-05", "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    assert antwort.json()["bestaetigt"] == 1
    je_isbn = {b["isbn"]: b for b in antwort.json()["planung"]["buecher"]}
    assert je_isbn[TERRA]["preis_status"] == "bestätigt"
    assert je_isbn[DEUTSCH]["preis_status"] == "offen"


def test_unbekannter_verlag_wird_abgelehnt(seiten: TestClient, abgeglichen: dict) -> None:
    antwort = seiten.post("/api/buchplanung/preise", json={
        "schuljahr": "2026/2027", "verlag": "Gibt-es-nicht", "kuerzel": "MLR",
        "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 400
    assert "kommt in dieser Datei" in antwort.json()["fehler"]


# ── Fachbestätigung ──────────────────────────────────────────────────────────


def test_fachbestaetigung_haelt_kuerzel_und_datum_fest(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    antwort = seiten.post("/api/buchplanung/fach", json={
        "schuljahr": "2026/2027", "fach": "Deutsch", "kuerzel": "ABC",
        "datum": "2026-09-03", "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    fach = next(f for f in antwort.json()["planung"]["faecher"] if f["fach"] == "Deutsch")
    assert fach["status"] == "bestätigt"
    assert (fach["kuerzel"], fach["datum"]) == ("ABC", "2026-09-03")


def test_fachbestaetigung_veraltet_wenn_ein_buch_dazukommt(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    bestaetigt = seiten.post("/api/buchplanung/fach", json={
        "schuljahr": "2026/2027", "fach": "Deutsch", "kuerzel": "ABC",
        "mtime": abgeglichen["mtime"],
    }).json()

    _BUECHER["2026/2027"][5].append(
        ("9783060000012", "Deutschbuch 6", ["Deutsch"], "Cornelsen", 23.0))
    try:
        antwort = seiten.post("/api/buchplanung/abgleich", json={})
    finally:
        _BUECHER["2026/2027"][5].pop()

    assert antwort.status_code == 200, antwort.text
    assert bestaetigt["mtime"] != antwort.json()["mtime"]
    fach = next(f for f in antwort.json()["planung"]["faecher"] if f["fach"] == "Deutsch")
    assert fach["status"] == "veraltet"
    assert "hinzugekommen: Deutschbuch 6" in fach["hinweis"]
    # Das Kürzel bleibt lesbar stehen - man soll sehen, wer zuletzt bestätigt hat.
    assert fach["kuerzel"] == "ABC"


# ── Planung und Rücklage ─────────────────────────────────────────────────────


def test_planungsstatus_wird_gegen_die_kennung_gerechnet(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Mit dem Anzeigenamen als Schuljahr stünde hier immer „im Einsatz"."""
    antwort = seiten.post("/api/buchplanung/planung", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "jahrgang": 5,
        "ausgemustert_nach": "2025/2026", "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    buch = next(b for b in antwort.json()["planung"]["buecher"] if b["isbn"] == DEUTSCH)
    assert next(z for z in buch["planung"] if z["jahrgang"] == 5)["status"] == "ausgemustert"


def test_einfuehrung_in_einen_kuenftigen_jahrgang(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    antwort = seiten.post("/api/buchplanung/planung", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "jahrgang": 7,
        "eingefuehrt_ab": "2028/2029", "beschluss": "FK 12.05.2026",
        "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    buch = next(b for b in antwort.json()["planung"]["buecher"] if b["isbn"] == DEUTSCH)
    zeile = next(z for z in buch["planung"] if z["jahrgang"] == 7)
    assert zeile["eingefuehrt_ab"] == "2028/2029"
    assert zeile["status"] == "geplant"
    assert zeile["herkunft"] == "nur Planung"


def test_ausmusterung_mit_ruecklage_fuer_die_fachschaft(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    stand = seiten.post("/api/buchplanung/planung", json={
        "schuljahr": "2026/2027", "isbn": ALT, "jahrgang": 9,
        "ausgemustert_nach": "2025/2026", "mtime": abgeglichen["mtime"],
    }).json()

    antwort = seiten.post("/api/buchplanung/ruecklage", json={
        "schuljahr": "2026/2027", "isbn": ALT, "fach": "Chemie", "anzahl": 5,
        "kuerzel": "FK", "bemerkung": "für die Sammlung", "mtime": stand["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    buch = next(b for b in antwort.json()["planung"]["buecher"] if b["isbn"] == ALT)
    assert next(z for z in buch["planung"] if z["jahrgang"] == 9)["status"] == "ausgemustert"
    assert buch["ruecklagen"] == [{
        "fach": "Chemie", "anzahl": 5, "status": "gewünscht", "kuerzel": "FK",
        "datum": None, "bemerkung": "für die Sammlung",
    }]


def test_ruecklage_fuer_ein_fremdes_fach_wird_abgelehnt(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    antwort = seiten.post("/api/buchplanung/ruecklage", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "fach": "Chemie", "anzahl": 3,
        "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 400
    assert "gehört nicht zum Fach" in antwort.json()["fehler"]


def test_schuljahr_ohne_schraegstrich_wird_abgelehnt(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    antwort = seiten.post("/api/buchplanung/planung", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "jahrgang": 7,
        "eingefuehrt_ab": "2028", "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 400
    assert "2026/2027" in antwort.json()["fehler"]


# ── Die Schreibkette ─────────────────────────────────────────────────────────


def test_veraltete_mtime_wird_mit_409_abgelehnt(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    seiten.post("/api/buchplanung/preis", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "preis": 22.5,
        "kuerzel": "MLR", "mtime": abgeglichen["mtime"],
    })
    antwort = seiten.post("/api/buchplanung/preis", json={
        "schuljahr": "2026/2027", "isbn": TERRA, "preis": 25.0,
        "kuerzel": "MLR", "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 409
    assert "neu laden" in antwort.json()["fehler"]


def test_eintragen_ohne_datei_meldet_den_fehlenden_abgleich(seiten: TestClient) -> None:
    antwort = seiten.post("/api/buchplanung/preis", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "preis": 22.5,
        "kuerzel": "MLR", "mtime": 1.0,
    })
    assert antwort.status_code == 503
    assert "aktualisieren" in antwort.json()["fehler"]


def test_unbekannte_isbn_wird_abgelehnt(seiten: TestClient, abgeglichen: dict) -> None:
    antwort = seiten.post("/api/buchplanung/preis", json={
        "schuljahr": "2026/2027", "isbn": "9780000000000", "preis": 1.0,
        "kuerzel": "MLR", "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 400
    assert "kein Buch" in antwort.json()["fehler"]


def test_fehlende_mtime_ist_ein_deutscher_satz(seiten: TestClient, abgeglichen: dict) -> None:
    antwort = seiten.post("/api/buchplanung/preis", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "preis": 22.5, "kuerzel": "MLR",
    })
    assert antwort.status_code == 400
    assert antwort.json()["fehler"] == "Es fehlt eine gültige Änderungszeit der geladenen Datei."


# ── Die Bedienelemente in den Bücherlisten-Seiten ────────────────────────────


def test_ohne_datei_steht_der_knopf_zum_aktualisieren(seiten: TestClient) -> None:
    _anmelden(seiten)
    text = seiten.get("/buecherliste/fach").text
    assert 'data-planung="abgleich"' in text
    assert "ist noch nichts gespeichert" in text


def test_verlagsseite_bietet_preispruefung(seiten: TestClient, abgeglichen: dict) -> None:
    text = seiten.get("/buecherliste/verlag/Klett").text
    assert 'data-planung="preise"' in text          # ganze Liste, oben
    assert 'data-planung="preis"' in text           # je Buch, in der Status-Spalte
    # Die Fach-Bedienelemente gehören nicht auf diese Seite.
    assert 'data-planung="fach"' not in text
    assert 'data-planung="aufklappen"' not in text


def test_fachseite_bietet_freigabe_und_planung(seiten: TestClient, abgeglichen: dict) -> None:
    text = seiten.get("/buecherliste/fach/Deutsch").text
    assert 'data-planung="fach"' in text
    assert 'data-planung="aufklappen"' in text
    assert 'data-planung="ruecklage"' in text
    assert 'data-planung-feld="eingefuehrt_ab"' in text
    assert 'data-planung-feld="ausgemustert_nach"' in text
    # Preise werden beim Verlag geprüft, nicht beim Fach.
    assert 'data-planung="preis"' not in text


def test_fachseite_zeigt_die_freigabe_und_ihren_verfall(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    seiten.post("/api/buchplanung/fach", json={
        "schuljahr": "2026/2027", "fach": "Deutsch", "kuerzel": "ABC",
        "mtime": abgeglichen["mtime"],
    })
    assert "label-success" in seiten.get("/buecherliste/fach/Deutsch").text

    _BUECHER["2026/2027"][5].append(
        ("9783060000012", "Deutschbuch 6", ["Deutsch"], "Cornelsen", 23.0))
    try:
        seiten.post("/api/buchplanung/abgleich", json={})
        text = seiten.get("/buecherliste/fach/Deutsch").text
    finally:
        _BUECHER["2026/2027"][5].pop()
    assert "veraltet" in text
    assert "hinzugekommen: Deutschbuch 6" in text


def test_uebersicht_zeigt_den_fortschritt_der_preispruefung(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    assert "von" in seiten.get("/buecherliste/verlag").text
    seiten.post("/api/buchplanung/preise", json={
        "schuljahr": "2026/2027", "verlag": "Klett", "kuerzel": "MLR",
        "mtime": abgeglichen["mtime"],
    })
    text = seiten.get("/buecherliste/verlag").text
    # Klett ist vollständig geprüft, Cornelsen noch nicht.
    assert "label-success" in text
    assert "0 von 1 geprüft" in text


def test_druckmenue_kennt_die_nicht_bestaetigten_faecher(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    seiten.post("/api/buchplanung/fach", json={
        "schuljahr": "2026/2027", "fach": "Deutsch", "kuerzel": "ABC",
        "mtime": abgeglichen["mtime"],
    })
    text = seiten.get("/buecherliste/fach").text
    # "nicht bestätigte" trägt jetzt eine echte Liste - ohne das bestätigte Fach.
    assert 'value="nicht_bestaetigte"' in text
    liste = text.split('value="nicht_bestaetigte"')[1].split("</label>")[0]
    assert "Erdkunde" in liste and "Politik" in liste
    assert "Deutsch" not in liste


def test_kaputte_datei_macht_die_buecherliste_nicht_unbrauchbar(
    seiten: TestClient, einstellungen: Einstellungen, abgeglichen: dict,
) -> None:
    """Die Seite kommt live aus IServ; der gespeicherte Stand ist eine Zugabe."""
    _datei(einstellungen).write_bytes(b"kein Excel")
    antwort = seiten.get("/buecherliste/fach/Deutsch")
    assert antwort.status_code == 200
    assert "Deutschbuch 5" in antwort.text
    assert "nicht lesbar" in antwort.text
