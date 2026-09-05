# Was noch offen ist

Stand: 2026-09-05. Diese Datei löst `PLAN.md` als Arbeitsliste ab; `PLAN.md`
liegt als abgeschlossener v1-Plan in [`archiv/`](archiv/PLAN.md).

Der **Struktur-Backlog** aus dem Review vom 2026-09-05 ist abgearbeitet (unten,
mit dem, was sich dabei geändert hat). Offen bleiben damit nur noch die beiden
**Funktionslücken**, die niemand außer Niklas erledigen kann — allen voran der
Testlauf auf dem Schul-Laptop. Er blockiert die Inbetriebnahme.

## Der Windows-Job hat sofort einen echten Fehler gefunden

Genau dafür war er da. `os.replace` — der letzte Schritt jedes atomaren
Schreibvorgangs — scheitert unter Windows mit `PermissionError` (`WinError 5`),
solange **irgendein** Handle auf die Zieldatei offen ist. Unter POSIX gelingt
dasselbe `rename` klaglos, deshalb konnte das lokal nie auffallen.

Betroffen war der Sidecar-Cache: vier lesende Threads gegen 60 Schreibvorgänge,
und **beide** Speicherorte fielen mit `WinError 5` aus. Das ist kein
Testartefakt — das Dashboard ist ausdrücklich für mehrere gleichzeitige Fenster
gedacht (Prüfliste, Abschnitt G), der Sidecar liegt auf dem Gruppenlaufwerk,
und ein Abruf schreibt ihn genau dann, wenn ein anderes Fenster ihn beim
Seitenaufbau liest. Auf dem Schul-Laptop hätte das gelegentlich die Meldung
„Titel und ISBN konnten diesmal nicht zwischengespeichert werden" erzeugt,
ohne dass etwas kaputt gewesen wäre.

Behoben durch kurzes Wiederholen (`_ersetze_mit_wiederholung`, sieben Versuche
über gut eine halbe Sekunde): ein Leser hält die Datei nur für die Dauer eines
`read()`. Hört der Fehler nicht auf, ist es kein Leser mehr, und der Rückfall
auf den lokalen Ordner greift wie zuvor. Zwei neue Tests stellen den
Windows-Fehler unter POSIX nach, damit beides prüfbar bleibt.

**Dieselbe Ursache traf auch die Leseseite.** Mit der Wiederholung beim
Schreiben war `WinError 5` weg, der nächste Lauf scheiterte im selben Test
aber an einem *leeren* Cache: während `os.replace` läuft, beantwortet Windows
ein `open()` mit einer Zugriffsverletzung, und `_datei_lesen` machte daraus
unter seinem gemeinsamen `except OSError` stillschweigend „kein Cache
vorhanden". Ein Seitenaufbau, der zufällig in einen Abruf fällt, hätte Titel
und ISBN leer gezeigt. Die Leseseite wiederholt jetzt mit denselben Werten.

**Und dieselbe Ursache steckte in der Arbeitsmappe selbst** (`sba-bestand`,
`atomic_save_workbook`) — dort ungefunden, weil die CI nur den Cache
provoziert. Erreichbar ist sie mit Absicht: der Lesepfad (`GET /` und
`/api/rows`) lädt die Mappe **ohne** Sperre, damit ein Leser nie auf einen
Schreiber warten muss; nur der Schreibpfad nimmt `arbeitsmappe_sperren`. Zwei
Fenster — Abschnitt G der Prüfliste — überlappen sich also genau so. Die Folge
wäre nicht nur ein verlorener Schreibvorgang, sondern eine falsche Erklärung:
`app/excel.py` übersetzt jeden `PermissionError` in „Die Datei ist gerade in
Excel geöffnet", und die Lehrkraft hätte Excel geschlossen und dieselbe
Meldung wieder bekommen. Der bestehende Test
`test_lesen_waehrend_des_schreibens_…` trifft den Fall nicht, weil er den Save
*vor* dem Ersetzen anhält.

**Zweiter Befund aus demselben Fehlschlag:** Pytest war auf Windows nach zwei
Minuten fertig, der Prozess lief danach aber weitere zehn Minuten, bis die CI
ihn abbrach. Ursache war der fehlgeschlagene Test selbst — er setzte sein
Stopp-Signal erst *nach* der Schleife, in der die Ausnahme flog, sodass vier
Leser-Threads endlos weiterliefen und der Interpreter beim Beenden auf sie
wartete. Jetzt stehen sie in einem `finally` und sind Daemon-Threads: ein
Fehlschlag kann den Lauf nicht mehr aufhängen. Das ist auch der Grund, warum
`--timeout` je Test hier nicht half — die Tests waren längst durch.

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
demselben Muster (`cell_ref in merged`, Zeilen 70 und 79).

