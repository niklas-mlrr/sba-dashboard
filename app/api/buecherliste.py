"""Die Bücherlisten-Seiten hinter dem Reiter "Bücherliste".

Wie ``GET /`` fangen diese Routen ihre Fehler selbst ab und liefern HTML: wer
im Menü auf "Fach" klickt und nicht angemeldet ist, soll einen Satz lesen, was
zu tun ist - kein JSON aus ``app/fehler.py``.
"""
from __future__ import annotations

from typing import Any, Callable, cast
from urllib.parse import quote

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from buecherlisten.core.daten import (
    Ansicht,
    Korrekturen,
    format_isbn,
    lade_buecherdaten,
    waehle_gruppen,
)
from buecherlisten.core.erzeugen import erzeuge_buecherlisten_pdfs, erzeuge_schuelerlisten_pdfs
from buecherlisten.planung import (
    FACH_BESTAETIGT,
    OHNE_VERLAG,
    fach_bestaetigung,
    fach_status,
    planungs_status,
)

from .. import buchplanung as planungsdomaene
from ..buecherlisten import (
    Buecherlisten,
    finde_gruppe,
    gruppen_nach_fach,
    gruppen_nach_verlag,
    lade_buecherlisten,
)
from ..sitzung import Abgelaufen, NichtAngemeldet
from .gemeinsam import aktuelle_einstellungen, vorlagen

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


def _korrekturen(request: Request) -> Callable[[str], Korrekturen | None]:
    """Die korrigierten Angaben der Buchreihen, je Schuljahr aus der Buchplanung.

    Sie wirken auf jeder Bücherlisten-Seite und in jedem PDF. Fehlt die Datei
    oder ist sie unlesbar, gilt IServ unverändert - eine kaputte Datei darf
    die Bücherliste nicht abwürgen (wie in :func:`_planungskontext`).
    """
    def laden(schuljahr: str) -> Korrekturen | None:
        try:
            stand = planungsdomaene.lies(aktuelle_einstellungen(request), schuljahr)
        except Exception:  # noqa: BLE001
            return None
        return stand.planung.korrekturen_fuer_iserv() if stand else None
    return laden


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
        return lade_buecherlisten(client, korrekturen=_korrekturen(request))
    except Exception as exc:  # noqa: BLE001 - jeder Netz- oder API-Fehler wird zur Seite
        return _hinweis(
            request, "IServ nicht erreichbar",
            f"Die Bücherlisten konnten nicht geladen werden: {exc}", 502,
        )


