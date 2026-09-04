"""Sidecar-Cache: atomares Schreiben, tolerantes Lesen, lokaler Rückfallort.

Jeder Test, der schreibt, setzt ``SBA_CACHE_DIR`` auf ein ``tmp_path``-
Unterverzeichnis - sonst würde der lokale Rückfallort ins echte
Benutzerprofil schreiben.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest
from bestand.core.testing import FakeClient

from app import cache as cache_modul

BENUTZER = "b.lehrer"
PASSWORT = "geheim-Kennwort-2026!"


def _abrufen(client, factory=FakeClient, **felder):
    """Löst denselben Abruf aus wie ``test_refresh.py`` - eigenständig gehalten,
    damit dieses Modul nicht von einem anderen Testmodul abhängt."""
    client.app.state.client_factory = factory
    nutzlast = {"benutzer": BENUTZER, "passwort": PASSWORT}
    nutzlast.update(felder)
    return client.post("/api/refresh", json=nutzlast)


def _warte_auf_ende(client, sekunden: float = 10.0) -> dict:
    frist = time.monotonic() + sekunden
    while time.monotonic() < frist:
        stand = client.get("/api/refresh/status").json()
        if stand["fertig"]:
            return stand
        time.sleep(0.02)
    raise AssertionError("Abruf wurde nicht fertig")


def _excel_pfad(tmp_path: Path) -> Path:
    """Ein plausibler Mappenpfad - die Datei selbst muss für den Cache nicht existieren."""
    return tmp_path / "Bestand- und Nachbestellungsliste 2026.xlsx"


# ── Rundlauf und Atomarität ───────────────────────────────────────────────────

def test_speichern_laden_rundlauf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Was gespeichert wird, kommt unverändert aus ``laden()`` zurück."""
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    cache = cache_modul.Cache(
        stand=datetime(2026, 9, 4, 12, 0, 0),
        schuljahr="2026/2027",
        eintraege={
            "0:Deutsch:C3": cache_modul.Eintrag(
                isbn="978-3-12-105207-3", titel="Terra 5/6", preis=19.95
            ),
        },
    )

    cache_modul.speichern(excel_pfad, cache)
    geladen = cache_modul.laden(excel_pfad)

    assert geladen == cache


def test_speichern_hinterlaesst_keinen_tmp_rest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    pfad = cache_modul.speichern(excel_pfad, cache_modul.Cache(schuljahr="2026/2027"))

    reste = list(pfad.parent.glob(f".{pfad.stem}.*"))
    assert reste == []
    assert pfad.is_file()


