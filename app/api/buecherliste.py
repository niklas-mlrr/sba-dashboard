"""Die Bücherlisten-Seiten hinter dem Reiter "Bücherliste".

Wie ``GET /`` fangen diese Routen ihre Fehler selbst ab und liefern HTML: wer
im Menü auf "Fach" klickt und nicht angemeldet ist, soll einen Satz lesen, was
zu tun ist - kein JSON aus ``app/fehler.py``.
"""
from __future__ import annotations

from typing import Any, Callable
from urllib.parse import quote

from buecherlisten.core.daten import lade_buecherdaten, waehle_faecher
from buecherlisten.core.erzeugen import erzeuge_buecherlisten_pdfs
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from ..buecherlisten import (
    Buecherlisten,
    finde_gruppe,
    gruppen_nach_fach,
    gruppen_nach_verlag,
    lade_buecherlisten,
)
from ..sitzung import Abgelaufen, NichtAngemeldet
from .gemeinsam import vorlagen

router = APIRouter()

# Ansicht -> (Überschrift, Gruppierung). Jahrgang hat keine Gruppierung, weil
# seine Zeilen die IServ-Listen selbst sind.
_ANSICHTEN: dict[str, tuple[str, Callable[[Buecherlisten], Any] | None]] = {
    "fach": ("Fach", gruppen_nach_fach),
    "verlag": ("Verlag", gruppen_nach_verlag),
    "jahrgang": ("Jahrgang", None),
}


def _seite(request: Request, vorlage: str, werte: dict, status: int = 200) -> Response:
    return vorlagen.TemplateResponse(
        request, vorlage, {"reiter": "buecherliste", **werte}, status_code=status,
    )


def _hinweis(request: Request, titel: str, meldung: str, status: int) -> Response:
    return _seite(request, "fehler.html",
                  {"titel": titel, "meldung": meldung, "ueberschrift": "Bücherliste"}, status)


def _laden(request: Request) -> Buecherlisten | Response:
    try:
        client = request.app.state.anmeldung.client()
    except (NichtAngemeldet, Abgelaufen) as exc:
        return _hinweis(
            request, "Nicht angemeldet",
            f"{exc} Die Bücherlisten werden live aus IServ geladen; "
            "danach diese Seite neu laden.", 401,
        )
    try:
        return lade_buecherlisten(client)
    except Exception as exc:  # noqa: BLE001 - jeder Netz- oder API-Fehler wird zur Seite
        return _hinweis(
            request, "IServ nicht erreichbar",
            f"Die Bücherlisten konnten nicht geladen werden: {exc}", 502,
        )


def _unbekannte_ansicht(request: Request, ansicht: str) -> Response:
    return _hinweis(request, "Unbekannte Ansicht", f"Es gibt keine Ansicht „{ansicht}“.", 404)


# Beide PDF-Routen stehen vor "/buecherliste/{ansicht}/{name:path}", sonst
# fängt diese "fach/pdf" und "fach/<Fach>/pdf" als Gruppennamen ab.
@router.get("/buecherliste/fach/pdf")
async def pdf_faecher(request: Request) -> Response:
    """PDF mehrerer Fächer; das Druckmenü der Fachübersicht schickt hierher.

    GET statt POST, wie die PDF-Exporte von IServ (``loan-slips``,
    ``forms/export/form-students``): alle Angaben stehen in der URL, also lädt
    F5 im PDF-Tab ohne "Formular erneut senden" dasselbe PDF neu, und nach
    einer abgelaufenen Anmeldung genügt Neuladen.

    Die Fächer kommen bei "Individuell" als fertige Liste. Das soll so
    bleiben: "veränderte" wird später im Menü geprüft und hakt die Fächer
    dort an, damit F5 dieselben Fächer zeigt, auch wenn sich danach etwas
    geändert hat (docs/roadmap.md).
    """
    abfrage = request.query_params

    def auswahl(alle: list[str]) -> tuple[list[str], str]:
        modus = abfrage.get("reihenfolge", "")
        if abfrage.get("faecher_auswahl") == "individuell":
            return abfrage.getlist("faecher"), modus
        # "Alle" sowie die Platzhalter "veränderte" und "nicht bestätigte".
        return alle, modus

    return await _pdf(request, auswahl)


@router.get("/buecherliste/fach/{name}/pdf")
async def pdf_fach(request: Request, name: str) -> Response:
    """PDF eines Fachs, aufgerufen aus dem Druckmenü auf dessen Seite."""
    return await _pdf(request, lambda alle: ([name], "split"))


