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
| [`docs/PLAN.md`](docs/PLAN.md) | Der abgeschlossene v1-Plan, historisch |

| Route | Zweck |
|-------|-------|
| `GET /` | Tabellenansicht (serverseitig gerendert) |
| `GET /api/rows` | Zeilen als JSON, mit `mtime` und Cache-Alter |
| `POST /api/cell` | Eine Zahl ändern: `{key, spalte, wert, mtime}` → 200/400/409/423 |
| `POST /api/refresh` | Abruf starten: `{benutzer, passwort}` → 202/400/401/403/504 |
| `GET /api/refresh/status` | Fortschritt des Abrufs (immer 200) |
| `POST /api/beenden` | Server beenden (Knopf in der Oberfläche) |
| `GET /health` | `{"status": "ok"}` |

Änderbar sind nur **Bestand** und **Bestellt**, und nur über den Zeilenschlüssel —
`/api/cell` nimmt keine freie Zellreferenz entgegen. Der Browser schickt die
`mtime` mit, die er gesehen hat; weicht sie ab, gibt es 409 statt eines stillen
Überschreibens. Diese Änderungszeit ist Pflicht. Ein gemeinsames Datei-Schloss
serialisiert außerdem manuelle Änderungen und IServ-Abrufe über Threads,
Dashboard-Prozesse und Rechner hinweg, sofern das SMB-Laufwerk Dateisperren
unterstützt.

Zugangsdaten für den Abruf kommen ausschließlich im POST-Körper an, werden sofort
mit `login()` geprüft und danach fallen gelassen — nie in `app.state`, nie in
einem Log, nie in einer Antwort.

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
```

Dieselben Schritte laufen in der CI (`.github/workflows/ci.yml`) auf Linux mit
Python 3.10 und 3.11 sowie auf Windows — letzteres nicht als Beigabe: die
Dateisperre (`msvcrt.locking` statt `fcntl.flock`), der Schreibpfad und die
`~$…`-Sperrdatei verhalten sich dort anders, und dort läuft die Anwendung
produktiv. Ein weiterer Job prüft, dass `requirements.txt` dem `uv export`
entspricht.

`tools/diagnose.py` prüft auf einem fremden Rechner die Kette vom Python bis zur
Arbeitsmappe und schreibt einen Bericht, den man weitergeben kann. Es schreibt
nie in die Mappe und braucht keine Zugangsdaten.

Zum Ausprobieren braucht es eine Mappe. Der Pfad steht in `config.json` unter
`excel_pfad_kandidaten` — eine **Liste**, weil dieselbe Datei auf dem einen
Rechner über einen Laufwerksbuchstaben und auf dem anderen über UNC erreichbar
ist. Der erste existierende Pfad gewinnt; existiert keiner, zeigt die Startseite
alle geprüften Pfade.

`config.json` ist der **ausgelieferte Standard** und wird im Betrieb nie
beschrieben. Was die Lehrkraft auswählt, landet in einer Benutzerkonfiguration
mit nur den abweichenden Schlüsseln — unter Windows in
`%LOCALAPPDATA%\sba-dashboard\config.json`, unter macOS in
`~/Library/Application Support/sba-dashboard/`, unter Linux in
`$XDG_CONFIG_HOME/sba-dashboard/` (bzw. `~/.config/…`). `SBA_CONFIG_DIR`
überschreibt den Ordner. Ein `--config PATH` schaltet in den
Arbeitskopie-Modus: dann sind Standard und Benutzerkonfiguration genau diese
eine Datei. Details in [`docs/architektur.md`](docs/architektur.md).

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

Die Kopie liegt danach in `.local/` und bleibt bei weiteren Starts erhalten.
Zum Zurücksetzen diese Datei löschen. Für einen Test mit einer echten Mappe
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