def test_schreibfehler_laesst_alte_datei_unveraendert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Eine Ausnahme mitten im Schreiben darf die vorherige Cache-Datei nicht antasten."""
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    alt = cache_modul.Cache(schuljahr="alter-stand")
    pfad = cache_modul.speichern(excel_pfad, alt)
    inhalt_vorher = pfad.read_text(encoding="utf-8")

    def kaputter_fsync(*args, **kwargs):
        raise OSError("Platte voll (simuliert)")

    import os

    monkeypatch.setattr(os, "fsync", kaputter_fsync)

    with pytest.raises(cache_modul.CacheFehler):
        cache_modul.speichern(excel_pfad, cache_modul.Cache(schuljahr="neuer-stand"))

    assert pfad.read_text(encoding="utf-8") == inhalt_vorher
    assert list(pfad.parent.glob(f".{pfad.stem}.*")) == []


# ── Rückfall auf den lokalen Ordner ───────────────────────────────────────────

def test_rueckfall_auf_lokalen_ordner_wenn_sidecar_nicht_schreibbar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    sidecar = cache_modul.cache_pfad(excel_pfad)
    original = cache_modul._atomar_schreiben

    def verweigere_sidecar(pfad, inhalt):
        if pfad == sidecar:
            raise OSError("Gruppenlaufwerk schreibgeschützt (simuliert)")
        return original(pfad, inhalt)

    monkeypatch.setattr(cache_modul, "_atomar_schreiben", verweigere_sidecar)

    cache = cache_modul.Cache(stand=datetime(2026, 9, 4, 12, 0, 0), schuljahr="2026/2027")
    ziel = cache_modul.speichern(excel_pfad, cache)

    assert ziel == cache_modul.cache_pfad_lokal(excel_pfad)
    assert not sidecar.exists()
    assert cache_modul.laden(excel_pfad) == cache


def test_beide_orte_nicht_schreibbar_wirft_cache_fehler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)

    def verweigere(pfad, inhalt):
        raise OSError("nicht beschreibbar (simuliert)")

    monkeypatch.setattr(cache_modul, "_atomar_schreiben", verweigere)

    with pytest.raises(cache_modul.CacheFehler):
        cache_modul.speichern(excel_pfad, cache_modul.Cache(schuljahr="2026/2027"))


# ── Vorrang bei zwei vorhandenen Cache-Dateien ────────────────────────────────

def _schreibe_direkt(pfad: Path, cache: cache_modul.Cache) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(cache_modul._cache_zu_json(cache), encoding="utf-8")


def test_neuerer_stand_gewinnt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    sidecar = cache_modul.cache_pfad(excel_pfad)
    lokal = cache_modul.cache_pfad_lokal(excel_pfad)

    aelter = cache_modul.Cache(stand=datetime(2026, 1, 1, 8, 0, 0), schuljahr="aelter")
    neuer = cache_modul.Cache(stand=datetime(2026, 1, 1, 9, 0, 0), schuljahr="neuer")

    _schreibe_direkt(sidecar, aelter)
    _schreibe_direkt(lokal, neuer)
    assert cache_modul.laden(excel_pfad).schuljahr == "neuer"

    _schreibe_direkt(sidecar, neuer)
    _schreibe_direkt(lokal, aelter)
    assert cache_modul.laden(excel_pfad).schuljahr == "neuer"


def test_fehlender_stand_gilt_als_aelter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    sidecar = cache_modul.cache_pfad(excel_pfad)
    lokal = cache_modul.cache_pfad_lokal(excel_pfad)

    ohne_stand = cache_modul.Cache(stand=None, schuljahr="ohne-stand")
    mit_stand = cache_modul.Cache(stand=datetime(2026, 1, 1, 8, 0, 0), schuljahr="mit-stand")

    _schreibe_direkt(sidecar, ohne_stand)
    _schreibe_direkt(lokal, mit_stand)
    assert cache_modul.laden(excel_pfad).schuljahr == "mit-stand"


def test_beide_ohne_stand_gewinnt_der_sidecar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    sidecar = cache_modul.cache_pfad(excel_pfad)
    lokal = cache_modul.cache_pfad_lokal(excel_pfad)

    eins = cache_modul.Cache(stand=None, schuljahr="sidecar-gewinnt",
                             eintraege={"k": cache_modul.Eintrag(titel="Sidecar")})
    zwei = cache_modul.Cache(stand=None, schuljahr="lokal-verliert",
                             eintraege={"k": cache_modul.Eintrag(titel="Lokal")})

    _schreibe_direkt(sidecar, eins)
    _schreibe_direkt(lokal, zwei)
    assert cache_modul.laden(excel_pfad).schuljahr == "sidecar-gewinnt"


def test_leerer_cache_verliert_gegen_nicht_leeren(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Beide ohne stand, aber der Sidecar ist leer - der nicht-leere lokale Cache gewinnt."""
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    sidecar = cache_modul.cache_pfad(excel_pfad)
    lokal = cache_modul.cache_pfad_lokal(excel_pfad)

    leer = cache_modul.Cache(stand=None, schuljahr=None, eintraege={})
    gefuellt = cache_modul.Cache(
        stand=None, schuljahr="2026/2027",
        eintraege={"k": cache_modul.Eintrag(titel="Terra 5/6")},
    )

    _schreibe_direkt(sidecar, leer)
    _schreibe_direkt(lokal, gefuellt)
    ergebnis = cache_modul.laden(excel_pfad)
    assert not ergebnis.leer
    assert ergebnis.schuljahr == "2026/2027"


# ── Toleranz beim Lesen ───────────────────────────────────────────────────────

def test_fehlende_datei_ergibt_leeren_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    ergebnis = cache_modul.laden(excel_pfad)
    assert ergebnis == cache_modul.Cache()
    assert ergebnis.leer


