# Was noch offen ist

Stand: 2026-09-04. Diese Datei löst `PLAN.md` als Arbeitsliste ab; `PLAN.md`
bleibt als abgeschlossener v1-Plan liegen.

## Die CI ist gelaufen — was sie bestätigt hat

Der erste Lauf hat die Annahme abgeräumt, die beim Einrichten offen blieb: das
Standard-`GITHUB_TOKEN` checkt die beiden öffentlichen Geschwister-Repos ohne
zusätzliches Secret in den Workspace aus, `astral-sh/setup-uv@v10.0.1` greift,
und der Abgleich von `requirements.txt` gegen `uv export` läuft in neun
Sekunden durch. Linux 3.10 und 3.11 sind grün.

Zwei Dinge, die dabei aufgefallen sind und behoben wurden:

- Es gab **keine Zeitgrenze**, weder je Job noch je Test. Ein Lauf, der nicht
  von selbst endet, hätte die GitHub-Vorgabe von 360 Minuten ausgeschöpft.
  Jetzt: `timeout-minutes: 30` je Job und `pytest-timeout` mit
  `--timeout-method=thread`, das im Ernstfall den Stack jedes Threads ausgibt
  statt schweigend weiterzulaufen.
- Die Suite brauchte **74 Sekunden** statt der angenommenen zehn. Der
  Nachmessung nach war das keine langsame Datei-Ein- und -Ausgabe, sondern ein
  Fehler in `bestand.core.grid`, der auch das Dashboard selbst betraf — siehe
  den nächsten Abschnitt. Nach der Behebung: 9,6 Sekunden.

## Nebenbefund aus der CI: `parse_grid` war 92x zu langsam

Die auffällige Laufzeit der Testsuite hatte eine Ursache, die den Schul-Laptop
unmittelbar betrifft. `bestand.core.grid` fragte für jede Zelle über
`"K3" in merged` ab, ob sie in einem Zellenverbund liegt. Openpyxl baut dabei
jedes Mal ein neues `CellRange` samt Prüfung seiner vier Deskriptoren — am
echten Blatt (142 Zellenverbünde) **1496 µs je Abfrage**. `parse_grid` stellt
rund 250.000 solcher Abfragen und brauchte damit **gut drei Sekunden**.

Das Dashboard ruft `parse_grid` bei **jedem** Seitenaufruf und **jeder**
Zellenänderung auf. Die drei Sekunden lagen also auf jedem Klick, zusätzlich
zur Wartezeit über das Netzlaufwerk.

Behoben in `sba-bestand` durch einen reinen Ganzzahlvergleich der vier Grenzen
(`merge_deckt_ab`) — inhaltlich dieselbe Prüfung, die `CellRange.__contains__`
am Ende auch macht, nur ohne Objektbau: 7,5 µs statt 1496 µs.
`parse_grid` fällt damit von **3,09 s auf 0,034 s** (Faktor 92), das Raster
ist unverändert (72 Zeilen, 16 Sperrflächen), und alle 43 Tests von
`sba-bestand` bleiben grün.

Beim Testlauf auf dem Schul-Laptop ist das die Erklärung, falls jemand die
Oberfläche von früher als zäh in Erinnerung hat. Nicht mituntersucht:
`sba-launcher/core/catalog.py` hat eigene Kopien derselben Hilfsfunktionen mit
demselben Muster — dort lohnt sich derselbe Handgriff, gehört aber nicht in
dieses Repo.

## Nur Niklas kann es erledigen

### 1. Testlauf auf dem Schul-Laptop

Der einzige Punkt, an dem wirklich Hardware fehlt. Alles andere ist offline
geprüft. Ablauf und Abnahmekriterien stehen in
[`schul-laptop-test.md`](schul-laptop-test.md); `tools/diagnose.py` sammelt die
Messwerte, die dabei anfallen, in eine Datei, die man mitschicken kann.

Am 2026-09-04 wurde die Liste **offline vorweggenommen**, soweit das ohne
Windows geht (Abschnitt „Trockenlauf" dort). Ergebnis: die Diagnose läuft mit
Rückgabewert 0 durch, meldet beide Geschwister-Pakete als installiert und das
Raster mit den erwarteten 72 Zeilen und 16 Sperrflächen; die Migration einer
alten Vollkopie (Abschnitt C) kürzt sie auf den einen abweichenden Schlüssel
ein, lässt den ausgelieferten Standard unangetastet und schreibt beim zweiten
Start nichts mehr; das Cache-Ausweichen auf den lokalen Ordner funktioniert
samt Rücklesen. Am Gerät bleibt damit das, was Windows, SMB, IServ und eine
Uhr braucht.

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
