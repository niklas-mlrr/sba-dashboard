"""Sidecar-Cache: Titel, ISBN und Preis der letzten IServ-Abfrage.

Die Arbeitsmappe kennt weder Titel noch ISBN einer Zeile - beides kommt aus
IServ. Damit die Tabelle auch ohne Abruf etwas anzeigt, legt der Refresh diese
Angaben neben die Mappe. Fehlt der Cache, bleiben die Spalten leer und die
Oberfläche sagt, dass sie erst nach dem ersten Abruf gefüllt sind.

Der Cache ist reine Anzeige. Keine Zahl der Tabelle wird je aus ihm gelesen.

Speicherort - geteilt vor schreibbar: Der Sidecar neben der Mappe bleibt der
primäre Ort, weil er gemeinsame Anzeigedaten sind - ein Abruf von einem
Rechner nützt allen, die die Mappe öffnen, und der Cache verschwindet mit der
Mappe, ohne dass ihn jemand extra aufräumen muss. Das Gruppenlaufwerk kann
aber schreibgeschützt oder kurz nicht erreichbar sein; dafür gibt es
zusätzlich einen lokalen, plattformabhängigen Rückfallort
(:func:`cache_pfad_lokal`, überschreibbar über die Umgebungsvariable
``SBA_CACHE_DIR``). Der Trade-off ist bewusst: geteilt schlägt garantiert
schreibbar, weil der Cache reine Anzeige ist - scheitert das Schreiben ganz,
bleiben Spalten leer, aber es steht nie eine falsche Zahl in der Tabelle.
:func:`laden` liest beide Orte tolerant und nimmt den mit dem neueren
``stand``, damit ein Abruf, der auf den lokalen Ordner ausweichen musste,
beim nächsten Laden trotzdem sichtbar wird.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CACHE_SUFFIX = ".dashboard-cache.json"


class CacheFehler(RuntimeError):
    """Weder der Sidecar neben der Mappe noch der lokale Rückfallort ließen sich schreiben."""


@dataclass(frozen=True)
class Eintrag:
    isbn: str | None = None
    titel: str | None = None
    preis: float | None = None


@dataclass(frozen=True)
class Cache:
    stand: datetime | None = None
    schuljahr: str | None = None
    eintraege: dict[str, Eintrag] = field(default_factory=dict)

    @property
    def leer(self) -> bool:
        return not self.eintraege

    def get(self, key: str) -> Eintrag:
        return self.eintraege.get(key, Eintrag())


def cache_pfad(excel_pfad: Path) -> Path:
    """Der Sidecar neben der Mappe - die gemeinsame Anzeige für alle, die sie öffnen."""
    return excel_pfad.parent / f"{excel_pfad.stem}{CACHE_SUFFIX}"


def _lokaler_cache_ordner() -> Path:
    """Der plattformabhängige Rückfallort, falls das Gruppenlaufwerk nicht beschreibbar ist.

    ``SBA_CACHE_DIR`` ersetzt den kompletten Ordner - nicht nur die Wurzel -,
    damit Tests gefahrlos in ein ``tmp_path``-Verzeichnis schreiben können,
    statt in das echte Benutzerprofil.
    """
    override = os.environ.get("SBA_CACHE_DIR")
    if override:
        return Path(override)
    system = platform.system()
    if system == "Windows":
        basis = os.environ.get("LOCALAPPDATA")
        wurzel = Path(basis) if basis else Path.home() / "AppData" / "Local"
        return wurzel / "sba-dashboard" / "cache"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "sba-dashboard" / "cache"
    xdg = os.environ.get("XDG_CACHE_HOME")
    wurzel = Path(xdg) if xdg else Path.home() / ".cache"
    return wurzel / "sba-dashboard"


def cache_pfad_lokal(excel_pfad: Path) -> Path:
    """Der lokale Rückfallort für ``excel_pfad``.

    Der Dateiname hängt vom aufgelösten absoluten Pfad der Mappe ab, nicht nur
    von ihrem Namen - sonst würden sich zwei gleichnamige Mappen (z. B. Original
    und eine Testkopie) im Rückfallort gegenseitig überschreiben.
    """
    aufgeloest = str(excel_pfad.resolve())
    digest = hashlib.sha256(aufgeloest.encode("utf-8")).hexdigest()[:16]
    return _lokaler_cache_ordner() / f"{excel_pfad.stem}-{digest}.json"


# ── Tolerantes Lesen ─────────────────────────────────────────────────────────

def _preis_lesen(wert: object) -> float | None:
    """``preis`` akzeptiert Zahlen und saubere numerische Strings, sonst ``None``.

    ``bool`` ist in Python eine Unterklasse von ``int`` und muss deshalb vor der
    ``int``/``float``-Prüfung ausgeschlossen werden - ``True`` ist kein Preis.
    """
    if isinstance(wert, bool):
        return None
    if isinstance(wert, (int, float)):
        return float(wert)
    if isinstance(wert, str):
        text = wert.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _stand_lesen(wert: object) -> datetime | None:
    """``stand`` muss ein ISO-Zeitstempel sein - alles andere wird zu ``None``."""
    if not isinstance(wert, str) or not wert:
        return None
    try:
        return datetime.fromisoformat(wert)
    except ValueError:
        return None


def _eintrag_lesen(wert: object) -> Eintrag:
    """Baut einen Eintrag aus rohen JSON-Daten; falsch typisierte Felder werden ``None``.

    Ist ``wert`` selbst kein Objekt, ist das Ergebnis ein leerer Eintrag statt
    eines Fehlers - der Schlüssel bleibt erhalten, nur ohne verwertbare Daten.
    """
    if not isinstance(wert, dict):
        return Eintrag()
    isbn = wert.get("isbn")
    titel = wert.get("titel")
    return Eintrag(
        isbn=isbn if isinstance(isbn, str) else None,
        titel=titel if isinstance(titel, str) else None,
        preis=_preis_lesen(wert.get("preis")),
    )


def _cache_aus_roh(roh: object) -> Cache:
    """Baut aus beliebigem geparsten JSON einen (ggf. teilweise leeren) Cache.

    Diese Funktion wirft nie - eine kaputte Eingabe liefert bestenfalls einen
    leeren, schlimmstenfalls einen teilweise gefüllten Cache zurück. Einzelne
    kaputte Einträge werden bereinigt statt die ganze Datei zu verwerfen.
    """
    if not isinstance(roh, dict):
        return Cache()
    schuljahr = roh.get("schuljahr")
    eintraege_roh = roh.get("eintraege")
    eintraege: dict[str, Eintrag] = {}
    if isinstance(eintraege_roh, dict):
        for key, wert in eintraege_roh.items():
            if not isinstance(key, str):
                continue
            eintraege[key] = _eintrag_lesen(wert)
    return Cache(
        stand=_stand_lesen(roh.get("stand")),
        schuljahr=schuljahr if isinstance(schuljahr, str) else None,
        eintraege=eintraege,
    )


def _datei_lesen(pfad: Path) -> Cache:
    """Liest eine einzelne Cache-Datei tolerant; jede kaputte Eingabe wird zu ``Cache()``."""
    try:
        with open(pfad, encoding="utf-8") as handle:
            text = handle.read()
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return Cache()
    if not text.strip():
        return Cache()
    try:
        roh = json.loads(text)
    except json.JSONDecodeError:
        return Cache()
    return _cache_aus_roh(roh)


def _waehle(sidecar: Cache, lokal: Cache) -> Cache:
    """Wählt zwischen zwei tolerant gelesenen Ständen nach den Vorrangregeln.

    Ein fehlender ``stand`` gilt als älter als jeder echte Zeitstempel. Bleibt
    es beim Stand unentschieden (beide fehlen oder beide sind gleich alt),
    gewinnt bei ungleicher Füllung der nicht-leere Cache; bleibt es weiterhin
    unentschieden, gewinnt der Sidecar - er ist die gemeinsame, für alle
    sichtbare Quelle.
    """
    if sidecar.stand != lokal.stand:
        if sidecar.stand is None:
            return lokal
        if lokal.stand is None:
            return sidecar
        try:
            return sidecar if sidecar.stand > lokal.stand else lokal
        except TypeError:
            # Ein ``stand`` mit Zeitzonenangabe lässt sich nicht mit einem
            # ohne vergleichen. Kein Grund zu werfen: diese Funktion steht im
            # Lesepfad und muss immer einen Cache liefern. Der Sidecar ist die
            # gemeinsame Quelle und gewinnt daher im Zweifel.
            return sidecar
    if sidecar.leer != lokal.leer:
        return lokal if sidecar.leer else sidecar
    return sidecar


def laden(excel_pfad: Path) -> Cache:
    """Liest beide Cache-Orte tolerant und nimmt den nach den Vorrangregeln neueren.

    Ein fehlender oder kaputter Cache an einem der beiden Orte ist kein Fehler.
    """
    sidecar = _datei_lesen(cache_pfad(excel_pfad))
    lokal = _datei_lesen(cache_pfad_lokal(excel_pfad))
    return _waehle(sidecar, lokal)


# ── Schreiben ────────────────────────────────────────────────────────────────

def _cache_zu_json(cache: Cache) -> str:
    inhalt = {
        "stand": cache.stand.isoformat() if cache.stand else None,
        "schuljahr": cache.schuljahr,
        "eintraege": {
            key: {"isbn": e.isbn, "titel": e.titel, "preis": e.preis}
            for key, e in cache.eintraege.items()
        },
    }
    return json.dumps(inhalt, ensure_ascii=False, indent=2)


# Wie oft und wie lange ``os.replace`` wiederholt wird, wenn Windows die
# Zieldatei gerade als geöffnet meldet. Die Summe der Wartezeiten liegt bei gut
# einer halben Sekunde (10+20+40+80+160+320 ms); ein Leser hält die Datei nur
# für die Dauer eines ``read()``, also Bruchteile davon.
_ERSETZ_VERSUCHE = 7
_ERSETZ_WARTE_START = 0.01


def _ersetze_mit_wiederholung(quelle: str, ziel: Path) -> None:
    """``os.replace``, das einen gleichzeitigen Leser unter Windows aussitzt.

    Unter POSIX ersetzt ``rename`` eine Datei auch dann, wenn jemand sie
    geöffnet hat - der Leser behält seinen alten Inhalt, der neue Name zeigt
    auf die neue Datei. **Windows nicht:** dort scheitert ``os.replace`` mit
    ``PermissionError`` (``WinError 5``), solange irgendein Handle auf die
    Zieldatei offen ist. Python öffnet Dateien ohne ``FILE_SHARE_DELETE``, ein
    lesendes ``open()`` genügt also.

    Das ist kein theoretischer Fall: das Dashboard ist ausdrücklich für mehrere
    gleichzeitige Fenster gedacht (``docs/schul-laptop-test.md``, Abschnitt G),
    der Sidecar liegt auf dem Gruppenlaufwerk, und ein Abruf schreibt ihn
    genau dann, wenn ein anderes Fenster ihn beim Seitenaufbau liest. Die CI
    hat den Fall am 2026-09-04 auf ``windows-latest`` gefunden, wo vier lesende
    Threads gegen 60 Schreibvorgänge liefen und **beide** Speicherorte mit
    ``WinError 5`` ausfielen.

    Ein Leser hält die Datei nur für die Dauer eines ``read()``. Kurzes
    Wiederholen löst den Konflikt deshalb zuverlässig, ohne dass irgendwo
    gesperrt werden müsste. Bleibt es dabei, ist der Grund ein anderer (echter
    Schreibschutz, fremdes Programm) - dann fliegt der Fehler weiter, und
    ``speichern`` weicht auf den lokalen Ordner aus.
    """
    warte = _ERSETZ_WARTE_START
    for versuch in range(_ERSETZ_VERSUCHE):
        try:
            os.replace(quelle, ziel)
            return
        except PermissionError:
            if versuch == _ERSETZ_VERSUCHE - 1:
                raise
            time.sleep(warte)
            warte *= 2


def _atomar_schreiben(pfad: Path, inhalt: str) -> None:
    """Schreibt ``inhalt`` unterbrechungssicher: Nachbardatei, fsync, ``os.replace``.

    Ein Abbruch mittendrin (WLAN weg, Prozess beendet) lässt die vorherige
    Cache-Datei unberührt statt einer halben JSON-Datei zurück. Anders als
    ``atomic_save_workbook`` aus der Ausleihe-Bibliothek: der Cache ist reines
    JSON, kein Workbook, und braucht deshalb weder openpyxl noch ein Backup.
    """
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{pfad.stem}.", suffix=pfad.suffix, dir=pfad.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(inhalt)
            handle.flush()
            os.fsync(handle.fileno())
        _ersetze_mit_wiederholung(tmp_name, pfad)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def speichern(excel_pfad: Path, cache: Cache) -> Path:
    """Schreibt den Cache atomar - erst neben die Mappe, sonst in den lokalen Rückfallort.

    Der Sidecar ist die gemeinsame Anzeige für alle, die die Mappe öffnen; er
    kann aber schreibgeschützt oder kurz nicht erreichbar sein. In dem Fall
    weicht das Schreiben auf einen lokalen Ordner aus, den nur dieser Rechner
    sieht. Scheitert auch das, ist der Cache diesmal nicht zu retten - der
    Aufrufer (der Refresh) macht daraus eine Warnung, keinen Fehlschlag des
    ganzen Laufs.
    """
    try:
        inhalt = _cache_zu_json(cache)
    except (TypeError, ValueError) as fehler:
        # Ein Wert aus IServ, den json nicht darstellen kann. Ein zweiter
        # Speicherort hilft dagegen nicht - aber der Aufrufer soll auch das als
        # Warnung behandeln können und nicht den ganzen Abruf verlieren, dessen
        # Zahlen zu diesem Zeitpunkt längst in der Mappe stehen.
        raise CacheFehler(f"Cache ließ sich nicht als JSON darstellen: {fehler}") from fehler
    ziel = cache_pfad(excel_pfad)
    try:
        _atomar_schreiben(ziel, inhalt)
        return ziel
    except OSError as fehler_sidecar:
        ausweichziel = cache_pfad_lokal(excel_pfad)
        try:
            _atomar_schreiben(ausweichziel, inhalt)
            return ausweichziel
        except OSError as fehler_lokal:
            raise CacheFehler(
                f"Cache ließ sich weder neben der Mappe ({fehler_sidecar}) noch lokal "
                f"({fehler_lokal}) speichern."
            ) from fehler_lokal
