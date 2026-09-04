# sba-dashboard

Weboberfläche für die **Bestands- und Nachbestellungsliste** der Schulbuchausleihe.
Sie zeigt das 62 Spalten breite Excel-Raster als gewöhnliche, filter- und
sortierbare Liste und wird später Zahlen zurückschreiben und den IServ-Abruf
auslösen.

Die Anwendung läuft lokal auf dem Rechner der Lehrkraft und hört nur auf
`127.0.0.1`. Die Mappe enthält personenbezogene Zahlen.

## Stand

Fertig ist der **Lesepfad**: Mappe finden, Raster parsen, Tabelle anzeigen.
Schreiben (`/api/cell`), der IServ-Abruf (`/api/refresh`), `START.bat` und die
Nachfolge-Anleitung sind geplant — der vollständige Plan steht in
[`docs/PLAN.md`](docs/PLAN.md), die Struktur-Befunde in
[`docs/architektur.md`](docs/architektur.md).

| Route | Zweck |
|-------|-------|
| `GET /` | Tabellenansicht (serverseitig gerendert) |
| `GET /api/rows` | Zeilen als JSON, mit `mtime` und Cache-Alter |
| `GET /health` | `{"status": "ok"}` |

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
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
```

## Gestaltung

`app/static/app.css` beginnt mit einem kleinen Satz Farb- und Schrift-Marken.
Sie sind **vorläufig**: das Dashboard soll sich am offiziellen
Schulbuchausleihe-Modul orientieren, dafür fehlt noch eine Vorlage. Wenn sie da
ist, werden nur die Werte in `:root` ersetzt.
