"""Der Vertrag zwischen ``app/static/app.js`` und der gerenderten Seite.

``app.js`` hat bewusst keinen Build-Schritt und damit auch keine
JS-Testumgebung - es gibt hier weder node noch ein Testframework für den
Browser, und beides einzuführen wäre für 235 Zeilen Vanilla teurer als der
Fehler, den es verhindert. Ungetestet muss die Datei deshalb aber nicht
bleiben: **alles, was sie über das HTML annimmt**, steht im HTML, und das HTML
baut Jinja aus einer Vorlage, die hier gerendert wird.

Diese Datei prüft daher nicht das Verhalten des Skripts, sondern seinen
Vertrag - jede ID, die es nachschlägt, jede Klasse, über die es greift, und
jedes Datenattribut, aus dem es liest. Die Namen werden aus ``app.js`` selbst
gelesen, nicht hier abgeschrieben: eine neue ``getElementById``-Zeile im Skript
zieht damit automatisch eine Prüfung nach sich, und eine umbenannte ID in der
Vorlage fällt sofort auf, statt erst im Browser der Lehrkraft.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parent.parent / "app" / "static" / "app.js"


class _Sammler(HTMLParser):
    """Ein minimaler Parser - er soll nur Attribute einsammeln, nichts deuten."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.klassen: set[str] = set()
        self.zeilen: list[dict[str, str | None]] = []
        self.zellen_je_zeile: list[list[dict[str, str | None]]] = []
        self.kopfzellen: list[dict[str, str | None]] = []
        self._in_kopf = False
        self._aktuelle: list[dict[str, str | None]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        werte = dict(attrs)
        if werte.get("id"):
            self.ids.add(str(werte["id"]))
        self.klassen.update((werte.get("class") or "").split())
        if tag == "thead":
            self._in_kopf = True
        elif tag == "th" and self._in_kopf:
            self.kopfzellen.append(werte)
        elif tag == "tr" and not self._in_kopf and werte.get("data-key"):
            self.zeilen.append(werte)
            self._aktuelle = []
            self.zellen_je_zeile.append(self._aktuelle)
        elif tag == "td" and self._aktuelle is not None:
            self._aktuelle.append(werte)
        elif tag == "input" and self._aktuelle is not None:
            # Das Eingabefeld gehört zur zuletzt geöffneten Zelle.
            self._aktuelle[-1] = {**self._aktuelle[-1], "input-spalte": werte.get("data-spalte")}

    def handle_endtag(self, tag: str) -> None:
        if tag == "thead":
            self._in_kopf = False


@pytest.fixture()
def seite(client) -> _Sammler:
    sammler = _Sammler()
    sammler.feed(client.get("/").text)
    return sammler


@pytest.fixture()
def js() -> str:
    return APP_JS.read_text(encoding="utf-8")


# ── Die Namen, die app.js nachschlägt ─────────────────────────────────────────

def test_jede_id_aus_app_js_gibt_es_auch_auf_der_seite(seite: _Sammler, js: str):
    """Der häufigste stille Bruch: eine ID in der Vorlage umbenannt.

    ``getElementById`` liefert dann ``null``, und die nächste Zeile wirft einen
    TypeError - der die **ganze** Datei anhält, also auch Teile, die mit der
    umbenannten ID nichts zu tun haben. Im Browser stünde die Tabelle danach
    ohne Filter, ohne Sortierung und ohne Speichern da, und in der Konsole
    stünde eine Zeile, die niemand liest.
    """
    gesucht = set(re.findall(r'getElementById\("([^"]+)"\)', js))
    assert gesucht, "die Suche selbst ist kaputt, wenn app.js keine IDs nachschlägt"
    assert gesucht <= seite.ids, f"fehlen auf der Seite: {sorted(gesucht - seite.ids)}"


def test_jede_klasse_aus_app_js_kommt_auf_der_seite_vor(seite: _Sammler, js: str):
    """``querySelector('.bedarfszelle')`` und Geschwister.

    Ausgenommen sind Klassen, die das Skript erst SETZT (``gespeichert``,
    ``fehlerhaft``, ``bedarf``, ``fehlgeschlagen``, ``warnung``): die stehen
    zurecht nicht im Ausgangs-HTML, sondern in ``app.css``.
    """
    gesetzt = {"gespeichert", "fehlerhaft", "bedarf", "fehlgeschlagen", "warnung"}
    gesucht = set(re.findall(r'querySelector(?:All)?\("\.([A-Za-zäöüß-]+)"\)', js)) - gesetzt
    assert gesucht, "die Suche selbst ist kaputt"
    assert gesucht <= seite.klassen, f"fehlen auf der Seite: {sorted(gesucht - seite.klassen)}"


# ── Die Datenattribute, aus denen app.js liest ────────────────────────────────

def test_jede_zeile_traegt_schluessel_bedarf_und_suchtext(seite: _Sammler):
    assert seite.zeilen, "ohne Zeilen prüft dieser Test nichts"
    for zeile in seite.zeilen:
        assert zeile["data-key"], zeile
        assert zeile["data-bedarf"] in {"0", "1"}, zeile
        # Der Suchtext ist kleingeschrieben, weil app.js den Begriff senkt und
        # dann includes() aufruft - ohne das fände die Suche "Erdkunde" nicht.
        assert zeile["data-suche"] == (zeile["data-suche"] or "").lower(), zeile


def test_die_tabelle_kennt_ihr_zeichen_fuer_keinen_wert(client):
    """``data-leer`` statt eines zweiten ``"—"`` im Skript."""
    text = client.get("/").text
    assert 'data-leer="—"' in text
    assert '"—"' not in APP_JS.read_text(encoding="utf-8")


def test_jede_sortierbare_spalte_hat_in_jeder_zeile_einen_sortierschluessel(seite: _Sammler):
    """``zellwert()`` greift über den Spaltenindex - da darf keine Zelle fehlen."""
    arten = [kopf.get("data-sort") for kopf in seite.kopfzellen]
    assert arten and all(art in {"text", "zahl"} for art in arten), arten
    for zellen in seite.zellen_je_zeile:
        assert len(zellen) == len(arten), "Kopf und Zeile sind unterschiedlich breit"
        for zelle in zellen:
            assert zelle.get("data-wert") is not None, zelle


def test_zahlenspalten_tragen_zahlen_oder_nichts(seite: _Sammler):
    """Sonst ergäbe ``Number(roh)`` in ``zellwert()`` stillschweigend NaN."""
    zahl_spalten = [i for i, kopf in enumerate(seite.kopfzellen) if kopf.get("data-sort") == "zahl"]
    assert zahl_spalten
    for zellen in seite.zellen_je_zeile:
        for i in zahl_spalten:
            roh = zellen[i]["data-wert"] or ""
            assert roh == "" or re.fullmatch(r"-?\d+", roh), (i, roh)


def test_textspalten_sind_kleingeschrieben(seite: _Sammler):
    """``zellwert()`` senkt nichts mehr - sonst sortierte "ISBN" vor "Physik"."""
    text_spalten = [i for i, k in enumerate(seite.kopfzellen) if k.get("data-sort") == "text"]
    for zellen in seite.zellen_je_zeile:
        for i in text_spalten:
            roh = zellen[i]["data-wert"] or ""
            # Die ISBN und der Jahrgang enthalten keine Buchstaben; die Prüfung
            # gilt trotzdem für alle, weil sie dann einfach nichts ändert.
            assert roh == roh.lower(), (i, roh)


# ── Übereinstimmung mit dem, was der Server gerechnet hat ─────────────────────

def test_der_sortierschluessel_stimmt_mit_der_api_ueberein(client, seite: _Sammler):
    """Seite und ``/api/rows`` müssen dieselbe Zahl zeigen - sonst sortiert die
    Tabelle nach etwas anderem, als sie anzeigt."""
    api = {z["key"]: z for z in client.get("/api/rows").json()["zeilen"]}
    spalten = ["fach", "jahrgang", "titel", "isbn",
               "angemeldet", "bestand", "bestellt", "zu_bestellen"]
    for zeile, zellen in zip(seite.zeilen, seite.zellen_je_zeile):
        daten = api[zeile["data-key"]]
        for name, zelle in zip(spalten, zellen):
            erwartet = daten[name]
            roh = zelle["data-wert"] or ""
            assert roh == ("" if erwartet is None else str(erwartet).lower()), (name, zeile)


def test_bedarf_gesamt_ist_die_summe_der_zellen(client, seite: _Sammler):
    """Dieselbe Summe, die ``bedarfNeuZeichnen()`` nach jeder Änderung bildet."""
    text = client.get("/").text
    gerendert = int(re.search(r'id="bedarf-gesamt">(\d+)<', text).group(1))
    bedarfsspalte = len(seite.kopfzellen) - 1
    summe = 0
    for zellen in seite.zellen_je_zeile:
        wert = zellen[bedarfsspalte]["data-wert"] or ""
        if wert and int(wert) > 0:
            summe += int(wert)
    assert summe == gerendert


def test_eingabefelder_stehen_nur_in_den_schreibbaren_spalten(seite: _Sammler):
    from app.excel import SCHREIBBARE_SPALTEN

    gefunden = {z.get("input-spalte") for zellen in seite.zellen_je_zeile for z in zellen}
    assert gefunden - {None} == set(SCHREIBBARE_SPALTEN)


def test_nach_einer_aenderung_traegt_die_api_alles_was_das_skript_einsetzt(client):
    """``zeileAktualisieren`` liest genau diese Felder aus der Antwort."""
    daten = client.get("/api/rows").json()
    zeile = next(z for z in daten["zeilen"] if z["bestand_ref"] == "G3")
    antwort = client.post("/api/cell", json={
        "key": zeile["key"], "spalte": "bestand", "wert": 3, "mtime": daten["mtime"],
    })
    assert antwort.status_code == 200, antwort.text
    zurueck = antwort.json()["zeile"]
    for feld in ("zu_bestellen", "bestand", "bestellt"):
        assert feld in zurueck, feld
    assert zurueck["bestand"] == 3