def _planungskontext(request: Request, schuljahr: str) -> dict[str, Any]:
    """Der gespeicherte Stand dieses Schuljahrs, fertig zum Anzeigen.

    ``schuljahr`` ist die IServ-**Kennung** ("2026/2027"), nicht der
    Anzeigename: sie ist der Schlüssel der Datei und geht von der Seite
    unverändert in jede Eintragung zurück.

    Die Seiten selbst kommen live aus IServ; was geprüft, bestätigt und geplant
    ist, steht in der Exceldatei. Beides wird hier zusammengelegt - **ohne**
    dass ein Fehler an der Datei die Bücherliste unbrauchbar macht: fehlt sie
    oder ist sie unlesbar, zeigt die Seite die Bücher und einen Hinweis.

    Die Status werden nicht mitgeliefert, sondern hier gerechnet - an genau der
    Stelle, an der auch die API sie rechnet (``buecherlisten/planung/modelle.py``).
    """
    leer: dict[str, Any] = {
        "schuljahr": schuljahr, "mtime": None, "fehler": None, "warnungen": [],
        "fach_je_name": {}, "planung_je_isbn_und_fach": {},
        "ruecklage_je_isbn": {}, "ausmusterungen_je_fach": {}, "vorjahr": "",
        "verlage": [],
    }
    try:
        stand = planungsdomaene.lies(aktuelle_einstellungen(request), schuljahr)
    except Exception as exc:  # noqa: BLE001 - eine kaputte Datei darf die Seite nicht abwürgen
        return {**leer, "fehler": f"Der gespeicherte Stand ist nicht lesbar: {exc}"}
    if stand is None:
        return leer

    planung = stand.planung
    zeilen: dict[str, dict[str, list[dict[str, Any]]]] = {}
    ruecklagen: dict[str, dict[str, Any]] = {}
    for buch in planung.buecher:
        # Je Fach eigene Zeilen: die Fach-Ansicht zeigt nur, was ihr Fach
        # angeht, und die Fachkonferenzleitung bestätigt nur ihre eigenen.
        je_fach: dict[str, list[dict[str, Any]]] = {}
        for fach, jahrgang in planung.zeilen_des_buchs(buch):
            zeile = planung.planungszeile(buch.isbn, fach, jahrgang)
            je_fach.setdefault(fach, []).append({
                "jahrgang": jahrgang,
                # ``aktuell`` heißt: dieses (Fach, Jahrgang) steht in einer
                # Bücherliste - in der dieses Schuljahrs oder der des Vorjahrs,
                # denn beide stehen in der Datei. Das Buch ist dort eingeführt;
                # zu entscheiden ist nur noch die Ausmusterung. Ein bloß
                # geplanter Jahrgang steht in keiner Liste und lässt sich
                # deshalb ganz ändern und wieder entfernen.
                "aktuell": (fach, jahrgang) in buch.kombinationen,
                "eingefuehrt_ab": zeile.eingefuehrt_ab if zeile else "",
                "ausgemustert_nach": zeile.ausgemustert_nach if zeile else "",
                "kuerzel": zeile.kuerzel if zeile else "",
                "datum": zeile.datum if zeile else None,
                "bemerkung": zeile.bemerkung if zeile else "",
                "status": planungs_status(zeile, planung.schuljahr),
            })
        zeilen[buch.isbn] = je_fach
    for wunsch in planung.ruecklagen:
        ruecklagen.setdefault(wunsch.isbn, {})[wunsch.fach] = {
            "anzahl": wunsch.anzahl, "status": wunsch.status,
            "kuerzel": wunsch.kuerzel, "datum": wunsch.datum,
            "bemerkung": wunsch.bemerkung,
        }

    # Was mit dem Vorjahr endete: in diesem Schuljahr nicht mehr auf der Liste.
    ausmusterungen: dict[str, dict[str, dict[str, Any]]] = {}
    for zeile in planung.planung:
        altes = planung.buch(zeile.isbn)
        if altes is None or not planung.vorjahr \
                or zeile.ausgemustert_nach != planung.vorjahr:
            continue
        # Nur vollständig ausgemustert: in keinem Jahrgang dieses Fachs bleibt
        # das Buch danach noch stehen.
        if any((rest := planung.planungszeile(altes.isbn, fach, jg)) is None
               or rest.ausgemustert_nach != planung.vorjahr
               for fach, jg in planung.zeilen_des_buchs(altes) if fach == zeile.fach):
            continue
        je_buch = ausmusterungen.setdefault(zeile.fach, {})
        eintrag = je_buch.setdefault(altes.isbn, {
            "titel": altes.titel, "verlag": altes.verlag, "isbn": altes.isbn,
            "isbn_anzeige": format_isbn(altes.isbn), "leihbar": altes.leihbar,
            "neupreis": altes.neupreis, "leihgebuehr": altes.leihgebuehr,
            "jahrgaenge": [],
        })
        eintrag["jahrgaenge"].append(zeile.jahrgang)
    ausgemustert: dict[str, list[dict[str, Any]]] = {
        fach: sorted(je_buch.values(), key=lambda e: e["titel"].casefold())
        for fach, je_buch in ausmusterungen.items()
    }
    for eintraege in ausgemustert.values():
        for eintrag in eintraege:
            eintrag["jahrgaenge"].sort()

    faecher: dict[str, dict[str, Any]] = {}
    for fach in planung.faecher:
        status, hinweis = fach_status(planung, fach)
        kuerzel, datum = fach_bestaetigung(planung, fach)
        faecher[fach] = {
            "status": status, "hinweis": hinweis, "kuerzel": kuerzel, "datum": datum,
        }

    return {
        "schuljahr": schuljahr,
        "mtime": stand.zustand.mtime,
        "fehler": None,
        "warnungen": list(planung.warnungen),
        "fach_je_name": faecher,
        "planung_je_isbn_und_fach": zeilen,
        "ruecklage_je_isbn": ruecklagen,
        "ausmusterungen_je_fach": ausgemustert,
        "vorjahr": planung.vorjahr,
        "verlage": [v for v in planung.verlage if v != OHNE_VERLAG],
    }


