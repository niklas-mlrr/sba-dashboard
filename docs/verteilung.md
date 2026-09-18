# Verteilungsgrenze: zwei Repos, ein venv

Stand: 2026-09-04, zur Zusammenlegung fortgeschrieben am 2026-09-18. Diese
Datei beantwortet eine Frage, die der Wartbarkeits-Durchgang aufgeworfen hat:
**wie kommen `ausleihe-api` und `sba-dashboard` auf den Schul-Laptop, ohne dass
die Anwendung davon abhängt, wo genau die Ordner liegen?**

Es waren drei Repos, bis `sba-bestand` am 2026-09-18 in `sba-dashboard`
aufgegangen ist. Die Abwägung unten ist deshalb an zwei Stellen eingetroffen und
wird nicht nachträglich glattgezogen: Möglichkeit 1 („Monorepo") war für *alle
drei* Repos verworfen — und ist für genau eines davon am Ende doch gewählt
worden. Der Unterschied ist der, der in der Begründung schon stand: `sba-bestand`
war keine wiederverwendbare Bibliothek mit eigenen Nutzern, sondern hatte genau
einen Leser. `ausleihe-api` hat drei und bleibt getrennt.

Bis hierher galt: das Geschwister-Layout ist verbindlich, und `START.bat` setzt
zur Laufzeit einen `PYTHONPATH` auf die beiden Nachbarordner. Das funktioniert,
koppelt aber die *laufende* Anwendung an eine Ordnerstruktur. Ein halb
gespiegelter Ordner, ein umbenannter Nachbar oder ein Fenster mit altem
`PYTHONPATH` bricht sie an einer Stelle, an der niemand mehr sucht.

## Die drei Möglichkeiten

### 1. uv-Workspace / Monorepo

Ein Workspace verlangt **eine** Wurzel mit einer `pyproject.toml`, die die
Mitglieder auflistet. Die drei Projekte sind aber drei eigene GitHub-Repos, und
`~/projects/sba/` ist absichtlich kein Repo. Ein Workspace hieße also entweder
die drei Repos zusammenlegen, oder ein viertes Repo als Wurzel einführen, das
die anderen drei als Submodule oder Unterordner trägt.

Dagegen sprechen drei Dinge:

* `ausleihe-api` ist die einzige wirklich wiederverwendbare Bibliothek und wird
  auch von `ausleihe-ausgabe` und `sba-launcher` benutzt. Sie in ein
  Dashboard-Monorepo zu ziehen macht sie zum Anhängsel eines Werkzeugs.
* Die Repo-Trennung ist die Übergabegrenze: ein Nachfolger kann `sba-dashboard`
  verstehen, ohne die Scan-Station zu lesen.
* Der Gewinn wäre ein gemeinsamer Lockfile. Den gibt es faktisch schon, weil
  `uv.lock` des Dashboards die Pfad-Abhängigkeiten mitauflöst.

**Verworfen** — Aufwand an der Repo-Struktur, Gewinn nur an der Lockfile.

### 2. Versionierte Wheels

`ausleihe-api` und (damals) `sba-bestand` würden Versionen bekommen, gebaut und
veröffentlicht (PyPI oder GitHub Releases); `sba-dashboard` hinge an
`iserv-ausleihe-api==0.2.*`.

Das ist die richtige Antwort, sobald es mehrere Nutzer mit unterschiedlichen
Stufen gibt. Heute nicht: jede Änderung an `bestand/core/` bräuchte einen
Versionsschub, einen Build und eine Freigabe, bevor das Dashboard sie sieht.
Bei einer Person, die an allen drei Repos gleichzeitig arbeitet, ist das genau
der Schritt, der in der Praxis übersprungen wird — und dann ist die Version im
Lockfile eine Lüge.

**Zurückgestellt** — richtig für später, jetzt Prozessaufwand ohne Nutzen.
Wann es sich lohnt: sobald ein zweiter Rechner eine *andere* Fassung von
`sba-bestand` fahren soll als der Entwicklungsstand.

### 3. Pfad-Abhängigkeiten in der Entwicklung, echter Install in der Auslieferung

**Gewählt.** Die Grenze läuft zwischen Entwickeln und Ausliefern:

* **Entwickeln** bleibt wie bisher: `[tool.uv.sources]` bindet die beiden
  Nachbarrepos als editable-Pfad ein. Eine Änderung in `bestand/core/` ist im
  Dashboard sofort sichtbar, ohne Build und ohne Versionsschub. Das
  Geschwister-Layout bleibt für Entwicklung und Tests verbindlich.
* **Ausliefern** hängt an nichts mehr außer dem venv. `START.bat` spiegelt die
  Quellbäume wie bisher nach `%LOCALAPPDATA%`, installiert dann aber
  `ausleihe-api` als gewöhnliches (nicht editable) Paket in dasselbe venv:

  ```bat
  pip install --no-build-isolation --no-deps "%CODE%\ausleihe-api"
  ```

  Bis 2026-09-18 stand hier ein zweiter Pfad, `"%CODE%\sba-bestand"`. Er ist
  weggefallen, ohne die Regel zu brechen: `bestand/` und `buecherlisten/` liegen
  jetzt im gespiegelten `sba-dashboard`-Baum selbst, also im
  Arbeitsverzeichnis, aus dem `python -m app.start` läuft. Sie werden von dort
  importiert wie `app` — und hängen damit an genau derselben einen Kopie, nicht
  an einem Ordner daneben.

  Danach ist kein `PYTHONPATH` mehr gesetzt. Die Spiegelordner sind nur noch
  Bauzutat, nicht Laufzeitabhängigkeit.

Drei Details, die diese Variante überhaupt tragfähig machen:

* `--no-build-isolation` benutzt das `setuptools`, das beim Anlegen des venv
  mitinstalliert wird, statt bei jedem Update eines aus dem Netz zu holen.
  Damit läuft ein Update auch dann, wenn der Laptop gerade offline ist.
* `--no-deps` hält `requirements.txt` als **einzige** Quelle für Paketversionen.
  Sonst könnte ein Sibling-Install eine andere `openpyxl`-Fassung nachziehen als
  die aus dem Lockfile exportierte.
* Neu installiert wird nur, wenn `robocopy` gemeldet hat, dass sich an den
  Geschwisterbäumen etwas geändert hat (Rückgabecode 1), oder wenn das venv neu
  ist. Ein gewöhnlicher Start baut also nichts.

## Was noch mit umgezogen ist

`atomic_save_workbook` lag in `ausleihe/inventory_excel.py`, also im
IServ-Client. Die Funktion kennt weder IServ noch HTTP, nur Dateisystem und
openpyxl. Sie liegt jetzt in `bestand/core/excel_io.py`, wo die CLI der
Bestandsliste und das Dashboard sie beide brauchen. `match_book` bleibt in
`ausleihe-api`: es prüft Buchdaten der API auf Eindeutigkeit und wird auch von
`sba-launcher` benutzt.

`reportlab` ist in `sba-bestand` von einer Pflicht- zu einer
Extra-Abhängigkeit geworden (`sba-bestand[pdf]`). Nur
`buecherlisten/generate_booklists.py` braucht es. Vorher installierte der
Schul-Laptop reportlab **und** Pillow — rund 15 MB Pakete, die das Dashboard nie
importiert, und zwei zusätzliche Räder, an denen die Ersteinrichtung scheitern
konnte.

**Seit 2026-09-17 braucht das Dashboard reportlab doch.** Es druckt die
Bücherlisten nach Fach, Verlag und Jahrgang (`GET /buecherliste/{ansicht}/pdf`)
mit `buecherlisten.core`. Damit hatte das Extra seinen Sinn verloren: es sollte
*anderen* Nutzern von `sba-bestand` die 15 MB ersparen, und der einzige andere
Nutzer war das Bestands-CLI — im selben Repo. Seit 2026-09-18 stehen
`reportlab>=4,<5` und `pypdf>=5,<7` deshalb als gewöhnliche Abhängigkeiten in
`pyproject.toml`; `[pdf]` und `uv sync --extra pdf` gibt es nicht mehr. Für
`requirements.txt` und den Schul-Laptop ändert sich dadurch **nichts**: das
Dashboard zog das Extra ohnehin immer mit, reportlab, Pillow und pypdf standen
schon vorher darin. Das Risiko von oben gilt unverändert: findet pip für die
Python-Version des Laptops kein Pillow-Rad, scheitert die Ersteinrichtung.
Prüfpunkt G2-7 in `schul-laptop-test.md`.

## Das eingefrorene Repo `sba-bestand`

Der lokale Ordner `sba-bestand` ist am 2026-09-18 gelöscht worden, das GitHub-Repo
`niklas-mlrr/sba-bestand` **nicht**. Der Grund ist `sba-launcher`: er klont es
(`core/gitops.py`), legt daneben ein eigenes `.venv-bestand` an und startet
`bestand/update_bestand_auto.py` (`core/bestand.py`, `gui/tab_bestand.py`,
`scripts/seed_from_iserv.py`). Ein Löschen oder Archivieren hätte den Launcher
sofort gebrochen.

Damit ist das Repo dort ein **eingefrorener Stand**: Änderungen an
`bestand/core/` in diesem Repo erreichen den Launcher nicht mehr. Wer das
zusammenführen will, hat zwei Wege — den Launcher auf `sba-dashboard` umstellen
(Klon-URL, Venv-Pfad, Skriptpfad in `core/bestand.py`), oder das CLI aus dem
Launcher herauslösen. Bis dahin gilt: eine Korrektur, die auch den
Bestands-Abruf des Launchers betrifft, muss **in beiden** Repos landen.

## Das Programmfenster braucht Tk — und bringt keine Abhängigkeit mit

Das Fenster (seit 2026-09-10, siehe [`architektur.md`](architektur.md#das-programmfenster-warum-der-server-in-den-nebenthread-wanderte))
ist **tkinter** aus der Standardbibliothek. `requirements.txt` ändert sich damit
nicht, und das ist hier keine Kleinigkeit: die Datei ist erzeugt, wird in der CI
gegen `uv export` geprüft, und jede neue Laufzeitabhängigkeit wäre ein weiteres
Paket, das die Ersteinrichtung auf dem Schul-Laptop aus dem Internet holen muss.

Tk ist beim Installer von python.org standardmäßig dabei („tcl/tk and IDLE", in
der Vorauswahl angehakt). Fehlt es — ein abgewähltes Häkchen, eine abgespeckte
Store-Fassung, ein Linux ohne `python3-tk` —, ist das **kein Startfehler**: der
Start fällt auf den Ablauf ohne Fenster zurück und nennt den Grund im Klartext
(`app.fenster.tkinter_verfuegbar`, ausgewertet in `app/start.py`). Ohne Fenster
gibt es dann allerdings keine Anmeldemaske, und damit keinen Abruf ohne
`POST /api/anmeldung` von Hand. Auf dem Schul-Laptop ist das deshalb ein Punkt
der Prüfliste (A2b), nicht eine Annahme.

## Migration

Auf einem Laptop, der schon einmal mit der alten `START.bat` gestartet wurde,
genügt ein Doppelklick auf die neue:

1. `robocopy` spiegelt die geänderten Quellbäume und meldet Änderungen.
2. `requirements.txt` hat sich geändert (reportlab und Pillow sind weg), also
   läuft `pip install -r` erneut. Die beiden nicht mehr benötigten Pakete
   bleiben im venv liegen; das ist Ballast, kein Fehler.
3. Der IServ-Client wird ins venv installiert.
4. Der Start setzt keinen `PYTHONPATH` mehr.

Ein vorhandenes venv muss **nicht** gelöscht werden. Wer sauber anfangen will,
löscht `%LOCALAPPDATA%\sba-dashboard\venv`; der nächste Start legt es neu an.
Die Benutzerkonfiguration und die Arbeitsmappe sind davon nicht betroffen.

## Rollback

Der Weg zurück ist eine Änderung an `START.bat` und sonst nichts:

1. Vor `python -m app.start` wieder
   `set "PYTHONPATH=%CODE%\ausleihe-api"` setzen. (Vor 2026-09-18 stand
   `%CODE%\sba-bestand` mit davor; der Ordner existiert nicht mehr.)
2. Den Abschnitt „3b" (`pip install --no-build-isolation ...`) entfernen oder
   überspringen.
3. `%LOCALAPPDATA%\sba-dashboard\venv` löschen, damit die installierten
   Geschwister-Pakete nicht mehr die gespiegelten Quellbäume überdecken.
   Diesen Schritt nicht vergessen: sonst importiert Python weiter aus
   `site-packages` und ein `PYTHONPATH` sieht wirkungslos aus.

Der Umzug von `atomic_save_workbook` ist davon unabhängig und wird nicht
zurückgerollt — er betrifft nur, aus welchem Modul die Funktion importiert wird.
Wer ihn doch zurückdrehen muss: die Datei `bestand/core/excel_io.py` nach
`ausleihe/inventory_excel.py` zurückkopieren und die drei Importstellen
(`app/excel.py`, `bestand/update_bestand.py`, `bestand/update_bestand_auto.py`)
umbiegen.