**Wird nicht mehr nachgezogen** (Entscheidung Niklas, 2026-09-05): `sba-launcher`
wird voraussichtlich nicht weiterentwickelt und nicht mehr benutzt. Die Notiz
bleibt als Fundstelle stehen, falls das Repo doch wiederbelebt wird — dann wäre
vor dem Handgriff erst zu messen, ob es dort überhaupt weh tut: im Dashboard lag
der Aufruf auf **jedem** Seitenaufbau und jeder Zellenänderung, in einem
Katalogaufbau läuft er vermutlich einmal.

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

## Struktur-Backlog (Review vom 2026-09-05) — abgearbeitet

Ein Struktur-Review fand 16 Punkte. Alle 16 sind erledigt: sechs in Commit
`24aaa08` (dazu `sba-bestand` `6478e4c`) — der dritte `os.replace`-Ort, die
doppelte Plattform-Ordner-Auflösung, die zwei Formen von
`/api/refresh/status`, die erinnerte Testisolation und zwei Fehler in
`app.js` —, die restlichen zehn danach. Was sich dabei geändert hat, in der
Reihenfolge der Liste:

1. **`Host`- und `Origin`-Prüfung.** Der einzige Punkt, der ein Versprechen
   des Projekts brach und nicht nur die Wartbarkeit. `app/sicherheit.py`:
   `TrustedHostMiddleware` gegen DNS-Rebinding (eine fremde Domain, die auf
   127.0.0.1 zeigt, durfte `/api/rows` lesen **und auswerten**) und eine
   eigene `HerkunftMiddleware` gegen die fremde Seite im Nachbartab, die
   `POST /api/beenden` auslösen konnte. Begründung, Grenzen und die Frage,
   warum ein fehlender `Origin` erlaubt bleibt: `architektur.md`, „Was die
   Bindung allein nicht abdeckt". Der `TestClient` schickt `Host: testserver`
   und braucht seither `base_url="http://127.0.0.1"` (`conftest.py`).
2. **Fehler-auf-HTTP-Abbildung** steht in `app/fehler.py`, einmal statt in
   jeder Route. `BlattFehlt` war vorher im Lesepfad 500 und im Schreibpfad
   503; es ist jetzt überall 500. Neu ist dafür `MappeUngeeignet` (400): eine
   *neu ausgewählte* Datei ohne Raster ist eine Eingabe der Lehrkraft, ein
   fehlendes Blatt in der Arbeitsmappe ein Serverzustand — vorher war beides
   dieselbe Klasse mit zwei Bedeutungen, und genau daran scheiterte eine
   zentrale Abbildung. `GET /` behält seinen eigenen Zweig, weil es HTML
   liefert, benutzt aber dieselben Statuscodes.
3. **`main.py` ist reine Verdrahtung** (75 Zeilen statt 345). Die Routen
   liegen als vier `APIRouter` in `app/api/`, `lies_tabelle` in `app/rows.py`,
   `validiere_excel_mappe` in `app/excel.py`, `lade_einstellungen` in
   `app/konfiguration.py`. Die Dateiliste steht in `architektur.md`,
   „Aufteilung innerhalb von `app/`".
4. **Pydantic-Modelle** in `app/modelle.py` plus **ein**
   `RequestValidationError`-Handler, der auf `{"fehler": "<deutsch>"}` mit
   Status 400 abbildet — nicht auf FastAPIs englisches, schemaförmiges 422.
   Er gibt insbesondere nie den Eingabewert zurück; bei `POST /api/refresh`
   wäre das das Passwort, und ein Test hält das fest.
5. **Die `object`-Notausgänge sind weg.** `Schreibergebnis.ws`/`.eintrag`
   sind `Worksheet` bzw. `GridEntry` ohne `None`-Vorgabe, und `lies_tabelle`
   gibt einen `Tabellenstand` zurück oder `None` — der Leerfall steht damit
   einmal im Rückgabetyp statt viermal im Inhalt.
6. **mypy in der CI**, streng genug, um etwas zu finden: `disallow_untyped_defs`
   (sonst überspringt mypy eine untypisierte Funktion samt Rumpf). Er lief
   auf jedem Runner mit dessen eigener Plattform — nur so wird der
   `msvcrt`-Zweig der Dateisperre überhaupt geprüft. Dafür wechselte
   `app/excel.py` von `os.name == "nt"` auf `sys.platform == "win32"`, die
   Schreibweise, die `app/paths.py` schon benutzte und die als einzige ein
   Typprüfer versteht.
7. **`pytest-cov`** mit `--cov` in den `addopts` (95 % am 2026-09-05, mit
   Zweigmessung). Die Schwelle von 85 % steht **nur** im CI-Aufruf: als
   `fail_under` hätte sie jeden Teillauf während der Arbeit an einer einzelnen
   Datei rot gemacht, und eine Schwelle, die bei richtiger Arbeit anschlägt,
   wird binnen einer Woche abgeschaltet.
8. **`app/static/app.js`** rechnet und rät nichts mehr: sortiert wird über
   `data-wert` an jeder Zelle statt über den angezeigten Text, und `„—"`
   steht als `data-leer` einmal in der Vorlage. `tests/test_oberflaeche.py`
   prüft den Vertrag zwischen Skript und Seite — und liest die Namen dafür
   **aus `app.js` selbst**, sodass eine neue `getElementById`-Zeile
   automatisch eine Prüfung nach sich zieht.
