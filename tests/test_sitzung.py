"""Die Anmeldung: ein Besitzer des Passworts, ein Zeitschloss, kein Leck.

Die Begründung des gesamten Entwurfs steht im Modul-Docstring von
``app/sitzung.py``. Hier steht, was davon tatsächlich eingehalten wird.
"""
from __future__ import annotations

import logging

import pytest
from bestand.core.testing import FakeClient

from app.sitzung import ABLAUF_SEKUNDEN, Abgelaufen, Anmeldung, NichtAngemeldet

PASSWORT = "geheim-Kennwort-2026!"
BENUTZER = "b.lehrer"


class _Uhr:
    """Eine Zeitquelle, die nur vorgeht, wenn der Test sie vorstellt.

    Damit ist das Zeitschloss in Millisekunden prüfbar statt in dreißig
    Minuten - und der Test hängt nicht an der Laufzeit der Suite.
    """

    def __init__(self) -> None:
        self.jetzt = 1000.0

    def __call__(self) -> float:
        return self.jetzt

    def weiter(self, sekunden: float) -> None:
        self.jetzt += sekunden


@pytest.fixture()
def uhr() -> _Uhr:
    return _Uhr()


@pytest.fixture()
def anmeldung(uhr: _Uhr) -> Anmeldung:
    return Anmeldung(ablauf_sekunden=60, zeit=uhr)


def _anmelden(anmeldung: Anmeldung, einstellungen, factory=FakeClient) -> None:
    anmeldung.anmelden(einstellungen, BENUTZER, PASSWORT, client_factory=factory)


# ── Anmelden, benutzen, abmelden ──────────────────────────────────────────────

def test_vor_der_anmeldung_gibt_es_keinen_client(anmeldung: Anmeldung):
    assert anmeldung.status() == {
        "angemeldet": False, "benutzer": None, "verfaellt_in": None, "ablauf_sekunden": 60,
    }
    with pytest.raises(NichtAngemeldet):
        anmeldung.client()


def test_nach_der_anmeldung_steht_der_benutzer_im_status(anmeldung: Anmeldung, einstellungen):
    _anmelden(anmeldung, einstellungen)
    status = anmeldung.status()
    assert status["angemeldet"] is True
    assert status["benutzer"] == BENUTZER
    assert status["verfaellt_in"] == 60
    assert isinstance(anmeldung.client(), FakeClient)


def test_abmelden_verwirft_den_client(anmeldung: Anmeldung, einstellungen):
    _anmelden(anmeldung, einstellungen)
    anmeldung.abmelden()
    assert anmeldung.status()["angemeldet"] is False
    with pytest.raises(NichtAngemeldet):
        anmeldung.client()


def test_eine_gescheiterte_anmeldung_laesst_die_bestehende_stehen(anmeldung: Anmeldung,
                                                                 einstellungen):
    """Ein Tippfehler im zweiten Versuch darf niemanden aus der Sitzung werfen."""
    _anmelden(anmeldung, einstellungen)
    erster_client = anmeldung.client()

    class _Kaputt:
        def __init__(self, *args) -> None:
            pass

        def login(self) -> None:
            from ausleihe.exceptions import AuthError
            raise AuthError("401")

    from ausleihe.exceptions import AuthError
    with pytest.raises(AuthError):
        _anmelden(anmeldung, einstellungen, _Kaputt)

    assert anmeldung.client() is erster_client


# ── Zeitschloss ───────────────────────────────────────────────────────────────

def test_die_anmeldung_verfaellt_nach_der_frist(anmeldung: Anmeldung, einstellungen, uhr: _Uhr):
    _anmelden(anmeldung, einstellungen)
    uhr.weiter(59)
    assert anmeldung.client() is not None  # kurz davor: noch gültig

    uhr.weiter(60)
    with pytest.raises(Abgelaufen) as fehler:
        anmeldung.client()
    assert "1 Minuten" in str(fehler.value)
    # Und danach ist es wieder der gewöhnliche "nicht angemeldet"-Fall, kein
    # zweites Mal "abgelaufen": der Client ist weg, nicht bloß abgewertet.
    with pytest.raises(NichtAngemeldet):
        anmeldung.client()


