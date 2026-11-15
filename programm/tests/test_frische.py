"""HTML-Seiten tragen ``Cache-Control: no-store`` (Begründung: ``app/frische.py``)."""
from __future__ import annotations


def test_html_seite_wird_nicht_zwischengespeichert(client):
    antwort = client.get("/")
    assert antwort.headers["content-type"].startswith("text/html")
    assert antwort.headers["cache-control"] == "no-store"


def test_fachseite_wird_nicht_zwischengespeichert(client):
    # Auch die Fehlerseite ist HTML - der Kopf hängt am Inhaltstyp, nicht an der Route.
    antwort = client.get("/buecherliste/fach/Mathematik")
    assert antwort.headers["content-type"].startswith("text/html")
    assert antwort.headers["cache-control"] == "no-store"


def test_json_und_statisches_bleiben_unberuehrt(client):
    assert "cache-control" not in client.get("/health").headers
    assert "cache-control" not in client.get("/static/app.css").headers
