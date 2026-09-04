# sba-dashboard v1 — Erstellungsplan
Stand: 2026-09-04. Wird bei Freigabe zu `sba-dashboard/docs/PLAN.md`.

## 0. Befunde aus dem Deep-Dive (bestimmen den Entwurf)

1. Kein `Bezahlt` im echten Workbook. Zustandslabels: Angemeldet/Bestand/Bestellt/zu bestellen, je 15x.
2. `zu bestellen` sind echte Formeln. Mit `data_only=False` laden -> Formeln bleiben erhalten,
   Werte sind nicht lesbar -> in Python rechnen.
3. Die **Merge-Topologie der Bestand-Spalte definiert die Zeilengruppe**:
   K3:K4 = Jg 5-6 ein Band, BC4:BC7 = Jg 6-9 ein Band, AU9:AU12 = Jg 11-12.
   Angemeldet bleibt je Jahrgang einzeln (J3=94, J4=73) und wird summiert:
   `=J3+J4-K3-L3`. Gruppenschluessel = Anker der Bestand-Zelle.
4. Merges ueber die volle Fachblock-Breite (4 Spalten, z.B. R3:U5, AD3:AG6, AX6:BA9,
   B12:E13) sind **"nicht angeboten"**-Flaechen, alle leer. Heute nur zufaellig
   verschont (match_book findet kein Buch). Wird explizite Regel + Test.
5. `update_bestand_auto.py` ist ein 450-Zeilen-`main()` mit argparse, Netz, Excel-Walk,
   Schreiben, Tabellenumbau und `print` vermischt. Der Refactor zieht daraus eine
   Bibliothek; die CLI bleibt Wort fuer Wort ausgabegleich.

## 1. Ablage: drei Geschwister-Repos

    ~/projects/sba/
      ausleihe-api/     unveraendert (Client + .env, nur Entwicklung)
      sba-bestand/      Refactor: neues Paket bestand/core/
      sba-dashboard/    NEU -> github niklas-mlrr/sba-dashboard

`sba-dashboard/pyproject.toml` bindet beide per `[tool.uv.sources]` als
editable-Pfad, identisches Muster wie sba-bestand und ausleihe-ausgabe.

## 2. Refactor sba-bestand: bestand/core/

Neu, rein, ohne os.environ/dotenv/print/argparse:

- `config.py`   BestandConfig.load(path) -> excel_path, sheet_name, safety_stock, match_overrides
- `grid.py`     Excel-Struktur (aus update_bestand_auto verschoben):
                resolve_anchor, classify_row, extract_grade, strip_hint,
                find_fach_for_col, find_zustand_for_col
                NEU: parse_grid(ws) -> Grid
- `iserv.py`    fetch_snapshot(client, sy_id=None, *, progress=None) -> Snapshot
                (load_grade_books, fetch_enrollment_counts_by_grade, fetch_series_data)
                Client wird **injiziert**, nie selbst gebaut.
- `update.py`   apply_snapshot(wb, grid, snapshot, cfg) -> UpdateResult
                rebuild_zu_bestellen(wb, result, snapshot, safety_stock)
                load_bestellt_counts(ws)
- `__init__.py` re-exportiert die oeffentliche Flaeche

Datenmodell:

    @dataclass(frozen=True)
    class GridSlot:                 # eine Zustandszelle
        zustand: str                # angemeldet|bestand|bestellt|zu_bestellen
        ref: str                    # Ankerreferenz, z.B. "K3"
        row: int; col: int
        span_rows: tuple[int, ...]  # alle vom Merge ueberdeckten Zeilen

    @dataclass(frozen=True)
    class GridEntry:                # eine Zeile der spaeteren Liste
        key: str                    # stabil: f"{block}:{fach_label}:{bestand_ref}"
        block: int                  # 0 = Sek I, 1 = Oberstufe
        fach_label: str             # "Politik (eA)"
        subject: str; hint: str|None
        grades: tuple[int, ...]     # (5,) oder (5,6)
        slots: dict[str, GridSlot]
        angemeldet_refs: tuple[str, ...]   # je Jahrgang eine

    @dataclass(frozen=True)
    class Grid:
        entries: tuple[GridEntry, ...]
        stand_refs: tuple[str, ...]
        blocked: tuple[str, ...]    # "nicht angeboten"-Flaechen

    @dataclass(frozen=True)
    class Snapshot:                 # alles aus IServ, kein Excel
        schoolyear_id: str; fetched_at: datetime
        booklists_by_grade: dict[int, dict]
        grade_books: dict[int, list[dict]]
        enrolled: dict[tuple[int,str], int]
        paid: dict[tuple[int,str], int]
        series_data: dict[str, dict]

    @dataclass
    class UpdateResult:
        changes: list[CellChange]; skipped: list[str]; diagnostics: list[str]
        zu_bestellen_rows: list[ZuBestellenRow]
        isbn_by_entry: dict[str, str]        # entry.key -> ISBN  (fuer den Cache)
        stand: datetime

