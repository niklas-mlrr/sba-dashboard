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

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Einstellungen
from conftest import TEST_BASIS_URL

DEUTSCH = "9783060000005"
TERRA = "9783121000562"
ALT = "9783120000009"
KAUF = "9783140000000"

# Schuljahr -> Jahrgang -> (ISBN, Titel, Fächer, Verlag, Preis, leihbar)
_BUECHER: dict[str, dict[int, list[tuple[str, str, list[str], str, float, bool]]]] = {
    "2025/2026": {
        5: [(DEUTSCH, "Deutschbuch 5", ["Deutsch"], "Cornelsen", 22.5, True),
            (TERRA, "Terra 5/6", ["Erdkunde", "Politik"], "Klett", 25.0, True)],
        9: [(ALT, "Chemie heute 9", ["Chemie"], "Westermann", 30.0, True)],
    },
    "2026/2027": {
        5: [(DEUTSCH, "Deutschbuch 5", ["Deutsch"], "Cornelsen", 22.5, True),
            (KAUF, "Wörterbuch Latein", ["Latein"], "Langenscheidt", 19.9, False)],
        6: [(TERRA, "Terra 5/6", ["Erdkunde", "Politik"], "Klett", 25.0, True)],
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
            {"borrowable": leihbar, "series": isbn,
             "series_data": {"isbn": isbn, "title": titel, "subjectsFlat": faecher,
                             "publisher": verlag, "price": preis, "fee": 5.0}}
            for isbn, titel, faecher, verlag, preis, leihbar in
            _BUECHER[schoolyear_id][booklist_id - 100]
        ]
        return {"sections": [{"options": [{"items": items}]}]}


class _Serien:
    """Das Inventar: jede Buchreihe, die in irgendeiner Liste steht."""

    def get_all(self, detailed: bool = False) -> list[SimpleNamespace]:
        return [SimpleNamespace(isbn=isbn, title=titel, publisher=verlag, price=preis, fee=5.0)
                for jahr in _BUECHER.values() for liste in jahr.values()
                for isbn, titel, _, verlag, preis, _ in liste]


class FakeClient:
    schoolyears = _Schuljahre()
    series = _Serien()

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
    assert je_isbn[DEUTSCH]["jahrgaenge"] == [5]
    # Nur im Vorjahr, aber leihbar: steht weiter in der Datei - dafür gibt es
    # die Ausmusterung und die Rücklage.
    assert je_isbn[ALT]["jahrgaenge"] == [9]
    # Ein Buch mit zwei Fächern steht in beiden.
    assert {f["fach"] for f in planung["faecher"]} == {
        "Chemie", "Deutsch", "Erdkunde", "Latein", "Politik"}


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
    assert antwort.json()["bestaetigt"] == 1


def test_ein_neues_buch_macht_das_fach_wieder_unbestaetigt(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    bestaetigt = seiten.post("/api/buchplanung/fach", json={
        "schuljahr": "2026/2027", "fach": "Deutsch", "kuerzel": "ABC",
        "mtime": abgeglichen["mtime"],
    }).json()

    _BUECHER["2026/2027"][5].append(
        ("9783060000012", "Deutschbuch 6", ["Deutsch"], "Cornelsen", 23.0, True))
    try:
        antwort = seiten.post("/api/buchplanung/abgleich", json={})
    finally:
        _BUECHER["2026/2027"][5].pop()

    assert antwort.status_code == 200, antwort.text
    assert bestaetigt["mtime"] != antwort.json()["mtime"]
    fach = next(f for f in antwort.json()["planung"]["faecher"] if f["fach"] == "Deutsch")
    assert fach["status"] == "teilweise"
    assert "Deutschbuch 6 (Jg. 5)" in fach["hinweis"]
    # Das Kürzel bleibt lesbar stehen - man soll sehen, wer zuletzt bestätigt hat.
    assert fach["kuerzel"] == "ABC"


# ── Planung und Rücklage ─────────────────────────────────────────────────────


def test_planungsstatus_wird_gegen_die_kennung_gerechnet(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Mit dem Anzeigenamen als Schuljahr stünde hier immer „im Einsatz"."""
    antwort = seiten.post("/api/buchplanung/planung", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "fach": "Deutsch", "jahrgang": 5,
        "ausgemustert_nach": "2025/2026", "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    buch = next(b for b in antwort.json()["planung"]["buecher"] if b["isbn"] == DEUTSCH)
    assert next(z for z in buch["planung"] if z["jahrgang"] == 5)["status"] == "ausgemustert"


def test_einfuehrung_in_einen_kuenftigen_jahrgang(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    antwort = seiten.post("/api/buchplanung/planung", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "fach": "Deutsch", "jahrgang": 7,
        "eingefuehrt_ab": "2028/2029", "bemerkung": "FK 12.05.2026",
        "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    buch = next(b for b in antwort.json()["planung"]["buecher"] if b["isbn"] == DEUTSCH)
    zeile = next(z for z in buch["planung"] if z["jahrgang"] == 7)
    assert zeile["fach"] == "Deutsch"
    assert zeile["eingefuehrt_ab"] == "2028/2029"
    assert zeile["status"] == "geplant"
    assert zeile["bemerkung"] == "FK 12.05.2026"


def test_auch_ein_kaufbuch_wird_ausgemustert(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Ausgemustert wird die Bücherliste, nicht der Bestand der Schule.

    Bis 2026-09-20 wies der Server das ab. Auch ein Buch, das die Familien
    selbst kaufen, steht bis zu einem Schuljahr auf der Liste und danach nicht
    mehr - und genau das hält die Spalte fest.
    """
    antwort = seiten.post("/api/buchplanung/planung", json={
        "schuljahr": "2026/2027", "isbn": KAUF, "fach": "Latein", "jahrgang": 7,
        "ausgemustert_nach": "2026/2027", "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    buch = next(b for b in antwort.json()["planung"]["buecher"] if b["isbn"] == KAUF)
    assert next(z for z in buch["planung"] if z["jahrgang"] == 7)["status"] == "läuft aus"


def test_fuer_ein_kaufbuch_gibt_es_keine_ruecklage(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Die Schule besitzt keine Exemplare davon - es ist nichts zurückzulegen."""
    antwort = seiten.post("/api/buchplanung/ruecklage", json={
        "schuljahr": "2026/2027", "isbn": KAUF, "fach": "Latein", "anzahl": 3,
        "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 400
    assert "lässt sich nichts zurücklegen" in antwort.json()["fehler"]


def test_das_menue_eines_kaufbuchs_zeigt_keinen_ruecklage_block(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    text = seiten.get("/buecherliste/fach/Latein").text
    vorlage = text.split('class="planung-vorlage"')[1].split("</template>")[0]
    assert "Rücklage für die Fachschaft" not in vorlage
    # Einführung und Ausmusterung stehen trotzdem offen.
    assert 'data-planung-feld="ausgemustert_nach"' in vorlage


def test_ausmusterung_mit_ruecklage_fuer_die_fachschaft(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    stand = seiten.post("/api/buchplanung/planung", json={
        "schuljahr": "2026/2027", "isbn": ALT, "fach": "Chemie", "jahrgang": 9,
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
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "fach": "Deutsch", "jahrgang": 7,
        "eingefuehrt_ab": "2028", "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 400
    assert "2026/2027" in antwort.json()["fehler"]


# ── Das Planungsmenü: alles zu einem Buch in einem Zug ───────────────────────


def _zeilen(antwort: dict, isbn: str, fach: str) -> dict[int, dict]:
    buch = next(b for b in antwort["planung"]["buecher"] if b["isbn"] == isbn)
    return {z["jahrgang"]: z for z in buch["planung"] if z["fach"] == fach}


def test_menue_schreibt_mehrere_jahrgaenge_und_die_ruecklage_auf_einmal(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Ein Menü, ein Knopf, eine Anfrage - sonst käme die zweite auf ein 409."""
    antwort = seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "fach": "Deutsch",
        "zeilen": [
            {"jahrgang": 5, "ausgemustert_nach": "2029/2030", "bemerkung": "FK 05/26"},
            {"jahrgang": 7, "eingefuehrt_ab": "2028/2029"},
            {"jahrgang": 8, "eingefuehrt_ab": "2029/2030"},
        ],
        "ruecklage": {"anzahl": 4, "bemerkung": "für die Sammlung"},
        "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    zeilen = _zeilen(antwort.json(), DEUTSCH, "Deutsch")
    assert zeilen[5]["ausgemustert_nach"] == "2029/2030"
    assert zeilen[5]["bemerkung"] == "FK 05/26"
    assert zeilen[5]["status"] == "läuft aus"
    assert zeilen[7]["status"] == "geplant"
    assert zeilen[8]["eingefuehrt_ab"] == "2029/2030"
    buch = next(b for b in antwort.json()["planung"]["buecher"] if b["isbn"] == DEUTSCH)
    assert buch["ruecklagen"] == [{
        "fach": "Deutsch", "anzahl": 4, "status": "gewünscht", "kuerzel": "",
        "datum": None, "bemerkung": "für die Sammlung",
    }]


def test_ein_nicht_mitgeschickter_jahrgang_verschwindet(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Das Menü zeigt den ganzen Stand, also schickt es ihn auch ganz zurück."""
    stand = seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "fach": "Deutsch",
        "zeilen": [{"jahrgang": 5}, {"jahrgang": 7, "eingefuehrt_ab": "2028/2029"}],
        "mtime": abgeglichen["mtime"],
    }).json()
    assert 7 in _zeilen(stand, DEUTSCH, "Deutsch")

    antwort = seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "fach": "Deutsch",
        "zeilen": [{"jahrgang": 5}], "mtime": stand["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    # Jahrgang 5 steht in einer Bücherliste und bleibt deshalb als Zeile stehen;
    # der nur geplante Jahrgang 7 ist weg.
    assert 7 not in _zeilen(antwort.json(), DEUTSCH, "Deutsch")


def test_derselbe_jahrgang_zweimal_wird_abgelehnt(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    antwort = seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "fach": "Deutsch",
        "zeilen": [{"jahrgang": 7, "eingefuehrt_ab": "2028/2029"},
                   {"jahrgang": 7, "eingefuehrt_ab": "2029/2030"}],
        "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 400
    assert "zweimal" in antwort.json()["fehler"]


def test_kuenftige_ausmusterung_laesst_die_bestaetigung_stehen(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Was erst in drei Jahren greift, ändert die bestätigte Liste nicht."""
    stand = seiten.post("/api/buchplanung/fach", json={
        "schuljahr": "2026/2027", "fach": "Deutsch", "kuerzel": "ABC",
        "mtime": abgeglichen["mtime"],
    }).json()

    antwort = seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "fach": "Deutsch",
        "zeilen": [{"jahrgang": 5, "ausgemustert_nach": "2029/2030"}],
        "mtime": stand["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    assert _zeilen(antwort.json(), DEUTSCH, "Deutsch")[5]["status"] == "läuft aus"
    fach = next(f for f in antwort.json()["planung"]["faecher"] if f["fach"] == "Deutsch")
    assert fach["status"] == "bestätigt"
    assert fach["kuerzel"] == "ABC"


def test_ausmusterung_im_laufenden_schuljahr_nimmt_die_bestaetigung_zurueck(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Jetzt fehlt das Buch in der Liste, die bestätigt wurde - also neu prüfen."""
    stand = seiten.post("/api/buchplanung/fach", json={
        "schuljahr": "2026/2027", "fach": "Deutsch", "kuerzel": "ABC",
        "mtime": abgeglichen["mtime"],
    }).json()

    antwort = seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "fach": "Deutsch",
        "zeilen": [{"jahrgang": 5, "ausgemustert_nach": "2025/2026"}],
        "mtime": stand["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    assert _zeilen(antwort.json(), DEUTSCH, "Deutsch")[5]["status"] == "ausgemustert"
    fach = next(f for f in antwort.json()["planung"]["faecher"] if f["fach"] == "Deutsch")
    # Deutsch hat genau diese eine Zeile; ohne ihr Kürzel ist nicht "teilweise"
    # bestätigt, sondern gar nichts.
    assert fach["status"] == "offen"
    assert fach["kuerzel"] == ""


def test_das_menue_weist_ein_fremdes_fach_ab(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    antwort = seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "fach": "Chemie",
        "zeilen": [{"jahrgang": 5}], "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 400
    assert "gehört nicht zum Fach" in antwort.json()["fehler"]


def test_die_jahrgang_spalte_zeigt_einfuehrung_und_ausmusterung(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Geplantes sieht man in der Liste selbst, nicht erst im Menü.

    Terra steht in Erdkunde in Jahrgang 6. Ein geplanter Jahrgang 7 kommt in
    der Spalte dazu, obwohl er in keiner Bücherliste steht - sonst wäre die
    Einführung nirgends zu sehen.
    """
    stand = seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": TERRA, "fach": "Erdkunde",
        # Jahrgang 5 schickt das Menü mit, wie es ihn zeigt: ausgemustert
        # nach dem Vorjahr. Fehlte er, wäre er laut Datei wieder im Einsatz.
        "zeilen": [{"jahrgang": 5, "ausgemustert_nach": "2025/2026"},
                   {"jahrgang": 6, "ausgemustert_nach": "2029/2030"},
                   {"jahrgang": 7, "eingefuehrt_ab": "2028/2029"}],
        "mtime": abgeglichen["mtime"],
    }).json()
    text = seiten.get("/buecherliste/fach/Erdkunde").text
    # Verschiedene Zusätze: jeder hängt an seinem Jahrgang.
    assert "5 (bis 2025/2026), 6 (bis 2029/2030), 7 (ab 2028/2029)" in text
    # Sortiert wird weiter nach den nackten Jahrgängen.
    assert 'data-wert="5, 6, 7"' in text

    # Derselbe Zusatz für alle: er steht trotzdem an jedem Jahrgang einzeln.
    seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": TERRA, "fach": "Erdkunde",
        "zeilen": [{"jahrgang": 6, "ausgemustert_nach": "2029/2030"},
                   {"jahrgang": 7, "eingefuehrt_ab": "2028/2029"},
                   {"jahrgang": 8, "eingefuehrt_ab": "2028/2029"}],
        "mtime": stand["mtime"],
    })
    text = _ohne_tags(seiten.get("/buecherliste/fach/Erdkunde").text)
    assert "6 (bis 2029/2030), 7 (ab 2028/2029), 8 (ab 2028/2029)" in text
    assert "7, 8 (ab" not in text


def test_ein_buch_fuer_nur_ein_schuljahr_zeigt_nur_dieses_jahr(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Eingeführt und ausgemustert im selben Schuljahr: nur das Jahr, ohne „ab“/„bis“.

    Ist es das laufende Schuljahr, bleibt es bei „bis …“.
    """
    antwort = seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": TERRA, "fach": "Erdkunde",
        "zeilen": [{"jahrgang": 6, "eingefuehrt_ab": "2026/2027",
                    "ausgemustert_nach": "2026/2027"},
                   {"jahrgang": 7, "eingefuehrt_ab": "2028/2029",
                    "ausgemustert_nach": "2028/2029"}],
        "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    text = seiten.get("/buecherliste/fach/Erdkunde").text
    assert "6 (bis 2026/2027), 7 (2028/2029)" in _ohne_tags(text)


def test_die_ruecklagen_spalte_erscheint_erst_mit_einer_ruecklage(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Eine Spalte aus lauter leeren Zellen sagt nichts - und ist der Normalfall."""
    ohne = seiten.get("/buecherliste/fach/Erdkunde").text
    assert ">Rücklagen<" not in ohne

    seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": TERRA, "fach": "Erdkunde",
        "zeilen": [], "ruecklage": {"anzahl": 12}, "mtime": abgeglichen["mtime"],
    })
    mit = seiten.get("/buecherliste/fach/Erdkunde").text
    assert ">Rücklagen<" in mit
    # Hinter "Leihbar", und als Zahl sortierbar.
    assert mit.index(">Leihbar<") < mit.index(">Rücklagen<")
    assert '<td data-wert="12">12</td>' in mit


def test_der_stand_einer_ruecklage_bleibt_beim_speichern_stehen(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Das Menü kennt den Stand nicht - also darf es ihn auch nicht überschreiben."""
    stand = seiten.post("/api/buchplanung/ruecklage", json={
        "schuljahr": "2026/2027", "isbn": TERRA, "fach": "Erdkunde", "anzahl": 8,
        "status": "zugesagt", "mtime": abgeglichen["mtime"],
    }).json()

    antwort = seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": TERRA, "fach": "Erdkunde", "zeilen": [],
        "ruecklage": {"anzahl": 9, "bemerkung": "doch mehr"}, "mtime": stand["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    buch = next(b for b in antwort.json()["planung"]["buecher"] if b["isbn"] == TERRA)
    wunsch = next(r for r in buch["ruecklagen"] if r["fach"] == "Erdkunde")
    assert (wunsch["anzahl"], wunsch["status"]) == (9, "zugesagt")


# ── Die Schreibkette ─────────────────────────────────────────────────────────


def test_veraltete_mtime_wird_mit_409_abgelehnt(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    seiten.post("/api/buchplanung/fach", json={
        "schuljahr": "2026/2027", "fach": "Deutsch", "kuerzel": "ABC",
        "mtime": abgeglichen["mtime"],
    })
    antwort = seiten.post("/api/buchplanung/fach", json={
        "schuljahr": "2026/2027", "fach": "Erdkunde", "kuerzel": "ABC",
        "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 409
    assert "neu laden" in antwort.json()["fehler"]


def test_eintragen_ohne_datei_meldet_den_fehlenden_abgleich(seiten: TestClient) -> None:
    antwort = seiten.post("/api/buchplanung/fach", json={
        "schuljahr": "2026/2027", "fach": "Deutsch", "kuerzel": "ABC", "mtime": 1.0,
    })
    assert antwort.status_code == 503
    assert "aktualisieren" in antwort.json()["fehler"]


def test_unbekannte_isbn_wird_abgelehnt(seiten: TestClient, abgeglichen: dict) -> None:
    antwort = seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": "9780000000000", "fach": "Deutsch",
        "zeilen": [], "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 400
    assert "kein Buch" in antwort.json()["fehler"]


def test_fehlende_mtime_ist_ein_deutscher_satz(seiten: TestClient, abgeglichen: dict) -> None:
    antwort = seiten.post("/api/buchplanung/fach", json={
        "schuljahr": "2026/2027", "fach": "Deutsch", "kuerzel": "ABC",
    })
    assert antwort.status_code == 400
    assert antwort.json()["fehler"] == "Es fehlt eine gültige Änderungszeit der geladenen Datei."


# ── Die Bedienelemente in den Bücherlisten-Seiten ────────────────────────────


def test_ohne_datei_steht_der_knopf_zum_aktualisieren(seiten: TestClient) -> None:
    _anmelden(seiten)
    text = seiten.get("/buecherliste/fach").text
    assert 'data-planung="abgleich"' in text
    assert 'class="hinweis"' not in text


def test_verlagsseite_bietet_keine_preispruefung(seiten: TestClient, abgeglichen: dict) -> None:
    text = seiten.get("/buecherliste/verlag/Klett").text
    assert 'data-planung="preise"' not in text
    assert 'data-planung="preis"' not in text
    assert ">Status<" not in text
    # Die Fach-Bedienelemente gehören nicht auf diese Seite.
    assert 'data-planung="fach"' not in text
    assert 'data-planung="aufklappen"' not in text


def test_fachseite_bietet_freigabe_und_planungsmenue(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Die Buchzeile ist der Knopf, und das Menü steht fertig als Vorlage da."""
    text = seiten.get("/buecherliste/fach/Deutsch").text
    assert 'data-planung="fach"' in text                     # Freigabe, oben
    assert 'class="aufklappbar"' in text                     # die Zeile öffnet das Menü
    assert 'data-planung="aufklappen"' in text
    assert 'class="planung-vorlage"' in text
    assert '<dialog id="planungsmenue"' in text
    assert 'data-planung="jahrgang-anfuegen"' in text        # "+ Jahrgang"
    assert 'data-planung="speichern"' in text
    assert 'data-planung="abbrechen"' in text
    # Gemeldet wird im Menü, nicht auf der Seite dahinter - die ist beim
    # offenen Dialog abgedunkelt.
    assert "data-planung-meldung" in text
    assert 'data-planung-feld="eingefuehrt_ab"' in text
    assert 'data-planung-feld="ausgemustert_nach"' in text
    assert 'data-planung-feld="bemerkung"' in text
    # Kürzel und Datum stehen nur oben an der Freigabe, nicht je Zeile: die
    # Fachkonferenzleitung bestätigt die Liste als Ganzes.
    assert text.count('data-planung-feld="kuerzel"') == 1
    assert text.count('data-planung-feld="datum"') == 1
    # Preise werden beim Verlag geprüft, nicht beim Fach.
    assert 'data-planung="preis"' not in text


def test_jahrgang_eines_laufenden_buchs_traegt_nur_die_ausmusterung(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Jahrgang 5 steht in einer Bücherliste - daran ist nichts mehr zu planen.

    Die Einführung ist Geschichte und darf nicht als Eingabefeld aussehen; der
    Jahrgang selbst schon gar nicht. Offen ist nur noch die Ausmusterung.
    """
    text = seiten.get("/buecherliste/fach/Deutsch").text
    vorlage = text.split('class="planung-vorlage"')[1].split("</template>")[0]
    zeile = " ".join(vorlage.split("<tr data-planung-zeile")[1].split("</tr>")[0].split())
    assert "data-aktuell" in zeile
    # Jahrgang und Einführung nur als verstecktes Feld - der Server bekommt sie
    # zurück, aber niemand tippt sie um.
    assert 'type="hidden" data-planung-feld="jahrgang"' in zeile
    assert 'type="hidden" data-planung-feld="eingefuehrt_ab"' in zeile
    # Offen ist die Ausmusterung, und die Bemerkung zu dieser Zeile.
    assert 'data-planung-feld="ausgemustert_nach"' in zeile
    assert "disabled" not in zeile
    assert 'data-planung-feld="bemerkung"' in zeile
    # Ein laufender Jahrgang lässt sich nicht wegklicken.
    assert 'data-planung="jahrgang-entfernen"' not in zeile


def test_fachseite_zeigt_die_freigabe_und_ihren_verfall(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    seiten.post("/api/buchplanung/fach", json={
        "schuljahr": "2026/2027", "fach": "Deutsch", "kuerzel": "ABC",
        "mtime": abgeglichen["mtime"],
    })
    assert "label-success" in seiten.get("/buecherliste/fach/Deutsch").text

    _BUECHER["2026/2027"][5].append(
        ("9783060000012", "Deutschbuch 6", ["Deutsch"], "Cornelsen", 23.0, True))
    try:
        seiten.post("/api/buchplanung/abgleich", json={})
        text = seiten.get("/buecherliste/fach/Deutsch").text
    finally:
        _BUECHER["2026/2027"][5].pop()
    assert "teilweise" in text
    assert "Deutschbuch 6 (Jg. 5)" in text


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
    """Ohne lesbare Datei zeigt die Seite IServ - und sagt, warum."""
    _datei(einstellungen).write_bytes(b"kein Excel")
    antwort = seiten.get("/buecherliste/fach/Deutsch")
    assert antwort.status_code == 200
    assert "Deutschbuch 5" in antwort.text
    assert "nicht lesbar" in antwort.text


def test_vorjahresbuch_steht_mit_dem_vorjahr_als_ausmusterung_in_der_datei(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """ALT stand nur 2025/2026 in Chemie/Jg. 9: der Abgleich trägt die Ausmusterung ein."""
    buch = next(b for b in abgeglichen["planung"]["buecher"] if b["isbn"] == ALT)
    zeile = next(z for z in buch["planung"] if z["jahrgang"] == 9)
    assert zeile["ausgemustert_nach"] == "2025/2026"


def test_fach_seite_listet_nur_vollstaendig_ausgemusterte_buecher(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Terra ist in Erdkunde nur in Jg. 5 ausgelaufen, Jg. 6 bleibt: nicht aufgeführt."""
    # Ohne Ausmusterung fehlt der ganze Abschnitt, samt Überschrift.
    erdkunde = seiten.get("/buecherliste/fach/Erdkunde").text
    assert "Ausmusterungen zu diesem Schuljahr" not in erdkunde
    latein = seiten.get("/buecherliste/fach/Latein").text
    assert "Ausmusterungen zu diesem Schuljahr" not in latein


def _mustere_terra_aus(seiten: TestClient, mtime: float, *faecher: str) -> float:
    """Jg. 5 und 6 von Terra in diesen Fächern: ausgemustert nach dem Vorjahr."""
    for fach in faecher:
        antwort = seiten.post("/api/buchplanung/buch", json={
            "schuljahr": "2026/2027", "isbn": TERRA, "fach": fach,
            "zeilen": [{"jahrgang": 5, "ausgemustert_nach": "2025/2026"},
                       {"jahrgang": 6, "ausgemustert_nach": "2025/2026"}],
            "mtime": mtime,
        })
        assert antwort.status_code == 200, antwort.text
        mtime = antwort.json()["mtime"]
    return mtime


def _haupttabelle(text: str) -> str:
    return text.split("Ausmusterungen zu diesem Schuljahr")[0]


def test_ausgemustertes_buch_laesst_sich_wie_die_anderen_planen(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Läuft Terra in Erdkunde ganz mit dem Vorjahr aus, steht es klickbar in der Tabelle."""
    _mustere_terra_aus(seiten, abgeglichen["mtime"], "Erdkunde")
    text = seiten.get("/buecherliste/fach/Erdkunde").text
    assert "Ausmusterungen zu diesem Schuljahr" in text
    tabelle = text.split('id="ausmusterungen"')[1]
    assert 'data-planung="aufklappen"' in tabelle
    assert f'<template class="planung-vorlage" data-isbn="{TERRA}" data-fach="Erdkunde">' in text
    assert 'data-planung-feld="anzahl"' in text.split("planung-vorlage")[-1]


def test_ganz_ausgemustertes_buch_steht_nur_unter_ausmusterungen_mit_ruecklage(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    mtime = _mustere_terra_aus(seiten, abgeglichen["mtime"], "Erdkunde")
    seiten.post("/api/buchplanung/ruecklage", json={
        "schuljahr": "2026/2027", "isbn": TERRA, "fach": "Erdkunde", "anzahl": 4,
        "mtime": mtime,
    })
    text = seiten.get("/buecherliste/fach/Erdkunde").text
    # IServ führt Terra noch in Jg. 6 - in der normalen Liste steht es trotzdem nicht.
    assert f'<tr data-isbn="{TERRA}"' not in _haupttabelle(text)
    tabelle = text.split('id="ausmusterungen"')[1].split("</table>")[0]
    assert f'data-isbn="{TERRA}"' in tabelle
    assert "<th data-sort=\"zahl\">Rücklagen</th>" in tabelle
    assert '<td data-wert="4">4</td>' in tabelle
    # Weil IServ es in Erdkunde Jg. 6 noch führt, ist die Ausmusterung rot markiert.
    assert 'zeile-ausmusterung' in tabelle
    assert '<span class="wert-ausmusterung">6</span>' in tabelle
    # Dieselben Spalten wie die normale Liste, das Ende steht am Jahrgang.
    assert re.findall(r"<th [^>]*>([^<]*)</th>", tabelle) == [
        "Titel", "Jahrgang", "Verlag", "ISBN", "Neupreis", "Leihgebühr", "Leihbar", "Rücklagen"]
    assert "5 (bis 2025/2026), 6 (bis 2025/2026)" in _ohne_tags(tabelle)


def test_ein_ueberall_ausgemustertes_buch_das_iserv_noch_fuehrt_ist_ganz_rot(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Excel führt Terra dieses Jahr nirgends mehr, IServ schon: die ganze Zeile rot."""
    _mustere_terra_aus(seiten, abgeglichen["mtime"], "Erdkunde", "Politik")
    for fach in ("Erdkunde", "Politik"):
        tabelle = seiten.get(f"/buecherliste/fach/{fach}").text.split('id="ausmusterungen"')[1]
        assert "reihe-weg" in _zeile_von(tabelle, TERRA)
    # IServ führt Terra dieses Jahr in Jg. 6.
    assert "reihe-weg" in _zeile_von(seiten.get("/buecherliste/jahrgang/6").text, TERRA)


def test_buch_das_in_einem_anderen_fach_bleibt_kommt_trotzdem_zur_ausmusterung(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """In Erdkunde ausgelaufen, in Politik weiter im Einsatz: in Erdkunde „Ausmusterung“."""
    _mustere_terra_aus(seiten, abgeglichen["mtime"], "Erdkunde")
    erdkunde = seiten.get("/buecherliste/fach/Erdkunde").text
    assert f'<tr data-isbn="{TERRA}"' not in _haupttabelle(erdkunde)
    assert f'data-isbn="{TERRA}"' in erdkunde.split('id="ausmusterungen"')[1]
    # Nur in Erdkunde ausgemustert, nicht die ganze Reihe: keine hinterlegte Zeile.
    assert "reihe-weg" not in erdkunde.split('id="ausmusterungen"')[1]
    politik = seiten.get("/buecherliste/fach/Politik").text
    assert "Ausmusterungen zu diesem Schuljahr" not in politik
    assert f'<tr data-isbn="{TERRA}"' in politik


def test_buch_das_im_selben_fach_weiterlaeuft_steht_in_der_normalen_liste(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Terra: in Erdkunde Jg. 5 mit dem Vorjahr ausgelaufen, Jg. 6 läuft weiter."""
    text = seiten.get("/buecherliste/fach/Erdkunde").text
    assert "Ausmusterungen zu diesem Schuljahr" not in text
    assert f'<tr data-isbn="{TERRA}"' in text
    assert "5 (bis 2025/2026), 6" in text


def test_handeingetragene_ausmusterung_bleibt_beim_naechsten_abgleich(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    seiten.post("/api/buchplanung/planung", json={
        "schuljahr": "2026/2027", "isbn": ALT, "fach": "Chemie", "jahrgang": 9,
        "ausgemustert_nach": "2024/2025", "mtime": abgeglichen["mtime"],
    })
    neu = seiten.post("/api/buchplanung/abgleich", json={"schuljahr": "2026/2027"}).json()
    buch = next(b for b in neu["planung"]["buecher"] if b["isbn"] == ALT)
    assert next(z for z in buch["planung"] if z["jahrgang"] == 9)["ausgemustert_nach"] == "2024/2025"


# ── Buchreihe: Titel, Verlag, Preise im Menü korrigieren ─────────────────────


def _buchreihe(titel: str, verlag: str, neupreis: float | None = 22.5,
               leihgebuehr: float | None = 5.0) -> dict:
    return {"titel": titel, "verlag": verlag, "neupreis": neupreis, "leihgebuehr": leihgebuehr}


def _korrigiere_deutsch(seiten: TestClient, mtime: float, **felder) -> dict:
    antwort = seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "fach": "Deutsch",
        "zeilen": [{"jahrgang": 5}],
        "buchreihe": {**_buchreihe("Deutschbuch 5", "Cornelsen"), **felder},
        "mtime": mtime,
    })
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


def test_das_menue_zeigt_die_buchreihe_vor_der_planung(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    text = seiten.get("/buecherliste/fach/Deutsch").text
    vorlage = text.split(f'data-isbn="{DEUTSCH}" data-fach="Deutsch">')[1].split("</template>")[0]
    # Erst die Buchreihe, dann Einführung/Ausmusterung, dann die Rücklage.
    assert vorlage.index("data-buchreihe") < vorlage.index("Einführung und Ausmusterung") \
        < vorlage.index("Rücklage für")
    for feld in ("isbn", "titel", "verlag", "neupreis", "leihgebuehr"):
        assert f'data-buchreihe-feld="{feld}"' in vorlage
    assert 'value="22.50"' in vorlage
    # Die ISBN ist gesperrt (grau, nicht anklickbar): sie ist der Schlüssel.
    isbn_feld = vorlage.split('data-buchreihe-feld="isbn"')[1].split(">")[0]
    assert "disabled" in isbn_feld
    # Die Verlage für die Vorschläge, einmal je Seite.
    verlage = text.split('id="planung-verlage">')[1].split("</script>")[0]
    assert json.loads(verlage) == ["Cornelsen", "Klett", "Langenscheidt", "Westermann"]


def test_korrigierte_buchreihe_steht_in_allen_bucherlisten(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    stand = _korrigiere_deutsch(seiten, abgeglichen["mtime"],
                                titel="Deutschbuch 5 NRW", verlag="Cornelsen Schulverlage",
                                neupreis=24.0)
    buch = next(b for b in stand["planung"]["buecher"] if b["isbn"] == DEUTSCH)
    assert buch["titel"] == "Deutschbuch 5 NRW"
    # Die Datei nennt IServ nicht mehr, nur ihre eigenen Werte.
    assert "iserv" not in buch

    fach = seiten.get("/buecherliste/fach/Deutsch").text
    assert "Deutschbuch 5 NRW" in fach
    assert "24,00" in fach
    # Das Menü nennt, was IServ sagt - live verglichen.
    assert "in IServ: Deutschbuch 5" in fach
    assert "in IServ: 22,50&nbsp;€" in fach

    verlag = seiten.get("/buecherliste/verlag").text
    assert "Cornelsen Schulverlage" in verlag
    assert seiten.get("/buecherliste/verlag/Cornelsen Schulverlage").status_code == 200


def test_korrektur_uebersteht_den_abgleich(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    _korrigiere_deutsch(seiten, abgeglichen["mtime"], titel="Deutschbuch 5 NRW")

    neu = seiten.post("/api/buchplanung/abgleich", json={"schuljahr": "2026/2027"}).json()
    buch = next(b for b in neu["planung"]["buecher"] if b["isbn"] == DEUTSCH)
    assert buch["titel"] == "Deutschbuch 5 NRW"
    assert not neu["planung"]["warnungen"]
    # Die Abweichung zeigt die Seite, live gegen IServ.
    assert "in IServ: Deutschbuch 5" in seiten.get("/buecherliste/fach/Deutsch").text


def test_eine_isbn_im_koerper_der_buchreihe_aendert_nichts(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Die ISBN steht im Menü nur zum Lesen; der Server nimmt keine an."""
    stand = _korrigiere_deutsch(seiten, abgeglichen["mtime"], isbn="9783161484100")
    assert any(b["isbn"] == DEUTSCH for b in stand["planung"]["buecher"])
    assert not any(b["isbn"] == "9783161484100" for b in stand["planung"]["buecher"])


def test_leerer_titel_wird_mit_einem_satz_abgewiesen(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    antwort = seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "fach": "Deutsch", "zeilen": [],
        "buchreihe": _buchreihe("", "Cornelsen"),
        "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 400
    assert antwort.json()["fehler"] == "Bitte einen Titel eintragen."


# ── Ein Buch hinzufügen ──────────────────────────────────────────────────────

NEU = "9783161484100"


def _hinzufuegen(seiten: TestClient, mtime: float, isbn: str, fach: str = "Deutsch",
                 **buchreihe) -> object:
    return seiten.post("/api/buchplanung/buch/neu", json={
        "schuljahr": "2026/2027", "isbn": isbn, "fach": fach,
        "zeilen": [{"jahrgang": 7, "eingefuehrt_ab": "2027/2028"}],
        "buchreihe": {**_buchreihe("Terra 5/6", "Klett", 25.0), **buchreihe},
        "mtime": mtime,
    })


def test_fachseite_bietet_buch_hinzufuegen_mit_vorschlaegen_aus_anderen_faechern(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    text = seiten.get("/buecherliste/fach/Deutsch").text
    assert 'data-planung="buch-neu"' in text
    vorlage = text.split('id="planung-neu-vorlage"')[1].split("</template>")[0]
    # Dasselbe Menü, aber die ISBN ist frei und schlägt vor.
    isbn_feld = vorlage.split('data-buchreihe-feld="isbn"')[1].split(">")[0]
    assert "disabled" not in isbn_feld
    assert 'data-vorschlag="isbn"' in isbn_feld
    assert 'data-vorschlag="titel"' in vorlage
    assert "Rücklage" not in vorlage
    vorschlaege = json.loads(text.split('id="planung-buecher">')[1].split("</script>")[0])
    isbns = {buch["isbn"] for buch in vorschlaege}
    # Die Bücher anderer Fächer (auch des Vorjahrs), nicht das eigene.
    assert isbns == {TERRA, ALT, KAUF}
    terra = next(buch for buch in vorschlaege if buch["isbn"] == TERRA)
    assert terra["titel"] == "Terra 5/6"
    assert terra["faecher"] == ["Erdkunde", "Politik"]
    assert terra["neupreis"] == 25.0

    # Nur in der Fach-Ansicht, und erst mit Datei.
    assert 'data-planung="buch-neu"' not in seiten.get("/buecherliste/verlag/Klett").text


def test_ein_hinzugefuegtes_buch_steht_danach_in_der_liste(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    antwort = _hinzufuegen(seiten, abgeglichen["mtime"], "978-3-12-100056-2")
    assert antwort.status_code == 200, antwort.text

    text = seiten.get("/buecherliste/fach/Deutsch").text
    zeile = text.split(f'<tr data-isbn="{TERRA}"')[1].split("</tr>")[0]
    assert "Terra 5/6" in zeile
    assert "7 (ab 2027/2028)" in zeile
    assert 'data-planung="aufklappen"' in zeile
    # Und es lässt sich öffnen wie jede andere Zeile.
    assert f'data-isbn="{TERRA}" data-fach="Deutsch">' in text
    # Aus den Vorschlägen ist es verschwunden.
    vorschlaege = json.loads(text.split('id="planung-buecher">')[1].split("</script>")[0])
    assert TERRA not in {buch["isbn"] for buch in vorschlaege}
    # In Erdkunde bleibt alles, wie es war.
    assert "7 (ab" not in seiten.get("/buecherliste/fach/Erdkunde").text


def test_eine_neue_isbn_steht_als_nicht_in_iserv_in_der_liste_und_bleibt(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    stand = _hinzufuegen(seiten, abgeglichen["mtime"], NEU, titel="Neues Deutschbuch 7",
                         verlag="Cornelsen").json()
    assert any(b["isbn"] == NEU for b in stand["planung"]["buecher"])

    text = seiten.get("/buecherliste/fach/Deutsch").text
    zeile = text.split(f'<tr data-isbn="{NEU}"')[1].split("</tr>")[0]
    assert "Neues Deutschbuch 7" in zeile
    assert "nicht in IServ" in zeile
    assert "Dieses Buch steht nicht in IServ" in text

    neu = seiten.post("/api/buchplanung/abgleich", json={"schuljahr": "2026/2027"}).json()
    assert any(b["isbn"] == NEU for b in neu["planung"]["buecher"])
    assert not neu["planung"]["warnungen"]


def test_hinzufuegen_meldet_fehler_als_satz(seiten: TestClient, abgeglichen: dict) -> None:
    antwort = _hinzufuegen(seiten, abgeglichen["mtime"], DEUTSCH)
    assert antwort.status_code == 400
    assert "gehört schon zum Fach Deutsch" in antwort.json()["fehler"]

    antwort = _hinzufuegen(seiten, abgeglichen["mtime"], "12345")
    assert antwort.status_code == 400
    assert "keine gültige ISBN" in antwort.json()["fehler"]


def test_hinzufuegen_mit_veralteter_mtime_ist_409(seiten: TestClient, abgeglichen: dict) -> None:
    assert _hinzufuegen(seiten, abgeglichen["mtime"], TERRA).status_code == 200
    assert _hinzufuegen(seiten, abgeglichen["mtime"], NEU).status_code == 409


def test_das_menue_heisst_wie_in_iserv_und_fragt_nach_leihbar(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    text = seiten.get("/buecherliste/fach/Deutsch").text
    vorlage = text.split(f'data-isbn="{DEUTSCH}" data-fach="Deutsch">')[1].split("</template>")[0]
    assert "Buchreihe bearbeiten" in vorlage
    # Erst die Buchreihe, dann Leihbar, dann Einführung und Ausmusterung.
    assert vorlage.index('data-buchreihe-feld="leihgebuehr"') \
        < vorlage.index('data-buchreihe-feld="leihbar"') \
        < vorlage.index("Einführung und Ausmusterung")
    leihbar = vorlage.split('data-buchreihe-feld="leihbar"')[1].split(">")[0]
    assert "checked" in leihbar
    neu = text.split('id="planung-neu-vorlage"')[1].split("</template>")[0]
    assert "Buch hinzufügen" in neu
    assert 'data-buchreihe-feld="leihbar"' in neu


def test_korrigiertes_leihbar_steht_in_der_liste(seiten: TestClient, abgeglichen: dict) -> None:
    antwort = seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": KAUF, "fach": "Latein",
        "zeilen": [{"jahrgang": 5}],
        "buchreihe": {**_buchreihe("Wörterbuch Latein", "Langenscheidt", 19.9), "leihbar": True},
        "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    text = seiten.get("/buecherliste/fach/Latein").text
    zeile = text.split(f'<tr data-isbn="{KAUF}"')[1].split("</tr>")[0]
    assert 'data-wert="1"' in zeile
    assert "in IServ: nein" in text
    # Jetzt gibt es auch den Rücklage-Block.
    assert "Rücklage für die Fachschaft Latein" in text


# ── Die Datei als Soll, IServ als Vergleich ──────────────────────────────────


def _iserv_aendern(monkeypatch: pytest.MonkeyPatch, jahrgang: int,
                   buecher: list[tuple[str, str, list[str], str, float, bool]]) -> None:
    """Ändert, was der Fake für dieses Schuljahr in IServ listet - erst NACH dem Abgleich."""
    monkeypatch.setitem(_BUECHER["2026/2027"], jahrgang, buecher)


def _zeile_von(text: str, isbn: str) -> str:
    return text.split(f'<tr data-isbn="{isbn}"')[1].split("</tr>")[0]


def _ohne_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _markiert(text: str) -> bool:
    return any(f'{art}"' in text or f"{art} " in text
               for art in ("aenderung", "einfuehrung", "ausmusterung"))


def test_ohne_abweichung_stimmt_die_seite_mit_iserv_ueberein(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    text = seiten.get("/buecherliste/fach/Deutsch").text
    assert not _markiert(text)
    assert not re.search(r"reihe-(neu|weg)", text)


def test_ein_anderer_preis_in_iserv_wird_markiert_und_die_datei_gezeigt(
    seiten: TestClient, abgeglichen: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _iserv_aendern(monkeypatch, 5, [
        (DEUTSCH, "Deutschbuch 5", ["Deutsch"], "Cornelsen", 24.0, True),
        (KAUF, "Wörterbuch Latein", ["Latein"], "Langenscheidt", 19.9, False)])
    text = seiten.get("/buecherliste/fach/Deutsch").text
    zeile = _zeile_von(text, DEUTSCH)
    assert "22,50" in zeile
    assert 'class="aenderung" title="In IServ: 24,00 €"' in zeile
    assert "zeile-aenderung" in zeile and not re.search(r"reihe-(neu|weg)", zeile)
    # Graue Hinweiskästen gibt es auf den Bücherlisten nicht.
    assert 'class="hinweis"' not in text

    # Die Übersicht trägt keinen Hinweis auf die Abweichung.
    assert "weicht von IServ ab" not in seiten.get("/buecherliste/fach").text
    # Auch Verlag und Jahrgang zeigen die Datei.
    assert "22,50" in _zeile_von(seiten.get("/buecherliste/verlag/Cornelsen").text, DEUTSCH)
    assert "22,50" in _zeile_von(seiten.get("/buecherliste/jahrgang/5").text, DEUTSCH)


def test_ein_buch_nur_in_iserv_steht_markiert_und_ohne_menue(
    seiten: TestClient, abgeglichen: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    neu = "9783060000012"
    _iserv_aendern(monkeypatch, 5, [*_BUECHER["2026/2027"][5],
                                    (neu, "Deutschbuch 6", ["Deutsch"], "Cornelsen", 23.0, True)])
    text = seiten.get("/buecherliste/fach/Deutsch").text
    zeile = _zeile_von(text, neu)
    # Die ganze Reihe führt nur IServ: roter Strich, ganze Zeile rot hinterlegt.
    assert "zeile-ausmusterung reihe-weg" in zeile
    assert '<span class="wert-ausmusterung">5</span>' in zeile
    assert "aufklappbar" not in zeile
    assert f'data-isbn="{neu}" data-fach="Deutsch">' not in text


def test_ein_aus_iserv_verschwundenes_buch_fehlt_in_iserv(
    seiten: TestClient, abgeglichen: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _iserv_aendern(monkeypatch, 5, [
        (KAUF, "Wörterbuch Latein", ["Latein"], "Langenscheidt", 19.9, False)])
    zeile = _zeile_von(seiten.get("/buecherliste/fach/Deutsch").text, DEUTSCH)
    # In keiner IServ-Liste mehr, die Buchreihe gibt es aber im Inventar: die
    # Zeile ist nicht hinterlegt, nur der Jahrgang blau.
    assert "zeile-einfuehrung" in zeile and "reihe-" not in zeile
    assert '<span class="wert-einfuehrung">5</span>' in zeile
    assert 'class="aenderung"' not in zeile
    # Das Menü bleibt: das Buch steht in der Datei.
    assert "aufklappbar" in zeile

    jahrgang = seiten.get("/buecherliste/jahrgang/5").text
    assert "Nicht in IServ" in jahrgang
    fehlend = _zeile_von(jahrgang.split("Nicht in IServ")[1], DEUTSCH)
    assert "zeile-einfuehrung" in fehlend and "reihe-" not in fehlend

    # Weicht die Datei von der Buchreihe im Inventar ab, ist das gelb.
    _korrigiere_deutsch(seiten, abgeglichen["mtime"], titel="Deutschbuch 5 NRW")
    zeile = _zeile_von(seiten.get("/buecherliste/fach/Deutsch").text, DEUTSCH)
    assert 'class="aenderung"' in zeile and "In IServ: Deutschbuch 5" in zeile


def test_eine_neue_reihe_ohne_buchreihe_im_inventar_ist_ganz_blau(
    seiten: TestClient, abgeglichen: dict,
) -> None:
    """Die ISBN gibt es in IServ gar nicht: einheitlich kräftig blau.

    Deutschbuch 5 aus dem vorigen Test steht dagegen im Inventar und bleibt
    hell blau mit kräftigem Fach und Jahrgang (``reihe-neu``).
    """
    antwort = seiten.post("/api/buchplanung/buch/neu", json={
        "schuljahr": "2026/2027", "isbn": NEU, "fach": "Deutsch",
        "zeilen": [{"jahrgang": 5, "eingefuehrt_ab": "2026/2027"}],
        "buchreihe": _buchreihe("Neues Deutschbuch", "Cornelsen"),
        "mtime": abgeglichen["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    zeile = _zeile_von(seiten.get("/buecherliste/fach/Deutsch").text, NEU)
    assert "reihe-unbekannt" in zeile and "reihe-neu" not in zeile
    fehlend = seiten.get("/buecherliste/jahrgang/5").text.split("Nicht in IServ")[1]
    assert "reihe-unbekannt" in _zeile_von(fehlend, NEU)


def test_ein_zusaetzlicher_jahrgang_in_iserv_markiert_die_jahrgangsspalte(
    seiten: TestClient, abgeglichen: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _iserv_aendern(monkeypatch, 6, [*_BUECHER["2026/2027"][6],
                                    (DEUTSCH, "Deutschbuch 5", ["Deutsch"], "Cornelsen", 22.5, True)])
    zeile = _zeile_von(seiten.get("/buecherliste/fach/Deutsch").text, DEUTSCH)
    assert 'class="ausmusterung" title="Ausmusterung, in IServ noch: Deutsch Jg. 6"' in zeile
    assert '<span class="wert-ausmusterung">6</span>' in zeile
    assert "zeile-ausmusterung" in zeile and not re.search(r"reihe-(neu|weg)", zeile)
    # Auf der Jahrgangsseite steht es beim Fach.
    zeile = _zeile_von(seiten.get("/buecherliste/jahrgang/6").text, DEUTSCH)
    assert "Ausmusterung, in IServ noch: Deutsch Jg. 6" in zeile
    assert '<span class="wert-ausmusterung">Deutsch</span>' in zeile


def test_eine_eingefuehrte_planung_gleicht_iserv(
    seiten: TestClient, abgeglichen: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Eingeführt ab diesem Schuljahr heißt: laut Datei dieses Jahr da."""
    seiten.post("/api/buchplanung/buch", json={
        "schuljahr": "2026/2027", "isbn": DEUTSCH, "fach": "Deutsch",
        "zeilen": [{"jahrgang": 5}, {"jahrgang": 6, "eingefuehrt_ab": "2026/2027"}],
        "mtime": abgeglichen["mtime"],
    })
    _iserv_aendern(monkeypatch, 6, [*_BUECHER["2026/2027"][6],
                                    (DEUTSCH, "Deutschbuch 5", ["Deutsch"], "Cornelsen", 22.5, True)])
    text = seiten.get("/buecherliste/fach/Deutsch").text
    assert not _markiert(text)


def test_der_abgleich_zieht_die_datei_nicht_auf_iserv_nach(
    seiten: TestClient, abgeglichen: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _iserv_aendern(monkeypatch, 5, [
        (DEUTSCH, "Deutschbuch 5", ["Deutsch"], "Cornelsen", 24.0, True),
        (KAUF, "Wörterbuch Latein", ["Latein"], "Langenscheidt", 19.9, False)])
    assert seiten.post("/api/buchplanung/abgleich", json={}).status_code == 200
    zeile = _zeile_von(seiten.get("/buecherliste/fach/Deutsch").text, DEUTSCH)
    assert "22,50" in zeile and "In IServ: 24,00 €" in zeile



class _Zellen(HTMLParser):
    """Zählt je Tabelle die Spaltenköpfe und je Zeile die Zellen."""

    def __init__(self) -> None:
        super().__init__()
        self.tabellen: list[tuple[list[int], list[tuple[str | None, int]]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.tabellen.append(([0], []))
        elif not self.tabellen:
            return
        elif tag == "th":
            self.tabellen[-1][0][0] += 1
        elif tag == "tr":
            self.tabellen[-1][1].append((dict(attrs).get("data-isbn"), 0))
        elif tag == "td":
            isbn, anzahl = self.tabellen[-1][1][-1]
            self.tabellen[-1][1][-1] = (isbn, anzahl + 1)


@pytest.mark.parametrize("ansicht", ["fach/Deutsch", "verlag/Cornelsen", "jahrgang/5"])
def test_markierte_zeilen_haben_alle_zellen(
    seiten: TestClient, abgeglichen: dict, monkeypatch: pytest.MonkeyPatch, ansicht: str,
) -> None:
    """Eine markierte Zelle darf ihre Nachbarn nicht verschlucken: ``<tdclass=…>``
    ist für den Browser keine Zelle, und alles dahinter rückt eine Spalte vor."""
    _iserv_aendern(monkeypatch, 5, [
        (DEUTSCH, "Deutschbuch 5 (alt)", ["Deutsch"], "Cornelsen", 24.0, False),
        (KAUF, "Wörterbuch Latein", ["Latein"], "Langenscheidt", 19.9, False)])
    text = seiten.get(f"/buecherliste/{ansicht}").text
    assert "<tdclass" not in text
    zellen = _Zellen()
    zellen.feed(text)
    for (koepfe,), zeilen in zellen.tabellen:
        for isbn, anzahl in zeilen:
            assert anzahl in (0, koepfe), f"{isbn}: {anzahl} Zellen, {koepfe} Spalten"
