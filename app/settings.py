"""Einstellungen - deutsche Schlüssel, weil die Lehrkraft sie bearbeitet.

Der Excel-Pfad ist bewusst eine **Liste von Kandidaten**: dieselbe Datei heißt auf
dem einen Rechner ``N:\\Buchausleihe Admins\\...`` und auf dem anderen
``\\\\iserv...\\Gruppen\\Buchausleihe Admins\\...``. Der erste existierende Pfad
gewinnt; existiert keiner, zeigt die Startseite alle geprüften Pfade an, statt mit
einer Ausnahme abzubrechen.

## Ordner schlägt Kandidatenliste

Seit es ein Programmfenster gibt (``app/fenster.py``), stellt die Lehrkraft dort
den **Ordner** ein, in dem die Mappe liegt, und nicht mehr den vollen Dateipfad:
der Dateiname trägt die Jahreszahl (``... 2026.xlsx``) und wechselt mit dem
Schuljahr, der Ordner bleibt. Ist ``excel_ordner`` gesetzt, gewinnt die dort
gefundene Mappe gegen ``excel_pfad_kandidaten``; die Fundregel steht bei
:func:`mappe_im_ordner`.

``excel_pfad_kandidaten`` bleibt daneben bestehen und bleibt Pflicht: es ist der
ausgelieferte Standard für einen Rechner, auf dem noch niemand etwas eingestellt
hat, und im Arbeitskopie-Modus (``--config``, siehe ``START.sh``) der einzige
Weg, auf eine einzelne Datei zu zeigen.

## Zwei Ebenen: ausgelieferter Standard + Benutzerkonfiguration

``config.json`` im Repo-Wurzelverzeichnis ist der **ausgelieferte Standard**. Er
wird im Normalbetrieb **nie** beschrieben - ein Git-Pull oder eine Neukopie durch
``START.bat`` darf keine Anpassung der Lehrkraft verlieren. JSON kennt keine
Kommentare, ein Hinweis darauf lässt sich also nicht in die Datei selbst
schreiben; er steht deshalb hier.

Die **Benutzerkonfiguration** liegt in einem plattformabhängigen Ordner (siehe
``app.paths``) und enthält **nur die tatsächlich geänderten Schlüssel** - kein
Vollduplikat des Standards. Beim Laden wird sie flach über den Standard gelegt:
Schlüssel des Benutzers gewinnen, unbekannte oder fehlende Schlüssel fallen auf
den Standard zurück. ``match_overrides`` wird dabei ebenfalls flach ersetzt
(nicht schlüsselweise gemischt) - das lässt sich einer Lehrkraft leichter
erklären als ein Mischverhalten, das von Fall zu Fall unterschiedlich wirkt.

Ein fehlendes oder kaputtes Overlay verhindert den Start nicht: fehlt es, gilt
stillschweigend der Standard (das ist der Normalfall bei der Ersteinrichtung);
ist es vorhanden, aber kaputt (z. B. ungültiges JSON durch einen Handeditier-
Versuch), gilt ebenfalls der Standard, aber der Grund wird als Klartext-Hinweis
zurückgegeben, den der Aufrufer auf der Konsole ausgibt (siehe
``app.konfiguration.lade_einstellungen``).

``Einstellungen.laden(pfad)`` bleibt daneben bestehen: sie lädt **genau eine**
Datei ohne jedes Overlay. Das ist der Arbeitskopie-Modus (``--config PATH``,
siehe ``START.sh``) - dort sind Standard und Benutzerkonfiguration bewusst
dieselbe Datei, und genau diese wird auch wieder beschrieben.

## Migration alter Vollkopien

Bevor es dieses Overlay-Modell gab, kopierte ``START.bat`` die gesamte
``config.json`` einmalig nach ``%LOCALAPPDATA%\\sba-dashboard\\config.json`` und
``speichere_excel_pfad`` (heute ``speichere_benutzerwerte``) schrieb bei der
Ersteinrichtung in diese Kopie zurück.
Eine solche Vollkopie würde als Overlay jedes künftige Update des ausgelieferten
Standards maskieren, weil sie für jeden Schlüssel einen (zufällig passenden)
Wert mitbringt. Beim Laden werden deshalb Schlüssel des Overlays, deren Wert
mit dem aktuellen Standard übereinstimmt, einmalig verworfen; nur echte
Abweichungen - allen voran die vom Benutzer gewählte Kandidatenreihenfolge -
bleiben erhalten. Die bereinigte Fassung wird atomar zurückgeschrieben, aber
nur, wenn sich dabei etwas ändert.

## Unbekannte Schlüssel

Eine künftige Programmversion darf neue Schlüssel einführen, die eine ältere
Benutzerkonfiguration noch nicht kennt (oder umgekehrt: ein Overlay enthält
einen Schlüssel, den diese Programmversion nicht mehr liest). Das allein ist
kein Fehler - sonst würde ein Update den Start einer Konfiguration verhindern,
die vorher funktioniert hat. Unbekannte Schlüssel werden stattdessen gesammelt
(``Einstellungen.unbekannte_schluessel``) und bleiben so sichtbar, ohne den
Start zu blockieren.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from bestand.core import BestandConfig

from .dateien import schreibe_atomar as _atomar_schreiben
from .paths import benutzer_konfigurationspfad

_BEKANNTE_SCHLUESSEL = frozenset({
    "iserv_domain",
    "excel_ordner",
    "excel_pfad_kandidaten",
    "blatt_raster",
    "sicherheitsbestand",
    "match_overrides",
    "port",
    "backups_behalten",
})

_DOMAIN_MUSTER = re.compile(r"[A-Za-z0-9.-]+")

# Vierstellige Jahreszahl im Dateinamen - "Bestand- ... 2026.xlsx". Bewusst
# nicht strenger: welches Jahr gemeint ist, entscheidet die Mappe, nicht dieses
# Muster.
_JAHR_MUSTER = re.compile(r"(?<!\d)(\d{4})(?!\d)")


class EinstellungsFehler(ValueError):
    """Eine Konfiguration ist unbrauchbar; der Aufrufer entscheidet über die Folge."""


def _lies_json_objekt(pfad: Path) -> dict:
    """Liest eine JSON-Datei und meldet Fehler auf Deutsch.

    Wird sowohl für ``Einstellungen.laden`` als auch für den ausgelieferten
    Standard in ``laden_mit_benutzerkonfiguration`` benutzt - in beiden Fällen
    ist ein Fehler hier ein echter, nicht abfangbarer Fehler.
    """
    try:
        with open(pfad, encoding="utf-8") as handle:
            roh = json.load(handle)
    except FileNotFoundError as exc:
        raise EinstellungsFehler(f"config.json nicht gefunden: {pfad}") from exc
    except json.JSONDecodeError as exc:
        raise EinstellungsFehler(f"config.json ist kein gültiges JSON ({pfad}): {exc}") from exc
    if not isinstance(roh, dict):
        raise EinstellungsFehler(
            f"config.json muss ein JSON-Objekt sein, nicht {type(roh).__name__} ({pfad})."
        )
    return roh


def _schreibe_json_atomar(pfad: Path, daten: dict) -> None:
    """Schreibt eine JSON-Datei atomar - über ``app.dateien.schreibe_atomar``.

    Bis 2026-09-05 machte diese Funktion nur ``write_text`` gefolgt von einem
    einzelnen ``os.replace`` - ohne ``fsync`` und ohne Wiederholung, anders als
    der Sidecar-Cache (``app/cache.py``). Das war der einzige der drei
    Windows-Ersetzen-Orte im Programm ohne den Wiederholungs-Fix vom
    2026-09-04 (CI auf ``windows-latest``: ``os.replace`` scheitert dort mit
    ``PermissionError``, solange irgendein Handle auf die Zieldatei offen
    ist) - und ausgerechnet der heißeste: die Migration alter Vollkopien in
    ``laden_mit_benutzerkonfiguration`` (siehe Modul-Docstring) kann bei
    praktisch jedem Programmstart hierher schreiben. ``app.dateien`` bündelt
    die Nachbardatei-plus-``fsync``-plus-Wiederholung-Logik jetzt für beide
    Aufrufer (Cache und Benutzerkonfiguration) an einer Stelle.
    """
    _atomar_schreiben(pfad, json.dumps(daten, ensure_ascii=False, indent=2) + "\n")


def pruefe_domain(domain: str) -> str | None:
    """Gibt eine deutsche Fehlermeldung zurück, oder None, wenn die Domain taugt.

    Öffentlich, weil ``POST /api/einstellungen`` denselben Satz braucht, bevor
    etwas gespeichert wird: Der Server, den das Fenster schickt, soll an genau
    derselben Regel scheitern wie einer, der in der Datei steht - und mit
    demselben Wortlaut, allen voran dem Hinweis auf das überflüssige ``https://``.
    """
    if not domain:
        return "'iserv_domain' fehlt oder ist leer."
    schema, _, rest = domain.partition("://")
    if rest and schema.lower() in ("http", "https"):
        return (
            f"'iserv_domain' darf kein Schema enthalten - '{schema}://' streichen, "
            f"nur '{rest.rstrip('/')}' eintragen. Das ist ein häufiger Tippfehler."
        )
    if " " in domain or "/" in domain or domain.count(".") == 0 or not _DOMAIN_MUSTER.fullmatch(domain):
        return (
            f"'iserv_domain' ist kein gültiger Hostname ({domain!r}). Erlaubt sind nur "
            "Buchstaben, Ziffern, '-' und '.', mit mindestens einem Punkt, ohne Schema "
            "(kein 'https://') und ohne Pfad."
        )
    return None


def mappe_im_ordner(ordner: Path) -> Path | None:
    """Die Arbeitsmappe in ``ordner``, nach einer festen Regel gewählt.

    Die Regel muss vorhersagbar sein - eine Lehrkraft, die nicht erklären kann,
    *warum* das Programm diese Datei genommen hat, kann auch nicht erkennen,
    dass es die falsche war. Deshalb in dieser Reihenfolge:

    1. Nur ``.xlsx`` **direkt** im Ordner. Die Sicherungen liegen eine Ebene
       tiefer in ``backups/`` (siehe ``app.excel.speichere_mappe``) und fallen
       damit von selbst weg.
    2. Ohne ``~$…``: das sind Excels eigene Sperrdateien einer geöffneten Mappe,
       keine Arbeitsmappen.
    3. Bei mehreren: die größte vierstellige Jahreszahl im Dateinamen gewinnt -
       beim Schuljahreswechsel liegt die alte Mappe oft noch daneben.
    4. Bei Gleichstand: die jüngste Änderungszeit.

    Öffnet **keine** Datei: diese Funktion läuft bei jeder Anfrage über
    ``excel_pfad()``, und das kann ein Netzlaufwerk sein. Ob die gewählte Mappe
    brauchbar ist, prüft ``app.excel.validiere_excel_mappe`` - einmal, wenn der
    Ordner eingestellt wird.
    """
    try:
        dateien = [
            eintrag for eintrag in ordner.iterdir()
            if eintrag.suffix.lower() == ".xlsx"
            and not eintrag.name.startswith("~$")
            and eintrag.is_file()
        ]
    except OSError:
        # Ordner weg, Netzlaufwerk nicht verbunden, keine Leserechte: alles
        # dasselbe wie "keine Mappe gefunden". Der Aufrufer zeigt den Ordner an.
        return None
    if not dateien:
        return None

    def schluessel(pfad: Path) -> tuple[int, float]:
        jahre = [int(treffer) for treffer in _JAHR_MUSTER.findall(pfad.stem)]
        try:
            mtime = pfad.stat().st_mtime
        except OSError:
            mtime = 0.0
        return (max(jahre) if jahre else 0, mtime)

    return max(sorted(dateien), key=schluessel)


@dataclass(frozen=True)
class Einstellungen:
    iserv_domain: str
    excel_pfad_kandidaten: tuple[Path, ...]
    blatt_raster: str
    # Der im Programmfenster eingestellte Ordner. Gesetzt schlägt er die
    # Kandidatenliste (siehe Modul-Docstring "Ordner schlägt Kandidatenliste").
    excel_ordner: Path | None = None
    sicherheitsbestand: int = 5
    match_overrides: dict[str, str] = field(default_factory=dict)
    port: int = 8765
    backups_behalten: int = 30
    # Nicht Teil der Konfigurationsdatei selbst (daher ohne Gegenstück in
    # config.json): der Ort, an den speichere_benutzerwerte schreibt. Im
    # --config-Modus (Einstellungen.laden) zeigt das Feld auf dieselbe Datei,
    # die auch gelesen wurde. Im Produktivmodus
    # (laden_mit_benutzerkonfiguration) zeigt es auf die Benutzerkonfiguration
    # im plattformabhängigen Ordner, nie auf den ausgelieferten Standard. Bei
    # einer direkt konstruierten Einstellungen-Instanz (z. B. in Tests) bleibt
    # es None; der Aufrufer von speichere_benutzerwerte muss dann selbst wissen,
    # wohin geschrieben wird.
    benutzer_config_pfad: Path | None = None
    # Schlüssel, die beim Laden in der Konfiguration standen, aber von dieser
    # Programmversion nicht ausgewertet werden - gesammelt statt verworfen,
    # damit eine künftige Version neue Schlüssel einführen kann, ohne ältere
    # (oder neuere) Konfigurationen unlesbar zu machen. Siehe Modul-Docstring.
    unbekannte_schluessel: tuple[str, ...] = ()

    @classmethod
    def laden(cls, pfad: Path) -> "Einstellungen":
        """Lädt genau diese eine Datei, ohne jedes Overlay.

        Für den Arbeitskopie-Modus (``--config PATH``) und für Tests, die eine
        bestimmte Konfiguration ohne Plattformlogik prüfen wollen.
        """
        pfad = Path(pfad)
        roh = _lies_json_objekt(pfad)
        return cls._aus_rohdaten(roh, benutzer_config_pfad=pfad)

    @classmethod
    def laden_mit_benutzerkonfiguration(
        cls, standard_pfad: Path, benutzer_pfad: Path | None = None,
    ) -> tuple["Einstellungen", str | None]:
        """Lädt den ausgelieferten Standard, legt die Benutzerkonfiguration darüber.

        ``benutzer_pfad`` fehlt normalerweise und wird dann über
        ``app.paths.benutzer_konfigurationspfad`` aufgelöst; Tests geben ihn
        explizit an (typischerweise über ``SBA_CONFIG_DIR``), damit nichts im
        echten Benutzerprofil landet.

        Der ausgelieferte Standard muss gültig sein - ein Fehler dort ist ein
        echter Fehler und wird als ``EinstellungsFehler`` geworfen. Fehlt die
        Benutzerkonfiguration oder ist sie kaputt, verhindert das den Start
        dagegen **nicht**: der Standard gilt, und der Grund kommt als zweiter
        Rückgabewert (Klartext für die Konsole, sonst ``None``) zurück - diese
        Funktion selbst gibt nichts aus, damit sie ohne Seiteneffekt testbar
        bleibt.

        Wird nie im ``--config``-Modus aufgerufen; dafür bleibt
        ``Einstellungen.laden`` zuständig.
        """
        standard_pfad = Path(standard_pfad)
        benutzer_pfad = Path(benutzer_pfad) if benutzer_pfad is not None else benutzer_konfigurationspfad()

        standard_roh = _lies_json_objekt(standard_pfad)

        hinweise: list[str] = []
        overlay_roh: dict = {}
        if benutzer_pfad.is_file():
            try:
                overlay_roh = _lies_json_objekt(benutzer_pfad)
            except EinstellungsFehler as exc:
                hinweise.append(
                    f"Benutzerkonfiguration ist unbrauchbar, der ausgelieferte Standard gilt: {exc}"
                )
                overlay_roh = {}

        # Migration alter Vollkopien (siehe Modul-Docstring): Schlüssel, deren
        # Wert mit dem aktuellen Standard übereinstimmt, sind keine echten
        # Übersteuerungen, sondern Duplikate aus der Zeit vor dem
        # Overlay-Modell. _FEHLEND ist eine eigene Wache, damit ein Schlüssel,
        # den es im Standard gar nicht gibt, nicht fälschlich als "gleich"
        # durchgeht.
        _FEHLEND = object()
        bereinigt = {
            schluessel: wert
            for schluessel, wert in overlay_roh.items()
            if standard_roh.get(schluessel, _FEHLEND) != wert
        }
        migration_noetig = bool(overlay_roh) and bereinigt != overlay_roh

        zusammengefuehrt = {**standard_roh, **bereinigt}
        einstellungen = cls._aus_rohdaten(zusammengefuehrt, benutzer_config_pfad=benutzer_pfad)

        if migration_noetig:
            try:
                _schreibe_json_atomar(benutzer_pfad, bereinigt)
            except OSError as exc:
                hinweise.append(
                    f"Bereinigte Benutzerkonfiguration ({benutzer_pfad}) konnte nicht "
                    f"gespeichert werden, alte Vollkopie bleibt bestehen: {exc}"
                )
            else:
                hinweise.append(
                    f"Benutzerkonfiguration ({benutzer_pfad}) bereinigt: veraltete Duplikate "
                    "des ausgelieferten Standards entfernt, echte Abweichungen (z. B. der "
                    "gewählte Excel-Pfad) bleiben erhalten."
                )

        return einstellungen, ("\n".join(hinweise) if hinweise else None)

    @classmethod
    def _aus_rohdaten(cls, roh: dict, *, benutzer_config_pfad: Path | None) -> "Einstellungen":
        """Validiert die zusammengeführten Rohdaten und baut die Einstellungen.

        Gemeinsamer Kern von ``laden`` und ``laden_mit_benutzerkonfiguration``,
        damit beide Wege exakt dieselben Prüfungen durchlaufen.
        """
        domain_fehler = pruefe_domain(str(roh.get("iserv_domain", "")))
        if domain_fehler:
            raise EinstellungsFehler(f"config.json: {domain_fehler}")

        kandidaten = roh.get("excel_pfad_kandidaten")
        if not isinstance(kandidaten, list) or not kandidaten:
            raise EinstellungsFehler(
                "config.json: 'excel_pfad_kandidaten' muss eine nicht leere Liste von Pfaden sein."
            )
        if not all(isinstance(k, str) and k.strip() for k in kandidaten):
            raise EinstellungsFehler(
                "config.json: 'excel_pfad_kandidaten' darf nur nicht leere Textpfade enthalten."
            )

        ordner_roh = roh.get("excel_ordner")
        if ordner_roh is not None and (not isinstance(ordner_roh, str) or not ordner_roh.strip()):
            raise EinstellungsFehler(
                "config.json: 'excel_ordner' muss ein nicht leerer Textpfad sein "
                "(oder fehlen, dann gilt 'excel_pfad_kandidaten')."
            )

        blatt = roh.get("blatt_raster")
        if not isinstance(blatt, str) or not blatt.strip():
            raise EinstellungsFehler("config.json: 'blatt_raster' muss ein nicht leerer Text sein.")

        stock = roh.get("sicherheitsbestand", 5)
        if not isinstance(stock, int) or isinstance(stock, bool) or stock < 0:
            raise EinstellungsFehler("config.json: 'sicherheitsbestand' muss eine ganze Zahl >= 0 sein.")

        overrides = roh.get("match_overrides", {})
        if not isinstance(overrides, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in overrides.items()
        ):
            raise EinstellungsFehler(
                "config.json: 'match_overrides' muss ein Objekt aus Text-Schlüsseln und ISBNs sein."
            )

        port = roh.get("port", 8765)
        if not isinstance(port, int) or isinstance(port, bool) or not (1024 <= port <= 65535):
            raise EinstellungsFehler(
                "config.json: 'port' muss eine ganze Zahl zwischen 1024 und 65535 sein "
                "(Ports darunter brauchen unter Linux/macOS Rechte, die niemand haben soll)."
            )

        backups = roh.get("backups_behalten", 30)
        if not isinstance(backups, int) or isinstance(backups, bool) or not (0 <= backups <= 1000):
            raise EinstellungsFehler(
                "config.json: 'backups_behalten' muss eine ganze Zahl zwischen 0 und 1000 sein."
            )

        unbekannt = tuple(sorted(schluessel for schluessel in roh if schluessel not in _BEKANNTE_SCHLUESSEL))

        return cls(
            iserv_domain=str(roh["iserv_domain"]),
            excel_pfad_kandidaten=tuple(Path(str(k)) for k in kandidaten),
            blatt_raster=str(blatt),
            excel_ordner=Path(ordner_roh.strip()) if isinstance(ordner_roh, str) else None,
            sicherheitsbestand=stock,
            match_overrides=dict(overrides),
            port=port,
            backups_behalten=backups,
            benutzer_config_pfad=Path(benutzer_config_pfad) if benutzer_config_pfad is not None else None,
            unbekannte_schluessel=unbekannt,
        )

    # ── Pfadauflösung ─────────────────────────────────────────────────────────

    def gepruefte_pfade(self) -> list[tuple[Path, bool]]:
        """Alles, wo nach der Mappe gesucht wurde, mit dem Ergebnis.

        Für die Anzeige, wenn nichts gefunden wurde: "keine Datei gefunden" ohne
        die Angabe, *wo* gesucht wurde, ist auf einem Netzlaufwerk nicht zu
        klären. Steht ein ``excel_ordner`` fest, ist sein Ergebnis der erste
        Eintrag - entweder die gefundene Mappe oder der Ordner selbst mit
        ``False``, damit die Lehrkraft den eingestellten Ordner vor sich sieht
        und nicht nur die ausgelieferten Vorschläge.
        """
        eintraege: list[tuple[Path, bool]] = []
        if self.excel_ordner is not None:
            gefunden = mappe_im_ordner(self.excel_ordner)
            eintraege.append((gefunden, True) if gefunden else (self.excel_ordner, False))
        eintraege += [(pfad, pfad.is_file()) for pfad in self.excel_pfad_kandidaten]
        return eintraege

    def excel_pfad(self) -> Path | None:
        """Die Mappe aus dem eingestellten Ordner, sonst der erste existierende Kandidat."""
        for pfad, vorhanden in self.gepruefte_pfade():
            if vorhanden:
                return pfad
        return None

    def bestand_config(self) -> BestandConfig:
        """Übersetzt in die Konfiguration der Bibliothek (englische Feldnamen)."""
        pfad = self.excel_pfad()
        if pfad is None:
            raise EinstellungsFehler("Keine der eingetragenen Excel-Dateien wurde gefunden.")
        return BestandConfig(
            excel_path=pfad,
            sheet_name=self.blatt_raster,
            safety_stock=self.sicherheitsbestand,
            match_overrides=dict(self.match_overrides),
        )


def speichere_benutzerwerte(
    einstellungen: Einstellungen,
    *,
    iserv_domain: str | None = None,
    excel_ordner: Path | None = None,
) -> Einstellungen:
    """Schreibt geänderte Einstellungen in die Benutzerkonfiguration zurück.

    Schreibt **ausschließlich** in ``einstellungen.benutzer_config_pfad`` - nie
    in den ausgelieferten Standard. Im ``--config``-Modus ist das dieselbe
    Datei, die auch gelesen wurde; im Produktivmodus die Benutzerkonfiguration
    im plattformabhängigen Ordner, die dabei bei Bedarf angelegt wird.

    Nur die übergebenen Schlüssel werden verändert; alle anderen Schlüssel der
    Benutzerkonfiguration bleiben stehen. Das ist der Grund für die
    Schlüsselwort-Parameter statt eines ``**felder``: welche Werte das Fenster
    speichern darf, steht damit in der Signatur und nicht erst in einer Prüfung
    im Rumpf.

    Bis 2026-09-10 hieß diese Funktion ``speichere_excel_pfad`` und konnte genau
    einen Schlüssel schreiben - damals gab es auch nur eine Einstellung, die sich
    im Betrieb ändern ließ (die Datei, über ``POST /api/einrichtung``). Mit dem
    Programmfenster sind es zwei, und die Stelle, die atomar in das Overlay
    schreibt, soll eine bleiben.

    Gibt die neuen Einstellungen zurück; der Aufrufer ersetzt damit
    ``app.state.einstellungen``.
    """
    ziel = einstellungen.benutzer_config_pfad
    if ziel is None:
        raise EinstellungsFehler(
            "Keine Benutzerkonfiguration bekannt - 'einstellungen' wurde nicht über "
            "Einstellungen.laden() oder Einstellungen.laden_mit_benutzerkonfiguration() geladen."
        )
    ziel = Path(ziel)

    aenderungen: dict[str, str] = {}
    if iserv_domain is not None:
        aenderungen["iserv_domain"] = iserv_domain
    if excel_ordner is not None:
        aenderungen["excel_ordner"] = str(excel_ordner)
    if not aenderungen:
        return einstellungen

    vorhanden: dict = {}
    if ziel.is_file():
        try:
            vorhanden = _lies_json_objekt(ziel)
        except EinstellungsFehler:
            # Die Datei ist bereits kaputt - beim Schreiben heilt sie sich
            # selbst, statt den Speichervorgang an einer fremden Altlast
            # scheitern zu lassen.
            vorhanden = {}

    vorhanden.update(aenderungen)
    _schreibe_json_atomar(ziel, vorhanden)

    return replace(
        einstellungen,
        iserv_domain=iserv_domain or einstellungen.iserv_domain,
        excel_ordner=excel_ordner or einstellungen.excel_ordner,
    )
