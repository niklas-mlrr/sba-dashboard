# `bestand/` und `buecherlisten/` — das Excel-Tooling

Zwei Pakete und zwei Kommandozeilenwerkzeuge, die die IServ-Ausleihe-API **nur
lesend** (GET) abfragen und daraus Dateien erzeugen:

| Ordner | Werkzeug | Ergebnis |
|--------|----------|----------|
| `bestand/core/` | Bibliothek | Excel-Raster lesen, IServ-Snapshot holen, Zahlen eintragen — netzfrei testbar |
| `bestand/` | `update_bestand_auto.py` | Kommandozeilen-Schale um `core/`: trägt Bestands-/Anmeldezahlen in die Excel-Liste ein |
| `buecherlisten/core/` | Bibliothek | Bücherdaten gruppieren und als PDF setzen — das, was auch das Dashboard druckt |
| `buecherlisten/` | `generate_booklists.py` | erzeugt die Bücherlisten-PDFs je Fach, Verlag oder Jahrgang (`--view`) |
| `buecherlisten/trg_web.py` | Bibliothek | die drei TRG-Website-Scraper (Fachkonferenzleitungen, Fächer, Kollegium) — netzlos testbar, siehe `tests/bibliothek/test_trg_web.py` |

Es wird **nie** nach IServ geschrieben.

Die Weboberfläche in `app/` benutzt `bestand.core` für jeden Abruf und jedes
Speichern (`app/refresh.py`, `app/excel.py`, `app/rows.py`) und
`buecherlisten.core` für den Druck der Listen (`app/api/buecherliste.py`). Die
beiden CLIs sind der zweite Nutzer derselben Pakete: sie laufen ohne die
Weboberfläche, direkt von der Kommandozeile.

## `bestand/core/` — die Bibliothek

Seit 2026-09-04 steckt die Logik nicht mehr im Skript, sondern in einem Paket.
Das war nötig, damit die Weboberfläche dieselbe Excel-Behandlung benutzt, statt
sie ein zweites Mal nachzubauen.

| Modul | Inhalt |
|-------|--------|
| `core/config.py` | `config.json` laden und prüfen |
| `core/grid.py` | Excel-Struktur: Fachblöcke, Mehrjahresbänder, „nicht angeboten"-Sperrflächen |
| `core/iserv.py` | `Snapshot` aus IServ — der Client wird **injiziert**, nie selbst gebaut |
| `core/update.py` | Snapshot anwenden, Blatt „zu Bestellen" neu aufbauen |
| `core/testing.py` | synthetisches Prüf-Workbook + Fake-IServ, von der App und den Bibliothekstests benutzt |

Nichts davon liest `os.environ`, lädt eine `.env`, parst Argumente oder schreibt
nach stdout. Genau daran hängt, dass sowohl ein Webserver als auch ein Skript
dieselben Funktionen aufrufen können. Die Tests laufen ohne Netz und ohne die
echte Mappe:

```bash
uv sync --all-groups
uv run pytest tests/bibliothek
```

`tests/bibliothek/test_cli_golden.py` friert die Konsolenausgabe von
`update_bestand_auto.py` ein — der Refactor hat sie zeichengleich gelassen.

Die Struktur-Befunde, die den Entwurf bestimmen (keine Bezahlt-Spalte,
Formelspalten, Merge-Topologie, Sperrflächen), stehen in
[`docs/architektur.md`](architektur.md).

## Voraussetzung: `ausleihe-api` daneben

Für die **Abrufe** braucht das Tooling das Repo
[`ausleihe-api`](https://github.com/niklas-mlrr/ausleihe-api) **direkt neben**
diesem — dort liegen der Python-Client (`ausleihe`) und die `.env` mit den
IServ-Zugangsdaten. Das Layout und die Einrichtung stehen in der
[README](../README.md); hier gilt nur der eine Punkt:

Dieses Repo hält bewusst **keine eigenen Secrets**. Fehlt `ausleihe-api/.env`,
brechen die beiden CLIs mit einer Meldung zu fehlenden `ISERV_*`-Variablen ab.

reportlab und pypdf sind seit 2026-09-18 gewöhnliche Abhängigkeiten, kein Extra
mehr (Begründung in `pyproject.toml` und in [`verteilung.md`](verteilung.md)):
`uv sync` genügt, ein `--extra pdf` gibt es nicht mehr.

## Benutzung

Siehe `bestand/README.md` und `buecherlisten/README.md`. Die vollständige
Anleitung für Nachfolger liegt in
[`nachfolge-anleitung.md`](nachfolge-anleitung.md) und in
[`ausleihe-ausgabe/docs/nachfolge-anleitung.md`](https://github.com/niklas-mlrr/ausleihe-ausgabe/blob/main/docs/nachfolge-anleitung.md)
(Teil 3).

## Herkunft

Bis 2026-08-21 lagen beide Werkzeuge im Repo `ausleihe-api` (als
`bestand- und nachbestellungen/` und `buecherlisten-nach-fach/`). Sie wurden
herausgelöst, weil `ausleihe-api` eine wiederverwendbare Bibliothek ist,
während dies hier schulspezifische Anwendungen sind — zunächst in ein eigenes
Repo, `sba-bestand`.

Am **2026-09-18** ist dieses Repo in `sba-dashboard` aufgegangen. Der Grund war
das Verhältnis von Aufwand zu Inhalt: für zwei importierte Pakete kostete die
Trennung drei Repos, zwei mypy-Läufe, zwei Testsuiten, je einen zusätzlichen
Checkout-Schritt pro CI-Job und ein Geschwister-Layout, das jeder Klon, jede
CI-Datei und das Startskript kennen mussten. Das Dashboard war der einzige
Leser der Bibliothek; ein Paketrand zwischen zwei Ordnern derselben Anwendung
trennte nichts, was getrennt gehörte. Diese Datei ist die ehemalige `README.md`
jenes Repos.

Das GitHub-Repo `niklas-mlrr/sba-bestand` bleibt **online und eingefroren**:
`sba-launcher` klont es und startet daraus `bestand/update_bestand_auto.py`.
Änderungen hier erreichen den Launcher daher nicht — siehe
[`verteilung.md`](verteilung.md).