async def _pdf(request: Request,
               auswahl: Callable[[list[str]], tuple[list[str], str]]) -> Response:
    """Lädt die Daten, wählt die Fächer und liefert das PDF zum Anzeigen.

    ``Content-Disposition: inline`` sorgt dafür, dass der Browser das PDF im
    neuen Tab anzeigt, statt es herunterzuladen. Gesperrte Felder schickt der
    Browser nicht - fehlt ``bestaetigung``, fehlen also auch die Rückgabe-Angaben.
    """
    abfrage = request.query_params

    def eins(name: str) -> str:
        return (abfrage.get(name) or "").strip()

    try:
        client = request.app.state.anmeldung.client()
    except (NichtAngemeldet, Abgelaufen) as exc:
        return _hinweis(request, "Nicht angemeldet",
                        f"{exc} Danach diese Seite neu laden.", 401)
    try:
        daten = await run_in_threadpool(lade_buecherdaten, client)
    except Exception as exc:  # noqa: BLE001 - jeder Netz- oder API-Fehler wird zur Seite
        return _hinweis(request, "IServ nicht erreichbar",
                        f"Die Bücherlisten konnten nicht geladen werden: {exc}", 502)

    gewuenscht, modus = auswahl(list(daten.faecher))
    if modus not in {"alphabet", "aufgabenfeld", "split"}:
        modus = "alphabet"
    faecher, unbekannt = waehle_faecher(daten.faecher, gewuenscht)
    if unbekannt or not faecher:
        return _hinweis(request, "Keine gültige Auswahl",
                        "Diese Fächer kommen in keiner Bücherliste vor: " + ", ".join(unbekannt)
                        if unbekannt else "Es ist kein Fach ausgewählt.", 400)

    try:
        (pdf, *_) = await run_in_threadpool(
            lambda: erzeuge_buecherlisten_pdfs(
                daten,
                faecher=faecher,
                modus=modus,  # type: ignore[arg-type]
                bestaetigung=bool(eins("bestaetigung")),
                rueckgabe_bis=eins("rueckgabe_bis") or None,
                rueckgabe_an=eins("rueckgabe_an") or None,
                doppelseitig=bool(eins("doppelseitig")),
                nur_falls_noetig=bool(eins("falls_noetig")),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _hinweis(request, "PDF nicht erzeugt",
                        f"Beim Erzeugen des PDFs ist ein Fehler aufgetreten: {exc}", 500)

    return Response(
        pdf.inhalt,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(pdf.dateiname)}"},
    )


@router.get("/buecherliste/{ansicht}")
def uebersicht(request: Request, ansicht: str) -> Response:
    if ansicht not in _ANSICHTEN:
        return _unbekannte_ansicht(request, ansicht)
    daten = _laden(request)
    if isinstance(daten, Response):
        return daten
    name, gruppierung = _ANSICHTEN[ansicht]
    return _seite(request, "buecherliste_uebersicht.html", {
        "ansicht": ansicht,
        "ansicht_name": name,
        "schuljahr": daten.schuljahr,
        "listen": daten.listen,
        "gruppen": gruppierung(daten) if gruppierung else (),
    })


@router.get("/buecherliste/{ansicht}/{name:path}")
def gruppe(request: Request, ansicht: str, name: str) -> Response:
    if ansicht not in _ANSICHTEN:
        return _unbekannte_ansicht(request, ansicht)
    daten = _laden(request)
    if isinstance(daten, Response):
        return daten
    ansicht_name, gruppierung = _ANSICHTEN[ansicht]
    werte: dict[str, Any] = {
        "ansicht": ansicht, "ansicht_name": ansicht_name, "schuljahr": daten.schuljahr,
    }
    if gruppierung is None:
        liste = daten.liste_fuer_jahrgang(int(name)) if name.isdigit() else None
        if liste is None:
            return _hinweis(request, "Nicht gefunden",
                            f"Für Jahrgang „{name}“ gibt es keine Bücherliste.", 404)
        return _seite(request, "buecherliste_gruppe.html",
                      {**werte, "titel": liste.titel, "liste": liste})
    gefunden = finde_gruppe(gruppierung(daten), name)
    if gefunden is None:
        return _hinweis(request, "Nicht gefunden",
                        f"„{name}“ kommt in keiner Bücherliste vor.", 404)
    return _seite(request, "buecherliste_gruppe.html",
                  {**werte, "titel": gefunden.name, "gruppe": gefunden})
