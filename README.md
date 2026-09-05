# sba-dashboard

Weboberfläche für die **Bestands- und Nachbestellungsliste** der Schulbuchausleihe.
Sie zeigt das 62 Spalten breite Excel-Raster als gewöhnliche, filter- und
sortierbare Liste, schreibt geänderte Zahlen zurück und holt den Stand auf Knopf-
druck aus IServ.

Die Anwendung läuft lokal auf dem Rechner der Lehrkraft und hört nur auf
`127.0.0.1`. Die Mappe enthält personenbezogene Zahlen.

## Stand

Lesen, Schreiben, Abrufen und Starten sind fertig und gegen die echte Mappe
geprüft. Offen sind nur noch der **Testlauf auf dem Schul-Laptop**
([Prüfliste](docs/schul-laptop-test.md)) und die **Gestaltungsvorlage**, für die
es noch keine Referenz gibt.

| Dokument | Wofür |
|----------|-------|
| [`docs/nachfolge-anleitung.md`](docs/nachfolge-anleitung.md) | Bedienung, ohne Vorwissen |
| [`docs/architektur.md`](docs/architektur.md) | Warum es so gebaut ist |
| [`docs/verteilung.md`](docs/verteilung.md) | Wie es auf den Laptop kommt, Migration und Rollback |
| [`docs/roadmap.md`](docs/roadmap.md) | Was offen ist |
| [`docs/schul-laptop-test.md`](docs/schul-laptop-test.md) | Prüfliste für den Testlauf |

`docs/archiv/` enthält abgeschlossene Dokumente, die nur noch als Beleg dienen —
derzeit den v1-Erstellungsplan.

[`docs/architektur.md`](docs/architektur.md) ist die **kanonische** Beschreibung
des Entwurfs. Was dort steht, wird hier nicht wiederholt, sondern verlinkt.

| Route | Zweck |
|-------|-------|
| `GET /` | Tabellenansicht (serverseitig gerendert) |
| `GET /api/rows` | Zeilen als JSON, mit `mtime` und Cache-Alter |
| `POST /api/cell` | Eine Zahl ändern: `{key, spalte, wert, mtime}` → 200/400/409/423/500/503 |
| `POST /api/einrichtung` | Excel-Pfad festlegen: `{pfad}` → 200/400/500 |
| `POST /api/refresh` | Abruf starten: `{benutzer, passwort}` → 202/400/401/403/409/504 |
| `GET /api/refresh/status` | Fortschritt des Abrufs (immer 200) |
| `POST /api/beenden` | Server beenden (Knopf in der Oberfläche) |
| `GET /health` | `{"status": "ok"}` |