`update_bestand_auto.py` schrumpft auf ~90 Zeilen: argparse, dotenv,
`AusleiheClient()`, Aufruf der core-Funktionen, unveraenderte Ausgabe,
`atomic_save_workbook`. Ein Golden-Test sichert die Ausgabegleichheit.

## 3. sba-dashboard: Ordner

    sba-dashboard/
      START.bat                 einziger Einstieg fuer die Lehrkraft
      config.json               ausgeliefert, ohne Secrets
      config.beispiel.json      kommentiert (Doku-Kopie)
      pyproject.toml  uv.lock  requirements.txt   (letzteres via `uv export`)
      app/
        __init__.py  main.py    FastAPI-App + Routen
        settings.py             config.json laden, Pfadkandidaten aufloesen
        excel.py                Lesen/Schreiben, Sperren, Konflikte, Backups
        rows.py                 Grid -> flaches Zeilenmodell + zu_bestellen in Python
        refresh.py              Refresh-Job (Thread, Fortschritt, Credentials im RAM)
        cache.py                Sidecar-Cache (ISBN/Titel/Preis der letzten Abfrage)
        templates/base.html  index.html
        static/app.js  app.css  (vanilla, kein Build)
      tests/
      docs/nachfolge-anleitung.md  architektur.md  PLAN.md
      README.md  .gitignore  LICENSE

## 4. config.json

    {
      "iserv_domain": "iserv-trg-oha.de",
      "excel_pfad_kandidaten": [
        "\\\\iserv.iserv-trg-oha.de\\Gruppen\\Buchausleihe Admins\\Bestand- und Nachbestellungsliste 2026.xlsx",
        "N:\\Buchausleihe Admins\\Bestand- und Nachbestellungsliste 2026.xlsx"
      ],
      "blatt_raster": "Bestand- und Nachbestellung",
      "sicherheitsbestand": 5,
      "match_overrides": {},
      "port": 8765,
      "backups_behalten": 30
    }

Liste statt einem Pfad loest Laufwerksbuchstabe-vs-UNC: der erste existierende
gewinnt; existiert keiner, zeigt `/` eine Fehlerseite mit den geprueften Pfaden.
Deutsche Schluessel, weil die Lehrkraft die Datei bearbeitet.

## 5. Routen

    GET  /                      Tabellenansicht (Jinja2, serverseitig gerendert)
    GET  /api/rows              JSON: Zeilen + mtime + Stand + Cache-Alter
    POST /api/cell              {key, spalte: bestand|bestellt, wert, mtime} -> 200/409/423
    POST /api/refresh           {benutzer, passwort} -> 202 + job_id
    GET  /api/refresh/status    {phase, fortschritt, fertig, fehler, zusammenfassung}
    POST /api/beenden           Server sauber stoppen (Knopf in der UI)
    GET  /health                {"status":"ok"}

Refresh laeuft im Hintergrund-Thread (60-90 s: /series?detailed=true,
enrollments, Buecherliste je Jahrgang). Ein Modul-Lock erlaubt genau einen Lauf.
Credentials: nur POST-Body, direkt in `AusleiheClient(domain, user, pw)`,
`client.login()` als Fail-Fast, danach lokale Referenzen loeschen. Nie auf
app.state, nie geloggt, nie in einer Antwort.

Fehlerabbildung: AuthError -> 401 "Zugangsdaten stimmen nicht",
ForbiddenError -> 403 "Ihr Konto hat keine Ausleihe-Verwalter-Rolle",
TransportError -> 504, diagnostics nicht leer -> 422 mit der Liste, **nichts gespeichert**.

## 6. Zeilenmodell (rows.py)

Pro GridEntry eine Zeile:

    Fach | Jg | Titel | ISBN | Angemeldet | Bestand | Bestellt | zu bestellen

- Jg: "5" oder "5-6" aus `entry.grades`
- Angemeldet: Summe ueber `angemeldet_refs` (Mehrjahresbaende!)
- zu bestellen: `angemeldet - bestand - bestellt`, **in Python**, nie aus der Formel
- Titel/ISBN/Preis aus dem Sidecar-Cache; fehlt er, bleiben die Spalten leer und
  ein Hinweis sagt "erst nach dem ersten Abruf verfuegbar"
- "nicht angeboten"-Flaechen erscheinen nicht
- Filter "nur Zeilen mit Bedarf" (`zu bestellen > 0`) und Sortierung: reines JS,
  keine Serverrunde

## 7. Excel-Zugriff (excel.py)

- Immer `load_workbook(path)` (data_only=False), nie ein Workbook zwischen Requests halten
- Schreiben: neu laden -> Anker setzen -> `atomic_save_workbook(wb, path, backup_dir=path.parent/"backups")`
- `PermissionError` -> HTTP 423 + Klartext "Die Datei ist gerade in Excel geoeffnet.
  Bitte schliessen und erneut versuchen."; liegt `~$<name>.xlsx` daneben, wird der
  darin stehende Benutzername mitgenannt
