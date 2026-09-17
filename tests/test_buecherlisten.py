"""Die Bücherlisten nach Fach, Verlag und Jahrgang - Domäne und Seiten.

Der Fake-Client liefert Daten in der Form, die IServ am 2026-09-17 tatsächlich
geschickt hat (``GET /schoolyears/:id/booklists/`` und ``…/booklists/:id``),
auf das Nötigste gekürzt.
"""
from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.buecherlisten import (
    OHNE_FACH,
    finde_gruppe,
    gruppen_nach_fach,
    gruppen_nach_verlag,
    lade_buecherlisten,
)
from app.main import create_app
from conftest import TEST_BASIS_URL


def _item(isbn: str, titel: str, faecher: list[str], verlag: str, leihbar: bool = True) -> dict:
    return {
        "series": isbn,
        "borrowable": leihbar,
        "series_data": {
            "isbn": isbn, "title": titel, "subjectsFlat": faecher, "publisher": verlag,
            "price": 26.95, "fee": 5.4,
        },
    }


_CHEMIE_5_6 = _item("9783127563313", "Elemente Chemie 5/6", ["Chemie"], "Klett")
_FORMELN = _item("9783661670003", "Formelsammlung", ["Mathematik", "Chemie"], "C. C. Buchner",
                 leihbar=False)

_DETAILS = {
    1295: {"sections": [
        {"title": "default", "position": 0, "options": [{"title": "default", "items": [
            _CHEMIE_5_6,
            _item("9783661310510", "Das waren Zeiten 1", ["Geschichte"], "Buchner"),
        ]}]},
        {"title": "Religion und W & N", "position": 1, "options": [
            {"title": "Religion", "items": [_item("9783120066088", "Moment mal! 1", ["Religion"], "Klett")]},
            {"title": "Werte & Normen", "items": [_item("9783661211015", "LebensWert 1", [], "")]},
        ]},
    ]},
    1296: {"sections": [
        {"title": "default", "position": 0, "options": [{"title": "default", "items": [
            _CHEMIE_5_6, _FORMELN,
        ]}]},
    ]},
}


def _kopf(listen_id: int, jahrgang: int, paket: bool = True) -> dict:
    return {
        "id": listen_id, "title": f"Jahrgang {jahrgang}", "grade": jahrgang, "package": paket,
        "package_fee": None, "e_begin": "2026-05-06T00:00:00.000Z",
        "e_end": "2026-06-07T00:00:00.000Z", "e_payment_deadline": "2026-06-10T00:00:00.000Z",
        "released": True, "Schoolyear": {"enrollment_enabled": True},
        "BankAccount": {"bank": "Sparkasse Osterode"},
    }


class _Schuljahre:
    def get_current(self) -> dict:
        return {"id": "2026/2027", "name": "Schuljahr 26/27"}

    def get_booklists(self, schoolyear_id: str) -> list[dict]:
        # Absichtlich nicht nach Jahrgang sortiert.
        return [_kopf(1296, 6, paket=False), _kopf(1295, 5)]

    def get_booklist(self, schoolyear_id: str, booklist_id: int) -> dict:
        return _DETAILS[booklist_id]


class FakeBuecherlistenClient:
    schoolyears = _Schuljahre()

    def __init__(self, *args, **kwargs) -> None:
        pass

    def login(self) -> bool:
        return True


@pytest.fixture()
def daten():
    return lade_buecherlisten(FakeBuecherlistenClient(), heute=date(2026, 9, 17))


# ── Domäne ───────────────────────────────────────────────────────────────────

def test_listen_sind_nach_jahrgang_sortiert_und_tragen_die_kopfdaten(daten):
    assert [liste.jahrgang for liste in daten.listen] == [5, 6]
    liste = daten.listen[0]
    assert liste.leihmodalitaet == "Paket"
    assert liste.beginn == date(2026, 5, 6)
    assert liste.zahlungsfrist == date(2026, 6, 10)
    assert liste.bank == "Sparkasse Osterode"
    assert daten.schuljahr == "Schuljahr 26/27"


def test_anmeldung_ist_nur_im_zeitraum_moeglich():
    im_zeitraum = lade_buecherlisten(FakeBuecherlistenClient(), heute=date(2026, 5, 20))
    danach = lade_buecherlisten(FakeBuecherlistenClient(), heute=date(2026, 9, 17))
    assert im_zeitraum.listen[0].anmeldung_moeglich is True
    assert danach.listen[0].anmeldung_moeglich is False