Jede Fehlerantwort hat die Form `{"fehler": "<deutscher Klartext>"}`; welche
Ausnahme zu welchem Status wird, steht als Tabelle in
[`docs/architektur.md`](docs/architektur.md#ausnahme--http-steht-an-genau-einer-stelle).

Änderbar ist nur **Bestellt**, und nur über den Zeilenschlüssel —
`/api/cell` nimmt keine freie Zellreferenz entgegen, und die beim Laden gesehene
`mtime` ist Pflicht. Warum es diese vier Schutzschichten braucht und was jede
einzelne verhindert, steht in
[`docs/architektur.md`](docs/architektur.md#der-schreibpfad-vier-schutzschichten).

Alle Anfragen müssen an `127.0.0.1` oder `localhost` adressiert sein
(`Host`-Prüfung gegen DNS-Rebinding), und zustandsändernde Anfragen mit fremdem
`Origin` werden abgelehnt. Beides ist keine Anmeldung — Begründung und Grenzen
in [`docs/architektur.md`](docs/architektur.md#was-die-bindung-allein-nicht-abdeckt).

## Entwickeln

Das **Geschwister-Layout ist verbindlich** (siehe `../README.md`):

```
<irgendein-ordner>/
  ausleihe-api/     IServ-Client + .env
  sba-bestand/      Bibliothek bestand/core/ + CLI
  sba-dashboard/    dieses Repo
```

```bash
uv sync --all-groups
uv run pytest            # offline, ohne IServ und ohne echte Excel-Datei
uv run ruff check app tests
uv run mypy              # Dateiliste und Strenge in pyproject.toml
```

Die Suite läuft offline und misst dabei ihre eigene Abdeckung (`--cov` steht in
den `addopts`). Konkrete Zahlen stehen bewusst nicht hier, sondern in der
Ausgabe des letzten Laufs — sie ändern sich mit jedem Commit, und eine falsche
Zahl im README ist schlimmer als keine. Die Schwelle von 85 % erzwingt nur die
CI, damit ein Teillauf während der Arbeit an einer einzelnen Datei nicht rot
wird.

`--timeout=300` je Test steht in `pyproject.toml` — eine Notbremse gegen einen
Test, der unbegrenzt auf einem Schloss oder einem Kindprozess wartet, keine
Leistungsvorgabe.

Dieselben Schritte laufen in der CI (`.github/workflows/ci.yml`) auf Linux mit
Python 3.10 und 3.11 sowie auf Windows — letzteres nicht als Beigabe: die
Dateisperre (`msvcrt.locking` statt `fcntl.flock`), der Schreibpfad und die
`~$…`-Sperrdatei verhalten sich dort anders, und dort läuft die Anwendung
produktiv. Auch mypy läuft auf jedem Runner mit dessen eigener Plattform: es
prüft immer nur den Zweig, den es dort gibt. Ein weiterer Job prüft, dass
`requirements.txt` dem `uv export` entspricht.

`tools/diagnose.py` prüft auf einem fremden Rechner die Kette vom Python bis zur
Arbeitsmappe und schreibt einen Bericht, den man weitergeben kann. Es schreibt
nie in die Mappe und braucht keine Zugangsdaten.

Zum Ausprobieren braucht es eine Mappe. Der Pfad steht in `config.json` unter
`excel_pfad_kandidaten` — eine **Liste**, weil dieselbe Datei auf dem einen
Rechner über einen Laufwerksbuchstaben und auf dem anderen über UNC erreichbar
ist. Der erste existierende Pfad gewinnt; existiert keiner, zeigt die Startseite
alle geprüften Pfade.

`config.json` ist der **ausgelieferte Standard** und wird im Betrieb nie
beschrieben; Anpassungen landen in einer Benutzerkonfiguration im
plattformabhängigen Ordner (`SBA_CONFIG_DIR` überschreibt ihn), und
`--config PATH` schaltet in den Arbeitskopie-Modus. Welcher Ordner auf welcher
Plattform, was validiert wird und wie eine alte Vollkopie migriert wird, steht
in [`docs/architektur.md`](docs/architektur.md#zwei-ebenen-ausgelieferter-standard--benutzerkonfiguration).

```bash
uv run python -m app.start           # sucht einen freien Port, oeffnet den Browser
uv run python -m app.start --kein-browser
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765   # ohne Beenden-Knopf
```

## macOS und Linux: mit Arbeitskopie starten

`START.bat` ist nur für den Schul-Laptop mit Windows. Auf macOS und Linux
startet `START.sh` das Dashboard mit einer lokalen Arbeitskopie. Standardmäßig
nimmt es die mitgelieferte, leere Excel-Vorlage. Sie hat dieselben Blätter,
Merges, Formeln und Formatierungen wie die echte Mappe, aber keine Arbeitsdaten.
Das Geschwister-Layout aus `ausleihe-api/`, `sba-bestand/` und
`sba-dashboard/` bleibt für die Python-Abhängigkeiten nötig.

```bash
cd ~/projects/sba/sba-dashboard
chmod +x START.sh       # nur beim ersten Mal
./START.sh
```

Beim ersten Start braucht der Mac [`uv`](https://docs.astral.sh/uv/):

```bash
brew install uv
```

Die Kopie liegt danach als `Bestand- und Nachbestellungsliste 2026.xlsx` im
Projektordner selbst — sichtbar, damit man sie im Dateimanager findet und in
Excel öffnen kann — und bleibt bei weiteren Starts erhalten. Daneben entsteht
`config.local.json`, die auf sie zeigt. Beides ist in `.gitignore` und wird von
`START.bat` nicht auf einen Schul-Rechner gespiegelt. Zum Zurücksetzen die
Mappe löschen. Für einen Test mit einer echten Mappe
den Pfad ausdrücklich mitgeben:

```bash
SBA_ORIGINAL_EXCEL="/voller/Pfad/Bestand- und Nachbestellungsliste 2026.xlsx" ./START.sh
```

Die Vorlage wird mit `tools/erzeuge_vorlage.py` aus einer echten Mappe erzeugt.
Das Werkzeug leert die veränderlichen Rasterwerte und Tabellenkörper, entfernt
Kommentare und Hyperlinks und setzt harmlose Dokumenteigenschaften. Es ist nur
für eine kontrollierte Aktualisierung der Vorlage gedacht.

## Auf dem Schul-Laptop

`START.bat` ist der einzige Einstieg für die Lehrkraft: Python suchen, die drei
Quellbäume nach `%LOCALAPPDATA%\sba-dashboard\` spiegeln, beim ersten Mal ein
venv anlegen, `ausleihe-api` und `sba-bestand` dort hinein installieren, dann
`python -m app.start`. Bei späteren Starts vergleicht es `requirements.txt` mit
dem zuletzt erfolgreich installierten Stand und aktualisiert Pakete nur bei einer
Änderung; die beiden Bibliotheken installiert es nur neu, wenn `robocopy`
gemeldet hat, dass sich an ihren Quellen etwas geändert hat.

`requirements.txt` wird erzeugt, nicht von Hand gepflegt:

```bash
uv export --no-dev --no-hashes --no-emit-project \
    --no-emit-package iserv-ausleihe-api --no-emit-package sba-bestand \
    --format requirements-txt -o requirements.txt
```

Die beiden Geschwister-Repos stehen bewusst nicht darin: als Pfad-Abhängigkeiten
hätten sie in einer Datei, die auf einem fremden Rechner mit `pip install -r`
verarbeitet wird, keine gültige Adresse. `START.bat` installiert sie stattdessen
aus den gespiegelten Quellbäumen mit `pip install --no-build-isolation --no-deps`
in dasselbe venv. **Zur Laufzeit ist deshalb kein `PYTHONPATH` mehr nötig** — die
Anwendung hängt an nichts außer dem venv.

Warum es drei Repos bleiben, was die Alternativen wären (uv-Workspace,
versionierte Wheels) und wie man den Schritt zurückdreht, steht in
[`docs/verteilung.md`](docs/verteilung.md).

## Gestaltung

`app/static/app.css` beginnt mit einem kleinen Satz Farb- und Schrift-Marken.
Sie sind **vorläufig**: das Dashboard soll sich am offiziellen
Schulbuchausleihe-Modul orientieren, dafür fehlt noch eine Vorlage. Wenn sie da
ist, werden nur die Werte in `:root` ersetzt.