@pytest.mark.parametrize("roh_text", [
    "",
    "   ",
    "{kein gueltiges json",
    "[1, 2, 3]",
    "42",
    '"nur ein string"',
    "null",
    "true",
])
def test_kaputte_oder_falsch_geformte_datei_ergibt_leeren_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, roh_text: str
):
    """Datei leer, kaputtes JSON, oder eine Wurzel, die kein Objekt ist -> nie eine Ausnahme."""
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    cache_modul.cache_pfad(excel_pfad).write_text(roh_text, encoding="utf-8")

    ergebnis = cache_modul.laden(excel_pfad)

    assert ergebnis == cache_modul.Cache()


@pytest.mark.parametrize("stand_roh", [123, "gestern", "", None, ["2026-09-04T12:00:00"]])
def test_unlesbarer_stand_wird_none_rest_bleibt_nutzbar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stand_roh
):
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    import json as _json

    roh = {"stand": stand_roh, "schuljahr": "2026/2027", "eintraege": {"k": {"titel": "Terra"}}}
    cache_modul.cache_pfad(excel_pfad).write_text(_json.dumps(roh), encoding="utf-8")

    ergebnis = cache_modul.laden(excel_pfad)

    assert ergebnis.stand is None
    assert ergebnis.schuljahr == "2026/2027"
    assert ergebnis.eintraege["k"].titel == "Terra"


def test_schuljahr_das_kein_string_ist_wird_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    import json as _json

    roh = {"stand": None, "schuljahr": 2026, "eintraege": {}}
    cache_modul.cache_pfad(excel_pfad).write_text(_json.dumps(roh), encoding="utf-8")

    assert cache_modul.laden(excel_pfad).schuljahr is None


@pytest.mark.parametrize("eintraege_roh", [[1, 2, 3], "kein objekt", 5, None])
def test_eintraege_das_kein_objekt_ist_ergibt_leeres_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, eintraege_roh
):
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    import json as _json

    roh = {"stand": None, "schuljahr": "2026/2027", "eintraege": eintraege_roh}
    cache_modul.cache_pfad(excel_pfad).write_text(_json.dumps(roh), encoding="utf-8")

    ergebnis = cache_modul.laden(excel_pfad)
    assert ergebnis.eintraege == {}
    assert ergebnis.schuljahr == "2026/2027"