def _unbekannte_ansicht(request: Request, ansicht: str) -> Response:
    return _hinweis(request, "Unbekannte Ansicht", f"Es gibt keine Ansicht „{ansicht}“.", 404)


# Wie die Auswahl einer Ansicht im Druckmenü und damit in der PDF-URL heißt.
_AUSWAHLFELD = {"fach": "faecher", "verlag": "verlage", "jahrgang": "jahrgaenge"}


# Beide PDF-Routen stehen vor "/buecherliste/{ansicht}/{name:path}", sonst
# fängt diese "fach/pdf" und "fach/<Fach>/pdf" als Gruppennamen ab.
@router.get("/buecherliste/{ansicht}/pdf")
async def pdf_gruppen(request: Request, ansicht: str) -> Response:
    """PDF mehrerer Fächer, Verlage oder Jahrgänge; aus dem Druckmenü der Übersicht.

    GET statt POST, wie die PDF-Exporte von IServ (``loan-slips``,
    ``forms/export/form-students``): alle Angaben stehen in der URL, also lädt
    F5 im PDF-Tab ohne "Formular erneut senden" dasselbe PDF neu, und nach
    einer abgelaufenen Anmeldung genügt Neuladen.

    Die Gruppen kommen bei "Individuell" als fertige Liste. Das soll so
    bleiben: "veränderte" wird später im Menü geprüft und hakt die Fächer
    dort an, damit F5 dieselben Fächer zeigt, auch wenn sich danach etwas
    geändert hat (docs/roadmap.md).
    """
    if ansicht not in _ANSICHTEN:
        return _unbekannte_ansicht(request, ansicht)
    abfrage = request.query_params
    feld = _AUSWAHLFELD[ansicht]

    def auswahl(alle: list[str]) -> tuple[list[str], str]:
        modus = abfrage.get("reihenfolge", "")
        if abfrage.get(f"{feld}_auswahl") == "individuell":
            return abfrage.getlist(feld), modus
        # "Alle" sowie die Platzhalter "veränderte" und "nicht bestätigte".
        return alle, modus

    return await _pdf(request, cast(Ansicht, ansicht), auswahl)


@router.get("/buecherliste/{ansicht}/{name:path}/pdf")
async def pdf_gruppe(request: Request, ansicht: str, name: str) -> Response:
    """PDF eines Fachs, Verlags oder Jahrgangs, aus dem Druckmenü seiner Seite."""
    if ansicht not in _ANSICHTEN:
        return _unbekannte_ansicht(request, ansicht)
    return await _pdf(request, cast(Ansicht, ansicht), lambda alle: ([name], "split"))