def test_grundpaket_und_wahlbereiche_werden_getrennt(daten):
    liste = daten.liste_fuer_jahrgang(5)
    assert liste.grundpaket.titel == "Grundpaket"
    assert [b.titel for b in liste.wahlbereiche] == ["Religion und W & N"]
    assert [o.titel for o in liste.wahlbereiche[0].optionen] == ["Religion", "Werte & Normen"]


def test_alle_buecher_sind_grundpaket_und_dann_die_wahlbereiche(daten):
    titel = [b.titel for b in daten.liste_fuer_jahrgang(5).alle_buecher]
    assert titel == ["Elemente Chemie 5/6", "Das waren Zeiten 1", "Moment mal! 1", "LebensWert 1"]


def test_mehrjahresband_wird_ein_eintrag_mit_beiden_jahrgaengen(daten):
    chemie = finde_gruppe(gruppen_nach_fach(daten), "Chemie")
    elemente = [b for b in chemie.buecher if b.isbn == "9783127563313"]
    assert len(elemente) == 1
    assert elemente[0].jahrgaenge == (5, 6)
    assert elemente[0].jahrgang_anzeige == "5, 6"


def test_buch_mit_zwei_faechern_steht_in_beiden(daten):
    gruppen = gruppen_nach_fach(daten)
    for fach in ("Mathematik", "Chemie"):
        assert "Formelsammlung" in [b.titel for b in finde_gruppe(gruppen, fach).buecher]


def test_faecher_sind_alphabetisch_und_buch_ohne_fach_hat_eine_gruppe(daten):
    namen = [g.name for g in gruppen_nach_fach(daten)]
    assert namen == sorted(namen, key=str.lower)
    assert OHNE_FACH in namen


def test_gruppen_nach_verlag(daten):
    gruppen = gruppen_nach_verlag(daten)
    klett = finde_gruppe(gruppen, "Klett")
    assert {b.titel for b in klett.buecher} == {"Elemente Chemie 5/6", "Moment mal! 1"}


def test_isbn_wird_mit_bindestrichen_angezeigt(daten):
    buch = finde_gruppe(gruppen_nach_fach(daten), "Geschichte").buecher[0]
    assert buch.isbn_anzeige == "978-3-661-31051-0"


# ── Seiten ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def seiten(einstellungen) -> TestClient:
    application = create_app(einstellungen=einstellungen,
                             client_factory=FakeBuecherlistenClient)
    with TestClient(application, base_url=TEST_BASIS_URL) as testclient:
        yield testclient


def _anmelden(client: TestClient) -> None:
    antwort = client.post("/api/anmeldung", json={"benutzer": "b.lehrer", "passwort": "x"})
    assert antwort.status_code == 200, antwort.text


def test_ohne_anmeldung_erscheint_ein_hinweis_statt_json(seiten: TestClient):
    antwort = seiten.get("/buecherliste/fach")
    assert antwort.status_code == 401
    assert "text/html" in antwort.headers["content-type"]
    assert "Programmfenster" in antwort.text


@pytest.mark.parametrize("ansicht, erwartet", [
    ("fach", "/buecherliste/fach/Chemie"),
    ("verlag", "/buecherliste/verlag/Klett"),
    ("jahrgang", "/buecherliste/jahrgang/5"),
])
def test_uebersichten_verlinken_ihre_gruppen(seiten: TestClient, ansicht: str, erwartet: str):
    _anmelden(seiten)
    antwort = seiten.get(f"/buecherliste/{ansicht}")
    assert antwort.status_code == 200
    assert f'href="{erwartet}"' in antwort.text
    assert "label-status" in antwort.text
    assert "Liste hinzufügen" not in antwort.text


def test_jahrgangsuebersicht_hat_die_iserv_spalten(seiten: TestClient):
    _anmelden(seiten)
    text = seiten.get("/buecherliste/jahrgang").text
    for spalte in ("Leihmodalität", "Festpreis", "Anmeldung", "Beginn", "Ende",
                   "Zahlungsfrist", "Bankverbindung", "Status"):
        assert f">{spalte}</th>" in text
    assert "Veröffentlicht" not in text


def test_gruppenseite_zeigt_die_buecher(seiten: TestClient):
    _anmelden(seiten)
    antwort = seiten.get("/buecherliste/verlag/C.%20C.%20Buchner")
    assert antwort.status_code == 200
    assert "Formelsammlung" in antwort.text
    assert "Zurück zur Übersicht" in antwort.text


def test_jahrgangsseite_zeigt_grundpaket_und_wahlbereiche(seiten: TestClient):
    _anmelden(seiten)
    text = seiten.get("/buecherliste/jahrgang/5").text
    assert "Grundpaket" in text and "Wahlbereiche" in text and "Moment mal! 1" in text


