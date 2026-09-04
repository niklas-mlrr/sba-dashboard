# Was noch offen ist

Stand: 2026-09-04. Diese Datei löst `PLAN.md` als Arbeitsliste ab; `PLAN.md`
bleibt als abgeschlossener v1-Plan liegen.

## Nur Niklas kann es erledigen

### 1. Testlauf auf dem Schul-Laptop

Der einzige Punkt, an dem wirklich Hardware fehlt. Alles andere ist offline
geprüft. Ablauf und Abnahmekriterien stehen in
[`schul-laptop-test.md`](schul-laptop-test.md); `tools/diagnose.py` sammelt die
Messwerte, die dabei anfallen, in eine Datei, die man mitschicken kann.

Besonders zu prüfen, weil hier zuletzt etwas Grundlegendes umgestellt wurde:

- Der erste Start nach der Umstellung installiert `ausleihe-api` und
  `sba-bestand` ins venv (vorher `PYTHONPATH`). Dauert das länger als ein paar
  Sekunden? Läuft es beim **zweiten** Start ohne Neuinstallation durch?
- Eine schon vorhandene `%LOCALAPPDATA%\sba-dashboard\config.json` aus der alten
  Fassung: bleibt der ausgewählte Excel-Pfad nach der Migration erhalten?
- Ist der Sidecar-Cache auf dem Gruppenlaufwerk schreibbar, oder weicht das
  Dashboard auf den lokalen Ordner aus? (Die Antwort steht in den Warnungen des
  Abrufs.)

### 2. Gestaltungsvorlage — weiterhin blockiert

**Offen und nicht auflösbar, solange keine Referenz vorliegt.** Das Dashboard
soll sich am offiziellen Schulbuchausleihe-Modul orientieren. Es gibt lokal
keine brauchbare Vorlage: die PNGs in `ausleihe-ausgabe/` sind Clipart,
`web/scan-view.css` ist iOS-Stil.

Gebraucht werden Screenshots des Moduls oder eine Beschreibung von Farben,
Typografie, Tabellenkopf und Knopfformen. Bis dahin läuft `app/static/app.css`
mit einem zurückhaltenden Platzhaltersatz an Marken; wenn die Vorlage da ist,
werden **nur die Werte in `:root`** ersetzt, nicht die Regeln darunter.

## Bewusst zurückgestellt

### Versionierte Wheels für die drei Repos

Heute binden sich die Repos über Pfade aneinander; ausgeliefert wird per Install
ins venv. Das trägt, solange eine Person an allen drei Repos gleichzeitig
arbeitet. Der Wechsel auf versionierte Wheels lohnt sich, sobald ein zweiter
Rechner eine *andere* Fassung von `sba-bestand` fahren soll als der
Entwicklungsstand. Begründung und Umschaltpunkt: [`verteilung.md`](verteilung.md).

### Refresh überschreibt Bestand und Bestellt

Bekannte Eigenschaft, keine Panne: der Abruf schreibt alle drei Spalten, wie es
das abgelöste Skript tat. Änderungen aus dem Browser an Bestand und Bestellt
leben also nur bis zum nächsten Abruf. Die Oberfläche sagt das an der Spalte
dazu. Eine Zusammenführung wäre erst sinnvoll, wenn jemand feststellt, dass ihn
das im Alltag stört.

### `zu Bestellen` im Browser bearbeiten

Nicht vorgesehen. Das Blatt wird beim Abruf neu aufgebaut; eine Bearbeitung
darin wäre beim nächsten Lauf weg, ohne dass es jemand merkt.

## Erledigt und damit hier nur noch als Stichwort

Lesen, Schreiben, IServ-Abruf, Windows- und macOS-Start, Ersteinrichtung mit
geprüfter Mappe, prozessübergreifende Schreibsperre, gehärteter Sidecar-Cache,
Trennung von ausgeliefertem Standard und Benutzerkonfiguration, eigenständige
Auslieferung ohne `PYTHONPATH`, CI mit Ruff und pytest auf Linux und Windows.
Wo das jeweils steht, sagt [`architektur.md`](architektur.md).
