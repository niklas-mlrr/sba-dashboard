# Verteilungsgrenze: drei Repos, ein venv

Stand: 2026-09-04. Diese Datei beantwortet eine Frage, die der
Wartbarkeits-Durchgang aufgeworfen hat: **wie kommen `ausleihe-api`,
`sba-bestand` und `sba-dashboard` auf den Schul-Laptop, ohne dass die Anwendung
davon abhängt, wo genau die Ordner liegen?**

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

`ausleihe-api` und `sba-bestand` würden Versionen bekommen, gebaut und
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
  drei Quellbäume wie bisher nach `%LOCALAPPDATA%`, installiert dann aber
  `ausleihe-api` und `sba-bestand` als gewöhnliche (nicht editable) Pakete in
  dasselbe venv:

  ```bat
  pip install --no-build-isolation --no-deps "%CODE%\ausleihe-api" "%CODE%\sba-bestand"
  ```

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

## Migration

Auf einem Laptop, der schon einmal mit der alten `START.bat` gestartet wurde,
genügt ein Doppelklick auf die neue:

1. `robocopy` spiegelt die geänderten Quellbäume und meldet Änderungen.
2. `requirements.txt` hat sich geändert (reportlab und Pillow sind weg), also
   läuft `pip install -r` erneut. Die beiden nicht mehr benötigten Pakete
   bleiben im venv liegen; das ist Ballast, kein Fehler.
3. Die beiden Bibliotheken werden ins venv installiert.
4. Der Start setzt keinen `PYTHONPATH` mehr.

Ein vorhandenes venv muss **nicht** gelöscht werden. Wer sauber anfangen will,
löscht `%LOCALAPPDATA%\sba-dashboard\venv`; der nächste Start legt es neu an.
Die Benutzerkonfiguration und die Arbeitsmappe sind davon nicht betroffen.

## Rollback

Der Weg zurück ist eine Änderung an `START.bat` und sonst nichts:

1. Vor `python -m app.start` wieder
   `set "PYTHONPATH=%CODE%\sba-bestand;%CODE%\ausleihe-api"` setzen.
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