@pytest.mark.parametrize("pfad", [
    "/buecherliste/fach/Alchemie", "/buecherliste/jahrgang/42", "/buecherliste/farbe",
])
def test_unbekanntes_ergibt_404_seite(seiten: TestClient, pfad: str):
    _anmelden(seiten)
    assert seiten.get(pfad).status_code == 404


def test_reiter_buecherliste_ist_aktiv(seiten: TestClient):
    _anmelden(seiten)
    text = seiten.get("/buecherliste/fach").text
    assert 'class="dropdown aktiv" id="buecherliste"' in text


# ── Sortieren ────────────────────────────────────────────────────────────────

class _Tabellen(HTMLParser):
    """Sammelt je sortierbarer Tabelle die Überschriften und Zeilen."""

    def __init__(self) -> None:
        super().__init__()
        self.tabellen: list[dict] = []
        self._zeile: list[dict] | None = None

    def handle_starttag(self, tag, attrs):
        werte = dict(attrs)
        if tag == "table" and "sortierbar" in (werte.get("class") or ""):
            self.tabellen.append({"koepfe": [], "zeilen": [], "attrs": werte})
        elif not self.tabellen:
            return
        elif tag == "th":
            self.tabellen[-1]["koepfe"].append(werte)
        elif tag == "tr" and self.tabellen[-1]["koepfe"]:
            self._zeile = []
            self.tabellen[-1]["zeilen"].append(self._zeile)
        elif tag == "td" and self._zeile is not None:
            self._zeile.append(werte)


@pytest.mark.parametrize("pfad", [
    "/buecherliste/fach", "/buecherliste/verlag", "/buecherliste/jahrgang",
    "/buecherliste/fach/Chemie", "/buecherliste/jahrgang/5",
])
def test_jede_tabelle_ist_sortierbar_und_vollstaendig(seiten: TestClient, pfad: str):
    """Der Vertrag mit static/sortieren.js: es greift über den Spaltenindex."""
    _anmelden(seiten)
    text = seiten.get(pfad).text
    assert '<script src="/static/sortieren.js"></script>' in text
    sammler = _Tabellen()
    sammler.feed(text)
    assert sammler.tabellen
    for tabelle in sammler.tabellen:
        assert all(k.get("data-sort") in {"text", "zahl"} for k in tabelle["koepfe"])
        assert tabelle["zeilen"]
        for zeile in tabelle["zeilen"]:
            assert len(zeile) == len(tabelle["koepfe"])


def test_zahlenspalten_haben_zahlen_als_schluessel(seiten: TestClient):
    _anmelden(seiten)
    sammler = _Tabellen()
    sammler.feed(seiten.get("/buecherliste/fach/Chemie").text)
    tabelle = sammler.tabellen[0]
    zahlen = [i for i, k in enumerate(tabelle["koepfe"]) if k["data-sort"] == "zahl"]
    assert zahlen
    for zeile in tabelle["zeilen"]:
        for i in zahlen:
            wert = zeile[i].get("data-wert")
            assert wert is not None and (wert == "" or re.fullmatch(r"-?\d+(\.\d+)?", wert)), wert


# ── Paketansicht ─────────────────────────────────────────────────────────────

def test_paketliste_hat_den_umschalter_und_eine_versteckte_gesamttabelle(seiten: TestClient):
    _anmelden(seiten)
    text = seiten.get("/buecherliste/jahrgang/5").text
    assert 'id="paketansicht"' in text and 'aria-pressed="true"' in text
    assert '<div id="gesamtansicht" hidden>' in text
    assert '<script src="/static/paketansicht.js"></script>' in text
    sammler = _Tabellen()
    sammler.feed(text)
    gesamt = [t for t in sammler.tabellen if "data-gesamt" in t["attrs"]]
    assert len(gesamt) == 1
    assert len(gesamt[0]["zeilen"]) == 4


def test_individuelle_liste_hat_keinen_umschalter(seiten: TestClient):
    _anmelden(seiten)
    text = seiten.get("/buecherliste/jahrgang/6").text
    assert 'id="paketansicht"' not in text
    assert "gesamtansicht" not in text


def test_skripte_finden_ihre_ids_auf_der_paketseite(seiten: TestClient):
    _anmelden(seiten)
    text = seiten.get("/buecherliste/jahrgang/5").text
    statisch = Path(__file__).resolve().parent.parent / "app" / "static"
    js = (statisch / "paketansicht.js").read_text(encoding="utf-8")
    for kennung in re.findall(r'getElementById\("([^"]+)"\)', js):
        assert f'id="{kennung}"' in text, kennung
