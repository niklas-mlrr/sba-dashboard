"""Lebenszeichen und Beenden - die zwei Routen ohne Bezug zur Mappe."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Antwortet immer, solange der Prozess lebt. Von ``tools/diagnose.py`` benutzt."""
    return {"status": "ok"}


@router.post("/api/beenden")
def api_beenden(request: Request) -> JSONResponse:
    """Fährt den Server herunter, wenn er über ``app/start.py`` gestartet wurde.

    ``app.state.server`` setzt ``app/start.py`` nach dem Bau der uvicorn-
    Instanz. Fehlt sie, läuft das Dashboard unter einem fremden Server
    (``uvicorn app.main:app`` von Hand) - dann gibt es nichts, was sich hier
    beenden ließe, und die Antwort sagt stattdessen, wie es geht.

    Diese Route war der Anlass für ``app/sicherheit.py``: sie nimmt keinen
    Körper und ist damit ohne Origin-Prüfung von jeder fremden Seite im selben
    Browser auslösbar.
    """
    server = getattr(request.app.state, "server", None)
    if server is None:
        return JSONResponse(
            {"fehler": "Dieser Server wurde nicht über START.bat gestartet und "
                       "lässt sich nur im Fenster beenden (Strg+C)."},
            status_code=501,
        )
    server.should_exit = True
    return JSONResponse({"ok": True, "text": "Das Dashboard wird beendet. "
                                             "Sie können das Fenster schließen."})