def test_einzelner_eintrag_mit_falschen_typen_wird_bereinigt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Ein kaputter Eintrag verliert nur seine falsch typisierten Felder, die übrigen bleiben."""
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    import json as _json

    roh = {
        "stand": None,
        "schuljahr": "2026/2027",
        "eintraege": {
            "kaputt": {"isbn": 12345, "titel": ["Terra"], "preis": "12,50"},
            "auch-kein-objekt": "text statt objekt",
            "gesund": {"isbn": "978-3-12-105207-3", "titel": "Terra 5/6", "preis": 19.95},
        },
    }
    cache_modul.cache_pfad(excel_pfad).write_text(_json.dumps(roh), encoding="utf-8")

    ergebnis = cache_modul.laden(excel_pfad)

    assert ergebnis.eintraege["kaputt"] == cache_modul.Eintrag(isbn=None, titel=None, preis=None)
    assert ergebnis.eintraege["auch-kein-objekt"] == cache_modul.Eintrag()
    assert ergebnis.eintraege["gesund"] == cache_modul.Eintrag(
        isbn="978-3-12-105207-3", titel="Terra 5/6", preis=19.95
    )


def test_nicht_string_schluessel_werden_uebersprungen():
    """JSON kennt nur String-Schlüssel; die Prüfung schützt trotzdem defensiv dagegen."""
    roh = {
        "stand": None,
        "schuljahr": "2026/2027",
        "eintraege": {1: {"titel": "Zahl als Schlüssel"}, "gueltig": {"titel": "Gueltig"}},
    }

    ergebnis = cache_modul._cache_aus_roh(roh)

    assert list(ergebnis.eintraege) == ["gueltig"]


@pytest.mark.parametrize("preis_roh, erwartet", [
    (19, 19.0),
    (19.95, 19.95),
    ("19.95", 19.95),
    (True, None),
    (False, None),
    ("12,50", None),
    ("nicht numerisch", None),
    (None, None),
])
def test_preis_typen(preis_roh, erwartet):
    eintrag = cache_modul._eintrag_lesen({"preis": preis_roh})
    assert eintrag.preis == erwartet


# ── Refresh-Verhalten ─────────────────────────────────────────────────────────

def test_abruf_endet_erfolgreich_wenn_cache_schreiben_fehlschlaegt(client, monkeypatch):
    """Die Bestandszahlen sind sicher in der Mappe - ein kaputter Cache wird zur Warnung,
    nicht zum Fehlschlag des ganzen Laufs."""

    def kaputt(*args, **kwargs):
        raise cache_modul.CacheFehler("Cache ließ sich nirgends speichern (simuliert).")

    monkeypatch.setattr(cache_modul, "speichern", kaputt)

    _abrufen(client)
    stand = _warte_auf_ende(client)

    assert stand["fehler"] is None, stand
    assert stand["fehlercode"] is None
    assert stand["fortschritt"] == 100
    assert any("nicht zwischengespeichert" in w for w in stand["warnungen"]), stand["warnungen"]
    assert any("Bestandszahlen" in w for w in stand["warnungen"]), stand["warnungen"]


# ── Nebenläufigkeit ───────────────────────────────────────────────────────────

def test_gleichzeitiges_lesen_waehrend_schreiben_sieht_nie_halbe_datei(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """``laden()`` liefert während paralleler Schreibvorgänge immer einen vollständigen
    Stand - nie eine Ausnahme und nie ein Gemisch aus altem und neuem Inhalt."""
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    cache_a = cache_modul.Cache(
        stand=datetime(2026, 1, 1, 8, 0, 0), schuljahr="A",
        eintraege={"k": cache_modul.Eintrag(isbn="1", titel="A", preis=1.0)},
    )
    cache_b = cache_modul.Cache(
        stand=datetime(2026, 1, 1, 9, 0, 0), schuljahr="B",
        eintraege={"k": cache_modul.Eintrag(isbn="2", titel="B", preis=2.0)},
    )
    cache_modul.speichern(excel_pfad, cache_a)

    fehler: list[BaseException] = []
    stopp = threading.Event()

    def leser() -> None:
        while not stopp.is_set():
            try:
                ergebnis = cache_modul.laden(excel_pfad)
            except BaseException as exc:  # noqa: BLE001 - genau das darf nie passieren
                fehler.append(exc)
                return
            if ergebnis.schuljahr not in ("A", "B") or ergebnis.eintraege["k"].titel != ergebnis.schuljahr:
                fehler.append(AssertionError(f"Zwischenstand gesehen: {ergebnis}"))
                return

    # daemon=True und try/finally sind hier kein Zierrat, sondern das Ergebnis
    # eines konkreten Vorfalls: als ``speichern`` unter Windows in der Schleife
    # eine Ausnahme warf, wurde ``stopp.set()`` nie erreicht. Die vier Leser
    # liefen danach endlos weiter, und weil sie keine Daemon-Threads waren,
    # wartete der Interpreter beim Beenden auf sie - pytest war nach zwei
    # Minuten fertig, der Prozess hing weitere zehn, bis die CI ihn abbrach.
    # Ein Fehlschlag in diesem Test darf den ganzen Lauf nicht aufhängen.
    threads = [threading.Thread(target=leser, daemon=True) for _ in range(4)]
    for thread in threads:
        thread.start()

    try:
        for runde in range(60):
            ziel = cache_a if runde % 2 == 0 else cache_b
            cache_modul.speichern(excel_pfad, ziel)
    finally:
        stopp.set()
        for thread in threads:
            thread.join(timeout=5)

    for thread in threads:
        assert not thread.is_alive()

    assert not fehler, fehler


def test_stand_mit_zeitzone_laesst_den_lesepfad_nicht_werfen(tmp_path, monkeypatch):
    """Ein von Hand bearbeiteter Cache kann einen Zeitstempel mit Zone tragen.

    ``laden`` steht im Lesepfad jeder Anfrage und muss auch dann einen Cache
    liefern; ein Vergleich zwischen naivem und zonenbehaftetem ``stand`` würde
    sonst mit ``TypeError`` durchschlagen.
    """
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    mappe = tmp_path / "Mappe.xlsx"
    mappe.write_bytes(b"x")

    cache_modul.cache_pfad(mappe).write_text(
        json.dumps({"stand": "2026-09-04T12:00:00+02:00", "eintraege": {"a": {"titel": "Mit Zone"}}}),
        encoding="utf-8",
    )
    lokal = cache_modul.cache_pfad_lokal(mappe)
    lokal.parent.mkdir(parents=True, exist_ok=True)
    lokal.write_text(
        json.dumps({"stand": "2026-09-04T11:00:00", "eintraege": {"a": {"titel": "Ohne Zone"}}}),
        encoding="utf-8",
    )

    geladen = cache_modul.laden(mappe)
    assert geladen.get("a").titel in {"Mit Zone", "Ohne Zone"}


def test_unserialisierbarer_wert_wird_zum_cachefehler(tmp_path, monkeypatch):
    """Der Aufrufer soll auch das als Warnung behandeln können, nicht als Abbruch."""
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    mappe = tmp_path / "Mappe.xlsx"
    mappe.write_bytes(b"x")

    kaputt = cache_modul.Cache(eintraege={"a": cache_modul.Eintrag(preis=object())})  # type: ignore[arg-type]
    with pytest.raises(cache_modul.CacheFehler):
        cache_modul.speichern(mappe, kaputt)


# ── os.replace unter Windows: gleichzeitiger Leser ───────────────────────────

def test_ersetzen_wiederholt_sich_wenn_windows_die_datei_als_offen_meldet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Ein ``PermissionError`` beim Ersetzen ist unter Windows der Normalfall, kein Defekt.

    Dort scheitert ``os.replace``, solange irgendein Handle auf die Zieldatei
    offen ist - ein lesendes ``open()`` genügt. Unter POSIX passiert das nie,
    deshalb wird der Fehler hier nachgestellt: die ersten beiden Versuche
    scheitern, der dritte gelingt, und ``speichern`` muss trotzdem den
    Sidecar zurückgeben statt auf den lokalen Ordner auszuweichen.
    """
    monkeypatch.setenv("SBA_CACHE_DIR", str(tmp_path / "lokal"))
    excel_pfad = _excel_pfad(tmp_path)
    echtes_replace = cache_modul.os.replace
    versuche: list[int] = []

    def zickiges_replace(quelle, ziel):
        versuche.append(1)
        if len(versuche) <= 2:
            raise PermissionError(5, "Access is denied")
        return echtes_replace(quelle, ziel)

    monkeypatch.setattr(cache_modul.os, "replace", zickiges_replace)
    monkeypatch.setattr(cache_modul.time, "sleep", lambda _: None)

    ziel = cache_modul.speichern(excel_pfad, cache_modul.Cache(
        stand=datetime(2026, 1, 1, 8, 0, 0), schuljahr="A",
        eintraege={"k": cache_modul.Eintrag(isbn="1", titel="A", preis=1.0)},
    ))

    assert ziel == cache_modul.cache_pfad(excel_pfad), "darf nicht lokal ausweichen"
    assert len(versuche) == 3, f"erwartet 3 Versuche, waren {len(versuche)}"
    assert cache_modul.laden(excel_pfad).schuljahr == "A"


