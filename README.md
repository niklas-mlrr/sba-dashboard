# sba-dashboard

Weboberfläche für die **Bestands- und Nachbestellungsliste** der Schulbuchausleihe.
Sie zeigt das 62 Spalten breite Excel-Raster als gewöhnliche, filter- und
sortierbare Liste, schreibt geänderte Zahlen zurück und holt den Stand auf Knopf-
druck aus IServ.

Die Anwendung läuft lokal auf dem Rechner der Lehrkraft und hört nur auf
`127.0.0.1`. Die Mappe enthält personenbezogene Zahlen.

## Stand

Lesen, Schreiben, Abrufen und Starten sind fertig und gegen die echte Mappe
geprüft. Offen ist die **Nachfolge-Anleitung** (`docs/nachfolge-anleitung.md`)
und der Testlauf auf dem Schul-Laptop. Der vollständige Plan steht in
[`docs/PLAN.md`](docs/PLAN.md), die Entwurfsgründe in
[`docs/architektur.md`](docs/architektur.md).

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

Zum Ausprobieren braucht es eine Mappe. Der Pfad steht in `config.json` unter
`excel_pfad_kandidaten` — eine **Liste**, weil dieselbe Datei auf dem einen
Rechner über einen Laufwerksbuchstaben und auf dem anderen über UNC erreichbar
ist. Der erste existierende Pfad gewinnt; existiert keiner, zeigt die Startseite
alle geprüften Pfade.

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
venv anlegen, dann `python -m app.start`. Bei späteren Starts vergleicht es
`requirements.txt` mit dem zuletzt erfolgreich installierten Stand und
aktualisiert Pakete nur bei einer Änderung. `requirements.txt` wird erzeugt,
nicht von Hand gepflegt:

```bash
uv export --no-dev --no-hashes --no-emit-project \
    --no-emit-package iserv-ausleihe-api --no-emit-package sba-bestand \
    --format requirements-txt -o requirements.txt
```

Die beiden Geschwister-Repos stehen bewusst nicht darin — sie kommen über den
`PYTHONPATH` (Begründung in `docs/architektur.md`).

## Gestaltung

`app/static/app.css` beginnt mit einem kleinen Satz Farb- und Schrift-Marken.
Sie sind **vorläufig**: das Dashboard soll sich am offiziellen
Schulbuchausleihe-Modul orientieren, dafür fehlt noch eine Vorlage. Wenn sie da
ist, werden nur die Werte in `:root` ersetzt.
