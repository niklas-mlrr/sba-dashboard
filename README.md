# sba-dashboard

Weboberfläche für die **Bestands- und Nachbestellungsliste** der Schulbuchausleihe.
Sie zeigt das 62 Spalten breite Excel-Raster als gewöhnliche, filter- und
sortierbare Liste, schreibt geänderte Zahlen zurück und holt den Stand auf Knopf-
druck aus IServ.

Die Anwendung läuft lokal auf dem Rechner der Lehrkraft und hört nur auf
`127.0.0.1`. Die Mappe enthält personenbezogene Zahlen.

## Stand

Lesen, Schreiben, Abrufen und Starten sind fertig und gegen die echte Mappe
geprüft. Ebenfalls seit 2026-09-19 lässt sich der **Arbeitsstand der
Bücherlisten speichern** — Freigabe durch die
Fachkonferenzleitungen, Einführung und Ausmusterung je Fach und Jahrgang sowie
Rücklagen für die Fachschaften. Er liegt als Exceldatei je Schuljahr neben der
Bestandsmappe (`buecherlisten/planung/`,
[`docs/architektur.md`](docs/architektur.md#die-buchplanung-listen-freigeben-einführung-und-ausmusterung),
Regeln in [`buecherlisten/planung/README.md`](buecherlisten/planung/README.md)); eingetragen wird in
den Bücherlisten-Seiten selbst. Seit 2026-09-20 öffnet dort ein Klick auf eine
Buchzeile ein **Planungsmenü** (Einführung und Ausmusterung je Jahrgang,
„+ Jahrgang“, Rücklage, Bemerkungen) mit Abbrechen und Speichern; was geplant
ist, steht danach in der Jahrgang-Spalte der Liste — `7, 8 (ab 2028/2029)`.
Seit 2026-09-24 steht darin zuerst die **Buchreihe** wie in IServ: Titel,
Verlag (mit Vorschlägen beim Tippen), Neupreis und Leihgebühr lassen sich
korrigieren; die ISBN steht grau hinterlegt darüber und bleibt, wie sie ist. Die Korrektur steht in der Planungsdatei und gilt in allen
Bücherlisten und PDFs. IServ selbst bleibt unverändert.
Bestätigt wird weiterhin die Liste als Ganzes, über „Liste bestätigen“ oben auf
der Seite. Seit 2026-09-19 gibt es außerdem den Reiter **Mehrjahresbände**: er vergleicht
die Jahrgangs-Bücherlisten zweier Schuljahre und schreibt daraus die Übersicht,
welche Bücher abzugeben sind — weiter in dieselbe Exceldatei wie bisher
(`mehrjahresbaende/`, [`docs/architektur.md`](docs/architektur.md#die-mehrjahresbände-übersicht)). Kopf und Bücherlisten (nach Fach, Verlag und Jahrgang, alle drei mit Druck
als PDF) folgen seit 2026-09-17 dem IServ-Modul Schulbuchausleihe. Beim
Jahrgang druckt „Schülerliste" die Druckversion aus IServ statt der eigenen. Offen ist vor
allem der **Testlauf auf dem Schul-Laptop** ([Prüfliste](docs/schul-laptop-test.md)).

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
| `GET /buecherliste/{fach,verlag,jahrgang}` | Bücherlisten-Übersicht aus der Buchplanungs-Datei, Abweichungen zu IServ markiert (braucht Anmeldung) |
| `GET /buecherliste/{ansicht}/{name}` | Bücher eines Fachs, Verlags oder Jahrgangs |
| `GET /buecherliste/{ansicht}/pdf` | Bücherlisten mehrerer Fächer, Verlage oder Jahrgänge als PDF (Druckmenü, Optionen in der URL, Antwort `inline`) |
| `GET /buecherliste/{ansicht}/{name}/pdf` | Bücherliste eines Fachs, Verlags oder Jahrgangs als PDF |
| `GET /mehrjahresbaende` | Übersicht, welche Bücher am Schuljahreswechsel abzugeben sind (aus der Exceldatei, ohne Anmeldung) |
| `GET /api/buchplanung?schuljahr=…` | Der gespeicherte Stand eines Schuljahrs als JSON (ohne Datei: `planung: null`) |
| `POST /api/buchplanung/abgleich` | Beide Schuljahre aus IServ holen und zusammenführen: `{schuljahr?, vorjahr?}` → 200/400/401/423/502/503 |
| `POST /api/buchplanung/fach` | Freigabe der Fachkonferenzleitung: `{schuljahr, fach, kuerzel, datum, mtime}` → 200/400/409/423/503 |
| `POST /api/buchplanung/buch` | Das Planungsmenü eines Buchs in einem Fach, in einem Zug: `{schuljahr, isbn, fach, zeilen: [{jahrgang, eingefuehrt_ab, ausgemustert_nach, bemerkung}], ruecklage, buchreihe, mtime}` — `zeilen` ist der ganze Stand, ein fehlender Jahrgang wird gelöscht; `buchreihe` `{titel, verlag, neupreis, leihgebuehr}` korrigiert die Angaben aus IServ in der Datei (auf „Buchreihen“, IServ-Wert als Kommentar) |
| `POST /api/buchplanung/planung` | Eine einzelne Zeile: `{schuljahr, isbn, fach, jahrgang, eingefuehrt_ab, ausgemustert_nach, kuerzel, datum, mtime}` |
| `POST /api/buchplanung/ruecklage` | Rücklage einer Fachschaft: `{schuljahr, isbn, fach, anzahl, status, mtime}` |
| `GET /api/mehrjahresbaende` | dieselbe Übersicht als JSON |
| `POST /api/mehrjahresbaende/erzeugen` | Aus zwei Schuljahren neu rechnen und die Datei schreiben: `{schuljahr?, vorjahr?}` → 200/400/401/423/502/503 |
| `POST /api/mehrjahresbaende/marke` | Eine Zelle ändern: `{jahrgang, fach, marke, mtime}` → 200/400/409/423/503 |
| `GET /api/rows` | Zeilen als JSON, mit `mtime` und Cache-Alter |
| `POST /api/cell` | Eine Zahl ändern: `{key, spalte, wert, mtime}` → 200/400/409/423/500/503 |
| `GET /api/einstellungen` | Server, Ordner und gefundene Mappe (fürs Fenster) |
| `POST /api/einstellungen` | Server und Ordner festlegen: `{server, ordner}` → 200/400/500 |
| `POST /api/anmeldung` | Bei IServ anmelden: `{benutzer, passwort}` → 200/400/401/403/504 |
| `GET /api/anmeldung` | Wer angemeldet ist und wann es verfällt (nie das Passwort) |
| `DELETE /api/anmeldung` | Abmelden, Client verwerfen |
| `POST /api/refresh` | Abruf starten, **ohne Körper** → 202/401/409/503 |
| `GET /api/refresh/status` | Fortschritt des Abrufs (immer 200) |
| `POST /api/beenden` | Server beenden (Knopf im Programmfenster) |
| `GET /health` | `{"status": "ok"}` |

Jede Fehlerantwort hat die Form `{"fehler": "<deutscher Klartext>"}`; welche
Ausnahme zu welchem Status wird, steht als Tabelle in
[`docs/architektur.md`](docs/architektur.md#ausnahme--http-steht-an-genau-einer-stelle).

Bedient wird das Programm über ein **eigenes Fenster** (tkinter): dort meldet man
sich bei IServ an, stellt Server und Ordner der Mappe ein, öffnet die Seite
erneut und beendet das Dashboard — auch dann, wenn der Browser-Tab längst zu ist.
Die Zugangsdaten werden **nie gespeichert**; sie liegen für die Laufzeit im
IServ-Client und verfallen nach 30 Minuten ohne Abruf. Warum das Passwort
überhaupt gehalten werden muss und was das Zeitschloss daran ändert, steht in
[`docs/architektur.md`](docs/architektur.md#die-anmeldung-einmal-im-fenster-mit-zeitschloss).

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
  sba-dashboard/    dieses Repo
```

Bis 2026-09-18 stand daneben ein drittes Repo, `sba-bestand`. Seine beiden
Pakete liegen jetzt hier:

```
app/                Weboberfläche: FastAPI, Templates, Programmfenster
bestand/            Excel-Kern (core/) + das Bestands-CLI
buecherlisten/      Bücherlisten-Kern (core/), die Buchplanung (planung/),
                    trg_web.py + das Listen-CLI
mehrjahresbaende/   Mehrjahresbände-Kern (core/) + das Übersichts-CLI
tests/              Tests der Weboberfläche
tests/bibliothek/   Tests der drei Bibliothekspakete
tools/              Diagnose und Vorlagen-Erzeuger, nicht Teil des Starts
vorlage/            leere Excel-Vorlage für START.sh und die Tests
```

Was die beiden Pakete enthalten und warum sie hier liegen, steht in
[`docs/bibliothek.md`](docs/bibliothek.md).

```bash
uv sync --all-groups
uv run pytest            # offline, ohne IServ und ohne echte Excel-Datei
uv run ruff check app tests bestand buecherlisten mehrjahresbaende
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

Server und Ordner lassen sich im Fenster hinterm Zahnrad einstellen; welche
`.xlsx` im Ordner genommen wird, entscheidet eine feste Regel
(`app.settings.mappe_im_ordner`: keine `~$…`-Sperrdateien, größte Jahreszahl im
Namen, bei Gleichstand die jüngste Änderungszeit).

`config.json` ist der **ausgelieferte Standard** und wird im Betrieb nie
beschrieben; Anpassungen landen in einer Benutzerkonfiguration im
plattformabhängigen Ordner (`SBA_CONFIG_DIR` überschreibt ihn), und
`--config PATH` schaltet in den Arbeitskopie-Modus. Welcher Ordner auf welcher
Plattform, was validiert wird und wie eine alte Vollkopie migriert wird, steht
in [`docs/architektur.md`](docs/architektur.md#zwei-ebenen-ausgelieferter-standard--benutzerkonfiguration).

```bash
uv run python -m app.start           # freier Port, Fenster; Browser nach der Anmeldung
uv run python -m app.start --kein-browser   # Browser nur über "Seite öffnen"
uv run python -m app.start --kein-fenster   # nur Server, beenden mit Strg+C
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765   # ohne Beenden-Knopf
```

Ohne Bildschirm — der Entwicklungs-VPS, die CI — fällt der Start von selbst auf
`--kein-fenster` zurück und sagt das auf der Konsole. Eine Anmeldemaske gibt es
dann nicht; ein Abruf braucht dort ein `POST` auf `/api/anmeldung`.

## macOS und Linux: mit Arbeitskopie starten

`START.bat` ist nur für den Schul-Laptop mit Windows. Auf macOS und Linux
startet `START.sh` das Dashboard mit einer lokalen Arbeitskopie. Standardmäßig
nimmt es die mitgelieferte, leere Excel-Vorlage. Sie hat dieselben Blätter,
Merges, Formeln und Formatierungen wie die echte Mappe, aber keine Arbeitsdaten.
Das Geschwister-Layout aus `ausleihe-api/` und `sba-dashboard/` bleibt für die
Python-Abhängigkeiten nötig.

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

`START.bat` ist der einzige Einstieg für die Lehrkraft: Python suchen, die
beiden Quellbäume nach `%LOCALAPPDATA%\sba-dashboard\` spiegeln, beim ersten
Mal ein venv anlegen, `ausleihe-api` dort hinein installieren, dann
`python -m app.start`. Bei späteren Starts vergleicht es `requirements.txt` mit
dem zuletzt erfolgreich installierten Stand und aktualisiert Pakete nur bei einer
Änderung; den Client installiert es nur neu, wenn `robocopy` gemeldet hat, dass
sich an seinen Quellen etwas geändert hat. `bestand/` und `buecherlisten/`
brauchen diesen Weg seit 2026-09-18 nicht mehr — sie liegen im gespiegelten
Projektbaum selbst und werden von dort importiert wie `app`.

`requirements.txt` wird erzeugt, nicht von Hand gepflegt:

```bash
uv export --no-dev --no-hashes --no-emit-project \
    --no-emit-package iserv-ausleihe-api \
    --format requirements-txt -o requirements.txt
```

`ausleihe-api` steht bewusst nicht darin: als Pfad-Abhängigkeit hätte es in einer
Datei, die auf einem fremden Rechner mit `pip install -r` verarbeitet wird, keine
gültige Adresse. `START.bat` installiert es stattdessen aus dem gespiegelten
Quellbaum mit `pip install --no-build-isolation --no-deps` in dasselbe venv. **Zur Laufzeit ist deshalb kein `PYTHONPATH` mehr nötig** — die
Anwendung hängt an nichts außer dem venv.

Warum es zwei Repos bleiben (und seit 2026-09-18 nicht mehr drei), was die
Alternativen wären (uv-Workspace, versionierte Wheels) und wie man den Schritt
zurückdreht, steht in [`docs/verteilung.md`](docs/verteilung.md).

## Gestaltung

`app/static/app.css` beginnt mit einem kleinen Satz Farb- und Schrift-Marken.
Sie sind **vorläufig**: das Dashboard soll sich am offiziellen
Schulbuchausleihe-Modul orientieren, dafür fehlt noch eine Vorlage. Wenn sie da
ist, werden nur die Werte in `:root` ersetzt.