def test_dauerhaft_belegte_datei_weicht_auf_den_lokalen_ordner_aus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Hört der PermissionError nicht auf, ist es kein Leser mehr - dann greift der Rückfallort."""
    lokal = tmp_path / "lokal"
    monkeypatch.setenv("SBA_CACHE_DIR", str(lokal))
    excel_pfad = _excel_pfad(tmp_path)
    echtes_replace = cache_modul.os.replace
    sidecar = cache_modul.cache_pfad(excel_pfad)

    def nur_sidecar_blockiert(quelle, ziel):
        if Path(ziel) == sidecar:
            raise PermissionError(5, "Access is denied")
        return echtes_replace(quelle, ziel)

    monkeypatch.setattr(cache_modul.os, "replace", nur_sidecar_blockiert)
    monkeypatch.setattr(cache_modul.time, "sleep", lambda _: None)

    ziel = cache_modul.speichern(excel_pfad, cache_modul.Cache(
        stand=datetime(2026, 1, 1, 8, 0, 0), schuljahr="A",
        eintraege={"k": cache_modul.Eintrag(isbn="1", titel="A", preis=1.0)},
    ))

    assert ziel == cache_modul.cache_pfad_lokal(excel_pfad)
    assert not sidecar.exists()
    assert cache_modul.laden(excel_pfad).schuljahr == "A"
