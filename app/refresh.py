"""IServ-Abruf mit instanzgebundenem Fortschrittszustand.

Jede FastAPI-Anwendung besitzt einen :class:`RefreshManager`. Damit sind
Hintergrundläufe, Sperren und ihr Status nicht mehr unsichtbarer Modulzustand:
Tests und mehrere App-Instanzen beeinflussen einander nicht.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from bestand.core import (
    EV_BOOKLISTS,
    EV_ENROLLMENTS,
    EV_GRADE_BOOKS,
    EV_NO_BOOKLIST,
    EV_SERIES,
    BestandConfig,
    Snapshot,
    UpdateResult,
    ZuBestellenRow,
    apply_snapshot,
    fetch_snapshot,
    format_isbn,
    load_bestellt_counts,
    parse_grid,
    rebuild_zu_bestellen,
    write_stand,
)

from . import cache as cache_modul
from .excel import Gesperrt, arbeitsmappe_sperren, lade_mappe, raster_blatt, speichere_mappe
from .settings import Einstellungen

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


class AusleiheProtokoll(Protocol):
    """Was das Dashboard vom IServ-Client wirklich benutzt: eine Anmeldung.

    Ein Protokoll und kein Import von ``ausleihe.AusleiheClient``, weil der
    Client **injiziert** wird (``create_app(client_factory=...)``): die Tests
    setzen ``bestand.core.testing.FakeClient`` ein und kommen so ohne Netz und
    ohne IServ aus. Alles Weitere - Bücherlisten, Anmeldezahlen, Serien - holt
    ``bestand.core.fetch_snapshot`` selbst aus ihm; was es dafür braucht, steht
    dort und gehört nicht hierher dupliziert.
    """

    def login(self) -> None: ...


# Der Bauplan, nicht der Client: Domain, Benutzername, Passwort.
ClientFabrik = Callable[[str, str, str], AusleiheProtokoll]


@dataclass
class Lauf:
    """Der Stand eines Abrufs. Enthält bewusst keine Zugangsdaten.

    ``job_id`` und ``gestartet`` sind ``| None``, obwohl ein echter Lauf beide
    immer setzt (``RefreshManager.starte`` übergibt sie sofort bei der
    Erzeugung). Der Grund ist :meth:`ohne_lauf`: damit die Antwort von
    ``GET /api/refresh/status`` vor dem ersten Lauf einer Sitzung exakt dieselbe
    Schlüsselmenge hat wie danach - strukturell garantiert statt von Hand in
    zwei Dateien synchron gehalten -, muss sich auch ein "noch kein Lauf"-Stand
    als ganz normales ``Lauf``-Objekt bauen und durch :meth:`als_dict` schicken
    lassen. Ohne Optional-Typ gäbe es dafür keinen gültigen Wert für
    ``job_id``/``gestartet``, und ``als_dict`` müsste raten, ob es gerade für
    einen echten oder einen fiktiven Lauf aufgerufen wird.
    """

    job_id: str | None
    gestartet: datetime | None
    phase: str | None = "anmeldung"
    text: str = "Anmeldung bei IServ"
    fortschritt: int = 5
    laeuft: bool = True
    fertig: bool = False
    fehler: str | None = None
    fehlercode: int | None = None
    diagnosen: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)
    zusammenfassung: dict[str, Any] | None = None
    beendet: datetime | None = None

    def als_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "gestartet": self.gestartet.isoformat(timespec="seconds") if self.gestartet else None,
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

    @classmethod
    def ohne_lauf(cls) -> "Lauf":
        """Der Stand, bevor in dieser Sitzung überhaupt ein Abruf lief.

        Baut bewusst ein waschechtes ``Lauf``-Objekt statt eines separaten
        Dict-Literals: so kann ``als_dict`` gar nicht mehr aus dem Ruder
        laufen, wenn später ein Feld dazukommt - dieser Konstruktor bekommt es
        automatisch mit (als Default-Wert des Dataclass-Felds, hier per
        Keyword auf die "nichts ist passiert"-Bedeutung überschrieben) und
        ``als_dict`` serialisiert es wie jedes andere Feld auch.
        """
        return cls(
            job_id=None,
            gestartet=None,
            phase=None,
            text="Noch kein Abruf in dieser Sitzung.",
            fortschritt=0,
            laeuft=False,
            fertig=False,
        )


def fehlerabbildung(exc: BaseException) -> tuple[int, str]:
    """Ausnahmen der Ausleihe-Bibliothek auf HTTP und Klartext abbilden."""
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


def melde_an(domain: str, benutzer: str, passwort: str, *,
             client_factory: ClientFabrik | None = None) -> AusleiheProtokoll:
    """Baut den Client und prüft Zugangsdaten, ohne sie zu speichern."""
    if client_factory is None:
        from ausleihe import AusleiheClient
        client_factory = AusleiheClient
    client = client_factory(domain, benutzer, passwort)
    client.login()
    return client


class RefreshManager:
    """Koordiniert genau einen Abruf für eine konkrete Dashboard-Instanz."""

    def __init__(self) -> None:
        self._lauf_lock = threading.Lock()
        self._zustand_lock = threading.Lock()
        self._aktueller: Lauf | None = None

    def status(self) -> dict[str, Any]:
        """Der Stand des letzten Laufs, oder ``Lauf.ohne_lauf()`` vor dem ersten Lauf.

        Gibt absichtlich immer ein Dict zurück (nie ``None``): der Aufrufer -
        der Web-Layer in ``app/api/abruf.py`` - muss so gar nicht mehr wissen, dass
        es einen "vor dem ersten Lauf"-Sonderfall gibt. Die Unterscheidung ist
        reines Innenleben des Refresh-Moduls.
        """
        with self._zustand_lock:
            aktuell = self._aktueller if self._aktueller is not None else Lauf.ohne_lauf()
            return aktuell.als_dict()

    def laeuft(self) -> bool:
        with self._zustand_lock:
            return self._aktueller is not None and self._aktueller.laeuft

    def starte(self, einstellungen: Einstellungen, client: AusleiheProtokoll, *,
               sy_id: str | None = None) -> str:
        """Startet den Hintergrundlauf. ``client`` ist bereits angemeldet."""
        if not self._lauf_lock.acquire(blocking=False):
            raise LaeuftBereits("Es läuft bereits ein Abruf. Bitte warten, bis er fertig ist.")
        job_id = uuid.uuid4().hex
        with self._zustand_lock:
            self._aktueller = Lauf(job_id=job_id, gestartet=datetime.now().replace(microsecond=0))

        threading.Thread(
            target=self._lauf,
            args=(einstellungen, client, sy_id),
            name=f"sba-refresh-{job_id[:8]}",
            daemon=True,
        ).start()
        return job_id

    def _setze(self, **felder: Any) -> None:
        with self._zustand_lock:
            if self._aktueller is None:
                return
            for name, wert in felder.items():
                setattr(self._aktueller, name, wert)

    def _fortschritt(self, event: str, payload: dict[str, Any]) -> None:
        eintrag = _PHASEN.get(event)
        if eintrag is None:
            return
        prozent, vorlage = eintrag
        self._setze(phase=event, text=vorlage.format(**payload), fortschritt=prozent)

    def _lade_jahrgaenge(self, snapshot: Snapshot) -> dict[int, list[dict]]:
        """Lädt jede Jahrgangs-Bücherliste einzeln und meldet Fortschritt."""
        lazy = snapshot.grade_books
        jahrgaenge = sorted(lazy)
        gesamt = max(1, len(jahrgaenge))
        start, vorlage = _PHASEN[EV_GRADE_BOOKS]
        spanne = _PHASEN["excel"][0] - start
        geladen: dict[int, list[dict]] = {}
        for nummer, grade in enumerate(jahrgaenge, start=1):
            self._setze(phase=EV_GRADE_BOOKS, text=vorlage.format(grade=grade),
                        fortschritt=start + round(spanne * (nummer - 1) / gesamt))
            geladen[grade] = lazy[grade]
        return geladen

    def _lauf(self, einstellungen: Einstellungen, client: AusleiheProtokoll,
              sy_id: str | None) -> None:
        """Der eigentliche Abruf. Der Thread lässt keine Ausnahme durch."""
        try:
            pfad = einstellungen.excel_pfad()
            if pfad is None:
                self._abschluss(fehler="Die Excel-Datei wurde nicht gefunden.", fehlercode=503)
                return
            config = einstellungen.bestand_config()
            warnungen: list[str] = []

            def fortschritt(event: str, payload: dict) -> None:
                if event == EV_GRADE_BOOKS:
                    return
                if event == EV_NO_BOOKLIST:
                    warnungen.append(
                        f"Für Jahrgang {payload['grade']} gibt es im Schuljahr "
                        f"{payload['schoolyear_id']} keine Bücherliste."
                    )
                    return
                self._fortschritt(event, payload)

            snapshot = fetch_snapshot(client, sy_id, progress=fortschritt)
            snapshot = replace(snapshot, grade_books=self._lade_jahrgaenge(snapshot))
            self._setze(phase="excel", text=_PHASEN["excel"][1],
                        fortschritt=_PHASEN["excel"][0])
            aktualisierung = self._aktualisiere_mappe(
                pfad, einstellungen, snapshot, config, warnungen,
            )
            if aktualisierung is None:
                return
            result, zeilen, backup = aktualisierung
            try:
                self._schreibe_cache(pfad, result, snapshot)
            except cache_modul.CacheFehler:
                # Die Bestandszahlen stehen bereits sicher in der Mappe - ein
                # kaputter Cache ist keine Zahl, sondern nur eine leere Anzeige.
                warnungen.append(
                    "Titel und ISBN konnten diesmal nicht zwischengespeichert werden - "
                    "diese Spalten können deshalb leer bleiben. Die Bestandszahlen sind "
                    "bereits gespeichert."
                )
            self._abschluss(
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
            self._abschluss(fehler=str(exc), fehlercode=423)
        except BaseException as exc:  # noqa: BLE001 - der Thread darf nichts durchlassen
            code, meldung = fehlerabbildung(exc)
            self._abschluss(fehler=meldung, fehlercode=code)
        finally:
            self._lauf_lock.release()

    def _aktualisiere_mappe(
        self, pfad: Path, einstellungen: Einstellungen, snapshot: Snapshot,
        config: BestandConfig, warnungen: list[str],
    ) -> tuple[UpdateResult, list[ZuBestellenRow], Path | None] | None:
        """Schreibt den fertigen Snapshot unter derselben Sperre wie manuelle Änderungen."""
        with arbeitsmappe_sperren(pfad):
            wb = lade_mappe(pfad)
            ws = raster_blatt(wb, einstellungen.blatt_raster)
            if "bestellt" not in wb.sheetnames:
                self._abschluss(fehler="Das Blatt 'bestellt' fehlt in der Mappe.", fehlercode=422,
                                warnungen=warnungen)
                return None

            grid = parse_grid(ws)
            for grade in sorted({c.grade for c in grid.cells if c.grade is not None}
                                - set(snapshot.booklists_by_grade)):
                warnungen.append(
                    f"Für Jahrgang {grade} gibt es im Schuljahr {snapshot.schoolyear_id} "
                    "keine Bücherliste. Die Zellen dieses Jahrgangs bleiben leer."
                )

            counts, fehler = load_bestellt_counts(wb["bestellt"])
            result = apply_snapshot(
                ws, grid, snapshot, config, bestellt_counts=counts,
                result=UpdateResult(diagnostics=list(fehler)),
            )
            if result.diagnostics:
                self._abschluss(
                    fehler="Die Zuordnung Fach zu Buch ist nicht eindeutig. Es wurde nichts gespeichert.",
                    fehlercode=422, diagnosen=list(result.diagnostics), warnungen=warnungen,
                )
                return None

            write_stand(ws, grid, result.stand, result)
            try:
                zeilen = rebuild_zu_bestellen(wb, result, snapshot, config.safety_stock)
            except (KeyError, ValueError, RuntimeError) as exc:
                self._abschluss(fehler=f"Das Blatt 'zu Bestellen' ließ sich nicht aufbauen: {exc}",
                                fehlercode=422, warnungen=warnungen)
                return None
            backup = speichere_mappe(wb, pfad, backups_behalten=einstellungen.backups_behalten)
        return result, zeilen, backup

    def _schreibe_cache(self, pfad: Path, result: UpdateResult, snapshot: Snapshot) -> None:
        eintraege: dict[str, cache_modul.Eintrag] = {}
        for key, isbn in result.isbn_by_entry.items():
            serie = snapshot.series_data.get(isbn, {})
            eintraege[key] = cache_modul.Eintrag(
                isbn=format_isbn(isbn), titel=serie.get("title") or None,
                preis=serie.get("price") or None,
            )
        cache_modul.speichern(pfad, cache_modul.Cache(
            stand=result.stand, schuljahr=snapshot.schoolyear_id, eintraege=eintraege,
        ))

    def _abschluss(self, **felder: Any) -> None:
        felder.setdefault("fertig", True)
        self._setze(
            laeuft=False,
            beendet=datetime.now().replace(microsecond=0),
            fortschritt=100 if felder.get("fehlercode") is None else self._aktuelle_prozent(),
            text=felder.get("fehler") or "Fertig",
            phase="fertig" if not felder.get("fehler") else "fehler",
            **felder,
        )

    def _aktuelle_prozent(self) -> int:
        with self._zustand_lock:
            return self._aktueller.fortschritt if self._aktueller else 0