async def _pdf(request: Request, ansicht: Ansicht,
               auswahl: Callable[[list[str]], tuple[list[str], str]]) -> Response:
    """Lädt die Daten, wählt die Gruppen und liefert das PDF zum Anzeigen.

    ``Content-Disposition: inline`` sorgt dafür, dass der Browser das PDF im
    neuen Tab anzeigt, statt es herunterzuladen. Gesperrte Felder schickt der
    Browser nicht - fehlt ``bestaetigung``, fehlen also auch die Rückgabe-Angaben.

    ``schuelerliste`` (nur Jahrgang) holt statt der eigenen Liste die
    Druckversion aus IServ - dieselbe PDF, die dort an den Bücherlisten hängt.
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
        daten = await run_in_threadpool(
            lambda: lade_buecherdaten(client, korrekturen=_korrekturen(request)))
    except Exception as exc:  # noqa: BLE001 - jeder Netz- oder API-Fehler wird zur Seite
        return _hinweis(request, "IServ nicht erreichbar",
                        f"Die Bücherlisten konnten nicht geladen werden: {exc}", 502)

    gewuenscht, modus = auswahl(list(daten.gruppen(ansicht)))
    if modus not in {"alphabet", "aufgabenfeld", "split"}:
        modus = "alphabet"
    if ansicht != "fach" and modus == "aufgabenfeld":
        modus = "alphabet"
    gruppen, unbekannt = waehle_gruppen(daten, ansicht, gewuenscht)
    if unbekannt or not gruppen:
        wort = _ANSICHTEN[ansicht][0]
        return _hinweis(request, "Keine gültige Auswahl",
                        f"Das kommt in keiner Bücherliste vor ({wort}): " + ", ".join(unbekannt)
                        if unbekannt else "Es ist nichts ausgewählt.", 400)

    schuelerliste = ansicht == "jahrgang" and bool(eins("schuelerliste"))
    try:
        if schuelerliste:
            (pdf, *_) = await run_in_threadpool(
                lambda: erzeuge_schuelerlisten_pdfs(
                    daten,
                    lambda listen_id: client.admin.get_booklist_pdf(daten.schuljahr_id, listen_id),
                    jahrgaenge=gruppen,
                    modus="split" if modus == "split" else "alphabet",
                    doppelseitig=bool(eins("doppelseitig")),
                    nur_falls_noetig=bool(eins("falls_noetig")),
                )
            )
        else:
            (pdf, *_) = await run_in_threadpool(
                lambda: erzeuge_buecherlisten_pdfs(
                    daten,
                    ansicht=ansicht,
                    faecher=gruppen,
                    modus=modus,  # type: ignore[arg-type]
                    bestaetigung=ansicht == "fach" and bool(eins("bestaetigung")),
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
    gruppen = gruppierung(daten) if gruppierung else ()
    # Was im Druckmenü zur Auswahl steht: die Gruppennamen, bei Jahrgang die
    # Listen mit Jahrgang ("Jahrgang 5", wie buecherlisten.core sie nennt).
    druck_gruppen = (
        [f"Jahrgang {liste.jahrgang}" for liste in daten.listen if liste.jahrgang is not None]
        if ansicht == "jahrgang" else [g.name for g in gruppen]
    )
    kontext = _planungskontext(request, daten.kennung)
    return _seite(request, "buecherliste_uebersicht.html", {
        "planung": kontext,
        # Was hinter "nicht bestätigte" im Druckmenü steckt: die Fächer ohne
        # gültige Freigabe. Der Server rechnet sie aus, nicht das Skript - so
        # steht im HTML dieselbe Liste, die auch die Seite anzeigt.
        "druck_nicht_bestaetigt": [
            name for name in druck_gruppen
            if (kontext["fach_je_name"].get(name) or {}).get("status") != FACH_BESTAETIGT
        ] if ansicht == "fach" and kontext["mtime"] is not None else None,
        "ansicht": ansicht,
        # Jede Ansicht hat ein Druckmenü; nur sein Inhalt unterscheidet sich.
        "druckbar": True,
        "ansicht_name": name,
        "schuljahr": daten.schuljahr,
        "listen": daten.listen,
        "gruppen": gruppen,
        "druck_gruppen": druck_gruppen,
    })


@router.get("/buecherliste/{ansicht}/{name:path}")
def gruppe(request: Request, ansicht: str, name: str) -> Response:
    if ansicht not in _ANSICHTEN:
        return _unbekannte_ansicht(request, ansicht)
    daten = _laden(request)
    if isinstance(daten, Response):
        return daten
    ansicht_name, gruppierung = _ANSICHTEN[ansicht]
    planung = _planungskontext(request, daten.kennung)
    werte: dict[str, Any] = {
        "planung": planung,
        "ansicht": ansicht, "ansicht_name": ansicht_name, "schuljahr": daten.schuljahr,
        "druckbar": True,
        # Die Vorschläge für das Feld "Verlag" im Planungsmenü: die der
        # heutigen Listen und die der Datei (dort stehen auch die des Vorjahrs).
        "verlage": sorted(
            {g.name for g in gruppen_nach_verlag(daten) if g.name != OHNE_VERLAG}
            | set(planung["verlage"]),
            key=str.casefold,
        ) if ansicht == "fach" else [],
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