9. **`architektur.md` ist kanonisch.** Das README trägt Routentabelle,
   Schnellstart und Verweise; was in `architektur.md` steht, wiederholt es
   nicht mehr. Die Wiki-Seite fasst zusammen.
10. **`PLAN.md` liegt in `docs/archiv/`** und steht nicht mehr in derselben
    Liste wie die lebenden Dokumente. Zahlen, die jeder Commit falsch machen
    kann („231 Tests", „9,6 s"), stehen weder im README noch in der
    Wiki-Seite.

### Zwei Funde, die dabei angefallen sind

**mypy hat einen echten Laufzeitfehler gefunden, bevor es jemand tat.** Der
Handler für `LaeuftBereits` rief seine Hilfsfunktion als
`_antwort(exc, 409, status=…)` auf — und der Parameter für den Statuscode hieß
ebenfalls `status`. Jeder Aufruf hätte mit `TypeError` abgebrochen. Erreichbar
war der Weg durchaus: `POST /api/refresh` prüft `manager.laeuft()`, aber
zwischen dieser Prüfung und `manager.starte()` liegt die Anmeldung bei IServ,
also eine knappe Sekunde Netz, in der ein zweites Fenster starten kann. Die
Suite hatte den Weg nie genommen, weil die Vorprüfung im Normalfall greift;
jetzt gibt es einen Test dafür.

**Die Abdeckung hat gezeigt, wo die Suite gar nicht hinsah.**
`app/konfiguration.py` stand bei 53 %: der Produktivpfad
`lade_einstellungen(None)` — Standard plus Benutzerkonfiguration, also genau
das, was jeder Start auf dem Schul-Laptop tut — wurde von keinem Test
aufgerufen. Die beiden Ebenen selbst waren geprüft, der Bootstrap darum herum
nicht. `tests/test_konfiguration.py` schließt das.

## Nachtrag: die Paketgrenze zu `bestand.core` (2026-09-05)

Der 17. Punkt, der im Backlog als Anschlussarbeit stand: `bestand.core` war
durchgehend annotiert, lieferte aber kein `py.typed`, und damit waren
`Snapshot`, `GridEntry`, `UpdateResult` und `BestandConfig` für mypy hier
`Any`. Erledigt in `sba-bestand` `e9d0321` und hier.

Erwartet war „zwei Zeilen"; es waren drei Befunde. Der Reihe nach:

**Der Marker allein reichte nicht.** mypy sah `bestand` weiterhin nicht,
py.typed hin oder her — der editable-Install von setuptools stellt das Paket
über einen Import-Finder bereit, nicht über einen Ordner in `site-packages`,
und mypy liest `sys.path`. Erst `mypy_path = "../sba-bestand"` machte die Typen
echt. Geprüft wurde das mit `reveal_type`, nicht am ausbleibenden Fehler — der
erste Lauf nach dem Marker meldete „Success", und das war die falsche Antwort
aus dem richtigen Grund. Begründung: `architektur.md`, „Die Paketgrenze ist
geprüft, nicht nur beschrieben".

**`apply_snapshot` nahm `snapshot` und `config` unannotiert.** Auch mit
gültigem Marker blieb der Aufruf aus `app/refresh.py` deshalb ungeprüft: eine
unannotierte Signatur ist implizit `Any`. Jetzt `snapshot: Snapshot,
config: BestandConfig` — nachgestellt geprüft, dass ein vertauschtes
Argumentpaar auch wirklich auffällt.

**`write_stand(ws, grid, result.stand, result)` war an drei Stellen ein
Typfehler** — hier, in `update_bestand_auto.py` und in `bestand.core` selbst.
`UpdateResult.stand` ist `datetime | None`, weil eine frisch gebaute
`UpdateResult` noch keinen Stand hat (das Dashboard baut eine, um die
Diagnosen von `load_bestellt_counts` hineinzureichen); `write_stand` verlangte
`datetime`. Kein Laufzeitfehler, `apply_snapshot` setzt das Feld immer — aber
die Signatur log, und drei Aufrufer schrieben denselben Fehler ab. Behoben in
der Bibliothek, nicht an den Aufrufstellen: `when` nimmt jetzt `None` und
heißt dann „nimm `result.stand`".

Nebenbei bekam `sba-bestand` seinen eigenen mypy-Lauf. Ohne den wäre `py.typed`
ein Versprechen an jeden Nutzer des Pakets, das dort nichts prüft — ein Bruch
fiele in diesem Repo auf statt in dem, das ihn verursacht. Er fand die zwei
weiteren Kleinigkeiten, die in `e9d0321` mit drinstehen.

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
Auslieferung ohne `PYTHONPATH`, Host- und Origin-Prüfung, zentrale
Fehlerabbildung, CI mit Ruff, mypy, pytest und Abdeckungsmessung auf Linux und
Windows. Wo das jeweils steht, sagt [`architektur.md`](architektur.md).
