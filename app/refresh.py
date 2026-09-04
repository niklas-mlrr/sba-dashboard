"""Der IServ-Abruf: ein Hintergrundlauf, genau einer, mit Fortschrittsanzeige.

Der Abruf dauert 60 bis 90 Sekunden - drei Rundreisen über die API plus eine
Bücherliste je Jahrgang. So lange darf keine HTTP-Anfrage offen stehen, also
läuft er in einem Thread und die Oberfläche fragt den Stand ab.

**Zugangsdaten.** Sie kommen im Formular an, gehen direkt in den Client, werden
mit ``login()`` sofort geprüft und danach fallen gelassen. Sie landen nie in
``app.state``, nie in einem Log, nie in einer Antwort und nie in der Mappe. Der
Fail-Fast beim Anmelden ist genau deshalb synchron in der Anfrage: nur dort
lässt sich "Passwort falsch" noch als 401 beantworten, statt als Fehler in einem
Statusobjekt, das niemand liest.

**Ganz oder gar nicht.** Meldet ``apply_snapshot`` Diagnosen, ist die Zuordnung
Fach -> Buch mehrdeutig. Dann wird *nichts* gespeichert. Eine halb aktualisierte
Bestandsliste wäre schlimmer als eine veraltete, weil ihr niemand ansieht,
welche Zahl von wann ist.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from bestand.core import (
    EV_BOOKLISTS,
    EV_ENROLLMENTS,
    EV_GRADE_BOOKS,
    EV_NO_BOOKLIST,
    EV_SERIES,
    UpdateResult,
    apply_snapshot,
    fetch_snapshot,
    format_isbn,
    load_bestellt_counts,
    parse_grid,
    rebuild_zu_bestellen,
    write_stand,
)

from . import cache as cache_modul
from .excel import Gesperrt, lade_mappe, raster_blatt, speichere_mappe
from .settings import Einstellungen

# Fortschritt in Prozent je Phase. Grob, aber ehrlich: die Serienabfrage ist mit
# Abstand der längste Schritt, die Jahrgangslisten teilen sich den Rest.
_PHASEN = {
    "anmeldung": (5, "Anmeldung bei IServ"),
    EV_BOOKLISTS: (10, "Bücherlisten werden geladen"),
    EV_ENROLLMENTS: (25, "Anmeldungen werden gezählt"),
    EV_SERIES: (40, "Bestandszahlen werden geladen"),
    EV_GRADE_BOOKS: (60, "Bücherliste Jahrgang {grade}"),
    "excel": (92, "Mappe wird geschrieben"),
    "fertig": (100, "Fertig"),
}


class LaeuftBereits(RuntimeError):
    """Es läuft schon ein Abruf - führt zu HTTP 409."""


@dataclass
class Lauf:
    """Der Stand des aktuellen oder letzten Abrufs. Enthält keine Zugangsdaten."""
    job_id: str
    gestartet: datetime
    phase: str = "anmeldung"
    text: str = "Anmeldung bei IServ"
    fortschritt: int = 5
    laeuft: bool = True
    fertig: bool = False
    fehler: str | None = None
    fehlercode: int | None = None
    diagnosen: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)
    zusammenfassung: dict | None = None
    beendet: datetime | None = None

    def als_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "gestartet": self.gestartet.isoformat(timespec="seconds"),
            "phase": self.phase,
            "text": self.text,
            "fortschritt": self.fortschritt,
            "laeuft": self.laeuft,
            "fertig": self.fertig,
            "fehler": self.fehler,
            "fehlercode": self.fehlercode,
            "diagnosen": list(self.diagnosen),
            "warnungen": list(self.warnungen),
            "zusammenfassung": self.zusammenfassung,
            "beendet": self.beendet.isoformat(timespec="seconds") if self.beendet else None,
        }


_lock = threading.Lock()          # genau ein Lauf, prozessweit
_zustand_lock = threading.Lock()  # schützt nur _aktueller
_aktueller: Lauf | None = None


def status() -> dict | None:
    """Der Stand des letzten Laufs, oder None wenn noch keiner lief."""
    with _zustand_lock:
        return _aktueller.als_dict() if _aktueller is not None else None


def laeuft() -> bool:
    with _zustand_lock:
        return _aktueller is not None and _aktueller.laeuft


def zuruecksetzen() -> None:
    """Nur für Tests: vergisst den letzten Lauf und gibt das Modul-Lock frei."""
    global _aktueller
    with _zustand_lock:
        _aktueller = None
    if _lock.locked():
        try:
            _lock.release()
        except RuntimeError:
            pass


def _setze(**felder) -> None:
    with _zustand_lock:
        if _aktueller is None:
            return
        for name, wert in felder.items():
            setattr(_aktueller, name, wert)


def fehlerabbildung(exc: BaseException) -> tuple[int, str]:
    """Ausnahmen der Ausleihe-Bibliothek auf HTTP-Status und Klartext abbilden."""
    from ausleihe.exceptions import AuthError, ForbiddenError, TransportError

    if isinstance(exc, AuthError):
        return 401, "Zugangsdaten stimmen nicht. Bitte Benutzername und Passwort prüfen."
    if isinstance(exc, ForbiddenError):
        return 403, ("Dieses Konto hat keine Ausleihe-Verwalter-Rolle in IServ und "
                     "darf die Zahlen nicht abrufen.")
    if isinstance(exc, TransportError):
        return 504, ("IServ hat nicht geantwortet. Bitte die Netzverbindung prüfen "
                     "und es später erneut versuchen.")
    return 500, f"Unerwarteter Fehler beim Abruf: {exc}"


def melde_an(domain: str, benutzer: str, passwort: str, *, client_factory=None):
    """Baut den Client und prüft die Zugangsdaten sofort - Fail-Fast.

    Gibt den angemeldeten Client zurück. Die Zugangsdaten werden hier nicht
    gespeichert; der Aufrufer lässt seine eigenen Referenzen anschließend fallen.
    """
    if client_factory is None:
        from ausleihe import AusleiheClient
        client_factory = AusleiheClient
    client = client_factory(domain, benutzer, passwort)
    client.login()
    return client


def starte(einstellungen: Einstellungen, client, *, sy_id: str | None = None) -> str:
    """Startet den Hintergrundlauf. ``client`` ist bereits angemeldet."""
    global _aktueller
    if not _lock.acquire(blocking=False):
        raise LaeuftBereits(
            "Es läuft bereits ein Abruf. Bitte warten, bis er fertig ist."
        )
    job_id = uuid.uuid4().hex
    with _zustand_lock:
        _aktueller = Lauf(job_id=job_id, gestartet=datetime.now().replace(microsecond=0))

    thread = threading.Thread(
        target=_lauf, args=(einstellungen, client, sy_id),
        name=f"sba-refresh-{job_id[:8]}", daemon=True,
    )
    thread.start()
    return job_id


def _fortschritt(event: str, payload: dict) -> None:
    eintrag = _PHASEN.get(event)
    if eintrag is None:
        return
    prozent, vorlage = eintrag
    _setze(phase=event, text=vorlage.format(**payload), fortschritt=prozent)


def _lade_jahrgaenge(snapshot) -> dict[int, list[dict]]:
    """Lädt jede Jahrgangs-Bücherliste einzeln und meldet den Stand dazwischen."""
    lazy = snapshot.grade_books
    jahrgaenge = sorted(lazy)
    gesamt = max(1, len(jahrgaenge))
    start, vorlage = _PHASEN[EV_GRADE_BOOKS]
    spanne = _PHASEN["excel"][0] - start
    geladen: dict[int, list[dict]] = {}
    for nummer, grade in enumerate(jahrgaenge, start=1):
        _setze(phase=EV_GRADE_BOOKS, text=vorlage.format(grade=grade),
               fortschritt=start + round(spanne * (nummer - 1) / gesamt))
        # Der Zugriff löst den HTTP-Abruf aus; eine fehlende Liste meldet der
        # Rückruf, den ``fetch_snapshot`` dem Mapping mitgegeben hat.
        geladen[grade] = lazy[grade]
    return geladen


def _lauf(einstellungen: Einstellungen, client, sy_id: str | None) -> None:
    """Der eigentliche Abruf. Läuft im Thread und fängt jede Ausnahme ab."""
    try:
        pfad = einstellungen.excel_pfad()
        if pfad is None:
            _abschluss(fehler="Die Excel-Datei wurde nicht gefunden.", fehlercode=503)
            return
        config = einstellungen.bestand_config()

        warnungen: list[str] = []

        def fortschritt(event: str, payload: dict) -> None:
            if event == EV_GRADE_BOOKS:
                return  # Die Schleife in _lade_jahrgaenge meldet das genauer.
            if event == EV_NO_BOOKLIST:
                warnungen.append(
                    f"Für Jahrgang {payload['grade']} gibt es im Schuljahr "
                    f"{payload['schoolyear_id']} keine Bücherliste."
                )
                return
            _fortschritt(event, payload)

        snapshot = fetch_snapshot(client, sy_id, progress=fortschritt)
        # Die Bücherlisten je Jahrgang werden hier selbst durchlaufen statt über
        # ``eager=True``: erst danach steht ihre Anzahl fest, und nur mit ihr
        # lässt sich der längste Abschnitt des Abrufs ehrlich als Fortschritt
        # anzeigen statt als stehender Balken. Das Dashboard will außerdem einen
        # abgeschlossenen Stand, bevor es die Mappe anfasst - keine HTTP-Runde
        # mitten im Schreiben.
        snapshot = replace(snapshot, grade_books=_lade_jahrgaenge(snapshot))

        _setze(phase="excel", text=_PHASEN["excel"][1], fortschritt=_PHASEN["excel"][0])
        wb = lade_mappe(pfad)
        ws = raster_blatt(wb, einstellungen.blatt_raster)
        if "bestellt" not in wb.sheetnames:
            _abschluss(fehler="Das Blatt 'bestellt' fehlt in der Mappe.", fehlercode=422,
                       warnungen=warnungen)
            return

        grid = parse_grid(ws)
        # Ein Jahrgang, der im Raster steht, aber in IServ keine Bücherliste hat,
        # ist kein Fehler - seine Zellen bleiben schlicht leer. Wer die Mappe
        # später liest, soll aber wissen, warum. Die Prüfung steht hier und nicht
        # am Fortschritts-Rückruf, weil erst das Raster sagt, welche Jahrgänge
        # überhaupt vorkommen.
        for grade in sorted({c.grade for c in grid.cells if c.grade is not None}
                            - set(snapshot.booklists_by_grade)):
            warnungen.append(
                f"Für Jahrgang {grade} gibt es im Schuljahr {snapshot.schoolyear_id} "
                "keine Bücherliste. Die Zellen dieses Jahrgangs bleiben leer."
            )

        counts, fehler = load_bestellt_counts(wb["bestellt"])
        result = apply_snapshot(
            ws, grid, snapshot, config,
            bestellt_counts=counts,
            result=UpdateResult(diagnostics=list(fehler)),
        )
        if result.diagnostics:
            _abschluss(
                fehler=("Die Zuordnung Fach zu Buch ist nicht eindeutig. "
                        "Es wurde nichts gespeichert."),
                fehlercode=422, diagnosen=list(result.diagnostics), warnungen=warnungen,
            )
            return

        write_stand(ws, grid, result.stand, result)
        try:
            zeilen = rebuild_zu_bestellen(wb, result, snapshot, config.safety_stock)
        except (KeyError, ValueError, RuntimeError) as exc:
            _abschluss(fehler=f"Das Blatt 'zu Bestellen' ließ sich nicht aufbauen: {exc}",
                       fehlercode=422, warnungen=warnungen)
            return

        backup = speichere_mappe(wb, pfad, backups_behalten=einstellungen.backups_behalten)
        _schreibe_cache(pfad, result, snapshot)

        _abschluss(
            warnungen=warnungen,
            zusammenfassung={
                "geaendert": len(result.changes),
                "uebersprungen": len(result.skipped),
                "nachbestellungen": len(zeilen),
                "stueckzahl": sum(z.stueckzahl for z in zeilen),
                "stand": result.stand.isoformat(timespec="seconds") if result.stand else None,
                "schuljahr": snapshot.schoolyear_id,
                "backup": backup.name if backup else None,
            },
        )
    except Gesperrt as exc:
        _abschluss(fehler=str(exc), fehlercode=423)
    except BaseException as exc:  # noqa: BLE001 - der Thread darf nichts durchlassen
        code, meldung = fehlerabbildung(exc)
        _abschluss(fehler=meldung, fehlercode=code)
    finally:
        try:
            _lock.release()
        except RuntimeError:  # pragma: no cover - nur bei doppeltem Abschluss
            pass


def _schreibe_cache(pfad: Path, result: UpdateResult, snapshot) -> None:
    """Legt Titel, ISBN und Preis neben die Mappe - nur für die Anzeige.

    ISBNs werden hier formatiert (``format_isbn``) und nicht als nackte
    Ziffernfolge abgelegt: der Cache wird ausschließlich angezeigt, und im
    Live-Test stand in der Mappe die Strichfassung, im Cache die nackte - zwei
    Schreibweisen derselben Zahl in derselben Zeile.
    """
    eintraege: dict[str, cache_modul.Eintrag] = {}
    for key, isbn in result.isbn_by_entry.items():
        serie = snapshot.series_data.get(isbn, {})
        eintraege[key] = cache_modul.Eintrag(
            isbn=format_isbn(isbn),
            titel=serie.get("title") or None,
            preis=serie.get("price") or None,
        )
    cache_modul.speichern(pfad, cache_modul.Cache(
        stand=result.stand,
        schuljahr=snapshot.schoolyear_id,
        eintraege=eintraege,
    ))


def _abschluss(**felder) -> None:
    felder.setdefault("fertig", True)
    _setze(laeuft=False, beendet=datetime.now().replace(microsecond=0),
           fortschritt=100 if felder.get("fehlercode") is None else _aktuelle_prozent(),
           text=_abschlusstext(felder), phase="fertig" if not felder.get("fehler") else "fehler",
           **felder)


def _aktuelle_prozent() -> int:
    with _zustand_lock:
        return _aktueller.fortschritt if _aktueller else 0


def _abschlusstext(felder: dict) -> str:
    return felder.get("fehler") or "Fertig"