- Konflikt: Client schickt die `mtime`, die er gesehen hat; weicht sie ab -> 409
  "Die Datei wurde inzwischen geaendert, bitte neu laden"
- `/api/cell` akzeptiert **keine freie Zellreferenz**: `key` wird gegen das frisch
  geparste Grid aufgeloest, Spalte nur `bestand` oder `bestellt`, Wert nur
  int >= 0 oder leer
- Backups auf die `backups_behalten` neuesten kuerzen

## 8. START.bat

1. Python finden (Leiter aus START-TEST.bat: portable -> `py -3` -> `python`),
   sonst Klartextanleitung ohne Admin
2. `robocopy /MIR` der drei Quellbaeume (ohne .git/.venv/__pycache__) nach
   `%LOCALAPPDATA%\sba-dashboard\app\` — Quelle bleibt auf dem Netzlaufwerk,
   Ausfuehrung lokal
3. venv unter `%LOCALAPPDATA%\sba-dashboard\venv` (nicht Temp, nicht SMB),
   nur beim ersten Mal; `pip install -r requirements.txt`
4. Freien Port ab `config.port` suchen (8765..8775), `uvicorn` an **127.0.0.1**
5. Browser oeffnen, Fenster als Serverkonsole offen lassen, Banner
   "Dieses Fenster nicht schliessen"; Beenden per Knopf in der UI oder Fenster zu

## 9. Tests (pytest, offline, kein Netz, keine echte Excel)

Fixture baut ein synthetisches Workbook mit openpyxl: zwei Fach/Jahrgang-Bloecke,
ein Mehrjahres-Merge, eine "nicht angeboten"-Flaeche, ein `bestellt`-Blatt und
eine `zuBestellen`-Tabelle mit Ergebniszeile.

sba-bestand:
- `test_grid_parse.py`   Anker, Mehrjahres-Gruppierung, Oberstufenblock,
                         Fach-Fallback auf hoehere Zeile, blockierte Flaechen
- `test_apply_snapshot.py` richtige Anker, Dedup-Regeln, Mehrdeutigkeit -> diagnostics,
                         "kein Buch" -> skipped statt Abbruch
- `test_zu_bestellen.py` Tabellengeometrie, Bestell-Nr.-Uebernahme per ISBN,
                         Ergebniszeile, 0-Treffer-Fall
- `test_cli_golden.py`   Ausgabe von update_bestand_auto.py unveraendert

sba-dashboard:
- `test_rows.py`         "5-6"-Spanne, Angemeldet-Summe, zu_bestellen in Python,
                         Formelzellen bleiben nach Speichern Formeln
- `test_cell_write.py`   nur bestand/bestellt, unbekannter key -> 400,
                         mtime-Konflikt -> 409
- `test_lock.py`         PermissionError -> 423 mit Klartext
- `test_refresh.py`      401/403/504-Abbildung; Passwort taucht in keiner Antwort
                         und in keinem Log auf; zweiter Refresh waehrend eines
                         laufenden -> 409
- `test_settings.py`     Pfadkandidaten, fehlende Datei -> Fehlerseite
- `test_health.py`

## 10. Doku

- `docs/nachfolge-anleitung.md` — deutsch, ohne Vorwissen, Stil der bestehenden
  Anleitung: Starten, Tabelle lesen, Zahl aendern, Abruf mit eigenem IServ-Konto,
  "Excel ist offen"-Meldung, Backups, was tun wenn nichts geht
- `docs/architektur.md` — die vier Befunde oben, Merge-Topologie, warum 127.0.0.1,
  warum venv in LOCALAPPDATA
- `README.md` — Entwicklerpfad (uv sync, Geschwister-Layout, Tests)

## 11. Reihenfolge

1. Refactor sba-bestand -> core/, CLI-Golden-Test gruen (kein Netz noetig)
2. sba-dashboard-Geruest: repo, pyproject, settings, /health, Fixtures
3. rows.py + / + Tabelle (Lesepfad, ohne IServ) — hier ist der erste sichtbare Erfolg
4. excel.py Schreibpfad + /api/cell (Sperre, Konflikt, Backups)
5. refresh.py + /api/refresh (+ Cache-Sidecar)
6. START.bat + requirements.txt, Testlauf auf dem Schul-Laptop
7. Doku, Nachfolge-Anleitung, Repo auf GitHub

## 12. Offener Punkt zur Kenntnis

Der Refresh ueberschreibt Bestand und Bestellt (so entschieden, Paritaet zum
Skript). Browser-Aenderungen an diesen beiden Spalten leben also nur bis zum
naechsten Abruf. Die UI sagt das an der Spalte dazu ("wird beim naechsten Abruf
ueberschrieben"), damit es niemanden ueberrascht.
