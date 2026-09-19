"""Der Reiter „Mehrjahresbände" über HTTP: Seite, Erzeugen, eine Marke ändern.

Ohne Netz: der Fake-Client liefert zwei Schuljahre, deren Unterschied genau die
vier Fälle abdeckt, die die Übersicht kennt. Die Aufgabenfeld-Zuordnung kommt
von der Schulwebsite und wird hier stillgelegt - ein Test, der sie vergäße,
würde bei jedem Lauf trg-osterode.de abfragen.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Einstellungen
from conftest import TEST_BASIS_URL

# Schuljahr -> Jahrgang -> (ISBN, Titel, Fach, leihbar)
_BUECHER: dict[str, dict[int, list[tuple[str, str, str, bool]]]] = {
    "2025/2026": {
        5: [("1", "Deutschbuch 5/6", "Deutsch", True),
            ("2", "Lambacher 5", "Mathematik", True),
            ("9", "Arbeitsheft", "Deutsch", False)],
        6: [("1", "Deutschbuch 5/6", "Deutsch", True)],
        # Individuelle Ausleihe, siehe _PAKET.
        7: [("3", "Politik alt", "Politik", True)],
    },
    "2026/2027": {
        6: [("1", "Deutschbuch 5/6", "Deutsch", True)],
        7: [("2", "Lambacher 5", "Mathematik", True)],
        # Damit Jg. 7 im alten Jahr nicht der letzte Jahrgang ist - sonst
        # griffe dessen Sonderregel und nicht die der individuellen Ausleihe.
        8: [("4", "Mathe 8", "Mathematik", True)],
    },
}
_PAKET = {5: True, 6: True, 7: False, 8: True}


class _Schuljahre:
    def get_current(self) -> dict:
        return {"id": "2026/2027", "name": "2026/2027"}

    def get_by_id(self, schoolyear_id: str) -> dict:
        if schoolyear_id not in _BUECHER:
            raise KeyError(schoolyear_id)
        return {"id": schoolyear_id, "name": schoolyear_id}

    def get_booklists(self, schoolyear_id: str) -> list[dict]:
        return [{"id": 100 + grade, "grade": grade, "package": _PAKET[grade]}
                for grade in sorted(_BUECHER[schoolyear_id])]

    def get_booklist(self, schoolyear_id: str, booklist_id: int) -> dict:
        items = [
            {"borrowable": leihbar, "series": isbn,
             "series_data": {"isbn": isbn, "title": titel, "subjectsFlat": [fach]}}
            for isbn, titel, fach, leihbar in _BUECHER[schoolyear_id][booklist_id - 100]
        ]
        return {"sections": [{"options": [{"items": items}]}]}


class FakeClient:
    schoolyears = _Schuljahre()

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def login(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def _ohne_website(monkeypatch: pytest.MonkeyPatch) -> None:
    """Die Aufgabenfelder kommen im Test als feste Zuordnung, nicht aus dem Netz."""
    monkeypatch.setattr(
        "app.mehrjahresbaende.aufgabenfeld_zuordnung",
        lambda vorgabe, warnungen, **kwargs: {
            "Deutsch": "Aufgabenfeld A", "Politik": "Aufgabenfeld B",
            "Mathematik": "Aufgabenfeld C",
        },
    )


@pytest.fixture()
def seiten(einstellungen: Einstellungen) -> TestClient:
    application = create_app(einstellungen=einstellungen, client_factory=FakeClient)
    with TestClient(application, base_url=TEST_BASIS_URL) as testclient:
        yield testclient


def _anmelden(client: TestClient) -> None:
    antwort = client.post("/api/anmeldung", json={"benutzer": "b.lehrer", "passwort": "x"})
    assert antwort.status_code == 200, antwort.text


def _datei(einstellungen: Einstellungen) -> Path:
    pfad = einstellungen.mehrjahresbaende_pfad()
    assert pfad is not None
    return pfad


def test_seite_ohne_datei_zeigt_den_leerzustand(seiten: TestClient) -> None:
    antwort = seiten.get("/mehrjahresbaende")
    assert antwort.status_code == 200
    assert "Noch keine Übersicht" in antwort.text
    assert "Aus IServ erzeugen" in antwort.text


def test_erzeugen_ohne_anmeldung_ist_401(seiten: TestClient) -> None:
    antwort = seiten.post("/api/mehrjahresbaende/erzeugen", json={})
    assert antwort.status_code == 401
    assert "fehler" in antwort.json()


def test_erzeugen_schreibt_die_datei_und_rechnet_die_marken(
    seiten: TestClient, einstellungen: Einstellungen,
) -> None:
    _anmelden(seiten)
    antwort = seiten.post("/api/mehrjahresbaende/erzeugen", json={})
    assert antwort.status_code == 200, antwort.text
    assert _datei(einstellungen).is_file()

    uebersicht = antwort.json()["uebersicht"]
    marken = {
        zeile["jahrgang"]: {zelle["fach"]: zelle["marke"] for zelle in zeile["zellen"]}
        for zeile in uebersicht["zeilen"]
    }
    # Jg. 5: Deutschbuch steht im neuen Jahr in Jg. 6 -> bleibt.
    assert marken[5]["Deutsch"] == ""
    # Lambacher steht im neuen Jahr in Jg. 7, also nicht in Jg. 6 -> abgeben.
    assert marken[5]["Mathematik"] == "X"
    # Jg. 6: Deutschbuch taucht in Jg. 7 nicht auf, aber noch in Jg. 6 -> abgeben.
    assert marken[6]["Deutsch"] == "X"
    assert marken[6]["Mathematik"] == "---"
    # Jg. 7 leiht individuell aus.
    zeile7 = next(zeile for zeile in uebersicht["zeilen"] if zeile["jahrgang"] == 7)
    assert zeile7["zellen"] == []
    assert "keine erneute Anmeldung" in zeile7["hinweis"]
    assert "Politik alt" in zeile7["hinweis"]
    assert uebersicht["herkunft"].endswith("2025/2026 → 2026/2027")


def test_seite_zeigt_die_erzeugte_uebersicht(seiten: TestClient) -> None:
    _anmelden(seiten)
    seiten.post("/api/mehrjahresbaende/erzeugen", json={})
    antwort = seiten.get("/mehrjahresbaende")
    assert antwort.status_code == 200
    assert "Jahrgang 5" in antwort.text
    assert "Aufgabenfeld A" in antwort.text
    assert "muss abgegeben werden" in antwort.text


def test_marke_aendern_schreibt_und_gibt_den_neuen_stand_zurueck(
    seiten: TestClient, einstellungen: Einstellungen,
) -> None:
    _anmelden(seiten)
    erzeugt = seiten.post("/api/mehrjahresbaende/erzeugen", json={}).json()

    antwort = seiten.post("/api/mehrjahresbaende/marke", json={
        "jahrgang": 5, "fach": "Mathematik", "marke": "B", "mtime": erzeugt["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    neu = antwort.json()
    assert neu["mtime"] != erzeugt["mtime"]

    from mehrjahresbaende.core import lies_uebersicht
    gelesen = lies_uebersicht(_datei(einstellungen))
    zeile = gelesen.zeile(5)
    assert zeile is not None
    zelle = zeile.zelle("Mathematik")
    assert zelle is not None and zelle.marke == "B"


def test_veraltete_mtime_wird_mit_409_abgelehnt(seiten: TestClient) -> None:
    _anmelden(seiten)
    erzeugt = seiten.post("/api/mehrjahresbaende/erzeugen", json={}).json()
    seiten.post("/api/mehrjahresbaende/marke", json={
        "jahrgang": 5, "fach": "Mathematik", "marke": "B", "mtime": erzeugt["mtime"],
    })
    antwort = seiten.post("/api/mehrjahresbaende/marke", json={
        "jahrgang": 5, "fach": "Deutsch", "marke": "X", "mtime": erzeugt["mtime"],
    })
    assert antwort.status_code == 409
    assert "neu laden" in antwort.json()["fehler"]


def test_unbekannte_marke_wird_abgelehnt(seiten: TestClient) -> None:
    """Ein Buchstabe ohne Legendenzeile wäre in der Datei nicht auflösbar."""
    _anmelden(seiten)
    erzeugt = seiten.post("/api/mehrjahresbaende/erzeugen", json={}).json()
    antwort = seiten.post("/api/mehrjahresbaende/marke", json={
        "jahrgang": 5, "fach": "Deutsch", "marke": "Z", "mtime": erzeugt["mtime"],
    })
    assert antwort.status_code == 400
    assert "keine gültige Marke" in antwort.json()["fehler"]


def test_marke_ohne_datei_meldet_das_fehlende_erzeugen(seiten: TestClient) -> None:
    antwort = seiten.post("/api/mehrjahresbaende/marke", json={
        "jahrgang": 5, "fach": "Deutsch", "marke": "X", "mtime": 1.0,
    })
    assert antwort.status_code == 503
    assert "Aus IServ erzeugen" in antwort.json()["fehler"]


def test_json_route_meldet_die_fehlende_datei_ohne_fehler(seiten: TestClient) -> None:
    antwort = seiten.get("/api/mehrjahresbaende")
    assert antwort.status_code == 200
    assert antwort.json()["uebersicht"] is None


def test_kopf_nennt_den_reiter_auf_jeder_seite(seiten: TestClient) -> None:
    antwort = seiten.get("/mehrjahresbaende")
    assert 'href="/mehrjahresbaende"' in antwort.text
    # Der alte Reiter heißt jetzt „Bücherlisten".
    assert "Bücherlisten" in antwort.text