def test_jede_benutzung_setzt_die_frist_zurueck(anmeldung: Anmeldung, einstellungen, uhr: _Uhr):
    """Wer alle paar Minuten abruft, wird nie herausgeworfen."""
    _anmelden(anmeldung, einstellungen)
    for _ in range(5):
        uhr.weiter(59)
        assert anmeldung.client() is not None


def test_der_status_verlaengert_die_frist_nicht(anmeldung: Anmeldung, einstellungen, uhr: _Uhr):
    """Der Takt des Fensters fragt dauernd nach - das darf das Schloss nicht aufhalten."""
    _anmelden(anmeldung, einstellungen)
    for _ in range(4):
        uhr.weiter(20)
        anmeldung.status()
    assert anmeldung.status()["angemeldet"] is False
    with pytest.raises(NichtAngemeldet):
        anmeldung.client()


def test_der_status_zaehlt_die_restzeit_herunter(anmeldung: Anmeldung, einstellungen, uhr: _Uhr):
    _anmelden(anmeldung, einstellungen)
    uhr.weiter(25)
    assert anmeldung.status()["verfaellt_in"] == 35


def test_ein_laufender_abruf_behaelt_seinen_client(anmeldung: Anmeldung, einstellungen,
                                                  uhr: _Uhr):
    """Der Grund, warum es keinen Wächter gegen laufende Abrufe braucht.

    ``RefreshManager.starte`` bekommt den Client als Parameter und hält damit
    eine eigene Referenz. Verfällt die Anmeldung mitten in einem langen Lauf,
    wird ihm deshalb nichts entzogen - er läuft zu Ende, und erst der nächste
    Abruf verlangt eine neue Anmeldung.
    """
    _anmelden(anmeldung, einstellungen)
    laufender_client = anmeldung.client()

    uhr.weiter(120)
    with pytest.raises(Abgelaufen):
        anmeldung.client()

    # Derselbe Client, den der Lauf in der Hand hält, ist unverändert benutzbar.
    laufender_client.login()


def test_die_vorgabefrist_sind_dreissig_minuten():
    """Die abgesprochene Zahl, an einer Stelle festgehalten."""
    assert ABLAUF_SEKUNDEN == 30 * 60
    assert Anmeldung().status()["ablauf_sekunden"] == ABLAUF_SEKUNDEN


def test_die_umgebungsvariable_verkuerzt_die_frist_fuer_den_handtest(monkeypatch):
    """``SBA_ANMELDUNG_ABLAUF`` - nur, damit das Schloss von Hand beobachtbar ist."""
    monkeypatch.setenv("SBA_ANMELDUNG_ABLAUF", "60")
    assert Anmeldung().status()["ablauf_sekunden"] == 60

    # Unsinn darin darf den Start nicht verhindern: dann gilt die Vorgabe.
    monkeypatch.setenv("SBA_ANMELDUNG_ABLAUF", "sofort")
    assert Anmeldung().status()["ablauf_sekunden"] == ABLAUF_SEKUNDEN
    monkeypatch.setenv("SBA_ANMELDUNG_ABLAUF", "0")
    assert Anmeldung().status()["ablauf_sekunden"] == ABLAUF_SEKUNDEN


# ── Kein Leck ─────────────────────────────────────────────────────────────────

def test_das_passwort_steht_nicht_im_status_im_repr_und_im_log(anmeldung: Anmeldung,
                                                               einstellungen, caplog):
    caplog.set_level(logging.DEBUG)
    _anmelden(anmeldung, einstellungen)

    assert PASSWORT not in str(anmeldung.status())
    assert PASSWORT not in repr(anmeldung)
    assert PASSWORT not in repr(vars(anmeldung))
    assert PASSWORT not in "\n".join(e.getMessage() for e in caplog.records)
    # Der Benutzername darf vorkommen - das Fenster zeigt ihn an.
    assert BENUTZER in repr(anmeldung)
